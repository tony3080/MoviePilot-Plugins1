# RSS一条龙

RSS一条龙是 ReelHarbor V1 的 MoviePilot V2 插件化版本，目标是统一管理 PT RSS、MoviePilot 已配置的 qBittorrent、媒体识别、同盘 staging 硬链接和 CloudDrive2 备份流程。

## 当前版本

`v0.3.0` 在可运行框架上完成了 qB 只读同步、本地库存核对和可编辑目录规划：

- MoviePilot V2 插件入口、市场元数据和 Vue 模块联邦页面。
- 只读枚举当前 MoviePilot 已配置且就绪的 qBittorrent 节点。
- 增量保存 torrent 快照，并复用 MoviePilot 的媒体识别和命名结果。
- 从 qB 文件清单生成预期目标相对路径，直接核对最终挂载媒体库中的本地文件和大小。
- 按 MoviePilot 分类和源路径生成精确的最终库存路径与硬链接 staging 路径。
- 配置页可编辑最终媒体库根目录、源路径路由、电影/剧集硬链接根目录和分类列表。
- 后台刷新任务、进度查询、节点/库存/关键词筛选和 QB 管理状态表。
- SQLite schema、迁移、任务恢复和只读分页 API。
- CloudDrive2 原始 `clouddrive.proto` 及生成的 Python gRPC 客户端代码。

当前版本不会执行 qB 写操作、创建或删除硬链接、暂停或取消 CD2 任务，也不会切换外部追更或扫库开关。

## 本地库存检查

库存检查不调用 MoviePilot/Emby 的媒体存在性接口。插件配置中的“最终媒体库根目录”必须指向 CD2 云端目录重新挂载后，插件进程能够直接访问的路径。

当前 MoviePilot 容器挂载为：

```text
/volume1/media/transmission -> /MP
/volume2/SSD                -> /SSD
```

因此 `v0.3.0` 预填以下配置，所有值都可以在插件配置页修改：

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
category_groups:
  movie: [演唱会, 动画电影, 华语电影, 外语电影]
  series: [儿童剧, 动漫, 国产剧, 日韩剧, 欧美剧, 纪录片, 综艺]
```

这里填写的都是 MoviePilot 插件容器内路径，不是 NAS 宿主机路径。库存目录按 `inventory_root / MP分类 / MoviePilot目标相对路径` 生成；硬链接目录按命中的源路由根目录、MP 分类和同一目标相对路径生成。源路由使用路径边界感知的最长前缀匹配，未知分类不会猜测目录。MoviePilot 负责识别和生成目标相对路径，插件随后使用本地文件系统逐项核对文件是否存在以及大小是否一致。根目录未配置、挂载离线和文件缺失是三个不同状态。

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
