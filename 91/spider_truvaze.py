#!/usr/bin/env python3
"""
Truvaze 爬虫脚本 - crawler.v1 协议版本
"""

CRAWLER_NAME = "truvaze"

import argparse
import json
import os
import random
import re
import signal
import sys
import time
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, unquote, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== 配置 ====================
BASE_URL = "https://truvaze.com"
LIST_URL = f"{BASE_URL}/zh-CN{{}}?{{}}page={{}}"
DETAIL_URL = f"{BASE_URL}/zh-CN/movie/{{}}"
DELAY_BETWEEN_PAGES = (3, 6)
DELAY_BETWEEN_DETAILS = (2, 5)
RETRY_COUNT = 3
RETRY_DELAY = 5
MAX_EMPTY_PAGES = 2

# 时间范围映射
PERIOD_OPTIONS = {
    "daily": "",
    "weekly": "/weekly",
    "monthly": "/monthly",
    "all": "/all",
}

# 排序方式映射
SORT_OPTIONS = {
    "favorite": "sort=favorite&",
    "views": "sort=views&",
    "duration": "sort=duration&",
    "latest": "sort=latest&",
    "default": "",
}

# Chrome 125 浏览器标识
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


class TruvazeSpider:
    """Truvaze 视频爬虫 - crawler.v1"""

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

    def parse_list_page(self, page_num: int, period: str = "monthly",
                        sort: str = "favorite") -> List[Dict]:
        """解析列表页，提取视频卡片信息"""
        if self._interrupted:
            return []

        period_path = PERIOD_OPTIONS.get(period, "")
        sort_param = SORT_OPTIONS.get(sort, "")
        url = LIST_URL.format(period_path, sort_param, page_num)
        _log(f"[INFO] 正在抓取列表页 {page_num}: {url}")

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            if self._interrupted:
                return []
            _log(f"[ERROR] 请求列表页失败: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        videos = []

        video_links = soup.find_all("a", href=re.compile(r"/movie/"))
        if not video_links:
            video_links = soup.select('a[href*="/movie/"]')

        seen_ids = set()

        for link in video_links:
            try:
                href = link.get("href", "")
                if not href:
                    continue

                video_id_match = re.search(r"/movie/([^/?]+)", href)
                if not video_id_match:
                    continue
                video_id = video_id_match.group(1)

                if video_id in seen_ids:
                    continue
                seen_ids.add(video_id)

                source_id = sanitize_source_id(video_id)
                if source_id in self.seen_ids:
                    continue

                # 提取时长
                duration = link.get_text(strip=True)
                duration_match = re.search(r'[\d:]+', duration)
                duration = duration_match.group(0) if duration_match else ""

                # 提取缩略图
                img = link.find("img")
                thumb_url = ""
                if img:
                    thumb_url = img.get("data-src") or img.get("src") or ""
                    if thumb_url and not thumb_url.startswith("http"):
                        thumb_url = urljoin(BASE_URL, thumb_url)

                videos.append({
                    "source_id": source_id,
                    "title": "",  # 标题在详情页提取
                    "thumbnail": thumb_url,
                    "url": urljoin(BASE_URL, href),
                    "duration": duration,
                })

            except Exception as e:
                _log(f"[WARN] 解析视频卡片失败: {e}")
                continue

        _log(f"[INFO] 列表页 {page_num} 找到 {len(videos)} 个新视频")
        return videos

    def parse_video_url(self, html: str) -> Optional[str]:
        """从详情页 HTML 中解析真实 MP4 地址"""
        mp4_url = None

        # 策略1：查找指向 mp4 的链接
        soup = BeautifulSoup(html, "lxml")
        mp4_links = soup.find_all("a", href=re.compile(r"\.mp4"))
        for link in mp4_links:
            href = link.get("href", "")
            if href and "video.twimg.com" in href:
                mp4_url = href
                break

        # 策略2：查找 video 标签的 source
        if not mp4_url:
            video_tag = soup.find("video")
            if video_tag:
                source = video_tag.find("source")
                if source:
                    mp4_url = source.get("src", "")
                if not mp4_url:
                    mp4_url = video_tag.get("src", "")

        # 策略3：正则匹配所有 mp4 URL
        if not mp4_url:
            mp4_matches = re.findall(r'https?://[^"\']+\.mp4[^"\']*', html)
            for match in mp4_matches:
                if "video.twimg.com" in match:
                    mp4_url = match
                    break

        return mp4_url

    def parse_detail_page(self, video_info: Dict) -> Optional[str]:
        """解析详情页，返回 mp4_url 或 None"""
        if self._interrupted:
            return None

        url = video_info.get("url", "")
        if not url:
            return None

        _log(f"[INFO] 正在解析详情页: {video_info.get('source_id', url)}")

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            if self._interrupted:
                return None
            _log(f"[ERROR] 请求详情页失败: {e}")
            return None

        mp4_url = self.parse_video_url(resp.text)
        if not mp4_url:
            _log(f"[WARN] 无法提取 MP4 地址: {video_info.get('source_id', '')}")
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
                "Referer": "https://twitter.com/",
            },
        }
        if video_info.get("duration"):
            item["duration"] = video_info["duration"]
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

    def crawl(self, period: str = "monthly", sort: str = "favorite",
              max_page: Optional[int] = None):
        """主爬取循环"""
        _log("[INFO] 开始爬取...")
        _log(f"[INFO] 已知 source_id 数: {len(self.seen_ids)}")
        _log(f"[INFO] candidate_budget: {self.candidate_budget}")
        _log(f"[INFO] 时间范围: {period}, 排序方式: {sort}")

        page = 1
        empty_pages = 0

        while not self._interrupted and self.emitted < self.candidate_budget:
            if max_page and page > max_page:
                _log(f"[INFO] 已达到最大页数 {max_page}，停止爬取")
                break

            video_list = self.parse_list_page(page, period, sort)

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
    parser = argparse.ArgumentParser(description="Truvaze 视频爬虫 - crawler.v1")
    parser.add_argument("--job", type=str, required=True, help="job.json 文件路径")
    args = parser.parse_args()

    with open(args.job, "r", encoding="utf-8") as f:
        job = json.load(f)

    spider = TruvazeSpider(job)

    # 从 config 中读取筛选参数
    config = job.get("config", {})
    period = config.get("period", "monthly")
    sort = config.get("sort", "favorite")
    max_page = config.get("max_page")

    spider.crawl(
        period=period,
        sort=sort,
        max_page=max_page,
    )


if __name__ == "__main__":
    main()
