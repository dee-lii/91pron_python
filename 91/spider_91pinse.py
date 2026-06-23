#!/usr/bin/env python3
"""
91PinSe 爬虫脚本 - crawler.v1 协议版本
"""

CRAWLER_NAME = "91pinse"

import argparse
import base64
import json
import os
import random
import re
import signal
import sys
import time
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, unquote, urlparse, parse_qs, quote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== 配置 ====================
BASE_URL = "https://91pinse.com"
DETAIL_URL = f"{BASE_URL}/v/{{}}"
DELAY_BETWEEN_PAGES = (3, 6)
DELAY_BETWEEN_DETAILS = (2, 5)
RETRY_COUNT = 3
RETRY_DELAY = 5
MAX_EMPTY_PAGES = 2

# 排序方式映射
SORT_OPTIONS = {
    "latest": "last",
    "hot": "hot",
    "score": "score",
    "view": "view",
    "like": "like",
}

# 时间筛选选项
TIME_OPTIONS = {
    "all": "",
    "today": "today",
    "week": "week",
    "month": "month",
}

# 排行榜选项
RANK_OPTIONS = {
    "current-hot": "/rank/current-hot",
    "month-hot": "/rank/month-hot",
    "month-favorite": "/rank/month-favorite",
    "recently-featured": "/rank/recently-featured",
    "popular-now": "/rank/popular-now",
}

# Chrome 125 浏览器标识
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


def _log(msg: str):
    """日志输出到 stderr"""
    print(msg, file=sys.stderr, flush=True)


def sanitize_source_id(raw_id: str) -> str:
    """清理 source_id，只保留字母、数字、下划线、连字符、点，最长 160 字符"""
    sanitized = re.sub(r"[^a-zA-Z0-9_\-.]", "_", raw_id)
    return sanitized[:160]


def decode_base64(encoded_str: str) -> str:
    """解码 Base64 字符串"""
    try:
        encoded_str = encoded_str.replace('-', '+').replace('_', '/')
        padding = 4 - len(encoded_str) % 4
        if padding != 4:
            encoded_str += '=' * padding
        return base64.b64decode(encoded_str).decode('utf-8')
    except Exception:
        return ""


