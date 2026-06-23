#!/usr/bin/env python3
"""
91Porn 爬虫脚本 - crawler.v1 协议版本
"""

CRAWLER_NAME = "91porn"

import argparse
import json
import os
import random
import re
import signal
import sys
import time
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== 配置 ====================
BASE_URL = "https://91porn.com"
LIST_URL = f"{BASE_URL}/v.php?category=hot&viewtype=basic&page={{}}"
DETAIL_URL = f"{BASE_URL}/view_video.php?viewkey={{}}"
DELAY_BETWEEN_PAGES = (3, 6)
DELAY_BETWEEN_DETAILS = (2, 5)
RETRY_COUNT = 3
RETRY_DELAY = 5
MAX_EMPTY_PAGES = 2

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _log(msg: str):
    """日志输出到 stderr"""
    print(msg, file=sys.stderr, flush=True)


def sanitize_source_id(raw_id: str) -> str:
    """清理 source_id，只保留字母、数字、下划线、连字符、点，最长 160 字符"""
    sanitized = re.sub(r"[^a-zA-Z0-9_\-.]", "_", raw_id)
    return sanitized[:160]


class Porn91Spider:
    """91Porn 视频爬虫 - crawler.v1"""

    def __init__(self, job: dict):
        self.job = job

        # 解析 candidate_budget
        self.candidate_budget = (
            job.get("candidate_budget")
            or job.get("target_new")
            or 10
        )
        if isinstance(self.candidate_budget, str):
            try:
                self.candidate_budget = int(self.candidate_budget)
            except (ValueError, TypeError):
                self.candidate_budget = 10
        if not isinstance(self.candidate_budget, int) or self.candidate_budget <= 0:
            self.candidate_budget = 10

        # 代理
        proxy_url = job.get("network", {}).get("proxy_url")

        # 初始化 session
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        retry_strategy = Retry(
            total=RETRY_COUNT,
            backoff_factor=RETRY_DELAY,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.trust_env = True

        if proxy_url:
            self.session.proxies = {"http": proxy_url, "https": proxy_url}

        # 加载已知 source_id
        self.seen_ids: Set[str] = set()
        seen_file = job.get("seen_source_ids_file")
        if seen_file and os.path.exists(seen_file):
            with open(seen_file, "r") as f:
                self.seen_ids = set(line.strip() for line in f if line.strip())
            _log(f"[INFO] 从 {seen_file} 加载了 {len(self.seen_ids)} 个已知 source_id")

        # 计数器
        self.checked = 0
        self.emitted = 0

        # 中断标志
        self._interrupted = False
        try:
            signal.signal(signal.SIGINT, self._handle_interrupt)
        except ValueError:
            pass

    def _handle_interrupt(self, signum, frame):
        self._interrupted = True
        _log("\n[INFO] 收到中断信号")

    def _delay(self, range_tuple: tuple):
        delay = random.uniform(*range_tuple)
        end_time = time.time() + delay
        while time.time() < end_time:
            if self._interrupted:
                return
            time.sleep(0.5)

    def _check_cloudflare(self, html: str) -> bool:
        if "Just a moment" in html or "Checking your browser" in html:
            _log("[WARN] 检测到 Cloudflare 拦截，请稍后重试或使用代理")
            return True
        return False

    def _warm_cookies(self):
        if self._interrupted:
            return
        try:
            resp = self.session.get(LIST_URL.format(1), timeout=15)
            resp.raise_for_status()
            if "mode" not in self.session.cookies:
                self.session.cookies.set("mode", "d", domain="91porn.com")
        except Exception as e:
            if self._interrupted:
                return
            _log(f"[WARN] Cookie 预热失败: {e}")
            self.session.cookies.set("mode", "d", domain="91porn.com")

    def parse_video_url(self, html: str) -> Optional[str]:
        """从详情页 HTML 中解析真实 MP4 地址"""
        mp4_url = None

        # 策略1：解析 strencode2 函数
        strencode_match = re.search(r"strencode2\(['\"](.+?)['\"]\)", html)
        if strencode_match:
            encoded_str = strencode_match.group(1)
            try:
                decoded_html = unquote(encoded_str)
                src_match = re.search(r"src=['\"]([^'\"]+)['\"]", decoded_html)
                if src_match:
                    mp4_url = src_match.group(1)
                else:
                    video_soup = BeautifulSoup(decoded_html, "lxml")
                    source = video_soup.find("source")
                    if source:
                        mp4_url = source.get("src", "")
                    if not mp4_url:
                        video_tag = video_soup.find("video")
                        if video_tag:
                            source = video_tag.find("source")
                            if source:
                                mp4_url = source.get("src", "")
                            if not mp4_url:
                                mp4_url = video_tag.get("src", "")
            except Exception as e:
                _log(f"[WARN] strencode2 解析失败: {e}")

        # 策略2：正则匹配 .mp4 URL
        if not mp4_url:
            mp4_matches = re.findall(r'https?://[^"\']+\.mp4[^"\']*', html)
            for match in mp4_matches:
                if "kwai" not in match and "ad-" not in match:
                    mp4_url = match
                    break

        return mp4_url

    def resolve_fresh_video_url(self, viewkey: str, source_id: Optional[str] = None) -> Optional[str]:
        """重新获取视频 URL（带 Cookie 预热和 source_id 验证）"""
        if self._interrupted:
            return None
        detail_url = DETAIL_URL.format(viewkey)
        try:
            self._warm_cookies()
            resp = self.session.get(detail_url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            if self._interrupted:
                return None
            _log(f"[WARN] 刷新 URL 失败: {e}")
            return None
        if self._check_cloudflare(resp.text):
            return None
        mp4_url = self.parse_video_url(resp.text)
        if not mp4_url:
            return None
        if source_id:
            source_id_match = re.search(r"(\d+)", resp.text[:5000])
            if source_id_match:
                page_id = source_id_match.group(1)
                if page_id != source_id:
                    _log("[WARN] source_id 不一致，刷新失败")
                    return None
        return mp4_url

    def parse_list_page(self, page_num: int) -> List[Dict]:
        """解析列表页，提取视频卡片信息"""
        if self._interrupted:
            return []

        url = LIST_URL.format(page_num)
        _log(f"[INFO] 正在抓取列表页 {page_num}: {url}")

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            if self._interrupted:
                return []
            _log(f"[ERROR] 请求列表页失败: {e}")
            return []

        if self._check_cloudflare(resp.text):
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        videos = []

        video_cards = soup.select("div.video-elem, div.col-md-3, div.thumb-block")
        if not video_cards:
            video_cards = soup.find_all("div", class_=re.compile(r"video|thumb|item"))

        seen_ids = set()

        for card in video_cards:
            try:
                link = card.find("a", href=re.compile(r"viewkey="))
                if not link:
                    continue
                href = link.get("href", "")
                viewkey_match = re.search(r"viewkey=([^&]+)", href)
                if not viewkey_match:
                    continue
                viewkey = viewkey_match.group(1)

                source_id = sanitize_source_id(viewkey)

                dedup_key = viewkey if viewkey else source_id
                if dedup_key in seen_ids:
                    continue
                seen_ids.add(dedup_key)

                if source_id in self.seen_ids:
                    continue

                title_elem = card.select_one("span.video-title, .title, h5, h4")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    title = link.get("title", "") or link.get_text(strip=True)

                img = card.find("img")
                thumb_url = ""
                if img:
                    thumb_url = img.get("data-src") or img.get("src") or ""
                    if thumb_url and not thumb_url.startswith("http"):
                        thumb_url = urljoin(BASE_URL, thumb_url)

                videos.append({
                    "source_id": source_id,
                    "title": title,
                    "thumbnail": thumb_url,
                    "url": urljoin(BASE_URL, href),
                })
            except Exception as e:
                _log(f"[WARN] 解析视频卡片失败: {e}")
                continue

        _log(f"[INFO] 列表页 {page_num} 找到 {len(videos)} 个新视频")
        return videos

    def parse_detail_page(self, video_info: Dict) -> Optional[str]:
        """解析详情页，返回 mp4_url 或 None"""
        if self._interrupted:
            return None

        url = video_info.get("url", "")
        if not url:
            return None

        _log(f"[INFO] 正在解析详情页: {video_info.get('title', url)}")

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            if self._interrupted:
                return None
            _log(f"[ERROR] 请求详情页失败: {e}")
            return None

        if self._check_cloudflare(resp.text):
            return None

        mp4_url = self.parse_video_url(resp.text)
        if not mp4_url:
            _log(f"[WARN] 无法提取 MP4 地址: {video_info.get('title', '')}")
            return None

        # 验证 source_id 一致性
        source_id_match = re.search(r"(\d+)", resp.text[:5000])
        if source_id_match and video_info.get("source_id"):
            page_id = source_id_match.group(1)
            if page_id != video_info["source_id"]:
                _log(f"[WARN] source_id 不一致，丢弃: {video_info.get('title', '')}")
                return None

        return mp4_url

    def emit_item(self, video_info: Dict, media_url: str):
        """输出单个 item 到 stdout"""
        item = {
            "type": "item",
            "source_id": video_info["source_id"],
            "title": video_info.get("title", ""),
            "media_url": media_url,
            "thumbnail_url": video_info.get("thumbnail", ""),
            "detail_url": video_info.get("url", ""),
            "headers": {
                "Referer": f"{BASE_URL}/",
            },
        }
        print(json.dumps(item, ensure_ascii=False), flush=True)
        self.emitted += 1

    def emit_progress(self, message: str = ""):
        """输出 progress 事件"""
        event = {
            "type": "progress",
            "checked": self.checked,
            "emitted": self.emitted,
        }
        if message:
            event["message"] = message
        print(json.dumps(event, ensure_ascii=False), flush=True)

    def emit_done(self):
        """输出 done 事件"""
        done = {
            "type": "done",
            "stats": {
                "checked": self.checked,
                "emitted": self.emitted,
            },
        }
        print(json.dumps(done, ensure_ascii=False), flush=True)

    def crawl(self):
        """主爬取循环"""
        _log("[INFO] 开始爬取...")
        _log(f"[INFO] 已知 source_id 数: {len(self.seen_ids)}")
        _log(f"[INFO] candidate_budget: {self.candidate_budget}")

        self._warm_cookies()

        page = 1
        empty_pages = 0

        while not self._interrupted and self.emitted < self.candidate_budget:
            video_list = self.parse_list_page(page)

            if not video_list:
                empty_pages += 1
                if empty_pages >= MAX_EMPTY_PAGES:
                    _log(f"[INFO] 连续 {MAX_EMPTY_PAGES} 页为空，停止爬取")
                    break
                page += 1
                self._delay(DELAY_BETWEEN_PAGES)
                continue
            else:
                empty_pages = 0

            for video_info in video_list:
                if self._interrupted or self.emitted >= self.candidate_budget:
                    break

                self.checked += 1

                mp4_url = self.parse_detail_page(video_info)
                if not mp4_url:
                    continue

                self.emit_item(video_info, mp4_url)
                self.emit_progress(f"Scanning page {page}")

                self._delay(DELAY_BETWEEN_DETAILS)

            page += 1
            self._delay(DELAY_BETWEEN_PAGES)

        self.emit_done()
        _log(f"[INFO] 爬取完成: checked={self.checked}, emitted={self.emitted}")


def main():
    parser = argparse.ArgumentParser(description="91Porn 视频爬虫 - crawler.v1")
    parser.add_argument("--job", type=str, required=True, help="job.json 文件路径")
    args = parser.parse_args()

    with open(args.job, "r", encoding="utf-8") as f:
        job = json.load(f)

    spider = Porn91Spider(job)
    spider.crawl()


if __name__ == "__main__":
    main()
