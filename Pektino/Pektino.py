#!/usr/bin/env python3
"""Pektino single-file crawler.v3 implementation (requests)."""

CRAWLER_NAME = "Pektino"
CRAWLER_PROTOCOL = "crawler.v3"
CRAWLER_FEEDS = '[{"id":"weekly","label":"周榜","default":true},{"id":"daily","label":"日榜"},{"id":"monthly","label":"月榜"},{"id":"all","label":"全部"}]'

import argparse
import base64
import datetime
import html as htmlmod
import json
import os
import re
import sys
import time
import traceback
import unicodedata
from email.utils import parsedate_to_datetime
from urllib.parse import quote, unquote, urlencode, urljoin, urlparse

import requests
from urllib3.util import Timeout

BASE_URL = "https://pektino.com"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")
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

    def remaining(self):
        seconds = self.end - time.monotonic()
        if seconds <= 0:
            raise ProtocolError(self.scope, "source_unavailable", "操作截止时间已到", True)
        return seconds

    def timeout(self, cap=30):
        total = min(float(cap), self.remaining())
        return Timeout(connect=max(0.05, min(10.0, total)), read=max(0.05, total), total=max(0.05, total))


def parse_duration(text):
    text = str(text or "").strip()
    total = 0
    for pattern, multiplier in ((r"(\d+)\s*小时", 3600), (r"(\d+)\s*分钟", 60), (r"(\d+)\s*秒", 1)):
        match = re.search(pattern, text)
        if match:
            total += int(match.group(1)) * multiplier
    if not total and re.fullmatch(r"\d+(?::\d{1,2}){1,2}", text):
        for part in text.split(":"):
            total = total * 60 + int(part)
    return total if 0 < total <= 604800 else None


def decode_play_url(value):
    if not value:
        return ""
    raw = htmlmod.unescape(str(value)).strip().strip("\\\"'").replace("\\/", "/")
    candidates = [raw]
    try:
        candidates.append(base64.b64decode(raw + "=" * (-len(raw) % 4), validate=False).decode("utf-8", "replace"))
    except Exception:
        pass
    for candidate in candidates:
        decoded = unquote(htmlmod.unescape(candidate).replace("\\/", "/")).strip().strip("\\\"'")
        if re.match(r"^https?://", decoded, re.I):
            return decoded
    return ""


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


