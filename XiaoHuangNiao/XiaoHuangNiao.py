#!/usr/bin/env python3
"""小黄鸟 single-file crawler.v3. Dependency: requests."""

CRAWLER_NAME = "XiaoHuangNiao"
CRAWLER_PROTOCOL = "crawler.v3"
CRAWLER_FEEDS = '[{"id":"hot-tweets","label":"热门黄推","default":true}]'

import argparse
import datetime
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
from urllib.parse import urlencode, urljoin, urlparse

import requests
from urllib3.util import Timeout

BASE_URL = "https://xiaohuangniao.me"
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


def positive_source_limit(value):
    if value is None:
        return 50
    if type(value) is not int or not 1 <= value <= 1000:
        raise ValueError("config.limit must be an integer between 1 and 1000")
    return value


def build_title(text, author="", tweet_id=""):
    value = str(text or "")
    value = re.sub(r"https?://\S+", " ", value, flags=re.I)
    value = re.sub(r"(?:t\.me|telegram|tg)\s*/\s*\S+", " ", value, flags=re.I)
    value = re.sub(r"@[\w]+", " ", value)
    value = re.sub(r"#[\w\u4e00-\u9fff]+", " ", value)
    value = re.sub(r"(?:✈️?|✉️|📩)?\s*(?:电报群?|电报|telegram|tg)\s*(?:👉|➡️|→|链接|🔗|:\s*)?", " ", value, flags=re.I)
    value = re.sub(r"庆祝?\d+[万wW]?粉丝|\d+[万wW]?粉丝|粉丝\d+[万wW]?|🚪打.折|打八折|打七折|打六折|限时半价|限时|走丢", " ", value)
    value = re.sub(r"(?:懂?车|车已|私推|完整版|加长版|长视频|移步|注册|关注|私密号|防走丢|备用号).{0,12}", " ", value)
    value = re.sub(r"更多精彩|主页直达|网页链接|点击链接|详见|作品见|可私|联系|加群|入群|粉丝群|订阅", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" ️👉➡️:：,，。.…")
    return value[:80] or ("by " + author if author else tweet_id or "xiaohuangniao")


def extract_video_candidates(data):
    if not isinstance(data, list):
        raise ProtocolError("source", "parse_failed", "API data 不是数组")
    candidates = []
    seen_ids = set()
    for tweet in data:
        if not isinstance(tweet, dict):
            continue
        tweet_id = str(tweet.get("tweetId") or "").strip()
        if not tweet_id:
            continue
        try:
            tweet_id = identifier(tweet_id, "tweetId")
        except ValueError:
            continue
        if tweet_id in seen_ids:
            continue
        seen_ids.add(tweet_id)
        media_candidates = []
        for media in tweet.get("mediaUrls") or []:
            if not isinstance(media, dict) or media.get("type") != "video":
                continue
            address = str(media.get("url") or "").strip()
            if address:
                try:
                    address = twitter_video_url(address)
                except ValueError:
                    continue
                bitrate = media.get("bitrate")
                bitrate = bitrate if type(bitrate) is int and bitrate >= 0 else 0
                media_candidates.append({"url": address, "bitrate": bitrate,
                                         "duration": media.get("duration")})
        entities = tweet.get("extendedEntities") or {}
        if isinstance(entities, dict):
            for media in entities.get("media") or []:
                if not isinstance(media, dict):
                    continue
                info = media.get("video_info") or {}
                if not isinstance(info, dict):
                    continue
                for variant in info.get("variants") or []:
                    if not isinstance(variant, dict) or str(variant.get("content_type", "")).lower() != "video/mp4":
                        continue
                    address = str(variant.get("url") or "").strip()
                    try:
                        address = twitter_video_url(address)
                    except ValueError:
                        continue
                    bitrate = variant.get("bitrate")
                    bitrate = bitrate if type(bitrate) is int and bitrate >= 0 else 0
                    media_candidates.append({"url": address, "bitrate": bitrate,
                                             "duration": info.get("duration_millis")})
        unique = {}
        for media in media_candidates:
            previous = unique.get(media["url"])
            if previous is None or media["bitrate"] > previous["bitrate"]:
                unique[media["url"]] = media
        media_candidates = sorted(unique.values(), key=lambda item: item["bitrate"], reverse=True)
        if not media_candidates:
            continue
        author = ""
        author_info = tweet.get("author")
        if isinstance(author_info, dict):
            author = str(author_info.get("userName") or author_info.get("name") or "").strip()
        thumbnail = ""
        if isinstance(entities, dict) and isinstance(entities.get("media"), list) and entities["media"]:
            first = entities["media"][0]
            if isinstance(first, dict):
                thumbnail = str(first.get("media_url_https") or first.get("media_url") or "").strip()
                if thumbnail:
                    try:
                        thumbnail = http_url(thumbnail)
                    except ValueError:
                        thumbnail = ""
        duration = media_candidates[0].get("duration")
        try:
            duration_seconds = int(duration) // 1000 if duration is not None else None
        except (TypeError, ValueError):
            duration_seconds = None
        if duration_seconds is not None and not 0 <= duration_seconds <= 604800:
            duration_seconds = None
        views = tweet.get("viewCount")
        try:
            views = int(views) if views is not None else None
        except (TypeError, ValueError):
            views = None
        candidates.append({"id": tweet_id,
                           "title": build_title(tweet.get("text"), author, tweet_id),
                           "detail_url": "https://x.com/i/status/" + tweet_id,
                           "thumbnail_url": thumbnail, "media_candidates": media_candidates,
                           "duration_seconds": duration_seconds,
                           "author": author, "views": views})
    return candidates


