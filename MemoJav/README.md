# MemoJav 爬虫（crawler.v3）

面向 `memojav.org` 的单文件 `crawler.v3` 爬虫，只提供 `milf` 栏目（默认）。依赖运行环境预装 `requests` 和 `beautifulsoup4`；部署时只需复制 `MemoJav.py`。

## 运行示例

`/tmp/memojav-job.json`：

```json
{
  "protocol": "crawler.v3",
  "task_id": "memojav-20260929",
  "crawler_id": "memojav",
  "feed_id": "milf",
  "work_dir": "/tmp/memojav-work",
  "config": {},
  "network": {"proxy_url": "http://127.0.0.1:7890"}
}
```

```bash
mkdir -p /tmp/memojav-work
python3 MemoJav.py --job /tmp/memojav-job.json <<'JSONL'
{"type":"discover","request_id":"d1","cursor":null,"limit":20,"deadline_at":"2026-09-29T08:01:00Z"}
{"type":"resolve","request_id":"r1","candidate":{"discovery_key":"detail:ABF-375","source_id":"ABF-375","locator":{"id":"ABF-375","detail_url":"https://memojav.org/video/ABF-375"}},"deadline_at":"2026-09-29T08:02:00Z"}
{"type":"stop","request_id":"s1","reason":"target_reached","deadline_at":"2026-09-29T08:02:01Z"}
JSONL
```

示例中的截止时间必须替换为实际的、带时区且尚未到期的时间。

## 行为

- `discover` 仅访问 `/categories/milf/` 和后续 `page-N` 列表，不请求详情或媒体。
- 列表原生番号转为大写并作为稳定 `source_id`（例如 `ABF-375`）。游标为 `page:N:offset`，不会因单次 `limit` 截断而丢失同页剩余候选；同一游标重试使用进程内列表快照。
- `resolve` 只处理后端选中的候选，进入详情页读取最新标题、预告和封面。协议允许候选 `source_id` 与 `locator.id` 不同：响应原样保留候选 `source_id`，站点原生番号、详情标题清洗、列表元数据查询和 HLS 路径均使用 `locator.id`。
- 标题继续保留原逻辑：原生 locator 番号为 `ABF-375` 时，详情 `ABF-375 | Seduced by ...` 清洗为 `ABF-375 Seduced by ...`。
- 媒体优先 Range 预检完整 HLS `https://video10.memojav.net/stream/{ID}/master.m3u8`，404/不可播放时才预检详情页当前 `preview-vid`；认证、限流和网络故障不会被吞掉为“空成功”。每个 URL 最多请求一次，不自动重试。

媒体和封面均使用 v3 独立对象：

```json
{
  "media": {
    "type": "url",
    "url": "https://video10.memojav.net/stream/ABF-375/master.m3u8",
    "headers": {"User-Agent": "...", "Referer": "https://memojav.org/"}
  },
  "thumbnail": {
    "type": "url",
    "url": "https://memojav.org/poster.jpg",
    "headers": {"User-Agent": "...", "Referer": "https://memojav.org/"}
  }
}
```

无封面、作者等可选值时字段直接省略，不输出 `null`。

## v2 不兼容变更

- job 必须包含 `protocol`、`task_id`、`crawler_id`、`feed_id`、绝对 `work_dir`、对象类型的 `config` 和 `network`。
- 不再自主遍历整个分类，不再输出 `done`；stdin 命令驱动 `discover → page`、`resolve → item`，`stop → stopped` 后退出。
- 删除 `candidate_budget`、`target_new`、`seen_source_ids_file`、`limits` 和脚本端运行/页数上限。
- 旧 `media_url`、`thumbnail_url`、共享 `headers` 已由 `media`、`thumbnail` 各自的 URL/headers 对象取代。
- 去重、入库新增目标、整轮爬取时间和重试均由后端负责；脚本不维护 seen 文件，也不自动重试。

站点列表约有多页；脚本不使用固定页数上限。某页候选全部重复或页面为空时，只要存在有效的后续 `page-N` 链接，就返回空 `items` 并继续；没有下一页链接才表示耗尽。具有列表/分页容器的空页可正常继续或结束，无法识别为列表结构且没有分页链接的 HTML 则返回 `parse_failed`。仅供学习交流，请遵守当地法律法规和源站规则。
