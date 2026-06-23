# 项目说明

这是一个视频网站爬虫集合项目，包含多个独立的 Python 爬虫脚本。

## 技术栈

- Python 3
- 依赖：见 requirements.txt
- 虚拟环境：venv/

## 爬虫列表

| 脚本 | 目标网站 |
|------|----------|
| `spider_91porn.py` | 91porn.com |
| `spider_91pinse.py` | 91pinse.com |
| `spider_truvaze.py` | truvaze.com |

## 项目结构

```
.
├── spider_91porn.py      # 91porn 爬虫
├── spider_91pinse.py     # 91pinse 爬虫
├── spider_truvaze.py     # truvaze 爬虫
├── requirements.txt      # Python 依赖
├── 91porn_videos/        # 91porn 下载目录
├── 91porn_videos.json    # 91porn 视频元数据
├── truvaze_videos/       # truvaze 下载目录
└── truvaze_videos.json   # truvaze 视频元数据
```

## 常用命令

```bash
# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 运行爬虫
python spider_91porn.py
python spider_91pinse.py
python spider_truvaze.py
```

## 注意事项

- 爬虫使用 yt-dlp 下载 M3U8 视频
- 支持断点续爬（自动跳过已下载视频）
- 支持代理配置（SOCKS5/HTTP）
- 有随机延迟避免被封
