# RSS一条龙

RSS一条龙是 ReelHarbor V1 的 MoviePilot V2 插件化版本，目标是统一管理 PT RSS、MoviePilot 已配置的 qBittorrent、媒体识别、同盘 staging 硬链接和 CloudDrive2 备份流程。

## 当前版本

`v0.4.1` 在可运行框架上完成了可编辑 RSS 任务、受任务范围约束的 qB 只读同步、本地 STRM 库存核对和目录规划：

- MoviePilot V2 插件入口、市场元数据和 Vue 模块联邦页面。
- 只读枚举当前 MoviePilot 已配置且就绪的 qBittorrent 节点。
- 增量保存 torrent 快照，并复用 MoviePilot 的媒体识别和命名结果。
- 从 qB 文件及其目录上下文生成 MoviePilot 完整目标相对路径，自动应用当前命名模板和自定义识别词。
- 按分类和 TMDB ID 锁定库存媒体目录；使用已有库存目录标题重新生成预期名称，只核对 `.strm`，不比较源媒体大小。
- 逐文件记录 `new_rel`、STRM 预期路径、匹配方式和库存状态，并汇总完整、部分缺失、目录缺失、空资源和目录冲突。
- 按 MoviePilot 分类和源路径生成精确的最终库存路径与硬链接 staging 路径。
- 配置页可编辑最终媒体库根目录、源路径路由以及电影/剧集硬链接根目录。
- QB 管理只识别已保存 VT+ RSS 任务声明的“QB下载器 + QB分类”组合，不扫描其他种子。
- VT+ RSS任务页支持新增、编辑、删除和批量保存，保存后立即更新 QB 管理范围。
- 站点身份页只读显示当前 MoviePilot 的站点名称、地址、启用状态和认证方式，不返回认证内容。
- 后台刷新任务、进度查询、节点/库存/关键词筛选和 QB 管理状态表。
- SQLite schema、迁移、任务恢复和只读分页 API。
- CloudDrive2 原始 `clouddrive.proto` 及生成的 Python gRPC 客户端代码。

当前版本不会执行 qB 写操作、创建或删除硬链接、暂停或取消 CD2 任务，也不会切换外部追更或扫库开关。

QB 管理范围取所有已保存 RSS 任务的 `QB下载器` 和 `QB分类`。分类按 qB 返回值精确匹配；任务未填写下载器或分类时会被忽略，完全没有有效组合时刷新任务直接失败并隐藏旧的全量扫描快照，绝不会退化为扫描整个下载器。RSS 任务即使暂时停用，其已下载种子仍保留在 QB 管理范围；删除任务或修改分类后，下次刷新会退出旧范围。

“站点身份”来自当前 MoviePilot 的站点管理。RSS 任务只保存站点 ID，后续需要识别国语或特效标签时，由 MoviePilot 站点服务在后端携带认证信息访问详情页；插件页面只显示站点名称、地址、启用状态和认证方式，不显示 Cookie、Token、API Key 或 passkey。

`v0.4.1` 已实现 RSS 任务配置的持久化、QB 管理范围联动和本地 STRM 库存判断，尚未实现 RSS 拉取、种子推送和“立即执行”，因此页面不会提供虚假的执行按钮。

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
3. 由 CloudDrive2 备份到云端目标。
4. 等待云端目录重新挂载到 MoviePilot/Emby 媒体库。

## 前端构建

```powershell
npm.cmd install
npm.cmd run build
```

构建输出必须保存在 `dist/assets`，并提交 `remoteEntry.js` 及其引用的资源。

## CloudDrive2 绑定代码

运行时依赖在 `requirements.txt` 中声明。更新 `clouddrive.proto` 后，可重新生成绑定：

```powershell
python -m grpc_tools.protoc -I . --python_out=generated --grpc_python_out=generated clouddrive.proto
```

生成后需要确保 `generated/clouddrive_pb2_grpc.py` 使用包内相对导入：

```python
from . import clouddrive_pb2 as clouddrive__pb2
```

## 数据位置

运行数据库默认名为 `rssallinone.db`，保存在 MoviePilot 为插件分配的数据目录。连接配置由 MoviePilot 插件配置保存，RSS 历史、任务状态、文件清单和恢复信息由 SQLite 保存。
