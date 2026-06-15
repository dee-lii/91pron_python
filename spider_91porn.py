#!/usr/bin/env python3
"""
91Porn 爬虫脚本 - 独立运行版本（支持下载）
从 https://github.com/nianzhibai/91 提取，复用原仓库下载逻辑

使用方法:
    # 安装依赖
    pip install requests beautifulsoup4 lxml

    # 全量爬取并下载视频
    python3 spider_91porn.py --download

    # 抓取并下载指定数量的新视频
    python3 spider_91porn.py --target-new 10 --download

    # 指定下载目录
    python3 spider_91porn.py --download --download-dir ./videos

    # 仅抓取元数据（不下载）
    python3 spider_91porn.py

    # 使用代理
    ALL_PROXY=socks5://127.0.0.1:1080 python3 spider_91porn.py --download
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
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== 配置 ====================
BASE_URL = "https://91porn.com"
LIST_URL = f"{BASE_URL}/v.php?category=hot&viewtype=basic&page={{}}"
DETAIL_URL = f"{BASE_URL}/view_video.php?viewkey={{}}"
DELAY_BETWEEN_PAGES = (3, 6)  # 列表页之间的延迟范围（秒）
DELAY_BETWEEN_DETAILS = (2, 5)  # 详情页之间的延迟范围（秒）
RETRY_COUNT = 3
RETRY_DELAY = 5
MAX_EMPTY_PAGES = 2  # 连续空页面数达到此值时停止
OUTPUT_FILE = "91porn_videos.json"
DEFAULT_DOWNLOAD_DIR = "./91porn_videos"
DOWNLOAD_TIMEOUT = 120  # 下载超时时间（秒）
CHUNK_SIZE = 8192  # 下载块大小

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
    判断是否需要刷新视频 URL（复用原仓库逻辑）

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


class Porn91Spider:
    """91Porn 视频爬虫"""

    def __init__(
        self,
        output_file: str = OUTPUT_FILE,
        stream_output: bool = False,
        resume: bool = True,
        seen_viewkeys_file: Optional[str] = None,
        download: bool = False,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
    ):
        self.output_file = output_file
        self.stream_output = stream_output
        self.resume = resume
        self.seen_viewkeys_file = seen_viewkeys_file
        self.download = download
        self.download_dir = download_dir

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

        # 已抓取的 viewkey 集合
        self.seen_viewkeys: Set[str] = set()
        self._load_seen_viewkeys()

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

    def _load_seen_viewkeys(self):
        """加载已抓取的 viewkey 集合"""
        if not self.resume:
            return

        # 从指定文件加载
        if self.seen_viewkeys_file and os.path.exists(self.seen_viewkeys_file):
            with open(self.seen_viewkeys_file, "r") as f:
                self.seen_viewkeys = set(line.strip() for line in f if line.strip())
            print(f"[INFO] 从 {self.seen_viewkeys_file} 加载了 {len(self.seen_viewkeys)} 个已知 viewkey")
            return

        # 从输出文件加载
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, "r") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.seen_viewkeys = {v.get("viewkey") for v in data if v.get("viewkey")}
                        self.videos = data
                        print(f"[INFO] 从 {self.output_file} 加载了 {len(self.seen_viewkeys)} 个已知 viewkey")
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

    def _check_cloudflare(self, html: str) -> bool:
        """检测 Cloudflare 拦截"""
        if "Just a moment" in html or "Checking your browser" in html:
            print("[WARN] 检测到 Cloudflare 拦截，请稍后重试或使用代理")
            return True
        return False

    def _warm_cookies(self):
        """
        Cookie 预热（复用原仓库逻辑）
        访问列表页获取 warm cookies，提高下载成功率
        """
        if self._interrupted:
            return

        try:
            resp = self.session.get(LIST_URL.format(1), timeout=15)
            resp.raise_for_status()
            # 确保有 mode=d cookie
            if "mode" not in self.session.cookies:
                self.session.cookies.set("mode", "d", domain="91porn.com")
        except Exception as e:
            if self._interrupted:
                return
            print(f"[WARN] Cookie 预热失败: {e}")
            # 设置默认 cookie
            self.session.cookies.set("mode", "d", domain="91porn.com")

    def parse_video_url(self, html: str) -> Optional[str]:
        """
        解析视频 URL（复用原仓库逻辑）

        Args:
            html: 详情页 HTML

        Returns:
            视频 MP4 URL 或 None
        """
        mp4_url = None

        # 策略1：解析 strencode2 函数（原仓库主策略）
        strencode_match = re.search(r"strencode2\(['\"](.+?)['\"]\)", html)
        if strencode_match:
            encoded_str = strencode_match.group(1)
            try:
                decoded_html = unquote(encoded_str)
                # 直接用正则提取 src 属性（兼容不完整的 HTML）
                src_match = re.search(r"src=['\"]([^'\"]+)['\"]", decoded_html)
                if src_match:
                    mp4_url = src_match.group(1)
                else:
                    # 备用：尝试 BeautifulSoup 解析
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
                print(f"[WARN] strencode2 解析失败: {e}")

        # 策略2：正则匹配 .mp4 URL（原仓库备选策略）
        if not mp4_url:
            mp4_matches = re.findall(r'https?://[^"\']+\.mp4[^"\']*', html)
            # 过滤广告域名（原仓库逻辑：排除含 "kwai" 或 "ad-" 的链接）
            for match in mp4_matches:
                if "kwai" not in match and "ad-" not in match:
                    mp4_url = match
                    break

        return mp4_url

    def resolve_fresh_video_url(self, viewkey: str, source_id: Optional[str] = None) -> Optional[str]:
        """
        重新获取视频 URL（复用原仓库 URL 刷新机制）

        Args:
            viewkey: 视频 viewkey
            source_id: 预期的 source_id（用于验证）

        Returns:
            新的视频 MP4 URL 或 None
        """
        if self._interrupted:
            return None

        detail_url = DETAIL_URL.format(viewkey)

        try:
            # Cookie 预热
            self._warm_cookies()

            # 请求详情页
            resp = self.session.get(detail_url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            if self._interrupted:
                return None
            print(f"[WARN] 刷新 URL 失败: {e}")
            return None

        if self._check_cloudflare(resp.text):
            return None

        # 解析视频 URL
        mp4_url = self.parse_video_url(resp.text)
        if not mp4_url:
            return None

        # 验证 source_id 一致性（原仓库逻辑）
        if source_id:
            source_id_match = re.search(r"(\d+)", resp.text[:5000])
            if source_id_match:
                page_id = source_id_match.group(1)
                if page_id != source_id:
                    print(f"[WARN] source_id 不一致，刷新失败")
                    return None

        return mp4_url

    def parse_list_page(self, page_num: int) -> List[Dict]:
        """解析列表页，提取视频卡片信息"""
        if self._interrupted:
            return []

        url = LIST_URL.format(page_num)
        print(f"[INFO] 正在抓取列表页 {page_num}: {url}")

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            if self._interrupted:
                return []
            print(f"[ERROR] 请求列表页失败: {e}")
            return []

        if self._check_cloudflare(resp.text):
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        videos = []

        # 查找视频卡片
        video_cards = soup.select("div.video-elem, div.col-md-3, div.thumb-block")
        if not video_cards:
            # 备用选择器
            video_cards = soup.find_all("div", class_=re.compile(r"video|thumb|item"))

        seen_ids = set()  # 页面内去重

        for card in video_cards:
            try:
                # 提取链接
                link = card.find("a", href=re.compile(r"viewkey="))
                if not link:
                    continue

                href = link.get("href", "")
                # 提取 viewkey
                viewkey_match = re.search(r"viewkey=([^&]+)", href)
                if not viewkey_match:
                    continue
                viewkey = viewkey_match.group(1)

                # 提取 source_id
                source_id_match = re.search(r"id=(\d+)", href)
                source_id = source_id_match.group(1) if source_id_match else ""

                # 页面内去重（优先用 viewkey，因为 source_id 可能为空）
                dedup_key = viewkey if viewkey else source_id
                if dedup_key in seen_ids:
                    continue
                seen_ids.add(dedup_key)

                # 已抓取过的跳过
                if viewkey in self.seen_viewkeys:
                    continue

                # 提取标题
                title_elem = card.select_one("span.video-title, .title, h5, h4")
                if title_elem:
                    title = title_elem.get_text(strip=True)
                else:
                    title = link.get("title", "") or link.get_text(strip=True)

                # 提取缩略图
                img = card.find("img")
                thumb_url = ""
                if img:
                    thumb_url = img.get("data-src") or img.get("src") or ""
                    if thumb_url and not thumb_url.startswith("http"):
                        thumb_url = urljoin(BASE_URL, thumb_url)

                videos.append({
                    "viewkey": viewkey,
                    "source_id": source_id,
                    "title": title,
                    "thumbnail": thumb_url,
                    "url": urljoin(BASE_URL, href),
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

        if self._check_cloudflare(resp.text):
            return None

        # 解析视频 URL
        mp4_url = self.parse_video_url(resp.text)

        if not mp4_url:
            print(f"[WARN] 无法提取 MP4 地址: {video_info.get('title', '')}")
            return None

        # 验证 source_id 一致性
        source_id_match = re.search(r"(\d+)", resp.text[:5000])
        if source_id_match and video_info.get("source_id"):
            page_id = source_id_match.group(1)
            if page_id != video_info["source_id"]:
                print(f"[WARN] source_id 不一致，丢弃: {video_info.get('title', '')}")
                return None

        video_info["mp4_url"] = mp4_url
        return video_info

    def download_atomic(self, url: str, filepath: str, referer: str) -> bool:
        """
        原子下载（复用原仓库逻辑）

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
            # 设置请求头
            headers = {
                "Referer": referer,
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
        下载视频（带 URL 刷新机制，复用原仓库逻辑）

        Args:
            video_info: 视频信息字典

        Returns:
            是否下载成功
        """
        mp4_url = video_info.get("mp4_url")
        title = video_info.get("title", "untitled")
        viewkey = video_info.get("viewkey")
        source_id = video_info.get("source_id")
        detail_url = video_info.get("url", "")

        if not mp4_url:
            print(f"[WARN] 无 MP4 地址，跳过下载: {title}")
            return False

        # 生成文件名
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

        # 带重试的下载（原仓库逻辑：最多 3 次）
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
                fresh_url = self.resolve_fresh_video_url(viewkey, source_id)
                if fresh_url:
                    current_url = fresh_url
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
        print(f"[INFO] 已知 viewkey 数: {len(self.seen_viewkeys)}")

        if self.download:
            print(f"[INFO] 下载模式已启用，下载目录: {self.download_dir}")
            # Cookie 预热
            self._warm_cookies()

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
                self.seen_viewkeys.add(detail["viewkey"])
                self.videos.append(detail)
                new_count += 1

                # 流式输出模式
                if self.stream_output:
                    # 重定向日志到 stderr，stdout 只输出 JSON
                    self.emit_stream_video(detail)

                print(f"[INFO] 新增视频 ({new_count}): {detail.get('title', detail.get('viewkey'))}")

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
    parser = argparse.ArgumentParser(description="91Porn 视频爬虫")
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
        "--seen-viewkeys-file",
        type=str,
        help="已知 viewkey 文件路径（每行一个）",
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
    spider = Porn91Spider(
        output_file=args.output,
        stream_output=args.stream_output,
        resume=not args.no_resume,
        seen_viewkeys_file=args.seen_viewkeys_file,
        download=args.download,
        download_dir=args.download_dir,
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
