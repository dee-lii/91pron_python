#!/usr/bin/env python3
"""91Porny single-file crawler.v3. Dependencies: requests, beautifulsoup4, lxml."""

CRAWLER_NAME = "91Porny"
CRAWLER_PROTOCOL = "crawler.v3"
CRAWLER_FEEDS = '[{"id":"top-list","label":"本月最热","default":true},{"id":"latest","label":"最近更新"},{"id":"hd","label":"高清视频"},{"id":"hot-list","label":"当前最热"},{"id":"recent-favorite","label":"最近加精"},{"id":"recent-rating","label":"最近得分"},{"id":"nonpaid","label":"非付费"},{"id":"ori","label":"91原创"},{"id":"long-list","label":"10分钟以上"},{"id":"longer-list","label":"20分钟以上"},{"id":"month-discuss","label":"本月讨论"},{"id":"top-favorite","label":"本月收藏"}]'

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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.util import Timeout

BASE_URL = "https://91porny.com"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
MIN_DELAY = 1.0
MAX_DELAY = 3.0
MAX_BODY = 8 * 1024 * 1024


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
            seconds = (when - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            return max(0, min(86400, int(seconds)))
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


def duration_seconds(text):
    parts = str(text or "").strip().split(":")
    if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
        return None
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total if total <= 604800 else None


def parse_play_count(text):
    match = re.search(r"([\d.]+)\s*([万千Kk]?)\s*次?播放", str(text or ""))
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    if match.group(2) == "万":
        number *= 10000
    elif match.group(2) in ("千", "K", "k"):
        number *= 1000
    return int(number)


def parse_listing_page(text, base_url):
    soup = text if isinstance(text, BeautifulSoup) else BeautifulSoup(text, "lxml")
    rows, seen = [], set()
    for card in soup.select("div.video-elem"):
        link = card.select_one('a[href*="/video/view/"]')
        if not link:
            continue
        match = re.search(r"/video/view/([0-9A-Za-z]+)", link.get("href", ""))
        if not match or match.group(1) in seen:
            continue
        source_id = match.group(1)
        seen.add(source_id)
        title_node = card.select_one("a.title")
        title = title_node.get_text(" ", strip=True) if title_node else source_id
        thumbnail = ""
        image = card.select_one("div.img")
        if image:
            found = re.search(r"url\(['\"]?([^)'\"]+)['\"]?\)", image.get("style", ""))
            if found:
                thumbnail = urljoin(base_url, found.group(1))
        layer = card.select_one("small.layer")
        author, views = "", None
        small = card.select_one("small.d-inline-block")
        if small:
            metadata = small.get_text(" ", strip=True)
            author_match = re.search(r"作者[:：]\s*([^\s|]+)", metadata)
            author = author_match.group(1) if author_match else ""
            views = parse_play_count(metadata)
        rows.append({"id": source_id, "title": title, "detail_url": urljoin(base_url, link["href"]),
                     "thumbnail_url": thumbnail,
                     "duration_seconds": duration_seconds(layer.get_text(strip=True)) if layer else None,
                     "author": author, "views": views})
    return rows


def parse_detail_page(text):
    soup = BeautifulSoup(text, "lxml")
    result = {}
    video = soup.select_one("video#video-play") or soup.select_one("video")
    if video:
        source = video.get("data-src") or video.get("src") or video.get("data-url") or ""
        if not source:
            nested = video.select_one("source[src], source[data-src]")
            if nested:
                source = nested.get("data-src") or nested.get("src") or ""
        source = htmlmod.unescape(source.strip())
        if source:
            result["media_url"] = source
        poster = video.get("data-poster") or video.get("poster") or ""
        if poster:
            result["thumbnail_url"] = htmlmod.unescape(poster.strip())
    if not result.get("media_url"):
        match = re.search(r'https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', htmlmod.unescape(text))
        if match:
            result["media_url"] = match.group(0)
    title = soup.select_one("h1")
    if title:
        result["title"] = title.get_text(" ", strip=True)
    views = re.search(r"([\d.]+[万千Kk]?)\s*次?播放", text)
    if views:
        result["views"] = parse_play_count(views.group(0))
    return result


class HttpClient:
    def __init__(self, job):
        self.headers = {"User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9"}
        self.custom_headers = protocol_headers(job.get("config", {}).get("headers", {}))
        source_base = job.get("config", {}).get("base_url", BASE_URL)
        self.source_origin = url_origin(source_base)
        self.proxies = {}
        proxy = job.get("network", {}).get("proxy_url")
        if proxy:
            self.proxies = {"http": proxy, "https": proxy}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.lock = threading.Lock()

    def close(self):
        pass

    def fetch_text(self, url, deadline, scope, referer=None):
        current = http_url(url)
        method = "GET"
        with requests.Session() as session:
            session.mount("http://", requests.adapters.HTTPAdapter(max_retries=0))
            session.mount("https://", requests.adapters.HTTPAdapter(max_retries=0))
            session.headers.update(self.headers)
            session.proxies.update(self.proxies)
            with self.lock:
                session.cookies.update(self.cookies)
            for _ in range(11):
                deadline.polite_sleep()
                headers = {"Referer": referer} if referer else {}
                if url_origin(current) == self.source_origin:
                    headers.update(self.custom_headers)
                try:
                    with session.request(method, current, headers=headers,
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
                            code = {401: "auth_required", 403: "auth_required", 404: "not_found",
                                    410: "not_found", 429: "rate_limited"}.get(status, "source_unavailable")
                            error_scope = "source" if code in {"auth_required", "rate_limited"} else scope
                            raise ProtocolError(error_scope, code, "源站返回 HTTP %d" % status,
                                                code in {"rate_limited", "source_unavailable"},
                                                retry_after(response.headers.get("Retry-After"))
                                                if code in {"rate_limited", "source_unavailable"} else None)
                        chunks, size = [], 0
                        for chunk in response.iter_content(65536):
                            deadline.remaining()
                            size += len(chunk)
                            if size > MAX_BODY:
                                raise ProtocolError(scope, "parse_failed", "源站响应超过 8 MiB")
                            chunks.append(chunk)
                        deadline.remaining()
                        with self.lock:
                            self.cookies.update(session.cookies)
                        return b"".join(chunks).decode("utf-8", errors="replace")
                except requests.exceptions.RequestException as error:
                    raise ProtocolError(scope, "source_unavailable", "源站网络请求失败", True) from error
        raise ProtocolError(scope, "source_unavailable", "源站重定向次数过多", True)

    def media_object(self, url, referer):
        url = http_url(url)
        headers = {"User-Agent": USER_AGENT, "Referer": referer}
        if url_origin(url) == self.source_origin:
            headers.update(self.custom_headers)
        with self.lock:
            temporary = requests.Session()
            temporary.cookies.update(self.cookies)
            prepared = temporary.prepare_request(requests.Request("GET", url, headers=headers))
            cookie = prepared.headers.get("Cookie")
            temporary.close()
        if cookie:
            headers["Cookie"] = cookie
        return {"type": "url", "url": url, "headers": protocol_headers(headers)}


class CrawlerV3:
    def __init__(self, job):
        self.job = job
        self.feed_id = job["feed_id"]
        self.config = job["config"]
        self.base_url = http_url(self.config.get("base_url", BASE_URL)).rstrip("/")
        self.http = HttpClient(job)
        self.pages = {}
        self.metadata = {}
        self.lock = threading.Lock()

    def close(self):
        self.http.close()

    def page_url(self, page):
        root = self.base_url + "/video/category/" + self.feed_id
        return root if page == 1 else root + "/" + str(page)

    def next_page(self, soup, page):
        path = "/video/category/" + re.escape(self.feed_id)
        numbers = []
        for link in soup.select("a[href]"):
            address = urlparse(urljoin(self.page_url(page), link["href"]))
            if address.hostname != urlparse(self.base_url).hostname:
                continue
            match = re.fullmatch(path + r"/(\d+)/?", address.path)
            if match and int(match.group(1)) > page:
                numbers.append(int(match.group(1)))
        return page + 1 if numbers and min(numbers) >= page + 1 else None

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
                or re.search(r"暂无|没有视频|no (?:videos|results|items)", soup.get_text(" "), re.I)):
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
                                      "locator": {"id": source_id,
                                                  "detail_url": http_url(row["detail_url"])}})
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
        text = self.http.fetch_text(detail_url, deadline, "item", self.base_url + "/")
        detail = parse_detail_page(text)
        row = self.metadata.get(locator_id, {})
        title = utf8_prefix(str(detail.get("title") or row.get("title") or "").strip(), 4096)
        media_url = detail.get("media_url")
        if not title or not media_url:
            raise ProtocolError("item", "parse_failed", "详情页缺少标题或可播放媒体地址")
        result = {"discovery_key": candidate["discovery_key"], "source_id": source_id,
                  "title": title, "detail_url": detail_url,
                  "media": self.http.media_object(urljoin(detail_url, media_url), self.base_url + "/")}
        thumbnail = detail.get("thumbnail_url") or row.get("thumbnail_url")
        if thumbnail:
            result["thumbnail"] = self.http.media_object(urljoin(detail_url, thumbnail), self.base_url + "/")
        author = str(row.get("author") or "").strip()
        if author:
            result["author"] = utf8_prefix(author, 1024)
        duration = row.get("duration_seconds")
        if type(duration) is int and 0 <= duration <= 604800:
            result["duration_seconds"] = duration
        views = detail.get("views") or row.get("views")
        if type(views) is int and views > 0:
            result["description"] = utf8_prefix("views: %d" % views, 65536)
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
    feeds = {feed["id"] for feed in json.loads(CRAWLER_FEEDS)}
    if job.get("feed_id") not in feeds:
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
    args = parser.parse_args()
    serve_job(args.job)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        os._exit(0)