class HttpClient:
    def __init__(self, job):
        self.headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*",
                        "Accept-Language": "zh-CN,zh;q=0.9"}
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
                        return response.headers, b"".join(chunks)
                except requests.exceptions.RequestException as error:
                    raise ProtocolError(scope, "source_unavailable", "源站网络请求失败", True) from error
        raise ProtocolError(scope, "source_unavailable", "源站重定向次数过多", True)

    def fetch_json(self, url, deadline, scope, referer=None):
        body = self.request(url, deadline, scope, referer)[1]
        try:
            result = json.loads(body.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProtocolError(scope, "parse_failed", "源站返回的 JSON 无法解析") from error
        if not isinstance(result, dict):
            raise ProtocolError(scope, "parse_failed", "源站 JSON 顶层不是对象")
        return result

    def probe_media(self, url, deadline):
        headers = dict(TWITTER_HEADERS)
        headers["Range"] = "bytes=0-0"
        url = twitter_video_url(url)
        response_headers, body = self.request(url, deadline, "item", headers=headers,
                                               body_limit=4096, truncate=True, media_probe=True)
        content_type = (response_headers.get("Content-Type") or "").lower()
        first = body[:256].lstrip().lower()
        if (not body or any(value in content_type for value in ("text/html", "application/json", "text/plain"))
                or first.startswith((b"<html", b"<!doctype", b'{"error', b"error"))):
            raise ProtocolError("item", "parse_failed", "Twitter 媒体地址未返回视频内容")

    def media_object(self, url, twitter=True):
        url = http_url(url)
        if twitter and urlparse(url).hostname.lower() not in {"video.twimg.com", "pbs.twimg.com"}:
            raise ValueError("Unsupported Twitter media host")
        headers = dict(TWITTER_HEADERS if twitter else {"User-Agent": USER_AGENT})
        if not twitter and url_origin(url) == self.source_origin:
            headers.update(self.custom_headers)
        return {"type": "url", "url": url, "headers": protocol_headers(headers)}


class CrawlerV3:
    def __init__(self, job):
        self.job = job
        self.config = job.get("config", {})
        self.base_url = http_url(self.config.get("base_url", BASE_URL)).rstrip("/")
        self.source_limit = positive_source_limit(self.config.get("limit"))
        self.http = HttpClient(job)
        self.snapshot = None
        self.rows = {}
        self.lock = threading.Lock()

    def close(self):
        self.http.close()

    def _snapshot(self, deadline):
        with self.lock:
            if self.snapshot is not None:
                return self.snapshot
        query = urlencode({"type": "hot-tweets", "limit": self.source_limit})
        payload = self.http.fetch_json(self.base_url + "/api/requestdb?" + query,
                                       deadline, "source", self.base_url + "/")
        if payload.get("success") is not True:
            raise ProtocolError("source", "parse_failed", "热门推文 API 返回 success=false")
        rows = extract_video_candidates(payload.get("data"))
        items = []
        for row in rows:
            source_id = identifier(row["id"], "source_id")
            items.append({"discovery_key": identifier("tweet:" + source_id, "discovery_key"),
                          "source_id": source_id, "locator": {"id": source_id}})
        with self.lock:
            deadline.remaining()
            if self.snapshot is None:
                self.snapshot = items
                self.rows = {row["id"]: row for row in rows}
            return self.snapshot

    def discover(self, command):
        limit = command.get("limit")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")
        cursor = command.get("cursor")
        if cursor is None:
            offset = 0
        else:
            identifier(cursor, "cursor")
            match = re.fullmatch(r"offset:(0|[1-9][0-9]*)", cursor)
            if not match:
                raise ValueError("Invalid pagination cursor")
            offset = int(match.group(1))
        deadline = command.get("_deadline") or CommandDeadline(command.get("deadline_at"), "source")
        items = self._snapshot(deadline)
        if offset > len(items):
            raise ValueError("Cursor offset is outside the cached snapshot")
        selected = items[offset:offset + limit]
        end = offset + len(selected)
        deadline.remaining()
        return {"items": selected, "next_cursor": "offset:%d" % end if end < len(items) else None}

    def resolve(self, command):
        candidate = validate_candidate(command.get("candidate"))
        deadline = command.get("_deadline") or CommandDeadline(command.get("deadline_at"), "item")
        locator_id = identifier(candidate["locator"].get("id"), "locator.id")
        source_id = identifier(candidate.get("source_id", locator_id), "source_id")
        self._snapshot(deadline)
        row = self.rows.get(locator_id)
        if row is None:
            raise ProtocolError("item", "not_found", "热门 API 快照中不存在该推文")
        media_url, last_error = None, None
        for media in row["media_candidates"]:
            try:
                self.http.probe_media(media["url"], deadline)
                media_url = media["url"]
                break
            except ProtocolError as error:
                last_error = error
                if error.fields["code"] in {"auth_required", "rate_limited", "source_unavailable"}:
                    raise
        if not media_url:
            if last_error is not None:
                raise last_error
            raise ProtocolError("item", "parse_failed", "推文没有可下载的视频地址")
        title = utf8_prefix(str(row["title"]).strip(), 4096)
        if not title:
            raise ProtocolError("item", "parse_failed", "推文标题为空")
        result = {"discovery_key": candidate["discovery_key"], "source_id": source_id,
                  "title": title, "detail_url": http_url(row["detail_url"]),
                  "media": self.http.media_object(media_url)}
        if row.get("thumbnail_url"):
            result["thumbnail"] = self.http.media_object(row["thumbnail_url"])
        author = str(row.get("author") or "").strip()
        if author:
            result["author"] = utf8_prefix(author, 1024)
        duration = row.get("duration_seconds")
        if type(duration) is int and 0 <= duration <= 604800:
            result["duration_seconds"] = duration
        views = row.get("views")
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
