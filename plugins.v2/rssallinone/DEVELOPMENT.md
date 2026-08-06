# RSS一条龙开发说明

本文档是 RSS一条龙插件的开发交接文档。新的开发者或 AI 应先阅读本文档，再阅读 `README.md`、`MoviePilot_ReelHarbor_V1_plugin_prompt.md` 和相关测试。本文档描述的是当前实现和已经确认的业务约束，不是一个可以随意改写的设计草案。

## 1. 项目定位

RSS一条龙是 MoviePilot V2 插件，负责把以下流程串起来：

```text
PT/RSS
  -> RSS 解析、去重、筛选
  -> 使用 MoviePilot 已配置的 qB 节点添加任务
  -> 按 RSS 任务规则修改 qB 源文件和目录名称
  -> MoviePilot 识别媒体并生成 QB 管理卡片
  -> qB 完成回调
  -> 入库开关决定是否进入入库管理
  -> 本地库存逐文件对比
  -> 用户加入待入库
  -> 创建硬链接
  -> CD2 上传任务监控
  -> Emby 扫库完成回调
  -> 恢复外部开关
```

当前版本：`0.13.8`。

插件中的“入库”不是 MoviePilot 通常意义上的转移入库，也不是上传到云盘。这里的入库是：

1. 根据 MoviePilot 命名计划生成目标相对路径。
2. 从 qB 源文件创建同盘硬链接。
3. 硬链接目录由 CloudDrive2 自动备份。
4. 插件只通过 CD2 gRPC 查询和监控上传任务，不调用 CD2 备份 API。

## 2. 不可破坏的业务约束

以下约束来自用户确认和 V1 行为，修改代码时必须保持：

- 库存检查只读取本地文件系统，不调用 MoviePilot 或 Emby 的媒体库接口。
- 库存最终只比较 `.strm` 文件；qB 下载源文件不是库存。
- 库存目录优先按分类和 TMDB ID 定位，再使用 MoviePilot 命名计划逐文件匹配。
- 电影和剧集分类默认由 MoviePilot 识别，但必须允许用户手动指定分类。手动分类优先于自动分类，并影响库存路径、硬链接路径和后续命名。
- 纪录片在当前 MoviePilot 配置中属于剧集，不要自行改成电影。
- qB 管理只识别已保存 RSS 任务指定的下载器、分类组合，不扫描所有 qB 任务。
- RSS 添加到 qB 时只保留 RSS 任务设置的分类，不添加 MoviePilot 内部标签。
- RSS 完成后的主流程依赖 qB 完成回调；qB 刷新识别只是人工兜底，不应恢复成周期性全量轮询。
- RSS 源文件命名和硬链接目标命名是两套独立规则：
  - RSS 任务的“重命名”和“添加中文标题”修改 qB 源文件/目录。
  - MoviePilot 命名格式和自定义识别词生成硬链接目标及 `.strm` 目标。
- `彩虹岛`实时硬链接链路默认关闭。V1 仍运行时不能启动插件侧实时硬链接。
- CD2 发生真实传输、风控、任务匹配超时等异常时，保留 qB 源文件，删除本轮新建的硬链接，并让卡片回退。
- 待入库队列一次只处理一张卡片。发生风控时暂停约 30 分钟，不并发处理后续卡片。
- 待入库开始前关闭追更和外部扫库；所有待入库、入库中、CD2 监控完成后请求目标 Emby 扫库；只有收到匹配的 `scheduledtasks.completed` 回调后才恢复原开关状态。
- 敏感字段（Cookie、passkey、authkey、token、signature、回调密钥等）不得写入日志、测试夹具、版本日志或提交内容。

## 3. 路径模型

### 3.1 当前默认容器映射

MoviePilot 当前使用的主要映射是：

```text
/volume1/media/transmission:/MP
/volume2/SSD:/SSD
```

插件默认布局在 `layout.py` 中定义：

