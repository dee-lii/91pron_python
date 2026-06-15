#!/usr/bin/env python3
"""
XHotList 爬虫脚本 - 独立运行版本（支持下载）
爬取 https://top.xhotlist.com/ 网站的 X(Twitter) 热门成人短视频

使用方法:
    # 安装依赖
    pip install requests beautifulsoup4 lxml

    # 全量爬取并下载视频
    python3 spider_xhotlist.py --download

    # 抓取并下载指定数量的新视频
    python3 spider_xhotlist.py --target-new 10 --download

    # 指定下载目录
    python3 spider_xhotlist.py --download --download-dir ./videos

    # 仅抓取元数据（不下载）
    python3 spider_xhotlist.py

    # 使用代理
    python3 spider_xhotlist.py --download --proxy socks5://127.0.0.1:1080

    # 按热门周期筛选
    python3 spider_xhotlist.py --period week --download

    # 按排序方式
    python3 spider_xhotlist.py --sort new --download

    # 按时长筛选
    python3 spider_xhotlist.py --duration short --download

    # 按标签筛选
    python3 spider_xhotlist.py --tag anime --download

    # 列出所有可用选项
    python3 spider_xhotlist.py --list-options
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
from urllib.parse import urljoin, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== 配置 ====================
BASE_URL = "https://top.xhotlist.com"
DELAY_BETWEEN_PAGES = (2, 4)  # 列表页之间的延迟范围（秒）
DELAY_BETWEEN_DETAILS = (1, 3)  # 详情页之间的延迟范围（秒）
RETRY_COUNT = 3
RETRY_DELAY = 5
MAX_EMPTY_PAGES = 3  # 连续空页面数达到此值时停止
OUTPUT_FILE = "xhotlist_videos.json"
DEFAULT_DOWNLOAD_DIR = "./xhotlist_videos"
DOWNLOAD_TIMEOUT = 120  # 下载超时时间（秒）
CHUNK_SIZE = 8192  # 下载块大小

# 热门周期选项
PERIOD_OPTIONS = {
    "all": "",  # 全部
    "day": "/period/day",  # 今日热门
    "week": "/period/week",  # 本周热门
    "month": "/period/month",  # 本月热门
    "total": "/period/total",  # 总热门
}

# 排序方式选项
SORT_OPTIONS = {
    "default": "",  # 播放最多（默认）
    "new": "/sort/new",  # 最新
    "duration": "/sort/duration",  # 时长最长
    "old": "/sort/old",  # 最早
}

# 时长筛选选项
DURATION_OPTIONS = {
    "all": "",  # 全部
    "short": "/duration/short",  # 5分钟内
    "medium": "/duration/medium",  # 5-30分钟
    "long": "/duration/long",  # 30分钟以上
}

# 热门标签列表（从网站提取）
POPULAR_TAGS = [
    "anime", "jk", "kyonyu", "lolita", "shaved", "beautiful-girl",
    "personal-filming", "hamedori", "sm", "small-breasts", "masturbation",
    "fellatio", "female-pervert", "outdoor", "shirouto", "gay",
    "big-sister", "orgy", "uncensored", "cosplay", "married-woman",
    "gal", "incest", "titjob", "voyeur", "cum-swallowing", "massage",
    "anal", "bukkake", "facial", "creampie", "female-teacher",
    "molestation", "handjob",
]

# Chrome 125 浏览器标识
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": BASE_URL,
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


class XHotListSpider:
    """XHotList 视频爬虫"""

    def __init__(
        self,
        output_file: str = OUTPUT_FILE,
        stream_output: bool = False,
        resume: bool = True,
        seen_ids_file: Optional[str] = None,
        download: bool = False,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
        period: str = "all",
        sort: str = "default",
        duration: str = "all",
        tag: Optional[str] = None,
    ):
        self.output_file = output_file
        self.stream_output = stream_output
        self.resume = resume
        self.seen_ids_file = seen_ids_file
        self.download = download
        self.download_dir = download_dir
        self.period = period
        self.sort = sort
        self.duration = duration
        self.tag = tag

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
        # 只在主线程中注册信号处理
        try:
            signal.signal(signal.SIGINT, self._handle_interrupt)
        except ValueError:
            # 非主线程中忽略信号注册
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

    def build_list_url(self, page_num: int) -> str:
        """
        构建列表页 URL

        Args:
            page_num: 页码

        Returns:
            完整的列表页 URL
        """
        # 标签模式
        if self.tag:
            base_path = f"/videos/tag/{self.tag}"
        else:
            # 组合周期、排序、时长
            period_path = PERIOD_OPTIONS.get(self.period, "")
            sort_path = SORT_OPTIONS.get(self.sort, "")
            duration_path = DURATION_OPTIONS.get(self.duration, "")

            # 优先使用排序路径（如果非默认）
            if sort_path and self.sort != "default":
                base_path = f"/videos{sort_path}"
            elif period_path:
                base_path = f"/videos{period_path}"
            elif duration_path:
                base_path = f"/videos{duration_path}"
            else:
                base_path = "/videos"

        # 添加分页
        if page_num > 1:
            return f"{BASE_URL}{base_path}/page/{page_num}"
        else:
            return f"{BASE_URL}{base_path}"

    def parse_list_page(self, page_num: int) -> List[Dict]:
        """解析列表页，提取视频卡片信息"""
        if self._interrupted:
            return []

        url = self.build_list_url(page_num)
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

        # 查找视频卡片
        video_cards = soup.find_all("a", class_="video-card")

        for card in video_cards:
            try:
                href = card.get("href", "")
                if not href:
                    continue

                # 提取视频 ID
                video_id_match = re.search(r"/video/([^/]+)", href)
                if not video_id_match:
                    continue
                video_id = video_id_match.group(1)

                # 已抓取过的跳过
                if video_id in self.seen_ids:
                    continue

                # 提取标题
                title_elem = card.find("span", class_="card-title")
                title = title_elem.get_text(strip=True) if title_elem else video_id

                # 提取时长
                duration_elem = card.find("span", class_="duration")
                duration = duration_elem.get_text(strip=True) if duration_elem else ""

                # 提取播放量
                meta_elem = card.find("span", class_="card-meta")
                views = 0
                if meta_elem:
                    views_text = meta_elem.get_text(strip=True)
                    views_match = re.search(r'([\d.]+)([KkMm]?)', views_text)
                    if views_match:
                        num = float(views_match.group(1))
                        suffix = views_match.group(2).upper()
                        if suffix == 'K':
                            views = int(num * 1000)
                        elif suffix == 'M':
                            views = int(num * 1000000)
                        else:
                            views = int(num)

                # 提取缩略图
                thumb_elem = card.find("img")
                thumb_url = ""
                if thumb_elem:
                    thumb_url = thumb_elem.get("src", "") or thumb_elem.get("data-src", "")

                videos.append({
                    "video_id": video_id,
                    "title": title,
                    "thumbnail": thumb_url,
                    "url": urljoin(BASE_URL, href),
                    "duration": duration,
                    "views": views,
                })

            except Exception as e:
                print(f"[WARN] 解析视频卡片失败: {e}")
                continue

        print(f"[INFO] 列表页 {page_num} 找到 {len(videos)} 个新视频")
        return videos

    def parse_detail_page(self, video_info: Dict) -> Optional[Dict]:
        """解析详情页，提取真实视频地址"""
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

        # 提取视频地址（从 <source> 标签）
        video_url = None
        source_elem = soup.find("source", type="video/mp4")
        if source_elem:
            video_url = source_elem.get("src", "")

        # 备用：从 download-action 链接提取
        if not video_url:
            download_link = soup.find("a", class_="download-action")
            if download_link:
                video_url = download_link.get("href", "")

        # 备用：从 <video> 标签的 src 属性提取
        if not video_url:
            video_elem = soup.find("video")
            if video_elem:
                video_url = video_elem.get("src", "")

        if not video_url:
            print(f"[WARN] 无法提取视频地址: {video_info.get('title', '')}")
            return None

        # 确保 URL 是完整的
        if video_url and not video_url.startswith("http"):
            video_url = urljoin(BASE_URL, video_url)

        video_info["video_url"] = video_url
        video_info["video_type"] = "mp4"

        # 提取标签
        tags = []
        tag_links = soup.find_all("a", href=re.compile(r"/videos/tag/"))
        for tag_link in tag_links:
            tag_text = tag_link.get_text(strip=True).replace("# ", "")
            if tag_text:
                tags.append(tag_text)
        video_info["tags"] = tags

        return video_info

    def download_video(self, video_info: Dict) -> bool:
        """
        下载视频

        Args:
            video_info: 视频信息字典

        Returns:
            是否下载成功
        """
        if self._interrupted:
            return False

        video_url = video_info.get("video_url")
        title = video_info.get("title", "untitled")
        video_id = video_info.get("video_id")

        if not video_url:
            print(f"[WARN] 无视频地址，跳过下载: {title}")
            return False

        # 生成文件名
        filename = sanitize_filename(f"{video_id}_{title}") + ".mp4"

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
        print(f"[INFO] URL: {video_url}")

        temp_filepath = filepath + ".part"

        try:
            # 设置请求头
            headers = {
                "Referer": BASE_URL,
                "User-Agent": HEADERS["User-Agent"],
            }

            # 流式下载
            resp = self.session.get(
                video_url,
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

            self.downloaded_files.add(filename)
            self.download_count += 1

            # 获取实际文件大小
            actual_size = os.path.getsize(filepath)
            actual_mb = actual_size / (1024 * 1024)
            print(f"[INFO] 下载完成: {filename} ({actual_mb:.1f} MB)")
            return True

        except requests.RequestException as e:
            print(f"\n[ERROR] 下载失败: {e}")
            # 清理临时文件
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
            self.download_failed += 1
            return False

        except Exception as e:
            print(f"\n[ERROR] 下载异常: {e}")
            # 清理临时文件
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
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

        # 显示筛选条件
        if self.tag:
            print(f"[INFO] 标签筛选: {self.tag}")
        else:
            conditions = []
            if self.period != "all":
                conditions.append(f"周期: {self.period}")
            if self.sort != "default":
                conditions.append(f"排序: {self.sort}")
            if self.duration != "all":
                conditions.append(f"时长: {self.duration}")
            if conditions:
                print(f"[INFO] 筛选条件: {', '.join(conditions)}")

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
                    self.emit_stream_video(detail)

                print(f"[INFO] 新增视频 ({new_count}): {detail.get('title', detail.get('video_id'))}")

                # 下载视频
                if self.download:
                    self.download_video(detail)
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
    # 无参数运行时显示使用指南
    if len(sys.argv) == 1:
        print("""
