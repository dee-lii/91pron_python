# 91 视频爬虫集合

包含多个视频网站的独立爬虫脚本。

## 爬虫列表

| 脚本 | 目标网站 | 状态 |
|------|----------|------|
| `spider_91porn.py` | 91porn.com | ✅ 可用 |
| `spider_91pinse.py` | 91pinse.com | ✅ 可用 |
| `spider_truvaze.py` | truvaze.com | ✅ 可用 |

---

## 91PinSe 爬虫 (`spider_91pinse.py`)

爬取 [91pinse.com](https://91pinse.com/) 网站的视频。

### 功能特性

- ✅ **独立运行**：无需外部依赖（除 Python 库）
- ✅ **完整下载**：使用 yt-dlp 下载 M3U8 视频
- ✅ **断点续爬**：自动跳过已抓取和已下载的视频
- ✅ **多种排序**：支持最新、热门、排行榜等多种排序方式
- ✅ **流式输出**：支持 JSONL 格式供管道使用
- ✅ **代理支持**：支持 SOCKS5/HTTP 代理
- ✅ **容错机制**：自动重试、随机延迟

### 快速开始

```bash
# 安装依赖
pip install requests beautifulsoup4 lxml

# 安装 yt-dlp（用于下载 M3U8 视频）
pip install yt-dlp

# 全量爬取并下载视频
python3 spider_91pinse.py --download

# 抓取并下载 10 个新视频
python3 spider_91pinse.py --target-new 10 --download

# 指定排序方式
python3 spider_91pinse.py --sort hot --download

# 使用排行榜
python3 spider_91pinse.py --rank month-hot --download

# 使用代理
python3 spider_91pinse.py --proxy socks5://127.0.0.1:1080 --download
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--proxy URL` | 代理地址（默认: socks5://127.0.0.1:1080） |
| `--page N` | 单页调试模式，只抓取第 N 页 |
| `--target-new N` | 目标新视频数量，达到后停止 |
| `--output FILE` | 输出文件路径（默认: `91pinse_videos.json`） |
| `--stream-output` | 流式输出模式（JSONL 格式） |
| `--no-resume` | 禁用断点续爬 |
| `--download` | 下载视频文件 |
| `--download-dir DIR` | 视频下载目录（默认: `./91pinse_videos`） |
| `--sort TYPE` | 排序方式：`latest`（最新）、`hot`（热门） |
| `--rank TYPE` | 排行榜：`current-hot`、`month-hot`、`month-favorite`、`recently-featured` |

### 输出格式

```json
[
  {
    "video_id": "439002",
    "title": "视频标题",
    "thumbnail": "https://cdn-image.fplayer.cc/images/xxx.webp",
    "url": "https://91pinse.com/v/439002",
    "duration": "0:01:08",
    "views": 12345,
    "author": "作者名",
    "video_url": "https://hls-v2.jfly.xyz/v/video.m3u8?...",
    "video_type": "m3u8"
  }
]
```

### 技术细节

- **列表页**：解析 `/v/` 路径，支持分页 `?page=N`
- **详情页**：动态查找 Base64 编码的视频地址（变量名混淆）
- **下载**：使用 yt-dlp 下载 M3U8 流（支持 .jpg 扩展名的分片）
- **去重**：基于 `video_id` 去重
- **延迟**：列表页 3-6 秒，详情页 2-5 秒随机延迟

---

## 91Porn 爬虫 (`spider_91porn.py`)

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或手动安装：
```bash
pip install requests beautifulsoup4 lxml
```

### 2. 运行爬虫

```bash
# 全量爬取并下载视频（推荐）
python3 spider_91porn.py --download

# 抓取并下载 10 个新视频后停止
python3 spider_91porn.py --target-new 10 --download

# 指定下载目录
python3 spider_91porn.py --download --download-dir ./my_videos

# 单页调试模式
python3 spider_91porn.py --page 1 --download

# 仅抓取元数据（不下载视频）
python3 spider_91porn.py

# 自定义输出文件
python3 spider_91porn.py --output my_videos.json

# 流式输出模式（JSONL 格式）
python3 spider_91porn.py --stream-output > output.jsonl

# 禁用断点续爬
python3 spider_91porn.py --no-resume
```

### 3. 使用代理

```bash
# SOCKS5 代理
ALL_PROXY=socks5://127.0.0.1:1080 python3 spider_91porn.py

# HTTP 代理
HTTP_PROXY=http://127.0.0.1:8080 HTTPS_PROXY=http://127.0.0.1:8080 python3 spider_91porn.py
```

## 输出格式

默认输出为 JSON 文件 `91porn_videos.json`，结构如下：

```json
[
  {
    "viewkey": "xxx",
    "source_id": "12345",
    "title": "视频标题",
    "thumbnail": "https://...",
    "url": "https://91porn.com/view_video.php?viewkey=xxx",
    "mp4_url": "https://...mp4"
  }
]
```

## 命令行参数

| 参数 | 说明 |
|------|------|
| `--page N` | 单页调试模式，只抓取第 N 页 |
| `--target-new N` | 目标新视频数量，达到 N 个后停止 |
| `--output FILE` | 输出文件路径（默认: `91porn_videos.json`） |
| `--stream-output` | 流式输出模式（每行一个 JSON，供管道使用） |
| `--no-resume` | 禁用断点续爬 |
| `--seen-viewkeys-file FILE` | 指定已知 viewkey 文件 |
| `--download` | 下载视频文件（使用标题作为文件名） |
| `--download-dir DIR` | 视频下载目录（默认: `./91porn_videos`） |

## 下载功能说明

### 基本用法

```bash
# 下载视频到默认目录 ./91porn_videos
python3 spider_91porn.py --download

# 下载到指定目录
python3 spider_91porn.py --download --download-dir /path/to/videos
```

### 下载特性（复用原仓库逻辑）

- ✅ **标题命名**：视频文件使用标题作为文件名（自动清理非法字符）
- ✅ **原子下载**：先下载到 `.part` 临时文件，完成后 `rename`，避免文件损坏
- ✅ **URL 刷新机制**：下载失败时自动重新获取视频 URL（视频 URL 含时效性 token）
- ✅ **Cookie 预热**：下载前先访问列表页获取 warm cookies，提高成功率
- ✅ **重试策略**：最多 3 次重试，针对 HTTP 403/404/410/429/5xx 等错误自动刷新 URL
- ✅ **断点续传**：自动跳过已下载的文件
- ✅ **进度显示**：实时显示下载进度和大小
- ✅ **中断处理**：Ctrl+C 中断时自动清理临时文件

### URL 刷新机制（原仓库核心逻辑）

视频直链包含时效性 token（`e` 参数为过期时间戳），会过期。脚本实现了原仓库的 URL 刷新机制：

1. 下载失败时，判断是否需要刷新 URL
2. 需要刷新时，重新请求详情页获取新的视频 URL
3. 刷新前先进行 Cookie 预热
4. 验证新 URL 的 source_id 一致性
5. 使用新 URL 重试下载

**触发刷新的错误类型**：
- HTTP 403, 404, 410, 429, 5xx
- 网络错误：timeout, connection reset, unexpected eof

### 文件命名规则

- 使用视频标题作为文件名
- 自动移除非法字符：`<>:"/\|?*`
- 自动截断过长的文件名（最大 200 字符）
- 自动添加 `.mp4` 扩展名

### 示例输出

```
[INFO] 开始下载: 某个视频标题
[INFO] URL: https://...mp4
[INFO] 下载进度: 100.0% (15.2/15.2 MB)
[INFO] 下载完成: 某个视频标题.mp4 (15.2 MB)

# URL 过期时的自动刷新
[INFO] 下载失败: 403 Forbidden
[INFO] 尝试刷新 URL (第 1/3 次)...
[INFO] 获取到新 URL: https://...mp4?new_token=xxx
[INFO] 下载完成: 某个视频标题.mp4 (15.2 MB)
```

## 注意事项

1. **地域限制**：目标网站可能有地域限制，请确保网络可达
2. **反爬机制**：脚本已有 Cloudflare 检测和重试逻辑，但不保证长期有效
3. **网站改版**：脚本依赖特定的 HTML 结构，如果网站改版需要更新解析逻辑
4. **合理使用**：请遵守相关法律法规，合理使用爬虫

## 技术细节

- **列表页**：抓取月度热门分类
- **详情页**：解析 `strencode2` 函数获取真实 MP4 地址
- **去重**：基于 `viewkey` 去重
- **延迟**：列表页 3-6 秒，详情页 2-5 秒随机延迟
- **重试**：最多 3 次重试，基础延迟 5 秒

## 原始项目

本脚本提取自 [nianzhibai/91](https://github.com/nianzhibai/91) 项目，原项目包含完整的视频站点功能（Go 后端 + React 前端 + 云盘存储）。
