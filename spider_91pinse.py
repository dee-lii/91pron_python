#!/usr/bin/env python3
"""
91PinSe 爬虫脚本 - 独立运行版本（支持下载）
爬取 https://91pinse.com/ 网站的视频

使用方法:
    # 安装依赖
    pip install requests beautifulsoup4 lxml

    # 全量爬取并下载视频
    python3 spider_91pinse.py --download

    # 抓取并下载指定数量的新视频
    python3 spider_91pinse.py --target-new 10 --download

    # 指定下载目录
    python3 spider_91pinse.py --download --download-dir ./videos

    # 仅抓取元数据（不下载）
    python3 spider_91pinse.py

    # 使用代理
    ALL_PROXY=socks5://127.0.0.1:1080 python3 spider_91pinse.py --download

    # 指定排序方式
    python3 spider_91pinse.py --sort hot --download

    # 按播放量排序 + 本周视频
    python3 spider_91pinse.py --sort view --time week --download

    # 按点赞数排序 + 本月视频
    python3 spider_91pinse.py --sort like --time month --download

    # 按分类/关键词抓取前几页
    python3 spider_91pinse.py --category 熟女 --page 3 --download

    # 列出所有可用分类选项
    python3 spider_91pinse.py --list-categories
"""

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
from urllib.parse import urljoin, unquote, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==================== 配置 ====================
BASE_URL = "https://91pinse.com"
LIST_URL = f"{BASE_URL}/v{{}}/?page={{}}"
DETAIL_URL = f"{BASE_URL}/v/{{}}"
DELAY_BETWEEN_PAGES = (3, 6)  # 列表页之间的延迟范围（秒）
DELAY_BETWEEN_DETAILS = (2, 5)  # 详情页之间的延迟范围（秒）
RETRY_COUNT = 3
RETRY_DELAY = 5
MAX_EMPTY_PAGES = 2  # 连续空页面数达到此值时停止
OUTPUT_FILE = "91pinse_videos.json"
DEFAULT_DOWNLOAD_DIR = "./91pinse_videos"
DOWNLOAD_TIMEOUT = 120  # 下载超时时间（秒）
CHUNK_SIZE = 8192  # 下载块大小

# 排序方式映射
SORT_OPTIONS = {
    "latest": "last",  # 最近更新
    "hot": "hot",  # 热门视频（独立页面）
    "score": "score",  # 综合排序（热门视频页）
    "view": "view",  # 播放最多
    "like": "like",  # 最多点赞
}

# 时间筛选选项
TIME_OPTIONS = {
    "all": "",  # 全部时间
    "today": "today",  # 今天
    "week": "week",  # 本周
    "month": "month",  # 本月
}

# 排行榜选项
RANK_OPTIONS = {
    "current-hot": "/rank/current-hot",  # 当前热门
    "month-hot": "/rank/month-hot",  # 月度趋势
    "month-favorite": "/rank/month-favorite",  # 月度收藏
    "recently-featured": "/rank/recently-featured",  # 精选视频
    "popular-now": "/rank/popular-now",  # 大家都在看
}

# 所有可用分类选项说明
CATEGORY_HELP = {
    "排序方式 (--sort)": {
        "latest": "最近更新（默认）",
        "hot": "热门视频",
        "score": "综合排序（热门视频页）",
        "view": "播放最多",
        "like": "最多点赞",
    },
    "时间筛选 (--time)": {
        "all": "全部时间（默认）",
        "today": "今天",
        "week": "本周",
        "month": "本月",
    },
    "排行榜 (--rank)": {
        "current-hot": "当前热门",
        "month-hot": "月度趋势",
        "month-favorite": "月度收藏",
        "recently-featured": "精选视频",
        "popular-now": "大家都在看",
    },
}

