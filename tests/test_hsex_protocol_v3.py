"""Hsex crawler.v3 offline regression tests; no live source or CDN requests.

Fixtures deliberately retain only structural HTML, not captured page content.
Run: python3 -B -m unittest discover -s tests -v
"""

import ast
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.parse import urlparse

import requests


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Hsex/Hsex.py"
spec = importlib.util.spec_from_file_location("offline_hsex", SCRIPT)
hsex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hsex)


def future(seconds=20):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=seconds)).isoformat()


def listing(ids=("101", "102", "103"), page=1, next_page=2, prefix="list", next_href=None):
    cards = "".join(
        '<div class="col"><div class="thumbnail"><a href="video-{0}.htm">'
        '<div class="image" style="background-image: url(\'https://img.invalid/{0}.webp\')">'
        '<var class="duration">01:02</var></div></a><div class="caption title">'
        '<h5><a href="video-{0}.htm">List title {0}</a></h5></div>'
        '<div class="info"><a href="user.htm?author=actor">Actor</a></div></div></div>'.format(value)
        for value in ids)
    following = ('<li><a href="%s">▶</a></li>' % (next_href or "%s-%d.htm" % (prefix, next_page))
                 if next_page is not None else "")
    pager = ('<ul class="pagination1"><li><a href="%s-1.htm">◀</a></li>'
             '<li class="page-item active"><a href="%s-%d.htm">%d</a></li>%s</ul>'
             % (prefix, prefix, page, page, following))
    return pager + '<div class="row body">' + cards + '</div>' + pager


MEDIA_URL = "https://cdn.invalid/123/signed%2Fpath/hls/101/index.m3u8?token=a%2Bb&expires=42"
DETAIL = (
    '<meta name="referrer" content="no-referrer">'
    '<meta property="og:url" content="{origin}/video-101.htm">'
    '<meta property="og:title" content="OG title">'
    '<meta property="og:video:actor" content="Detail actor">'
    '<meta property="video:duration" content="00:06:14">'
    '<meta name="description" content="Description">'
    '<meta property="og:image" content="https://img.invalid/og.jpg">'
    '<div class="panel-heading"><h3 class="panel-title">Native title</h3></div>'
    '<video id="video-play" poster="https://img.invalid/poster.webp">'
    '<source id="video-source" src="' + MEDIA_URL.replace('&', '&amp;') + '" '
    'type="application/x-mpegURL"></video>')


class FakeResponse:
    def __init__(self, status=200, body=b"ok", headers=None):
        self.status_code, self.body, self.headers = status, body, dict(headers or {})

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def iter_content(self, unused):
        if self.body:
            yield self.body


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
        self.headers, self.proxies, self.mounts = {}, {}, {}
        self.trust_env = True

    def mount(self, name, adapter):
        self.mounts[name] = adapter

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected retry or extra request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False


