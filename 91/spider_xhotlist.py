#!/usr/bin/env python3
"""
XHotList 爬虫脚本 - crawler.v1 协议版本
"""

CRAWLER_NAME = "xhotlist"

import argparse
import json
import os
import random
import re
import signal
import sys
import time
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== 配置 ====================
BASE_URL = "https://top.xhotlist.com"
DELAY_BETWEEN_PAGES = (2, 4)
DELAY_BETWEEN_DETAILS = (1, 3)
RETRY_COUNT = 3
RETRY_DELAY = 5
MAX_EMPTY_PAGES = 3

# 热门周期选项
PERIOD_OPTIONS = {
    "all": "",
    "day": "/period/day",
    "week": "/period/week",
    "month": "/period/month",
    "total": "/period/total",
}

# 排序方式选项
SORT_OPTIONS = {
    "default": "",
    "new": "/sort/new",
    "duration": "/sort/duration",
    "old": "/sort/old",
}

# 时长筛选选项
DURATION_OPTIONS = {
    "all": "",
    "short": "/duration/short",
    "medium": "/duration/medium",
    "long": "/duration/long",
}

# Chrome 125 浏览器标识
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": BASE_URL,
}


def _log(msg: str):
    """日志输出到 stderr"""
    print(msg, file=sys.stderr, flush=True)


def sanitize_source_id(raw_id: str) -> str:
    """清理 source_id，只保留字母、数字、下划线、连字符、点，最长 160 字符"""
    sanitized = re.sub(r"[^a-zA-Z0-9_\-.]", "_", raw_id)
    return sanitized[:160]


class XHotListSpider:
    """XHotList 视频爬虫 - crawler.v1"""

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

    def build_list_url(self, page_num: int, period: str = "all",
                       sort: str = "default", duration: str = "all",
                       tag: Optional[str] = None) -> str:
        """构建列表页 URL"""
        if tag:
            base_path = f"/videos/tag/{tag}"
        else:
            period_path = PERIOD_OPTIONS.get(period, "")
            sort_path = SORT_OPTIONS.get(sort, "")
            duration_path = DURATION_OPTIONS.get(duration, "")

            if sort_path and sort != "default":
                base_path = f"/videos{sort_path}"
            elif period_path:
                base_path = f"/videos{period_path}"
            elif duration_path:
                base_path = f"/videos{duration_path}"
            else:
                base_path = "/videos"

        if page_num > 1:
            return f"{BASE_URL}{base_path}/page/{page_num}"
        else:
            return f"{BASE_URL}{base_path}"

    def parse_list_page(self, page_num: int, period: str = "all",
                        sort: str = "default", duration: str = "all",
                        tag: Optional[str] = None) -> List[Dict]:
        """解析列表页，提取视频卡片信息"""
        if self._interrupted:
            return []

        url = self.build_list_url(page_num, period, sort, duration, tag)
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

        video_cards = soup.find_all("a", class_="video-card")

        for card in video_cards:
            try:
                href = card.get("href", "")
                if not href:
                    continue

                video_id_match = re.search(r"/video/([^/]+)", href)
                if not video_id_match:
                    continue
                video_id = video_id_match.group(1)

                source_id = sanitize_source_id(video_id)
                if source_id in self.seen_ids:
                    continue

                title_elem = card.find("span", class_="card-title")
                title = title_elem.get_text(strip=True) if title_elem else ""

                duration_elem = card.find("span", class_="duration")
                card_duration = duration_elem.get_text(strip=True) if duration_elem else ""

                thumb_elem = card.find("img")
                thumb_url = ""
                if thumb_elem:
                    thumb_url = thumb_elem.get("src", "") or thumb_elem.get("data-src", "")

                videos.append({
                    "source_id": source_id,
                    "title": title,
                    "thumbnail": thumb_url,
                    "url": urljoin(BASE_URL, href),
                    "duration": card_duration,
                })

            except Exception as e:
                _log(f"[WARN] 解析视频卡片失败: {e}")
                continue

        _log(f"[INFO] 列表页 {page_num} 找到 {len(videos)} 个新视频")
        return videos

    def parse_video_url(self, html: str) -> Optional[str]:
        """从详情页 HTML 中解析真实视频地址"""
        soup = BeautifulSoup(html, "lxml")
        video_url = None

        # 策略1：从 <source> 标签提取
        source_elem = soup.find("source", type="video/mp4")
        if source_elem:
            video_url = source_elem.get("src", "")

        # 策略2：从 download-action 链接提取
        if not video_url:
            download_link = soup.find("a", class_="download-action")
            if download_link:
                video_url = download_link.get("href", "")

        # 策略3：从 <video> 标签的 src 属性提取
        if not video_url:
            video_elem = soup.find("video")
            if video_elem:
                video_url = video_elem.get("src", "")

        # 确保 URL 是完整的
        if video_url and not video_url.startswith("http"):
            video_url = urljoin(BASE_URL, video_url)

        return video_url

    def parse_detail_page(self, video_info: Dict) -> Optional[str]:
        """解析详情页，返回视频 URL 或 None"""
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

        video_url = self.parse_video_url(resp.text)
        if not video_url:
            _log(f"[WARN] 无法提取视频地址: {video_info.get('title', '')}")
            return None

        return video_url

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

    def crawl(self, period: str = "all", sort: str = "default",
              duration: str = "all", tag: Optional[str] = None,
              max_page: Optional[int] = None):
        """主爬取循环"""
        _log("[INFO] 开始爬取...")
        _log(f"[INFO] 已知 source_id 数: {len(self.seen_ids)}")
        _log(f"[INFO] candidate_budget: {self.candidate_budget}")
        if tag:
            _log(f"[INFO] 标签筛选: {tag}")
        else:
            conditions = []
            if period != "all":
                conditions.append(f"周期: {period}")
            if sort != "default":
                conditions.append(f"排序: {sort}")
            if duration != "all":
                conditions.append(f"时长: {duration}")
            if conditions:
                _log(f"[INFO] 筛选条件: {', '.join(conditions)}")

        page = 1
        empty_pages = 0

        while not self._interrupted and self.emitted < self.candidate_budget:
            if max_page and page > max_page:
                _log(f"[INFO] 已达到最大页数 {max_page}，停止爬取")
                break

            video_list = self.parse_list_page(page, period, sort, duration, tag)

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

                video_url = self.parse_detail_page(video_info)
                if not video_url:
                    continue

                self.emit_item(video_info, video_url)
                self.emit_progress(f"Scanning page {page}")

                self._delay(DELAY_BETWEEN_DETAILS)

            page += 1
            self._delay(DELAY_BETWEEN_PAGES)

        self.emit_done()
        _log(f"[INFO] 爬取完成: checked={self.checked}, emitted={self.emitted}")


def main():
    parser = argparse.ArgumentParser(description="XHotList 视频爬虫 - crawler.v1")
    parser.add_argument("--job", type=str, required=True, help="job.json 文件路径")
    args = parser.parse_args()

    with open(args.job, "r", encoding="utf-8") as f:
        job = json.load(f)

    spider = XHotListSpider(job)

    # 从 config 中读取筛选参数
    config = job.get("config", {})
    period = config.get("period", "all")
    sort = config.get("sort", "default")
    duration = config.get("duration", "all")
    tag = config.get("tag")
    max_page = config.get("max_page")

    spider.crawl(
        period=period,
        sort=sort,
        duration=duration,
        tag=tag,
        max_page=max_page,
    )


if __name__ == "__main__":
    main()
