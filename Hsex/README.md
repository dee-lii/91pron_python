# Hsex — crawler.v3

面向 <https://hsex.icu/> 的独立单文件爬虫。依赖 Python 3、`requests` 和 `beautifulsoup4`；使用标准库 `html.parser`，不需要 lxml、浏览器或 JavaScript 执行环境。

```bash
python3 -m pip install requests beautifulsoup4
python3 /absolute/path/Hsex.py --job /absolute/path/job.json
```

仅实现持久化 `crawler.v3` JSONL 协议，不是直接下载器。脚本可单独复制到任务目录运行，不依赖本目录 README、测试或其他爬虫。

## 任务配置

```json
{
  "protocol": "crawler.v3",
  "task_id": "task-001",
  "crawler_id": "hsex",
  "feed_id": "latest",
  "work_dir": "/absolute/task/work",
  "config": {},
  "network": {}
}
```

`protocol`、`task_id`、`crawler_id`、`feed_id`、绝对路径 `work_dir` 必填。`config` / `network` 可省略，但提供时必须为对象。`network.proxy_url` 会用于所有源站 HTTP(S) 请求；启动时也同步到大小写 HTTP(S)_PROXY 环境变量。没有显式代理时采用 requests 的环境代理设置。

栏目只通过 `feed_id` 选择，**不使用 `config.category`**：

| feed_id | 栏目 | 列表路径 |
| --- | --- | --- |
| `latest` | 最新（默认） | `/list-N.htm` |
| `weekly` | 本周最热 | `/top7_list-N.htm` |
| `monthly` | 本月最热 | `/top_list-N.htm` |
| `five-min` | 5 分钟以上 | `/5min_list-N.htm` |
| `long` | 长视频 | `/long_list-N.htm` |
| `hot` | 当前最热 | `/hot_list-N.htm` |

这些路由来自站点导航。当前真实列表/分页验证只覆盖 `latest`，其他栏目有离线路径测试，但尚未逐一在线验证。

支持的可选 `config`：

- `base_url`：默认 `https://hsex.icu`。必须是无凭据的 HTTP(S) **origin**，不可包含路径、查询或 fragment；允许尾部 `/`。可指向本地测试服务。源站请求和分页均受该 origin 约束。
- `media_headers`：显式覆盖/补充返回给后端的视频下载头。
- `thumbnail_headers`：独立覆盖/补充封面下载头。不会继承 `media_headers`。

下载头对象最多 64 个字段；头名、值长度及 CR/LF/NUL 均按协议校验，合并默认 User-Agent 后也不得超过 64 个头。不要配置来源不明的 Cookie 或密钥：显式配置的头会随对应下载对象交给后端，对该媒体 URL 使用，而不保证 URL 属于源站同域。脚本不会从源站 Session 自动复制 Cookie、Authorization 等机密到 CDN；不支持源站登录头配置。

默认两个下载对象均仅携带公开浏览器 `User-Agent`，**没有 `Referer` 或 `Origin`**。这是基于源站 `meta referrer=no-referrer` 及独立 HLS 清单连通性验证，不合成 CDN 地址，不切换 CDN，也不无证据添加防盗链头。

不设置爬虫侧整轮候选数、页数、解析次数或时间预算。后端负责整轮去重、筛选、时限、重试和下载。

## JSONL 交互

stdin 每行一个 UTF-8 JSON 对象；stdout 只输出协议 JSON、逐行立即刷新，日志/错误堆栈写 stderr。一次进程可连续处理多条命令，命令之间长期等待不会主动退出或输出内容。

```jsonl
{"type":"discover","request_id":"d1","cursor":null,"limit":24,"deadline_at":"2099-01-01T00:00:00Z"}
{"type":"resolve","request_id":"r1","candidate":{"discovery_key":"video:101","source_id":"101","locator":{"id":"101"}},"deadline_at":"2099-01-01T00:00:00Z"}
{"type":"stop","request_id":"s1","reason":"target_reached","deadline_at":"2099-01-01T00:00:00Z"}
```

- `discover` → `page`：只读列表，最多返回 `limit` 条（1–100），不请求详情或探测媒体。候选 `source_id` 为原生数字 ID，跨栏目统一 `discovery_key=video:ID`，`locator={"id":"ID"}`。
- `resolve` → `item`：仅请求选定 ID 的 `/video-ID.htm`。URL 由 `locator.id` 推导，忽略调用者传入的其他 locator URL，避免任意抓取；存在 `og:url` 时校验详情身份。保留候选原有 `source_id`，即使它与 `locator.id` 不同。
- `stop` → `stopped`：原样回传 request_id 后正常退出 0，不处理后续输入。
- 响应只使用协议字段；未获取的可选元数据省略，不填 null。只有 `next_cursor` 可以为 null。不推断/新建标签，当前省略 `tags`。
- 非法 JSON、重复键、非对象、超长输入或其他命令错误会返回 `error`，之后仍可接收 `stop`。无法恢复有效 request_id 时使用 `invalid-request`。单行不超过 1 MiB，stdout 总计不超过 64 MiB；达到总输出上限会结束运行，不继续输出越界内容。EOF 未收到 stop 视为异常结束。

