# KanAV 爬虫（crawler.v3）

面向 `kanav.ad` 的单文件 `crawler.v3` 爬虫。依赖运行环境预装 `requests`、`beautifulsoup4`、`lxml`（SOCKS 代理另需 PySocks）。脚本部署时只需复制 `Kanav.py`，不依赖同目录文件。

## 栏目

- `home`（默认）：首页精选，仅首页一页，保持旧脚本默认的 home-only 行为。
- `category`：分类分页；分类由 `config.type_id` 指定，默认 `1`（中文字幕）。

`crawler.v2` 的 `config.home_only` 已删除，栏目必须用 job 顶层 `feed_id` 选择。

## 运行示例

`/tmp/kanav-job.json`：

```json
{
  "protocol": "crawler.v3",
  "task_id": "kanav-20260929",
  "crawler_id": "kanav",
  "feed_id": "category",
  "work_dir": "/tmp/kanav-work",
  "config": {"type_id": "1"},
  "network": {"proxy_url": "http://127.0.0.1:7890"}
}
```

启动后，命令通过 stdin 逐行发送；以下时间应换成实际的、带时区且尚未到期的截止时间：

```bash
mkdir -p /tmp/kanav-work
python3 Kanav.py --job /tmp/kanav-job.json <<'JSONL'
{"type":"discover","request_id":"d1","cursor":null,"limit":24,"deadline_at":"2026-09-29T08:01:00Z"}
{"type":"resolve","request_id":"r1","candidate":{"discovery_key":"detail:123","source_id":"123","locator":{"id":"123","detail_url":"https://kanav.ad/index.php/vod/play/id/123/sid/1/nid/1.html"}},"deadline_at":"2026-09-29T08:02:00Z"}
{"type":"stop","request_id":"s1","reason":"target_reached","deadline_at":"2026-09-29T08:02:01Z"}
JSONL
```

`discover` 只读列表页，返回轻量候选和确定性的 `page:N:offset` 游标；同一游标在进程内使用已缓存页面快照，重试结果稳定。`resolve` 仅解析指定候选的 `player_aaaa`，兼容明文、percent 编码和 base64(percent URL) 的播放地址。

成功解析的媒体形状为：

```json
{
  "type": "item",
  "request_id": "r1",
  "discovery_key": "detail:123",
  "source_id": "123",
  "title": "标题",
  "media": {
    "type": "url",
    "url": "https://cdn.example/video.m3u8",
    "headers": {"User-Agent": "...", "Referer": "https://kanav.ad/"}
  },
  "thumbnail": {
    "type": "url",
    "url": "https://kanav.ad/upload/cover.jpg",
    "headers": {"User-Agent": "...", "Referer": "https://kanav.ad/"}
  }
}
```

视频与封面各自携带下载头；无值的可选字段会省略。

## v2 不兼容变更

- 不再自主连续爬取，不再输出 `progress` / `done`；进程持续等待 `discover`、`resolve`、`stop`。
- 删除 `candidate_budget`、`target_new`、`seen_source_ids_file`、`limits`、页数上限等 v2 控制项。
- `media_url` / `thumbnail_url` / 通用 `headers` 改为独立的 `media` / `thumbnail` 对象。
- 脚本和 HTTP adapter 不做自动重试；认证、限流、404、网络和解析失败作为协议 `error` 返回，由后端决定是否重试。
- 去重、新增目标和整轮时间限制由后端负责；本脚本不设任意 `MAX_PAGES`。分类页即使整页内容重复或为空，只要页面仍提供有效的下一页链接，就返回空 `items` 和下一页游标；缺少下一页链接才视为实际耗尽。无法识别为列表结构且没有有效分页链接的 HTML 会报 `parse_failed`，不会伪装成空成功。

## 站点说明

- 首页：`/`
- 分类第一页：`/index.php/vod/type/id/{type_id}.html`
- 分类后续页：`/index.php/vod/type/id/{type_id}/page/{page}.html`
- 播放页：`/index.php/vod/play/id/{vod_id}/sid/1/nid/1.html`
- `discover` 产生的 `source_id` 使用站点原生数字 vod id，跨栏目保持一致。协议上 `source_id` 与 `locator.id` 不要求相等：`resolve` 会原样保留候选提供的 `source_id`，并仅使用 `locator.id` 校验播放器、查询列表元数据和生成站点原生兜底标题。

仅供学习交流，请遵守当地法律法规和源站规则。
