# Pektino 爬虫（crawler.v3）

Pektino（原 Truvaze / Twitter 视频排行榜）的单文件 `crawler.v3` 爬虫，使用 Next.js REST API。运行环境需预装 `requests`；部署只需复制 `Pektino.py`。

## 栏目

栏目范围已从旧 `config.range` 移到 job 顶层 `feed_id`：

- `weekly`：周榜，默认。
- `daily`：日榜；API 不发送 `range` 参数。
- `monthly`：月榜。
- `all`：全部。

所有栏目固定 `sort=favorite`，同一 `url_cd` 在不同栏目使用同一个 `source_id`。

## 运行示例

`/tmp/pektino-job.json`：

```json
{
  "protocol": "crawler.v3",
  "task_id": "pektino-20260929",
  "crawler_id": "pektino",
  "feed_id": "weekly",
  "work_dir": "/tmp/pektino-work",
  "config": {
    "locale": "zh-CN",
    "per_page": 50,
    "is_anime_only": false,
    "min_time": 0,
    "max_time": 0
  },
  "network": {"proxy_url": "http://127.0.0.1:7890"}
}
```

```bash
mkdir -p /tmp/pektino-work
python3 Pektino.py --job /tmp/pektino-job.json <<'JSONL'
{"type":"discover","request_id":"d1","cursor":null,"limit":24,"deadline_at":"2026-09-29T08:01:00Z"}
{"type":"resolve","request_id":"r1","candidate":{"discovery_key":"detail:abc123","source_id":"abc123","locator":{"id":"abc123","url_cd":"abc123","media_urls":["https://video.twimg.com/ext_tw_video/example/pu/vid/720x1280/video.mp4"],"detail_url":"https://pektino.com/zh-CN/movie/abc123","title":"示例"}},"deadline_at":"2026-09-29T08:02:00Z"}
{"type":"stop","request_id":"s1","reason":"target_reached","deadline_at":"2026-09-29T08:02:01Z"}
JSONL
```

截止时间必须带时区且尚未到期。

## 配置

```json
{
  "locale": "zh-CN",
  "per_page": 50,
  "is_anime_only": false,
  "min_time": 0,
  "max_time": 0
}
```

- `locale`：详情页语言路径，默认 `zh-CN`。
- `per_page`：API 每页数量，整数 `1..200`，默认 `50`。
- `is_anime_only`：动漫过滤，必须是布尔值。
- `min_time` / `max_time`：秒数过滤，整数 `0..604800`；0 表示不限。
- `sort`、`range`、`max_pages` 不再是配置项；排序固定为 favorite，范围由 `feed_id` 指定，不设任意页数上限。

## 发现与解析

- `discover` 只访问 `/api/media` 列表，绝不预检媒体或批量请求详情。候选 locator 保存列表快照中的媒体备选和必要元数据，限制在 16 KiB。
- 分页游标为 `page:N:offset`；单次 `limit` 最多 100，不丢失同页余项。同一游标重试使用进程内快照。对象响应的 `currentPage` / `lastPage`（或 snake_case 等价字段）是分页依据：即使中间页为空或与前页重复，只要 `currentPage < lastPage`，仍返回下一页游标；到达 `lastPage` 才耗尽。缺少有效分页元数据的对象响应视为解析错误。顶层 JSON 数组没有续页契约，明确按“第一页即完整有限结果”处理，且不会尝试第二页。
- `resolve` 才对该候选的 Twitter MP4 做 Range 预检。列表地址不可用时，使用站点原生 `locator.id` 请求一次 `/api/media/{id}` 刷新地址，再按顺序预检尚未尝试的备选 URL。协议允许候选 `source_id` 与 `locator.id` 不同：响应原样保留候选 `source_id`，详情刷新和原生标题兜底使用 `locator.id`；`discover` 自身仍为原生候选生成相同的两者。
- 单一 URL 不重复请求，requests adapter 不配置重试。认证/限流/网络异常会返回协议错误，404 或内容明显不是媒体时可尝试下一个备选。

返回给后端的下载信息为：

```json
{
  "media": {
    "type": "url",
    "url": "https://video.twimg.com/.../video.mp4",
    "headers": {
      "User-Agent": "...",
      "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
      "Referer": "https://x.com/",
      "Origin": "https://x.com"
    }
  },
  "thumbnail": {
    "type": "url",
    "url": "https://pbs.twimg.com/...",
    "headers": {
      "User-Agent": "...",
      "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
      "Referer": "https://x.com/",
      "Origin": "https://x.com"
    }
  }
}
```

媒体和封面各自带完整下载头；无值的可选字段省略。

## 网络与 v2 不兼容变更

- Pektino API 始终 `trust_env=False` 直连，携带 `age_verified`、`site_lang` Cookie 和 `/{locale}` Referer。
- `network.proxy_url` **仅**用于 Twitter 媒体预检；返回的媒体对象包含 X 下载头，后端负责其下载网络策略。
- 不再输出 v2 `progress` / `done`，不读取 `candidate_budget`、`target_new`、seen 文件或 `limits`。
- 后端负责去重、新增目标、整轮时间限制和错误重试；脚本保持 stdin JSONL 会话直到收到 `stop`。

不使用 Selenium/Playwright，不下载媒体文件，不尝试姐妹站或镜像。仅供学习交流，请遵守当地法律法规和源站规则。
