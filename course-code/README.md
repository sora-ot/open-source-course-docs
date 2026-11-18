# 课程项目源码

该文件夹内容保存了课堂资料对应的完整源码，便于与课程讲义对照阅读。

## 源码阅读入口

- MiniMind：[模型结构](minimind/model/model_minimind.py)、[数据集](minimind/dataset/lm_dataset.py)、[预训练](minimind/trainer/train_pretrain.py)、[SFT](minimind/trainer/train_full_sft.py)、[PPO](minimind/trainer/train_ppo.py)、[采样引擎](minimind/trainer/rollout_engine.py)。
- Pi Agent：[Agent](pi-agent/packages/agent/src/agent.ts)、[Agent Loop](pi-agent/packages/agent/src/agent-loop.ts)、[会话装配](pi-agent/packages/coding-agent/src/core/sdk.ts)、[AgentSession](pi-agent/packages/coding-agent/src/core/agent-session.ts)、[会话记录](pi-agent/packages/coding-agent/src/core/session-manager.ts)。
- OpenClaw：[工作区与 Bootstrap 文件](openclaw/src/agents/workspace.ts)、[Bootstrap 上下文](openclaw/src/agents/bootstrap-files.ts)、[Skill 加载](openclaw/src/agents/skills/workspace.ts)、[运行尝试入口](openclaw/src/agents/pi-embedded-runner/run/attempt.ts)。
- EasySpider：[扩展 global.js](easyspider/Extension/manifest_v3/src/content-scripts/global.js)、[扩展 main.js](easyspider/Extension/manifest_v3/src/content-scripts/main.js)、[流程图](easyspider/ElectronJS/src/taskGrid/FlowChart.js)、[消息与任务管理](easyspider/ElectronJS/src/taskGrid/logic.js)、[执行器](easyspider/ExecuteStage/easyspider_executestage.py)。EasySpider 收录整个项目的源码，教学注释最明确的候选仍是扩展的 global.js 和 main.js。

## 许可证

各项目保持各自原有许可证：[MiniMind](minimind/LICENSE)、[Pi Agent](pi-agent/LICENSE)、[OpenClaw](openclaw/LICENSE)、[EasySpider](easyspider/LICENSE)。第三方子项目及静态资源适用其随附许可证。
