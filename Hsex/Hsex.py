#!/usr/bin/env python3
"""Hsex single-file crawler.v3 implementation (requests + BeautifulSoup)."""

CRAWLER_NAME = "Hsex"
CRAWLER_PROTOCOL = "crawler.v3"
CRAWLER_FEEDS = '[{"id":"latest","label":"最新","default":true},{"id":"weekly","label":"本周最热"},{"id":"monthly","label":"本月最热"},{"id":"five-min","label":"5分钟以上"},{"id":"long","label":"长视频"},{"id":"hot","label":"当前最热"}]'

import argparse
import copy
import datetime
import json
import os
import queue
import re
import threading
import sys
import time
import traceback
import unicodedata
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.util import Timeout

BASE_URL = "https://hsex.icu"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
ERROR_CODES = {"not_found", "parse_failed", "auth_required", "rate_limited", "source_unavailable"}


def utf8_prefix(value, maximum):
    return str(value).encode("utf-8")[:maximum].decode("utf-8", errors="ignore")


def identifier(value, name):
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value.encode("utf-8")) > 512
            or any(unicodedata.category(char) == "Cc" for char in value)):
        raise ValueError(name + " must be a nonempty 1-512 byte identifier")
    return value


def http_url(value):
    if not isinstance(value, str) or len(value.encode("utf-8")) > 8192:
        raise ValueError("invalid HTTP(S) URL")
    parsed = urlparse(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or any(char.isspace() or unicodedata.category(char) == "Cc" for char in value)):
        raise ValueError("invalid HTTP(S) URL")
    parsed.port
    return value


def protocol_headers(headers):
    if not isinstance(headers, dict) or len(headers) > 64:
        raise ValueError("headers must be an object with at most 64 entries")
    clean = {}
    for name, value in headers.items():
        if (not isinstance(name, str) or len(name.encode("utf-8")) > 256
                or not re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", name)
                or not isinstance(value, str) or len(value.encode("utf-8")) > 8192
                or any(char in value for char in "\r\n\0")):
            raise ValueError("invalid HTTP header")
        clean[name] = value
    return clean


class ProtocolError(Exception):
    def __init__(self, scope, code, message, retryable=False, retry_after_seconds=None):
        super().__init__(message)
        if scope not in {"item", "source"} or code not in ERROR_CODES:
            raise ValueError("invalid protocol error")
        self.fields = {"scope": scope, "code": code,
                       "message": utf8_prefix(message, 8192) or "操作失败",
                       "retryable": bool(retryable)}
        if retry_after_seconds is not None:
            self.fields["retry_after_seconds"] = max(0, min(86400, int(retry_after_seconds)))


# Compatibility name used by the upstream protocol regression suite.
SourceError = ProtocolError


def retry_after(value):
    if not value:
        return None
    try:
        return max(0, min(86400, int(value)))
    except (TypeError, ValueError):
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=datetime.timezone.utc)
            return max(0, min(86400, int((when - datetime.datetime.now(datetime.timezone.utc)).total_seconds())))
        except (TypeError, ValueError, OverflowError):
            return None


