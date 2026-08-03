# RSS一条龙

RSS一条龙是 ReelHarbor V1 的 MoviePilot V2 插件化版本，目标是统一管理 PT RSS、MoviePilot 已配置的 qBittorrent、媒体识别、同盘 staging 硬链接和 CloudDrive2 备份流程。

## 当前版本

`v0.1.0` 是可运行框架版本，已包含：

- MoviePilot V2 插件入口、市场元数据和 Vue 模块联邦页面。
- `AppPage.vue` 全页工作区、插件详情摘要和配置页面。
- SQLite schema、迁移、完整性检查和只读分页 API。
- 媒体、qB 快照、RSS 任务、RSS 历史、后台任务、CD2 watch 和审计表。
- CloudDrive2 原始 `clouddrive.proto` 及生成的 Python gRPC 客户端代码。
- 当前 MoviePilot 实例、qBittorrent-only 和外部集成的能力状态模型。

框架版本不会执行 qB 写操作、创建或删除硬链接、暂停或取消 CD2 任务，也不会切换外部追更或扫库开关。

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