class HsexProtocolV3Tests(unittest.TestCase):
    def job(self, feed_id="latest", config=None, network=None):
        return {"protocol": "crawler.v3", "task_id": "test-task", "crawler_id": "test-crawler",
                "feed_id": feed_id, "work_dir": tempfile.gettempdir(),
                "config": dict(config or {}), "network": dict(network or {})}

    def crawler(self, **kwargs):
        crawler = hsex.CrawlerV3(self.job(**kwargs))
        self.addCleanup(crawler.close)
        return crawler

    @staticmethod
    def discover(cursor=None, limit=2, deadline_at=None):
        return {"type": "discover", "request_id": "discovery", "cursor": cursor,
                "limit": limit, "deadline_at": deadline_at or future()}

    @staticmethod
    def resolve(source_id="stable-backend-id", native="101", **locator):
        return {"type": "resolve", "request_id": "resolve", "deadline_at": future(),
                "candidate": {"discovery_key": "video:" + native, "source_id": source_id,
                              "locator": {"id": native, **locator}}}

    def fixture_pages(self, crawler, pages):
        def fetch(url, *unused):
            self.assertRegex(urlparse(url).path, r"/list-\d+\.htm")
            page = int(urlparse(url).path.removeprefix('/list-').removesuffix('.htm'))
            return pages[page]
        crawler._request = Mock(side_effect=fetch)
        return crawler._request

    def test_static_declarations_and_feeds(self):
        found = {}
        for node in ast.parse(SCRIPT.read_text()).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"CRAWLER_NAME", "CRAWLER_PROTOCOL", "CRAWLER_FEEDS"}:
                        self.assertLessEqual(node.lineno, 200)
                        self.assertIsInstance(node.value, ast.Constant)
                        self.assertNotIn(target.id, found)
                        found[target.id] = node.value.value
        self.assertEqual(found["CRAWLER_NAME"], "Hsex")
        self.assertEqual(found["CRAWLER_PROTOCOL"], "crawler.v3")
        feeds = json.loads(found["CRAWLER_FEEDS"])
        self.assertEqual([f["id"] for f in feeds], ["latest", "weekly", "monthly", "five-min", "long", "hot"])
        self.assertEqual(sum(f.get("default") is True for f in feeds), 1)
        self.assertEqual(next(f["id"] for f in feeds if f.get("default")), "latest")
        for f in feeds:
            self.assertFalse(set(f) - {"id", "label", "default"})

    def test_required_job_fields_and_config_validation(self):
        for name in ("protocol", "task_id", "crawler_id", "feed_id", "work_dir"):
            job = self.job()
            del job[name]
            with self.subTest(field=name), self.assertRaises((ValueError, KeyError)):
                hsex.CrawlerV3(job)
        for updates in ({"protocol": "crawler.v2"}, {"feed_id": "unknown"}, {"work_dir": "relative"},
                        {"config": None}, {"network": []}, {"task_id": " "}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                hsex.CrawlerV3({**self.job(), **updates})
        for base in ("https://user:pass@fixture.invalid", "https://fixture.invalid/path",
                     "https://fixture.invalid?x=1", "https://fixture.invalid/#x", "file:///tmp"):
            with self.subTest(base=base), self.assertRaises(ValueError):
                self.crawler(config={"base_url": base})
        self.assertEqual(self.crawler(config={"base_url": "http://127.0.0.1:4567/"}).base_url,
                         "http://127.0.0.1:4567")
        job = self.job()
        del job['config'], job['network']
        hsex.CrawlerV3(job).close()

    def test_feed_routes_and_identity_independent_of_feed(self):
        for feed, prefix in hsex.FEED_PATHS.items():
            with self.subTest(feed=feed):
                crawler = self.crawler(feed_id=feed, config={"category": "ignored", "max_pages": 1})
                crawler._request = Mock(return_value=listing(("101",), prefix=prefix, next_page=None))
                result = crawler.discover(self.discover())
                self.assertEqual(crawler._request.call_args.args[0], "https://hsex.icu/%s-1.htm" % prefix)
                self.assertEqual(result["items"], [{"discovery_key": "video:101", "source_id": "101", "locator": {"id": "101"}}])

    def test_list_css_thumbnail_metadata_and_discovery_no_detail_or_probe(self):
        crawler = self.crawler()
        crawler._request = Mock(return_value=listing())
        crawler.resolve = Mock(side_effect=AssertionError("discover fetched detail"))
        result = crawler.discover(self.discover())
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(crawler.rows["101"]["title"], "List title 101")
        self.assertEqual(crawler.rows["101"]["thumbnail_url"], "https://img.invalid/101.webp")
        self.assertEqual(crawler.rows["101"]["duration_seconds"], 62)
        self.assertEqual(crawler.rows["101"]["author"], "Actor")
        crawler._request.assert_called_once()
        self.assertTrue(crawler._request.call_args.args[0].endswith('/list-1.htm'))
        crawler.resolve.assert_not_called()

    def test_overflow_retry_and_overlap_snapshots(self):
        crawler = self.crawler(config={"candidate_budget": 1, "max_pages": 1, "seen": ["101"]})
        fetch = self.fixture_pages(crawler, {1: listing(), 2: listing(("103", "104"), 2, None)})
        first = crawler.discover(self.discover())
        self.assertEqual(first["next_cursor"], "page:1:2")
        self.assertEqual(first, crawler.discover(self.discover()))
        tail = crawler.discover(self.discover(first["next_cursor"]))
        self.assertEqual([v["source_id"] for v in tail["items"]], ["103"])
        second = crawler.discover(self.discover(tail["next_cursor"]))
        self.assertEqual([v["source_id"] for v in second["items"]], ["104"])
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(first, crawler.discover(self.discover()))
        self.assertEqual(fetch.call_count, 2)

    def test_duplicate_and_empty_pages_keep_valid_next_pointer(self):
        for middle in (("101", "102"), ()):
            with self.subTest(middle=middle):
                crawler = self.crawler()
                self.fixture_pages(crawler, {1: listing(("101", "102")),
                    2: listing(middle, 2, 3), 3: listing(("102", "105"), 3, None)})
                p1 = crawler.discover(self.discover(limit=100))
                p2 = crawler.discover(self.discover(p1["next_cursor"], 100))
                self.assertEqual(p2, {"items": [], "next_cursor": "page:3:0"})
                self.assertEqual(p2, crawler.discover(self.discover(p1["next_cursor"], 100)))
                p3 = crawler.discover(self.discover(p2["next_cursor"], 100))
                self.assertEqual([v["source_id"] for v in p3["items"]], ["105"])
                self.assertIsNone(p3["next_cursor"])

    def test_explicit_next_jump_path_query_preserved_without_cap(self):
        crawler = self.crawler()
        crawler._request = Mock(side_effect=[listing(("101",), next_page=99999,
                                                   next_href="/list-99999.htm?token=a%2Bb"),
                                             listing(("102",), 99999, None)])
        page = crawler.discover(self.discover())
        self.assertEqual(page["next_cursor"], "page:99999:0")
        last = crawler.discover(self.discover(page["next_cursor"]))
        self.assertIsNone(last["next_cursor"])
        self.assertEqual(crawler._request.call_args.args[0], "https://hsex.icu/list-99999.htm?token=a%2Bb")

    def test_invalid_next_targets_and_unrecognized_html_fail(self):
        for target in ("list-1.htm", "list-0.htm", "top_list-2.htm", "https://evil.invalid/list-2.htm",
                       "https://hsex.icu.evil.invalid/list-2.htm", "https://user:pass@hsex.icu/list-2.htm"):
            with self.subTest(target=target):
                crawler = self.crawler()
                crawler._request = Mock(return_value=listing(next_href=target))
                with self.assertRaises(hsex.ProtocolError) as raised:
                    crawler.discover(self.discover())
                self.assertEqual(raised.exception.fields["code"], "parse_failed")
                self.assertEqual(raised.exception.fields["scope"], "source")
        for text in ("<html>Verify you are human</html>", '<div class="row body"></div>',
                     listing().replace('class="page-item active"', 'class="page-item"'),
                     listing().replace('href="list-1.htm">1<', 'href="list-4.htm">1<')):
            crawler = self.crawler()
            crawler._request = Mock(return_value=text)
            with self.assertRaises(hsex.ProtocolError):
                crawler.discover(self.discover())

    def test_empty_final_structural_page_exhausts(self):
        crawler = self.crawler()
        crawler._request = Mock(return_value=listing((), next_page=None))
        self.assertEqual(crawler.discover(self.discover()), {"items": [], "next_cursor": None})

    def test_limits_cursors_deadlines_validated(self):
        crawler = self.crawler()
        crawler._request = Mock(return_value=listing())
        for limit in (True, 0, 101, "2"):
            with self.assertRaises(ValueError):
                crawler.discover(self.discover(limit=limit))
        for cursor in ("", "page:0:0", "page:1:-1", 2, "page:1:999"):
            with self.assertRaises(ValueError):
                crawler.discover(self.discover(cursor=cursor))
        command = self.discover()
        del command["cursor"]
        with self.assertRaises(ValueError):
            crawler.discover(command)
        for date in ("2020-01-01T00:00:00", "bad", None):
            with self.assertRaises(ValueError):
                hsex.CommandDeadline(date, "source")

    def test_resolve_exact_hls_metadata_no_referer_no_probe_preserves_source_id(self):
        crawler = self.crawler()
        crawler._request = Mock(return_value=DETAIL.format(origin=crawler.base_url))
        result = crawler.resolve(self.resolve(detail_url="https://evil.invalid/do-not-fetch"))
        self.assertEqual(result["discovery_key"], "video:101")
        self.assertEqual(result["source_id"], "stable-backend-id")
        self.assertEqual(result["title"], "Native title")
        self.assertEqual(result["author"], "Detail actor")
        self.assertEqual(result["description"], "Description")
        self.assertEqual(result["duration_seconds"], 374)
        self.assertEqual(result["media"]["url"], MEDIA_URL)
        self.assertEqual(result["thumbnail"]["url"], "https://img.invalid/poster.webp")
        self.assertEqual(result["detail_url"], "https://hsex.icu/video-101.htm")
        for name in ("media", "thumbnail"):
            self.assertEqual(result[name]["type"], "url")
            self.assertEqual(result[name]["headers"], {"User-Agent": hsex.USER_AGENT})
        crawler._request.assert_called_once()
        self.assertEqual(crawler._request.call_args.args[0], result['detail_url'])
        self.assertNotIn("tags", result)
        self.assertNotIn(None, result.values())

    def test_resolve_fallbacks_and_metadata_bounds(self):
        crawler = self.crawler()
        crawler.rows["101"] = {"title": "Cached", "thumbnail_url": "https://img.invalid/cached.jpg",
                               "duration_seconds": 62, "author": "Cached actor"}
        bare = '<video id="video-play"><source id="video-source" src="https://cdn.invalid/a.m3u8"></video>'
        for extra, expected_title, thumb in (
                ('<meta property="og:title" content="OG"><meta property="og:image" content="/og.jpg">', 'OG', 'https://hsex.icu/og.jpg'),
                ('', 'Cached', 'https://img.invalid/cached.jpg')):
            crawler._request = Mock(return_value=bare + extra)
            command = self.resolve()
            del command['candidate']['source_id']
            result = crawler.resolve(command)
            self.assertEqual(result['source_id'], '101')
            self.assertEqual(result['title'], expected_title)
            self.assertEqual(result['thumbnail']['url'], thumb)
            self.assertEqual(result['duration_seconds'], 62)
        huge = ('<meta property="og:title" content="' + '测' * 5000 + '">'
                '<meta property="og:video:actor" content="' + '测' * 2000 + '">'
                '<meta name="description" content="' + '测' * 30000 + '">')
        crawler._request = Mock(return_value=bare + huge)
        result = crawler.resolve(self.resolve())
        for key, maximum in (('title', 4096), ('author', 1024), ('description', 65536)):
            self.assertLessEqual(len(result[key].encode()), maximum)

    def test_resolve_bad_media_and_wrong_native_identity(self):
        for change in (lambda s: s.replace('video-101.htm', 'video-102.htm'),
                       lambda s: s.replace(MEDIA_URL.replace('&', '&amp;'), 'javascript:alert(1)'),
                       lambda s: s.replace('id="video-source"', 'id="other"'),
                       lambda s: '<html>Challenge</html>'):
            crawler = self.crawler()
            crawler._request = Mock(return_value=change(DETAIL.format(origin=crawler.base_url)))
            with self.assertRaises(hsex.ProtocolError) as raised:
                crawler.resolve(self.resolve())
            self.assertEqual(raised.exception.fields['code'], 'parse_failed')
            self.assertEqual(raised.exception.fields['scope'], 'item')
        crawler = self.crawler()
        crawler._request = Mock()
        with self.assertRaises(ValueError):
            crawler.resolve(self.resolve(native='../101'))
        crawler._request.assert_not_called()

    def test_download_headers_are_independent_explicit_validated_and_no_cookie_copy(self):
        crawler = self.crawler(config={'media_headers': {'X-Media': 'yes', 'Referer': 'https://custom.invalid/'},
                                       'thumbnail_headers': {'X-Thumb': 'yes'}})
        crawler._request = Mock(return_value=DETAIL.format(origin=crawler.base_url))
        item = crawler.resolve(self.resolve())
        self.assertEqual(item['media']['headers']['X-Media'], 'yes')
        self.assertNotIn('X-Media', item['thumbnail']['headers'])
        self.assertNotIn('Referer', item['thumbnail']['headers'])
        self.assertNotIn('Cookie', item['media']['headers'])
        for headers in ({'X': 'bad\nvalue'}, {'Bad Name': 'x'}, {'X': None}, None,
                        {'X-%d' % i: 'a' for i in range(65)}):
            with self.assertRaises(ValueError):
                self.crawler(config={'media_headers': headers})

    def test_status_mapping_and_no_automatic_retry(self):
        for scope in ('source', 'item'):
            for status, code, retryable in ((401, 'auth_required', False), (403, 'auth_required', False),
                    (404, 'not_found', False), (429, 'rate_limited', True), (503, 'source_unavailable', True)):
                with self.subTest(scope=scope, status=status):
                    crawler = self.crawler()
                    session = FakeSession([FakeResponse(status, headers={'Retry-After': '17'})])
                    with patch.object(hsex.requests, 'Session', return_value=session), self.assertRaises(hsex.ProtocolError) as raised:
                        crawler._request(crawler.base_url + '/list-1.htm', hsex.CommandDeadline(future(), scope), scope)
                    fields = raised.exception.fields
                    self.assertEqual(fields['code'], code)
                    self.assertEqual(fields['scope'], 'source' if code in {'auth_required', 'rate_limited'} else scope)
                    self.assertEqual(fields['retryable'], retryable)
                    if retryable:
                        self.assertEqual(fields['retry_after_seconds'], 17)
                    self.assertEqual(len(session.calls), 1)
                    for adapter in session.mounts.values():
                        self.assertEqual(adapter.max_retries.total, 0)

    def test_network_error_proxy_and_remaining_timeout(self):
        crawler = self.crawler(network={'proxy_url': 'http://127.0.0.1:7890'})
        session = FakeSession([requests.ConnectionError('offline')])
        with patch.object(hsex.requests, 'Session', return_value=session), self.assertRaises(hsex.ProtocolError) as raised:
            crawler._request(crawler.base_url + '/list-1.htm', hsex.CommandDeadline(future(2), 'source'), 'source')
        self.assertEqual(raised.exception.fields['code'], 'source_unavailable')
        self.assertTrue(raised.exception.fields['retryable'])
        self.assertEqual(session.proxies, {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'})
        self.assertFalse(session.trust_env)
        self.assertEqual(len(session.calls), 1)
        self.assertLessEqual(session.calls[0][1]['timeout'].total, 2)
        self.assertFalse(session.calls[0][1]['allow_redirects'])
        self.assertNotIn('Referer', session.headers)

    def test_expired_deadline_no_network_even_cached_and_politeness_bounded(self):
        crawler = self.crawler()
        with patch.object(hsex.requests, 'Session') as session:
            for command, operation in ((self.discover(deadline_at=future(-1)), crawler.discover),
                                       ({**self.resolve(), 'deadline_at': future(-1)}, crawler.resolve)):
                with self.assertRaises(hsex.ProtocolError):
                    operation(command)
            session.assert_not_called()
        crawler.last_request = time.monotonic()
        with patch.object(hsex.time, 'sleep') as sleep, self.assertRaises(hsex.ProtocolError):
            crawler._request(crawler.base_url + '/list-1.htm', hsex.CommandDeadline(future(0.1), 'source'), 'source')
        sleep.assert_not_called()

    def test_slow_listing_parser_times_out_and_late_completion_cannot_commit(self):
        crawler = self.crawler()
        crawler._request = Mock(return_value=listing())
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        original = crawler._parse_listing

        def slow_parser(*args):
            entered.set()
            release.wait(2)
            try:
                return original(*args)
            finally:
                finished.set()

        crawler._parse_listing = Mock(side_effect=slow_parser)
        started = time.monotonic()
        with self.assertRaises(hsex.ProtocolError) as raised:
            crawler.discover(self.discover(deadline_at=future(0.2)))
        self.assertTrue(entered.is_set())
        self.assertEqual(raised.exception.fields['code'], 'source_unavailable')
        self.assertLess(time.monotonic() - started, 0.25)
        self.assertEqual((crawler.pages, crawler.rows, crawler.page_urls), ({}, {}, {}))
        # While the parser remains blocked, another operation must not start a
        # second worker or make another source request.
        with self.assertRaises(hsex.ProtocolError):
            crawler.discover(self.discover(deadline_at=future(0.1)))
        self.assertEqual(crawler._request.call_count, 1)
        release.set()
        self.assertTrue(finished.wait(1))
        self.assertEqual((crawler.pages, crawler.rows, crawler.page_urls), ({}, {}, {}))
        crawler._parse_listing = original
        self.assertEqual(len(crawler.discover(self.discover())['items']), 2)

    def test_whole_operation_transaction_isolation_after_timeout(self):
        crawler = self.crawler()
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()

        def late_mutation(isolated, command, deadline):
            entered.set()
            release.wait(2)
            try:
                # Simulate a parser/operation that does not cooperate with
                # cancellation and mutates state even after its caller timed out.
                isolated.pages[7] = {'items': []}
                isolated.rows['late'] = {'title': 'late'}
                isolated.page_urls[8] = 'https://hsex.icu/list-8.htm'
                return {'items': [], 'next_cursor': None}
            finally:
                finished.set()

        with patch.object(hsex.CrawlerV3, '_discover', late_mutation):
            with self.assertRaises(hsex.ProtocolError):
                crawler.discover(self.discover(deadline_at=future(0.15)))
            self.assertTrue(entered.is_set())
            release.set()
            self.assertTrue(finished.wait(1))
        self.assertEqual((crawler.pages, crawler.rows, crawler.page_urls), ({}, {}, {}))

    def test_detail_parser_and_response_preparation_share_absolute_deadline(self):
        for phase in ('parser', 'serialization'):
            with self.subTest(phase=phase):
                crawler = self.crawler()
                crawler._request = Mock(return_value=DETAIL.format(origin=crawler.base_url))
                entered, release, finished = threading.Event(), threading.Event(), threading.Event()
                command = {**self.resolve(), 'deadline_at': future(0.2)}
                original = hsex.BeautifulSoup if phase == 'parser' else hsex.json.dumps

                def slow(*args, **kwargs):
                    # Serialization may also be used for locator validation.
                    is_response = phase == 'parser' or (isinstance(args[0], dict) and args[0].get('type') == 'item')
                    if is_response:
                        entered.set()
                        release.wait(2)
                    try:
                        return original(*args, **kwargs)
                    finally:
                        if is_response:
                            finished.set()

                target = patch.object(hsex, 'BeautifulSoup', side_effect=slow) if phase == 'parser' else patch.object(hsex.json, 'dumps', side_effect=slow)
                started = time.monotonic()
                with target:
                    with self.assertRaises(hsex.ProtocolError):
                        crawler.resolve(command)
                    self.assertLess(time.monotonic() - started, 0.25)
                    self.assertTrue(entered.is_set())
                    release.set()
                    self.assertTrue(finished.wait(1))
                self.assertIsNone(crawler._prepared_line)
                self.assertEqual((crawler.pages, crawler.rows, crawler.page_urls), ({}, {}, {}))

    def test_real_heavy_html_rejected_before_expensive_dom_build(self):
        padding = '<div></div>' * 100000  # 1.1 MiB, well below the 8 MiB body cap.
        for kind in ('discover', 'resolve'):
            with self.subTest(kind=kind):
                crawler = self.crawler()
                crawler._request = Mock(return_value=padding + (listing() if kind == 'discover' else DETAIL.format(origin=crawler.base_url)))
                command = self.discover(deadline_at=future(0.25)) if kind == 'discover' else {**self.resolve(), 'deadline_at': future(0.25)}
                started = time.monotonic()
                with self.assertRaises(hsex.ProtocolError) as raised:
                    getattr(crawler, kind)(command)
                self.assertLess(time.monotonic() - started, 0.25)
                self.assertEqual(raised.exception.fields['code'], 'parse_failed')
                self.assertEqual((crawler.pages, crawler.rows, crawler.page_urls), ({}, {}, {}))

    def test_slow_read_absolute_deadline_and_single_network_attempt(self):
        class Slow(FakeResponse):
            def iter_content(self, unused):
                time.sleep(0.3)
                yield b'ok'
        crawler = self.crawler()
        session = FakeSession([Slow()])
        started = time.monotonic()
        with patch.object(hsex.requests, 'Session', return_value=session), self.assertRaises(hsex.ProtocolError):
            crawler._request(crawler.base_url + '/list-1.htm', hsex.CommandDeadline(future(0.15), 'source'), 'source')
        self.assertLess(time.monotonic() - started, 0.25)
        self.assertEqual(len(session.calls), 1)

    def test_redirect_guard_and_body_cap(self):
        for location in ('https://evil.invalid/list-1.htm', 'https://user:pass@hsex.icu/list-1.htm', '/video-1.htm'):
            crawler = self.crawler()
            session = FakeSession([FakeResponse(302, headers={'Location': location})])
            with patch.object(hsex.requests, 'Session', return_value=session), self.assertRaises(hsex.ProtocolError):
                crawler._request(crawler.base_url + '/list-1.htm', hsex.CommandDeadline(future(), 'source'), 'source')
            self.assertEqual(len(session.calls), 1)
        session = FakeSession([FakeResponse(body=b'x' * 101)])
        crawler = self.crawler()
        with patch.object(hsex, 'MAX_BODY', 100), patch.object(hsex.requests, 'Session', return_value=session), self.assertRaises(hsex.ProtocolError):
            crawler._request(crawler.base_url + '/list-1.htm', hsex.CommandDeadline(future(), 'source'), 'source')

    def test_protocol_error_fields_duration_and_writer_bounds(self):
        self.assertEqual(hsex.ProtocolError('item', 'not_found', 'gone').fields,
                         {'scope': 'item', 'code': 'not_found', 'message': 'gone', 'retryable': False})
        self.assertEqual(hsex.parse_duration('00:06:14'), 374)
        self.assertEqual(hsex.parse_duration('00:00'), 0)
        for value in ('bad', '1:99', '999999:00'):
            self.assertIsNone(hsex.parse_duration(value))
        writer = hsex.ProtocolWriter()
        with patch.object(sys, 'stdout', io.StringIO()) as output:
            writer.write({'type': 'stopped', 'request_id': 'ok'})
            self.assertEqual(json.loads(output.getvalue())['request_id'], 'ok')
            with self.assertRaises(ValueError):
                writer.write({'x': 'a' * 1024 * 1024})
            writer.total = 64 * 1024 * 1024
            with self.assertRaises(ValueError):
                writer.write({'type': 'stopped'})

    def test_combined_large_headers_return_one_error_then_stop(self):
        # Each header is valid, but escaped JSON expands the combined item >1 MiB.
        headers = {'X-Large-%d' % index: '\x01' * 8192 for index in range(12)}
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / 'job.json'
            job.write_text(json.dumps(self.job(config={'media_headers': headers, 'thumbnail_headers': headers})))
            commands = json.dumps(self.resolve()) + '\n' + json.dumps({'type': 'stop', 'request_id': 'end'}) + '\n'
            with patch.object(hsex.CrawlerV3, '_request', return_value=DETAIL.format(origin='https://hsex.icu')), \
                    patch.object(sys, 'stdin', io.StringIO(commands)), \
                    patch.object(sys, 'stdout', io.StringIO()) as output, \
                    patch.object(sys, 'stderr', io.StringIO()):
                hsex.serve_job(str(job))
                rows = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual([row['type'] for row in rows], ['error', 'stopped'])
            self.assertEqual(rows[0]['request_id'], 'resolve')
            self.assertEqual(rows[0]['code'], 'parse_failed')

    def test_copied_file_loop_recovers_malformed_commands_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / 'crawler.py'
            shutil.copyfile(SCRIPT, copied)
            job = Path(directory) / 'job.json'
            job.write_text(json.dumps(self.job()))
            lines = ['{bad json', '[]', '{"type":"x","type":"y","request_id":"dup"}',
                     json.dumps({'type': 'unknown', 'request_id': 'exact-unknown'}),
                     json.dumps({'type': 'resolve', 'request_id': 'expired', 'deadline_at': future(-1), 'candidate': {}}),
                     json.dumps({'type': 'stop', 'request_id': 'exact-stop', 'reason': 'anything'})]
            result = subprocess.run([sys.executable, '-B', str(copied), '--job', str(job)],
                input='\n'.join(lines) + '\n', text=True, capture_output=True, cwd=directory, timeout=4)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual(len(output), len(lines))
            self.assertTrue(all(row['type'] == 'error' for row in output[:-1]))
            self.assertEqual(output[-1], {'type': 'stopped', 'request_id': 'exact-stop'})
            self.assertEqual(output[-3]['request_id'], 'exact-unknown')
            self.assertEqual(output[-2]['code'], 'source_unavailable')

    def test_oversize_command_recovers_and_invalid_job_has_no_stdout(self):
        with tempfile.TemporaryDirectory() as directory:
            job = Path(directory) / 'job.json'
            job.write_text(json.dumps(self.job()))
            data = '{"x":"' + ('a' * 1024 * 1024) + '"}\n' + json.dumps({'type': 'stop', 'request_id': 'end'}) + '\n'
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--job', str(job)],
                                    input=data, text=True, capture_output=True, timeout=4)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([json.loads(v)['type'] for v in result.stdout.splitlines()], ['error', 'stopped'])
            job.write_text(json.dumps({**self.job(), 'protocol': 'crawler.v2'}))
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), '--job', str(job)],
                                    input='', text=True, capture_output=True, timeout=4)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, '')

    def test_copied_file_discover_resolve_stop_loopback_no_media_requests(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append((self.path, self.headers))
                origin = 'http://127.0.0.1:%d' % self.server.server_port
                if self.path == '/list-1.htm':
                    body = listing(('101',), next_page=None)
                elif self.path == '/video-101.htm':
                    body = DETAIL.format(origin=origin)
                else:
                    self.send_error(500)
                    return
                data = body.encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *unused):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                copied = Path(directory) / 'Hsex.py'
                shutil.copyfile(SCRIPT, copied)
                job = Path(directory) / 'job.json'
                job.write_text(json.dumps(self.job(config={'base_url': 'http://127.0.0.1:%d' % server.server_port})))
                commands = [self.discover(), self.resolve(), {'type': 'stop', 'request_id': 'done'}]
                env = dict(os.environ)
                for key in list(env):
                    if key.lower() in {'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'}:
                        env.pop(key)
                result = subprocess.run([sys.executable, '-B', str(copied), '--job', str(job)],
                    input=''.join(json.dumps(v) + '\n' for v in commands), cwd=directory,
                    text=True, capture_output=True, env=env, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = [json.loads(v) for v in result.stdout.splitlines()]
                self.assertEqual([v['type'] for v in output], ['page', 'item', 'stopped'])
                self.assertEqual(output[1]['source_id'], 'stable-backend-id')
                self.assertEqual(output[1]['media']['url'], MEDIA_URL)
                self.assertEqual(output[-1], {'type': 'stopped', 'request_id': 'done'})
                self.assertEqual([v[0] for v in calls], ['/list-1.htm', '/video-101.htm'])
                self.assertTrue(all('Referer' not in headers and 'Origin' not in headers for _, headers in calls))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