```text
库存根目录：/SSD/云盘/strm/影视库

源路径路由 UP：
  匹配前缀：/MP
  电影硬链接根：/MP/电影UP
  剧集硬链接根：/MP/剧集UP

源路径路由 SSD：
  匹配前缀：/SSD
  默认硬链接根：/SSD/云盘/l
```

用户可以在插件设置中修改库存根目录和源路径路由。路由匹配采用最长前缀，必须按路径边界匹配，不能把 `/MP2` 错判为 `/MP`。

### 3.2 四类路径必须区分

一张媒体卡片可能同时保存以下路径：

```text
qB 源路径：       qB 下载目录内的实际媒体文件
当前源路径：      源路径迁移或实时硬链接后的插件可访问路径
插件硬链接路径：  本轮创建的同盘硬链接
库存路径：        目标媒体库中的 .strm 文件
CD2 目标路径：    根据硬链接路径映射到 CD2 云端的完整路径
```

不要用文件名推导这些路径，也不要用 CD2 文件名关联上传任务。路径必须来自持久化 `file_mappings`。

### 3.3 路径示例

```text
qB 源：/MP/剧集UP/国产剧/某剧/Season 1/E01.mkv
硬链接：/MP/剧集UP/国产剧/某剧/Season 1/某剧 - S01E01.mkv
库存：/SSD/云盘/strm/影视库/国产剧/某剧 (2026) - {tmdbid=123}/Season 1/某剧 - S01E01.strm
CD2 目标：由配置的 CD2 目标根目录加上硬链接路径的相对部分生成
```

## 4. 主要模块

| 文件 | 责任 |
| --- | --- |
| `__init__.py` | MoviePilot 插件入口、API、服务注册、调度器、配置读取 |
| `database.py` | SQLite 表结构、事务、幂等写入、快照和历史记录 |
| `domain.py` | 媒体状态和状态迁移规则 |
| `layout.py` | 分类、电影/剧集分组、库存根目录和源路径路由 |
| `rss_tasks.py` | RSS 任务默认值、字段规范化、保存和删除任务 |
| `rss_feed.py` | RSS/Atom 只读抓取、解析、过滤、来源身份和敏感参数遮蔽 |
| `rss_execute.py` | RSS 正式执行、qB 入队、去重、源命名、站点标签和历史记录 |
| `rss_rename.py` | RSS 源文件普通规则、中文标题、国配/特效和目录深度命名 |
| `rss_site_labels.py` | UBits、CHD/PTCHDBits、HDSKY 的独立标签解析 |
| `qb_sync.py` | qB 任务范围、识别、卡片生成、完成回调和延时删除计划 |
| `inventory.py` | TMDB 目录锁定、MoviePilot 命名计划和逐个 `.strm` 对比 |
| `file_manager.py` | 只读目录浏览、单项识别、当前目录批量识别和重复保护 |
| `media_actions.py` | 待入库、硬链接、回退、删除、共享源保护和库存刷新 |
| `pending_import.py` | 串行待入库队列、CD2 监控、风控回滚、扫库回调和开关恢复 |
| `external_controls.py` | Emby 追更开关和 SA 外部扫库开关的独立 API 客户端 |
| `clouddrive_client.py` | CD2 gRPC 上传任务查询、暂停和取消 |
| `capabilities.py` | 运行环境能力检测，包括 gRPC 依赖 |
| `src/components/AppPage.vue` | 插件主页面、卡片、标签、选择、分页和请求序号保护 |
| `src/components/Config.vue` | 插件配置页面 |
| `src/components/FileManagerBrowser.vue` | 文件管理页面 |
| `clouddrive.proto` | 原始 CD2 gRPC 契约；生成代码必须保持与原文件一致 |

## 5. SQLite 数据模型

主要表：

