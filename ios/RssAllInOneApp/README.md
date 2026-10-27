# RSS一条龙 iOS

原生 SwiftUI 客户端，最低 iOS 17，当前版本 0.2.0。通过 MoviePilot 的现有 HTTP API 操作 RSS一条龙，无需增加服务器接口。服务端需要包含本地插件的最新接口，例如 `qb/check-presence` 和 `media/mark-unidentified`。

## 功能

| 页面 | 功能 |
| --- | --- |
| 入库 | 状态、媒体类型与多 RSS 任务筛选，分页，媒体详情，P/T 链接，人工识别、国配与特效编辑，移入未识别，重新识别，批量待入库、入库、复查库存、删除源文件或插件硬链接 |
| qB | 节点与状态筛选、服务端搜索、进度、人工识别、移入未识别、刷新识别、核对已删除的待下载任务、批量删除任务并保留文件 |
| RSS | 新建、编辑、删除任务配置，Cron 或分钟间隔、所有服务端任务字段，配置测试与测试结果，立即执行、试跑一条、自动处理剩余项目、停止手动处理、暂停调度 |
| 文件 | 服务器目录浏览、当前目录搜索、单个文件或目录识别、批量识别、进度入口 |
| 更多 | 总览、入库进度、追更与 SA 开关、结束扫库等待、后台失败任务及清理、RSS 历史、站点身份、目录规划、依赖状态、回调记录、插件完整设置、存量修复与数据维护 |

入库搜索仅搜索当前已加载的记录；服务端媒体 API 尚不接受关键词。qB 搜索由服务端完成。长列表分页加载，操作仍由 NAS 执行，退出 App 不会停止服务器后台任务。修改配置前重新读取并比较，检测到其他客户端修改时拒绝覆盖；服务器 API 本身没有原子版本锁。

App 中的详情使用真实服务器数据；连接失败会显示错误，不会用演示数据替代。设置保存会重新初始化 MP 插件。删除源文件、硬链接等不可恢复操作有确认提示；服务器仍执行原有保护规则。

## 连接

填写 iPhone 可访问的 MoviePilot 根地址，并使用 MP 用户名、密码登录；开启二次验证时填写动态验证码。也支持粘贴有效的 **Bearer 访问令牌**，它与 MP API Key 不同。

令牌保存在 iOS Keychain；密码不保存，普通偏好设置不保存令牌。支持局域网 HTTP、HTTPS 及反向代理路径前缀。通过 VPN 或 HTTPS 反向代理连接外网实例时，需要提供 iPhone 实际可达的地址。

## GitHub Actions 构建

推送 `ios/RssAllInOneApp/**` 或工作流文件后，`.github/workflows/ios-build.yml` 自动启动。也可在该分支的 Actions 工作流页面手动运行。

流程在 macOS Runner 上生成项目，运行单元测试与模拟服务器界面测试，再构建真机 Release。构建产物：

- `rssallinone-ios-unsigned`：`RSS-All-In-One-unsigned.ipa`，需要你自行签名后安装。
- `rssallinone-ios-simulator`：模拟器 App。
- `ios-test-results`：测试结果及界面截图。

未签名 IPA 不能直接安装到 iPhone。远端构建使用 GitHub 提供的 macOS/Xcode，本地 Windows 无需安装 Xcode。仓库不需要保存你的 MP 密码、令牌或签名证书。

## macOS 本地构建

项目由 XcodeGen 根据 `project.yml` 生成：

```bash
brew install xcodegen
xcodegen generate
xcodebuild -project RssAllInOneApp.xcodeproj \
  -scheme RssAllInOneApp \
  -sdk iphonesimulator \
  -configuration Debug \
  CODE_SIGNING_ALLOWED=NO build
```

运行完整 UI 测试前，在另一个终端启动 `python3 UITests/mock_server.py`。模拟服务器仅监听本机，并拒绝未定义的写操作。`--ui-testing` 启动参数只在 Debug 中隔离连接偏好，不包含在 Release 工作流程中。
