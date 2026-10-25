#!/usr/bin/env python3
"""Xhotlist single-file crawler.v3. Dependencies: requests, beautifulsoup4, lxml."""

CRAWLER_NAME = "Xhotlist"
CRAWLER_PROTOCOL = "crawler.v3"
CRAWLER_FEEDS = '[{"id":"latest","label":"最新","default":true},{"id":"tag","label":"标签筛选"}]'

import argparse
import datetime
import html as htmlmod
import json
import os
import queue
import random
import re
import sys
import threading
import time
import traceback
import unicodedata
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.util import Timeout

BASE_URL = "https://xhotvideo.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
MIN_DELAY = 1.0
MAX_DELAY = 3.0
MAX_BODY = 8 * 1024 * 1024
TWITTER_HEADERS = {"User-Agent": USER_AGENT, "Referer": "https://x.com/", "Origin": "https://x.com", "Accept": "*/*"}


def utf8_prefix(value, size):
    return str(value).encode("utf-8")[:size].decode("utf-8", errors="ignore")


def identifier(value, name):
    if (not isinstance(value, str) or not value or value != value.strip()
            or len(value.encode("utf-8")) > 512
            or any(unicodedata.category(char) == "Cc" for char in value)):
        raise ValueError(name + " must be a 1-512 byte identifier")
    return value


def http_url(value):
    if not isinstance(value, str) or len(value.encode("utf-8")) > 8192:
        raise ValueError("Invalid HTTP(S) URL")
    parsed = urlparse(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or any(char.isspace() or unicodedata.category(char) == "Cc" for char in value)):
        raise ValueError("Invalid HTTP(S) URL")
    parsed.port
    return value


def protocol_headers(headers):
    if not isinstance(headers, dict) or len(headers) > 64:
        raise ValueError("headers must be an object with at most 64 entries")
    for name, value in headers.items():
        if (not isinstance(name, str) or len(name.encode("utf-8")) > 256
                or not re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", name)
                or not isinstance(value, str) or len(value.encode("utf-8")) > 8192
                or any(char in value for char in "\r\n\0")):
            raise ValueError("Invalid HTTP header")
    return dict(headers)


def url_origin(value):
    parsed = urlparse(http_url(value))
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme.lower(), parsed.hostname.lower(), port


def twitter_video_url(value):
    value = http_url(value)
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname.lower() != "video.twimg.com":
        raise ValueError("Unsupported Twitter video host")
    return value


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


class ProtocolError(Exception):
    def __init__(self, scope, code, message, retryable=False, retry_after_seconds=None):
        super().__init__(message)
        self.fields = {"scope": scope, "code": code,
                       "message": utf8_prefix(message, 8192) or "操作失败",
                       "retryable": bool(retryable)}
        if retry_after_seconds is not None:
            self.fields["retry_after_seconds"] = max(0, min(86400, int(retry_after_seconds)))


SourceError = ProtocolError


