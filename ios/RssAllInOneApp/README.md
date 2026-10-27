# RSS一条龙 iOS 第一版

这是一个原生 SwiftUI 客户端原型，后端继续使用 MoviePilot 上的 RSS一条龙插件。

## 本地查看

需要 macOS + Xcode，或在 GitHub Actions 的 macOS Runner 上构建。项目文件由 XcodeGen 根据 `project.yml` 生成：

```bash
brew install xcodegen
xcodegen generate
xcodebuild -project RssAllInOneApp.xcodeproj \
  -scheme RssAllInOneApp \
  -sdk iphonesimulator \
  -configuration Debug \
  CODE_SIGNING_ALLOWED=NO build
```

没有配置 MP 地址时，App 会使用演示数据展示第一版界面。连接真实实例时填写 MP 地址和访问令牌。
