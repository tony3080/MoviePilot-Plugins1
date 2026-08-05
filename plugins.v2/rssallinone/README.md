# RSS一条龙

RSS一条龙是 ReelHarbor V1 的 MoviePilot V2 插件化版本，目标是统一管理 PT RSS、MoviePilot 已配置的 qBittorrent、媒体识别和同盘硬链接入库流程。CloudDrive2 只负责监听硬链接目录并自动备份，插件不调用其备份 API。

## 当前版本

`v0.13.0` 接通待入库/CD2受控队列。CRON和“立即处理”只负责触发同一套持久化批次：有待入库项目时先关闭并验证追更和外部扫库，随后逐卡创建硬链接；每个新硬链接按完整CD2目标路径、大小和本轮时间窗发现上传任务，绑定任务key后监控秒传。真实传输会暂停/取消任务并回滚本卡，风控会回滚并暂停队列30分钟；全部完成后调用目标Emby刷新，等待匹配的 `scheduledtasks.completed` 回调后恢复批次开始前的开关状态。

`v0.10.2` 保留回退卡片的 `R` 标记：刷新时仍重新识别并复查库存，但不会清除回退来源，只有再次成功入库后才移除 `R`。入库管理状态筛选不再显示仅供内部流程使用的“已发现”和“入库中”；其中“入库中”仍作为创建硬链接期间防止重复执行的瞬时状态保留在后端。

