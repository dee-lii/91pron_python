"""Persistent, offline crawler.v3 regression suite.

Run from the repository root with:
    python3 -B -m unittest discover -s tests -v

Every source response and media probe is synthetic.  Tests must never contact a
real target site.
"""

import ast
import datetime as dt
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = (
    "Kanav/Kanav.py",
    "MemoJav/MemoJav.py",
    "Pektino/Pektino.py",
    "Porny91/Porny91.py",
    "Xhotlist/Xhotlist.py",
    "XiaoHuangNiao/XiaoHuangNiao.py",
)
PAGED = SCRIPTS[:-1]
ALLOWED_FEED_KEYS = {"id", "label", "default"}
PAGE_KEYS = {"items", "next_cursor"}
CANDIDATE_KEYS = {"discovery_key", "source_id", "locator"}
ITEM_KEYS = {
    "discovery_key", "source_id", "title", "media", "thumbnail",
    "detail_url", "author", "description", "duration_seconds", "tags",
}


def future(seconds=20):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)).isoformat()


def expired():
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)).isoformat()


class FakeResponse:
    def __init__(self, status=200, body=b"ok", headers=None):
        self.status_code = status
        self._body = body
        self.headers = dict(headers or {})

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def iter_content(self, unused_size):
        if self._body:
            yield self._body


