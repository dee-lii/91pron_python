#!/usr/bin/env python3
"""KanAV single-file crawler.v3 implementation (requests + BeautifulSoup)."""

CRAWLER_NAME = "KanAV"
CRAWLER_PROTOCOL = "crawler.v3"
CRAWLER_FEEDS = '[{"id":"home","label":"首页精选","default":true},{"id":"category","label":"分类"}]'

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
from urllib.parse import unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.util import Timeout

BASE_URL = "https://kanav.ad"
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
    def __init__(self, job):
        self.job = validate_job(job)
        self.feed_id = job["feed_id"]
        self.config = job["config"]
        self.base_url = http_url(self.config.get("base_url", BASE_URL)).rstrip("/")
        type_id = str(self.config.get("type_id", "1")).strip()
        if not type_id.isdigit() or int(type_id) < 1:
            raise ValueError("config.type_id must be a positive integer")
        self.type_id = str(int(type_id))
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"})
        proxy = job["network"].get("proxy_url")
        if proxy:
            self.session.proxies.update({"http": proxy, "https": proxy})
        self.pages = {}
        self.rows = {}

    def close(self):
        self.session.close()

    def _request(self, url, deadline, scope, referer=None):
        headers = {"Referer": referer} if referer else {}
        current = http_url(url)
        visited = set()
        for _ in range(10):
            deadline.remaining()
            if current in visited:
                raise ProtocolError(scope, "source_unavailable", "源站重定向循环", True)
            visited.add(current)
            try:
                response = self.session.get(current, headers=headers, timeout=deadline.timeout(),
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
                        if size > 8 * 1024 * 1024:
                            raise ProtocolError(scope, "parse_failed", "源站响应超过 8 MiB")
                        chunks.append(chunk)
                except requests.RequestException as error:
                    raise ProtocolError(scope, "source_unavailable", "读取源站响应失败", True) from error
                return b"".join(chunks).decode("utf-8", errors="replace")
        raise ProtocolError(scope, "source_unavailable", "源站重定向过多", True)

    def _page_url(self, page):
        if self.feed_id == "home":
            return self.base_url + "/"
        if page == 1:
            return self.base_url + "/index.php/vod/type/id/%s.html" % self.type_id
        return self.base_url + "/index.php/vod/type/id/%s/page/%d.html" % (self.type_id, page)

    def _parse_listing(self, text):
        soup = BeautifulSoup(text, "lxml")
        rows = []
        for card in soup.select("div.video-item"):
            link = card.find("a", href=re.compile(r"/vod/play/id/\d+/"))
            if not link:
                continue
            match = re.search(r"/vod/play/id/(\d+)/", link.get("href", ""))
            if not match:
                continue
            source_id = match.group(1)
            image = card.find("img")
            title_node = card.select_one("div.entry-title a")
            duration_node = card.select_one("span.model-view")
            title = title_node.get_text(" ", strip=True) if title_node else (image.get("alt", "").strip() if image else "")
            thumbnail = ""
            if image:
                thumbnail = image.get("data-original") or image.get("data-src") or image.get("src") or ""
            rows.append({"id": source_id, "title": title, "detail_url": urljoin(self.base_url, link["href"]),
                         "thumbnail_url": urljoin(self.base_url + "/", thumbnail) if thumbnail else "",
                         "duration_seconds": parse_duration(duration_node.get_text(" ", strip=True)) if duration_node else None})
        return soup, rows

    def _next_page(self, soup, page):
        if self.feed_id == "home":
            return None
        expected = page + 1
        pattern = re.compile(r"/index\.php/vod/type/id/%s/page/(\d+)\.html" % re.escape(self.type_id))
        numbers = []
        for link in soup.select("a[href]"):
            match = pattern.search(urlparse(urljoin(self.base_url, link["href"])).path)
            if match:
                numbers.append(int(match.group(1)))
        return expected if any(number >= expected for number in numbers) else None

    def discover(self, command):
        if "cursor" not in command or "limit" not in command or "deadline_at" not in command:
            raise ValueError("discover requires cursor, limit and deadline_at")
        deadline = CommandDeadline(command["deadline_at"], "source")
        cursor = command["cursor"]
        limit = command["limit"]
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
            page_url = self._page_url(page)
            soup, rows = self._parse_listing(self._request(page_url, deadline, "source", self.base_url + "/"))
            next_page = self._next_page(soup, page)
            recognized_empty = (next_page is not None
                                or soup.select_one(".video-list, .video-items, .module-items, .no-results, .no-videos, .empty-list")
                                or re.search(r"暂无|没有|no\s+(?:videos?|results?)", soup.get_text(" ", strip=True), re.I))
            if not rows and not recognized_empty:
                raise ProtocolError("source", "parse_failed", "无法识别列表页结构")
            previous = {item["source_id"] for old_page, data in self.pages.items() if old_page < page for item in data["items"]}
            items, local = [], set()
            for row in rows:
                self.rows.setdefault(row["id"], row)
                if row["id"] in previous or row["id"] in local:
                    continue
                local.add(row["id"])
                locator = {"id": row["id"], "detail_url": http_url(row["detail_url"])}
                if len(json.dumps(locator, ensure_ascii=False).encode("utf-8")) > 16384:
                    raise ProtocolError("source", "parse_failed", "候选 locator 超过 16 KiB")
                items.append({"discovery_key": identifier("detail:" + row["id"], "discovery_key"),
                              "source_id": row["id"], "locator": locator})
            # A duplicate or structurally empty page emits no candidates but still follows
            # the source's validated next link; only a missing next link means exhaustion.
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
        next_cursor = ("page:%d:%d" % (page, end) if end < len(cached["items"])
                       else "page:%d:0" % cached["next_page"] if cached["next_page"] else None)
        deadline.remaining()
        return {"items": selected, "next_cursor": next_cursor}

    def _media(self, url, referer):
        headers = {"User-Agent": USER_AGENT}
        if referer:
            headers["Referer"] = referer
        return {"type": "url", "url": http_url(url), "headers": protocol_headers(headers)}

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
        # source_id is the backend-visible identity and need not equal the site's
        # locator ID. Preserve a supplied value exactly; use locator_id on-site.
        source_id = identifier(candidate.get("source_id", locator_id), "source_id")
        detail = http_url(locator.get("detail_url"))
        text = self._request(detail, deadline, "item", self.base_url + "/")
        match = re.search(r"player_aaaa\s*=\s*", text)
        if not match:
            raise ProtocolError("item", "parse_failed", "播放配置不存在")
        start, depth, end = match.end(), 0, -1
        for index in range(start, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end < 0:
            raise ProtocolError("item", "parse_failed", "播放配置 JSON 不完整")
        raw = htmlmod.unescape(text[start:end]).replace("\\/", "/")
        try:
            player = json.loads(raw)
        except json.JSONDecodeError:
            try:
                player = json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
            except json.JSONDecodeError as error:
                raise ProtocolError("item", "parse_failed", "播放配置 JSON 无法解析") from error
        if not isinstance(player, dict):
            raise ProtocolError("item", "parse_failed", "播放配置不是对象")
        if player.get("id") is not None and str(player["id"]) != locator_id:
            raise ProtocolError("item", "parse_failed", "播放配置与 locator.id 不匹配")
        media_url = decode_play_url(player.get("url") or player.get("file") or "")
        if not media_url:
            raise ProtocolError("item", "parse_failed", "未解析到可播放媒体地址")
        row = self.rows.get(locator_id, {})
        vod = player.get("vod_data") if isinstance(player.get("vod_data"), dict) else {}
        title = utf8_prefix(str(vod.get("vod_name") or row.get("title") or ("KanAV-" + locator_id)).strip(), 4096)
        result = {"discovery_key": key, "source_id": source_id, "title": title,
                  "detail_url": detail, "media": self._media(media_url, self.base_url + "/")}
        thumbnail = row.get("thumbnail_url")
        if thumbnail:
            result["thumbnail"] = self._media(thumbnail, self.base_url + "/")
        author = str(vod.get("vod_actor") or "").strip()
        if author:
            result["author"] = utf8_prefix(author, 1024)
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
    parser = argparse.ArgumentParser(description="KanAV crawler.v3")
    parser.add_argument("--job", required=True, help="crawler.v3 job JSON absolute path")
    arguments = parser.parse_args()
    serve_job(arguments.job)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        os._exit(0)
