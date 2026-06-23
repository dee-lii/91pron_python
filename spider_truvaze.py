#!/usr/bin/env python3
"""
Truvaze 爬虫脚本 - 独立运行版本（支持下载）
爬取 https://truvaze.com/zh-CN 网站的视频

使用方法:
    # 安装依赖
    pip install requests beautifulsoup4 lxml

    # 全量爬取并下载视频
    python3 spider_truvaze.py --download

    # 抓取并下载指定数量的新视频
    python3 spider_truvaze.py --target-new 10 --download

    # 指定下载目录
    python3 spider_truvaze.py --download --download-dir ./videos

    # 仅抓取元数据（不下载）
    python3 spider_truvaze.py

    # 使用代理
    ALL_PROXY=socks5://127.0.0.1:1080 python3 spider_truvaze.py --download

    # 指定排序方式
    python3 spider_truvaze.py --sort views --download
"""

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
DELAY_BETWEEN_PAGES = (3, 6)  # 列表页之间的延迟范围（秒）
DELAY_BETWEEN_DETAILS = (2, 5)  # 详情页之间的延迟范围（秒）
RETRY_COUNT = 3
RETRY_DELAY = 5
MAX_EMPTY_PAGES = 2  # 连续空页面数达到此值时停止
OUTPUT_FILE = "truvaze_videos.json"
DEFAULT_DOWNLOAD_DIR = "./truvaze_videos"
DOWNLOAD_TIMEOUT = 120  # 下载超时时间（秒）
CHUNK_SIZE = 8192  # 下载块大小

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


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    清理文件名，移除非法字符

    Args:
        filename: 原始文件名
        max_length: 最大文件名长度

    Returns:
        清理后的文件名
    """
    # 移除或替换非法字符
    illegal_chars = r'[<>:"/\\|?*\x00-\x1f]'
    filename = re.sub(illegal_chars, '_', filename)

    # 移除首尾空格和点
    filename = filename.strip(' .')

    # 如果文件名为空，使用默认名称
    if not filename:
        filename = "untitled"

    # 截断过长的文件名
    if len(filename) > max_length:
        filename = filename[:max_length]

    return filename


def should_refresh_url(error: Exception, status_code: Optional[int] = None) -> bool:
    """
    判断是否需要刷新视频 URL

    Args:
        error: 异常对象
        status_code: HTTP 状态码

    Returns:
        是否需要刷新 URL
    """
    error_str = str(error).lower()

    # 需要刷新的错误类型
    refresh_errors = [
        "deadlineexceeded",
        "timeout",
        "unexpected eof",
        "connection reset",
        "connection refused",
        "network is unreachable",
    ]

    # 检查错误信息
    for err_type in refresh_errors:
        if err_type in error_str:
            return True

    # 检查 HTTP 状态码
    if status_code:
        # 需要刷新的状态码
        refresh_codes = {403, 404, 410, 429, 500, 502, 503, 504}
        if status_code in refresh_codes:
            return True

    return False


class TruvazeSpider:
    """Truvaze 视频爬虫"""

    def __init__(
        self,
        output_file: str = OUTPUT_FILE,
        stream_output: bool = False,
        resume: bool = True,
        seen_ids_file: Optional[str] = None,
        download: bool = False,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
        sort: str = "favorite",
        period: str = "monthly",
    ):
        self.output_file = output_file
        self.stream_output = stream_output
        self.resume = resume
        self.seen_ids_file = seen_ids_file
        self.download = download
        self.download_dir = download_dir
        self.sort = sort
        self.period = period

        # 初始化 session
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

        # 重试策略
        retry_strategy = Retry(
            total=RETRY_COUNT,
            backoff_factor=RETRY_DELAY,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # 优先使用 IPv4（针对 SOCKS5 代理）
        self.session.trust_env = True

        # 已抓取的视频 ID 集合
        self.seen_ids: Set[str] = set()
        self._load_seen_ids()

        # 已下载的视频文件（用于断点续传）
        self.downloaded_files: Set[str] = set()
        if self.download:
            self._load_downloaded_files()

        # 抓取结果
        self.videos: List[Dict] = []

        # 下载统计
        self.download_count = 0
        self.download_failed = 0

        # 中断标志（线程安全）
        self._interrupted = False
        try:
            signal.signal(signal.SIGINT, self._handle_interrupt)
        except ValueError:
            pass

    def _load_seen_ids(self):
        """加载已抓取的视频 ID 集合"""
        if not self.resume:
            return

        # 从指定文件加载
        if self.seen_ids_file and os.path.exists(self.seen_ids_file):
            with open(self.seen_ids_file, "r") as f:
                self.seen_ids = set(line.strip() for line in f if line.strip())
            print(f"[INFO] 从 {self.seen_ids_file} 加载了 {len(self.seen_ids)} 个已知视频 ID")
            return

        # 从输出文件加载
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.seen_ids = {v.get("video_id") for v in data if v.get("video_id")}
                        self.videos = data
                        print(f"[INFO] 从 {self.output_file} 加载了 {len(self.seen_ids)} 个已知视频 ID")
            except (json.JSONDecodeError, Exception) as e:
                print(f"[WARN] 加载已有数据失败: {e}")

    def _load_downloaded_files(self):
        """加载已下载的视频文件列表"""
        if not os.path.exists(self.download_dir):
            return

        for filename in os.listdir(self.download_dir):
            if filename.endswith('.mp4'):
                self.downloaded_files.add(filename)

        print(f"[INFO] 下载目录已有 {len(self.downloaded_files)} 个视频文件")

    def _handle_interrupt(self, signum, frame):
        """处理 Ctrl+C 中断"""
        self._interrupted = True
        print("\n[INFO] 收到中断信号，正在保存已有数据...")

    def _delay(self, range_tuple: tuple):
        """随机延迟（支持中断）"""
        delay = random.uniform(*range_tuple)
        # 分段 sleep，每 0.5 秒检查一次中断标志
        end_time = time.time() + delay
        while time.time() < end_time:
            if self._interrupted:
                return
            time.sleep(0.5)

    def parse_list_page(self, page_num: int) -> List[Dict]:
        """解析列表页，提取视频卡片信息"""
        if self._interrupted:
            return []

        # 构建时间范围和排序参数
        period_path = PERIOD_OPTIONS.get(self.period, "")
        sort_param = SORT_OPTIONS.get(self.sort, "")
        url = LIST_URL.format(period_path, sort_param, page_num)
        print(f"[INFO] 正在抓取列表页 {page_num}: {url}")

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            if self._interrupted:
                return []
            print(f"[ERROR] 请求列表页失败: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        videos = []

        # 查找视频卡片 - 根据 truvaze.com 的实际结构
        # 视频条目通常是包含链接和缩略图的块
        # 查找所有视频链接
        video_links = soup.find_all("a", href=re.compile(r"/movie/"))
        if not video_links:
            # 备用选择器
            video_links = soup.select('a[href*="/movie/"]')

        seen_ids = set()  # 页面内去重

        for link in video_links:
            try:
                href = link.get("href", "")
                if not href:
                    continue

                # 提取视频 ID
                video_id_match = re.search(r"/movie/([^/?]+)", href)
                if not video_id_match:
                    continue
                video_id = video_id_match.group(1)

                # 页面内去重
                if video_id in seen_ids:
                    continue
                seen_ids.add(video_id)

                # 已抓取过的跳过
                if video_id in self.seen_ids:
                    continue

                # 提取时长（在链接文本中）
                duration = link.get_text(strip=True)
                # 清理时长文本（移除排名图标等非数字字符）
                duration_match = re.search(r'[\d:]+', duration)
                duration = duration_match.group(0) if duration_match else ""

                # 提取缩略图
                img = link.find("img")
                thumb_url = ""
                if img:
                    thumb_url = img.get("data-src") or img.get("src") or ""
                    if thumb_url and not thumb_url.startswith("http"):
                        thumb_url = urljoin(BASE_URL, thumb_url)

                # 提取统计信息（在链接外部，通过图标识别）
                metadata = {}
                # 获取链接的父容器的 HTML
                parent = link.parent
                if parent:
                    parent_html = str(parent)
                    # 使用正则直接从 HTML 中提取图标后面的数字
                    # 观看数（直接跟在 img 标签后面）
                    views_match = re.search(r'eye-black\.svg[^>]*/?>\s*(\d[\d,]*)', parent_html)
                    if views_match:
                        metadata["views"] = int(views_match.group(1).replace(",", ""))
                    # 评论数（直接跟在 img 标签后面）
                    comments_match = re.search(r'comment-black\.svg[^>]*/?>\s*(\d[\d,]*)', parent_html)
                    if comments_match:
                        metadata["comments"] = int(comments_match.group(1).replace(",", ""))
                    # 收藏数（在 span 标签中）
                    likes_match = re.search(r'heart-black\.svg[^>]*/?>\s*<span[^>]*>(\d[\d,]*)</span>', parent_html)
                    if likes_match:
                        metadata["likes"] = int(likes_match.group(1).replace(",", ""))

                videos.append({
                    "video_id": video_id,
                    "duration": duration,
                    "thumbnail": thumb_url,
                    "url": urljoin(BASE_URL, href),
                    "metadata": metadata,
                })

            except Exception as e:
                print(f"[WARN] 解析视频卡片失败: {e}")
                continue

        print(f"[INFO] 列表页 {page_num} 找到 {len(videos)} 个新视频")
        return videos

    def parse_detail_page(self, video_info: Dict) -> Optional[Dict]:
        """解析详情页，提取真实 MP4 地址"""
        if self._interrupted:
            return None

        url = video_info.get("url", "")
        if not url:
            return None

        print(f"[INFO] 正在解析详情页: {video_info.get('title', url)}")

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            if self._interrupted:
                return None
            print(f"[ERROR] 请求详情页失败: {e}")
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        # 解析视频 URL - truvaze.com 直接在 <a> 标签中暴露 mp4 链接
        mp4_url = None

        # 策略1：查找指向 mp4 的链接
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
            mp4_matches = re.findall(r'https?://[^"\']+\.mp4[^"\']*', resp.text)
            for match in mp4_matches:
                if "video.twimg.com" in match:
                    mp4_url = match
                    break

        if not mp4_url:
            print(f"[WARN] 无法提取 MP4 地址: {video_info.get('video_id', '')}")
            return None

        video_info["mp4_url"] = mp4_url

        # 提取统计信息（通过图标识别）
        metadata = video_info.get("metadata", {})
        page_html = resp.text
        # 使用正则直接从 HTML 中提取图标后面的数字
        # 观看数（直接跟在 img 标签后面）
        views_match = re.search(r'eye-black\.svg[^>]*/?>\s*(\d[\d,]*)', page_html)
        if views_match:
            metadata["views"] = int(views_match.group(1).replace(",", ""))
        # 评论数（直接跟在 img 标签后面）
        comments_match = re.search(r'comment-black\.svg[^>]*/?>\s*(\d[\d,]*)', page_html)
        if comments_match:
            metadata["comments"] = int(comments_match.group(1).replace(",", ""))
        # 收藏数（在 span 标签中）
        likes_match = re.search(r'heart-black\.svg[^>]*/?>\s*<span[^>]*>(\d[\d,]*)</span>', page_html)
        if likes_match:
            metadata["likes"] = int(likes_match.group(1).replace(",", ""))
        video_info["metadata"] = metadata

        # 提取标签（链接格式为 /category/xxx）
        tags = []
        tag_elements = soup.find_all("a", href=re.compile(r"/category/"))
        for tag_elem in tag_elements:
            tag_text = tag_elem.get_text(strip=True)
            if tag_text:
                # 移除 # 前缀
                tag_text = tag_text.lstrip("#")
                tags.append(tag_text)
        if tags:
            video_info["tags"] = tags

        # 提取评论中提到的番号（如 FC2PPV-xxxxx, FC2-PPV-xxxxx 等）
        comments = soup.find_all(["p", "div", "span"], class_=re.compile(r"comment"))
        video_codes = []
        for comment in comments:
            text = comment.get_text()
            # 匹配各种番号格式
            code_matches = re.findall(r'(?:FC2[-_]?PPV[-_]?\d+|SIVR[-_]?\d+|SSNI[-_]?\d+|SDDE[-_]?\d+|IPX[-_]?\d+|ABP[-_]?\d+|PRED[-_]?\d+)', text, re.IGNORECASE)
            video_codes.extend(code_matches)
        if video_codes:
            video_info["video_codes"] = list(set(video_codes))

        # 生成标题（用于文件命名）
        title_parts = []
        # 优先使用番号
        if video_info.get("video_codes"):
            title_parts.append(video_info["video_codes"][0])
        # 其次使用标签
        if tags:
            title_parts.extend(tags[:2])  # 最多取2个标签
        # 最后使用时长
        if video_info.get("duration"):
            title_parts.append(video_info["duration"])

        if title_parts:
            video_info["title"] = "_".join(title_parts)
        else:
            video_info["title"] = video_info.get("video_id", "untitled")

        return video_info

    def download_atomic(self, url: str, filepath: str, referer: str) -> bool:
        """
        原子下载

        Args:
            url: 下载 URL
            filepath: 目标文件路径
            referer: Referer 头

        Returns:
            是否下载成功
        """
        if self._interrupted:
            return False

        temp_filepath = filepath + ".part"

        try:
            # 设置请求头 - Twitter CDN 需要 twitter.com 作为 Referer
            headers = {
                "Referer": "https://twitter.com/",
                "User-Agent": HEADERS["User-Agent"],
            }

            # 流式下载
            resp = self.session.get(
                url,
                headers=headers,
                stream=True,
                timeout=DOWNLOAD_TIMEOUT
            )
            resp.raise_for_status()

            # 获取文件大小
            total_size = int(resp.headers.get('content-length', 0))
            downloaded_size = 0

            # 写入临时文件
            with open(temp_filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                    if self._interrupted:
                        # 中断时删除临时文件
                        f.close()
                        if os.path.exists(temp_filepath):
                            os.remove(temp_filepath)
                        return False

                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        # 显示进度
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            downloaded_mb = downloaded_size / (1024 * 1024)
                            total_mb = total_size / (1024 * 1024)
                            print(f"\r[INFO] 下载进度: {progress:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", end="", flush=True)

            # 下载完成，原子重命名
            os.replace(temp_filepath, filepath)
            print()  # 换行

            return True

        except requests.RequestException as e:
            print(f"\n[ERROR] 下载失败: {e}")
            # 清理临时文件
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            return e

        except Exception as e:
            print(f"\n[ERROR] 下载异常: {e}")
            # 清理临时文件
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            return e

    def download_video_with_refresh(self, video_info: Dict) -> bool:
        """
        下载视频（带 URL 刷新机制）

        Args:
            video_info: 视频信息字典

        Returns:
            是否下载成功
        """
        mp4_url = video_info.get("mp4_url")
        title = video_info.get("title", "untitled")
        video_id = video_info.get("video_id")
        detail_url = video_info.get("url", "")

        if not mp4_url:
            print(f"[WARN] 无 MP4 地址，跳过下载: {title}")
            return False

        # 生成文件名（使用标题，如果标题是 video_id 则添加时长）
        if title == video_id:
            duration = video_info.get("duration", "")
            filename = sanitize_filename(f"{video_id}_{duration}") + ".mp4"
        else:
            filename = sanitize_filename(title) + ".mp4"

        # 检查是否已下载
        if filename in self.downloaded_files:
            print(f"[INFO] 文件已存在，跳过下载: {filename}")
            return True

        # 创建下载目录
        os.makedirs(self.download_dir, exist_ok=True)

        filepath = os.path.join(self.download_dir, filename)

        # 如果文件已存在但不在记录中
        if os.path.exists(filepath):
            print(f"[INFO] 文件已存在，跳过下载: {filename}")
            self.downloaded_files.add(filename)
            return True

        print(f"[INFO] 开始下载: {title}")
        print(f"[INFO] URL: {mp4_url}")

        # 带重试的下载
        current_url = mp4_url
        for attempt in range(RETRY_COUNT):
            if self._interrupted:
                return False

            # 尝试下载
            result = self.download_atomic(current_url, filepath, detail_url)

            if result is True:
                # 下载成功
                self.downloaded_files.add(filename)
                self.download_count += 1

                # 获取实际文件大小
                actual_size = os.path.getsize(filepath)
                actual_mb = actual_size / (1024 * 1024)
                print(f"[INFO] 下载完成: {filename} ({actual_mb:.1f} MB)")
                return True

            # 下载失败，判断是否需要刷新 URL
            error = result
            status_code = None
            if isinstance(error, requests.HTTPError) and error.response is not None:
                status_code = error.response.status_code

            if should_refresh_url(error, status_code):
                print(f"[INFO] 尝试刷新 URL (第 {attempt + 1}/{RETRY_COUNT} 次)...")
                # 重新解析详情页获取新的 mp4 URL
                fresh_info = self.parse_detail_page(video_info)
                if fresh_info and fresh_info.get("mp4_url"):
                    current_url = fresh_info["mp4_url"]
                    print(f"[INFO] 获取到新 URL: {current_url}")
                    # 延迟后重试
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    print(f"[WARN] URL 刷新失败")

            # 不需要刷新或刷新失败
            break

        # 所有重试都失败
        self.download_failed += 1
        return False

    def emit_stream_video(self, video: Dict):
        """流式输出单个视频（JSONL 格式）"""
        print(json.dumps(video, ensure_ascii=False), flush=True)

    def save_videos(self):
        """保存抓取结果到文件"""
        if not self.videos:
            return

        # 原子写入
        temp_file = self.output_file + ".part"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.videos, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, self.output_file)
            print(f"[INFO] 已保存 {len(self.videos)} 个视频到 {self.output_file}")
        except Exception as e:
            print(f"[ERROR] 保存失败: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

    def crawl(
        self,
        max_page: Optional[int] = None,
        target_new: Optional[int] = None,
    ):
        """
        主爬取循环

        Args:
            max_page: 最大页数（None 表示全量爬取）
            target_new: 目标新视频数量（达到后停止）
        """
        print("[INFO] 开始爬取...")
        print(f"[INFO] 已知视频 ID 数: {len(self.seen_ids)}")
        print(f"[INFO] 时间范围: {self.period}")
        print(f"[INFO] 排序方式: {self.sort}")

        if self.download:
            print(f"[INFO] 下载模式已启用，下载目录: {self.download_dir}")

        page = 1
        empty_pages = 0
        new_count = 0

        while not self._interrupted:
            # 检查页数限制
            if max_page and page > max_page:
                print(f"[INFO] 已达到最大页数 {max_page}，停止爬取")
                break

            # 抓取列表页
            video_list = self.parse_list_page(page)

            if not video_list:
                empty_pages += 1
                if empty_pages >= MAX_EMPTY_PAGES:
                    print(f"[INFO] 连续 {MAX_EMPTY_PAGES} 页为空，停止爬取")
                    break
                page += 1
                self._delay(DELAY_BETWEEN_PAGES)
                continue
            else:
                empty_pages = 0

            # 逐个解析详情页
            for video_info in video_list:
                if self._interrupted:
                    break

                # 解析详情页
                detail = self.parse_detail_page(video_info)
                if not detail:
                    continue

                # 添加到结果集
                self.seen_ids.add(detail["video_id"])
                self.videos.append(detail)
                new_count += 1

                # 流式输出模式
                if self.stream_output:
                    # 重定向日志到 stderr，stdout 只输出 JSON
                    self.emit_stream_video(detail)

                print(f"[INFO] 新增视频 ({new_count}): {detail.get('title', detail.get('video_id'))}")

                # 下载视频
                if self.download:
                    self.download_video_with_refresh(detail)
                    # 下载后延迟
                    self._delay((1, 3))

                # 检查目标数量
                if target_new and new_count >= target_new:
                    print(f"[INFO] 已达到目标数量 {target_new}，停止爬取")
                    self.save_videos()
                    self._print_summary()
                    return

                self._delay(DELAY_BETWEEN_DETAILS)

            page += 1
            self._delay(DELAY_BETWEEN_PAGES)

        # 保存结果
        self.save_videos()
        self._print_summary()

    def _print_summary(self):
        """打印爬取摘要"""
        print("\n" + "=" * 50)
        print("[摘要] 爬取完成")
        print(f"[摘要] 发现视频数: {len(self.videos)}")

        if self.download:
            print(f"[摘要] 下载成功: {self.download_count}")
            print(f"[摘要] 下载失败: {self.download_failed}")
            print(f"[摘要] 下载目录: {os.path.abspath(self.download_dir)}")

        print("=" * 50)

        if self._interrupted:
            print("[INFO] 爬取被中断")


def main():
    parser = argparse.ArgumentParser(description="Truvaze 视频爬虫")
    parser.add_argument(
        "--proxy",
        type=str,
        default="socks5://127.0.0.1:1080",
        help="代理地址（默认: socks5://127.0.0.1:1080）",
    )
    parser.add_argument(
        "--page",
        type=int,
        help="单页调试模式，只抓取指定页",
    )
    parser.add_argument(
        "--target-new",
        type=int,
        help="目标新视频数量，达到后停止",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=OUTPUT_FILE,
        help=f"输出文件路径（默认: {OUTPUT_FILE}）",
    )
    parser.add_argument(
        "--stream-output",
        action="store_true",
        help="流式输出模式（JSONL 格式，供管道使用）",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="禁用断点续爬",
    )
    parser.add_argument(
        "--seen-ids-file",
        type=str,
        help="已知视频 ID 文件路径（每行一个）",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="下载视频文件（使用标题作为文件名）",
    )
    parser.add_argument(
        "--download-dir",
        type=str,
        default=DEFAULT_DOWNLOAD_DIR,
        help=f"视频下载目录（默认: {DEFAULT_DOWNLOAD_DIR}）",
    )
    parser.add_argument(
        "--sort",
        type=str,
        choices=list(SORT_OPTIONS.keys()),
        default="favorite",
        help="排序方式（默认: favorite）",
    )
    parser.add_argument(
        "--period",
        type=str,
        choices=list(PERIOD_OPTIONS.keys()),
        default="monthly",
        help="时间范围（默认: monthly）",
    )

    args = parser.parse_args()

    # 设置代理
    if args.proxy:
        proxy = args.proxy
        # 根据代理类型设置对应的环境变量
        if proxy.startswith("socks"):
            os.environ["ALL_PROXY"] = proxy
            print(f"[INFO] 使用 SOCKS5 代理: {proxy}")
        else:
            os.environ["HTTP_PROXY"] = proxy
            os.environ["HTTPS_PROXY"] = proxy
            print(f"[INFO] 使用 HTTP 代理: {proxy}")

    # 创建爬虫实例
    spider = TruvazeSpider(
        output_file=args.output,
        stream_output=args.stream_output,
        resume=not args.no_resume,
        seen_ids_file=args.seen_ids_file,
        download=args.download,
        download_dir=args.download_dir,
        sort=args.sort,
        period=args.period,
    )

    # 开始爬取
    if args.page:
        spider.crawl(max_page=args.page)
    elif args.target_new:
        spider.crawl(target_new=args.target_new)
    else:
        spider.crawl()


if __name__ == "__main__":
    main()
