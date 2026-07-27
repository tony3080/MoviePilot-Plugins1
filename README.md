# MoviePilot 豆瓣订阅插件

面向 MoviePilot V2 的第三方插件仓库。插件从用户配置的 RSS 获取电视剧，按国家或地区过滤，读取豆瓣声明的总集数并匹配 TMDB。已经开播但豆瓣尚未公布总集数时，会暂按 100 集订阅并按执行周期持续复核；受管订阅完成后会暂停卡片，延迟复核豆瓣总集数，没有增加时由 MoviePilot 正常完成。插件还会每天记录当日有 TMDB 排期的活动电视剧订阅，晚间对进度没有增加的订阅触发缺集搜索。

当前版本：`0.4.1`，要求 MoviePilot `2.15.0` 或更高版本。

后续开发请先阅读 [开发交接文档](./开发交接文档.md)，其中记录了当前实现、MoviePilot 调用契约、测试状态、已知限制和推荐开发顺序。

0.4.1 已实现订阅历史查重、RSS 记录搜索/失败筛选/单条重试、TMDB 搜索诊断及“XXXX篇”分季匹配，设计与验收边界见 [0.4.1 改进需求](./0.4.1改进需求.md)。

## 仓库结构

```text
.
├── package.json                         # V1 索引（当前为空）
├── package.v2.json                      # V2 插件市场索引
├── plugins.v2/
│   └── doubansubscribe/
│       ├── __init__.py                  # 插件入口，类名必须为 DoubanSubscribe
│       ├── core.py                      # RSS 解析、季度假设与候选评分
│       ├── src/                         # Vue 配置页与详情页源码
│       ├── dist/assets/                 # MoviePilot 加载的前端构建产物
│       └── README.md                    # 插件说明
├── tests/
│   ├── test_core.py                     # 纯解析、分类和匹配逻辑
│   ├── test_lifecycle.py                # 模拟豆瓣复核、每日订阅补齐、历史搜索和永久去重
│   └── test_repository.py               # 仓库结构和 MoviePilot 调用契约
└── 豆瓣接口与TMDB电视剧匹配设计.md       # 匹配方案设计文档
```

该布局遵循 MoviePilot 官方第三方插件库约定：V2 专用代码位于 `plugins.v2/<插件ID小写>/`，插件主类定义在 `__init__.py`，市场元数据登记在 `package.v2.json`，且两处版本号保持一致。

## 本地校验

```bash
python -m compileall -q plugins.v2
python -m unittest discover -s tests -v
git diff --check
```

完整的豆瓣、TMDB 与订阅联调需要将仓库接入 MoviePilot V2 宿主；仓库测试覆盖 RSS 解析、地区分类、标题与季度拆分、篇章分季匹配、匹配评分、订阅历史去重、单条重试、豆瓣总集数复核流程、每日更新快照与补齐搜索、全历史搜索、永久去重及订阅锁定调用契约。

## 接入 MoviePilot

仓库发布到 GitHub 的 `main` 分支后，在 MoviePilot V2 的插件市场中添加仓库地址：

```text
https://github.com/tony3080/MoviePilot-Plugins1/
```

MoviePilot 第三方插件市场仅支持 GitHub 仓库的 `main` 分支。发布新版本时，必须同时更新 `package.v2.json` 的 `version`、`history` 和插件类的 `plugin_version`。

## 参考

- [MoviePilot 官方插件仓库](https://github.com/jxxghp/MoviePilot-Plugins)
- [MoviePilot V2 插件开发指南](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/V2_Plugin_Development.md)
- [MoviePilot 插件开发文档](https://wiki.movie-pilot.org/zh/plugindev)

## 许可证

本项目使用 GNU General Public License v3.0，详见 [LICENSE](./LICENSE)。