class CommandDeadline:
    def __init__(self, deadline_at, scope):
        if not isinstance(deadline_at, str):
            raise ValueError("deadline_at must be a timezone-aware string")
        try:
            deadline = datetime.datetime.fromisoformat(deadline_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("invalid deadline_at") from error
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            raise ValueError("deadline_at must include a timezone")
        self.end = time.monotonic() + (deadline - datetime.datetime.now(datetime.timezone.utc)).total_seconds() - 0.05
        self.scope = scope
        self.cancelled = threading.Event()

    def remaining(self):
        seconds = self.end - time.monotonic()
        if self.cancelled.is_set() or seconds <= 0:
            raise ProtocolError(self.scope, "source_unavailable", "操作截止时间已到", True)
        return seconds

    def timeout(self, cap=30):
        total = min(float(cap), self.remaining())
        return Timeout(connect=min(10.0, total), read=total, total=total)


def url_origin(value):
    parsed = urlparse(http_url(value))
    return parsed.scheme.lower(), parsed.hostname.lower(), parsed.port or (443 if parsed.scheme == "https" else 80)


def parse_duration(text):
    text = str(text or "").strip()
    if not re.fullmatch(r"[0-9]+(?::[0-5][0-9]){1,2}", text):
        return None
    total = 0
    for part in text.split(":"):
        total = total * 60 + int(part)
    return total if 0 <= total <= 604800 else None


def validate_job(job):
    if not isinstance(job, dict):
        raise ValueError("job must be an object")
    if job.get("protocol") != CRAWLER_PROTOCOL:
        raise ValueError("unsupported protocol")
    for field in ("task_id", "crawler_id"):
        identifier(job.get(field), field)
    feeds = {entry["id"] for entry in json.loads(CRAWLER_FEEDS)}
    if not isinstance(job.get("feed_id"), str) or job["feed_id"] not in feeds:
        raise ValueError("unsupported feed_id")
    if not isinstance(job.get("work_dir"), str) or not os.path.isabs(job["work_dir"]):
        raise ValueError("work_dir must be an absolute path")
    for field in ("config", "network"):
        if field not in job:
            job[field] = {}
        if not isinstance(job[field], dict):
            raise ValueError(field + " must be an object")
    proxy = job["network"].get("proxy_url")
    if proxy is not None and (not isinstance(proxy, str) or not proxy.strip()
                              or len(proxy.encode("utf-8")) > 8192
                              or any(char in proxy for char in "\r\n\0")):
        raise ValueError("network.proxy_url must be a nonempty string")
    return job


def load_object(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError("invalid JSON constant: " + value)
    result = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(result, dict):
        raise ValueError("JSON value must be an object")
    return result


FEED_PATHS = {"latest": "list", "weekly": "top7_list", "monthly": "top_list",
              "five-min": "5min_list", "long": "long_list", "hot": "hot_list"}
MAX_BODY = 8 * 1024 * 1024
# Keep pathological DOMs from leaving expensive abandoned parser workers.
MAX_HTML_MARKERS = 20000
REQUEST_INTERVAL = 0.25


def run_before_deadline(operation, deadline, launched=None):
    """Bound the caller's wait, including parsing/serialization and stalled I/O.

    Callers must isolate mutable operation state until this function succeeds.
    """
    outcomes = queue.Queue(maxsize=1)

    def execute():
        try:
            outcomes.put((operation(), None))
        except Exception as error:
            outcomes.put((None, error))

    deadline.remaining()
    threading.Thread(target=execute, daemon=True).start()
    if launched is not None:
        launched.set()
    try:
        value, error = outcomes.get(timeout=deadline.remaining())
    except queue.Empty:
        deadline.cancelled.set()
        raise ProtocolError(deadline.scope, "source_unavailable", "操作截止时间已到", True)
    deadline.remaining()
    if error is not None:
        raise error
    return value


class CrawlerV3:
    def __init__(self, job):
        self.job = validate_job(job)
        self.feed_id = job["feed_id"]
        self.config = job["config"]
        self.base_url = http_url(self.config.get("base_url", BASE_URL)).rstrip("/")
        base = urlparse(self.base_url)
        if base.path or base.params or base.query or base.fragment:
            raise ValueError("config.base_url must be an HTTP(S) origin, without a path/query/fragment")
        self.origin = url_origin(self.base_url)
        self.media_headers = self._download_headers("media_headers")
        self.thumbnail_headers = self._download_headers("thumbnail_headers")
        self.pages, self.rows, self.page_urls = {}, {}, {}
        self.last_request = 0.0
        self._operation_lock = threading.Lock()
        self._rate_lock = threading.Lock()
        self._rate_time = [0.0]
        self._prepared_line = None

    def _download_headers(self, name):
        headers = {"User-Agent": USER_AGENT}
        overrides = protocol_headers(self.config.get(name, {}))
        # Header names are case-insensitive, including overrides of User-Agent.
        for key, value in overrides.items():
            headers = {k: v for k, v in headers.items() if k.lower() != key.lower()}
            headers[key] = value
        return protocol_headers(headers)

    def close(self):
        pass  # Transport workers own and close their Sessions independently.

    def _same_origin(self, url):
        return url_origin(url) == self.origin

    def _request(self, url, deadline, scope):
        url = http_url(url)
        if not self._same_origin(url):
            raise ValueError("source requests must stay on config.base_url")
        if not self._rate_lock.acquire(timeout=deadline.remaining()):
            deadline.remaining()
            raise ProtocolError(scope, "source_unavailable", "请求间隔等待超时", True)
        try:
            deadline.remaining()
            delay = max(0.0, REQUEST_INTERVAL - (time.monotonic() - max(self.last_request, self._rate_time[0])))
            if delay:
                if deadline.remaining() <= delay + 0.01:
                    raise ProtocolError(scope, "source_unavailable", "截止时间不足以等待请求间隔", True)
                if deadline.cancelled.wait(delay):
                    deadline.remaining()
            deadline.remaining()
            self._rate_time[0] = time.monotonic()
            self.last_request = self._rate_time[0]
        finally:
            self._rate_lock.release()
        return run_before_deadline(lambda: self._fetch(url, deadline, scope), deadline)

    def _fetch(self, url, deadline, scope):
        current, visited = url, set()
        expected_path = urlparse(url).path
        with requests.Session() as session:
            session.mount("http://", requests.adapters.HTTPAdapter(max_retries=0))
            session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
            session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html",
                                    "Accept-Language": "zh-CN,zh;q=0.9"})
            proxy = self.job["network"].get("proxy_url")
            if proxy:
                session.trust_env = False
                session.proxies.update({"http": proxy, "https": proxy})
            for _ in range(10):
                deadline.remaining()
                if current in visited:
                    raise ProtocolError(scope, "source_unavailable", "源站重定向循环", True)
                visited.add(current)
                try:
                    with session.get(current, timeout=deadline.timeout(), allow_redirects=False,
                                     stream=True) as response:
                        deadline.remaining()
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("Location")
                            if not location:
                                raise ProtocolError(scope, "parse_failed", "重定向缺少 Location")
                            try:
                                target = http_url(urljoin(current, location))
                                if not self._same_origin(target) or urlparse(target).path != expected_path:
                                    raise ValueError("redirect changed the requested content identity")
                            except ValueError as error:
                                raise ProtocolError(scope, "parse_failed", str(error)) from error
                            current = target
                            continue
                        if response.status_code >= 400:
                            code = {401: "auth_required", 403: "auth_required", 404: "not_found",
                                    410: "not_found", 429: "rate_limited"}.get(response.status_code, "source_unavailable")
                            error_scope = "source" if code in {"auth_required", "rate_limited"} else scope
                            retryable = code in {"rate_limited", "source_unavailable"}
                            raise ProtocolError(error_scope, code, "源站返回 HTTP %d" % response.status_code,
                                                retryable, retry_after(response.headers.get("Retry-After"))
                                                if retryable else None)
                        chunks, size = [], 0
                        for chunk in response.iter_content(65536):
                            deadline.remaining()
                            size += len(chunk)
                            if size > MAX_BODY:
                                raise ProtocolError(scope, "parse_failed", "源站响应超过 8 MiB")
                            chunks.append(chunk)
                        deadline.remaining()
                        return b"".join(chunks).decode("utf-8", errors="replace")
                except requests.RequestException as error:
                    raise ProtocolError(scope, "source_unavailable", "源站网络请求失败", True) from error
        raise ProtocolError(scope, "source_unavailable", "源站重定向过多", True)

    def _page_url(self, page):
        return self.page_urls.get(page, self.base_url + "/%s-%d.htm" % (FEED_PATHS[self.feed_id], page))

    def _listing_page_number(self, url):
        parsed = urlparse(http_url(url))
        match = re.fullmatch(r"/" + re.escape(FEED_PATHS[self.feed_id]) + r"-([0-9]+)\.htm", parsed.path)
        if not self._same_origin(url) or parsed.params or parsed.fragment or not match or int(match[1]) < 1:
            raise ValueError("pagination link must stay on the same site and feed")
        return int(match[1])

    def _pagination(self, soup, page, page_url):
        pagers = soup.select("ul.pagination1")
        if not pagers:
            raise ProtocolError("source", "parse_failed", "列表缺少可识别的分页结构")
        targets = []
        for pager in pagers:
            active = pager.select_one("li.active a[href]")
            if not active:
                raise ProtocolError("source", "parse_failed", "分页缺少当前页")
            try:
                if self._listing_page_number(urljoin(page_url, active["href"])) != page:
                    raise ValueError("pagination active page does not match cursor")
                links = [link for link in pager.select("a[href]") if link.get_text(strip=True) == "▶"]
                next_urls = {http_url(urljoin(page_url, link["href"])) for link in links}
                if len(next_urls) > 1:
                    raise ValueError("conflicting next links")
                target = next(iter(next_urls), None)
                if target is not None and self._listing_page_number(target) <= page:
                    raise ValueError("next link must advance the current page")
                targets.append(target)
            except ValueError as error:
                raise ProtocolError("source", "parse_failed", str(error)) from error
        if len(set(targets)) != 1:
            raise ProtocolError("source", "parse_failed", "上下分页链接不一致")
        target = targets[0]
        return (self._listing_page_number(target), target) if target else (None, None)

    @staticmethod
    def _parse_html(text, scope):
        # C-level counting is cheap even at the body cap; BeautifulSoup DOM
        # construction/selection on 100k tiny tags is not. This is a structural
        # safety bound, not a page/candidate budget.
        if len(text) > MAX_BODY or text.count("<") > MAX_HTML_MARKERS:
            raise ProtocolError(scope, "parse_failed", "HTML 结构过于复杂或响应过大")
        return BeautifulSoup(text, "html.parser")

    def _parse_listing(self, text, page, page_url):
        soup = self._parse_html(text, "source")
        if not soup.select_one(".row.body"):
            raise ProtocolError("source", "parse_failed", "无法识别列表页结构")
        next_page, next_url = self._pagination(soup, page, page_url)
        rows = []
        cards = soup.select(".row.body .thumbnail")
        for card in cards:
            native = None
            for link in card.find_all("a", href=True, recursive=False):
                url = urljoin(page_url, link["href"])
                try:
                    parsed = urlparse(http_url(url))
                    match = re.fullmatch(r"/video-([0-9]+)\.htm", parsed.path)
                    if self._same_origin(url) and match and not (parsed.query or parsed.fragment or parsed.params):
                        native = match[1]
                        break
                except ValueError:
                    continue
            if native is None:
                continue
            identifier(native, "source_id")
            title = card.select_one(".caption.title h5 a")
            image = card.select_one(".image[style]")
            thumb = ""
            if image:
                match = re.search(r"background-image\s*:\s*url\(\s*(?:'([^']*)'|\"([^\"]*)\"|([^)]*))\s*\)",
                                  image["style"], re.I)
                if match:
                    thumb = urljoin(page_url, next((v for v in match.groups() if v is not None), "").strip())
                    try:
                        http_url(thumb)
                    except ValueError:
                        thumb = ""
            duration = card.select_one("var.duration")
            author = None
            for node in card.select(".info a[href]"):
                parsed = urlparse(urljoin(page_url, node["href"]))
                if parsed.path == "/user.htm" and re.search(r"(?:^|&)author=", parsed.query):
                    author = node.get_text(" ", strip=True)
                    break
            rows.append({"id": native, "title": title.get_text(" ", strip=True) if title else "",
                         "thumbnail_url": thumb, "author": author or "",
                         "duration_seconds": parse_duration(duration.get_text(strip=True)) if duration else None})
        if cards and not rows:
            raise ProtocolError("source", "parse_failed", "无法识别列表候选")
        return rows, next_page, next_url

    def _execute(self, command, scope, kind, operation):
        deadline = CommandDeadline(command.get("deadline_at"), scope)
        deadline.remaining()
        # Retain the lock until an abandoned worker actually finishes: subsequent
        # commands cannot accumulate concurrent CPU parsers. stop bypasses it.
        if not self._operation_lock.acquire(timeout=deadline.remaining()):
            deadline.remaining()
            raise ProtocolError(scope, "source_unavailable", "上一操作尚未结束", True)
        finished = threading.Event()
        release_lock = threading.Lock()
        released = False

        def release_once():
            nonlocal released
            with release_lock:
                if not released:
                    released = True
                    self._operation_lock.release()

        def transaction():
            try:
                isolated = copy.copy(self)
                isolated.pages = dict(self.pages)
                isolated.rows = dict(self.rows)
                isolated.page_urls = dict(self.page_urls)
                result = operation(isolated, command, deadline)
                # Include complete response preparation in the timed worker;
                # serve_job writes this already serialized line, without doing
                # potentially expensive duplicate JSON encoding on the main thread.
                response = {"type": kind, "request_id": command.get("request_id", "invalid-request"), **result}
                line = json.dumps(response, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
                size = len(line.encode("utf-8"))
                if size > 1024 * 1024:
                    raise ValueError("protocol response exceeds 1 MiB")
                deadline.remaining()
                return result, line, size, isolated
            finally:
                finished.set()
                if deadline.cancelled.is_set():
                    release_once()

        launched = threading.Event()
        try:
            deadline.remaining()
            result, line, size, isolated = run_before_deadline(transaction, deadline, launched)
            deadline.remaining()
            # Only the command caller can publish state. A timed-out transaction,
            # even if parsing later completes, has no path to these assignments.
            self.pages, self.rows, self.page_urls = isolated.pages, isolated.rows, isolated.page_urls
            self._prepared_line = (line, size)
            return result
        finally:
            deadline.cancelled.set()
            if finished.is_set() or not launched.is_set():
                release_once()

    def discover(self, command):
        return self._execute(command, "source", "page", CrawlerV3._discover)

    def _discover(self, command, deadline):
        if "cursor" not in command or "limit" not in command or "deadline_at" not in command:
            raise ValueError("discover requires cursor, limit and deadline_at")
        deadline.remaining()
        limit = command["limit"]
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        if command["cursor"] is None:
            page, offset = 1, 0
        else:
            cursor = identifier(command["cursor"], "cursor")
            match = re.fullmatch(r"page:([1-9][0-9]*):(0|[1-9][0-9]*)", cursor)
            if not match:
                raise ValueError("invalid cursor")
            page, offset = map(int, match.groups())
        if page not in self.pages:
            url = self._page_url(page)
            rows, next_page, next_url = self._parse_listing(self._request(url, deadline, "source"), page, url)
            previous = {key for number, state in self.pages.items() if number < page for key in state["source_ids"]}
            items, local = [], set()
            for row in rows:
                native = row["id"]
                if native not in previous and native not in local:
                    items.append({"discovery_key": identifier("video:" + native, "discovery_key"),
                                  "source_id": native, "locator": {"id": native}})
                local.add(native)
            deadline.remaining()
            if next_page is not None:
                old_url = self.page_urls.get(next_page)
                if old_url is not None and old_url != next_url:
                    raise ProtocolError("source", "parse_failed", "下一页地址发生冲突")
                self.page_urls[next_page] = next_url
            for row in rows:
                self.rows.setdefault(row["id"], row)
            self.pages[page] = {"items": items, "source_ids": local, "next_page": next_page}
        state = self.pages[page]
        if offset > len(state["items"]):
            raise ValueError("cursor offset exceeds cached page")
        selected = state["items"][offset:offset + limit]
        end = offset + len(selected)
        next_cursor = ("page:%d:%d" % (page, end) if end < len(state["items"])
                       else "page:%d:0" % state["next_page"] if state["next_page"] else None)
        deadline.remaining()
        return {"items": selected, "next_cursor": next_cursor}

    def _media(self, url, thumbnail=False):
        return {"type": "url", "url": http_url(url),
                "headers": dict(self.thumbnail_headers if thumbnail else self.media_headers)}

    def resolve(self, command):
        return self._execute(command, "item", "item", CrawlerV3._resolve)

    def _resolve(self, command, deadline):
        deadline.remaining()
        candidate = command.get("candidate")
        if not isinstance(candidate, dict):
            raise ValueError("candidate must be an object")
        key = identifier(candidate.get("discovery_key"), "discovery_key")
        locator = candidate.get("locator")
        if not isinstance(locator, dict) or len(json.dumps(locator, ensure_ascii=False).encode("utf-8")) > 16384:
            raise ValueError("locator must be an object no larger than 16 KiB")
        native = identifier(locator.get("id"), "locator.id")
        if not re.fullmatch(r"[0-9]+", native):
            raise ValueError("locator.id must be a native numeric video ID")
        source_id = identifier(candidate.get("source_id", native), "source_id")
        # Never fetch a caller-supplied locator URL: native ID alone selects content.
        detail = self.base_url + "/video-" + native + ".htm"
        soup = self._parse_html(self._request(detail, deadline, "item"), "item")

        def meta(name):
            node = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            return str(node.get("content", "")).strip() if node else ""

        identity = meta("og:url")
        if identity:
            try:
                parsed = urlparse(http_url(urljoin(detail, identity)))
                if not self._same_origin(urljoin(detail, identity)) or parsed.path != urlparse(detail).path:
                    raise ValueError("detail identity does not match locator.id")
            except ValueError as error:
                raise ProtocolError("item", "parse_failed", str(error)) from error
        video = soup.select_one("video#video-play")
        source = video.select_one("source#video-source[src]") if video else None
        if source is None:
            raise ProtocolError("item", "parse_failed", "详情缺少原生视频源")
        try:
            # HTML parsing unescapes attributes once; do not decode/rewrite signed paths or queries.
            media = self._media(source["src"])
        except ValueError as error:
            raise ProtocolError("item", "parse_failed", "详情媒体 URL 无效") from error
        row = self.rows.get(native, {})
        node = soup.select_one(".panel-heading h3.panel-title")
        title = (node.get_text(" ", strip=True) if node else "") or meta("og:title") or row.get("title", "")
        title = utf8_prefix(title.strip(), 4096)
        if not title:
            raise ProtocolError("item", "parse_failed", "详情缺少标题")
        result = {"discovery_key": key, "source_id": source_id, "title": title,
                  "detail_url": detail, "media": media}
        for thumb in (video.get("poster"), meta("og:image"), row.get("thumbnail_url")):
            if thumb:
                try:
                    result["thumbnail"] = self._media(urljoin(detail, thumb), thumbnail=True)
                    break
                except ValueError:
                    continue
        author = meta("og:video:actor") or row.get("author", "")
        if author:
            result["author"] = utf8_prefix(author, 1024)
        description = meta("description") or meta("og:description")
        if description:
            result["description"] = utf8_prefix(description, 64 * 1024)
        duration = parse_duration(meta("video:duration"))
        if duration is None:
            duration = row.get("duration_seconds")
        if type(duration) is int and 0 <= duration <= 604800:
            result["duration_seconds"] = duration
        deadline.remaining()
        return result


# Compatibility with the upstream class name.
Crawler = CrawlerV3


class ProtocolWriter:
    def __init__(self):
        self.total = 0

    def write(self, response, prepared=None):
        if prepared is None:
            line = json.dumps(response, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
            size = len(line.encode("utf-8"))
        else:
            line, size = prepared
        if size > 1024 * 1024:
            raise ValueError("protocol response exceeds 1 MiB")
        if self.total + size > 64 * 1024 * 1024:
            raise ValueError("protocol stdout exceeds 64 MiB")
        sys.stdout.write(line)
        sys.stdout.flush()
        self.total += size


def _error_response(request_id, scope, error):
    if isinstance(error, ProtocolError):
        fields = error.fields
    else:
        traceback.print_exc(file=sys.stderr)
        fields = {"scope": scope, "code": "parse_failed",
                  "message": utf8_prefix(error, 8192) or "命令解析失败", "retryable": False}
    return {"type": "error", "request_id": request_id, **fields}


def serve_job(job_path):
    with open(job_path, "r", encoding="utf-8") as handle:
        job = validate_job(load_object(handle.read()))
    proxy = job["network"].get("proxy_url")
    if proxy:
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ[name] = proxy
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = ""
    crawler = CrawlerV3(job)
    writer = ProtocolWriter()
    try:
        while True:
            line = sys.stdin.readline(1024 * 1024 + 1)
            if not line:
                raise EOFError("stdin closed before stop")
            if len(line.encode("utf-8")) > 1024 * 1024:
                while line and not line.endswith("\n"):
                    line = sys.stdin.readline(1024 * 1024 + 1)
                writer.write(_error_response("invalid-request", "source",
                                             ValueError("command exceeds 1 MiB")))
                continue
            command = None
            try:
                command = load_object(line)
                request_id = identifier(command.get("request_id"), "request_id")
            except Exception as error:
                traceback.print_exc(file=sys.stderr)
                raw_id = command.get("request_id") if isinstance(command, dict) else "invalid-request"
                try:
                    raw_id = identifier(raw_id, "request_id")
                except ValueError:
                    raw_id = "invalid-request"
                writer.write(_error_response(raw_id, "source", error))
                command = None
                continue
            kind = command.get("type")
            if kind == "stop":
                writer.write({"type": "stopped", "request_id": request_id})
                return
            scope = "source" if kind == "discover" else "item"
            try:
                if kind == "discover":
                    response = {"type": "page", "request_id": request_id, **crawler.discover(command)}
                elif kind == "resolve":
                    response = {"type": "item", "request_id": request_id, **crawler.resolve(command)}
                else:
                    raise ValueError("unknown command type")
                prepared = crawler._prepared_line
            except Exception as error:
                response = _error_response(request_id, scope, error)
                prepared = None
            writer.write(response, prepared=prepared)
    finally:
        crawler.close()


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Hsex crawler.v3")
    parser.add_argument("--job", required=True, help="crawler.v3 job JSON absolute path")
    arguments = parser.parse_args()
    serve_job(arguments.job)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        os._exit(0)