# 预设分类关键词（来自首页标签）
PRESET_CATEGORIES = [
    "熟女", "巨乳", "阿姨", "内射", "高颜值", "少妇", "学生", "黑人",
    "绿帽", "3p", "偷情", "母狗", "人妻", "眼镜", "露脸", "黑丝",
    "大奶", "自慰", "电话", "女大", "双飞", "强推", "对白", "极品",
    "技师", "高潮", "足交", "肛交", "换妻", "调教", "口爆", "cos",
    "单男", "体育生", "后入", "打桩", "喷水", "骚话",
]

# Chrome 125 浏览器标识
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
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
    # 先移除 HTML 标签（如 <mark> 等高亮标签）
    filename = re.sub(r'<[^>]+>', '', filename)

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


def decode_base64(encoded_str: str) -> str:
    """解码 Base64 字符串"""
    try:
        # 处理 URL 安全的 Base64
        encoded_str = encoded_str.replace('-', '+').replace('_', '/')
        # 补齐 padding
        padding = 4 - len(encoded_str) % 4
        if padding != 4:
            encoded_str += '=' * padding
        return base64.b64decode(encoded_str).decode('utf-8')
    except Exception as e:
        return ""


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


class PinSe91Spider:
    """91PinSe 视频爬虫"""

    def __init__(
        self,
        output_file: str = OUTPUT_FILE,
        stream_output: bool = False,
        resume: bool = True,
        seen_ids_file: Optional[str] = None,
        download: bool = False,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
        sort: str = "latest",
        time_filter: str = "all",
        rank: Optional[str] = None,
        category: Optional[str] = None,
    ):
        self.output_file = output_file
        self.stream_output = stream_output
        self.resume = resume
        self.seen_ids_file = seen_ids_file
        self.download = download
        self.download_dir = download_dir
        self.sort = sort
        self.time_filter = time_filter
        self.rank = rank
        self.category = category

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
            if filename.endswith('.mp4') or filename.endswith('.m3u8'):
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

        # 构建 URL
        if self.category:
            # 分类/关键词搜索模式
            from urllib.parse import quote
            url = f"{BASE_URL}/v/search?keyword={quote(self.category)}&page={page_num}"
        elif self.rank:
            # 排行榜模式
            rank_path = RANK_OPTIONS.get(self.rank, "")
            url = f"{BASE_URL}{rank_path}?page={page_num}"
        elif self.sort == "hot":
            # 热门视频使用独立路径
            url = f"{BASE_URL}/v/hot/?page={page_num}"
        else:
            # 普通列表模式，使用查询参数
            sort_value = SORT_OPTIONS.get(self.sort, "last")
            time_value = TIME_OPTIONS.get(self.time_filter, "")
            params = f"page={page_num}"
            if sort_value and sort_value != "hot":
                params = f"sort={sort_value}&{params}"
            if time_value:
                params = f"time={time_value}&{params}"
            url = f"{BASE_URL}/v/?{params}"

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

        # 查找视频卡片 - 根据 91pinse.com 的实际结构
        # 视频链接格式为 /v/{videoId}（如 /v/438988）
        video_links = soup.find_all("a", href=re.compile(r"^/v/\d+$"))
        if not video_links:
            # 备用选择器
            video_links = soup.select('a[href*="/v/"]')

        seen_ids = set()  # 页面内去重

        # 按视频 ID 分组链接（同一个视频可能有多个链接：时长、标题等）
        video_groups = {}
        for link in video_links:
            try:
                href = link.get("href", "")
                if not href:
                    continue

                # 提取视频 ID
                video_id_match = re.search(r"/v/(\d+)", href)
                if not video_id_match:
                    continue
                video_id = video_id_match.group(1)

                # 跳过 author 链接
                if "/author/" in href:
                    continue

                if video_id not in video_groups:
                    video_groups[video_id] = []
                video_groups[video_id].append(link)
            except Exception:
                continue

        # 处理每个视频组
        for video_id, links in video_groups.items():
            try:
                # 页面内去重
                if video_id in seen_ids:
                    continue
                seen_ids.add(video_id)

                # 已抓取过的跳过
                if video_id in self.seen_ids:
                    continue

                # 提取标题（跳过时长文本）
                title = ""
                duration = ""
                thumb_url = ""

                for link in links:
                    text = link.get_text(strip=True)
                    link_title = link.get("title", "")

                    # 跳过时长文本（格式如 "0:01:08HDPreview"）
                    if re.match(r'^\d+:\d+:\d+', text):
                        # 提取时长
                        duration_match = re.search(r'(\d+:\d+:\d+)', text)
                        if duration_match:
                            duration = duration_match.group(1)
                        # 提取缩略图
                        img = link.find("img")
                        if img:
                            thumb_url = img.get("data-src") or img.get("src") or ""
                            if thumb_url and not thumb_url.startswith("http"):
                                thumb_url = urljoin(BASE_URL, thumb_url)
                        continue

                    # 优先使用 title 属性
                    if link_title and len(link_title) > len(title):
                        title = link_title

                    # 其次使用链接文本（排除纯数字和时长格式）
                    if not title and text and not re.match(r'^\d+$', text) and not re.match(r'^\d+:\d+', text):
                        title = text

                if not title:
                    title = f"视频 {video_id}"

                # 提取观看数（从父元素中查找）
                parent = links[0].parent if links else None
                views = 0
                if parent:
                    parent_text = parent.get_text()
                    views_match = re.search(r'(\d[\d,]*)\s*(?:次观看|views|观看)', parent_text)
                    if views_match:
                        views = int(views_match.group(1).replace(",", ""))

                videos.append({
                    "video_id": video_id,
                    "title": title,
                    "thumbnail": thumb_url,
                    "url": urljoin(BASE_URL, f"/v/{video_id}"),
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

        # 提取标题（如果列表页没有提取到）
        if not video_info.get("title"):
            title_elem = soup.find("h1", class_=re.compile(r"watch-title"))
            if title_elem:
                video_info["title"] = title_elem.get_text(strip=True)

        # 提取观看数
        views_elem = soup.find(string=re.compile(r'\d[\d,]*\s*(?:次观看|views|观看)'))
        if views_elem:
            views_match = re.search(r'(\d[\d,]*)', views_elem)
            if views_match:
                video_info["views"] = int(views_match.group(1).replace(",", ""))

        # 提取点赞数
        likes_elem = soup.find(string=re.compile(r'\d[\d,]*\s*(?:点赞|likes|赞)'))
        if likes_elem:
            likes_match = re.search(r'(\d[\d,]*)', likes_elem)
            if likes_match:
                video_info["likes"] = int(likes_match.group(1).replace(",", ""))

        # 提取作者
        author_elem = soup.find("a", href=re.compile(r"/v/author/"))
        if author_elem:
            # 只提取作者名（第一个 span），避免包含发布时间
            author_span = author_elem.find("span", class_=re.compile(r"truncate"))
            if author_span:
                video_info["author"] = author_span.get_text(strip=True)
            else:
                video_info["author"] = author_elem.get_text(strip=True)

        # 提取发布时间
        time_elem = soup.find("time")
        if time_elem:
            video_info["release_date"] = time_elem.get("datetime", "") or time_elem.get_text(strip=True)

        # 提取视频地址（Base64 编码）
        # 网站使用动态变量名混淆，需要动态查找
        video_url = None
        scripts = soup.find_all("script")
        for script in scripts:
            text = script.get_text()
            # 查找 Base64 编码的 URL 模式：var _xxx='base64...', _yyy='base64...'
            # 匹配 atob() 调用中的 Base64 字符串
            base64_pattern = r"var\s+_\w+\s*=\s*'([A-Za-z0-9+/=\\]+)'\s*,\s*_\w+\s*=\s*'([A-Za-z0-9+/=\\]+)'"
            match = re.search(base64_pattern, text)
            if match and 'atob' in text:
                encoded_url1 = match.group(1).replace('\\u003D', '=')
                encoded_url2 = match.group(2).replace('\\u003D', '=')

                url1 = decode_base64(encoded_url1)
                url2 = decode_base64(encoded_url2)

                # 优先使用第一个 URL（通常是主地址）
                if url1 and url1.startswith('http'):
                    video_url = url1
                elif url2 and url2.startswith('http'):
                    video_url = url2
                break

        if not video_url:
            print(f"[WARN] 无法提取视频地址: {video_info.get('title', '')}")
            return None

        video_info["video_url"] = video_url
        video_info["video_type"] = "m3u8" if ".m3u8" in video_url else "mp4"

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

    def download_m3u8(self, url: str, filepath: str, referer: str) -> bool:
        """
        下载 M3U8 视频（使用 yt-dlp）

        Args:
            url: M3U8 URL
            filepath: 目标文件路径
            referer: Referer 头

        Returns:
            是否下载成功
        """
        if self._interrupted:
            return False

        try:
            import subprocess

            # 构建 yt-dlp 命令
            cmd = [
                "yt-dlp",
                "--referer", referer,
                "--user-agent", HEADERS['User-Agent'],
                "-o", filepath,
                "--no-warnings",
                "--quiet",
                "--progress",
                url
            ]

            print(f"[INFO] 使用 yt-dlp 下载 M3U8 视频...")

            # 执行 yt-dlp 命令
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )

            # 等待完成
            stdout, stderr = process.communicate()

            if process.returncode == 0:
                print(f"[INFO] yt-dlp 下载完成")
                return True
            else:
                print(f"[ERROR] yt-dlp 下载失败: {stderr[:500]}")
                return False

        except FileNotFoundError:
            print("[ERROR] 未找到 yt-dlp，请先安装 yt-dlp: pip install yt-dlp")
            return False
        except Exception as e:
            print(f"[ERROR] M3U8 下载异常: {e}")
            return False

    def download_video_with_refresh(self, video_info: Dict) -> bool:
        """
        下载视频（带 URL 刷新机制）

        Args:
            video_info: 视频信息字典

        Returns:
            是否下载成功
        """
        video_url = video_info.get("video_url")
        title = video_info.get("title", "untitled")
        video_id = video_info.get("video_id")
        detail_url = video_info.get("url", "")

        if not video_url:
            print(f"[WARN] 无视频地址，跳过下载: {title}")
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
        print(f"[INFO] URL: {video_url}")

        # 带重试的下载
        current_url = video_url
        for attempt in range(RETRY_COUNT):
            if self._interrupted:
                return False

            # 根据视频类型选择下载方式
            if video_info.get("video_type") == "m3u8":
                result = self.download_m3u8(current_url, filepath, detail_url)
            else:
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
                # 重新解析详情页获取新的视频 URL
                fresh_info = self.parse_detail_page(video_info)
                if fresh_info and fresh_info.get("video_url"):
                    current_url = fresh_info["video_url"]
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
        if self.category:
            print(f"[INFO] 分类/关键词: {self.category}")
        elif self.rank:
            print(f"[INFO] 排行榜: {self.rank}")
        else:
            time_desc = TIME_OPTIONS.get(self.time_filter, "")
            time_str = f" (时间: {self.time_filter})" if time_desc else ""
            print(f"[INFO] 排序方式: {self.sort}{time_str}")

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


def print_usage_guide():
    """打印使用指南"""
    script = os.path.basename(__file__)
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    91PinSe 视频爬虫                          ║
╚══════════════════════════════════════════════════════════════╝

📖 使用方法:

  1️⃣  抓取视频（仅获取元数据，不下载）
     python3 {script} --category 熟女 --page 3

  2️⃣  抓取并下载视频
     python3 {script} --category 熟女 --page 3 --download

  3️⃣  按排序方式抓取热门视频
     python3 {script} --sort hot --download
     python3 {script} --sort view --time week --download

  4️⃣  抓取排行榜视频
     python3 {script} --rank current-hot --download

  5️⃣  使用代理（需要代理服务运行中）
     python3 {script} --category 熟女 --download --proxy socks5://127.0.0.1:1080

📋 常用参数:
  --category <关键词>   按分类/标签筛选（如: 熟女、少妇、人妻、黑丝）
  --page <页数>         抓取前几页（默认: 分类模式3页）
  --download            下载视频文件
  --download-dir <目录>  指定下载目录（默认: ./91pinse_videos）
  --proxy <地址>        使用代理（如: socks5://127.0.0.1:1080）
  --sort <排序>         排序方式: latest/hot/score/view/like
  --time <时间>         时间筛选: all/today/week/month

💡 快速开始:
  python3 {script} --list-categories    # 查看所有可用分类
  python3 {script} --category 少妇 --page 2 --download

📌 注意: 默认不使用代理，如需代理请用 --proxy 参数指定
""".format(script=script))


def main():
    # 无参数运行时显示使用指南
    if len(sys.argv) == 1:
        print_usage_guide()
        sys.exit(0)

    parser = argparse.ArgumentParser(description="91PinSe 视频爬虫")
    parser.add_argument(
        "--proxy",
        type=str,
        default="",
        help="代理地址（如: socks5://127.0.0.1:1080）",
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
        default="latest",
        help="排序方式（默认: latest）",
    )
    parser.add_argument(
        "--time",
        type=str,
        choices=list(TIME_OPTIONS.keys()),
        default="all",
        help="时间筛选（默认: all）",
    )
    parser.add_argument(
        "--rank",
        type=str,
        choices=list(RANK_OPTIONS.keys()),
        help="排行榜类型（与 --sort 互斥）",
    )
    parser.add_argument(
        "--category",
        type=str,
        help="按关键词/标签筛选（如: 熟女、少妇、人妻、黑丝 等），支持任意关键词",
    )
    parser.add_argument(
        "--list-categories",
        action="store_true",
        help="列出预设分类关键词",
    )

    args = parser.parse_args()

    # 列出预设分类
    if args.list_categories:
        print("=" * 60)
        print("[INFO] 所有可用分类选项:")
        print("=" * 60)
        for category_name, options in CATEGORY_HELP.items():
            print(f"\n  {category_name}:")
            for key, desc in options.items():
                print(f"    {key:20s} {desc}")
        print("\n" + "-" * 60)
        print("[INFO] 预设分类关键词 (--category):")
        for i, cat in enumerate(PRESET_CATEGORIES, 1):
            print(f"  {i:2d}. {cat}")
        print(f"\n[INFO] 使用示例:")
        print(f"  python3 {os.path.basename(__file__)} --sort view --time week --download")
        print(f"  python3 {os.path.basename(__file__)} --rank current-hot --download")
        print(f"  python3 {os.path.basename(__file__)} --category 熟女 --page 3 --download")
        print("[INFO] 也可以使用任意自定义关键词")
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
    spider = PinSe91Spider(
        output_file=args.output,
        stream_output=args.stream_output,
        resume=not args.no_resume,
        seen_ids_file=args.seen_ids_file,
        download=args.download,
        download_dir=args.download_dir,
        sort=args.sort,
        time_filter=args.time,
        rank=args.rank,
        category=args.category,
    )

    # 分类模式下，--page 表示抓取前几页（默认 3 页）
    if args.category:
        max_page = args.page if args.page else 3
        print(f"[INFO] 分类模式: 抓取 '{args.category}' 前 {max_page} 页")
        if args.target_new:
            spider.crawl(max_page=max_page, target_new=args.target_new)
        else:
            spider.crawl(max_page=max_page)
    elif args.page:
        spider.crawl(max_page=args.page)
    elif args.target_new:
        spider.crawl(target_new=args.target_new)
    else:
        spider.crawl()


if __name__ == "__main__":
    main()