class CrawlerV3:
    MEDIA_HEADERS = {"User-Agent": USER_AGENT, "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
                     "Referer": "https://x.com/", "Origin": "https://x.com"}

    def __init__(self, job):
        self.job = validate_job(job)
        self.feed_id = job["feed_id"]
        self.config = job["config"]
        self.base_url = http_url(self.config.get("base_url", BASE_URL)).rstrip("/")
        self.locale = str(self.config.get("locale", "zh-CN")).strip().strip("/")
        if not self.locale or len(self.locale.encode("utf-8")) > 64 or not re.fullmatch(r"[A-Za-z0-9_-]+", self.locale):
            raise ValueError("config.locale is invalid")
        self.per_page = self._integer("per_page", 50, 1, 200)
        self.min_time = self._integer("min_time", 0, 0, 604800)
        self.max_time = self._integer("max_time", 0, 0, 604800)
        if self.min_time and self.max_time and self.min_time > self.max_time:
            raise ValueError("config.min_time exceeds config.max_time")
        anime = self.config.get("is_anime_only", False)
        if not isinstance(anime, bool):
            raise ValueError("config.is_anime_only must be boolean")
        self.is_anime = anime
        self.api_session = requests.Session()
        self.api_session.trust_env = False
        self.api_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*",
                                         "Accept-Language": "zh-CN,zh;q=0.9",
                                         "Referer": self.base_url + "/" + self.locale})
        self.api_session.cookies.set("age_verified", str(int((time.time() + 365 * 86400) * 1000)),
                                     domain=urlparse(self.base_url).hostname, path="/")
        self.api_session.cookies.set("site_lang", json.dumps({"code": self.locale, "label": "简体中文"},
                                                              ensure_ascii=True, separators=(",", ":")),
                                     domain=urlparse(self.base_url).hostname, path="/")
        self.media_session = requests.Session()
        self.media_session.trust_env = False
        proxy = job["network"].get("proxy_url")
        if proxy:
            self.media_session.proxies.update({"http": proxy, "https": proxy})
        self.pages = {}

    def _integer(self, name, default, minimum, maximum):
        value = self.config.get(name, default)
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError("config.%s must be an integer from %d to %d" % (name, minimum, maximum))
        return value

    def close(self):
        self.api_session.close()
        self.media_session.close()

    def _response(self, session, url, deadline, scope, headers=None, maximum=8 * 1024 * 1024, sample=False):
        current = http_url(url)
        visited = set()
        for _ in range(10):
            deadline.remaining()
            if current in visited:
                raise ProtocolError(scope, "source_unavailable", "源站重定向循环", True)
            visited.add(current)
            try:
                response = session.get(current, headers=headers or {}, timeout=deadline.timeout(),
                                       allow_redirects=False, stream=True)
            except requests.RequestException as error:
                raise ProtocolError(scope, "source_unavailable", "源站网络请求失败", True) from error
            with response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        raise ProtocolError(scope, "parse_failed", "重定向缺少 Location")
                    current = http_url(urljoin(current, location))
                    continue
                if response.status_code >= 400:
                    code = {401: "auth_required", 403: "auth_required", 404: "not_found",
                            410: "not_found", 429: "rate_limited"}.get(response.status_code, "source_unavailable")
                    # A stale Twitter CDN URL commonly returns 403; it is not
                    # evidence that the Pektino API needs authentication.
                    if session is self.media_session and response.status_code == 403:
                        code = "not_found"
                    error_scope = "source" if code in {"auth_required", "rate_limited"} else scope
                    raise ProtocolError(error_scope, code, "源站返回 HTTP %d" % response.status_code,
                                        code in {"rate_limited", "source_unavailable"},
                                        retry_after(response.headers.get("Retry-After"))
                                        if code in {"rate_limited", "source_unavailable"} else None)
                chunks, size = [], 0
                try:
                    for chunk in response.iter_content(65536):
                        deadline.remaining()
                        size += len(chunk)
                        if size > maximum and not sample:
                            raise ProtocolError(scope, "parse_failed", "源站响应过大")
                        chunks.append(chunk[:max(0, maximum - (size - len(chunk)))])
                        if sample:
                            break
                except requests.RequestException as error:
                    raise ProtocolError(scope, "source_unavailable", "读取源站响应失败", True) from error
                return b"".join(chunks), current, response.headers
        raise ProtocolError(scope, "source_unavailable", "源站重定向过多", True)

    def _api_json(self, url, deadline, scope):
        body, _, _ = self._response(self.api_session, url, deadline, scope)
        try:
            data = json.loads(body.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProtocolError(scope, "parse_failed", "Pektino API 返回无效 JSON") from error
        if not isinstance(data, (dict, list)):
            raise ProtocolError(scope, "parse_failed", "Pektino API JSON 类型无效")
        return data

    @staticmethod
    def _items(payload, requested_page):
        # A top-level array has no continuation contract, so treat it as one complete,
        # finite response on page 1. Object responses must explicitly describe pages.
        if isinstance(payload, list):
            if requested_page != 1:
                raise ProtocolError("source", "parse_failed", "无分页元数据的数组只能作为第一页")
            return payload, 1, 1
        if not isinstance(payload, dict):
            raise ProtocolError("source", "parse_failed", "API 列表响应类型无效")
        container = payload
        rows = payload.get("items")
        if not isinstance(rows, list):
            nested = payload.get("data")
            if isinstance(nested, list):
                rows = nested
            elif isinstance(nested, dict):
                container = nested
                rows = nested.get("items")
            else:
                rows = None
        if not isinstance(rows, list):
            raise ProtocolError("source", "parse_failed", "API 列表字段无效")

        def page_number(container, camel, snake):
            value = container.get(camel, container.get(snake))
            if type(value) is int and value > 0:
                return value
            if isinstance(value, str) and value.isdigit() and int(value) > 0:
                return int(value)
            raise ProtocolError("source", "parse_failed", "API 缺少有效分页元数据")

        current = page_number(container, "currentPage", "current_page")
        last = page_number(container, "lastPage", "last_page")
        if last < current:
            raise ProtocolError("source", "parse_failed", "API 分页范围无效")
        return rows, current, last

    @staticmethod
    def _urls(value):
        found = []
        def visit(node):
            if isinstance(node, dict):
                for child in node.values():
                    visit(child)
            elif isinstance(node, list):
                for child in node:
                    visit(child)
            elif isinstance(node, str):
                url = node.strip().replace("\\/", "/")
                if url.startswith("http://video.twimg.com/"):
                    url = "https://" + url[len("http://"):]
                if url.startswith("https://video.twimg.com/") and ".mp4" in urlparse(url).path.lower() and url not in found:
                    found.append(url)
        visit(value)
        return found

    def _locator(self, row, source_id):
        author = str(row.get("tweet_account") or row.get("author") or "").strip().lstrip("@")
        title = str(row.get("anime_title") or row.get("title") or "").strip()
        raw_detail = str(row.get("detail_url") or "").strip()
        detail = raw_detail if raw_detail.startswith(("http://", "https://")) else (
            self.base_url + "/" + self.locale + "/movie/" + quote(str(row.get("url_cd") or source_id), safe="_-") )
        locator = {"id": source_id, "url_cd": str(row.get("url_cd") or source_id),
                   "media_urls": self._urls(row)[:12], "detail_url": http_url(detail)}
        if title:
            locator["title"] = utf8_prefix(re.sub(r"\s+", " ", title).strip(), 4096)
        thumbnail = str(row.get("thumbnail") or "").strip()
        if thumbnail:
            try:
                locator["thumbnail"] = http_url(thumbnail)
            except ValueError:
                pass
        if author and author != "unknown":
            locator["author"] = utf8_prefix(author, 1024)
        try:
            duration = round(float(row.get("time") or row.get("duration") or 0))
        except (TypeError, ValueError, OverflowError):
            duration = 0
        if 0 < duration <= 604800:
            locator["duration_seconds"] = duration
        description = []
        for label, field in (("views", "pv"), ("likes", "favorite")):
            try:
                value = round(float(row.get(field) or 0))
            except (TypeError, ValueError, OverflowError):
                value = 0
            if value > 0:
                description.append("%s: %d" % (label, value))
        tweet = str(row.get("tweet_url") or "").strip()
        if not tweet.startswith(("http://", "https://")):
            tweet = "https://x.com/i/status/" + quote(source_id, safe="")
        description.append("source: " + tweet)
        locator["description"] = utf8_prefix(" | ".join(description), 65536)
        if len(json.dumps(locator, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 16384:
            locator.pop("description", None)
            locator["media_urls"] = locator["media_urls"][:4]
        if len(json.dumps(locator, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 16384:
            raise ProtocolError("source", "parse_failed", "候选 locator 超过 16 KiB")
        return locator

    def _list_url(self, page):
        query = {"page": page, "per_page": self.per_page,
                 "isAnimeOnly": 1 if self.is_anime else 0, "sort": "favorite"}
        if self.feed_id != "daily":
            query["range"] = self.feed_id
        if self.min_time:
            query["min_time"] = self.min_time
        if self.max_time:
            query["max_time"] = self.max_time
        return self.base_url + "/api/media?" + urlencode(query)

    def discover(self, command):
        if "cursor" not in command or "limit" not in command or "deadline_at" not in command:
            raise ValueError("discover requires cursor, limit and deadline_at")
        deadline = CommandDeadline(command["deadline_at"], "source")
        cursor, limit = command["cursor"], command["limit"]
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        if cursor is None:
            page, offset = 1, 0
        else:
            identifier(cursor, "cursor")
            match = re.fullmatch(r"page:([1-9]\d*):(0|[1-9]\d*)", cursor)
            if not match:
                raise ValueError("invalid cursor")
            page, offset = map(int, match.groups())
        if page not in self.pages:
            payload = self._api_json(self._list_url(page), deadline, "source")
            rows, current, last = self._items(payload, page)
            if current != page:
                raise ProtocolError("source", "parse_failed", "API 返回了错误页码")
            valid = [row for row in rows if isinstance(row, dict)]
            if rows and not valid:
                raise ProtocolError("source", "parse_failed", "API 列表没有有效对象")
            previous = {item["source_id"] for old, data in self.pages.items() if old < page for item in data["items"]}
            items, local = [], set()
            for row in valid:
                raw_id = row.get("url_cd") or row.get("id")
                try:
                    source_id = identifier(str(raw_id).strip(), "source_id")
                except ValueError:
                    continue
                if source_id in previous or source_id in local:
                    continue
                local.add(source_id)
                items.append({"discovery_key": identifier("detail:" + source_id, "discovery_key"),
                              "source_id": source_id, "locator": self._locator(row, source_id)})
            # Explicit API pagination is authoritative: an empty or duplicate page can
            # still have later pages. De-duplication only suppresses emitted candidates.
            next_page = page + 1 if page < last else None
            self.pages[page] = {"items": items, "next_page": next_page}
        cached = self.pages[page]
        if offset > len(cached["items"]):
            raise ValueError("cursor offset exceeds cached page")
        selected, payload_bytes = [], 128
        for item in cached["items"][offset:offset + limit]:
            item_bytes = len(json.dumps(item, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1
            if selected and payload_bytes + item_bytes > 900 * 1024:
                break
            selected.append(item)
            payload_bytes += item_bytes
        end = offset + len(selected)
        following = ("page:%d:%d" % (page, end) if end < len(cached["items"])
                     else "page:%d:0" % cached["next_page"] if cached["next_page"] else None)
        deadline.remaining()
        return {"items": selected, "next_cursor": following}

    def _probe(self, url, deadline):
        try:
            body, final_url, headers = self._response(self.media_session, url, deadline, "item",
                                                      {**self.MEDIA_HEADERS, "Range": "bytes=0-255"}, 4096, sample=True)
        except ProtocolError as error:
            if error.fields["code"] == "not_found":
                return ""
            raise
        content_type = str(headers.get("Content-Type") or "").lower()
        head = body[:256].lstrip().lower()
        if (not head or head.startswith((b"<html", b"<!doctype", b'{"error', b"error"))
                or any(kind in content_type for kind in ("text/html", "application/json", "text/plain"))):
            return ""
        return final_url

    def _media(self, url):
        return {"type": "url", "url": http_url(url), "headers": protocol_headers(dict(self.MEDIA_HEADERS))}

    def resolve(self, command):
        if "candidate" not in command or "deadline_at" not in command:
            raise ValueError("resolve requires candidate and deadline_at")
        deadline = CommandDeadline(command["deadline_at"], "item")
        candidate = command["candidate"]
        if not isinstance(candidate, dict):
            raise ValueError("candidate must be an object")
        key = identifier(candidate.get("discovery_key"), "discovery_key")
        locator = candidate.get("locator")
        if not isinstance(locator, dict) or len(json.dumps(locator, ensure_ascii=False).encode("utf-8")) > 16384:
            raise ValueError("locator must be an object no larger than 16 KiB")
        locator_id = identifier(locator.get("id"), "locator.id")
        # Keep the candidate source_id as the output identity. locator_id is the
        # native Pektino key used for detail refresh and native metadata fallback.
        source_id = identifier(candidate.get("source_id", locator_id), "source_id")
        candidates = self._urls(locator.get("media_urls", []))
        attempted, selected, last_unavailable = set(), "", None

        def try_urls(urls):
            nonlocal selected, last_unavailable
            for url in urls:
                if url in attempted:
                    continue
                attempted.add(url)
                try:
                    selected = self._probe(url, deadline)
                except ProtocolError as error:
                    if error.fields["code"] != "source_unavailable":
                        raise
                    last_unavailable = error
                    continue
                if selected:
                    return

        try_urls(candidates)
        detail_payload = None
        if not selected:
            # locator.id is authoritative for site lookup. Discovery currently sets
            # url_cd to the same native value, but external candidates need not.
            detail_payload = self._api_json(self.base_url + "/api/media/" + quote(locator_id, safe="_-"), deadline, "item")
            try_urls(self._urls(detail_payload))
        if not selected:
            if last_unavailable is not None:
                raise last_unavailable
            raise ProtocolError("item", "source_unavailable", "没有可读取的 Twitter 媒体地址", True)
        merged = {}
        if isinstance(detail_payload, dict):
            nested = detail_payload.get("data")
            merged = nested if isinstance(nested, dict) else detail_payload
        title = str(merged.get("anime_title") or merged.get("title") or locator.get("title") or "").strip()
        author = str(merged.get("tweet_account") or merged.get("author") or locator.get("author") or "").strip().lstrip("@")
        if not title and author and author != "unknown":
            title = "@%s 的视频" % author
        title = utf8_prefix(re.sub(r"\s+", " ", title).strip() or locator_id, 4096)
        detail_url = http_url(locator.get("detail_url"))
        result = {"discovery_key": key, "source_id": source_id, "title": title,
                  "detail_url": detail_url, "media": self._media(selected)}
        thumbnail = str(merged.get("thumbnail") or locator.get("thumbnail") or "").strip()
        if thumbnail:
            try:
                result["thumbnail"] = self._media(thumbnail)
            except ValueError:
                pass
        if author and author != "unknown":
            result["author"] = utf8_prefix(author, 1024)
        description = str(locator.get("description") or "").strip()
        if description:
            result["description"] = utf8_prefix(description, 65536)
        duration = locator.get("duration_seconds")
        try:
            fresh_duration = round(float(merged.get("time") or merged.get("duration") or 0))
            if 0 < fresh_duration <= 604800:
                duration = fresh_duration
        except (TypeError, ValueError, OverflowError):
            pass
        if type(duration) is int and 0 <= duration <= 604800:
            result["duration_seconds"] = duration
        deadline.remaining()
        return result


# Compatibility with the upstream class name.
Crawler = CrawlerV3


class ProtocolWriter:
    def __init__(self):
        self.total = 0

    def write(self, response):
        line = json.dumps(response, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        size = len(line.encode("utf-8"))
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
            except Exception as error:
                response = _error_response(request_id, scope, error)
            writer.write(response)
    finally:
        crawler.close()


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Pektino crawler.v3")
    parser.add_argument("--job", required=True, help="crawler.v3 job JSON absolute path")
    arguments = parser.parse_args()
    serve_job(arguments.job)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        os._exit(0)