- `rss_tasks`：RSS 任务配置和调度顺序。
- `rss_history`：RSS 来源身份、内容键、处理状态和去重信息。
- `torrent_snapshots`：当前 qB 任务快照，只保留当前受管任务。
- `media_items`：入库管理卡片和识别结果。
- `file_mappings`：每个媒体文件的源路径、硬链接路径、库存路径和新文件名。
- `import_batches`：待入库批次、原始外部开关、扫库等待和结果。
- `import_watches`：每个硬链接对应的 CD2 监控任务。
- `qb_delete_jobs`：qB 延时删除任务。
- `background_tasks`：文件批量识别和其他后台任务进度。

所有后台流程必须满足：

- 可重复执行而不重复创建记录。
- 插件重启后能够从 SQLite 恢复非终态任务。
- 外部操作完成后再更新持久化状态。
- 不能通过文件名猜测丢失的映射。

## 6. 媒体状态

`domain.py` 中的主要状态：

```text
discovered   已发现
identified   已识别
unidentified 未识别
existing     已存在或库存已完整
pending      待入库
importing    入库中
imported     已入库
rolled_back  回退
```

其中 `importing` 是内部保护状态，前端默认不作为长期筛选项展示；`rolled_back` 必须保留回退标记，直到再次成功入库。

## 7. RSS 执行流程

### 7.1 RSS 任务

任务配置至少包括：

- 任务名称、RSS URL、qB 下载器、CRON。
- 保存路径、qB 分类、标题包含过滤。
- 添加时暂停、推送种子文件、识别国语、识别特效、添加中文标题。
- RSS 源文件重命名、下载权限、删除任务延迟、删除文件开关。
- 站点身份、国语关键词。
- 是否允许进入入库管理。

RSS 调度总开关关闭后，所有任务 CRON 和“立即执行”都应停止；已有历史和 qB 任务不能被删除。

### 7.2 去重优先级

来源身份优先级：

1. 站点 torrent ID。
2. opaque GUID。
3. 规范化 enclosure URL。
4. 详情 URL。
5. 标题加发布时间。

历史键：`SHA-256(task_id + source_identity)`。

最终内容键：`downloader_id + info_hash`。

获取 info-hash 后，GUID、种子 ID 和不同 URL 必须合并为同一内容。

### 7.3 源名称处理顺序

```text
加入 qB
  -> RSS 任务普通重命名规则
  -> 添加中文标题
  -> 查询国语和特效标签
  -> 按固定顺序整理标记
  -> 重新读取 qB 文件列表和路径
  -> MoviePilot 识别
  -> 生成 QB 管理卡片
```

国配和特效标准顺序是：

```text
主体-国配-特效-REMUX-版本标记.扩展名
```

普通重命名规则支持文字替换和 `/表达式/flags => replacement`。文件先处理，目录按深度从深到浅处理，扩展名必须保留。

## 8. qB 管理和回调

- qB 管理只展示当前 qB 中仍存在的、且属于已保存 RSS 任务范围的任务。
- 下载完成后由 qB 回调进入插件的完成处理逻辑。
- 回调处理识别结果、库存状态和 RSS 入库开关。
- RSS 任务勾选“入库”才进入入库管理；未勾选的任务下载完成后不进入入库管理。
- 手动刷新 qB 只用于重新识别或 qB 任务被手动删除后的兜底。
- qB 删除默认保留下载文件；要求删除文件时必须确认 qB 任务状态和删除结果。

回调密钥分开管理：

- MoviePilot qB 回调使用 MoviePilot 侧认证配置。
- Emby 扫库回调使用插件 `scan_callback_secret`。
- 不要把两者混用，也不要把真实密钥写入仓库。

## 9. 本地库存判断

库存根目录由分类精确决定。库存目录查找顺序：

1. 读取 MoviePilot 识别结果中的媒体类型、分类、TMDB ID、标题、年份和季号。
2. 在库存根目录下查找包含 `[tmdbid=ID]` 或 `{tmdbid=ID}` 的一级目录。
3. 如果多个目录匹配，使用 MoviePilot 当前预期目录进行消歧；仍无法消歧时标记冲突。
4. 找到旧目录后，使用库存目录标题覆盖本次识别标题，避免译名或年份差异导致文件名漂移。
5. 按 MoviePilot 的完整命名计划生成预期文件路径。
6. 只读取目标目录中的 `.strm` 文件并逐个比较。

