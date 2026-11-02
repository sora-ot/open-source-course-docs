---
title: "10 · Bootstrap、Skill 与 Extension"
description: "openclaw · 会话与上下文 · 课程讲义"
project: "openclaw"
sourcePath: "OpenClaw/OpenClaw-Course/10_Bootstrap、Skill与Extension加载原理完整讲义.md"
originalUrl: "/originals/openclaw/chapter-10.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 10 Bootstrap、Skill 与 Extension 加载原理完整讲义：从文件到上下文与运行能力

### 先理解概念：Bootstrap 是什么

**Bootstrap 通常译为“引导”或“启动准备”。在本讲中，它具体指：在 Agent 执行本次任务之前，由宿主程序发现、读取并整理工作环境中的基础资料，再将这些资料注入模型上下文的过程。** 这里的宿主程序，就是组织 Agent 运行的 OpenClaw 或独立 Pi 程序。

为什么需要这一步？用户可能只输入“帮我选一份午饭”，但模型还需要知道“这个助手怎样工作”“用户有哪些偏好”“项目有哪些约定”。这些长期适用的信息可以保存在工作目录的文件里，由程序准备模型输入时统一加载，不必让用户每次重新输入。

#### 开头例子：一个午饭助手会涉及哪些文件

下面先把 OpenClaw 一侧可能涉及的文件放在同一个 Workspace 中认识。**这是文件用途的完整教学示意，不要求所有文件同时存在，也不表示所有文件每次都会进入模型输入。** 本节以本地 `OpenClaw-2026.4.22` 的实现为准。

```text
lunch-workspace/
├── AGENTS.md                 # 工作约定：处理任务时遵循哪些规则
├── SOUL.md                   # 行为风格：怎样与用户交流、怎样做事
├── TOOLS.md                  # 本地工具备注：环境中的名称、别名和使用注意事项
├── IDENTITY.md               # 助手身份：名字、形象、标识等
├── USER.md                   # 用户资料：称呼、时区、长期偏好等
├── HEARTBEAT.md              # 心跳检查清单：周期唤醒时关注哪些事情
├── BOOTSTRAP.md              # 首次使用引导：建立身份与用户资料，完成后可删除
├── MEMORY.md                 # 整理后的长期记忆
├── memory.md                 # MEMORY.md 不存在时尝试的备用文件名
├── BOOT.md                   # 相关启动文件：由 boot-md Hook 在 Gateway 启动时处理
├── memory/
│   └── 2026-10-27.md         # 每日记忆；不在默认 Bootstrap 候选列表中
├── packages/
│   └── canteen/
│       ├── AGENTS.md         # 子目录工作约定；可配置额外 Bootstrap Hook 加载
│       └── TOOLS.md          # 子目录工具备注；同上
└── .openclaw/
    └── workspace-state.json  # 程序记录首次引导状态；不作为提示词正文注入
```

**先看默认 Bootstrap 候选文件。** 前七个文件名固定列入候选；长期记忆另按存在情况选择 `MEMORY.md` 或 `memory.md`。各文件的典型分工与午饭例子如下：

| 文件 | 主要回答什么问题 | 本例可以写入的内容 |
|---|---|---|
| `AGENTS.md` | 这个工作环境中，处理任务应遵守哪些约定？ | “推荐之前核对价格与库存；没有用户明确授权，不要下单；结尾说明是否已经下单。” |
| `SOUL.md` | 助手应以怎样的风格和原则行动？ | “像一位简洁、耐心的午饭顾问；先给结论；不知道库存时明确说明，不编造。” |
| `TOOLS.md` | 本地环境中的工具名称、对象和约定是什么？ | “食堂别名 `east` 表示东区食堂；菜单查询结果中的价格单位为元。”这些只是环境备注，实际工具还需要程序注册。 |
| `IDENTITY.md` | 助手是谁？ | “名字：午饭小助；身份：校园午饭助手；标识：🍱。”它偏重身份记录，`SOUL.md` 偏重行为方式。 |
| `USER.md` | 服务的用户是谁，有什么相对稳定的偏好？ | “称呼：王老师；时区：Asia/Shanghai；平时偏好不辣，喜欢简短回答。”本次明确提出的新要求仍需结合当前用户消息判断。 |
| `HEARTBEAT.md` | 心跳唤醒时应检查什么？ | “检查今天午间预订是否有待确认事项；没有需要处理的事项时按心跳约定回复。”检查时间与心跳启用状态由运行配置决定，写入清单本身不创建定时器。 |
| `BOOTSTRAP.md` | 首次使用时还要完成哪些设置？ | “先与用户确定助手名字、称呼和口味偏好，更新 `IDENTITY.md`、`USER.md`，设置完成后删除本文件。”它是首次引导的说明文本。 |
| `MEMORY.md` | 哪些过往事实与决定值得长期保留？ | “用户上次确认喜欢东区食堂的清淡套餐；鸡腿饭曾获得好评。”它保存整理后的经验，实时库存和价格仍以本次查询为准。 |
| `memory.md` | 没有大写长期记忆文件时，使用哪个名字？ | 用途与 `MEMORY.md` 相同，是备用文件名。默认解析先检查 `MEMORY.md`，找到后就不再另选 `memory.md`；在大小写不敏感的文件系统上，两种拼写可能指向同一文件。 |

这些职责是便于维护的内容约定。程序主要按文件名、路径和运行条件加载正文，并不会为每个文件分别执行一种业务函数。特别是，`TOOLS.md` 里的文字不会自动注册工具，`HEARTBEAT.md` 里的文字也不会自动建立调度任务。