class PinSe91Spider:
    """91PinSe 视频爬虫 - crawler.v1"""

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

    def build_list_url(self, page_num: int, category: Optional[str] = None,
                       rank: Optional[str] = None, sort: str = "latest",
                       time_filter: str = "all") -> str:
        """构建列表页 URL"""
        if category:
            url = f"{BASE_URL}/v/search?keyword={quote(category)}&page={page_num}"
        elif rank:
            rank_path = RANK_OPTIONS.get(rank, "")
            url = f"{BASE_URL}{rank_path}?page={page_num}"
        elif sort == "hot":
            url = f"{BASE_URL}/v/hot/?page={page_num}"
        else:
            sort_value = SORT_OPTIONS.get(sort, "last")
            time_value = TIME_OPTIONS.get(time_filter, "")
            params = f"page={page_num}"
            if sort_value and sort_value != "hot":
                params = f"sort={sort_value}&{params}"
            if time_value:
                params = f"time={time_value}&{params}"
            url = f"{BASE_URL}/v/?{params}"
        return url

    def parse_list_page(self, page_num: int, category: Optional[str] = None,
                        rank: Optional[str] = None, sort: str = "latest",
                        time_filter: str = "all") -> List[Dict]:
        """解析列表页，提取视频卡片信息"""
        if self._interrupted:
            return []

        url = self.build_list_url(page_num, category, rank, sort, time_filter)
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

        video_links = soup.find_all("a", href=re.compile(r"^/v/\d+$"))
        if not video_links:
            video_links = soup.select('a[href*="/v/"]')

        seen_ids = set()
        video_groups = {}
        for link in video_links:
            try:
                href = link.get("href", "")
                if not href:
                    continue
                video_id_match = re.search(r"/v/(\d+)", href)
                if not video_id_match:
                    continue
                video_id = video_id_match.group(1)
                if "/author/" in href:
                    continue
                if video_id not in video_groups:
                    video_groups[video_id] = []
                video_groups[video_id].append(link)
            except Exception:
                continue

        for video_id, links in video_groups.items():
            try:
                if video_id in seen_ids:
                    continue
                seen_ids.add(video_id)

                source_id = sanitize_source_id(video_id)
                if source_id in self.seen_ids:
                    continue

                title = ""
                duration = ""
                thumb_url = ""

                for link in links:
                    text = link.get_text(strip=True)
                    link_title = link.get("title", "")

                    if re.match(r'^\d+:\d+:\d+', text):
                        duration_match = re.search(r'(\d+:\d+:\d+)', text)
                        if duration_match:
                            duration = duration_match.group(1)
                        img = link.find("img")
                        if img:
                            thumb_url = img.get("data-src") or img.get("src") or ""
                            if thumb_url and not thumb_url.startswith("http"):
                                thumb_url = urljoin(BASE_URL, thumb_url)
                        continue

                    if link_title and len(link_title) > len(title):
                        title = link_title
                    if not title and text and not re.match(r'^\d+$', text) and not re.match(r'^\d+:\d+', text):
                        title = text

                if not title:
                    title = f"视频 {video_id}"

                videos.append({
                    "source_id": source_id,
                    "title": title,
                    "thumbnail": thumb_url,
                    "url": urljoin(BASE_URL, f"/v/{video_id}"),
                    "duration": duration,
                })

            except Exception as e:
                _log(f"[WARN] 解析视频卡片失败: {e}")
                continue

        _log(f"[INFO] 列表页 {page_num} 找到 {len(videos)} 个新视频")
        return videos

    def parse_video_url(self, html: str) -> Optional[str]:
        """从详情页 HTML 中解析真实视频地址（Base64 编码）"""
        video_url = None
        soup = BeautifulSoup(html, "lxml")
        scripts = soup.find_all("script")
        for script in scripts:
            text = script.get_text()
            base64_pattern = r"var\s+_\w+\s*=\s*'([A-Za-z0-9+/=\\]+)'\s*,\s*_\w+\s*=\s*'([A-Za-z0-9+/=\\]+)'"
            match = re.search(base64_pattern, text)
            if match and 'atob' in text:
                encoded_url1 = match.group(1).replace('\\u003D', '=')
                encoded_url2 = match.group(2).replace('\\u003D', '=')
                url1 = decode_base64(encoded_url1)
                url2 = decode_base64(encoded_url2)
                if url1 and url1.startswith('http'):
                    video_url = url1
                elif url2 and url2.startswith('http'):
                    video_url = url2
                break
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

    def crawl(self, category: Optional[str] = None, rank: Optional[str] = None,
              sort: str = "latest", time_filter: str = "all", max_page: Optional[int] = None):
        """主爬取循环"""
        _log("[INFO] 开始爬取...")
        _log(f"[INFO] 已知 source_id 数: {len(self.seen_ids)}")
        _log(f"[INFO] candidate_budget: {self.candidate_budget}")
        if category:
            _log(f"[INFO] 分类/关键词: {category}")
        elif rank:
            _log(f"[INFO] 排行榜: {rank}")
        else:
            _log(f"[INFO] 排序方式: {sort}, 时间: {time_filter}")

        page = 1
        empty_pages = 0

        while not self._interrupted and self.emitted < self.candidate_budget:
            if max_page and page > max_page:
                _log(f"[INFO] 已达到最大页数 {max_page}，停止爬取")
                break

            video_list = self.parse_list_page(page, category, rank, sort, time_filter)

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

                media_url = self.parse_detail_page(video_info)
                if not media_url:
                    continue

                self.emit_item(video_info, media_url)
                self.emit_progress(f"Scanning page {page}")

                self._delay(DELAY_BETWEEN_DETAILS)

            page += 1
            self._delay(DELAY_BETWEEN_PAGES)

        self.emit_done()
        _log(f"[INFO] 爬取完成: checked={self.checked}, emitted={self.emitted}")


def main():
    parser = argparse.ArgumentParser(description="91PinSe 视频爬虫 - crawler.v1")
    parser.add_argument("--job", type=str, required=True, help="job.json 文件路径")
    args = parser.parse_args()

    with open(args.job, "r", encoding="utf-8") as f:
        job = json.load(f)

    spider = PinSe91Spider(job)

    # 从 config 中读取筛选参数
    config = job.get("config", {})
    category = config.get("category")
    rank = config.get("rank")
    sort = config.get("sort", "latest")
    time_filter = config.get("time", "all")
    max_page = config.get("max_page")

    spider.crawl(
        category=category,
        rank=rank,
        sort=sort,
        time_filter=time_filter,
        max_page=max_page,
    )


if __name__ == "__main__":
    main()