- 每张 RSS 任务卡片可直接执行只读测试，也可对已保存配置立即入队执行。
- RSS CRON 按任务启用状态注册；VT+ 工具栏提供独立的 RSS 调度总开关，测试时可暂停全部 RSS，恢复时无需重新配置任务。
- 正式执行使用 MoviePilot 已配置的 qBittorrent 节点和站点身份，支持 URL/种子文件首选顺序、模式切换、3/10/30 秒退避、分类、保存路径、暂停状态和上传限速。
- RSS 成功取得 info-hash 后，任务勾选“重命名”时按配置顺序实际修改 qB 文件和目录；支持普通替换与 `/正则/flags => replacement`，其中 `g` 表示全局替换，文件先处理，目录再从深到浅处理。
- “添加中文标题”独立于普通重命名开关，从 RSS 标题方括号候选中提取有效中文名，并以 `[中文标题].` 前缀修改 qB 文件和目录；技术词、国语、国配、特效和字幕标签不会被误判为已有中文标题。
- 源名称处理严格分段执行：普通规则与中文标题完成后，才查询站点国语/特效标签；命中后统一整理为 `国配-特效-REMUX-版本标记`，最终处理成功后才触发 MoviePilot 识别并生成 QB 卡片。
- UBits 直接解析 RSS 详情页标签区域；CHD/PTCHDBits 与 HDSKY 使用站内搜索，多结果时必须使用 RSS torrent ID 精确定位。相同站点请求至少间隔 60 秒，403/429/503 冷却 300 秒后只重试一次。
- qB 源改名与 MoviePilot 目标命名完全分离：MP 当前模板、自定义识别词、TMDB、季集、分辨率等继续生成 `new_rel`、硬链接目标和 STRM 库存目标。
- 每个媒体文件持久化下载器、info-hash、qB 文件索引、当前源路径、`new_rel`、硬链接路径和库存路径，后续创建或删除任一侧时不再通过文件名反推。
- RSS 历史只把成功入队、qB 已存在、内容重复和已处理视为永久去重；失败记录可在下次执行重试。
- 解析 RSS 2.0 与 Atom 的标题、详情链接、GUID、enclosure 种子链接、发布时间和站点 torrent ID。
- 按“torrent ID、opaque GUID、enclosure URL、详情 URL、标题加发布时间”的优先级生成稳定来源身份和 SHA-256 去重键。
- 在测试结果中执行不区分大小写的“名称包含”筛选，并预检数据库中已有 RSS 历史与订阅内重复条目。
- 缺少 enclosure 的条目单独标记，不会被视为可推送种子。
- RSS URL、详情 URL 和 enclosure URL 中的 `passkey`、`authkey`、`token`、`rsskey`、`signature` 等参数统一脱敏。
- RSS 测试不会写入历史、不会推送 qB，也不会影响以后正式执行的去重判断。
- MoviePilot V2 插件入口、市场元数据和 Vue 模块联邦页面。
- 只读枚举当前 MoviePilot 已配置且就绪的 qBittorrent 节点。
- 增量保存 torrent 快照，并复用 MoviePilot 的媒体识别和命名结果。
- 从 qB 文件及其目录上下文生成 MoviePilot 完整目标相对路径，自动应用当前命名模板和自定义识别词。
- 当实际文件名缺少发行信息时，使用 qB 任务标题已解析出的资源类型、HDR、分辨率、音视频编码、制作组和命中识别词补齐 MoviePilot 命名输入，但不覆盖文件级季号和集号。
- QB 管理直接显示每条记录的资源字段、命中识别词数量及任务标题补全状态，完整规则可悬停查看。
- 每次识别都通过 MoviePilot 当前“自定义识别词”和“自定义占位符”配置重新计算 `customization`，按 `@` 保序去重合并任务标题与实际文件结果，再交给原生命名模板。
- QB 管理单独显示最终传给 `{{ customization }}` 的值，避免把 `apply_words` 命中清单误当成命名占位符。
- 站点身份、QB、入库、RSS 历史和后台任务表格完整显示当前接口已加载的数据，不再因隐藏分页栏而只显示前 10 条。
- 按分类和 TMDB ID 锁定库存媒体目录；使用已有库存目录标题重新生成预期名称，只核对 `.strm`，不比较源媒体大小。
- 逐文件记录 `new_rel`、STRM 预期路径、匹配方式和库存状态，并汇总完整、部分缺失、目录缺失、空资源和目录冲突。
- 按 MoviePilot 分类和源路径生成精确的最终库存路径与硬链接 staging 路径。
- 入库管理支持批量转待入库、立即硬链接入库、删源、只删插件硬链接和硬链接/源文件双删；高风险操作需要二次确认。
- 普通入库使用 `os.link(current_source_path, local_hardlink_path)`，逐文件跳过已有 STRM 库存；失败回滚仅删除本轮新建目标。
- “只删硬链接”仅删除映射中标记为插件拥有的目标，库存已存在文件、外部已有目标和 qB 源文件均保留，卡片回退后可再次入库。
- 配置页可编辑最终媒体库根目录、源路径路由以及电影/剧集硬链接根目录。
- QB 管理只识别已保存 VT+ RSS 任务声明的“QB下载器 + QB分类”组合，不扫描其他种子。
- 插件不再定时扫描 qB 来推进正常流程；“刷新识别”仅保留为手动兜底。qB 完成回调按 info-hash 找到受管任务，勾选“入库”的项目进入入库管理，未勾选的项目直接从 QB 管理移除。
- “完成后删除任务”建立独立到期任务；到期时重新核对该 info-hash 已完成，再通过 MoviePilot 的 qB 删除接口操作。勾选“删除文件”时删除的是 qB 保存路径中的源文件，不会按插件媒体卡片路径删除其他硬链接。
- VT+ RSS任务页支持新增、编辑、删除和批量保存，保存后立即更新 QB 管理范围。
- 站点身份页只读显示当前 MoviePilot 的站点名称、地址、启用状态和认证方式，不返回认证内容。
- 后台刷新任务、进度查询、节点/库存/关键词筛选和 QB 管理状态表。
- SQLite schema、迁移、任务恢复和只读分页 API。
- CloudDrive2 原始 `clouddrive.proto` 及生成的 Python gRPC 客户端代码。