class FakeSession:
    """Minimal requests.Session double shared by all three transport styles."""

    def __init__(self, responses=None):
        self.responses = list(responses or [FakeResponse()])
        self.calls = []
        self.headers = {}
        self.proxies = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.trust_env = True

    def _send(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected automatic retry")
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        return self._send("GET", url, **kwargs)

    def request(self, method, url, **kwargs):
        return self._send(method, url, **kwargs)

    def mount(self, *unused):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False


class CrawlerProtocolV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules = {}
        for index, relative in enumerate(SCRIPTS):
            spec = importlib.util.spec_from_file_location(
                "offline_protocol_crawler_%d" % index, ROOT / relative)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls.modules[relative] = module
        cls.temp = tempfile.TemporaryDirectory(prefix="crawler-v3-tests-")
        cls.work = Path(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def job(self, relative, config=None, network=None, protocol="crawler.v3", feed_id=None):
        module = self.modules[relative]
        feeds = json.loads(module.CRAWLER_FEEDS)
        default = next(feed["id"] for feed in feeds if feed.get("default"))
        # Exercise KanAV's paginated feed by default; its home feed is intentionally
        # a one-page snapshot and cannot cover cursor-to-next-page behavior.
        selected_feed = feed_id or ("category" if relative == "Kanav/Kanav.py" else default)
        return {
            "protocol": protocol,
            "task_id": "offline-task",
            "crawler_id": "offline-crawler",
            "feed_id": selected_feed,
            "work_dir": str(self.work),
            "config": dict(config or {}),
            "network": dict(network or {}),
        }

    def crawler(self, relative, config=None, network=None):
        return self.modules[relative].CrawlerV3(self.job(relative, config, network))

    @staticmethod
    def command(cursor=None, limit=2, request_id="request-a", deadline_at=None):
        return {"type": "discover", "request_id": request_id, "cursor": cursor,
                "limit": limit, "deadline_at": deadline_at or future()}

    @staticmethod
    def assert_media_schema(test, media):
        test.assertIsInstance(media, dict)
        test.assertEqual(set(media) - {"type", "url", "headers"}, set())
        test.assertEqual(media.get("type"), "url")
        parsed = urlparse(media.get("url", ""))
        test.assertIn(parsed.scheme, {"http", "https"})
        test.assertTrue(parsed.hostname)
        if "headers" in media:
            test.assertIsInstance(media["headers"], dict)
            test.assertTrue(all(isinstance(k, str) and isinstance(v, str)
                                for k, v in media["headers"].items()))

    def assert_page_schema(self, page, limit):
        self.assertEqual(set(page), PAGE_KEYS)
        self.assertIsInstance(page["items"], list)
        self.assertLessEqual(len(page["items"]), limit)
        self.assertTrue(page["next_cursor"] is None or isinstance(page["next_cursor"], str))
        for candidate in page["items"]:
            self.assertEqual(set(candidate), CANDIDATE_KEYS)
            self.assertTrue(candidate["discovery_key"])
            self.assertTrue(candidate["source_id"])
            self.assertIsInstance(candidate["locator"], dict)

    def assert_item_schema(self, item, candidate):
        self.assertFalse(set(item) - ITEM_KEYS)
        self.assertEqual(item["discovery_key"], candidate["discovery_key"])
        self.assertEqual(item["source_id"], candidate["source_id"])
        self.assertIsInstance(item["title"], str)
        self.assertTrue(item["title"].strip())
        self.assert_media_schema(self, item["media"])
        if "thumbnail" in item:
            self.assert_media_schema(self, item["thumbnail"])

    @staticmethod
    def ids_for(relative):
        if relative == "MemoJav/MemoJav.py":
            return ["ABP-001", "ABP-002", "ABP-003", "ABP-004", "ABP-005"]
        return ["101", "102", "103", "104", "105"]

    def listing_fixture(self, relative, crawler, page, ids, has_next):
        """Realistic source-shaped listing fixture including an actual next link."""
        if relative == "Kanav/Kanav.py":
            cards = "".join(
                '<div class="video-item"><a href="/index.php/vod/play/id/{0}/sid/1/nid/1.html">'
                '<img data-original="/covers/{0}.jpg" alt="Video {0}"></a>'
                '<div class="entry-title"><a>Video {0}</a></div>'
                '<span class="model-view">01:02</span></div>'.format(value)
                for value in ids)
            next_link = ('<a href="/index.php/vod/type/id/{0}/page/{1}.html">next</a>'
                         .format(crawler.type_id, page + 1)) if has_next else ""
            return cards + next_link + ('<div class="no-videos">暂无</div>' if not ids else "")
        if relative == "MemoJav/MemoJav.py":
            cards = "".join(
                '<a class="video-item" href="/video/{0}"><img class="video-poster" '
                'src="/covers/{0}.jpg"><span class="video-title">Title {0}</span>'
                '<span class="video-metadata">1 • 2 • Actor</span></a>'.format(value)
                for value in ids)
            next_link = '<a href="/categories/milf/page-{0}">next</a>'.format(page + 1) if has_next else ""
            return cards + next_link + ('<div class="no-videos">No videos</div>' if not ids else "")
        if relative == "Porny91/Porny91.py":
            cards = "".join(
                '<div class="video-elem"><a class="title" href="/video/view/{0}">Title {0}</a>'
                '<div class="img" style="background:url(/covers/{0}.jpg)"></div>'
                '<small class="layer">01:02</small><small class="d-inline-block">作者: Actor 123次播放</small></div>'
                .format(value) for value in ids)
            root = "/video/category/" + crawler.feed_id
            next_link = '<a href="{0}/{1}">next</a>'.format(root, page + 1) if has_next else ""
            return cards + next_link + ('<div class="no-videos">No videos</div>' if not ids else "")
        if relative == "Xhotlist/Xhotlist.py":
            cards = "".join(
                '<a class="video-card" href="/video/{0}"><span class="thumb"><img '
                'src="/covers/{0}.jpg"></span><span class="duration">01:02</span>'
                '<span class="card-meta">1.2K</span></a>'.format(value) for value in ids)
            root = urlparse(crawler.page_url(1)).path.rstrip("/")
            next_link = '<a href="{0}/page/{1}">next</a>'.format(root, page + 1) if has_next else ""
            return cards + next_link + ('<div class="no-videos">No videos</div>' if not ids else "")
        raise AssertionError(relative)

    def install_paged_discovery(self, relative, crawler, rows_by_page, final_page=3):
        """Install a zero-network listing backend and return its page-call log."""
        calls = []
        if relative == "Pektino/Pektino.py":
            def api(url, unused_deadline, unused_scope):
                page = int(parse_qs(urlparse(url).query)["page"][0])
                calls.append(page)
                rows = []
                for value in rows_by_page[page]:
                    rows.append({"url_cd": value, "title": "Title " + value,
                                 "detail_url": "https://fixture.invalid/movie/" + value,
                                 "video": "https://video.twimg.com/ext_tw_video/%s/a.mp4" % value})
                return {"items": rows, "currentPage": page, "lastPage": final_page}
            crawler._api_json = Mock(side_effect=api)
            return calls

        method_name = "_request" if relative == "Kanav/Kanav.py" else "_text" if relative == "MemoJav/MemoJav.py" else None
        if method_name:
            def fetch(url, *unused):
                match = list(__import__("re").finditer(r"(?:/page/|page-)(\d+)", url))
                page = int(match[-1].group(1)) if match else 1
                calls.append(page)
                return self.listing_fixture(relative, crawler, page, rows_by_page[page], page < final_page)
            setattr(crawler, method_name, Mock(side_effect=fetch))
        else:
            def fetch(url, *unused):
                path = urlparse(url).path.rstrip("/")
                found = __import__("re").search(r"(?:/page)?/(\d+)$", path)
                page = int(found.group(1)) if found else 1
                calls.append(page)
                return self.listing_fixture(relative, crawler, page, rows_by_page[page], page < final_page)
            crawler.http.fetch_text = Mock(side_effect=fetch)
        return calls

    def xhn_payload(self, count=5):
        data = []
        for index in range(1, count + 1):
            value = str(9000 + index)
            data.append({
                "tweetId": value, "text": "Native title %s #tag" % value,
                "author": {"userName": "actor"}, "viewCount": "12",
                "mediaUrls": [{"type": "video", "url":
                    "https://video.twimg.com/ext_tw_video/%s/high.mp4" % value,
                    "bitrate": 1000, "duration": 62000}],
                "extendedEntities": {"media": []},
            })
        return {"success": True, "data": data}

    # --- declarations, startup, command loop ---------------------------------

    def test_declarations_and_feed_schema_are_static_and_valid(self):
        for relative, module in self.modules.items():
            with self.subTest(crawler=relative):
                tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
                declarations = {}
                for node in tree.body:
                    if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.lineno <= 200:
                        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                        for target in targets:
                            if isinstance(target, ast.Name) and target.id in {"CRAWLER_NAME", "CRAWLER_PROTOCOL", "CRAWLER_FEEDS"}:
                                self.assertIsInstance(node.value, ast.Constant)
                                self.assertIsInstance(node.value.value, str)
                                self.assertNotIn(target.id, declarations)
                                declarations[target.id] = node.value.value
                self.assertEqual(set(declarations), {"CRAWLER_NAME", "CRAWLER_PROTOCOL", "CRAWLER_FEEDS"})
                self.assertEqual(module.CRAWLER_PROTOCOL, "crawler.v3")
                self.assertTrue(1 <= len(module.CRAWLER_NAME.strip()) <= 80)
                feeds = json.loads(module.CRAWLER_FEEDS)
                self.assertTrue(1 <= len(feeds) <= 64)
                self.assertEqual(sum(feed.get("default") is True for feed in feeds), 1)
                self.assertEqual(len({feed["id"] for feed in feeds}), len(feeds))
                for feed in feeds:
                    self.assertFalse(set(feed) - ALLOWED_FEED_KEYS)
                    self.assertRegex(feed["id"], r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
                    self.assertEqual(feed["label"], feed["label"].strip())

    def test_protocol_error_exposes_normative_fields(self):
        for relative, module in self.modules.items():
            with self.subTest(crawler=relative):
                error = module.ProtocolError("item", "not_found", "gone", False)
                self.assertEqual(error.fields, {"scope": "item", "code": "not_found",
                                                "message": "gone", "retryable": False})

    def test_jobs_reject_v2_and_each_required_field(self):
        required = ("protocol", "task_id", "crawler_id", "feed_id", "work_dir")
        for relative, module in self.modules.items():
            with self.subTest(crawler=relative, case="v2"):
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    module.validate_job(self.job(relative, protocol="crawler.v2"))
            for field in required:
                with self.subTest(crawler=relative, missing=field):
                    job = self.job(relative)
                    del job[field]
                    with self.assertRaises((ValueError, KeyError, TypeError)):
                        module.validate_job(job)

    def test_copied_single_file_stop_has_exact_id_no_startup_output_and_exit_zero(self):
        with tempfile.TemporaryDirectory(prefix="copied-crawler-") as directory:
            work = Path(directory)
            for relative in SCRIPTS:
                with self.subTest(crawler=relative):
                    copied = work / Path(relative).name
                    shutil.copyfile(ROOT / relative, copied)
                    job_file = work / "job.json"
                    job_file.write_text(json.dumps(self.job(relative)), encoding="utf-8")
                    stop = {"type": "stop", "request_id": "exact-stop-id",
                            "reason": "target_reached", "deadline_at": future()}
                    environment = dict(os.environ)
                    environment.update({"HTTP_PROXY": "http://127.0.0.1:1",
                                        "HTTPS_PROXY": "http://127.0.0.1:1",
                                        "NO_PROXY": ""})
                    result = subprocess.run(
                        [sys.executable, "-B", str(copied), "--job", str(job_file)],
                        input=json.dumps(stop) + "\n", text=True, capture_output=True,
                        cwd=work, env=environment, timeout=4)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines(), [
                        json.dumps({"type": "stopped", "request_id": "exact-stop-id"},
                                   ensure_ascii=False, separators=(",", ":"))])

    def test_invalid_job_never_writes_protocol_stdout(self):
        for relative in SCRIPTS:
            with self.subTest(crawler=relative):
                job_file = self.work / (Path(relative).stem + "-v2.json")
                job_file.write_text(json.dumps(self.job(relative, protocol="crawler.v2")), encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, "-B", str(ROOT / relative), "--job", str(job_file)],
                    input="", text=True, capture_output=True, timeout=4)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_command_loop_continues_after_malformed_and_command_error(self):
        for relative in SCRIPTS:
            with self.subTest(crawler=relative):
                job_file = self.work / (Path(relative).stem + "-loop.json")
                job_file.write_text(json.dumps(self.job(relative)), encoding="utf-8")
                bad_json = '{"type":"discover","request_id":"broken",\n'
                unknown = json.dumps({"type": "bogus", "request_id": "bad-command",
                                      "deadline_at": future()})
                stop = json.dumps({"type": "stop", "request_id": "after-errors",
                                   "deadline_at": future()})
                result = subprocess.run(
                    [sys.executable, "-B", str(ROOT / relative), "--job", str(job_file)],
                    input=bad_json + unknown + "\n" + stop + "\n", text=True,
                    capture_output=True, timeout=4)
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = [json.loads(line) for line in result.stdout.splitlines()]
                self.assertEqual(len(lines), 3)
                self.assertEqual(lines[0]["type"], "error")
                self.assertEqual(lines[1]["request_id"], "bad-command")
                self.assertEqual(lines[1]["type"], "error")
                self.assertEqual(lines[2], {"type": "stopped", "request_id": "after-errors"})

    # --- discovery ------------------------------------------------------------

    def test_discover_overflow_is_per_source_deterministic_and_idempotent(self):
        for relative in PAGED:
            values = self.ids_for(relative)
            crawler = self.crawler(relative, {"candidate_budget": 1, "seen": [values[0]],
                                               "max_pages": 1})
            try:
                calls = self.install_paged_discovery(relative, crawler, {1: values[:3]}, final_page=1)
                first = crawler.discover(self.command(limit=2, request_id="one"))
                retry = crawler.discover(self.command(limit=2, request_id="new-request-id"))
                self.assertEqual(first, retry)
                self.assertEqual([item["source_id"] for item in first["items"]], values[:2])
                self.assertEqual(first["next_cursor"], "page:1:2")
                tail = crawler.discover(self.command(first["next_cursor"], 2, "tail"))
                self.assertEqual([item["source_id"] for item in tail["items"]], values[2:3])
                self.assertIsNone(tail["next_cursor"])
                self.assertEqual(calls, [1])
                self.assert_page_schema(first, 2)
                self.assert_page_schema(tail, 2)
            finally:
                crawler.close()

    def test_duplicate_and_empty_intermediate_pages_follow_actual_next_metadata(self):
        for relative in PAGED:
            for middle in ("duplicate", "empty"):
                with self.subTest(crawler=relative, middle=middle):
                    crawler = self.crawler(relative, {"max_pages": 1})
                    try:
                        values = self.ids_for(relative)
                        page2 = values[:3] if middle == "duplicate" else []
                        calls = self.install_paged_discovery(
                            relative, crawler, {1: values[:3], 2: page2,
                                                3: [values[1], values[3], values[4]]}, final_page=3)
                        page1 = crawler.discover(self.command(None, 100))
                        page2_result = crawler.discover(self.command(page1["next_cursor"], 100))
                        self.assertEqual(page2_result["items"], [])
                        self.assertEqual(page2_result["next_cursor"], "page:3:0")
                        self.assertEqual(page2_result,
                                         crawler.discover(self.command(page1["next_cursor"], 100,
                                                                       "same-cursor-new-id")))
                        page3 = crawler.discover(self.command(page2_result["next_cursor"], 100))
                        self.assertEqual([item["source_id"] for item in page3["items"]],
                                         values[3:5])
                        self.assertIsNone(page3["next_cursor"])
                        self.assertEqual(calls, [1, 2, 3])
                    finally:
                        crawler.close()

    def test_discover_never_fetches_details_or_probes_media(self):
        for relative in PAGED:
            crawler = self.crawler(relative)
            try:
                self.install_paged_discovery(relative, crawler,
                                             {1: self.ids_for(relative)[:2]}, final_page=1)
                forbidden = []
                if hasattr(crawler, "_probe"):
                    crawler._probe = Mock(side_effect=AssertionError("discover probed media"))
                    forbidden.append(crawler._probe)
                if hasattr(crawler, "http"):
                    crawler.http.probe_media = Mock(side_effect=AssertionError("discover probed media"))
                    forbidden.append(crawler.http.probe_media)
                result = crawler.discover(self.command(limit=2))
                self.assertEqual(len(result["items"]), 2)
                for mock in forbidden:
                    mock.assert_not_called()
            finally:
                crawler.close()

    def test_xiaohuangniao_snapshot_is_finite_cached_and_limits_are_independent(self):
        relative = "XiaoHuangNiao/XiaoHuangNiao.py"
        crawler = self.crawler(relative, {"limit": 5, "candidate_budget": 1,
                                           "seen": ["9001"], "max_pages": 1})
        try:
            payload = self.xhn_payload(5)
            crawler.http.fetch_json = Mock(return_value=payload)
            crawler.http.probe_media = Mock(side_effect=AssertionError("discover must not probe"))
            first = crawler.discover(self.command(None, 2, "first"))
            retry = crawler.discover(self.command(None, 2, "retry"))
            second = crawler.discover(self.command(first["next_cursor"], 2, "second"))
            final = crawler.discover(self.command(second["next_cursor"], 2, "final"))
            self.assertEqual(first, retry)
            self.assertEqual([len(first["items"]), len(second["items"]), len(final["items"])], [2, 2, 1])
            self.assertIsNone(final["next_cursor"])
            crawler.http.fetch_json.assert_called_once()
            requested = crawler.http.fetch_json.call_args.args[0]
            self.assertEqual(parse_qs(urlparse(requested).query)["limit"], ["5"])
            crawler.http.probe_media.assert_not_called()
        finally:
            crawler.close()

    # --- resolve --------------------------------------------------------------

    def resolve_fixture(self, relative):
        crawler = self.crawler(relative, {"existing_tags": ["kept"]})
        deadline = future()
        if relative == "Kanav/Kanav.py":
            candidate = {"discovery_key": "detail:101", "source_id": "101",
                         "locator": {"id": "101", "detail_url": "https://fixture.invalid/detail/101"}}
            crawler.rows["101"] = {"title": "Listing title", "thumbnail_url":
                                   "https://fixture.invalid/covers/101.jpg", "duration_seconds": 62}
            player = {"id": "101", "url": "https://cdn.invalid/101.m3u8",
                      "vod_data": {"vod_name": "Native title", "vod_actor": "Actor"}}
            crawler._request = Mock(return_value="<script>player_aaaa = %s;</script>" % json.dumps(player))
        elif relative == "MemoJav/MemoJav.py":
            candidate = {"discovery_key": "detail:ABP-001", "source_id": "ABP-001",
                         "locator": {"id": "ABP-001", "detail_url": "https://fixture.invalid/video/ABP-001"}}
            crawler.rows["ABP-001"] = {"title": "Listing title", "thumbnail_url":
                                       "https://fixture.invalid/cover.jpg", "meta": "a • b • Actor"}
            crawler._text = Mock(return_value='<h1 id="title">ABP-001 - Native title</h1>'
                                 '<video id="preview-vid" src="https://cdn.invalid/preview.mp4" '
                                 'poster="https://cdn.invalid/poster.jpg"></video>')
            crawler._probe = Mock(side_effect=["", "https://cdn.invalid/preview.mp4"])
        elif relative == "Pektino/Pektino.py":
            candidate = {"discovery_key": "detail:tweet101", "source_id": "tweet101",
                         "locator": {"id": "tweet101", "url_cd": "tweet101",
                                     "title": "Listing title", "author": "actor",
                                     "detail_url": "https://fixture.invalid/movie/tweet101",
                                     "media_urls": ["https://video.twimg.com/ext/a.mp4"]}}
            crawler._probe = Mock(side_effect=["", "https://video.twimg.com/ext/fallback.mp4"])
            crawler._api_json = Mock(return_value={"data": {"id": "tweet101", "title": "Native title",
                "video": "https://video.twimg.com/ext/fallback.mp4",
                "thumbnail": "https://pbs.twimg.com/media/cover.jpg"}})
        elif relative == "Porny91/Porny91.py":
            candidate = {"discovery_key": "video:101", "source_id": "101",
                         "locator": {"id": "101", "detail_url": "https://fixture.invalid/video/view/101"}}
            crawler.metadata["101"] = {"title": "Listing", "author": "Actor",
                                       "thumbnail_url": "https://fixture.invalid/cover.jpg", "duration_seconds": 62}
            crawler.http.fetch_text = Mock(return_value='<h1>Native title</h1><video id="video-play" '
                                                   'src="https://cdn.invalid/native.mp4" poster="/poster.jpg"></video>')
        elif relative == "Xhotlist/Xhotlist.py":
            candidate = {"discovery_key": "video:101", "source_id": "101",
                         "locator": {"id": "101", "detail_url": "https://fixture.invalid/video/101"}}
            crawler.metadata["101"] = {"title": "Listing", "thumbnail_url": "",
                                       "duration_seconds": 62}
            crawler.http.fetch_text = Mock(return_value='<h1>Native title</h1><video><source '
                'src="https://video.twimg.com/ext_tw_video/101/native.mp4"></video>'
                '<div class="tags"><a>kept</a><a>discarded</a></div>')
            crawler.http.probe_media = Mock(return_value=None)
        else:
            candidate = {"discovery_key": "tweet:9001", "source_id": "9001",
                         "locator": {"id": "9001"}}
            crawler.http.fetch_json = Mock(return_value=self.xhn_payload(1))
            crawler.http.probe_media = Mock(return_value=None)
        command = {"type": "resolve", "request_id": "resolve-one", "candidate": candidate,
                   "deadline_at": deadline}
        return crawler, candidate, command

    def test_resolve_preserves_native_identity_title_fallback_urls_and_media_headers(self):
        for relative in SCRIPTS:
            crawler, candidate, command = self.resolve_fixture(relative)
            try:
                item = crawler.resolve(command)
                self.assert_item_schema(item, candidate)
                self.assertIn("Native title", item["title"])
                self.assertIn("headers", item["media"])
                self.assertIn("User-Agent", item["media"]["headers"])
                if relative == "MemoJav/MemoJav.py":
                    self.assertEqual(item["media"]["url"], "https://cdn.invalid/preview.mp4")
                    self.assertEqual(crawler._probe.call_count, 2)
                if relative == "Pektino/Pektino.py":
                    self.assertEqual(item["media"]["url"], "https://video.twimg.com/ext/fallback.mp4")
                    self.assertEqual(crawler._probe.call_count, 2)
                if relative == "Xhotlist/Xhotlist.py":
                    self.assertEqual(item.get("tags"), ["kept"])
            finally:
                crawler.close()

    def test_resolve_preserves_supplied_source_id_while_locator_id_drives_lookup(self):
        for relative in SCRIPTS:
            with self.subTest(crawler=relative):
                crawler, candidate, command = self.resolve_fixture(relative)
                try:
                    supplied_id = "backend-stable-id"
                    changed = dict(candidate, source_id=supplied_id)
                    command["candidate"] = changed
                    item = crawler.resolve(command)
                    self.assert_item_schema(item, changed)
                    self.assertEqual(item["source_id"], supplied_id)
                    self.assertIn("Native title", item["title"])
                    locator_id = candidate["locator"]["id"]
                    if relative == "Kanav/Kanav.py":
                        self.assertIn('"id": "%s"' % locator_id,
                                      crawler._request.return_value)
                    elif relative == "MemoJav/MemoJav.py":
                        self.assertIn(locator_id, item["title"])
                    elif relative == "Pektino/Pektino.py":
                        self.assertIn(locator_id, crawler._api_json.call_args.args[0])
                    elif relative in {"Porny91/Porny91.py", "Xhotlist/Xhotlist.py"}:
                        self.assertEqual(crawler.http.fetch_text.call_args.args[0],
                                         candidate["locator"]["detail_url"])
                    else:
                        self.assertIn(locator_id, crawler.rows)
                finally:
                    crawler.close()

    def test_stale_twitter_cdn_403_falls_back_to_readable_alternative(self):
        relatives = ("Pektino/Pektino.py", "Xhotlist/Xhotlist.py",
                     "XiaoHuangNiao/XiaoHuangNiao.py")
        stale = "https://video.twimg.com/ext_tw_video/stale/old.mp4"
        readable = "https://video.twimg.com/ext_tw_video/fresh/good.mp4"
        for relative in relatives:
            with self.subTest(crawler=relative):
                module = self.modules[relative]
                crawler = self.crawler(relative)
                fake = FakeSession([
                    FakeResponse(403, b"", {"Content-Type": "text/plain"}),
                    FakeResponse(206, b"video", {"Content-Type": "video/mp4"}),
                ])
                try:
                    if relative == "Pektino/Pektino.py":
                        candidate = {"discovery_key": "detail:lookup-1", "source_id": "stable-1",
                                     "locator": {"id": "lookup-1", "url_cd": "lookup-1",
                                                 "title": "Native title",
                                                 "detail_url": "https://fixture.invalid/movie/lookup-1",
                                                 "media_urls": [stale, readable]}}
                        crawler.media_session = fake
                    elif relative == "Xhotlist/Xhotlist.py":
                        candidate = {"discovery_key": "video:lookup-1", "source_id": "stable-1",
                                     "locator": {"id": "lookup-1",
                                                 "detail_url": "https://fixture.invalid/video/lookup-1"}}
                        crawler.http.fetch_text = Mock(return_value=(
                            '<h1>Native title</h1><video><source src="%s">'
                            '<source src="%s"></video>' % (stale, readable)))
                    else:
                        candidate = {"discovery_key": "tweet:lookup-1", "source_id": "stable-1",
                                     "locator": {"id": "lookup-1"}}
                        payload = self.xhn_payload(1)
                        payload["data"][0]["tweetId"] = "lookup-1"
                        payload["data"][0]["mediaUrls"] = [
                            {"type": "video", "url": stale, "bitrate": 2000, "duration": 62000},
                            {"type": "video", "url": readable, "bitrate": 1000, "duration": 62000},
                        ]
                        crawler.http.fetch_json = Mock(return_value=payload)
                    command = {"type": "resolve", "request_id": "cdn-fallback",
                               "candidate": candidate, "deadline_at": future()}
                    session_patch = patch.object(module.requests, "Session", return_value=fake)
                    delay_patch = (patch.object(module.random, "uniform", return_value=0)
                                   if hasattr(module, "random") else patch.object(module.time, "sleep"))
                    with session_patch, delay_patch:
                        item = crawler.resolve(command)
                    self.assertEqual(item["source_id"], "stable-1")
                    self.assertEqual(item["media"]["url"], readable)
                    self.assertEqual([call[1] for call in fake.calls], [stale, readable])
                finally:
                    crawler.close()

    def test_xhotlist_rejects_twitter_hostname_confusion_before_probe(self):
        relative = "Xhotlist/Xhotlist.py"
        module = self.modules[relative]
        crawler = self.crawler(relative)
        candidate = {"discovery_key": "video:lookup-1", "source_id": "stable-1",
                     "locator": {"id": "lookup-1",
                                 "detail_url": "https://fixture.invalid/video/lookup-1"}}
        try:
            crawler.http.fetch_text = Mock(return_value=(
                '<h1>Native title</h1><video><source '
                'src="https://video.twimg.com.attacker.invalid/trap.mp4"></video>'))
            crawler.http.probe_media = Mock(side_effect=AssertionError("malicious host was probed"))
            with self.assertRaises(module.ProtocolError) as raised:
                crawler.resolve({"type": "resolve", "request_id": "host-check",
                                 "candidate": candidate, "deadline_at": future()})
            self.assertEqual(raised.exception.fields["scope"], "item")
            self.assertEqual(raised.exception.fields["code"], "parse_failed")
            crawler.http.probe_media.assert_not_called()
        finally:
            crawler.close()

    # --- deadlines and transport ---------------------------------------------

    def raw_request(self, relative, crawler, url, deadline, scope):
        if relative == "Kanav/Kanav.py":
            return crawler._request(url, deadline, scope)
        if relative == "MemoJav/MemoJav.py":
            return crawler._request(url, deadline, scope)
        if relative == "Pektino/Pektino.py":
            return crawler._response(crawler.api_session, url, deadline, scope)
        if relative == "Porny91/Porny91.py":
            return crawler.http.fetch_text(url, deadline, scope)
        return crawler.http.request(url, deadline, scope)

    def test_expired_deadline_rejects_before_any_network_call(self):
        for relative, module in self.modules.items():
            crawler = self.crawler(relative)
            fake = FakeSession()
            try:
                deadline = module.CommandDeadline(expired(), "source")
                if relative in {"Kanav/Kanav.py", "MemoJav/MemoJav.py"}:
                    crawler.session = fake
                    context = patch.object(module.requests, "Session", return_value=fake)
                elif relative == "Pektino/Pektino.py":
                    crawler.api_session = fake
                    context = patch.object(module.requests, "Session", return_value=fake)
                else:
                    context = patch.object(module.requests, "Session", return_value=fake)
                with context, patch.object(module.random, "uniform", return_value=0) if hasattr(module, "random") else patch.object(module.time, "sleep"):
                    with self.assertRaises(module.ProtocolError) as raised:
                        self.raw_request(relative, crawler, "https://fixture.invalid/list", deadline, "source")
                self.assertEqual(raised.exception.fields["scope"], "source")
                self.assertEqual(raised.exception.fields["code"], "source_unavailable")
                self.assertEqual(fake.calls, [])
            finally:
                crawler.close()

    def test_network_timeout_uses_remaining_time_and_transport_does_not_retry(self):
        for relative, module in self.modules.items():
            crawler = self.crawler(relative)
            fake = FakeSession([FakeResponse(200, b"ok", {"Content-Type": "text/plain"})])
            try:
                deadline = module.CommandDeadline(future(2), "source")
                if relative in {"Kanav/Kanav.py", "MemoJav/MemoJav.py"}:
                    crawler.session = fake
                elif relative == "Pektino/Pektino.py":
                    crawler.api_session = fake
                context = patch.object(module.requests, "Session", return_value=fake)
                delay_patch = (patch.object(module.random, "uniform", return_value=0)
                               if hasattr(module, "random") else patch.object(module.time, "sleep"))
                with context, delay_patch:
                    self.raw_request(relative, crawler, "https://fixture.invalid/ok", deadline, "source")
                self.assertEqual(len(fake.calls), 1)
                timeout = fake.calls[0][2]["timeout"]
                total = getattr(timeout, "total", None)
                total = total if isinstance(total, (int, float)) else getattr(timeout, "total_timeout", None)
                self.assertIsNotNone(total)
                self.assertGreater(total, 0)
                self.assertLessEqual(total, 2.1)
            finally:
                crawler.close()

    def test_credentialed_redirect_is_rejected_without_following_it(self):
        relatives = ("Porny91/Porny91.py", "Xhotlist/Xhotlist.py",
                     "XiaoHuangNiao/XiaoHuangNiao.py")
        location = "https://user:password@video.twimg.com/private.mp4"
        for relative in relatives:
            with self.subTest(crawler=relative):
                module = self.modules[relative]
                crawler = self.crawler(relative)
                fake = FakeSession([FakeResponse(302, b"", {"Location": location})])
                try:
                    deadline = module.CommandDeadline(future(5), "item")
                    delay_patch = patch.object(module.random, "uniform", return_value=0)
                    with patch.object(module.requests, "Session", return_value=fake), delay_patch:
                        with self.assertRaises((ValueError, module.ProtocolError)) as raised:
                            self.raw_request(relative, crawler,
                                             "https://fixture.invalid/redirect", deadline, "item")
                    if isinstance(raised.exception, module.ProtocolError):
                        self.assertEqual(raised.exception.fields["scope"], "item")
                        self.assertEqual(raised.exception.fields["code"], "parse_failed")
                        self.assertFalse(raised.exception.fields["retryable"])
                    self.assertEqual(len(fake.calls), 1)
                finally:
                    crawler.close()

    def test_http_status_mapping_scope_and_single_attempt(self):
        cases = ((401, "auth_required", False), (403, "auth_required", False),
                 (404, "not_found", False), (429, "rate_limited", True),
                 (503, "source_unavailable", True))
        for relative, module in self.modules.items():
            for operation_scope in ("source", "item"):
                for status, code, retryable in cases:
                    with self.subTest(crawler=relative, scope=operation_scope, status=status):
                        crawler = self.crawler(relative)
                        fake = FakeSession([FakeResponse(status, b"", {"Retry-After": "17"})])
                        try:
                            deadline = module.CommandDeadline(future(5), operation_scope)
                            if relative in {"Kanav/Kanav.py", "MemoJav/MemoJav.py"}:
                                crawler.session = fake
                            elif relative == "Pektino/Pektino.py":
                                crawler.api_session = fake
                            context = patch.object(module.requests, "Session", return_value=fake)
                            delay_patch = (patch.object(module.random, "uniform", return_value=0)
                                           if hasattr(module, "random") else patch.object(module.time, "sleep"))
                            with context, delay_patch, self.assertRaises(module.ProtocolError) as raised:
                                self.raw_request(relative, crawler, "https://fixture.invalid/status", deadline,
                                                 operation_scope)
                            fields = raised.exception.fields
                            self.assertEqual(fields["code"], code)
                            expected_scope = "source" if code in {"auth_required", "rate_limited"} else operation_scope
                            self.assertEqual(fields["scope"], expected_scope)
                            self.assertEqual(fields["retryable"], retryable)
                            if retryable:
                                self.assertEqual(fields.get("retry_after_seconds"), 17)
                            self.assertEqual(len(fake.calls), 1)
                        finally:
                            crawler.close()

    def test_pektino_routes_api_direct_and_only_configured_proxy_to_media(self):
        relative = "Pektino/Pektino.py"
        proxy = "http://127.0.0.1:7890"
        crawler = self.crawler(relative, network={"proxy_url": proxy})
        try:
            self.assertIs(crawler.api_session.trust_env, False)
            self.assertEqual(crawler.api_session.proxies, {})
            self.assertIs(crawler.media_session.trust_env, False)
            self.assertEqual(crawler.media_session.proxies,
                             {"http": proxy, "https": proxy})
        finally:
            crawler.close()


if __name__ == "__main__":
    unittest.main()