### 分页与重试

解析 `.row.body .thumbnail` 的直接子链接，不把相关区域/推荐链接当候选。标题、CSS background-image 封面、`var.duration` 和作者从列表缓存用于元数据回退。

以 `ul.pagination1` 中 **文本恰为 `▶`** 的链接作为下一页；检查当前 `li.active`、同源、相同栏目路径及页码前进。上下重复分页必须一致。实际链接目标（包括查询参数）保存在任务内，不假定下一页一定是 N+1，不从最大页码猜测，不硬编码站点末页。

`page:N:offset` 游标保留页内剩余候选。已读取页面按任务内快照缓存，相同游标重试保持相同内容；跨页重叠 ID 去重，但完全重复页或带合法结构的空页仍沿实际下一页继续。只有有效列表没有下一页时才返回 `next_cursor:null`。HTTP 404 列表返回源站级 `not_found`，不伪装为正常耗尽；未知/挑战 HTML 返回 `parse_failed`。

快照和显式下一页 URL 存于进程内存，不落盘；跨进程恢复不会保留旧列表快照。对不断变化的源站，重新启动的列表内容可能变化；持久去重由后端完成。

### 详情、下载与截止时间

详情读取 `video#video-play source#video-source[src]` 的绝对 HTTP(S) 地址。除 HTML 属性实体解码外，媒体 URL 的签名路径、编码、查询均原样保留。标题优先面板标题、再 `og:title`、最后缓存列表标题；作者、时长、描述读取对应 meta；封面依次使用 video poster、og:image、缓存列表封面。元数据按协议 UTF-8 字节上限截断。

爬虫只返回嵌套 `media` / `thumbnail` URL 对象，不下载清单、分片或视频，不做媒体连通性探测。需要后端在获取新鲜详情后尽快下载签名 URL。

每条 discover/resolve 均要求带时区的绝对 `deadline_at`，整个操作（网络、HTML 解析、候选生成、元数据和完整响应 JSON 序列化）在同一个 deadline 下运行，公开 Python API 也受此限制；预留 50 ms 响应时间。命令 worker 只修改隔离的事务状态，只有调用线程在截止时间内收到完整结果后才发布 pages / rows / next URL 快照。超时后立即停止等待并返回错误，晚完成的 worker 无法提交缓存。serve_job 直接写入 worker 已准备的 JSONL，不在主线程重复序列化成功响应。

同一爬虫最多保留一个未完成的操作 worker；若过期解析仍在结束中，新 discover/resolve 只能在自己的 deadline 内等待，不能累积并发解析 worker；stop 不等待该锁。另有 8 MiB HTML 体积上限和 20,000 个 `<` 标记的结构复杂度保护，防止大量空标签造成昂贵 DOM 构造；这些是解析安全限制，不是候选数或页数预算。超时的 Python 线程不能被强制杀死，可能继续消耗少量 CPU 至解析结束；过期时它不能再发起网络请求，也不能发布快照。已经阻塞的底层 DNS/socket 也可能稍后才退出。

请求间有固定 0.25 秒最小间隔，共享请求间隔状态受锁保护，等待与每次网络尝试/读取均受取消信号和 deadline 限制。传输层无自动重试，失败交回后端。源站重定向仅允许同 origin、同内容路径，最多 10 次。

错误码：`401/403 → auth_required`（源站级、不重试）；`429 → rate_limited`（源站级、可重试，读取 Retry-After）；`404/410 → not_found`；网络/其他 HTTP 错误 → `source_unavailable`；结构或媒体地址无法解析 → `parse_failed`。discover 错误始终为 source；普通详情失败为 item。过期命令使用协议允许的 `source_unavailable`，不输出协议未定义的 timeout 错误码。

## 验证范围

- 专用离线测试：`tests/test_hsex_protocol_v3.py`；合成最小结构，不收录完整抓取页面；HTTP 模拟和 loopback 服务，不访问真实源站/CDN。
- 已保存公开页面验证：最新第一页/第二页/末页的列表选择器、重叠候选、分页及详情原生 HLS/封面/时长可解析；测试实现阶段未新增真实站点请求。
- 父任务独立网络验证：详情元数据可读取，原生 HLS playlist 在无 Referer/Origin、公开 UA 条件下返回 HTTP 200、`application/vnd.apple.mpegurl` 和 `#EXTM3U`（1186 字节）。**只验证了元数据和清单连通性，未下载媒体分片或完整视频。**

运行整个仓库的离线回归：

```bash
python3 -B -m unittest discover -s tests -v
```

Python 接口：`CrawlerV3(job)`、`discover(command) -> {items,next_cursor}`、`resolve(command) -> item_fields`、`serve_job(job_path)`、`ProtocolError.fields`；兼容别名 `Crawler` / `SourceError`。
