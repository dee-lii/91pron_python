# 91Porny 爬虫（91porny.com）

本脚本实现 SpiderFor91 的 **`crawler.v3`** stdin/stdout JSONL 协议。它是单文件爬虫，运行环境需预装 `requests`、`beautifulsoup4`、`lxml`。

## 栏目

栏目由 job 顶层的 `feed_id` 选择，不再使用 `config.category`。

| feed_id | 名称 |
| --- | --- |
| `top-list` | 本月最热（默认） |
| `latest` | 最近更新 |
| `hd` | 高清视频 |
| `hot-list` | 当前最热 |
| `recent-favorite` | 最近加精 |
| `recent-rating` | 最近得分 |
| `nonpaid` | 非付费 |
| `ori` | 91 原创 |
| `long-list` | 10 分钟以上 |
| `longer-list` | 20 分钟以上 |
| `month-discuss` | 本月讨论 |
| `top-favorite` | 本月收藏 |

## 启动

```bash
python3 Porny91.py --job /absolute/path/to/job.json
```

完整 job 示例：

```json
{
  "protocol": "crawler.v3",
  "task_id": "porny91-20260929",
  "crawler_id": "porny91",
  "feed_id": "top-list",
  "work_dir": "/absolute/task/work",
  "config": {},
  "network": {"proxy_url": "http://127.0.0.1:7890"}
}
```

`protocol`、非空的 `task_id`/`crawler_id`、受支持的 `feed_id`、绝对路径 `work_dir` 均为必填；`config` 与 `network` 必须是对象（可省略并采用 `{}`）。代理会同时用于列表、详情请求。可选的 `config.base_url` 和 `config.headers` 主要用于部署或测试环境。

启动后脚本持续从 stdin 读取命令，每行一个 JSON。例如：

```jsonl
{"type":"discover","request_id":"req-1","cursor":null,"limit":24,"deadline_at":"2026-09-29T08:01:00Z"}
{"type":"resolve","request_id":"req-2","candidate":{"discovery_key":"video:123","source_id":"123","locator":{"id":"123","detail_url":"https://91porny.com/video/view/123"}},"deadline_at":"2026-09-29T08:02:00Z"}
{"type":"stop","request_id":"req-3","reason":"target_reached","deadline_at":"2026-09-29T08:02:01Z"}
```

对应 stdout 只会输出协议 JSONL：`discover` 得到一个 `page`，`resolve` 得到一个 `item`，`stop` 得到 `stopped` 并以 0 退出。每个命令恰好一个最终响应，`request_id` 原样返回；日志只写 stderr。

成功解析的视频使用嵌套媒体对象，视频与封面分别携带自己的下载头：

```json
{
  "type": "item",
  "request_id": "req-2",
  "discovery_key": "video:123",
  "source_id": "123",
  "title": "示例标题",
  "detail_url": "https://91porny.com/video/view/123",
  "media": {
    "type": "url",
    "url": "https://cdn.example/index.m3u8?t=...",
    "headers": {"User-Agent": "...", "Referer": "https://91porny.com/"}
  },
  "thumbnail": {
    "type": "url",
    "url": "https://cdn.example/poster.jpg",
    "headers": {"User-Agent": "...", "Referer": "https://91porny.com/"}
  }
}
```

源站返回 401/403、429、404/410、网络故障或页面无法解析时会输出结构化 `error`。脚本不自动重试请求；是否重试以及等待时间由后端决定。

## crawler.v3 行为

- `discover` 只读取列表页，不请求详情或探测媒体。
- 页码与页内 offset 都写入 cursor；同一个 cursor 重试使用任务内缓存的同一列表快照，不会丢掉超出本次 `limit` 的卡片。
- 没有固定最大页数、候选预算、seen 文件、`progress` 或 `done` 事件。后端负责去重、新增目标和整轮时间预算。
- `resolve` 只解析指定候选，并实时获取带时效参数的 m3u8；请求及礼貌延时都受该命令带时区的 `deadline_at` 限制。

## 站点备忘

- 列表：`/video/category/{feed_id}`，后续页为 `/{page}`；卡片限定为 `div.video-elem`。
- 详情：`/video/view/{id}`；媒体通常在 `video#video-play[data-src]`，也兼容 `src`、`data-url` 和嵌套 `source`。
- `source_id` 是站点原生 video id，不包含栏目，因此同一视频跨栏目身份稳定。
- m3u8 的 `t`/`m` 参数会过期，后端收到结果后应尽快下载。
- 脚本保留 1–3 秒随机礼貌间隔；请遵守当地法律法规及站点规则。
