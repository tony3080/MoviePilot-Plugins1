# MoviePilot 豆瓣订阅插件

面向 MoviePilot V2 的第三方插件仓库，用于开发“豆瓣条目识别、TMDB 作品与季度匹配、准确创建订阅”能力。

> 当前状态：仓库骨架已完成，核心匹配与订阅功能尚在开发中。

## 仓库结构

```text
.
├── package.json                         # V1 索引（当前为空）
├── package.v2.json                      # V2 插件市场索引
├── plugins.v2/
│   └── doubansubscribe/
│       ├── __init__.py                  # 插件入口，类名必须为 DoubanSubscribe
│       └── README.md                    # 插件说明
├── tests/                               # 不依赖 MoviePilot 宿主的仓库校验
└── 豆瓣接口与TMDB电视剧匹配设计.md       # 匹配方案设计文档
```

该布局遵循 MoviePilot 官方第三方插件库约定：V2 专用代码位于 `plugins.v2/<插件ID小写>/`，插件主类定义在 `__init__.py`，市场元数据登记在 `package.v2.json`，且两处版本号保持一致。

## 本地校验

```bash
python -m compileall -q plugins.v2
python -m unittest discover -s tests -v
git diff --check
```

完整运行验证需要将仓库接入 MoviePilot V2 宿主；这里只执行不依赖宿主模块的静态校验。

## 接入 MoviePilot

仓库发布到 GitHub 的 `main` 分支后，在 MoviePilot V2 的插件市场中添加仓库地址：

```text
https://github.com/<你的 GitHub 用户名>/<仓库名>/
```

MoviePilot 第三方插件市场仅支持 GitHub 仓库的 `main` 分支。发布新版本时，必须同时更新 `package.v2.json` 的 `version`、`history` 和插件类的 `plugin_version`。

## 参考

- [MoviePilot 官方插件仓库](https://github.com/jxxghp/MoviePilot-Plugins)
- [MoviePilot V2 插件开发指南](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/V2_Plugin_Development.md)
- [MoviePilot 插件开发文档](https://wiki.movie-pilot.org/zh/plugindev)

## 许可证

本项目使用 GNU General Public License v3.0，详见 [LICENSE](./LICENSE)。
