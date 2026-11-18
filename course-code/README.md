# 课程项目源码

这里保存课堂资料对应的完整源码快照，便于与课程讲义对照阅读。文件直接取自教师资料工作区，保留额外教学注释；没有对这些项目执行依赖安装或构建。

## 来源

| 项目入口 | 来源（相对教师资料目录） | 文件数 | 大小 |
| --- | --- | ---: | ---: |
| [MiniMind](minimind/) | `MiniMind整理版/源码对照/minimind` | 29 | 0.72 MiB |
| [Pi Agent](pi-agent/) | `OpenClaw/pi-master` | 804 | 13.20 MiB |
| [OpenClaw](openclaw/) | `OpenClaw/OpenClaw-2026.4.22` | 15015 | 113.93 MiB |
| [EasySpider](easyspider/) | `EasySpider` | 346 | 61.88 MiB |

Pi Agent 使用已经确认的 `pi-master`，包版本为 0.69.0。OpenClaw 使用 `OpenClaw-2026.4.22`。文件取自当前工作区，包含本地增加的教学注释；具体基线提交和排除记录见 [sources.json](sources.json)。

MiniMind 按指定整理版目录保留全部 27 个 Python 文件，另从同源 `MiniMind/minimind` 补充 LICENSE 与 requirements.txt。该整理版来源本身没有分词器资源、模型权重和训练数据，这些资源不在本快照中。

## 源码阅读入口

- MiniMind：[模型结构](minimind/model/model_minimind.py)、[数据集](minimind/dataset/lm_dataset.py)、[预训练](minimind/trainer/train_pretrain.py)、[SFT](minimind/trainer/train_full_sft.py)、[PPO](minimind/trainer/train_ppo.py)、[采样引擎](minimind/trainer/rollout_engine.py)。
- Pi Agent：[Agent](pi-agent/packages/agent/src/agent.ts)、[Agent Loop](pi-agent/packages/agent/src/agent-loop.ts)、[会话装配](pi-agent/packages/coding-agent/src/core/sdk.ts)、[AgentSession](pi-agent/packages/coding-agent/src/core/agent-session.ts)、[会话记录](pi-agent/packages/coding-agent/src/core/session-manager.ts)。
- OpenClaw：[工作区与 Bootstrap 文件](openclaw/src/agents/workspace.ts)、[Bootstrap 上下文](openclaw/src/agents/bootstrap-files.ts)、[Skill 加载](openclaw/src/agents/skills/workspace.ts)、[运行尝试入口](openclaw/src/agents/pi-embedded-runner/run/attempt.ts)。
- EasySpider：[扩展 global.js](easyspider/Extension/manifest_v3/src/content-scripts/global.js)、[扩展 main.js](easyspider/Extension/manifest_v3/src/content-scripts/main.js)、[流程图](easyspider/ElectronJS/src/taskGrid/FlowChart.js)、[消息与任务管理](easyspider/ElectronJS/src/taskGrid/logic.js)、[执行器](easyspider/ExecuteStage/easyspider_executestage.py)。EasySpider 收录整个项目的源码，教学注释最明确的候选仍是扩展的 global.js 和 main.js。

## 收录与排除

- 保留源码、构建脚本、依赖声明、锁文件、配置模板、测试、示例、文档及必要静态资源。`generated.ts` 等由上游版本管理的源文件、测试归档、字体和 Gradle wrapper 引导文件仍随源码保留。
- 不收录 `.git`、`node_modules`、依赖缓存、Python 缓存、Gradle 缓存、`dist`、`build` 等本地依赖和应用构建目录。
- 不收录 Pi 的 DOOM 示例 `build/doom.js`、`build/doom.wasm`，以及 OpenClaw 的 `extensions/diffs/assets/viewer-runtime.js`；生成它们的源码和构建脚本保留。
- 不收录 EasySpider 已打包的 `ElectronJS/EasySpider_en`、`ElectronJS/EasySpider_zh` 和 `.crx` 文件。扩展原始代码位于 `Extension/manifest_v3`；本地任务数据库 `ElectronJS/tasks` 也不收录，项目任务示例保留在 `Examples`。
- 原项目忽略配置原文保存为 `.gitignore.upstream`；本文件夹统一用 [.gitignore](.gitignore) 防止误收依赖与构建输出。这样也避免旧忽略规则把当前快照包含的源文件隐藏。

这些是供阅读和自行开发的源码，并非已经安装依赖的运行包。运行具体项目时，按该项目自己的说明准备依赖和外部资源；被排除的应用产物需要自行生成。

## 与课程文档站的关系

本文件夹位于文档站根目录，与 `docs/` 并列；VitePress 不会编译这里的项目，也不会将这些项目的网页和文档自动加入课程站点。文档站本地调试仍使用根目录原有的 `npm run dev` 等命令。

## 许可证

各项目保持各自原有许可证：[MiniMind](minimind/LICENSE)、[Pi Agent](pi-agent/LICENSE)、[OpenClaw](openclaw/LICENSE)、[EasySpider](easyspider/LICENSE)。第三方子项目及静态资源适用其随附许可证。