当前版本会执行 RSS 任务配置的 qB 入队和源文件/目录改名，生成并持久化独立的 MoviePilot 硬链接目标映射，并在入库管理中按选择显式创建或删除普通入库硬链接。RSS 任务中的“完成后创建实时硬链接”仍是另一条特殊链路，默认关闭；V1 仍在运行期间必须保持关闭。两条链路都不调用 CloudDrive2 API，也不会切换外部追更或扫库开关。

## qB 完成回调

仓库提供 [`qb_completed_notify.sh.example`](qb_completed_notify.sh.example)。复制到 qB 容器的 `/config/qb_completed_notify.sh` 后，只需填写 `V1_SECRET` 和 MoviePilot 的 `MP_API_TOKEN`，不要把真实密钥提交到 Git。

同一份脚本可以复制到多个 qB 容器。V1 节点名和 MoviePilot 下载器名必须分别传入，因为同一个 qB 在两个系统中可能使用不同名称。qBittorrent 的“Torrent 完成时运行外部程序”填写：

```sh
/bin/sh /config/qb_completed_notify.sh "<V1节点名称>" "<MoviePilot下载器名称>" "<qB WebUI地址>" "%I" "%L" "%N" "%G"
```

当前三个节点应分别配置：

```sh
/bin/sh /config/qb_completed_notify.sh "QBSSD" "QB" "http://192.168.110.31:8081" "%I" "%L" "%N" "%G"
/bin/sh /config/qb_completed_notify.sh "QB电影" "QB电影" "http://192.168.110.31:8084" "%I" "%L" "%N" "%G"
/bin/sh /config/qb_completed_notify.sh "QB完结" "QB完结" "http://192.168.110.31:8085" "%I" "%L" "%N" "%G"
```

脚本仍兼容原来的六参数和四参数命令。四参数模式默认使用 `V1=QBSSD`、`MoviePilot=QB` 和 `http://192.168.110.31:8081`；多 qB 部署建议使用上面的七参数命令。

脚本会通知现有 V1，并独立通知 RSS一条龙：

```text
POST /api/v1/plugin/RssAllInOne/qb/completed
X-API-KEY: <MoviePilot API Token>
{"info_hash":"<qB hash>","downloader_id":"<MoviePilot下载器名称>"}
```

两个通知都会独立重试，V1 临时失败不会阻止 RSS 一条龙收到完成事件。插件对非受管 hash 返回 `success=true, ignored=true`，因此同一个 qB 全局完成脚本可以安全处理其他分类。

如果 qB 任务标签中精确包含 `MOVIEPILOT`，脚本还会继续调用 MoviePilot 原生的 `/api/v1/transfer/now`；没有该标签时记录为跳过。RSS一条龙添加的任务不携带 `MOVIEPILOT` 标签，因此不会误触发 MoviePilot 原生整理流程。

`/api/v1/transfer/now` 本身不接收节点名；V1 节点名只用于 V1 回调，MoviePilot 下载器名只用于 RSS一条龙插件回调。

彩虹岛路径边界如下：

```text
qB 做种源：/SSD/QB目录/REMUX/CHD
V1 实时硬链接：/SSD/QB目录/REMUX/CHDlink
```

RSS 延时删除通过 qB 删除前者；以后从文件管理批量识别 `CHDlink` 时，媒体卡片的源路径是后者，入库后的“删源”只应删除 `CHDlink` 对应硬链接，不得反向删除 qB 的 CHD 做种源。

QB 管理范围取所有已保存 RSS 任务的 `QB下载器` 和 `QB分类`。分类按 qB 返回值精确匹配；任务未填写下载器或分类时会被忽略，完全没有有效组合时刷新任务直接失败并隐藏旧的全量扫描快照，绝不会退化为扫描整个下载器。RSS 任务即使暂时停用，其已下载种子仍保留在 QB 管理范围；删除任务或修改分类后，下次刷新会退出旧范围。

