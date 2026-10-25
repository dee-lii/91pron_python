# 小黄鸟爬虫（xiaohuangniao.me）

本脚本实现 SpiderFor91 的 **`crawler.v3`** stdin/stdout JSONL 协议，运行环境需预装 `requests`。

## 数据源现状

- 唯一栏目是 `hot-tweets`（默认）：首页“热门黄推内容”使用的 `GET /api/requestdb?type=hot-tweets&limit=N`。
- `/tweets`、`/search` 当前不可作为稳定列表源。
- API 数据直接带 Twitter 视频候选，`source_id` 使用原生 `tweetId`。
- 这是一个有限热门快照，不是真正的分页 API。脚本每个进程只抓取一次快照，再按 offset 分页。

## 启动与 job

```bash
python3 XiaoHuangNiao.py --job /absolute/path/to/job.json
```

```json
{
  "protocol": "crawler.v3",
  "task_id": "xhn-hot-20260929",
  "crawler_id": "xiaohuangniao",
  "feed_id": "hot-tweets",
  "work_dir": "/absolute/task/work",
  "config": {"limit": 50},
  "network": {"proxy_url": "http://127.0.0.1:7890"}
}
```

`protocol`、非空 `task_id`/`crawler_id`、`feed_id` 和绝对路径 `work_dir` 必填；`config` 与 `network` 必须是对象（可省略并采用 `{}`）。`config.limit` 是 1–1000 的整数，只控制首次源 API 请求希望抓取的数量；服务端可能自行限制返回数。它与每条 `discover` 命令的后端 `limit` 相互独立。v2 的 `config.type` 已由 `feed_id` 替代。

## stdin 命令示例

```jsonl
{"type":"discover","request_id":"req-1","cursor":null,"limit":10,"deadline_at":"2026-09-29T08:01:00Z"}
{"type":"resolve","request_id":"req-2","candidate":{"discovery_key":"tweet:1234567890","source_id":"1234567890","locator":{"id":"1234567890"}},"deadline_at":"2026-09-29T08:02:00Z"}
{"type":"stop","request_id":"req-3","reason":"source_exhausted","deadline_at":"2026-09-29T08:02:01Z"}
```

`discover` 返回 `page`；同一 API 快照由 `offset:N` cursor 继续，实际耗尽时 `next_cursor` 为 `null`。`resolve` 返回指定推文的 `item`；`stop` 返回 `stopped` 后退出。stdout 只包含协议 JSONL，每条命令恰好一个最终响应并保留原 `request_id`；日志走 stderr。

视频和封面各自使用嵌套媒体对象及下载头：

```json
{
  "media": {
    "type": "url",
    "url": "https://video.twimg.com/ext_tw_video/...mp4?tag=...",
    "headers": {
      "User-Agent": "...",
      "Referer": "https://x.com/",
      "Origin": "https://x.com",
      "Accept": "*/*"
    }
  },
  "thumbnail": {
    "type": "url",
    "url": "https://pbs.twimg.com/media/example.jpg",
    "headers": {
      "User-Agent": "...",
      "Referer": "https://x.com/",
      "Origin": "https://x.com",
      "Accept": "*/*"
    }
  }
}
```

## crawler.v3 行为

- 首个 `discover` 只请求一次热门 API，不探测媒体；列表快照和 cursor 重试结果在进程内保持稳定。
- API 结果只保留含视频的推文。标题继续清除 URL、电报推广、@提及、#标签及常见广告词，清洗为空时回退作者或 tweetId。
- `resolve` 只处理后端指定候选，并按码率从高到低对官方 mp4 做最小 Range 预检，允许回退到其他官方表示。
- 401/403、429、404/410、网络错误、API `success=false` 或结构错误会返回结构化 `error`，不会伪装为空成功；没有自动 HTTP 或爬虫重试。
- 不再使用 v2 的 `candidate_budget`、seen 文件、`limits`、`progress`/`done`。后端负责去重、新增目标、重试和整轮时间预算。
- API 请求、媒体预检以及随机 1–3 秒礼貌等待均受每条命令带时区的 `deadline_at` 约束。

## 字段与 caveat

API 常见字段包括 `tweetId`、`text`、`mediaUrls[]`、`extendedEntities.media[].video_info.variants`、封面地址、作者和 `viewCount`。推文详情页对游客可能返回 404，因此脚本不会依赖详情网页生成标题。

Twitter 直链带时效 token，可能因删除或封禁失效；后端应及时下载。服务端通常只返回少量轮换热门内容，适合定时增量任务。本脚本仅供学习交流，请遵守当地法律法规及站点规则。