默认候选的源码入口见 [loadWorkspaceBootstrapFiles](/source/?file=1bbb045d02c254e25a.ts#L511)，长期记忆文件名的选择见 [resolveMemoryBootstrapEntry](/source/?file=1bbb045d02c254e25a.ts#L490)。

**再看与启动或上下文有关、但加载路径不同的文件。** 它们也画在上面的例子里，阅读源码时需要追踪各自入口：

| 文件或路径 | 用途与加载条件 |
|---|---|
| `packages/canteen/AGENTS.md`、`packages/canteen/TOOLS.md` | 默认 Workspace 加载器只列出根目录候选，不递归收集所有子目录文件。启用并配置 `bootstrap-extra-files` Hook 后，可以用 `packages/*/AGENTS.md` 等路径模式追加。这一内置 Hook 只接受上表中的已识别文件名，并要求解析后的文件仍位于 Workspace 内。自定义 Bootstrap Hook 还可以修改候选集合，需看具体实现。 |
| `memory/2026-10-27.md` 等每日记忆 | 保存当天的原始记录。默认 Bootstrap 候选列表不会自动扫描 `memory/` 并注入全部日志；是否已由其他运行路径提供，或需要模型借助工具继续读取，要检查实际上下文。内置额外文件 Hook 也不会仅凭通配符就接受 `2026-10-27.md` 这个文件名。 |
| `BOOT.md` | 配置启用 `boot-md` Hook 后，在 Gateway 启动事件中触发一次启动检查任务，按文件内容运行。它既不同于首次设置用的 `BOOTSTRAP.md`，也不在上述默认 Bootstrap 候选列表中。 |
| `.openclaw/workspace-state.json` | 供程序记录首次引导文件的创建时间、设置完成时间等状态，帮助判断是否还需要首次引导。它属于状态数据，不作为基础资料正文拼进 system prompt。 |

额外文件的规则见 [bootstrap-extra-files Hook](/source/?file=840da0b3aa00bcc2e5.md)，Gateway 启动任务见 [boot-md Hook](/source/?file=04931923b98b7c82e2.md)。后文的 `skills/choose-lunch/SKILL.md` 与 `.pi/extensions/lunch.ts` 分别属于 Skill、Extension 加载路径，在课堂主线中单独展开。

**“是候选文件”还不等于“这一次一定注入”。** 会话类型、运行模式、Hook、文件是否存在、字符预算与缓存都会影响最终结果。例如，本地 subagent / Cron 会话的基础筛选保留 `AGENTS.md`、`TOOLS.md`、`SOUL.md`、`IDENTITY.md`、`USER.md`；轻量上下文模式还会继续过滤。这里先认识文件，后文再逐步跟踪这些条件。

#### 先单独讲清楚：BOOTSTRAP.md 是首次使用时的设置说明书

**`BOOTSTRAP.md` 是放在 OpenClaw Workspace 根目录中的 Markdown 文件，里面写的是“这个助手刚建立时，先与用户确认哪些信息，再把确认结果保存到哪里”。** 可以把它理解成助手第一次使用时的设置说明书：先确定“我是谁、为谁服务、怎样交流”，再开始日常工作。它的文件名虽然叫 Bootstrap，但它只是整个 Bootstrap 加载流程可能读取的一份资料。

为什么已经有 `IDENTITY.md`、`USER.md`、`SOUL.md`，还需要它？因为刚创建工作区时，这些文件通常只有默认模板，尚未填入真实信息。**`BOOTSTRAP.md` 说明“怎样完成设置”；另外三个文件保存“设置完成后得到的身份、用户资料和行为约定”。** 前者通常在完成设置后删除，后者继续保留，供日常运行使用。

##### 先看例子：第一次见面时，输入和输出分别是什么

假设刚建立了午饭助手的工作区，助手还没有名字，也不知道用户怎样称呼、喜欢什么口味。为了把流程讲清楚，可以把 `BOOTSTRAP.md` 写成下面这样；这是根据官方模板用途改写的教学示例，不是模板原文：

```markdown
# 午饭助手首次设置

先自然地与用户交谈，确认以下信息；用户已经说明的内容不要重复询问：
1. 助手叫什么名字，以什么身份帮助用户。
2. 用户希望怎样被称呼，使用哪个时区，有哪些长期口味偏好。
3. 用户希望回答简短还是详细，处理午饭任务有哪些边界。

把确认的助手身份写入 IDENTITY.md，把用户资料写入 USER.md。
与用户确认交流风格和行为原则后，更新 SOUL.md。
设置完成后删除本 BOOTSTRAP.md，保留刚才填写的资料文件。
```

用户第一次输入：

> 你叫午饭小助，是我的校园午饭助手。叫我王老师，时区是上海。我平时不吃辣，回答简短一点；没有我的明确授权不要下单。

这次设置的**输入**是：`BOOTSTRAP.md` 的引导要求、已有资料文件，以及用户提供的真实信息。助手结合这些输入，必要时继续确认缺失的信息，再通过可用的文件工具保存。设置成功后的**输出**是磁盘中的资料变化，例如：

```text
IDENTITY.md  → 名字：午饭小助；身份：校园午饭助手。
USER.md      → 称呼：王老师；时区：Asia/Shanghai；长期偏好：不辣。
SOUL.md      → 回答简短；没有用户明确授权，不下单。
BOOTSTRAP.md → 完成设置后删除。
```

这些写入结果是便于理解的内容示意，实际编辑时应保留文件中仍然适用的其他内容。助手在对话中回复“设置好了”还不够，必须确认相应写入、编辑和删除操作确实成功。**`BOOTSTRAP.md` 自己不会写文件，也不会自行删除；模型决定如何按说明处理，宿主执行实际的工具操作。** 如果当前运行缺少正常工作区访问或所需工具，就应说明哪些设置尚未完成，不能宣称已经保存。

下一次用户说“帮我选午饭”时，助手可以从保留下来的资料中得知“称呼王老师、偏好不辣、回答简短”。这时不需要重新执行初次见面的问答。`BOOTSTRAP.md` 已经完成使命，而加载其他工作环境资料的 Bootstrap 流程仍然存在。

##### 文件从哪里来，程序又怎样让模型看到它

下面把“创建说明书”和“按说明书完成设置”分成两个阶段：

```text
阶段一：程序准备文件，不需要调用模型
OpenClaw 初始化 Workspace，启用 ensureBootstrapFiles
    ↓ ensureAgentWorkspace()
创建缺失的基础资料文件，并检查首次设置状态
    ↓ 需要首次引导时，读取软件随附的 BOOTSTRAP.md 模板
写入 Workspace/BOOTSTRAP.md，记录 bootstrapSeededAt

阶段二：模型结合用户交互完成设置
宿主准备一次适合首次设置的交互运行
    ↓ 默认候选列表包含 BOOTSTRAP.md
按会话、模式、Hook 与预算规则整理上下文，供模型读取
    ↓ 首次引导模式还会提供“先读 BOOTSTRAP.md 并按其完成设置”的提示
模型与用户确认身份、资料和风格
    ↓ 文件工具成功执行编辑与删除
保留 IDENTITY.md / USER.md / SOUL.md，删除 BOOTSTRAP.md
    ↓ 后续 ensureAgentWorkspace() 检查引导记录及文件状态
已记录创建且引导文件已不存在时，记录 setupCompletedAt
```

软件随附的模板位于 [docs/reference/templates/BOOTSTRAP.md](/source/?file=ab1e6a853cdca9470c.md)，初始化逻辑位于 [ensureAgentWorkspace](/source/?file=1bbb045d02c254e25a.ts#L347)。实际使用的是 Workspace 中的那份文件，用户也可以直接编辑它；并不是每次运行都从软件模板覆盖工作区内容。程序还会识别已有用户资料等设置迹象，避免给已经配置过的工作区重新创建首次引导文件。

上面的第二阶段描述正常的首次交互路径，**不代表所有会话都会完整注入并执行首次设置**。例如子代理与轻量模式会筛选上下文，受限运行也可能只能提示稍后完成。首次引导提示的组装可看 [buildAgentUserPromptPrefix](/source/?file=320774609bbc40c9fc.ts#L192)。状态文件主要记录程序观察到的设置状态，并不表示程序已经逐项验证资料填写正确。

##### 与前面几个名字的关系

| 名称 | 在这个例子中的含义 |
|---|---|
| Bootstrap 加载流程 | 程序为模型读取、整理工作环境资料的过程，后续正常运行仍会用到。 |
| `BOOTSTRAP.md` | 首次设置的说明书：引导对话、填写身份与用户资料，完成后通常删除。它不是完整的 system prompt；正文可作为上下文的一部分提供给模型。 |
| `IDENTITY.md` / `USER.md` / `SOUL.md` | 首次设置后继续保留的资料：分别记录助手身份、用户信息和行为风格。 |
| `BOOT.md` | Gateway 服务启动时可触发的任务清单，例如检查菜单是否就绪。由启用的 `boot-md` Hook 处理，不负责首次认识用户。 |

**一句话记住：`BOOTSTRAP.md` 告诉助手“第一次怎样把自己和用户的资料设置好”；完成设置后留下的是资料文件，后续启动检查则由另一份 `BOOT.md` 描述。**

#### 单独说明：BOOT.md 是 Gateway 启动时交给助手的任务清单

**`BOOT.md` 是一个可选的 Markdown 文件，用来描述“OpenClaw Gateway 启动后，希望助手先做哪些检查或准备工作”。** Gateway 是承载 OpenClaw 渠道接入与运行调度等功能的网关服务。这里的“启动”指这个服务启动，并非用户每发送一条消息就执行一次。

例如，午饭助手的服务重启后，你希望它先检查工作资料和菜单文件是否齐全，再写一份本地检查结果，就可以在 Workspace 根目录创建 `BOOT.md`：

```markdown
# 午饭助手启动检查

1. 检查工作目录中是否存在 AGENTS.md 和 USER.md。
2. 检查 menus/today.json 是否存在；存在时读取，不存在时记录“菜单尚未准备”。
3. 把上述检查结果写入 reports/startup-status.md，目录不存在时先创建。
4. 这里只做资料检查与本地记录，不提交午饭订单，不发送对外通知。
```

这些是给模型阅读的自然语言任务要求。模型理解后，可以调用文件读取、目录创建、文件写入等可用工具完成任务；`BOOT.md` 本身不会被当作 Shell 脚本执行。示例中的路径是教学约定，实际文件操作仍依赖工具可用性和执行结果。

**创建文件后，还需要启用并加载 `boot-md` Hook，启动检查才会由这条机制触发。** 本地源码的调用链是：

```text
Gateway 启动，产生 gateway:startup 事件
    ↓ 已启用的 boot-md Hook 收到事件
对配置中的各个 Agent 解析其 Workspace
    ↓ runBootOnce()
读取对应 Workspace 根目录下的 BOOT.md
    ├── 不存在或去除空白后为空 → 跳过启动检查
    └── 有内容 → buildBootPrompt() 将正文组装为启动检查任务消息
                    ↓ agentCommand({ message, ... })
                发起一次 Agent 运行，模型按任务内容选择工具并处理
```

`BOOT.md` 的正文在这里被组装成启动任务消息，并非作为默认 Bootstrap 文件拼入每次运行的 system prompt。它通常由用户或维护者编写，也可让助手协助生成；保留文件后，后续 Gateway 再次启动仍可触发，不能把 `runBootOnce` 理解为整个安装生命周期只执行一次。源码按大写文件名 `BOOT.md` 查找，跨平台使用时应保持这个拼写。

| 容易混淆的名称 | 各自解决什么问题 | 何时发挥作用 |
|---|---|---|
| Bootstrap 加载流程 | 为模型准备工作环境资料 | 宿主准备本次运行的上下文时 |
| `BOOTSTRAP.md` | 首次使用时建立助手身份、用户资料等 | 首次设置尚未完成时；完成后通常删除 |
| `BOOT.md` | 服务启动后，希望助手先完成哪些任务 | 已启用的 `boot-md` Hook 处理 Gateway 启动事件时 |
| `HEARTBEAT.md` | 周期唤醒时，希望助手检查哪些事情 | 心跳机制按配置触发时 |

可以把午饭例子串起来理解：首次配置用 `BOOTSTRAP.md` 确定“你叫午饭小助”；每次服务启动可按 `BOOT.md` 检查“菜单文件准备好了吗”；正常处理任务时加载 `AGENTS.md` 等工作约定；周期巡检再参考 `HEARTBEAT.md`。

对应源码见 [boot-md/handler.ts](/source/?file=202a21206a56915919.ts) 和 [gateway/boot.ts](/source/?file=0cb8b37b92285d1e02.ts)。

#### 这些文件是怎么来的：程序、用户和大模型各做什么

**这些文件可以由程序从模板创建，也可以由用户直接编写，还可以由模型根据交互内容提出写入操作、再由工具执行。** 要把“最初的文件框架从哪里来”“后来的具体内容由谁提供”“谁真正把内容保存到磁盘”分开理解。同一个文件在不同阶段可以有不同来源。

**第一步：初始化程序从已有模板创建基础文件，这一步不需要调用大模型。** 本地 OpenClaw 的 [ensureAgentWorkspace](/source/?file=1bbb045d02c254e25a.ts#L347) 在 `ensureBootstrapFiles` 启用时，读取随项目提供的模板，去掉模板的文档元信息，再创建缺失的基础文件：

```text
项目随附的 docs/reference/templates/*.md
    ↓ 初始化程序读取模板正文，无需请求大模型
Workspace 中缺失的基础文件
    ├── AGENTS.md
    ├── SOUL.md
    ├── TOOLS.md
    ├── IDENTITY.md
    ├── USER.md
    └── HEARTBEAT.md

首次引导尚未建立、且工作区未被判定为已经完成设置时
    └── 另从模板创建 BOOTSTRAP.md
```

这里的“自动创建”主要是把软件随附的默认正文或待填写框架写入 Workspace。例如，`USER.md` 模板有称呼、时区等字段，但初始化程序不会凭空知道真实用户的口味。写文件使用“仅在缺失时创建”的逻辑，已有文件会保留；是否需要 `BOOTSTRAP.md` 还会参考引导状态和已有用户内容，不能理解成每次启动都重新生成一套文件。`MEMORY.md`、每日记忆和 `BOOT.md` 不属于这段初始化代码统一创建的基础文件。

**第二步：用户提供真实信息，用户或模型再把信息补进文件。** 例如首次交互中，用户说：

> 你叫午饭小助。我姓王，叫我王老师就行。我平时不吃辣，回答简短一点。

按照 [BOOTSTRAP.md 模板](/source/?file=ab1e6a853cdca9470c.md) 的引导，助手可以把名字整理进 `IDENTITY.md`，把称呼和口味偏好整理进 `USER.md`，再与用户讨论并更新 `SOUL.md`。用户也可以直接在编辑器里填写这些内容。模板只是告诉模型怎样完成设置；它不会自行执行文件修改。

如果由模型协助保存，实际路径是：

```text
用户在对话中提供信息或提出修改要求
    ↓ 模型结合上下文整理内容，选择目标文件
模型提出文件写入 / 编辑工具调用
    ↓ 宿主执行可用且获准的工具操作
文件实际写入成功
    ↓ 后续运行按加载与缓存规则读取保存后的内容
```

因此，模型在聊天里说“我记住了”，或者展示一段拟写内容，并不等于文件已经保存。要判断是否真正持久化，需要看到写入工具或其他保存程序成功执行；后续何时采用新内容，还取决于资源刷新和缓存。

**第三步：日常使用中，不同文件由不同方式维护。** 对照前面的午饭例子，可以这样理解：

| 文件 | 初始来源与后续维护方式 |
|---|---|
| `AGENTS.md`、`SOUL.md` | 可以先使用软件模板；用户、项目维护者可直接修改，也可以要求助手通过编辑工具调整工作约定或行为风格。 |
| `TOOLS.md` | 可以先使用模板；本地名称、别名、设备与工具使用备注由用户或维护者补充，助手也可根据已确认的环境信息协助整理。 |
| `IDENTITY.md`、`USER.md` | 可以先创建待填写的模板；具体身份、称呼和偏好通常在首次交互及后续使用中补充，既可手填，也可由助手通过工具保存。 |
| `HEARTBEAT.md` | 可以先使用模板；具体检查清单由用户设置，或由助手按用户要求写入。文件内容与运行配置共同决定怎样开展心跳检查。 |
| `BOOTSTRAP.md` | 需要首次引导时由程序从模板创建；助手按说明与用户完成设置后，可以通过工具删除，用户也可手动处理。删除动作本身不是文件中的文字自动执行的。 |
| `MEMORY.md` / `memory.md` | 由用户或助手逐步创建、整理长期事实与决定；没有相关写入过程时，文件可以一直不存在。默认 Bootstrap 加载器只尝试读取，不替模型总结并生成长期记忆。 |
| `memory/YYYY-MM-DD.md` 等记忆记录 | 可以由用户手写，或由助手在任务与记忆保存流程中通过工具追加；启用的 Hook 也可能直接生成其他命名形式的记忆文件。具体来源需看执行路径。 |
| `BOOT.md` | 可由用户或维护者编写，也可让助手协助创建；启用的 `boot-md` Hook 负责读取并触发启动任务，不代表它会自动替用户设计这份清单。 |
| 子目录中的 `AGENTS.md`、`TOOLS.md` | 通常由对应项目的维护者提供，也可由助手协助编写；`bootstrap-extra-files` Hook 负责按配置发现和加载已有文件，不负责生成这些文件的业务内容。 |
| `.openclaw/workspace-state.json` | 由程序记录和更新引导状态。时间戳、版本号等属于运行状态数据，不需要大模型生成。 |

还有一种值得区分的混合情况：本地 [session-memory Hook](/source/?file=6dc25f362388df5d0a.ts) 在启用并收到 `/new` 或 `/reset` 事件时，可以读取近期会话，由程序组装正文并写入 `memory/日期-短名.md`。其中短名可由大模型生成，也可以退回时间标记。**模型参与文件名生成，不等于整篇文件正文都是模型重新总结出来的。**

本讲后面的午饭样例内容是为教学预先编写的；实际使用时，模板提供初始结构，用户与项目提供具体事实和要求，模型可以协助整理，程序和工具负责保存，Bootstrap 加载流程再读取这些文件。独立 Pi 的项目上下文加载器负责发现已有的 `AGENTS.md` / `CLAUDE.md`，也不能仅凭“支持读取这些名字”就推断它会自动生成项目规则。

#### 这些文件怎样变成模型输入

Bootstrap 加载流程按候选文件规则取得资料，经过筛选和长度预算处理，生成上下文文本；随后，系统提示词构建程序把这些文本放入最终 system prompt，供本次运行中的模型请求使用。

```text
工作环境中的基础资料文件
    ↓ 宿主程序发现、读取、筛选，并按预算整理
上下文文件列表 [{ path, content }, ...]
    ↓ 系统提示词构建程序组装
最终 system prompt
    ↓ 与用户消息、工具定义等一起构成模型请求
模型结合工作约定与用户需求处理任务
```

**因此，Bootstrap 是准备上下文的程序过程；`AGENTS.md` 等文件是这个过程的输入，整理后的上下文文本是它的输出。** `BOOTSTRAP.md` 则只是 OpenClaw 的候选文件之一，通常用于首次使用时的初始化引导；即使首次设置完成后删除了这个文件，后续运行仍然需要准备其他基础资料。

本讲会分别跟踪两套实现：**OpenClaw 有自己的 Bootstrap 文件加载流程；独立 Pi 通过项目上下文加载器读取 `AGENTS.md` / `CLAUDE.md`，再拼入 system prompt。** 两者都能为模型补充环境资料，但文件发现规则和调用路径需要分别看源码。

> 阅读顺序：先理解开头的 Bootstrap 与文件用途，再读 A.1～A.6 的完整材料；A.7～A.13 集中用例子说明运行过程，先不进入实现。理解输入输出后，再从 B 节开始统一看代码与调用栈。
>
> **第一部分 A：完整文件，以及 Bootstrap、Skill、Extension 的连续运行例子。**  
> **第二部分 B～F：资源准备、运行循环、命令展开与 OpenClaw 的源码调用链。**  
> **第三、四部分：加载算法、边界核对，以及 Bootstrap、Skill、Extension 的源码定位索引。**
>
> 最核心的一句话是：
>
> **Bootstrap 把工作环境资料送进上下文；Skill 让模型按需取得做事方法；Extension 把处理函数和工具注册到运行程序。**

第 09 讲已经说明会话历史怎样保存和恢复。接下来先看历史之外的输入：项目规则、Skill 和 Extension 从哪些文件加载，怎样影响上下文与运行能力。下一讲再加入跨会话的长期记忆；第 13 讲把这些资源与模型、工具、历史装配起来，第 14 讲展开会话执行。

Bootstrap 主线以本地 `OpenClaw-2026.4.22` 为准；Pi 的 Skill、Extension 主线以 `pi-master` 为准。两层分别说明，不能假定 OpenClaw 原样启用了 Pi 的全部默认资源发现路径。

文中的目录、午饭工具和文件内容是教学数据。`SKILL.md` 是资源样例，Extension 样例需要放在对应 Pi 项目环境中使用；本文不会实际加载这些样例或请求模型。

---

## 第一部分：完整文件与运行例子

先读本节的完整工程，再从 A.7 开始只用例子走完准备与运行过程。午饭任务采用 **独立 Pi** 做 Skill、Extension 主线；A.8 单独用 OpenClaw 展示 Bootstrap 的候选与预算。两套宿主分别说明，源码与调用栈统一从 B 节开始。

本讲先把 `session.prompt(...)` 当作“宿主把用户输入交给会话”的使用入口，观察文件加载前后的内容变化。例子会给出所需创建代码；AgentSession 的完整装配放在第 13 讲，`prompt()` 的检查、排队与执行分支放在第 14 讲。

### A. 完整例子：用户究竟输入什么，项目里究竟有什么

假设工程绝对路径是 `/work/lunch-project`。Windows 上用自己的绝对路径替换它即可。

```text
lunch-project/
├── AGENTS.md                         # Pi 自动收集的项目上下文
└── .pi/
    ├── prompts/
    │   └── lunch.md                   # /lunch 命令对应的 Prompt 模板
    ├── skills/
    │   └── choose-lunch/
    │       └── SKILL.md               # 方法说明，不是 JS 函数
    └── extensions/
        └── lunch.ts                   # 真正的工具函数和拦截函数
```

本例的菜单固定为教学数据：牛肉面 A，18 元、辣、有货；鸡腿饭 B，22 元、不辣、有货；蛋炒饭 C，10 元、不辣、有货。真实产品应把工具实现替换成实际查询接口。

#### A.1 用户输入的 prompt

先用普通输入贯穿全文：

```text
帮我找不辣、20 元以内的午饭，先给方案，不要下单。
```

对应 SDK 调用是：

```ts
await session.prompt("帮我找不辣、20 元以内的午饭，先给方案，不要下单。");
```

这里的 `session` 是 `createAgentSession()` 返回的 `AgentSession`，不是 `SessionManager`。前者处理本次输入和运行，后者负责会话树与持久化。

#### A.2 完整的项目上下文 AGENTS.md

文件：`/work/lunch-project/AGENTS.md`。

```markdown
# 午饭助手工作约定

你负责查询和比较午饭，回答使用中文。
遇到午饭推荐任务，先查阅可用的 choose-lunch 技能，按其中的方法处理。
价格、口味、库存以工具本次返回的数据为准，不要编造。
没有用户明确授权，不要下单。
最终回答给出菜名、价格、筛选理由及是否已经下单。
```

这是 Pi 的项目上下文资源。Pi 默认识别各层目录里的 `AGENTS.md` 或 `CLAUDE.md`；**不会因为旁边放了 `SOUL.md`、`USER.md`，就自动采用 OpenClaw 的那套候选文件规则**。

> **`AGENTS.md` 是面向 Agent 的持久化项目指令文件。框架负责读取它，并将其正文注入模型上下文。在当前 Pi 实现中，正文被拼入 system prompt 的 Project Context 部分；其他框架可能采用不同的消息角色与加载方式。**

#### A.3 完整的 Prompt 模板 lunch.md

文件：`/work/lunch-project/.pi/prompts/lunch.md`。

**这份模板由本讲预先编写，实际项目中由用户或维护者创建。Pi 加载这个文件后，才有本例的 `/lunch` 模板入口；它不是系统内置的午饭命令，也不是发现 Skill 后自动生成的。** 文件名 `lunch.md` 决定模板名称 `lunch`，正文决定展开后的任务文字。A.9.2 会把文件来源、加载、填参和发给模型的全过程放在一起说明。

```markdown
---
description: 根据口味和预算给出午饭方案
---
请帮我选择午饭。
口味要求：$1。
预算上限：$2 元。
附加要求：${@:3}。
先查阅 choose-lunch 技能，再查询和比较。最终说明是否下单。
```

用户也可以输入：

```text
/lunch 不辣 20 "先给方案，不要下单"
```

模板展开后的用户消息正文是：

```text
请帮我选择午饭。
口味要求：不辣。
预算上限：20 元。
附加要求：先给方案，不要下单。
先查阅 choose-lunch 技能，再查询和比较。最终说明是否下单。
```

Frontmatter 的 `description` 用于模板元数据；模型收到的是展开后的正文。模板文件名决定这里的 `lunch` 命令名。

#### A.4 完整的 Skill 文件

文件：`/work/lunch-project/.pi/skills/choose-lunch/SKILL.md`。

```markdown
---
name: choose-lunch
description: 当用户要求选择或比较午饭时，按口味、预算和库存筛选候选，给出方案。
---

# 选择午饭

## 输入
从用户本次消息取得口味、预算和是否授权下单；缺少关键条件时再询问。

## 步骤
1. 调用 list_meals 获取本次菜单中的 id、name、price、spicy。
2. 按当前用户的口味和预算排除不符合的候选。
3. 调用 get_stock，传入通过筛选的候选 id 列表。
4. 在有货的候选中选择价格最低的一项；同价时说明可选项。
5. 给出菜名、价格、口味、库存及筛选理由。
6. 用户只要求方案时，到此结束，不调用 place_order。

## 异常
工具失败或没有候选时明确说明，不把未知价格或未知库存补成确定值。

## 输出示例
推荐蛋炒饭：10 元、不辣、有货，符合 20 元预算。尚未下单。
```

`description` 帮助模型判断何时读它；正文告诉模型读完后怎么做。`list_meals` 等名字只是对工具的引用，Skill 加载器不会由这些文字自动生成工具。

#### A.5 完整的 Extension：把三个工具和拦截器都写出来

文件：`/work/lunch-project/.pi/extensions/lunch.ts`。

下面沿用本地 [hello.ts 扩展示例](/source/?file=fcf958bd02dabfc044.ts) 的 `Type`、`defineTool` 和 `ExtensionAPI` 写法。菜单和库存都在内存中，`place_order` 只是演示工具；没有外部下单接口。

```ts
import { Type } from "@mariozechner/pi-ai";
import { defineTool, type ExtensionAPI } from "@mariozechner/pi-coding-agent";

const meals = [
  { id: "A", name: "牛肉面", price: 18, spicy: true },
  { id: "B", name: "鸡腿饭", price: 22, spicy: false },
  { id: "C", name: "蛋炒饭", price: 10, spicy: false },
];
const stock: Record<string, number> = { A: 8, B: 6, C: 12 };

export default function (pi: ExtensionAPI) {
  // 加载时保存这三个工具定义；此刻没有执行查询。
  pi.registerTool(defineTool({
    name: "list_meals",
    label: "查询午饭菜单",
    description: "返回教学菜单中的 id、菜名、价格和是否辣。",
    parameters: Type.Object({}),
    async execute(_toolCallId, _params, _signal, _onUpdate, _ctx) {
      return {
        content: [{ type: "text", text: JSON.stringify(meals) }],
        details: { meals },
      };
    },
  }));

  pi.registerTool(defineTool({
    name: "get_stock",
    label: "查询午饭库存",
    description: "按候选 id 返回教学库存；null 表示未知。",
    parameters: Type.Object({ ids: Type.Array(Type.String()) }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      const items = params.ids.map((id) => ({ id, stock: stock[id] ?? null }));
      return {
        content: [{ type: "text", text: JSON.stringify(items) }],
        details: { items },
      };
    },
  }));

  pi.registerTool(defineTool({
    name: "place_order",
    label: "演示下单",
    description: "演示订单接口；本课扩展会在执行前阻止此工具。",
    parameters: Type.Object({ mealId: Type.String() }),
    async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
      return {
        content: [{ type: "text", text: `演示订单：${params.mealId}` }],
        details: { mealId: params.mealId },
      };
    },
  }));

  // 加载时登记函数引用；运行时发生工具调用，Runner 才调用它。
  pi.on("tool_call", async (event) => {
    if (event.toolName === "place_order") {
      return { block: true, reason: "课堂演示只提供方案，不允许下单。" };
    }
  });
}
```

模型能看到工具的名字、描述、参数 Schema；看不到上述 `execute` 函数的 JavaScript 实现。函数保存在宿主进程中，由 AgentLoop 选择并执行。工具返回的 `content` 才进入后续模型上下文；`details` 用于结构化信息和宿主展示，不应依赖它代替模型可读的 `content`。

#### A.6 从 SDK 启动这个例子

假设已安装与本地源码 API 一致的 Pi 包、TypeScript 执行环境，并配置好模型及认证。在工程目录执行下面的 TypeScript 入口；当前工作目录必须是上面的 `lunch-project`。

```ts
import { createAgentSession } from "@mariozechner/pi-coding-agent";

const { session, extensionsResult } = await createAgentSession({
  cwd: process.cwd(),
});

try {
  if (extensionsResult.errors.length > 0) {
    throw new Error(JSON.stringify(extensionsResult.errors));
  }
  console.log("技能：", session.resourceLoader.getSkills().skills);
  console.log("活跃工具：", session.getActiveToolNames());
  console.log("系统提示词：", session.systemPrompt);

  session.subscribe((event) => {
    if (event.type === "tool_execution_start") {
      console.log("工具开始：", event.toolName, event.args);
    }
    if (event.type === "message_end") {
      console.log("消息完成：", JSON.stringify(event.message));
    }
  });

  await session.prompt("帮我找不辣、20 元以内的午饭，先给方案，不要下单。");
} finally {
  session.dispose();
}
```

这是完整的教学调用方式，本文没有实际请求模型。真实模型的工具选择和轮次数可能变化；后文展示一条符合 Skill 的预期轨迹。

还可以把最后一次输入分别换成 `/lunch 不辣 20 "先给方案，不要下单"` 或 `/skill:choose-lunch 不辣，20 元以内，先给方案，不要下单`。A.9 会完整展示用户主动介绍并使用技能的对话、模型与工具的消息交接，以及它与两种命令入口的区别；D 节统一进入输入展开的实现。

### A.7 先看准备结果：文件都在，助手就已经会选午饭了吗

从这里到 A.13，先把例子跑通，不进入源码、不背函数名。A.5、A.6 已经给出的实现暂时当作准备好的材料；代码怎样登记、查找和调用，留到 B～F 统一追踪。

先固定条件：独立 Pi 使用 A 节的项目，新建没有旧消息的会话，模型和认证已配置，没有其他同名资源，也没有额外的工具白名单限制。程序先准备会话，用户随后才提交午饭任务。

| 准备时读到的材料 | 准备阶段交出什么 | 模型什么时候看到，或程序什么时候使用 |
|---|---|---|
| `AGENTS.md` | 带来源位置的工作约定正文 | 正文放入系统提示词，随请求提供给模型 |
| `lunch.md` 提示词模板 | 一份尚未填入口味、预算的模板 | 用户输入 `/lunch ...` 后，宿主填入参数，再作为用户消息发送 |
| `choose-lunch/SKILL.md` | 技能的名称、描述和文件位置等说明信息 | 先形成技能目录；模型需要方法时再请求正文，或用户显式指定后由宿主展开 |
| `lunch.ts` 扩展 | 三个工具，以及工具执行前的下单检查 | 工具说明可以提供给模型；执行函数和检查函数留在宿主，等触发时调用 |

本例准备好以后，模型可以使用 `read`、`bash`、`edit`、`write` 以及 `list_meals`、`get_stock`、`place_order`。这七项是本例条件下的活跃工具，不是所有宿主都固定具备的清单。菜单、库存还没有查询，午饭答案也还没有生成。

**准备阶段的输入是目录、配置与资源文件；输出是能接收任务的会话，以及已经装配好的提示词、技能目录、模板和工具。** 模型尚未读到选餐 Skill 的六个步骤；程序读过技能文件以整理目录，不等于已经把方法全文交给模型。

下面先用 OpenClaw 讲 Bootstrap 的加载范围和预算，再回到独立 Pi 讲 Skill 与 Extension。两套宿主共用午饭情境，但不能混用它们的文件发现规则或插件接口。

### A.8 Bootstrap 例子：要装哪些资料，太长时又留下多少

#### A.8.1 先准备 OpenClaw 的午饭 Workspace

假设首次设置已经完成，`BOOTSTRAP.md` 已删除。工作区有这些文件；其中菜单和报告用于说明“在目录里”和“被默认注入”有什么区别：

```text
lunch-workspace/
├── AGENTS.md
├── SOUL.md
├── TOOLS.md
├── IDENTITY.md
├── USER.md
├── HEARTBEAT.md
├── MEMORY.md
├── skills/choose-lunch/SKILL.md
├── menus/today.json
└── reports/last-month.md
```

`AGENTS.md` 沿用 A.2 的工作约定，Skill 沿用 A.4。其他资料可以这样填写：

| 文件 | 本例正文可以表达什么 |
|---|---|
| `SOUL.md` | “你是一位认真核实信息的午饭助手。用简短中文回答，区分已查询的数据与未知数据。” |
| `TOOLS.md` | “本地菜单演示使用 list_meals 查询价格和口味，get_stock 查询库存。”这只是备注，仍需宿主实际提供工具。 |
| `IDENTITY.md` | “名字：午饭小助；身份：校园午饭助手。” |
| `USER.md` | “称呼：王老师；平时不吃辣，工作日午饭通常控制在 20 元以内；本次明确提出不同预算时结合本次要求处理。” |
| `HEARTBEAT.md` | “心跳检查时，关注今天午间预订有无待确认事项。”是否触发由心跳配置决定。 |
| `MEMORY.md` | “用户上次确认喜欢东区食堂的清淡套餐。”实时价格和库存仍需查询。 |

这一节的输入是这套 Workspace、运行配置、会话类型与运行模式。输出是**本次最终选中的资料片段，附带各自来源路径**，随后交给系统提示词组装。它不是推荐答案，也不是整个工作区的压缩包。

#### A.8.2 例子一：普通任务到底会考虑哪些文件

OpenClaw 默认按固定顺序考虑下面的基础候选，再按存在情况补充长期记忆文件：

```text
AGENTS.md → SOUL.md → TOOLS.md → IDENTITY.md
          → USER.md → HEARTBEAT.md → BOOTSTRAP.md
          → MEMORY.md，或未找到它时尝试 memory.md
```

这是候选顺序，不代表无条件把所有正文发给模型。对上面的工作区，`BOOTSTRAP.md` 已经不存在；加载层可以保留缺失信息，生成上下文时产生受预算限制的缺失提示。程序不会因此重新猜测用户身份，也不会把缺失提示当成首次设置正文。

`menus/today.json`、`reports/last-month.md` 和 Skill 正文不在这份默认基础候选清单中。它们可以随后通过工具或各自的资源机制读取。`BOOT.md` 走 Gateway 启动 Hook；每日记忆也不能仅凭位于 `memory/` 就认定已经全部注入。子目录的 `AGENTS.md` 等需要相应额外文件配置或其他加载路径。

**这里“要加载哪些文件”首先由宿主规则决定，不是让模型先列目录、自己挑一批文件做 Bootstrap。** 模型收到资料以后，才可能因任务需要另外请求读取菜单或方法正文。

#### A.8.3 例子二：同一工作区，换成子任务或轻量运行

| 这次运行的条件 | 基础资料会怎样变化 | 应怎样理解输出 |
|---|---|---|
| 普通主会话、完整上下文 | 从上述候选继续经过运行规则、Hook 与预算处理 | 有资格参与加载，不等于正文一定完整保留 |
| subagent 或 Cron 会话的基础筛选 | 基础保留集合为 `AGENTS.md`、`TOOLS.md`、`SOUL.md`、`IDENTITY.md`、`USER.md` | 这一层减少候选；还不能据此推断后续所有访问能力 |
| 轻量 heartbeat 运行 | 轻量过滤只保留 `HEARTBEAT.md` 候选 | 后续条件仍决定实际输出 |
| 轻量 default / cron 运行 | 轻量过滤在这一层把候选清空 | Bootstrap Hook 等后续处理仍需结合实际配置看 |

例如，把“只查一下 C 还有没有库存”交给子任务时，不能直接假定父会话全部基础资料都原样复制给了子任务。这里先解释候选怎样减少；真正能读取什么，还受后续上下文与工具条件影响。普通运行中，`HEARTBEAT.md` 也可能因 Agent 与心跳配置被排除。

#### A.8.4 例子三：单文件预算和全部文件预算怎样一起扣

先采用容易手算的**教学预算**，不是本地默认值：单文件最多 600 个字符，所有基础资料正文及缺失提示合计最多 1000 个字符。假定筛选后按顺序只处理下表三份文件，长度是去掉末尾空白后的长度：

| 文件 | 原正文长度 | 轮到它时总额度剩余 | 本文件最多可用 | 假定实际输出长度 | 处理后总额度剩余 |
|---|---:|---:|---:|---:|---:|
| `AGENTS.md` | 500 | 1000 | 600 | 500，完整保留 | 500 |
| `SOUL.md` | 300 | 500 | 500 | 300，完整保留 | 200 |
| `USER.md` | 900 | 200 | 200 | 200，包含截断提示 | 0 |

最后一行假定截断后的实际长度正好为 200；实际实现按生成结果的真实长度扣减，不保证每次都把额度用满。表中的结果是：前两份全文保留，`USER.md` 只留下一个带截断说明的片段，后面没有额度继续添加文件。

再换一个条件：假设第一个文件就有 900 个字符，单文件上限仍为 600。即使总额度还有 1000，也不能让它独占 900；会先把它整理到单文件额度内，余下总额度再留给后续文件。**单文件上限限制一份文件，总上限限制累计结果，两者同时生效。**

本地实现的默认单文件上限是 **12000 字符**，默认总上限是 **60000 字符**，可由对应配置调整。这是 Bootstrap 资料的字符额度，不是整个模型请求的 token 上限；用户消息、技能目录、工具定义等不能全部算进这张扣减表。

#### A.8.5 例子四：被截断的资料长什么样，文件会不会被改掉

假设用户资料前面写着称呼与时区，后面还有很多历史备注。注入结果可能像这样：

```text
USER.md 开头的一部分：称呼、时区……
〔中间内容已截断，需要全文时读取原文件〕
USER.md 末尾的一部分：最近维护的备注……
```

上面是可读示意，实际标记的文字由实现生成。程序先为标记与必要分隔留空间，再把剩余正文额度大致按开头 75%、末尾 25% 分配；因此不能直接把 200 乘以 75%，就宣称一定保留了 150 个开头字符。剩余总额度不足 64 字符时，本地实现不会继续处理下一份存在的文件正文；缺失提示有自己的限额处理，也会消耗总额度。

原始 `USER.md` 仍然完整留在磁盘上，截断只改变这次注入的副本。需要全文且读取工具可用时，模型还能另外读取。缺失文件则没有正文可截取，只能得到缺失提示；它不会自动变成一份用户资料。

到这里应能先不看代码回答：**哪批文件有资格进入、按什么顺序处理、这次真正保留了多少、未进入上下文的东西后面怎样取得。** E 节再用源码逐步验证这四个问题。

### A.9 Skill 完整例子：用户介绍技能，模型请求读取，再按方法执行

这一节先讲完整对话：**用户在本地看过 Skill，把它的存在告诉模型；模型先回复怎样使用；用户随后要求使用；模型请求读取正文，再按方法查菜单、查库存并回答。** `/lunch` 模板和 `/skill:choose-lunch` 是另外两种输入写法，分别在 A.9.2、A.9.3 对照，不用它们也能完成这段对话。

继续使用独立 Pi 的本地文件和工具。假定文件可访问，所需工具已启用，没有额外输入改写。如果模型的技能目录本来就列出了它，用户的介绍是在补充指向；即使没有自动目录介绍，用户提供的名称、用途和可访问路径也可以成为模型认识这份方法的来源。**在目录里可见、在用户消息里被介绍、正文已进入上下文，是三个不同状态。**

#### A.9.1 完整对话：从“我有一个 Skill”到真正取得推荐

**第一步：用户先在编辑器中看文件。** 用户打开 A.4 的 `SKILL.md`，知道这是一份按口味、预算和库存选午饭的方法。这个动作只发生在用户电脑上；如果正文没有通过消息、上下文注入或工具结果提供给模型，模型不会因为用户打开了文件就自动看到它。

**第二步：用户把技能的存在和位置告诉模型。** 例如，用户发送：

> 我在项目里放了一份 choose-lunch 技能，用来按口味、预算和库存选午饭。文件是 /work/lunch-project/.pi/skills/choose-lunch/SKILL.md。先告诉我你会怎样使用它，暂时不要查询菜单。

这一条消息只介绍了技能名称、用途和位置，没有粘贴六个步骤。因此模型现在知道“有这份方法”，还没有从这条消息中取得方法全文。

**第三步：模型先返回说明文字。** 一种符合上面要求的回复是：

> 我可以先读取你给出的 SKILL.md，取得具体方法，再按它查询菜单、筛选候选和核对库存。你可以直接告诉我这次的口味与预算，并要求我按这份技能处理。

到这里，模型输出的是怎样使用的说明，尚未查询菜单。不能把这段回复当成已经读取或执行成功。**“先说明、下一条再执行”是本例用户特意要求的教学过程；日常任务不需要固定多一次确认。**

**第四步：用户给出本次任务，要求模型使用。** 用户接着发送：

> 现在请读取刚才那份 choose-lunch 技能，按它帮我选不辣、20 元以内的午饭，只给方案，不要下单。

宿主把前面的对话和这条新消息提供给模型，所以模型可以从前文找到技能路径。用户不必输入 `/lunch`，也不必把技能文件伪装成一个工具名。

**第五步：模型请求读取，宿主执行，再把正文交回模型。** 这一段展开成三次交接，分别看消息是谁产生的、传给谁。下面是 Pi 内部消息的简化阅读视图，省略模型、用量、时间等字段，不是直接复制运行的程序代码。

**交接一：模型 → 宿主，返回助手消息，其中含 `toolCall`。** 模型可以同时说一句“我先读取这份技能，再按步骤查询”；真正用于调度的是下面的工具调用块：

```text
role    = "assistant"
content = [{
  type: "toolCall",
  id: "call_skill",
  name: "read",
  arguments: {
    path: "/work/lunch-project/.pi/skills/choose-lunch/SKILL.md"
  }
}]
```

它的意思是：“请宿主调用 read，读取这个路径；这次调用的编号是 call_skill。”**此时正文还没有读到，模型返回的是读取请求。** `call_skill` 只是这次调用的示例编号，不是技能名，也不是另一个工具。

**交接二：宿主 → read 工具 → 宿主，执行读取并包装 `toolResult`。** 宿主按工具名 `read` 找到文件读取工具，将路径交给它，取得文件内容，再生成下面的结果消息。本课技能文件很短，假设一次完整读取成功：

```text
role        = "toolResult"
toolCallId  = "call_skill"
toolName    = "read"
content     = [{ type: "text", text: A.4 的完整技能文件文本 }]
isError     = false
```

这里的 `text` 在实际运行中是 A.4 那份文件的真实文本；上面用说明代替全文。各字段可以直接对照：

| 字段 | 在本例中说明什么 |
|---|---|
| `role = "toolResult"` | 这是一条工具执行结果消息，由宿主组织，不是模型提出的下一次调用 |
| `toolCallId = "call_skill"` | 对应前一条调用块的 `id`，把请求与结果关联起来 |
| `toolName = "read"` | 实际执行的是文件读取工具，不是一个名为 `choose-lunch` 的执行函数 |
| `content` | 文件读取返回的技能全文，模型接下来才能据此理解具体步骤 |
| `isError = false` | 这次工具调用没有被标记为错误，不代表选餐任务已经完成 |

**所以，`toolCall` 在读取之前，由模型返回；`toolResult` 在读取之后，由宿主返回给模型。不能把 `toolResult` 当成触发这次读取的指令。** 普通说明文字给人看，工具调用请求给宿主调度；不是程序看到“我先读取”这几个汉字就自动去读文件。

**交接三：宿主 → 模型，把请求和结果一起放进下一次模型输入。** 这次输入的消息顺序可读作：

```text
前面介绍技能、说明使用方式的对话
    + 本次用户要求：不辣、20 元以内、只给方案
    + 助手消息：read 请求，id 为 call_skill
    + 工具结果：toolResult，toolCallId 为 call_skill，包含技能全文
    ↓ 再次请求模型
模型现在取得方法正文，按其中步骤提出下一次业务工具调用
```

例如，下一条助手消息中的工具调用块可以是：

```text
type      = "toolCall"
id        = "call_menu"
name      = "list_meals"
arguments = {}
```

宿主再调用菜单工具，把菜单作为另一条工具结果返回；模型接着筛选并请求库存。**不是拿到 `toolResult` 后再去执行一次“Skill 函数”，而是把技能正文交回模型，让模型按方法请求实际业务工具。** 源码怎样完成这三次交接，后面的 C.4～C.6 再一起看。

**第六步：正文回到模型以后，按方法完成任务。** 把执行阶段完整排开：

| 执行阶段的模型请求 | 这次请求中已有的关键材料 | 模型返回什么 | 宿主下一步做什么 |
|---|---|---|---|
| 第 1 次 | 前面对话中的技能位置，加上“不辣、20 元以内、只给方案” | `read` 请求，目标为技能文件 | 读出正文，接成工具结果 |
| 第 2 次 | 用户任务与刚读到的六个步骤 | `list_meals` 请求 | 查询并返回 A=18 元/辣、B=22 元/不辣、C=10 元/不辣 |
| 第 3 次 | 方法与菜单结果 | 排除 A、B，提出 `get_stock` 请求，候选为 C | 返回 C 的库存为 12 |
| 第 4 次 | 用户任务、方法、菜单与库存结果 | 推荐蛋炒饭，并说明符合预算、尚未下单 | 把最终文字交给用户 |

最终用户看到的回答可以是：

> 推荐蛋炒饭：10 元、不辣，当前有货。牛肉面口味不符，鸡腿饭超过预算；蛋炒饭符合要求。尚未下单。

完整过程是：**用户在本地了解技能 → 在消息中介绍名称、用途和位置 → 模型回复使用方式 → 用户提出使用要求 → 模型请求读文件 → 宿主返回正文 → 模型按方法请求业务工具 → 宿主返回业务结果 → 模型给出推荐。** 介绍阶段的文字回复，与执行阶段的工具请求，需要分开观察。这是一条教学轨迹，不是要求所有运行固定经历这些轮数。

#### A.9.2 /lunch 模板到底从哪里来：是 A.3 预先写好的文件

**`/lunch` 是本讲为午饭例子自定义的 Prompt 模板入口。模板就是 A.3 的 `/work/lunch-project/.pi/prompts/lunch.md`，由本讲作者预先编写；真实工程里由用户或项目维护者创建，也可以让助手协助写入。** Pi 不会因为发现 `choose-lunch` 技能，就自动生成这个文件或自动赠送一个 `/lunch` 命令。

把文件与命令的来源关系直接放在一起：

```text
用户或维护者创建文件：lunch-project/.pi/prompts/lunch.md
    ↓ Pi 准备项目资源时发现并读取这份模板
按文件名 lunch.md 记住模板名称 lunch，保存模板正文
    ↓ 用户输入 /lunch 后面的一串参数
宿主找到这份已加载模板，填好正文，再把展开文字交给模型
```

模板中的任务正文是下面这段；`$1`、`$2` 等是待替换位置：

```text
请帮我选择午饭。
口味要求：$1。
预算上限：$2 元。
附加要求：${@:3}。
先查阅 choose-lunch 技能，再查询和比较。最终说明是否下单。
```

所以用户输入 `/lunch 不辣 20 "先给方案，不要下单"` 时，宿主先填入参数：

| 命令中的参数 | 填到模板哪里 | 填入后的内容 |
|---|---|---|
| `不辣` | `$1` | 口味要求：不辣 |
| `20` | `$2` | 预算上限：20 元 |
| `先给方案，不要下单` | `${@:3}` | 附加要求：先给方案，不要下单 |

第一次交给模型的用户消息于是变成：

```text
请帮我选择午饭。
口味要求：不辣。
预算上限：20 元。
附加要求：先给方案，不要下单。
先查阅 choose-lunch 技能，再查询和比较。最终说明是否下单。
```

**`lunch.md` 保存的是“怎样替用户把任务要求说完整”，`choose-lunch/SKILL.md` 保存的是“取得任务后怎样一步步选午饭”。** 模板里只提到去查阅技能，没有复制技能正文；后面仍要走“模型请求读技能 → 正文回接 → 查菜单与库存”的过程。

如果没有创建并加载 `lunch.md`，就不能假定 `/lunch` 可用。在没有其他扩展命令接管的前提下，Pi 的模板展开找不到它时会保留原输入，不会凭空补出这段正文。模板后来才创建或修改时，还要核对资源是否已刷新。名称来自文件名，描述元数据不负责生成命令名称。

#### A.9.3 /skill:choose-lunch：用户显式指定，宿主先把正文带上

用户也可以直接输入：

```text
/skill:choose-lunch 不辣，20 元以内，先给方案，不要下单
```

假定这一入口已启用，没有同名扩展命令提前接管，宿主在请求模型之前就查找已加载的 `choose-lunch`，读取技能文件、去掉开头的元数据，把方法正文与用户要求放在一起。首次用户消息的阅读视图是：

```text
【指定技能：choose-lunch；附带技能文件位置和相对路径基准】
A.4 中的输入说明、六个步骤、异常处理与输出示例全文

【本次用户要求】
不辣，20 元以内，先给方案，不要下单
```

这是便于理解的示意，实际包装留到 D 节看代码。**与 A.9.1 的自然语言使用不同，这里是宿主在发请求之前主动读取和展开，不用先等模型输出读取请求。** 模型第一次已取得方法，可以直接查询菜单，再查询库存并回答。方法正文位于首次用户消息中，不是运行途中变成了新的系统提示词。

显式指定仍不等于业务已经完成：菜单、库存还需要实际查询，也不能保证固定少一轮模型请求。OpenClaw 自己的命令映射与资格规则需要看它的宿主路径，不能直接照搬这里的 Pi 入口。

#### A.9.4 没找到技能、同名或隐藏时，不能把输入当成成功

| 条件 | 本例应怎样理解 |
|---|---|
| `/skill:` 指定的技能没有进入已加载列表 | 本地 Pi 的这条展开路径会保留原输入，不能认定正文已附入 |
| `/skill:` 找到技能，但文件无法读取 | 本地 Pi 报告读取错误并保留原输入；需要核对实际展开结果 |
| 多个来源有同名技能 | 先由加载器处理冲突；Pi 的底层合并按到达顺序保留首次加入的同名项并报告冲突，不能只凭目录更近就猜覆盖关系 |
| 技能设置为不供模型自行选用 | 本地 Pi 可以不把它列入模型目录，但显式 Skill 入口仍能查找已加载项；这不等于技能完全未加载，也不是文件访问权限控制 |
| 其他扩展已经登记同名斜杠命令 | 它可能提前接管，不能再假定这里的模板或技能展开一定发生 |

本地输入展开也不是循环解释所有命令：先处理技能命令，再处理模板，各做一次。如果模板展开后才得到一行 `/skill:...`，程序不会自动回头再展开技能。实际入口顺序放在 D 节验证。

#### A.9.5 如果模型只回复“请调用这个技能”，接下来会发生什么

假设模型先返回普通文字：“可以使用 choose-lunch，请提供本次要求，或使用 `/skill:choose-lunch ...`。”**这是一条建议，本身没有发起工具执行。** 用户接着可以像 A.9.1 那样说“现在读取并按它处理”，也可以发送 A.9.3 的显式技能命令；前者由模型再提出读取请求，后者由宿主预先展开正文。

再区分一种情况：如果用户不是只介绍名称和路径，而是已经把 A.4 的全文粘贴进消息，模型就已从用户消息拿到了方法，不一定需要为了取得同一正文再读一次本地文件。反过来，用户仅在编辑器里打开过全文、在消息中只说“我有这个技能”，不足以把正文传给模型。

| 让模型取得方法的方式 | 谁提供“有这个技能”的信息 | 谁推进正文读取 | 正文进入哪里 |
|---|---|---|---|
| A.9.1：用户介绍后要求使用 | 用户提供名称、用途与路径 | 模型提出 `read`，宿主执行 | 文件工具结果 |
| A.9.2：`/lunch` 模板 | 预写模板要求查阅技能，目录或消息提供定位信息 | 展开任务后，模型再提出 `read` | 文件工具结果 |
| A.9.3：`/skill:choose-lunch` | 用户明确指定已加载技能 | 宿主在请求模型前读取 | 首次用户消息 |
| 用户直接粘贴正文 | 用户直接提供方法 | 不必为取得同一正文再读文件 | 用户消息 |

无论选哪条路径，最终都要分别核对：**模型知道技能存在了吗？取得正文了吗？提出查询了吗？工具真的返回数据了吗？** 这四个问题不能用一句“已经调用 Skill”代替。

### A.10 Extension 例子：扩展什么时候加载，谁来调用它

这一节仍讲独立 Pi 的 A.5 扩展。它与 Skill 的差别是：Skill 给模型方法文字，Extension 在宿主中提供工具和处理函数。**模型不用阅读扩展的 TypeScript 文件，也不用先输出“加载 lunch.ts”。**

#### A.10.1 准备时先登记能力，运行时再触发

把 A.5 当作一个已写好的工具包，先不看其中的实现：

```text
准备会话
    ↓ 宿主发现并加载午饭扩展
记下三个工具：查菜单、查库存、演示下单
记下一条检查：工具执行前，遇到下单请求就阻止
    ↓ 宿主装配允许使用的工具与事件处理
模型请求中出现可用工具的名称、用途与参数要求
```

这个阶段执行的是扩展的初始化和登记，不是三个工具的业务操作。也没有订单请求需要拦截。只有真正发生相应工具请求时，已经登记的工具与检查才被调用。

#### A.10.2 模型调用扩展提供的工具：以查库存为例

| 顺序 | 输入或触发条件 | 谁处理 | 输出 |
|---|---|---|---|
| 1 | 模型已知只剩 C 符合口味和预算，且能看到库存工具说明 | 模型提出调用 `get_stock`，候选 id 为 C | 一个带工具名和参数的调用请求 |
| 2 | 宿主收到这个请求 | 宿主先通知工具执行前的检查 | 本课检查只拦下单，所以这次不阻止 |
| 3 | 允许继续的库存请求 | 宿主按工具名找到扩展提供的执行函数 | 执行查询，得到 C 的库存为 12 |
| 4 | 库存工具返回的数据 | 宿主接成工具结果，继续请求模型 | 模型结合结果形成推荐 |

所以“扩展怎么调用”在这条路径上要拆成两件事：模型请求某个工具；宿主调到扩展里对应的执行函数。**工具名和参数来自模型输出，真正的业务函数由宿主执行。**

#### A.10.3 宿主自动触发扩展的检查：以阻止下单为例

正常午饭轨迹不会下单。为了观察检查效果，另外假设模型误提出“为 C 下单”：

```text
输入：模型的 place_order 请求，菜品为 C
    ↓ 宿主进入工具执行前的检查时机
通知已经登记的工具调用监听函数
    ↓ 午饭扩展发现工具名是 place_order
输出：阻止本次调用，并附上“课堂只给方案，不允许下单”的原因
    ↓ 宿主不进入下单工具的业务函数
将阻止结果接回工具循环，供模型后续说明
```

模型没有另行请求“调用下单检查”，检查是宿主在约定时机自动触发的。Skill 或 `AGENTS.md` 中的“不要下单”影响模型决策；扩展检查则在这条工具执行路径上实际阻止调用。它只覆盖已接入相应检查的路径，本身不是操作系统沙箱。

#### A.10.4 扩展还有用户命令入口吗

可以有。比如另外写一个扩展，登记 `/lunch-status` 命令，让用户查看菜单服务的连接状态：用户输入命令 → 宿主识别已登记命令 → 调用该扩展的命令处理函数 → 显示状态。处理函数可以自己决定是否再向模型发送材料；并不是每个扩展命令都必须先请求模型。

**这只是说明另一类入口，A.5 的午饭扩展没有登记这个命令，不能直接运行它。** A.5 实际只有三个工具和一个工具调用检查。扩展能否进入运行环境、支持哪些事件和命令，还要以宿主接口为准，不能把 Pi 扩展直接复制成 OpenClaw 插件。

| 扩展中的能力 | 运行时是谁先触发 | 宿主随后调用什么 |
|---|---|---|
| 扩展工具 | 模型输出工具调用请求 | 该工具的执行函数 |
| 事件或工具检查 | 宿主到达约定时机，发出相应事件 | 已登记的监听函数 |
| 扩展命令 | 用户输入已登记的命令 | 该命令的处理函数 |

工具还要经过允许范围与活跃工具选择，才能提供给模型。**“扩展加载成功”“工具登记成功”“工具在本次请求中可见”“工具真正执行成功”是四个不同的观察结果。**

### A.11 把一次午饭运行串起来：四次模型请求怎样接力

沿 A.1 的普通午饭输入，选取一条符合 Skill 的教学轨迹：宿主提供技能目录，模型请求读取正文，再按方法查询。读取请求与工具结果的消息格式见 A.9.1。它不是实际请求日志，也不承诺真实模型固定使用四轮；这里每次只产生一个工具调用，便于观察输入输出。

| 第几次模型请求 | 已收到的主要材料 | 模型这次输出什么 | 宿主随后做什么 |
|---|---|---|---|
| 第 1 次 | 工作约定、技能目录、用户要求、可用工具说明 | 请求读取 `choose-lunch/SKILL.md` | 检查调用、执行文件读取，把正文接回消息 |
| 第 2 次 | 前面的材料，加上 Skill 正文 | 请求查询菜单 | 检查调用、执行菜单工具，返回 A=18 元/辣、B=22 元/不辣、C=10 元/不辣 |
| 第 3 次 | 前面的材料，加上菜单 | 排除 A、B，请求 C 的库存 | 检查调用、执行库存工具，返回 C 有 12 份 |
| 第 4 次 | 前面的材料，加上库存结果 | 推荐蛋炒饭：10 元、不辣、有货，符合 20 元预算，尚未下单 | 交付回答；没有其他待处理输入时结束 |

为了后面读调用栈，先给消息取简称。这只是讲义中的编号，不是要求模型输出的变量：

| 简称 | 消息内容 |
|---|---|
| U | 用户的午饭要求 |
| A1 / R1 | 模型请求读技能 / 文件读取返回的正文 |
| A2 / R2 | 模型请求菜单 / 菜单结果 |
| A3 / R3 | 模型请求库存 / 库存结果 |
| A4 | 最终推荐 |

假设没有上下文扩展增删消息，也没有压缩，四次请求可以这样读：

```text
第 1 次：系统提示词 + [U]                         + 工具定义
第 2 次：系统提示词 + [U, A1, R1]                 + 工具定义
第 3 次：系统提示词 + [U, A1, R1, A2, R2]         + 工具定义
第 4 次：系统提示词 + [U, A1, R1, A2, R2, A3, R3] + 工具定义
最后再把 A4 加入活动消息
```

这里的加号表示一次请求包含几类材料，不是把所有东西拼成一个字符串。Bootstrap 工作约定在本例的系统提示词中，按需读取的 Skill 正文在 R1 中，扩展的 JavaScript 函数始终留在宿主。查询结果接回消息以后，还需要下一次模型请求来理解和利用。

若换成 A.9.3 的显式 Skill 输入，方法正文一开始就在 U 中，不必先为了取得正文生成 A1/R1；菜单、库存、回答仍需后续接力。A.9.1 的自然语言使用则保留“先请求读取、正文回接后继续”的过程，只是前面多了用户介绍技能与模型回复的对话。若走到 A.10 的下单分支，则产生阻止结果，不会正常执行订单函数。

### A.12 再换两个条件：改了文件，或工具没有启用

**条件一：用户把默认预算从 20 元改成 30 元。** 磁盘上的 `USER.md` 保存成功，只能证明文件变了。还要看宿主是否复用了 Bootstrap 文件快照、何时刷新上下文，以及下一次模型请求实际带了什么；不能统一承诺“保存后下一条消息必定生效”。用户在本次消息明确提出的新要求，也要与长期资料区分。

**条件二：Skill 文件可见，但库存工具未启用。** 模型可能读到“查询库存”这一步，却没有相应可用工具。此时正确结论是能力条件不足，需要说明库存未确认；不能把 Skill 正文当成已经查过库存的证据。反过来，库存工具已启用也不证明模型已经读过并遵循 Skill。

修改 Skill 时，还要分别考虑目录中的描述是否已刷新、运行中实际读到哪份正文；修改扩展时，还要看是否重新加载并绑定运行环境，旧函数及其保存的状态不会因为磁盘代码改变就自动替换。具体的缓存与刷新入口放在后面的第 25 节核对。

### A.13 进入源码之前：先用一张表判断每一步的输入输出

| 环节 | 本例输入 | 本例输出 | 谁负责推进 |
|---|---|---|---|
| Bootstrap | Workspace、配置、会话与运行条件 | 经过筛选及预算处理的基础资料片段 | 宿主程序 |
| Skill 发现 | 技能文件与资源规则 | 名称、描述、位置组成的目录 | 宿主程序 |
| 模型按需取 Skill | 目录、读取要求、当前午饭任务 | 读取请求 → 工具结果中的方法正文 | 模型决定请求，宿主执行 |
| 用户用自然语言介绍并要求使用 Skill | 前面对话中的技能名称、用途与路径，加上本次任务 | 读取请求 → 工具结果中的正文 → 继续查询 | 用户介绍和提出要求，模型请求工具，宿主执行 |
| 用户显式用 Skill | 技能命令与本次要求 | 含方法正文的首次用户消息 | 宿主在发给模型前展开 |
| Prompt 模板 | `/lunch` 命令、参数、模板正文 | 填好口味与预算的任务文字 | 宿主展开，不直接查询菜单 |
| Extension 准备 | 扩展模块及允许范围 | 可调用的工具、检查与其他登记项 | 宿主加载、登记、装配 |
| Extension 运行 | 模型工具请求、宿主事件或用户命令 | 工具数据、检查结果或命令处理结果 | 宿主调用对应函数 |
| 最终推荐 | 用户要求、方法、菜单与库存结果 | 蛋炒饭方案，并说明尚未下单 | 模型生成，宿主交付 |

现在再读代码，逐步回答的是：**这份输入传给谁、处理后保存在哪里、谁在下一步取出、何时真正发给模型或执行工具。** B～F 集中讲源码与调用栈，不再等讲到一半才补充完整业务例子。

---

## 第二部分：统一讲源码与调用栈

A.7～A.13 已经说明完整运行过程。现在依次验证资源准备、模型与工具循环、输入展开、OpenClaw Bootstrap 四条调用链。树中的分支表示调用顺序与数据交接；跨模型请求、事件和异步等待时，不把它们画成永不退出的一条同步栈。

### B. 准备阶段源码：文件怎样变成可用资源

本节沿用 A.7 的**独立 Pi 项目** `/work/lunch-project` 及其运行条件。OpenClaw 自己的 Bootstrap 调用路径集中在 E 节；这里核对 Pi 的资源加载器、扩展登记与会话装配。

#### B.1 代码阅读的目标：核对 A.7 的准备结果

准备阶段的完整例子已放在 A.7。接下来固定相同输入，在代码里核对三处交接，而不是重新设计业务流程：

| 代码中的观察位置 | 应核对的输入 | 应核对的输出或状态 |
|---|---|---|
| SDK 调用加载器 | `cwd`、`agentDir`、配置与资源路径 | 加载器保存上下文、模板、Skill 对象、扩展结果 |
| 加载器调用资源读取函数 | A.2～A.5 各资源的绝对路径 | 文本正文、元数据对象或登记项，不是午饭答案 |
| 会话构造运行环境 | 加载器中的资源与工具选择 | `agent.state.systemPrompt`、`agent.state.tools` 与扩展 Runner |

下面先看总调用树，再分别进入文本资源、扩展登记和工具装配。`reload()` 结束只证明资源准备结束；是否真正使用 Skill，要到 C 节检查模型请求和工具结果。

#### B.2 再进代码：createAgentSession 的参数怎样交给加载器

参考第 05 讲的读法，先把调用处的实参和定义处的形参对上。教学入口把 A.6 的工作目录写成具体值：

```ts
const result = await createAgentSession({ cwd: "/work/lunch-project" });
const session = result.session;
```

跳到 [sdk.ts 的 createAgentSession](/source/?file=07502145bf1ffa712b.ts#L176)。下面是其中的源码摘录，省略模型、认证和历史等准备：

```ts
const cwd = options.cwd ?? options.sessionManager?.getCwd() ?? process.cwd();
const agentDir = options.agentDir ?? getDefaultAgentDir();
let resourceLoader = options.resourceLoader;

if (!resourceLoader) {
  resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
  await resourceLoader.reload();
  time("resourceLoader.reload");
}
```

| 本例传入或取得的值 | 进入哪里 | 接下来用于什么 |
|---|---|---|
| `options.cwd = "/work/lunch-project"` | 局部变量 `cwd`，再进入加载器构造选项 | 确定项目资源所在的工作目录 |
| 没有传 `options.resourceLoader` | `resourceLoader` 起初是 `undefined` | 进入创建默认加载器的分支 |
| `getDefaultAgentDir()` 得到的目录 | 局部变量 `agentDir`，再进入加载器 | 发现用户级资源；本例假设没有影响案例的额外资源 |

`await resourceLoader.reload()` 等待资源准备结束。**`reload()` 返回的是 `Promise<void>`，资源结果保存在加载器内部，后面通过 getter 取得；它不是直接返回推荐答案，也不是直接返回会话。** 最外面的 `createAgentSession()` 才返回包含 `session`、`extensionsResult` 等字段的结果对象。传入自定义加载器时，不进入这里的默认 `reload` 分支，宿主需要预先准备它。

先把准备阶段的主要调用关系摆出来。下面的树按发生顺序展开，并列分支表示前一个返回后再做下一个，不表示所有函数同时留在栈中；省略本课暂不追踪的模型、历史和主题处理：

```text
教学入口：createAgentSession({ cwd: "/work/lunch-project" })
└─ sdk.ts：createAgentSession(options)
   ├─ new DefaultResourceLoader({ cwd, agentDir, settingsManager })
   ├─ await resourceLoader.reload()
   │  ├─ 解析启用的包资源、项目资源和显式资源路径
   │  ├─ loadExtensions(...)              → B.4 展开
   │  ├─ updateSkillsFromPaths(...)        → B.3 展开
   │  ├─ updatePromptsFromPaths(...)       → B.3 展开
   │  └─ loadProjectContextFiles(...)      → B.3 展开
   ├─ new Agent(...)
   ├─ new AgentSession({ agent, resourceLoader, cwd, ... })
   │  ├─ _installAgentToolHooks()
   │  └─ _buildRuntime(...)                → B.5 展开
   └─ return { session, extensionsResult, modelFallbackMessage }
```

#### B.3 三种文本资源：读取之后，各自留下什么

先跳到 [resource-loader.ts 的 reload](/source/?file=9d3a691c82fb128e60.ts#L343)。它先解析资源路径；本例得到的路径指向 A 节的文件。下面分别跟随一次读取，观察输入与输出。扩展模块在实际 `reload` 中先加载，本节先集中解释文本资源的三种产物，扩展在 B.4 单独展开。

**第一条：项目约定保留正文。** 调用关系是：

```text
createAgentSession(...)
  → resourceLoader.reload()
    → loadProjectContextFiles({ cwd: "/work/lunch-project", agentDir })
      → loadContextFileFromDir("/work/lunch-project")
        → readFileSync("/work/lunch-project/AGENTS.md", "utf-8")
      ← { path: "/work/lunch-project/AGENTS.md", content: A.2 的完整正文 }
    ← 项目上下文文件数组，保存到加载器
```

定义见 [loadProjectContextFiles](/source/?file=9d3a691c82fb128e60.ts#L82) 和 [loadContextFileFromDir](/source/?file=9d3a691c82fb128e60.ts#L62)。前者还处理用户级与祖先目录上下文，上图只展开走到本例目录的那一次调用。同目录先尝试 `AGENTS.md`，否则再尝试 `CLAUDE.md`。路径告诉后面“这些规则来自哪里”，`content` 留住全文，供 B.5 组装提示词。

**第二条：模板保存正文，暂时不替换参数。** 调用关系是：

```text
resourceLoader.reload()
  → updatePromptsFromPaths(已发现的模板路径)
    → loadPromptTemplates(...)
      → loadTemplatesFromDir(...) / loadTemplateFromFile(...)
        → 读取 .pi/prompts/lunch.md，解析 frontmatter 和 body
      ← PromptTemplate：name="lunch"，content=带占位符的 body
```

目录路径会先进入目录遍历，文件路径可以直接进入文件加载。定义见 [loadTemplateFromFile](/source/?file=81f806b0803812db28.ts#L109)。以下是结果的阅读视图，省略描述、来源等字段，`content` 的其余行沿用 A.3：

```text
name     = "lunch"
filePath = "/work/lunch-project/.pi/prompts/lunch.md"
content  = "请帮我选择午饭。\n口味要求：$1。\n预算上限：$2 元。\n……"
```

此时还没有收到 `/lunch 不辣 20 ...`，所以 `$1`、`$2` 仍是占位符。D 节才把用户参数代入它们。

**第三条：Skill 读过文件，但返回对象不包含正文。** 本例启用的技能目录会被上层转换成 `SKILL.md` 文件路径，因此可以沿文件分支追：

```text
resourceLoader.reload()
  → updateSkillsFromPaths(["/work/lunch-project/.pi/skills/choose-lunch/SKILL.md"])
    → loadSkills({ cwd, agentDir, skillPaths, includeDefaults: false })
      → loadSkillFromFile(技能绝对路径, "project")
        → readFileSync(filePath, "utf-8")
        → parseFrontmatter(rawContent)
      ← { skill: 技能说明对象, diagnostics: [...] }
    ← { skills: [技能说明对象], diagnostics: [...] }
  ← 加载器保存 skills 与诊断信息
```

`includeDefaults: false` 表示这一层不重新发现默认目录；默认路径已经由上层解析后传入。它不代表“项目 Skill 不加载”。如果传入的仍是目录，`loadSkills` 会先走目录遍历，再进入文件读取。

打开 [skills.ts 的 loadSkillFromFile](/source/?file=08398ed5b2b3650ff5.ts#L288)，核心源码摘录如下：

```ts
const rawContent = readFileSync(filePath, "utf-8");
const { frontmatter } = parseFrontmatter<SkillFrontmatter>(rawContent);
const skillDir = dirname(filePath);
const parentDirName = basename(skillDir);
const name = frontmatter.name || parentDirName;
```

本例 `filePath` 代入技能绝对路径，`rawContent` 就是 A.4 整份文件，`frontmatter.name` 是 `"choose-lunch"`。经过校验，返回的 `skill` 对象主要是：

```ts
// 阅读视图：省略 sourceInfo 的具体结构。
{
  name: "choose-lunch",
  description: "当用户要求选择或比较午饭时，按口味、预算和库存筛选候选，给出方案。",
  filePath: "/work/lunch-project/.pi/skills/choose-lunch/SKILL.md",
  baseDir: "/work/lunch-project/.pi/skills/choose-lunch",
  disableModelInvocation: false,
}
```

要找的是返回对象的字段，而不只是 `readFileSync` 这一行：**文件确实被读过，但返回的 `Skill` 没有 `content` 字段。** 后面生成目录时使用名称、描述和位置，不会顺便带上选餐步骤。

#### B.4 扩展加载：执行初始化函数，登记工具与监听函数

先代入本例：输入是 `.pi/extensions/lunch.ts` 的绝对路径。期待的输出是三个工具和一个监听函数，不是 `list_meals` 的菜单结果。

打开 [extensions/loader.ts 的 loadExtension](/source/?file=d170abdf93d664a78b.ts#L390)，下面是它成功路径中的源码摘录：

```ts
const factory = await loadExtensionModule(resolvedPath);
// 中间省略无效 factory 的检查。
const extension = createExtension(extensionPath, resolvedPath);
const api = createExtensionAPI(extension, runtime, cwd, eventBus);
await factory(api);
```

`factory` 就是 A.5 默认导出的函数。调用处把 `api` 传入，定义处用形参 `pi` 接住，所以 A.5 的 `pi.registerTool(...)` 实际调用的是加载器创建的 API：

```text
resourceLoader.reload()
  → loadExtensions(["/work/lunch-project/.pi/extensions/lunch.ts"], cwd, eventBus)
    → loadExtension(extensionPath, cwd, eventBus, runtime)
      ├─ loadExtensionModule(resolvedPath)
      │  └─ jiti.import(resolvedPath, { default: true }) → 取得默认导出工厂
      ├─ createExtension(...) → 建立 tools、handlers 等空集合
      ├─ createExtensionAPI(...) → 建立交给工厂的 api
      └─ await factory(api)
         └─ A.5：export default function (pi) { ... }，此时 pi 就是 api
            ├─ pi.registerTool(list_meals 的定义)
            ├─ pi.registerTool(get_stock 的定义)
            ├─ pi.registerTool(place_order 的定义)
            └─ pi.on("tool_call", 下单拦截函数)
    ← { extensions, errors, runtime }
```

再跳进同文件的 `createExtensionAPI`，查看保存动作，以下为两段源码摘录：

```ts
// registerTool 中：tool 是传入的整个工具定义，里面含 execute 函数。
extension.tools.set(tool.name, {
  definition: tool,
  sourceInfo: extension.sourceInfo,
});

// on 中：event 是事件名，handler 是传入的监听函数。
const list = extension.handlers.get(event) ?? [];
list.push(handler);
extension.handlers.set(event, list);
```

把这两次保存代入本例，得到：

```text
extension.tools
  "list_meals"  → 工具定义，包含参数 Schema 和 execute 函数
  "get_stock"   → 工具定义，包含参数 Schema 和 execute 函数
  "place_order" → 工具定义，包含参数 Schema 和 execute 函数

extension.handlers
  "tool_call"   → [A.5 的下单拦截函数]
```

`factory(api)` 已经执行，不等于每个 `execute` 和 `handler` 都执行了。前者负责登记；后两者是保存在集合里的函数，等真正发生工具调用时才运行。

#### B.5 从登记结果到会话：工具与系统提示词分别装到哪里

前面 `reload` 完成后，SDK 创建 `AgentSession`，将同一个加载器传给它。跟到 [AgentSession 构造器](/source/?file=24209413646c397dc9.ts#L313)，再顺着调用进入运行环境装配：

```text
createAgentSession(...)
  → new AgentSession({ agent, resourceLoader, cwd, ... })
    ├─ _installAgentToolHooks()
    │  └─ 设置 agent.beforeToolCall / afterToolCall 回调，供以后调用
    └─ _buildRuntime({ activeToolNames, includeAllExtensionTools: true })
       ├─ createAllToolDefinitions(cwd, ...) → 准备 read 等内置工具定义
       ├─ resourceLoader.getExtensions() → 取回 B.4 的扩展登记结果
       ├─ new ExtensionRunner(...) → 接收扩展与 runtime
       ├─ _bindExtensionCore(...) / _applyExtensionBindings(...)
       └─ _refreshToolRegistry(...)
          ├─ 合并内置工具与扩展工具，按允许范围过滤并包装 execute
          └─ setActiveToolsByName(本次启用的工具名)
             ├─ agent.state.tools = 选中的工具对象数组
             └─ _rebuildSystemPrompt(validToolNames)
                └─ buildSystemPrompt({ contextFiles, skills, selectedTools, ... })
                   ← 系统提示词字符串，保存到 agent.state.systemPrompt
```

运行环境实现见 [_buildRuntime](/source/?file=24209413646c397dc9.ts#L2390)，工具装配见 [_refreshToolRegistry](/source/?file=24209413646c397dc9.ts#L2297)。本例没有白名单限制，初始内置活跃工具加上扩展工具后，A.6 的 `session.getActiveToolNames()` 应包含 A.7 列出的七项。

继续进入 [_rebuildSystemPrompt](/source/?file=24209413646c397dc9.ts#L916)，它取出资源的源码是：

```ts
const loadedSkills = this._resourceLoader.getSkills().skills;
const loadedContextFiles = this._resourceLoader.getAgentsFiles().agentsFiles;
```

这里的 `loadedSkills` 是 B.3 的技能说明对象数组，`loadedContextFiles` 是项目文件路径与正文数组。它们分别进入 `buildSystemPrompt` 的 `skills`、`contextFiles`；活跃工具名进入 `selectedTools`。返回值是一段字符串，并不是消息历史数组。

在 [system-prompt.ts](/source/?file=16fcd113d065a4c54a.ts#L160) 中，项目文件正文追加到 `# Project Context`。活跃工具有 `read` 时，技能再经过 [formatSkillsForPrompt](/source/?file=08398ed5b2b3650ff5.ts#L349) 变成目录；其中 `disableModelInvocation=true` 的技能会被排除。本例技能可见，因此相关输出如下，其他提示词段落和项目正文中间行省略：

```text
# Project Context
Project-specific instructions and guidelines:

## /work/lunch-project/AGENTS.md
# 午饭助手工作约定
你负责查询和比较午饭，回答使用中文。
遇到午饭推荐任务，先查阅可用的 choose-lunch 技能，按其中的方法处理。
……其余工作约定见 A.2，实际拼入的是完整正文……

<available_skills>
  <skill>
    <name>choose-lunch</name>
    <description>当用户要求选择或比较午饭时，按口味、预算和库存筛选候选，给出方案。</description>
    <location>/work/lunch-project/.pi/skills/choose-lunch/SKILL.md</location>
  </skill>
</available_skills>
```

这就完成了 A.7 所列的准备阶段输入输出：项目文件变成提示词正文，Skill 对象变成目录，工具定义变成活跃工具，模板留在加载器供以后展开。**`lunch.ts` 的函数体没有发给模型，Skill 六个步骤也没有混进这份目录。** 工具的名字、描述和参数 Schema 随请求的工具定义发送，真正执行函数仍留在宿主。

#### B.6 调试时怎样确认“准备好了”

在 A.6 的 `createAgentSession` 返回处暂停，按下面三项检查即可，不需要先请求模型：

| 观察位置 | 本例应看到的值 | 能证明什么 |
|---|---|---|
| `session.resourceLoader.getSkills().skills` | 含 `name="choose-lunch"` 和技能绝对路径的对象 | 技能已经被发现并解析 |
| `session.getActiveToolNames()` | 包含 `read` 和三个午饭工具 | 工具已经装进当前活跃集合 |
| `session.systemPrompt` | 含 A.2 正文，以及 `choose-lunch` 的名称、描述、位置 | 首次请求所需的基础说明已经组装 |

这些检查证明的是“已准备资源”。是否真正读了 Skill 正文、是否按步骤查询，必须继续看 C 节的运行轨迹。

### C. 运行阶段源码：沿 A.11 的模型与工具轨迹追调用链

#### C.1 代码阅读的入口：沿 A.11 的同一条运行轨迹

A.9.1 已展示模型读取请求与宿主返回结果的交接，A.10 已讲工具与检查怎样触发，A.11 已给出四次请求的输入输出。现在只追这些步骤对应的调用位置。沿用 A.7 的空闲新会话，输入仍为 A.1 的普通午饭请求，没有额外输入改写、消息增删或压缩。

| 要验证的交接 | 从哪里向下跟 | 返回后重点看什么 |
|---|---|---|
| 用户字符串进入 Agent | `AgentSession.prompt` → `Agent.prompt` → AgentLoop | 构造的 U，以及本次上下文快照 |
| 模型输出读取请求 | `runLoop` → `streamAssistantResponse` | A1 的工具名、参数与调用 id |
| 读取请求执行成正文 | 工具执行入口 → `read.execute` | R1 的模型可读内容 |
| 正文进入下一次请求 | 工具结果追加 → 下一次 `streamAssistantResponse` | 请求消息确实包含 R1 |
| 菜单、库存及下单检查 | 同一工具循环 → 前置钩子 → 对应 `execute` | R2、R3；或阻止结果及订单函数未进入 |

这些调用涉及异步请求与循环，不是始终压在同一条同步栈上。下文的调用树表示先后调用、返回与接续关系。

#### C.2 消息编号怎样与代码中的字段对上

U、A1/R1、A2/R2、A3/R3、A4 的内容和逐轮排列见 A.11。进入源码后，分别在下面几个位置核对同一批消息；不要只凭一个函数已经返回，就认定它们已经进入下一次模型请求。

| 源码中的字段或局部值 | 本例要核对的材料 |
|---|---|
| `agent.state.systemPrompt` / 请求中的 `systemPrompt` | 工作约定与技能目录；不是 R1 正文的新存放位置 |
| `messages`、`currentContext.messages` | 从 U 起，按运行进展追加助手消息和工具结果 |
| 请求使用的 `llmContext.messages` | 经上下文处理、转换后，本轮真正提供给模型的消息 |
| 请求中的 `tools` | 当前可用工具定义；不是扩展 JavaScript 函数体 |

下文每次写“第二次请求”，都指 A.11 中已接回 R1 的那次；业务工具与文件读取工具沿同一类结果回接机制工作。

#### C.3 再进代码：AgentSession.prompt 把字符串交给谁

回到 A.6 的实际入口：

```ts
await session.prompt("帮我找不辣、20 元以内的午饭，先给方案，不要下单。");
```

跳到 [agent-session.ts 的 prompt](/source/?file=24209413646c397dc9.ts#L968)。先看这一层的输入输出：它接收用户字符串，预处理后构造本次新消息，再交给内部 `Agent`。以下是本例经过的分支，展示的是有先后顺序的调用与处理，不是某一时刻的完整同步栈：

```text
教学入口：session.prompt(午饭请求字符串)
└─ AgentSession.prompt(text)
   ├─ 没有斜杠前缀 → 不进入扩展命令执行分支
   ├─ 本例未注册 input handler → 输入保持原样
   ├─ _expandSkillCommand(text) → 普通文字，原样返回
   ├─ expandPromptTemplate(text, 模板数组) → 普通文字，原样返回
   ├─ 当前会话空闲；检查模型、认证及必要的历史压缩
   ├─ 构造 U：role="user"，文本为 expandedText
   ├─ emitBeforeAgentStart(...) → 本例没有修改提示词或补消息的 handler
   └─ await this.agent.prompt([U])
      └─ Agent.prompt(input)
         ├─ normalizePromptInput([U]) → 已是数组，原样交回
         └─ runPromptMessages([U])
            └─ runWithLifecycle(运行回调)
               └─ runAgentLoop([U], 上下文快照, 循环配置, ...)
                  └─ runLoop(...) → C.4 展开
```

`AgentSession` 与 `Agent` 都有 `prompt`，但本次接收的值不同：外层收到字符串；内层收到已经准备好的 `[U]`。不会让内部 Agent 再把整个数组当作一段用户文字。

外层构造 U 的源码摘录如下，其他消息注入处理省略：

```ts
messages = [];
const userContent: (TextContent | ImageContent)[] = [{ type: "text", text: expandedText }];
// 本例没有图片，省略图片追加分支。
messages.push({
  role: "user",
  content: userContent,
  timestamp: Date.now(),
});
// 中间还会处理待发送消息和 before_agent_start，见上方调用链。
await this.agent.prompt(messages);
```

注意这一层没有“读取描述，匹配午饭关键词，然后自动执行 Skill 六步骤”的程序分支。普通输入用哪份 Skill，是后续模型根据目录、项目约定与用户任务作出的选择。

#### C.4 第一次请求：上下文怎样进入模型，模型怎样交回 A1

继续从 [Agent.runPromptMessages](/source/?file=3688aa044ebb960834.ts#L396) 进入 [runAgentLoop](/source/?file=6adbf9ab77a3572a2f.ts#L96)。它将新消息接入当前上下文，再进入 `runLoop`。本例的新输入是 `[U]`，新会话的旧消息数组为空，因此第一次请求的消息就是 `[U]`。

```text
runAgentLoop([U], { systemPrompt, messages: [], tools }, config, ...)
  → runLoop(currentContext, ...)
    → streamAssistantResponse(currentContext, config, ...)
      ├─ transformContext(messages, ...) → 本例保留 [U]
      ├─ convertToLlm(messages) → 转成模型支持的消息
      └─ streamFunction(config.model, llmContext, options)
         └─ SDK 安装的 streamFn(model, context, options)
            └─ streamSimple(model, context, 带认证的选项)
               └─ 具体 Provider 发出请求；协议与流式细节见第 05 讲
    ← 读取返回流，形成助手消息 A1
```

在 [streamAssistantResponse](/source/?file=6adbf9ab77a3572a2f.ts#L288) 中，准备模型上下文的源码是：

```ts
let messages = context.messages;
if (config.transformContext) {
  messages = await config.transformContext(messages, signal);
}
const llmMessages = await config.convertToLlm(messages);
const llmContext: Context = {
  systemPrompt: context.systemPrompt,
  messages: llmMessages,
  tools: context.tools,
};
```

| 调用中的数据 | 本例具体值 | 对应 C.2 的材料 |
|---|---|---|
| `context.systemPrompt` | B.5 组装的项目规则和技能目录等 | `systemPrompt` |
| `context.messages` | 本例第一次为 `[U]` | 消息数组 |
| `context.tools` | 包括 `read` 与午饭工具的活跃工具对象 | `tools`，由 Provider 整理可发送的定义 |

模型返回 A1，其 `content` 中包含下面这个工具调用块。这里只显示完整调用块，助手消息外层的模型、usage、时间等字段省略：

```json
{
  "type": "toolCall",
  "id": "call_skill",
  "name": "read",
  "arguments": {
    "path": "/work/lunch-project/.pi/skills/choose-lunch/SKILL.md"
  }
}
```

到这里模型只交回了“请求读取这个路径”的数据。下一步才进入宿主工具执行。

#### C.5 执行 read：从 A1 的工具名找到函数，再得到 R1

输入是 A1 里的 `name="read"` 与 `arguments.path`，输出是文件工具结果 R1。顺着 [executeToolCalls](/source/?file=6adbf9ab77a3572a2f.ts#L424) 往下跳：

```text
runLoop(...) 取得 A1，发现其中有 toolCall
  → executeToolCalls(currentContext, A1, config, ...)
    → 顺序或并行执行分支（本例只有一个 toolCall）
      ├─ prepareToolCall(currentContext, A1, toolCall, config, ...)
      │  ├─ 从 currentContext.tools 查找 name === "read" 的工具
      │  ├─ 准备并校验 arguments，取得 { path: 技能绝对路径 }
      │  └─ beforeToolCall(...) → 扩展观察这次调用，本例放行 read
      ├─ executePreparedToolCall(prepared, ...)
      │  └─ prepared.tool.execute("call_skill", { path: 技能绝对路径 }, ...)
      │     └─ 工具包装函数 → read 工具定义的 execute(...)
      │        ├─ resolveReadPath(path, cwd) → 技能绝对路径
      │        └─ 检查文件并读取文本 → { content: 文本块数组, details }
      ├─ finalizeExecutedToolCall(...) → 处理结果及执行后钩子
      └─ createToolResultMessage(...) → R1，role="toolResult"
```

工具包装见 [wrapToolDefinition](/source/?file=1e0c83f34aa98ecb8e.ts#L6)。它保留同一个工具的名字、描述和参数，把调用委托给 `definition.execute(...)`，并补入扩展上下文。读取实现见 [createReadToolDefinition](/source/?file=00474589cfa9d9ff08.ts#L122) 返回对象中的 `execute`。

把准备工具调用的源码与本例数据对起来，见 [prepareToolCall](/source/?file=6adbf9ab77a3572a2f.ts#L606)：

```ts
const tool = currentContext.tools?.find((t) => t.name === toolCall.name);
// 省略工具不存在时的错误返回。
const preparedToolCall = prepareToolCallArguments(tool, toolCall);
const validatedArgs = validateToolArguments(tool, preparedToolCall);
```

`toolCall.name` 来自 A1 的 `"read"`；查到的 `tool` 来自 B.5 的活跃工具数组；`validatedArgs.path` 来自模型给出的文件路径。它们在 [executePreparedToolCall](/source/?file=6adbf9ab77a3572a2f.ts#L660) 中分别成为执行函数和参数：

```ts
const result = await prepared.tool.execute(
  prepared.toolCall.id,
  prepared.args as never,
  signal,
  /* 工具进度回调，源码正文此处省略 */
);
```

上面是调用片段的阅读示意，回调本身省略，不能直接作为完整调用语句复制运行。对本例，就是把 `"call_skill"` 和 `{ path: "/work/lunch-project/.pi/skills/choose-lunch/SKILL.md" }` 交给读取工具。普通文本会经过行数与字节数限制；本课 Skill 很短，假设一次完整返回，长文件则可能需要继续读取。

最后由 [createToolResultMessage](/source/?file=6adbf9ab77a3572a2f.ts#L761) 包装，R1 的阅读视图如下。`content[0].text` 在实际运行中是 A.4 的文件内容，这里用说明代替全文：

```text
role        = "toolResult"
toolCallId  = "call_skill"
toolName    = "read"
content     = [{ type: "text", text: A.4 的完整技能文件文本 }]
isError     = false
```

`toolCallId` 将 R1 和 A1 的那次请求对应起来。文件读取成功产生 R1，此时仍要继续回到循环，才能把它发给模型。

#### C.6 回到循环：R1 怎样成为第二次请求的输入

回到 [runLoop](/source/?file=6adbf9ab77a3572a2f.ts#L252)，工具执行返回后，源码追加结果：

```ts
for (const result of toolResults) {
  currentContext.messages.push(result);
  newMessages.push(result);
}
```

本例 `toolResults` 只有 R1。A1 已在读取模型响应时加入上下文，因此这次追加之后：

```text
执行 read 之前：currentContext.messages = [U, A1]
执行 read 之后：currentContext.messages = [U, A1, R1]
    ↓ runLoop 继续下一次模型请求
streamAssistantResponse(...)
    ↓ 第二次输入包含 R1 中的 Skill 正文
模型输出 A2：请求 list_meals({})
```

从第二次请求开始，模型才有条件读取并遵循六个具体步骤。这里既没有调用“技能执行器”，也没有把 Markdown 编译为函数；后续仍然由模型输出工具请求，宿主执行工具。

#### C.7 继续菜单和库存：同一执行链，换了工具名与参数

第一次工具调用已经追完，后两次无需另找一套执行器。它们重新走 C.5 的查找、校验、钩子、执行、结果包装：

| 本次模型输出 | 工具查找结果 | 进入 A.5 的函数时收到什么 | 工具返回到消息中的主要内容 |
|---|---|---|---|
| A2：`list_meals({})` | `name="list_meals"` 的活跃工具 | 空参数对象 `{}` | A、B、C 的 `id/name/price/spicy` 数据 |
| A3：`get_stock({"ids":["C"]})` | `name="get_stock"` 的活跃工具 | `params.ids` 为 `["C"]` | `[{"id":"C","stock":12}]` |

以查询库存为例，调用链中的具体值变成：

```text
runLoop：收到 A3 中的 get_stock 工具调用
  → executeToolCalls → 执行分支 → prepareToolCall
    → 找到 name="get_stock" 的工具，校验 { ids: ["C"] }，钩子放行
  → executePreparedToolCall
    → 包装后的 get_stock.execute → A.5 注册定义的 execute
      → params.ids.map(...) 读取本例 stock["C"]，得到 12
    ← { content: [{ type: "text", text: '[{"id":"C","stock":12}]' }], details: ... }
  → 包成 R3，加入消息数组
  → 下一次 streamAssistantResponse：模型同时看到菜单与库存
  ← A4：推荐蛋炒饭，尚未下单
```

筛掉辣的 A、超预算的 B，再只查询 C 的库存，是这条教学轨迹中模型依据 Skill 与工具数据作出的选择；资源加载器不会替模型完成业务筛选。

最终 `await session.prompt(...)` 等待本次运行及相关重试处理完成，返回值是 `void`，不会直接返回答案字符串。A4 保存在消息状态，并通过 A.6 的订阅事件通知宿主，终端或界面再显示它。

#### C.8 如果模型请求下单，拦截器的输入和输出怎样影响执行

这是一条单独的异常分支，不是 A.11 正常四轮轨迹的必经步骤。假设模型额外输出 `place_order({"mealId":"C"})`，本例希望得到“工具被阻止”的结果，且不进入订单函数。

B.4 登记的监听函数此时才被调用。调用关系如下，`config.beforeToolCall` 通过 Agent 配置接到 B.5 安装的回调：

```text
prepareToolCall(..., place_order 的调用数据, ...)
  → config.beforeToolCall(...)
    → AgentSession 安装的 agent.beforeToolCall
      → ExtensionRunner.emitToolCall({
          type: "tool_call", toolName: "place_order", input: { mealId: "C" }, ...
        })
        → A.5 的 tool_call handler(event)
        ← { block: true, reason: "课堂演示只提供方案，不允许下单。" }
      ← Runner 将阻止结果交回
  ← prepareToolCall 返回即时错误结果，跳过 executePreparedToolCall
```

看 [prepareToolCall](/source/?file=6adbf9ab77a3572a2f.ts#L606) 对返回值的处理，以下为源码摘录：

```ts
if (beforeResult?.block) {
  return {
    kind: "immediate",
    result: createErrorToolResult(beforeResult.reason || "Tool execution was blocked"),
    isError: true,
  };
}
```

输入 `event.toolName` 决定监听函数是否返回阻止结果；输出 `block=true` 又决定核心执行分支是否跳过工具。这就解释了为什么它能阻止 `place_order.execute`：**核心程序检查并使用了返回值。** 错误结果仍会被包装为对应工具结果，交给后续模型处理，而不是在系统提示词里多写一句“不要下单”就算执行了拦截。

### D. 输入展开源码：普通文字、模板命令与显式 Skill 命令

#### D.1 三种输入各自落到哪条代码路径

普通文字、模板命令与显式技能命令的区别已放在 A.9，这里只核对它们是否经过宿主的文本展开。本例 `expandPromptTemplates=true`，没有同名扩展命令提前接管，也没有 `input` handler 改写输入。

A.9.1 中用户介绍技能、随后说“现在读取并按它处理”，在这一层都属于普通文字，不会被当成 `/skill:` 展开。它们作为用户消息交给模型；模型随后发出的 `read` 请求走 C 节的工具循环。先前对话让模型知道路径，不需要增加一条新的命令解析分支。

| A.9 的输入 | `_expandSkillCommand` | `expandPromptTemplate` | 随后交给 Agent 的 U |
|---|---|---|---|
| 普通午饭文字 | 不匹配，原样返回 | 不匹配，原样返回 | 原任务文字 |
| `/lunch ...` | 不是技能命令，原样返回 | 查模板并替换参数 | A.9.2 的展开文字 |
| `/skill:choose-lunch ...` | 查 Skill、读正文、包装 | 已不以斜杠开头，原样返回 | A.9.3 的方法正文加本次要求 |

按实际调用顺序，两次展开之前还有扩展命令与输入事件处理。D.4 给出两条命令分别经过的完整调用链。

#### D.2 模板分支：在断点处核对局部值

以 A.9.2 的输入进入 `expandPromptTemplate`，再进入参数解析与替换函数，核对：

| 代码中的值 | 本例应该是什么 |
|---|---|
| `templateName` | `"lunch"` |
| `argsString` | `不辣 20 "先给方案，不要下单"` |
| `args` | 三项字符串：`不辣`、`20`、`先给方案，不要下单` |
| `template.content` | B.3 中保存的模板正文，仍含 `$1`、`$2`、`${@:3}` |
| `substituteArgs` 的返回值 | A.9.2 的完整任务文字，不含模板 frontmatter |

沿调用返回 `AgentSession.prompt` 后，再看构造 U 时采用的 `expandedText`。这条路径复用已保存的模板，不需要在这里重新读取模板文件。

#### D.3 显式 Skill 分支：在断点处核对正文来源

以 A.9.3 的输入进入 `_expandSkillCommand`，核对技能查找、读文件和返回文字：

| 代码中的值 | 本例应该是什么 |
|---|---|
| `skillName` | `"choose-lunch"` |
| `args` | `不辣，20 元以内，先给方案，不要下单` |
| `skill.filePath` | B.3 加载对象中保存的技能绝对路径 |
| `content` | 再次从文件读到的整份 Skill，包括 frontmatter |
| `body` | 去掉 frontmatter 后的方法正文 |
| `skillBlock` 与最终返回值 | 带名称、位置、相对路径基准的正文包装，再附上 `args` |

返回值随后成为 `expandedText`，再进入 U；它没有先经过一次 `read` 工具调用。完整包装语句和异常分支见 D.4，第一轮消息的业务含义见 A.9.3。

#### D.4 再进代码：先展开 Skill 命令，后展开模板

回到 [AgentSession.prompt](/source/?file=24209413646c397dc9.ts#L968)，文本展开的源码是：

```ts
let expandedText = currentText;
if (expandPromptTemplates) {
  expandedText = this._expandSkillCommand(expandedText);
  expandedText = expandPromptTemplate(expandedText, [...this.promptTemplates]);
}
```

默认 `expandPromptTemplates=true`，因此本节会进入两次调用。但在它们之前还会尝试扩展命令、通知 `input` handler；本课扩展没有登记同名命令或输入改写，所以这两条输入都继续来到这里。若同名扩展命令已经接管，后面的模板或 Skill 展开就不会发生。

现在从调用处往定义处跳，分别代入 D.2、D.3 的字符串。

**模板分支的调用链：**

```text
session.prompt('/lunch 不辣 20 "先给方案，不要下单"')
  → _tryExecuteExtensionCommand(text) → 没有名为 lunch 的扩展命令，返回 false
  → _expandSkillCommand(text) → 不是 /skill: 开头，原样返回
  → expandPromptTemplate(text, 已加载的模板数组)
    ├─ templateName = "lunch"
    ├─ argsString = '不辣 20 "先给方案，不要下单"'
    ├─ templates.find(...) → 取得 B.3 保存的 lunch 模板对象
    ├─ parseCommandArgs(argsString) → ["不辣", "20", "先给方案，不要下单"]
    └─ substituteArgs(template.content, args) → 返回 A.9.2 的完整展开文本
  → 构造 user 消息 → agent.prompt([U]) → 后续沿 C 节运行
```

跳到 [expandPromptTemplate](/source/?file=81f806b0803812db28.ts#L293)，找到模板后执行的源码如下：

```ts
const template = templates.find((t) => t.name === templateName);
if (template) {
  const args = parseCommandArgs(argsString);
  return substituteArgs(template.content, args);
}
```

这里传给 `substituteArgs` 的第一个参数是加载时保存的模板正文，第二个参数是刚解析的三个字符串。模板在这里不用再次读磁盘；返回值仍是字符串，不会在函数内部查询菜单。

**显式 Skill 分支的调用链：**

```text
session.prompt('/skill:choose-lunch 不辣，20 元以内，先给方案，不要下单')
  → _tryExecuteExtensionCommand(text) → 本例没有对应扩展命令，返回 false
  → _expandSkillCommand(text)
    ├─ skillName = "choose-lunch"
    ├─ args = "不辣，20 元以内，先给方案，不要下单"
    ├─ getSkills().skills.find(...) → B.3 的技能对象
    ├─ readFileSync(skill.filePath, "utf-8") → 再次读取技能文件
    ├─ stripFrontmatter(content).trim() → 取得方法正文
    └─ 组合 skillBlock 与 args → 返回 A.9.3 所示的正文与本次要求
  → expandPromptTemplate(上一步结果, 模板数组)
    └─ 结果从 <skill 开始，不是斜杠命令，原样返回
  → 构造 user 消息 → agent.prompt([U]) → 第一次请求就带方法正文
```

进入 [_expandSkillCommand](/source/?file=24209413646c397dc9.ts#L1174)，正文读取和返回部分的源码如下，技能名与参数解析等语句省略：

```ts
const skill = this.resourceLoader.getSkills().skills.find((s) => s.name === skillName);
if (!skill) return text;

const content = readFileSync(skill.filePath, "utf-8");
const body = stripFrontmatter(content).trim();
const skillBlock = `<skill name="${skill.name}" location="${skill.filePath}">\nReferences are relative to ${skill.baseDir}.\n\n${body}\n</skill>`;
return args ? `${skillBlock}\n\n${args}` : skillBlock;
```

此处的“再次读取”与 C 节不同：C 节是模型请求 `read` 后，正文进入工具结果；这里是宿主在输入预处理时直接读文件，正文进入用户消息。如果技能未找到，函数返回原输入；读文件失败时会报告扩展错误并返回原输入，不能把所有 `/skill:` 字符串都当成已成功注入正文。

#### D.5 用两条边界检验你是否理解了展开过程

**第一条：本地实现不是递归展开。** 它先调用一次 `_expandSkillCommand`，后调用一次 `expandPromptTemplate`。如果把 `lunch.md` 的正文改成 `/skill:choose-lunch $ARGUMENTS`，模板展开得到的虽然是一行技能命令，但此时 Skill 展开步骤已经过去，不会自动回头再处理一遍。应像 A.3 那样写出任务与查阅要求，或者直接提交 `/skill:...`。

**第二条：这三个入口都不直接返回推荐答案。** 它们最终准备出不同的用户消息 U，随后仍进入 Agent 的模型与工具循环。可以在 `AgentSession.prompt` 构造 U 的位置停住：普通输入看见原请求，`/lunch` 看见 A.9.2 的展开文字，`/skill:` 看见 A.9.3 的方法正文与用户要求。再继续到首次模型请求，才能确认它实际收到了哪些材料。

### E. OpenClaw Bootstrap 源码：验证 A.8 的候选筛选与预算

#### E.1 代码阅读的输入输出：沿用 A.8 的 Workspace

OpenClaw 的完整文件例子、候选顺序、运行筛选和预算扣减已经放到 A.8。现在在源码里验证这些处理，不将独立 Pi 的 `AGENTS.md` 发现规则套到 OpenClaw 上。

| 源码交接点 | 应核对什么 |
|---|---|
| Workspace 加载返回 | 候选的 `name`、`path`、`content` 或 `missing`，顺序与 A.8.2 一致 |
| 会话筛选、模式处理及 Hook 之后 | 本次真正参与后续处理的候选集合 |
| 预算处理返回 | `contextFiles` 中每项的 `path`、实际 `content` 与总长度 |
| 系统提示词组装与覆盖之后 | 基础资料正文，以及另外生成的技能目录 |
| `activeSession.prompt` 之后的模型请求 | 本次系统提示词、用户消息与工具集合 |

这里追踪的是基础资料进入模型输入的路径；`BOOTSTRAP.md` 首次设置和 `BOOT.md` 启动任务的职责仍按开头的说明区分。

#### E.2 从 OpenClaw 运行入口到模型上下文

外层真实调用点在 [run/attempt.ts](/source/?file=4c2d09aeeb74b60140.ts)。阅读时按以下两支合流来跟踪：

```text
OpenClaw 一次 embedded run
  ├→ resolveAttemptBootstrapContext
  │    → 回调 resolveBootstrapContextForRun
  │      → resolveBootstrapFilesForRun
  │      → loadWorkspaceBootstrapFiles / 会话缓存
  │      → 会话与运行模式过滤、Bootstrap Hook
  │      → buildBootstrapContextFiles
  │    得到 contextFiles: [{path, content}, ...]
  │
  ├→ resolveSkillsPromptForRun
  │    得到 OpenClaw 筛选、限额后的技能目录
  │
  └→ buildEmbeddedSystemPrompt，把 contextFiles、skillsPrompt 等合并
       → createEmbeddedAgentSessionWithResourceLoader 创建并准备 Pi session
       → applySystemPromptOverrideToSession 应用外层构造的系统提示词
       → activeSession.prompt(effectivePrompt)
       → Agent / AgentLoop / 工具执行 / 下一次模型请求
```

Bootstrap 总入口的真实实现见 [bootstrap-files.ts](/source/?file=7c1bbc771f3fd53983.ts#L263)：

```ts
const bootstrapFiles = await resolveBootstrapFilesForRun(params);
const contextFiles = buildBootstrapContextFiles(bootstrapFiles, {
  maxChars: resolveBootstrapMaxChars(params.config),
  totalMaxChars: resolveBootstrapTotalMaxChars(params.config),
  warn: params.warn,
});
return { bootstrapFiles, contextFiles };
```

文件候选在 [workspace.ts 的 loadWorkspaceBootstrapFiles](/source/?file=1bbb045d02c254e25a.ts#L511)，字符预算在 [bootstrap.ts 的 buildBootstrapContextFiles](/source/?file=e5b04f17f3c5715d33.ts#L278)。最终正文进入系统提示词后，才随 `activeSession.prompt` 触发的模型请求被使用。

OpenClaw 外层还会重建、修改运行提示词和工具集合，不能把独立 Pi 的最终 `systemPrompt` 原样当成 OpenClaw 的最终请求。

##### E.2.1 resolveBootstrapContextForRun 在什么时候调用

**它由 OpenClaw 外层的运行流程调用，发生在创建 Pi 会话之前。** 所以在 `AgentSession`、Pi SDK 和 `ResourceLoader.reload()` 内部找不到它。

这条嵌入式 Pi 路径的执行顺序如下，中间省略其他准备工作：

```text
OpenClaw：runEmbeddedAttempt()
  │
  ├─ resolveAttemptBootstrapContext(...)
  │    └─ resolveBootstrapContextForRun(...)  ← 这里调用
  │         ├─ resolveBootstrapFilesForRun(...)
  │         │    └─ 读取或复用文件 → 筛选 → Hook → 清理
  │         └─ buildBootstrapContextFiles(...)
  │              → 返回 { bootstrapFiles, contextFiles }
  │
  ├─ buildEmbeddedSystemPrompt({ contextFiles, ... })
  │    → 构建 OpenClaw 系统提示词
  │
  ├─ new DefaultResourceLoader(...)
  ├─ await resourceLoader.reload()
  │
  ├─ createEmbeddedAgentSessionWithResourceLoader(...)
  │    └─ Pi SDK：createAgentSession({ resourceLoader, ... })
  │         └─ 创建 AgentSession
  │
  ├─ applySystemPromptOverrideToSession(session, systemPromptText)
  │    → 将外层准备好的提示词应用到 Pi 会话
  │
  └─ activeSession.prompt(...)
       → 开始本次任务
```

在同一个 `attempt.ts` 里按下面顺序跳转，就能把两边接起来：

| 源码位置 | 做什么 |
|---|---|
| [第 594 行](/source/?file=4c2d09aeeb74b60140.ts#L594) | 调用 Bootstrap 调度函数；第 602 行传入实际调用 |
| [第 898 行](/source/?file=4c2d09aeeb74b60140.ts#L898) | 通常将 `contextFiles` 交给系统提示词构建器；配置了完整提示词覆盖时走覆盖分支 |
| [第 1075 行](/source/?file=4c2d09aeeb74b60140.ts#L1075) | 创建 ResourceLoader，随后 `reload()` |
| [第 1161 行](/source/?file=4c2d09aeeb74b60140.ts#L1161) | 调用包装函数，进入 Pi SDK 创建会话 |
| [第 1182 行](/source/?file=4c2d09aeeb74b60140.ts#L1182) | 将 OpenClaw 提示词应用到会话 |

**这里要把两套准备流程分开理解：** OpenClaw 外层先准备自己的 Bootstrap 上下文与提示词；Pi 的 ResourceLoader 随后准备 Pi 的扩展、Skill、模板等资源。SDK 收到已经准备好的 `resourceLoader` 后，会直接复用它，见 [sdk.ts 第 194 行](/source/?file=07502145bf1ffa712b.ts#L194)。

这里的“创建会话之前”指这次 attempt 装配 Pi 会话的先后顺序，不代表只在整个 Session 生命周期的最初调用一次，也不是每执行一个工具都重新走一次。普通运行会经过 `resolveAttemptBootstrapContext` 的判断：满足续轮跳过条件时，返回空的 Bootstrap 上下文并跳过实际调用，见 [attempt.context-engine-helpers.ts 第 34–47 行](/source/?file=3ec792ba6a38339f2a.ts#L34)。

另外，[compact.ts 第 468 行](/source/?file=b687488d4e2e73c03f.ts#L468) 也会直接调用这个函数，用于压缩流程中的上下文准备。因此它既用于普通运行，也用于压缩；不能只在 `AgentSession.prompt()` 或 SDK 的默认加载分支里寻找它。

### F. 课堂断点表：从哪一行能证明已经用到 Skill

| 观察点 | 文件 / 函数 | 应看到的本例数据 |
|---|---|---|
| 资源已发现 | `resource-loader.ts / updateSkillsFromPaths` | 名为 choose-lunch 的 Skill 对象 |
| 目录已注入 | `system-prompt.ts / buildSystemPrompt` | `<available_skills>`，仅元数据 |
| 用户任务已接收 | `agent-session.ts / prompt` | `expandedText` 与 `role=user` |
| 模型选择技能 | `agent-loop.ts / runLoop` | assistant 的 `read` 工具块 |
| 真正读取文件 | `tools/read.ts / execute` | Skill 的绝对路径及文件正文 |
| 正文进入活动上下文 | `agent-loop.ts / runLoop` | `currentContext.messages` 新增 `toolResult` |
| 正文进入后续请求 | `agent-loop.ts / streamAssistantResponse` | `llmContext.messages` 含正文 |
| 按方法执行查询 | `lunch.ts / list_meals.execute` | 实际执行的业务工具及参数 |

“已发现 Skill”只能证明资源加载成功；“后续模型请求有正文，并发生符合方法的工具操作”才能说明本次轨迹如何使用了它。

---

## 第三部分：加载算法与边界核对

### 20. 所有“加载”都应该拆成几个问题

| 问题 | 应检查什么 |
|---|---|
| 去哪里找 | 候选目录、配置、资源包、显式路径 |
| 找到的是谁 | 规范化路径、资源名、来源元数据 |
| 是否接受 | 文件格式、路径边界、大小、启用条件 |
| 冲突怎么办 | 同名去重、加载顺序、诊断 |
| 生成什么 | 上下文文本、技能目录、运行时注册对象 |
| 什么时候生效 | 本次请求、下一轮、下一次 run、reload 后 |

只看见一个 `load` 函数名，无法回答这六个问题。

### 21. Bootstrap 的算法

```text
输入：Workspace、配置、Session 标识、运行模式

1. 取得候选引导文件；部分路径可能复用 Session 缓存。
2. 按 Session 类型过滤候选。
3. 应用上下文模式过滤。
4. 运行 Bootstrap Hook，接收修改后的候选集合。
5. 清理无效路径，并执行相关运行规则。
6. 按顺序处理文件：
       文件缺失 → 产生受预算限制的缺失提示；
       文件过长 → 首尾截断并添加标记；
       总预算不足 → 停止或跳过后续处理。
7. 输出带 path、content 的 Context Files。
8. 系统提示词构造器将它们组织成模型输入的一部分。
```

这是数据装配流程，不是让 LLM 来决定怎样遍历目录。

### 22. Skill 的算法

```text
输入：资源根目录、显式路径、配置、资格条件

1. 扫描候选 Skill。
2. 解析 SKILL.md 的元数据，形成 Skill 对象。
3. 规范化路径，去重，按加载器规则处理同名冲突。
4. 应用启用条件、允许范围和可见性规则。
5. 生成有预算限制的可用技能目录。
6. 模型按需调用 read；或宿主展开显式技能命令。
7. Skill 正文进入当前任务上下文。
```

OpenClaw 的环境资格条件还可能涉及配置、所需程序或环境条件；它们属于加载器判断，不是正文执行结果。

### 23. Extension 的算法

```text
输入：启用的扩展路径或内联工厂

1. 创建这一批扩展共享的 ExtensionRuntime。
2. 对每个扩展加载模块，取得工厂函数。
3. 创建该扩展独立的 handlers、tools、commands 等容器。
4. 创建面向该扩展的 API。
5. 执行并等待工厂，用 API 保存注册项。
6. 收集成功扩展和加载错误。
7. 创建 / 更新 ExtensionRunner，绑定核心动作与 UI 能力。
8. 运行时在事件与工具钩子处查找并调用注册项。
```

工厂本身可以是异步的。不能把“注册 API 是同步方法”误读为“整个扩展加载一定同步完成”。

### 24. 三种输出结构

```text
Bootstrap：
    [{ path, content }, ...]

Skill：
    [{ name, description, filePath, baseDir, ... }, ...]
    + 可用技能目录文本

Extension：
    [{ handlers: Map, tools: Map, commands: Map, ... }, ...]
    + 共享 Runtime
    + 错误 / 冲突诊断
```

它们不是同一个数组里的三类文本。

### 25. 缓存和 reload 为什么不能忽略

资源发生修改后，要问的是：

```text
磁盘内容已经变了吗？
    ↓
加载器是否重新发现资源？
    ↓
目录、上下文或 Runtime 是否已经更新？
    ↓
下一次模型请求或事件处理是否使用更新后的对象？
```

Bootstrap 可能复用 Session 文件快照；Skill 目录可能复用 Snapshot；Extension 可能仍有旧的闭包和状态。

因此不能统一承诺“文件保存后下一条消息必定立即生效”。具体要看资源刷新与宿主绑定路径。

Pi 扩展失效机制还会阻止旧 Runtime 在 reload 或替换会话后继续执行部分动作。

---

## 第四部分：源码细节与定位索引

### 26. Bootstrap 的总入口

打开 [bootstrap-files.ts](/source/?file=7c1bbc771f3fd53983.ts#L263)。

```ts
// 源码摘录：resolveBootstrapContextForRun 的核心装配。
const bootstrapFiles = await resolveBootstrapFilesForRun(params);
const contextFiles = buildBootstrapContextFiles(bootstrapFiles, {
    maxChars: resolveBootstrapMaxChars(params.config),
    totalMaxChars: resolveBootstrapTotalMaxChars(params.config),
    warn: params.warn,
});
return { bootstrapFiles, contextFiles };
```

`bootstrapFiles` 保留候选及加载信息；`contextFiles` 是加工后准备注入的内容。返回两份结果有助于诊断“读到了文件，但最终注入了多少”。

### 27. 候选文件在哪里构造

打开 [workspace.ts 的 loadWorkspaceBootstrapFiles](/source/?file=1bbb045d02c254e25a.ts#L511)。

这里显式列出 AGENTS、SOUL、TOOLS、IDENTITY、USER、HEARTBEAT、BOOTSTRAP 等候选，并尝试解析记忆 Bootstrap 文件。

成功读取时保存内容，失败时保存 `missing` 标记。读取通过带边界检查的辅助函数进行。

接着看 [filterBootstrapFilesForSession](/source/?file=1bbb045d02c254e25a.ts#L582)，就能找到 subagent / Cron 的基础允许集合。

`resolveBootstrapFilesForRun` 还调用 `applyBootstrapHookOverrides`。这条 OpenClaw Hook 路径与后面 Pi 的 `pi.on(...)` 不属于同一个注册 API。

### 28. 两级预算在哪里扣减

打开 [bootstrap.ts 的 buildBootstrapContextFiles](/source/?file=e5b04f17f3c5715d33.ts#L278)。

```ts
// 源码摘录：当前文件额度与最终输出的预算处理。
const fileMaxChars = Math.max(1, Math.min(maxChars, remainingTotalChars));
const trimmed = trimBootstrapContent(file.content ?? "", file.name, fileMaxChars);
const contentWithinBudget = clampToBudget(trimmed.content, remainingTotalChars);
```

后面用 `contentWithinBudget.length` 扣减总额度，再保存 Context File。

该文件本地默认值是单文件 12,000 字符、总计 60,000 字符；配置可以覆盖。教学例子的 600 / 1000 不代表默认配置。

`trimBootstrapContent` 中的首尾比例分配针对扣除标记后的内容预算。最终还有长度限制与 UTF-16 边界处理。

### 29. Skill 文件格式与相对路径怎样对到源码

完整技能文件见 A.4，正文读取与结果回接的例子见 A.9.1。这里继续打开 [skills.ts 的 loadSkillFromFile](/source/?file=08398ed5b2b3650ff5.ts#L288)，核对输入的绝对路径、解析出的 frontmatter、名称与描述的校验，以及返回对象中的 `filePath` 和 `baseDir`。

其中 `baseDir` 来自技能文件所在目录；B.3 已展开这条读取调用链。目录提示会要求模型将参考文件的相对路径解析到技能目录，显式 Skill 展开的包装也带上这一基准。两者的实际构造分别见第 30 节与 D.4。

需要验证的是：返回的技能对象保存元数据与路径，参考文件并未在这里递归读取；正文及参考文件何时进入消息，要继续观察 C 节的文件工具结果或 D 节的显式输入展开。

### 30. 技能目录为什么只出现元数据

打开 [Pi 的 formatSkillsForPrompt](/source/?file=08398ed5b2b3650ff5.ts#L349)。

```ts
// 源码摘录：为每项技能生成目录条目。
for (const skill of visibleSkills) {
    lines.push("  <skill>");
    lines.push(`    <name>${escapeXml(skill.name)}</name>`);
    lines.push(`    <description>${escapeXml(skill.description)}</description>`);
    lines.push(`    <location>${escapeXml(skill.filePath)}</location>`);
    lines.push("  </skill>");
}
```

生成的是 name、description、location。没有把 Skill 正文接在每一项后面。

这段代码还会先过滤 `disableModelInvocation`，所以“已加载技能数”与“模型可见目录项数”也可能不同。

### 31. 显式技能命令如何展开

打开 [agent-session.ts 的 _expandSkillCommand](/source/?file=24209413646c397dc9.ts#L1174)。

核心步骤是：

```text
解析 /skill: 后面的名称和参数
    ↓
从 ResourceLoader.getSkills() 按名称查找
    ↓
读取 skill.filePath
    ↓
去掉 Frontmatter
    ↓
用带 name、location 和参考目录说明的块包装正文
    ↓
拼上用户参数
```

未知技能和读取失败有相应的保留原输入 / 诊断处理，并不会凭空执行一个同名工具。

### 32. OpenClaw 的 Skill 目录还要经过哪些步骤

打开 [skills/workspace.ts](/source/?file=70b1e55a5ec65eab28.ts)。

按以下函数顺序阅读：

```text
loadSkillEntries
    ↓
filterSkillEntries
    ↓
resolveWorkspaceSkillPromptState
    ↓
compactSkillPaths、排序
    ↓
applySkillsPromptLimits
    ↓
formatSkillsForPrompt 或紧凑目录格式
```

当目录过大时，本地代码可能切换为省略描述的紧凑格式，或减少目录条目，并生成提示。

`resolveSkillsPromptForRun` 还可能优先使用已有 Snapshot 的 prompt。

因此调试“模型为什么没看到某个 Skill”，应先检查发现、资格、可见性、预算与 Snapshot，而不是直接认定模型忽略了正文。

### 33. Extension 工厂怎样写

下面是 Pi 扩展的教学样例。假设应用确实注册了名为 `place_order` 的工具，演示环境要求一律阻止它：

```ts
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export default function blockOrder(pi: ExtensionAPI) {
    pi.on("tool_call", async (event) => {
        if (event.toolName === "place_order") {
            return {
                block: true,
                reason: "本次演示只比较方案，不提交订单。",
            };
        }
    });
}
```

工厂运行时，`pi.on` 保存处理函数。只有以后出现工具调用，内部的工具名检查才运行。

这里特意把演示规则写死，以便看清加载机制。真实业务若允许授权后下单，还需设计授权状态及其更新流程。

### 34. 模块加载后怎样取得工厂

打开 [extensions/loader.ts](/source/?file=d170abdf93d664a78b.ts#L348)。

本地实现通过 Jiti 导入扩展模块，检查默认导出是否是函数。

接着 `loadExtension` 中执行：

```ts
// 源码摘录：loadExtension 内的一组连续语句。
const extension = createExtension(extensionPath, resolvedPath);
const api = createExtensionAPI(extension, runtime, cwd, eventBus);
await factory(api);
```

`createExtension` 建立该扩展自己的 Map；`createExtensionAPI` 让注册操作写入这些 Map；`factory(api)` 完成实际注册。

模块导入会执行模块顶层代码，工厂也运行在宿主程序中。因此它与只解析 Markdown 的 Skill 加载有明显不同。

### 35. pi.on 实际怎样保存函数

打开 [createExtensionAPI](/source/?file=d170abdf93d664a78b.ts#L191)。

```ts
// 源码摘录：API 对象中的 on 方法。
on(event: string, handler: HandlerFn): void {
    runtime.assertActive();
    const list = extension.handlers.get(event) ?? [];
    list.push(handler);
    extension.handlers.set(event, list);
}
```

到这里还没有执行 handler。

不同扩展有自己的 `handlers` Map；同一批加载结果共享一个 `ExtensionRuntime`，它保存以后要绑定的操作入口和可变状态。

### 36. 为什么加载阶段不能随意发送会话消息

打开 [createExtensionRuntime](/source/?file=d170abdf93d664a78b.ts#L136)。

初始 Runtime 中，`sendMessage`、`appendEntry`、`setActiveTools` 等动作入口使用尚未初始化的占位实现。

这是因为工厂加载时，不一定已经绑定了可用的 AgentSession。

```text
加载期：可以声明需要监听什么、提供什么工具
绑定后：相应动作入口才能操作当前会话
```

`registerTool` 是允许在加载期进行的注册操作；它与立即调用该工具是两回事。

### 37. tool_call 为什么真的能挡住执行

先看 [AgentSession 安装工具钩子](/source/?file=24209413646c397dc9.ts#L382)：它把 Agent 的 `beforeToolCall` 接到 ExtensionRunner。

存在 `tool_call` handler 时，这条路径还会等待此前排入的会话事件队列，再发出工具调用拦截事件。

再看 [ExtensionRunner.emitToolCall](/source/?file=1a64f1a2d3fca70128.ts#L768)：

```ts
// 源码摘录：handler 返回值的处理。
if (handlerResult) {
    result = handlerResult as ToolCallEventResult;
    if (result.block) {
        return result;
    }
}
```

`block` 被传回工具执行路径处理，因此可以在实际执行前阻止调用。

它能够生效，依赖“核心路径真的调用并使用返回值”，而不是仅仅给事件起了一个名字。

### 38. 谁把整个资源集合准备好

打开 [DefaultResourceLoader.reload](/source/?file=9d3a691c82fb128e60.ts#L343)。

它组织包资源与显式路径、加载扩展工厂、收集冲突诊断，并更新 Skill、Prompt 等资源。

再看 [createAgentSession](/source/?file=07502145bf1ffa712b.ts#L176)：

```ts
// 源码摘录：没有传入 ResourceLoader 时的默认路径。
if (!resourceLoader) {
    resourceLoader = new DefaultResourceLoader({ cwd, agentDir, settingsManager });
    await resourceLoader.reload();
    time("resourceLoader.reload");
}
```

如果宿主传入自己的 ResourceLoader，就应由宿主确保准备工作符合要求。不能指望这个条件分支自动替所有自定义加载器执行 reload。

OpenClaw 的 [attempt.ts](/source/?file=4c2d09aeeb74b60140.ts) 正是把外层准备好的资源、工具和系统提示词接入 Pi 的位置之一。

### 39. 一张排查表

| 现象 | 优先检查的位置 |
|---|---|
| AGENTS.md 明明存在，模型却没看到完整内容 | Bootstrap 候选、模式过滤、Hook、字符预算、缓存 |
| Skill 在磁盘上，却没出现在目录里 | 路径发现、Frontmatter、同名冲突、资格、可见性和目录预算 |
| 模型知道有 Skill，但不知道详细步骤 | 本次上下文是否真正包含正文，read 是否成功 |
| Extension 文件存在，但 handler 没运行 | 是否加载工厂、是否注册、Runner 是否绑定、核心事件是否经过该钩子 |
| 注册工具后模型仍没用到 | 允许名称集合、活跃工具、运行快照与下一次模型请求 |
| reload 后旧回调操作会话时报错 | 是否继续使用失效 Runtime 或旧会话上下文 |

课堂练习：把“先查库存”分别写入 AGENTS.md、Skill 和 Extension。解释三种写法各自改变哪条路径，哪些依赖模型决策，哪些需要程序显式返回并处理控制结果。

上一讲：[09 SessionManager 全流程详解](/openclaw/chapter-09)  
下一讲：[11 记忆系统 RAG 原理](/openclaw/chapter-11)