“站点身份”来自当前 MoviePilot 的站点管理。RSS 任务只保存站点 ID，后续需要识别国语或特效标签时，由 MoviePilot 站点服务在后端携带认证信息访问详情页；插件页面只显示站点名称、地址、启用状态和认证方式，不显示 Cookie、Token、API Key 或 passkey。

双阶段命名当前已经落地：第一阶段在 RSS 入队后修改 qB 实际文件/目录名称；第二阶段使用 MoviePilot 当前命名规则生成独立的硬链接与 STRM 目标，并保存源目标映射。国语/特效站点标签解析、qB 完成回调、手动批量硬链接入库、基于映射的双侧删除以及CD2待入库监控队列已经接通。普通手动“入库”不调用CD2；只有“待入库”队列调用CD2上传任务接口进行秒传监控、暂停和取消。

## 本地库存检查

库存检查不调用 MoviePilot/Emby 的媒体存在性接口。插件配置中的“最终媒体库根目录”必须指向 CD2 云端目录重新挂载后，插件进程能够直接访问的路径。

当前 MoviePilot 容器挂载为：

```text
/volume1/media/transmission -> /MP
/volume2/SSD                -> /SSD
```

目录规划默认预填以下配置，所有值都可以在插件配置页修改：

```yaml
inventory_root: /SSD/云盘/strm/影视库
source_routes:
  - name: UP
    prefix: /MP
    link_roots:
      movie: /MP/电影UP
      series: /MP/剧集UP
  - name: SSD
    prefix: /SSD
    link_roots:
      default: /SSD/云盘/l
```

这里填写的都是 MoviePilot 插件容器内路径，不是 NAS 宿主机路径。分类库存根目录为 `inventory_root / MP分类`；插件先扫描其一级目录，通过 `[tmdbid=ID]` 或 `{tmdbid=ID}` 精确锁定媒体目录，未命中时才按 MoviePilot 生成的预期目录名做不区分大小写的完整匹配。找到 TMDB 目录后，插件提取目录中已经使用的标题，再通过 MoviePilot 当前命名模板重新生成完整文件相对路径。硬链接目录继续使用真实媒体扩展名，库存路径只把最终扩展名派生为 `.strm`。库存端只扫描锁定媒体目录中的 `.strm`，不使用源文件大小；优先匹配精确相对路径，失败后比较去掉库存标题和扩展名后的完整文件特征。QB 页面显示 `已存在 3/3` 或 `不完整 2/3`，同名 `.mkv`、`.mp4`不会被当作库存。根目录未配置、挂载离线、目录冲突、目录缺失和文件缺失分别记录。

## 术语

本插件中的“入库”不是 MoviePilot 的媒体转移入库。它表示：

1. 使用 MoviePilot 的媒体识别和命名结果。
2. 在与下载源同一文件系统的 staging 目录创建硬链接。
3. 硬链接目录触发外部 CloudDrive2 自动备份。
4. 等待云端目录重新挂载到 MoviePilot/Emby 媒体库。

## 前端构建

```powershell
npm.cmd install
npm.cmd run build
```

构建输出必须保存在 `dist/assets`，并提交 `remoteEntry.js` 及其引用的资源。

## CloudDrive2 参考代码

`clouddrive.proto` 与生成代码仅作为 V1 历史接口参考，当前插件运行时不连接 CloudDrive2，也不创建或跟踪备份任务。需要校验原接口时，可重新生成绑定：

```powershell
python -m grpc_tools.protoc -I . --python_out=generated --grpc_python_out=generated clouddrive.proto
```

生成后需要确保 `generated/clouddrive_pb2_grpc.py` 使用包内相对导入：

```python
from . import clouddrive_pb2 as clouddrive__pb2
```

## 数据位置

运行数据库默认名为 `rssallinone.db`，保存在 MoviePilot 为插件分配的数据目录。连接配置由 MoviePilot 插件配置保存，RSS 历史、任务状态、文件清单和恢复信息由 SQLite 保存。