╔══════════════════════════════════════════════════════════════╗
║              XHotList 爬虫 - X(Twitter)热门视频              ║
╚══════════════════════════════════════════════════════════════╝

📖 使用方法:

  1️⃣  抓取视频（仅获取元数据，不下载）
     python3 spider_xhotlist.py --period week --page 3

  2️⃣  抓取并下载视频
     python3 spider_xhotlist.py --period week --page 3 --download

  3️⃣  按标签筛选
     python3 spider_xhotlist.py --tag anime --download
     python3 spider_xhotlist.py --tag cosplay --page 5 --download

  4️⃣  按时长筛选
     python3 spider_xhotlist.py --duration short --download

  5️⃣  使用代理
     python3 spider_xhotlist.py --download --proxy socks5://127.0.0.1:1080

📋 常用参数:
  --period <周期>     热门周期: all/day/week/month/total
  --sort <排序>       排序方式: default/new/duration/old
  --duration <时长>   时长筛选: all/short/medium/long
  --tag <标签>        按标签筛选（如: anime/cosplay/jk）
  --page <页数>       抓取前几页（默认: 5）
  --download          下载视频文件
  --download-dir      指定下载目录（默认: ./xhotlist_videos）
  --proxy <地址>      使用代理

💡 快速开始:
  python3 spider_xhotlist.py --list-options    # 查看所有可用选项
  python3 spider_xhotlist.py --period week --page 2 --download
  python3 spider_xhotlist.py --tag anime --download

