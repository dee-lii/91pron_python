# Xhotlist 爬虫（xhotvideo.com）

本脚本实现 SpiderFor91 的 **`crawler.v3`** stdin/stdout JSONL 协议。原域名 `top.xhotlist.com` 已跳转到 `xhotvideo.com`。运行环境需预装 `requests`、`beautifulsoup4`、`lxml`。

## 栏目

- `latest`：最新列表，默认栏目。
- `tag`：标签筛选；选择此栏目时必须提供非空 `config.tag`。

`config.tag` 在 `latest` 栏目中不会暗中改变列表入口。

## 启动与 job

```bash
python3 Xhotlist.py --job /absolute/path/to/job.json
```

最新列表 job：

```json
{
  "protocol": "crawler.v3",
  "task_id": "xhot-latest-20260929",
  "crawler_id": "xhotlist",
  "feed_id": "latest",
  "work_dir": "/absolute/task/work",
  "config": {},
  "network": {}
}
```

标签列表 job：

```json
{
  "protocol": "crawler.v3",
  "task_id": "xhot-anime-20260929",
  "crawler_id": "xhotlist",
  "feed_id": "tag",
  "work_dir": "/absolute/task/work",
  "config": {"tag": "anime"},
  "network": {"proxy_url": "http://127.0.0.1:7890"}
}
```

`protocol`、非空 `task_id`/`crawler_id`、`feed_id` 和绝对路径 `work_dir` 必填；`config`、`network` 必须是对象（可省略并采用 `{}`）。可选 `config.base_url`、`config.headers` 主要供部署或测试使用。

## stdin 命令示例

```jsonl
{"type":"discover","request_id":"req-1","cursor":null,"limit":24,"deadline_at":"2026-09-29T08:01:00Z"}
{"type":"resolve","request_id":"req-2","candidate":{"discovery_key":"video:fzuhnhnazgqsbx3-","source_id":"fzuhnhnazgqsbx3-","locator":{"id":"fzuhnhnazgqsbx3-","detail_url":"https://xhotvideo.com/video/fzuhnhnazgqsbx3-"}},"deadline_at":"2026-09-29T08:02:00Z"}
{"type":"stop","request_id":"req-3","reason":"target_reached","deadline_at":"2026-09-29T08:02:01Z"}
```

stdout 只输出 JSONL：`page`、`item`、结构化 `error` 或最终 `stopped`。每条命令只有一个最终响应且保留原 `request_id`；日志只写 stderr。`stop` 后立即正常退出。

媒体和封面使用独立的嵌套 URL 对象。Twitter CDN 下载头不会放在 item 顶层：

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
    "url": "https://pbs.twimg.com/ext_tw_video_thumb/...jpg",
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

- `discover` 只读 `/videos` 或 `/videos/tag/{tag}` 列表，不请求详情、不探测 CDN。
- cursor 保存源页和页内 offset；任务内缓存列表快照，重试相同 cursor 得到稳定结果，且 `limit` 不会截断丢失页内剩余项。
- `resolve` 才请求单个详情页，收集官方 `video.twimg.com` 候选，并逐个执行最小 Range 预检；第一个可读表示被返回。
- 401/403、429、404/410、网络错误和解析错误不会被当作空成功；脚本不自动重试，后端依据结构化 `error` 决定重试。
- 不再支持 v2 的 `candidate_budget`、seen 文件、`limits`、`config.max_pages`、`progress`/`done`。后端负责去重、新增目标、重试和整轮时间预算。
- 每次网络操作和随机 1–3 秒礼貌等待均受命令的带时区 `deadline_at` 限制。

## 站点备忘

- 最新页：`/videos`、`/videos/page/{n}`；标签页：`/videos/tag/{tag}`、后续 `/page/{n}`。
- 卡片是 `a.video-card`，详情为 `/video/{id}`。
- `source_id` 使用站点原生 id，与 feed 无关，跨栏目保持一致。
- 详情可能保留多个 Twitter CDN 地址；直链 token 可能过期，原推文删除或封禁也可能导致 403。
- 本脚本仅供学习交流，请遵守当地法律法规及站点规则。