库存统计必须保存：

```text
folder_status
total_files
exists_count
missing_count
```

目录存在不等于库存完整。`目录已存在（0/20）` 仍然是不完整库存。

## 10. 文件管理

文件管理页面只能浏览配置的源路径路由范围，不能通过 `..`、绝对路径或符号链接逃逸。

- 当前目录工具栏的“批量识别”处理当前目录内的直接子文件和直接子目录。
- 文件夹行的操作只识别该文件夹内部媒体，不把文件夹本身当作媒体。
- 单文件行支持单项识别。
- 识别前通过源路径和持久化文件映射检查重复，避免重复建立卡片。
- 识别操作不应弹出浏览器确认框。

## 11. 待入库、CD2 和外部开关

### 11.1 批次状态

```text
switch_snapshot_saved  已保存外部开关原状态，尚未关闭
running                正在串行处理
paused_risk            CD2 风控暂停，等待冷却
waiting_scan_callback  已请求媒体库刷新，等待 Emby 完成回调
restore_failed         恢复追更或扫库开关失败，等待重试
completed              批次完成
failed                 批次失败
```

创建批次时必须先读取并持久化追更/扫库原状态，再执行关闭。旧批次没有快照时应保护性停止，不能猜测原状态。

### 11.2 单卡流程

```text
identified
  -> pending
  -> importing
  -> 创建缺失硬链接，跳过已存在文件
  -> 成功或至少有可复用文件：进入 imported
  -> 完全失败：回到 identified 并记录失败原因
```

CD2 监控只关联本轮真正创建的硬链接。任务匹配使用完整目标路径、大小和时间窗口，之后使用 CD2 返回的任务 key，不得只按文件名匹配。

出现真实传输、风控错误或超时：

1. 暂停/取消对应 CD2 任务。
2. 只删除本轮创建且仍归插件所有的硬链接。
3. 保留 qB 源文件。
4. 删除或回退入库记录。
5. 风控时暂停整个批次约 30 分钟。

### 11.3 Emby 扫库回调

成功处理完全部卡片后：

1. 保持追更和外部扫库关闭。
2. 调用目标 Emby 媒体库刷新。
3. 持久化等待回调状态和截止时间。
4. 只接受匹配服务器、任务 ID/名称和时间窗口的 `scheduledtasks.completed`。
5. 回调确认后恢复批次开始前的开关。
6. 超时应记录失败并恢复开关，不能记为成功。

追更和外部扫库是两个独立程序/接口，配置不能共用：

- 追更：Emby 地址、PageId、Token。
- 外部扫库：SA 地址、账号、密码、配置名、目标节点。

## 12. 删除和共享源保护

删除操作分为：

- `delete_source`：删除当前卡片源文件并删除卡片记录，已入库卡片禁止使用。
- `delete_hardlinks`：只删除插件创建的硬链接，卡片回退为可识别状态。
- `delete_both`：删除当前卡片拥有的硬链接和源文件，并清理完整已入库记录。

删除源文件前必须调用数据库的源路径所有者检查。若其他卡片仍引用同一路径，必须保留源文件。删除最后一个拥有者时才允许删除。

不要只相信数据库里的 `hardlink_owned`：后续还应补充 `os.path.samefile(source, target)` 检查，防止硬链接目标被替换后误删替换文件。

## 13. API 入口概览

逻辑 API 由 `__init__.py` 注册，实际 MoviePilot 基础路径由宿主决定。

查询类：

```text
/overview              插件总览
/health                数据库和能力状态
/media                 入库管理列表
/torrents              qB 管理列表
/qb/downloaders        qB 节点
/layout                路径规划
/categories            分类列表
/rss/tasks             RSS 任务
/rss/history           RSS 历史
/sites                 站点身份
/tasks                 后台任务
/files/browse          文件浏览
/import/status         待入库状态
```