📌 注意: 默认不使用代理，如需代理请用 --proxy 参数指定
""")
        sys.exit(0)

    parser = argparse.ArgumentParser(description="XHotList 视频爬虫")
    parser.add_argument(
        "--proxy",
        type=str,
        default="",
        help="代理地址（如: socks5://127.0.0.1:1080）",
    )
    parser.add_argument(
        "--page",
        type=int,
        default=5,
        help="抓取前几页（默认: 5）",
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
        help="下载视频文件",
    )
    parser.add_argument(
        "--download-dir",
        type=str,
        default=DEFAULT_DOWNLOAD_DIR,
        help=f"视频下载目录（默认: {DEFAULT_DOWNLOAD_DIR}）",
    )
    parser.add_argument(
        "--period",
        type=str,
        choices=list(PERIOD_OPTIONS.keys()),
        default="all",
        help="热门周期（默认: all）",
    )
    parser.add_argument(
        "--sort",
        type=str,
        choices=list(SORT_OPTIONS.keys()),
        default="default",
        help="排序方式（默认: default - 播放最多）",
    )
    parser.add_argument(
        "--duration",
        type=str,
        choices=list(DURATION_OPTIONS.keys()),
        default="all",
        help="时长筛选（默认: all）",
    )
    parser.add_argument(
        "--tag",
        type=str,
        help="按标签筛选（如: anime, cosplay, jk）",
    )
    parser.add_argument(
        "--list-options",
        action="store_true",
        help="列出所有可用选项",
    )

    args = parser.parse_args()

    # 列出选项
    if args.list_options:
        print("=" * 60)
        print("[INFO] 所有可用选项:")
        print("=" * 60)

        print("\n  热门周期 (--period):")
        for key, desc in PERIOD_OPTIONS.items():
            print(f"    {key:12s} {desc or '(默认)'}")

        print("\n  排序方式 (--sort):")
        for key, desc in SORT_OPTIONS.items():
            print(f"    {key:12s} {desc or '(默认: 播放最多)'}")

        print("\n  时长筛选 (--duration):")
        for key, desc in DURATION_OPTIONS.items():
            print(f"    {key:12s} {desc or '(默认)'}")

        print("\n  热门标签 (--tag):")
        for i, tag in enumerate(POPULAR_TAGS, 1):
            print(f"    {i:2d}. {tag}")

        print(f"\n[INFO] 使用示例:")
        print(f"  python3 {os.path.basename(__file__)} --period week --page 3 --download")
        print(f"  python3 {os.path.basename(__file__)} --tag anime --download")
        print(f"  python3 {os.path.basename(__file__)} --duration short --sort new --download")
        sys.exit(0)

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
    spider = XHotListSpider(
        output_file=args.output,
        stream_output=args.stream_output,
        resume=not args.no_resume,
        seen_ids_file=args.seen_ids_file,
        download=args.download,
        download_dir=args.download_dir,
        period=args.period,
        sort=args.sort,
        duration=args.duration,
        tag=args.tag,
    )

    # 开始爬取
    spider.crawl(max_page=args.page, target_new=args.target_new)


if __name__ == "__main__":
    main()