class CommandDeadline:
    def __init__(self, deadline_at, scope):
        if not isinstance(deadline_at, str):
            raise ValueError("deadline_at must be a string")
        try:
            parsed = datetime.datetime.fromisoformat(deadline_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("deadline_at must be an ISO-8601 timestamp") from error
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("deadline_at must include a timezone")
        seconds = (parsed - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        self.expires_at = time.monotonic() + seconds - 0.05
        self.scope = scope
        self.cancelled = threading.Event()

    def remaining(self):
        seconds = self.expires_at - time.monotonic()
        if self.cancelled.is_set() or seconds <= 0:
            raise ProtocolError(self.scope, "source_unavailable", "命令截止时间已到", True)
        return seconds

    def polite_sleep(self):
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        if self.remaining() <= delay + 0.05:
            raise ProtocolError(self.scope, "source_unavailable", "命令截止时间不足以等待请求间隔", True)
        time.sleep(delay)
        self.remaining()


def run_before_deadline(operation, deadline, *args):
    outcomes = queue.Queue(maxsize=1)
    def execute():
        try:
            outcomes.put((operation(*args, deadline), None))
        except Exception as error:
            outcomes.put((None, error))
    deadline.remaining()
    threading.Thread(target=execute, daemon=True).start()
    try:
        result, error = outcomes.get(timeout=deadline.remaining())
    except queue.Empty:
        deadline.cancelled.set()
        raise ProtocolError(deadline.scope, "source_unavailable", "命令截止时间已到", True)
    deadline.remaining()
    if error is not None:
        raise error
    return result


def parse_duration(text):
    parts = str(text or "").strip().split(":")
    if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
        return None
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total if total <= 604800 else None


def parse_play_count(text):
    match = re.search(r"([\d.]+)\s*([KMkm万])?", str(text or ""))
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    suffix = (match.group(2) or "").upper()
    number *= 1000 if suffix == "K" else 1000000 if suffix == "M" else 10000 if suffix == "万" else 1
    return int(number)


def parse_listing_page(text, base_url):
    soup = text if isinstance(text, BeautifulSoup) else BeautifulSoup(text, "lxml")
    rows, seen = [], set()
    for card in soup.select("a.video-card"):
        match = re.search(r"/video/([^/?#]+)", card.get("href", ""))
        if not match or match.group(1) in seen:
            continue
        source_id = match.group(1)
        seen.add(source_id)
        image = card.select_one("span.thumb img")
        thumbnail = (image.get("src") or image.get("data-src") or "") if image else ""
        duration = card.select_one("span.duration")
        metadata = card.select_one("span.card-meta")
        rows.append({"id": source_id, "title": source_id,
                     "detail_url": urljoin(base_url, card["href"]),
                     "thumbnail_url": urljoin(base_url, thumbnail) if thumbnail else "",
                     "duration_seconds": parse_duration(duration.get_text(strip=True)) if duration else None,
                     "views": parse_play_count(metadata.get_text(" ", strip=True)) if metadata else None})
    return rows


def parse_detail_page(text):
    soup = BeautifulSoup(text, "lxml")
    media_urls = []
    for node in soup.select("video source[src], video[src]"):
        address = htmlmod.unescape(node.get("src", "").strip())
        try:
            address = twitter_video_url(address)
        except ValueError:
            continue
        if address not in media_urls:
            media_urls.append(address)
    for address in re.findall(r'https://video\.twimg\.com/[^"\'\s<>]+?\.mp4(?:\?[^"\'\s<>]*)?', htmlmod.unescape(text)):
        try:
            address = twitter_video_url(address)
        except ValueError:
            continue
        if address not in media_urls:
            media_urls.append(address)
    result = {"media_urls": media_urls}
    title = soup.select_one("h1")
    if title:
        result["title"] = title.get_text(" ", strip=True)
    metadata = soup.select_one(".meta-row")
    if metadata:
        value = metadata.get_text(" ", strip=True)
        duration = re.search(r"时长\s*([\d:]+)", value)
        views = re.search(r"播放\s*([\d.]+[KM万]?)", value)
        if duration:
            result["duration_seconds"] = parse_duration(duration.group(1))
        if views:
            result["views"] = parse_play_count(views.group(1))
    result["tags"] = list(dict.fromkeys(
        node.get_text(strip=True).lstrip("#").strip()
        for node in soup.select(".tags a, .tag a, a[href^='/videos/tag/']")
        if node.get_text(strip=True).lstrip("#").strip()))
    return result


class HttpClient:
    def __init__(self, job):
        self.headers = {"User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8"}
        self.custom_headers = protocol_headers(job.get("config", {}).get("headers", {}))
        source_base = job.get("config", {}).get("base_url", BASE_URL)
        self.source_origin = url_origin(source_base)
        proxy = job.get("network", {}).get("proxy_url")
        self.proxies = {"http": proxy, "https": proxy} if proxy else {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.lock = threading.Lock()

    def close(self):
        pass

    def request(self, url, deadline, scope, referer=None, headers=None, body_limit=MAX_BODY,
                truncate=False, media_probe=False):
        current = http_url(url)
        with requests.Session() as session:
            session.mount("http://", requests.adapters.HTTPAdapter(max_retries=0))
            session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
            session.headers.update(self.headers)
            session.proxies.update(self.proxies)
            with self.lock:
                session.cookies.update(self.cookies)
            for _ in range(11):
                deadline.polite_sleep()
                request_headers = dict(headers or {})
                if referer:
                    request_headers["Referer"] = referer
                if url_origin(current) == self.source_origin:
                    request_headers.update(self.custom_headers)
                try:
                    with session.get(current, headers=request_headers,
                                     timeout=Timeout(total=min(30, deadline.remaining())),
                                     stream=True, allow_redirects=False) as response:
                        deadline.remaining()
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("Location")
                            if not location:
                                raise ProtocolError(scope, "parse_failed", "重定向缺少 Location")
                            current = http_url(urljoin(current, location))
                            continue
                        if response.status_code >= 400:
                            status = response.status_code
                            code = ({403: "not_found"}.get(status) if media_probe else None)
                            code = code or {401: "auth_required", 403: "auth_required", 404: "not_found",
                                            410: "not_found", 429: "rate_limited"}.get(status, "source_unavailable")
                            error_scope = "source" if code in {"auth_required", "rate_limited"} else scope
                            raise ProtocolError(error_scope, code, "源站返回 HTTP %d" % status,
                                                code in {"rate_limited", "source_unavailable"},
                                                retry_after(response.headers.get("Retry-After"))
                                                if code in {"rate_limited", "source_unavailable"} else None)
                        chunks, size = [], 0
                        for chunk in response.iter_content(65536):
                            deadline.remaining()
                            if truncate and size + len(chunk) > body_limit:
                                chunks.append(chunk[:body_limit - size])
                                size = body_limit
                                break
                            size += len(chunk)
                            if size > body_limit:
                                raise ProtocolError(scope, "parse_failed", "源站响应过大")
                            chunks.append(chunk)
                        with self.lock:
                            deadline.remaining()
                            self.cookies.update(session.cookies)
                        return response.status_code, response.headers, b"".join(chunks)
                except requests.exceptions.RequestException as error:
                    raise ProtocolError(scope, "source_unavailable", "源站网络请求失败", True) from error
        raise ProtocolError(scope, "source_unavailable", "源站重定向次数过多", True)

    def fetch_text(self, url, deadline, scope, referer=None):
        return self.request(url, deadline, scope, referer)[2].decode("utf-8", errors="replace")

    def probe_media(self, url, deadline):
        headers = dict(TWITTER_HEADERS)
        headers["Range"] = "bytes=0-0"
        url = twitter_video_url(url)
        _, response_headers, body = self.request(url, deadline, "item", headers=headers,
                                                  body_limit=4096, truncate=True, media_probe=True)
        content_type = (response_headers.get("Content-Type") or "").lower()
        first = body[:256].lstrip().lower()
        if (not body or any(value in content_type for value in ("text/html", "application/json", "text/plain"))
                or first.startswith((b"<html", b"<!doctype", b'{"error', b"error"))):
            raise ProtocolError("item", "parse_failed", "Twitter 媒体地址未返回视频内容")

    def media_object(self, url, twitter=False, referer=None):
        url = http_url(url)
        if twitter and urlparse(url).hostname.lower() not in {"video.twimg.com", "pbs.twimg.com"}:
            raise ValueError("Unsupported Twitter media host")
        headers = dict(TWITTER_HEADERS if twitter else {"User-Agent": USER_AGENT})
        if referer:
            headers["Referer"] = referer
        if not twitter and url_origin(url) == self.source_origin:
            headers.update(self.custom_headers)
        return {"type": "url", "url": url, "headers": protocol_headers(headers)}


class CrawlerV3:
    def __init__(self, job):
        self.job = job
        self.feed_id = job["feed_id"]
        self.config = job["config"]
        self.base_url = http_url(self.config.get("base_url", BASE_URL)).rstrip("/")
        self.tag = ""
        if self.feed_id == "tag":
            tag = self.config.get("tag")
            if not isinstance(tag, str) or not tag.strip() or any(unicodedata.category(c) == "Cc" for c in tag):
                raise ValueError("config.tag is required for the tag feed")
            self.tag = tag.strip()
        self.http = HttpClient(job)
        self.pages, self.metadata = {}, {}
        self.lock = threading.Lock()

    def close(self):
        self.http.close()

    def page_url(self, page):
        if self.feed_id == "tag":
            root = self.base_url + "/videos/tag/" + quote(self.tag, safe="")
        else:
            root = self.base_url + "/videos"
        return root if page == 1 else root + "/page/" + str(page)

    def next_page(self, soup, page):
        expected = urlparse(self.page_url(1)).path.rstrip("/")
        for link in soup.select("a[href]"):
            address = urlparse(urljoin(self.page_url(page), link["href"]))
            if address.hostname != urlparse(self.base_url).hostname:
                continue
            match = re.fullmatch(re.escape(expected) + r"/page/(\d+)/?", address.path)
            if match and int(match.group(1)) > page:
                return page + 1
        return None

    @staticmethod
    def _cursor(value):
        if value is None:
            return 1, 0
        identifier(value, "cursor")
        match = re.fullmatch(r"page:([1-9][0-9]*):(0|[1-9][0-9]*)", value)
        if not match:
            raise ValueError("Invalid pagination cursor")
        return int(match.group(1)), int(match.group(2))

    def _load_page(self, page, deadline):
        with self.lock:
            cached = self.pages.get(page)
        if cached is not None:
            return cached
        url = self.page_url(page)
        text = self.http.fetch_text(url, deadline, "source", self.base_url + "/")
        soup = BeautifulSoup(text, "lxml")
        rows = parse_listing_page(soup, url)
        following = self.next_page(soup, page)
        if not rows and following is None and not (soup.select_one(".no-results,.no-videos,.empty-list")
                or re.search(r"no (?:videos|results|items)|暂无|没有视频", soup.get_text(" "), re.I)):
            raise ProtocolError("source", "parse_failed", "无法识别视频列表结构")
        keys = {"video:" + str(row["id"]) for row in rows}
        with self.lock:
            repeated = any(number < page and state["source_keys"] == keys and keys
                           for number, state in self.pages.items())
            previous = {key for number, state in self.pages.items() if number < page
                        for key in state["source_keys"]}
            items = []
            if not repeated:
                for row in rows:
                    source_id = identifier(str(row["id"]), "source_id")
                    key = identifier("video:" + source_id, "discovery_key")
                    self.metadata.setdefault(source_id, row)
                    if key not in previous:
                        items.append({"discovery_key": key, "source_id": source_id,
                                      "locator": {"id": source_id, "detail_url": http_url(row["detail_url"])}})
            state = {"items": items, "source_keys": keys, "next_page": following}
            deadline.remaining()
            self.pages[page] = state
            return state

    def discover(self, command):
        limit = command.get("limit")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")
        page, offset = self._cursor(command.get("cursor"))
        deadline = command.get("_deadline") or CommandDeadline(command.get("deadline_at"), "source")
        state = self._load_page(page, deadline)
        if offset > len(state["items"]):
            raise ValueError("Cursor offset is outside the cached page")
        selected = state["items"][offset:offset + limit]
        end = offset + len(selected)
        next_cursor = ("page:%d:%d" % (page, end) if end < len(state["items"])
                       else "page:%d:0" % state["next_page"] if state["next_page"] is not None else None)
        deadline.remaining()
        return {"items": selected, "next_cursor": next_cursor}

    def resolve(self, command):
        candidate = validate_candidate(command.get("candidate"))
        deadline = command.get("_deadline") or CommandDeadline(command.get("deadline_at"), "item")
        locator = candidate["locator"]
        locator_id = identifier(locator.get("id"), "locator.id")
        source_id = identifier(candidate.get("source_id", locator_id), "source_id")
        detail_url = http_url(locator.get("detail_url"))
        detail = parse_detail_page(self.http.fetch_text(detail_url, deadline, "item", self.base_url + "/"))
        media_url = None
        last_error = None
        for address in detail.get("media_urls", []):
            try:
                self.http.probe_media(twitter_video_url(address), deadline)
                media_url = address
                break
            except ProtocolError as error:
                last_error = error
                if error.fields["code"] in {"auth_required", "rate_limited", "source_unavailable"}:
                    raise
        if not media_url:
            if last_error is not None:
                raise last_error
            raise ProtocolError("item", "parse_failed", "详情页缺少可播放 Twitter 视频地址")
        row = self.metadata.get(locator_id, {})
        title = utf8_prefix(str(detail.get("title") or row.get("title") or "").strip(), 4096)
        if not title:
            raise ProtocolError("item", "parse_failed", "详情页缺少标题")
        result = {"discovery_key": candidate["discovery_key"], "source_id": source_id,
                  "title": title, "detail_url": detail_url,
                  "media": self.http.media_object(media_url, twitter=True)}
        thumbnail = row.get("thumbnail_url")
        if thumbnail:
            result["thumbnail"] = self.http.media_object(thumbnail, twitter=True)
        duration = detail.get("duration_seconds") if detail.get("duration_seconds") is not None else row.get("duration_seconds")
        if type(duration) is int and 0 <= duration <= 604800:
            result["duration_seconds"] = duration
        views = detail.get("views") or row.get("views")
        if type(views) is int and views > 0:
            result["description"] = utf8_prefix("views: %d" % views, 65536)
        existing = self.config.get("existing_tags", [])
        if isinstance(existing, list):
            tags = list(dict.fromkeys(tag for tag in detail.get("tags", [])
                    if isinstance(tag, str) and tag.strip() and tag in existing
                    and len(tag.encode("utf-8")) <= 256))[:100]
            if tags:
                result["tags"] = tags
        deadline.remaining()
        return result


Crawler = CrawlerV3


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def load_json(text):
    def reject_constant(value):
        raise ValueError("Invalid JSON constant: " + value)
    result = json.loads(text, object_pairs_hook=unique_keys, parse_constant=reject_constant)
    if not isinstance(result, dict):
        raise ValueError("JSON must be an object")
    return result


def validate_candidate(candidate):
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be an object")
    key = identifier(candidate.get("discovery_key"), "candidate.discovery_key")
    locator = candidate.get("locator")
    if (not isinstance(locator, dict)
            or len(json.dumps(locator, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 16384):
        raise ValueError("candidate.locator must be an object of at most 16 KiB")
    if "source_id" in candidate:
        identifier(candidate["source_id"], "candidate.source_id")
    return {"discovery_key": key, "locator": locator,
            **({"source_id": candidate["source_id"]} if "source_id" in candidate else {})}


def validate_job(job):
    if job.get("protocol") != CRAWLER_PROTOCOL:
        raise ValueError("Unsupported protocol")
    if job.get("feed_id") not in {feed["id"] for feed in json.loads(CRAWLER_FEEDS)}:
        raise ValueError("Unsupported feed_id")
    for field in ("task_id", "crawler_id"):
        identifier(job.get(field), field)
    if not isinstance(job.get("work_dir"), str) or not os.path.isabs(job["work_dir"]):
        raise ValueError("work_dir must be an absolute path")
    for field in ("config", "network"):
        if field not in job:
            job[field] = {}
        if not isinstance(job[field], dict):
            raise ValueError(field + " must be an object")
    proxy = job["network"].get("proxy_url")
    if proxy is not None:
        if (not isinstance(proxy, str) or not proxy.strip()
                or any(char.isspace() or unicodedata.category(char) == "Cc" for char in proxy)):
            raise ValueError("network.proxy_url must be a nonempty proxy URL string")
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ[name] = proxy
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = ""
    return job


class ProtocolWriter:
    def __init__(self):
        self.total = 0
    def write(self, response):
        line = json.dumps(response, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        size = len(line.encode("utf-8"))
        if size > 1024 * 1024 or self.total + size > 64 * 1024 * 1024:
            raise ValueError("Protocol output size limit reached")
        sys.stdout.write(line)
        sys.stdout.flush()
        self.total += size


def best_request_id(line):
    match = re.search(r'"request_id"\s*:\s*("(?:\\.|[^"\\])*")', line)
    if match:
        try:
            return identifier(json.loads(match.group(1)), "request_id")
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    return "invalid-command"


def serve_job(job_path):
    with open(job_path, encoding="utf-8") as source:
        job = validate_job(load_json(source.read()))
    crawler = CrawlerV3(job)
    writer = ProtocolWriter()
    try:
        while True:
            line = sys.stdin.readline(1024 * 1024 + 1)
            if not line:
                raise EOFError("stdin closed before stop")
            request_id = best_request_id(line)
            command, deadline = None, None
            try:
                if len(line.encode("utf-8")) > 1024 * 1024:
                    while line and not line.endswith("\n"):
                        line = sys.stdin.readline(1024 * 1024 + 1)
                    raise ValueError("Command exceeds 1 MiB")
                command = load_json(line)
                request_id = identifier(command.get("request_id"), "request_id")
                kind = command.get("type")
                if kind == "stop":
                    writer.write({"type": "stopped", "request_id": request_id})
                    return
                scope = "source" if kind == "discover" else "item"
                response = {"request_id": request_id}
                deadline = CommandDeadline(command.get("deadline_at"), scope)
                command["_deadline"] = deadline
                if kind == "discover":
                    response.update(type="page", **run_before_deadline(crawler.discover, deadline, command))
                elif kind == "resolve":
                    response.update(type="item", **run_before_deadline(crawler.resolve, deadline, command))
                else:
                    raise ValueError("Unknown command type")
            except ProtocolError as error:
                response = {"type": "error", "request_id": request_id, **error.fields}
            except Exception as error:
                traceback.print_exc(file=sys.stderr)
                scope = "source" if isinstance(command, dict) and command.get("type") == "discover" else "item"
                response = {"type": "error", "request_id": request_id, "scope": scope,
                            "code": "parse_failed", "message": utf8_prefix(error, 8192) or "解析失败",
                            "retryable": False}
            finally:
                if deadline is not None:
                    deadline.cancelled.set()
                if isinstance(command, dict):
                    command.pop("_deadline", None)
            writer.write(response)
    finally:
        crawler.close()


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=CRAWLER_NAME + " crawler.v3")
    parser.add_argument("--job", required=True)
    arguments = parser.parse_args()
    serve_job(arguments.job)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        os._exit(0)