写入类：

```text
/rss/tasks              保存 RSS 任务
/rss/test               只读测试 RSS
/rss/run                立即执行 RSS
/rss/control            暂停/恢复 RSS
/qb/refresh             手动刷新 qB
/qb/item/refresh        刷新单个 qB 项目
/qb/item/identify       手动指定识别
/qb/delete              删除 qB 任务并默认保留文件
/qb/completed           qB 完成通知
/media/action           入库、回退和删除操作
/media/delete           删除插件媒体记录
/media/refresh          刷新库存
/import/run             启动待入库队列
/files/recognize        单项文件识别
/files/recognize-batch  当前目录批量识别
/external/catchup/control 追更开关
/external/scan/control    外部扫库开关
/emby/scheduledtasks/completed Emby 扫库完成回调
```

除 Emby 回调使用独立回调密钥外，普通 API 必须遵循 MoviePilot 插件 API 认证约束。

## 14. 前端约束

- 卡片选中用于批量操作，不在卡片上添加重复的单独入库/删除按钮。
- 页面、qB 节点、入库状态和 RSS 任务筛选切换时必须清空选中项。
- 页面切换前清空旧列表，并用请求序号阻止过期响应覆盖新页面。
- qB 卡片左上角来源按钮为 P，TMDB 链接为 T；入库卡片根据状态显示 R、!、P、T。
- 标签使用不同语义颜色；长标签必须换行或收缩，不能溢出卡片。
- 前端不使用 `v-html` 展示未信任的 RSS、文件名或站点内容。
- 修改 Vue 后，在 `plugins.v2/rssallinone` 目录执行 `npm.cmd run build`，构建产物由插件加载。

## 15. 测试和验证

在仓库根目录：

```powershell
python -m unittest discover -s tests -v
python -m compileall -q plugins.v2/rssallinone tests
python -m pip check
```

在插件目录：

```powershell
npm.cmd run build
```

高风险修改必须增加故障注入测试，至少覆盖：

- qB 任务不存在时的删除文件行为。
- Emby started、缺失事件和 completed 回调。
- 外部开关在关闭前后崩溃恢复。
- CD2 超时、真实传输和风控回滚。
- 共享源文件、重复卡片和最后一个拥有者删除。
- 被替换的硬链接目标不能被误删。

## 16. 当前已知待改进项

以下事项在 `0.13.8` 仍值得后续处理：

1. RSS enclosure 和站点详情请求需要增加同源/允许域名校验，避免把 PT Cookie 发送到任意 URL。
2. 普通删除硬链接路径还应使用 `os.path.samefile()` 校验目标仍指向原源文件。
3. 后端应禁止通过普通媒体删除接口删除 `imported` 记录，避免留下孤立硬链接。
4. CD2 当前使用明文 gRPC，应支持 TLS 或明确限制在可信隔离网络。
5. RSS 历史、已完成批次和监控任务需要统一的可配置保留策略。
6. 当前构建依赖存在 Vite/esbuild 审计告警，升级前需验证 MoviePilot 联邦构建兼容性。

## 17. 继续开发规则

开始修改前：

1. 先确认修改属于 RSS 执行、qB 同步、库存、入库、CD2、外部开关还是前端层。
2. 阅读对应模块和现有测试，不要直接重写跨层逻辑。
3. 保持 SQLite 写入幂等，并为重启、重复回调、重复识别和部分失败设计恢复路径。
4. 不要把 qB 源文件名、MoviePilot 目标名、库存 `.strm` 名称混为一套规则。
5. 不要把追更、SA 扫库、Emby 媒体库刷新和 CD2 上传混成一个客户端。
6. 不要提交真实 Cookie、Token、API Key、回调密钥或本地数据库。
7. 完成后先跑测试、编译和前端构建，再修改版本号和市场日志。

对外版本日志写在 `package.v2.json`，只使用简短的概括性描述，不暴露内部实现名称；详细变更、接口和状态机写在本文档与测试中。
