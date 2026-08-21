# 多版本订阅（设计阶段）

> 当前目录只用于方案讨论，尚未注册为 MoviePilot 插件，也未加入 `package.v2.json`。

## 目标

接管 MoviePilot 的站点 RSS 订阅匹配，为同一个媒体维护多个相互独立的版本通道，例如：

- 1080p：独立过滤规则、目标数量和进度。
- 2160p：独立过滤规则、目标数量和进度。

插件只负责读取站点 RSS、匹配订阅、添加下载和记录添加结果。下载完成后的整理、刮削和媒体库刷新继续由 MoviePilot 根据下载器回调处理。

## 初步结论

方案可行，但不应把多个版本硬塞进 MoviePilot 的一条原生订阅记录。原生订阅只有一套过滤规则和一套完成状态，洗版状态表达的是逐步升级到更优版本，不能表达“1080p 和 2160p 同时各保留一份”的独立进度。

建议采用插件自有订阅表，并复用 MoviePilot 的基础能力：

1. 使用 MoviePilot 已配置的站点、Cookie、RSS 地址和代理设置。
2. 调用 `TorrentsChain().refresh(stype="rss", sites=...)` 获取已解析、初步识别的 RSS `Context`。
3. 插件按媒体身份、季集范围和版本通道独立匹配候选资源。
4. 使用 MoviePilot `DownloadChain.download_single(..., return_detail=True)` 添加下载，不直接调用 qBittorrent API，也不使用会按缺失集收敛的 `batch_download()`。
5. 下载添加成功后写入插件自己的进度账本；MoviePilot 同时正常写下载历史并发送 `DownloadAdded` 事件。
6. 下载完成和后续整理仍由 MoviePilot 原链路处理。

## 接管边界

“接管”建议定义为：插件独立执行 RSS 拉取、候选匹配和下载决策，MoviePilot 原生订阅调度不再处理这些受管订阅。

不建议运行时替换或猴子补丁 `SubscribeChain.refresh()`。这种方式会影响全部原生订阅，并且在 MoviePilot 升级后非常脆弱。

第一版可采用以下安全边界：

- 多版本订阅只存在于插件中，不创建同媒体的多条 MP 原生订阅。
- 插件读取 MP 的全局 RSS 站点选择，也允许每条订阅覆盖站点范围。
- 插件启动时检查同媒体是否仍有活动的 MP 原生订阅；存在冲突时拒绝接管并提示暂停或迁移该订阅。
- 没有活动原生订阅时，MP 自带刷新任务会自然跳过；仍需保留的其他原生订阅可以继续运行。
- 插件不自动清空 `RssSites`，也不修改用户已有原生订阅。

## 建议的数据模型

### subscriptions

- `id`
- `media_type`
- `media_source` / `media_id`
- `tmdb_id` / `douban_id`
- `title` / `year`
- `season`
- `total_episode`
- `sites`
- `state`

### version_profiles

- `id`
- `subscription_id`
- `name`，如 `1080p`、`2160p`
- `filter_groups`
- `target_count`
- `downloader`
- `save_path`
- `label`
- `enabled`
- `priority`

### download_records

- `subscription_id`
- `profile_id`
- `site_id`
- `torrent_title`
- `info_hash`
- `season`
- `episodes`
- `status`：`reserved` / `added` / `failed`
- `created_at`

数据库必须对 `info_hash` 建唯一约束；电视剧还需要按“订阅 + 版本通道 + 季 + 集”计算覆盖进度，避免同一集的重复资源错误增加完成数。

## 并发与计数

下载添加应使用两阶段状态：

1. 匹配到资源后先写 `reserved`，阻止并发 RSS 批次重复选择。
2. `DownloadChain` 返回成功后改为 `added`；失败则改为 `failed`，允许以后重试。

建议同时展示两种数字：

- 添加任务数：成功进入下载器的种子数量。
- 覆盖进度：每个版本通道已覆盖的电影或剧集数量。

仅用“种子数量”判断电视剧完成会被整季包、多集包和重复单集误导，因此完成条件应以版本通道的集覆盖为准。

每个版本通道应允许配置独立保存路径。即使下载目录不同，最终整理模板也必须包含分辨率或版本标记，否则 MP 整理到同一目标文件名时仍可能覆盖；第一版只做启动检查和明确提示，不接管整理策略。

## 第一版范围

- 仅支持 MP 已配置的 PT 站点 RSS。
- 支持电影和单季电视剧。
- 每条订阅可配置多个版本通道。
- 复用 MP 资源识别、规则过滤和下载链路。
- 记录添加结果、去重和各版本进度。
- 提供手动执行和定时执行。
- 不负责下载完成状态、整理、刮削和入库。

## 开发前需要确认

1. `target_count` 表示“每个版本下载几个种子”，还是电视剧中“每集每个版本只要一个资源”。
2. 1080p 与 2160p 是否必须进入不同保存目录，以确保 MP 整理后两个版本不会互相覆盖。
3. 原生 MP 订阅是否全部停用，还是只把插件创建/导入的订阅交给插件。
4. 第一版是否只做 RSS 实时匹配，暂不做定时站点搜索补漏。
