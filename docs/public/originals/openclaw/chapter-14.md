# 14 AgentSession 执行原理：与直接 new Agent 对照理解七项能力

第 13 讲已经把模型、认证、资源、工具和历史装配成会话。本讲接着执行用户输入，重点看 `session.prompt()` 比直接 `Agent.prompt()` 增加了哪些处理，以及输入排队、事件落盘、历史切换、压缩和重试怎样衔接。第 12 讲已用互联网 RAG 说明联网资料怎样经工具返回参与回答。学完本讲的单会话执行过程，第 15 讲再把视角扩展到多个会话之间的协作。

# 开场：先用 AgentSession 完成一次午饭会话

先站在使用者的位置看一遍：我要一个能用项目选餐规则、能中途改要求、能保存和重新打开讨论的午饭助手。**下面先给出操作与效果，再解释内部实现。**

这里采用 SDK 教学程序，开发者执行代码模拟用户输入；不是在额外的网页上点击按钮。第 13 讲已准备好模型、认证、资源加载器和菜单工具：蛋炒饭 10 元、鸡腿饭 20 元、牛肉面 30 元。

## 1. 先看完整操作过程：用户做什么，有什么好处

| 操作时机 | 用户要做的事／输入 | 宿主调用的代码 | 可以看到的效果与好处 |
|---|---|---|---|
| 开始前 | “这个助手怎么用？” | `session.prompt("/meal-help")` | 已注册扩展命令直接显示帮助，不必请模型猜这条命令的含义 |
| 空闲时 | “用选餐 Skill，预算20元，选最贵的一份” | `session.prompt("/skill:choose-lunch 帮我选一份20元以内最贵的午饭，先查菜单。")` | 会话读取 Skill，把项目规则与用户要求一起交给 Agent |
| 菜单查询中 | “预算改成15元” | `session.steer("预算改成15元。")` | 接入正在进行的任务，界面或终端可显示“待调整”，最终按15元选蛋炒饭 |
| 同一任务仍运行时 | “选好后只输出菜名和价格” | `session.followUp("选好后，再只输出菜名和价格。")` | 先排队，等当前选餐准备结束再处理，最后输出“蛋炒饭，10元” |
| 第一轮结束后 | “为什么没选鸡腿饭？” | `session.prompt("为什么没选鸡腿饭？")` | 沿用同一 Agent 的前文，说明20元超过最新15元预算；会话继续记录追问 |
| 历史就绪后 | “回到查完菜单时，按30元重新选” | `session.navigateTree(menuEntry.id, { summarize: false })`，再 `prompt(...)` | 旧方案保留，新分支选择牛肉面，不必自己同时修改历史位置与消息数组 |
| 下次启动 | “继续刚才那份讨论” | `SessionManager.open(savedFile)`，交给 `createAgentSession(...)` | 从文件恢复当前分支，接着问“刚才选了什么”即可引用牛肉面结论 |
| 后续聊得很长 | “保留预算和结论，把前面整理一下” | `session.compact("保留当前预算、菜单和选餐结论。")` | 用摘要与近期原文继续，原始记录仍留在历史树中 |
| 追问遇到临时限流 | 用户仍只问一次“刚才选了什么？” | 启用 `retry` 后调用 `session.prompt(...)` | 会话等待后从当前上下文继续，通知重试状态，用户不必重复发送问题 |

文件模板是另一种方便的发起方式：若项目有 `.pi/prompts/lunch.md`，用户可以发 `/lunch`，宿主调用 `session.prompt("/lunch")`。在这次演示中，它可以替代上表的首次 Skill 提问；不需要两种入口都发送一次。

## 2. 这次会话的核心使用代码

下面是一条完整的使用流程。模型、认证沿用第 13 讲；`resourceLoader` 已加载 `choose-lunch` Skill、`lunch` 模板和已注册的 `meal-help` 帮助命令，`listMeals` 返回上面的三份菜单。Skill、模板和菜单工具的内容在后文展开；帮助命令的最小扩展在本开场末尾给出。

### 2.1 创建会话，并把输出显示出来

```ts
import {
    createAgentSession, SessionManager, SettingsManager,
    type AgentSession,
} from "@mariozechner/pi-coding-agent";

const manager = SessionManager.create(process.cwd());
const settingsManager = SettingsManager.inMemory({
    retry: { enabled: false },
    compaction: { enabled: false },
});
const { session } = await createAgentSession({
    resourceLoader,
    sessionManager: manager,
    settingsManager,
    customTools: [listMeals],
    tools: ["list_meals"],
});
await session.bindExtensions({});

const stopDisplay = session.subscribe((event) => {
    if (event.type === "queue_update") {
        console.log("待调整：", event.steering, "待追问：", event.followUp);
    }
    if (event.type === "message_end") {
        console.log(event.message.role, event.message.content);
    }
});
```

**对应例子：** 创建后得到一个可反复使用的 `session`。打印监听用来显示消息，消息的历史保存已由 Session 内部接好，打印回调不需要再写文件。设置关闭自动重试和自动压缩，只为使这次课堂观察的结束时机清楚。

### 2.2 发起选餐，中途修改，再排队追问

```ts
// 已注册帮助命令：直接显示帮助，不走普通选餐模型调用。
await session.prompt("/meal-help");

// 开始选餐，先不 await，保留运行中的补充机会。
const running = ask(session,
    "/skill:choose-lunch 帮我选一份20元以内最贵的午饭，先查菜单。",
);

// 教学工具先等待放行；确认查询已开始，再发送两条补充。
await menuStarted;
await session.steer("预算改成15元。");
await session.followUp("选好后，再只输出菜名和价格。");
releaseMenu();
await running;

// 现在第一轮结束，普通追问复用同一个 session。
await ask(session, "为什么没选鸡腿饭？");
```

**对应例子：** 终端先显示帮助。选餐开始后能看到两条待发送文字；查菜单完成后，steering 先送达，推荐改为蛋炒饭；follow-up 后送达，输出菜名价格。最后的普通追问可以解释鸡腿饭20元超过新预算。

`menuStarted` 与 `releaseMenu()` 是本讲菜单工具提供的课堂控制，用来保证补充输入确实发生在查询过程中，第二部分第 1.0 节给出完整定义。`ask()` 是下面给出的观察包装；真正启动任务的仍是 `session.prompt()`。

### 2.3 从同一份历史里换一个方案

```ts
const menuEntry = manager.getBranch().find((entry) =>
    entry.type === "message" &&
    entry.message.role === "toolResult" &&
    entry.message.toolName === "list_meals",
);
if (menuEntry) {
    const result = await session.navigateTree(menuEntry.id, { summarize: false });
    if (!result.cancelled) {
        await ask(session, "预算改成30元，仍选预算内最贵的一份。");
    }
}
const savedFile = session.sessionFile;
console.log("会话文件：", savedFile);
```

**对应例子：** 先找到查菜单的真实历史节点，再同步历史位置与 Agent 消息。从那里改成30元后可以选牛肉面；15元蛋炒饭与追问仍留在旧分支。节点 ID 来自历史记录，不要求使用者自己拼接父子关系。

### 2.4 结束旧对象，重新打开这份会话

```ts
stopDisplay();
await session.abort();
session.dispose();

if (savedFile) {
    const { session: restored } = await createAgentSession({
        resourceLoader,
        sessionManager: SessionManager.open(savedFile),
        settingsManager,
        customTools: [listMeals],
        tools: ["list_meals"],
    });
    await restored.bindExtensions({});
    const stopRestoredDisplay = restored.subscribe((event) => {
        if (event.type === "message_end") console.log(event.message.content);
    });
    try {
        await ask(restored, "刚才预算是多少，选了哪一份？");
    } finally {
        stopRestoredDisplay();
        await restored.abort();
        restored.dispose();
    }
}
```

**对应例子：** 新的 AgentSession 可以按已保存的30元分支接着讨论，回答“30元，牛肉面”。这里用同一进程的新对象演示重新打开；跨进程时记下打印的 `savedFile`，下次准备好资源后将该路径交给 `SessionManager.open()` 即可。

打开文件与恢复旧菜单不会自动重新查询库存或菜单。这个后续追问才会调用模型；其回答措辞和是否再次查工具由实际模型行为决定。

### 2.5 以后讨论变长，再手动压缩

这是长对话时的另一项操作，独立于上面已经清理结束的演示；在仍有效、已积累足够历史的当前会话上调用：

```ts
async function compactAndContinue(activeSession: AgentSession): Promise<void> {
    const result = await activeSession.compact("保留当前预算、菜单价格、选餐规则和最终结论。");
    console.log(result.summary);
    await ask(activeSession, "现在预算是多少，最终选了什么？");
}
```

**对应例子：** 在尚未 dispose 的当前长会话上调用 `compactAndContinue(currentSession)`，较早讨论转成摘要，近期原文保留，后续模型继续回答预算与结论。自动压缩关闭不妨碍手动调用；本讲第六个场景给出足够长历史的压缩结果，不要求上面几句短对话立刻触发相同裁剪。

### 2.6 服务暂时限流时，允许会话自动再试

在仍有效的会话中，可以启用会话级自动重试；具体次数和退避时间在第七个场景配置：

```ts
async function askWithRetry(activeSession: AgentSession): Promise<void> {
    activeSession.setAutoRetryEnabled(true);
    await activeSession.prompt("刚才预算是多少，选了哪一份？");
}
```

**对应例子：** 用户只发一次问题。若服务先返回可重试的限流错误，会话按配置等待后调用内部 `agent.continue()`，成功后回答“30元，牛肉面”。本例原先关闭重试是为了观察前几个场景；启用它后，宿主应结合重试事件和这次 prompt 的等待来判断进度。

## 3. 观察包装：为什么这里用 ask

上述课堂例子关闭自动重试和自动压缩，没有额外事件扩展处理。包装在发起 prompt 前订阅结束通知，再同时等待 prompt 和这次 Session 的 `agent_end` 通知，便于随后检查前面已处理的历史消息：

```ts
async function ask(session: AgentSession, text: string): Promise<void> {
    let finish!: () => void;
    const ended = new Promise<void>((resolve) => { finish = resolve; });
    const unsubscribe = session.subscribe((event) => {
        if (event.type === "agent_end") finish();
    });
    try {
        await Promise.all([session.prompt(text), ended]);
    } finally {
        unsubscribe();
    }
}
```

**对应例子：** 初次选餐时，`ask()` 一直等到 steering、follow-up 都被本例循环消费并发出结束通知；后面的历史查找因此不会只看到半轮消息。它仅用于本例从空闲发起的普通模型输入，不用于已接管并直接返回的 `/meal-help`，也不是任意后台任务的通用等待方法。

上面 `/meal-help` 的注册可以使用项目文件 `.pi/extensions/meal-help.ts`。在第 13 讲的资源加载阶段发现该文件，宿主等待 `resourceLoader.reload()` 后再创建会话：

```ts
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export default function mealHelp(pi: ExtensionAPI) {
    pi.registerCommand("meal-help", {
        description: "显示午饭助手的用法",
        handler: async () => {
            console.log("用 /skill:choose-lunch 或 /lunch 开始；查询中可改预算，选好后可继续追问。");
        },
    });
}
```

**对应例子：** `session.bindExtensions({})` 后，命令注册表已有 `meal-help`。开场的 `session.prompt("/meal-help")` 就执行这个 handler 并直接返回；若没配置这个扩展，不能期待任意 `/meal-help` 都自动成为命令。

从这个完整流程可以看到：**直接 Agent 本来就能选餐、追问和排队；AgentSession 的好处是把命令与资源展开、待发送状态、消息记录、历史导航、恢复和压缩接成一套可直接使用的会话操作。** 接下来再看能力清单和每个场景的具体实现。

# 看完例子，再对照 AgentSession 比直接 Agent 多了什么

**会话入口识别“用户发来的内容是不是一条命令、一个 Skill 调用或一个模板调用”，再决定交给 Agent 什么。** 上面的使用过程对应下面这些新增或接好的能力。

这里比较的是“直接 new Agent，没有自行添加会话逻辑”和“使用 AgentSession 及其连接的 SDK、扩展、Manager”。两者都通过原来的 Agent Loop 执行模型与工具。

## 先列清单：多了哪些东西，用户具体怎么用

| 新增或接好的能力 | 具体输入／操作 | Session 这一层做什么 | 直接 Agent 的情况 |
|---|---|---|---|
| **扩展斜杠命令** | `session.prompt("/meal-help")`，前提是扩展已注册该命令 | 查命令注册表，执行 handler；已接管则返回，不自动发起普通模型请求 | `agent.prompt("/meal-help")` 把它当普通文字，不查扩展命令注册表 |
| **Skill 显式调用** | `session.prompt("/skill:choose-lunch 预算20元")` | 查找已加载 Skill，读取 SKILL.md，去掉头部，将正文与参数包装进 user 消息 | 不自行查 Skill 文件；应用先展开后再传给 Agent |
| **文件提示词模板** | `session.prompt("/lunch")`，项目已配置 `.pi/prompts/lunch.md` | 将模板调用展开为文件正文，再交给 Agent | 不自行读取模板；只接收宿主给的文字 |
| **输入与启动前扩展** | 用户输入“午饭老规矩”；扩展把它改成 Skill 调用，或补充“今日只提供堂食” | input 阶段可改写／接管，before_agent_start 可补消息、调整本次系统提示词 | 此入口不自动接这套扩展生命周期，应用自行准备或安装回调 |
| **会话运行预检** | 发送选餐要求，但尚未选模型或配置认证 | 提前检查模型、认证来源，并按条件检查是否先压缩上下文 | 依赖应用配置模型与认证；Agent.prompt 本层没有这些会话预检 |
| **待发送文字与排队入口** | 查询中 `session.steer("预算改成15元")`，或用带 streamingBehavior 的 prompt | 包装消息、维护待发送文字、发 queue_update；交给 Agent 已有队列 | Agent 已有 steer/followUp 队列；文字包装与显示状态由应用补齐 |
| **自动连接消息保存** | 正常选餐过程中完成一条 user、assistant 或 toolResult 消息 | 内部监听事件，交给 SessionManager 追加历史；持久化由 Manager 执行 | 有事件和内存消息，但保存监听、历史文件由应用接入 |
| **历史导航与恢复** | 回到菜单节点另选方案；下次打开旧会话 | navigateTree 同步历史位置和 Agent 消息；Manager＋SDK 完成历史恢复装配 | 可以使用宿主装回的消息，历史树、文件与同步流程由应用管理 |
| **会话上下文压缩** | `session.compact("保留当前预算和选餐结论")` | 生成摘要、保存压缩边界，重建 Agent 当前消息 | 应用自行组织摘要、保存、转换和消息替换 |
| **会话级自动重试** | 启用 retry，普通追问遇到429或暂时过载 | 判断错误、退避等待、继续当前上下文、发重试事件并协调等待 | Agent 没有这套会话级恢复策略；Provider/SDK 底层可能另有请求重试 |

其中前三项都是斜杠开头，却有不同的处理结果：

```text
/meal-help                 → 执行已注册扩展命令，可能直接结束本次入口处理
/skill:choose-lunch 预算20元 → 读 Skill 正文，变成供模型阅读的完整 user 文字
/lunch                     → 读提示词模板，变成供模型阅读的普通 user 文字
```

**斜杠只是输入形式，不代表都会执行一个函数，也不代表都会发模型请求。** Skill 与模板展开后仍交给原来的 Agent；扩展命令可以直接处理业务，也可以由其 handler 自行发起其他操作。

## 再分清：哪些能力 Agent 本来就有

直接 `new Agent(...)` 已经有 `prompt()`、`steer()`、`followUp()` 和 `subscribe()`，也保留 `agent.state.messages` 支撑内存中的连续追问。它能读宿主提供的工具定义、执行模型提出的工具调用，并发出运行事件。

AgentSession 接的是上表中的会话处理。尤其不能把“支持中途改预算”“可以收到事件”本身说成新增能力；新增的是围绕这些已有能力的输入处理、状态通知、扩展调度和历史操作。

还要区分 Pi 界面的内置命令：`/model`、`/login`、`/tree`、`/compact` 等由[交互宿主](../pi-master/packages/coding-agent/src/modes/interactive/interactive-mode.ts)先识别，再调用相应服务。不能据此推断直接调用 `session.prompt("/compact")` 就会触发内置压缩；SDK 手动压缩使用 `session.compact()`。本讲 `prompt()` 中首先查的是扩展注册命令。

`createAgentSession()` 是工厂函数，`AgentSession` 是它创建的会话对象，两者都不是另一套 Agent Loop。得到 `session` 后，通常复用它处理多次输入。

**只需要调用模型、工具和内存中的连续对话时，直接 Agent 就够。需要上述配套能力时，可以使用 AgentSession，也可以由应用自己实现。** 下面先讲简单场景，再逐项对照核心代码。

# 第一部分：七个场景的完整输入与处理结果

## 1. 操作方式与共同数据

本例使用 SDK：开发者在教学项目里执行 TypeScript 调用，模拟用户输入。模型、认证和资源加载沿用第 13 讲。七个场景只使用一个 `list_meals` 工具，返回：

```json
[
  { "name": "蛋炒饭", "price": 10 },
  { "name": "鸡腿饭", "price": 20 },
  { "name": "牛肉面", "price": 30 }
]
```

先用 Skill 发起 20 元选餐任务，在菜单查询过程中修改为 15 元、排队要求格式化回答，再观察事件保存，回到菜单结果按 30 元重选，演示对话变长后的上下文压缩，再独立观察一次模型限流后的自动重试。

下文的消息编号 L0～L6、历史节点 e0～e6、时间戳和工具调用 ID 都是教学数据。为把 Skill 展开的字符串写清楚，统一假设加载器记录的项目路径为 `/course/lunch`；实际运行用本机路径。模型调用和回答固定推演，不是实测日志。

## 2. 场景一：prompt，加入 Skill 后到底发给 Agent 什么

### 2.1 先给出 Skill 文件

项目中有 `.pi/skills/choose-lunch/SKILL.md`，完整内容为：

```markdown
---
name: choose-lunch
description: 查询菜单，并按用户当前预算选择价格最高的一份午饭。
---
先调用 list_meals 查询菜单。
在用户当前预算以内，选择价格最高的一份。
用户修改预算后，按最新预算选择。
```

资源加载器已发现这个 Skill，记录了 `name = choose-lunch`、`filePath = /course/lunch/.pi/skills/choose-lunch/SKILL.md`、`baseDir = /course/lunch/.pi/skills/choose-lunch`。这是本例展开命令的前提。

### 2.2 用户操作：显式使用这个 Skill

开发者执行下面这一行，模拟用户发送命令：

```ts
const sessionRunning = session.prompt(
    "/skill:choose-lunch 帮我选一份20元以内最贵的午饭，先查菜单。",
);
```

**对应例子：** 此时 Agent 空闲。Session 解析出技能名 `choose-lunch` 和后面的选餐要求，读取技能文件，去掉 YAML 头部，再包装正文。这里先不等待 `sessionRunning` 完成，后面要在工具查询中补充要求。

### 2.3 展开后，prompt 的完整文字

经过 `_expandSkillCommand()` 后，`expandedText` 就是下面这整段，换行也按源码格式展示：

```text
<skill name="choose-lunch" location="/course/lunch/.pi/skills/choose-lunch/SKILL.md">
References are relative to /course/lunch/.pi/skills/choose-lunch.

先调用 list_meals 查询菜单。
在用户当前预算以内，选择价格最高的一份。
用户修改预算后，按最新预算选择。
</skill>

帮我选一份20元以内最贵的午饭，先查菜单。
```

将这段文字记为 `expandedLunchText`。它接着被包装为一条 user 消息 L0：

```text
L0.role = "user"
L0.content = [{ type: "text", text: expandedLunchText }]
L0.timestamp = 本次创建时间

本次调用：内部 agent.prompt([L0])
首次模型请求的材料：systemPrompt + [L0] + list_meals 工具定义
```

所以，**Skill 正文和本次选餐要求在这里进入同一条 user 消息。** YAML 的 name、description 没有原样粘进去；name 和路径用于外层标记。Skill 也没有变成一个自动执行的 JavaScript 工具。

系统提示词与 L0 仍是两个位置。`system-prompt.ts` 在启用 `read` 工具时可以追加 `<available_skills>` 目录，目录只列名字、说明和路径。本例只启用 `list_meals`，默认构建不会追加该目录；但显式 `/skill:` 展开仍可由 Session 读取文件，不依赖模型调用 `read`。

### 2.4 直接 new Agent 会有什么不同

| 操作 | 直接 Agent | AgentSession |
|---|---|---|
| 原样传入 `/skill:choose-lunch ...` | 它只把这串文字包装成 user 消息，不自行寻找 Skill 文件 | 解析技能名、读取正文、构造上面完整的 `expandedText` |
| 希望模型真正看到这三条技能规则 | 应用先展开，调用 `agent.prompt(expandedLunchText)` | 调用 `session.prompt(skillCommand)`，由会话层展开 |
| 最后执行菜单查询 | 原来的 Agent Loop 执行 | 仍由内部 Agent 的原循环执行 |

后面的 A/B 对照让 A 手工提供同样的 `expandedLunchText`，B 使用 `/skill:` 命令。这样进入循环的业务材料一致，可以清楚比较 Session 额外承担的工作。

## 3. 场景二：steer，查询中改预算，队列里究竟是什么

### 3.1 用户何时补充

模型读到 L0，返回 L1：调用 `list_meals`。工具已开始，但尚未返回菜单。开发者这时执行：

```ts
await session.steer("预算改成15元。");
console.log(session.getSteeringMessages());
```

**对应例子：** 调用只等待入队。当前已完成的 Agent 消息还是 L0、L1，L2 菜单结果还没有出现；getter 输出 `["预算改成15元。"]`。

### 3.2 一句文字被保存成哪两种数据

```text
Session 的显示列表：
  _steeringMessages = ["预算改成15元。"]

Agent 的真正执行队列收到：
  { role: "user",
    content: [{ type: "text", text: "预算改成15元。" }],
    timestamp: t1 }

宿主收到：
  { type: "queue_update",
    steering: ["预算改成15元。"], followUp: [] }
```

这里的预算消息已经排队，还未进入活动上下文，也未作为普通消息 Entry 保存。菜单返回为 L2 后，循环在检查点取出它，产生 L3 的 `message_start`、`message_end`。

此后的模型请求使用 `[L0, L1, L2, L3]`。L0 中的 Skill 要求“按最新预算”，L3 明确将 20 元改成 15 元，模型因此给出 L4：推荐 10 元蛋炒饭。

### 3.3 和直接 Agent 的区别

A 自己构造上述 user 消息，调用 `agent.steer(message)`；B 用字符串调用，Session 负责包装、待发送列表和通知。两者的队列消费时机都由 Agent Loop 决定。

L3 送达时，B 先从显示列表移除这句话并通知 `steering: []`，再按完整消息保存。A 若也要这份显示状态，需要宿主自己维护。

## 4. 场景三：followUp，队列中第二句话何时才出现

### 4.1 用户继续追加，但先不处理

仍在菜单工具等待返回的时候，开发者执行：

```ts
await session.followUp("选好后，再只输出菜名和价格。");
console.log(session.getSteeringMessages());
console.log(session.getFollowUpMessages());
```

**对应例子：** 两个列表分别输出 `["预算改成15元。"]` 和 `["选好后，再只输出菜名和价格。"]`。这时两条补充都在队列里，尚未成为 L3、L5。

Agent 的 follow-up 队列收到的消息是：

```text
{ role: "user",
  content: [{ type: "text", text: "选好后，再只输出菜名和价格。" }],
  timestamp: t2 }
```

### 4.2 放行菜单后，按什么顺序处理

| 时刻 | 模型或循环在做什么 | Session 待调整列表 | Session 待追问列表 |
|---|---|---|---|
| 查询尚未完成 | 等 L2 菜单 | 预算改成 15 元 | 只输出菜名和价格 |
| L2 返回，L3 送达 | 下一次响应按 15 元选餐 | 空 | 只输出菜名和价格 |
| L4 给出蛋炒饭方案 | 没有新工具和 steering，准备结束 | 空 | 仍在等待 |
| L5 送达 | 将格式要求加入后继续请求模型 | 空 | 空 |
| L6 返回 | 输出“蛋炒饭，10元” | 空 | 空 |

L5 送达后的模型上下文是 `[L0, L1, L2, L3, L4, L5]`；它已经知道选中蛋炒饭，现在按新要求输出格式化结果。

### 4.3 和直接 Agent 的区别

直接 `agent.followUp(message)` 已有同样的消费时机；Session 增加文字包装、Skill/模板展开、待发送状态和保存衔接。follow-up 使同一次 run 继续，到 L6 后才按本例条件发出 `agent_end`。

这里演示的是“选好后再处理下一条”。若把格式要求也放进 `steer()`，它会在 steering 检查点进入当前任务，而不是在循环准备结束时才取出。

## 5. 场景四：事件处理，一份菜单怎样从事件变成历史记录

### 5.1 固定看 L2，而不是只说“会收到事件”

菜单工具返回后，Agent 产生 L2 的完成事件。只展示与本例有关的字段：

```json
{
  "type": "message_end",
  "message": {
    "role": "toolResult",
    "toolCallId": "call_menu",
    "toolName": "list_meals",
    "content": [{
      "type": "text",
      "text": "[{\"name\":\"蛋炒饭\",\"price\":10},{\"name\":\"鸡腿饭\",\"price\":20},{\"name\":\"牛肉面\",\"price\":30}]"
    }],
    "isError": false,
    "timestamp": 1003
  }
}
```

这是菜单数据作为工具结果消息的形状。它不会自动变成助手最终回答；循环还要把结果交给模型。

### 5.2 事件处理每走一步，状态怎样变化

| 步骤 | 实际处理 | 结果 |
|---|---|---|
| 1 | Agent 的 `processEvents()` 处理 L2 | `agent.state.messages` 从 `[L0, L1]` 变为 `[L0, L1, L2]` |
| 2 | 通知 Session 内部监听 | L2 的处理接入 `_agentEventQueue` |
| 3 | `_processAgentEvent()` 通知扩展、宿主 | 宿主可以打印菜单；此时本条历史追加还在后面 |
| 4 | `appendMessage(L2)` | 新建 e2，`parentId = e1`，leaf 变为 e2 |
| 5 | Manager 持久化 | 启用持久化且已有助手消息时，追加对应 JSONL 记录 |

宿主可这样观察具体消息：

```ts
session.subscribe((event) => {
    if (event.type === "message_end" && event.message.role === "toolResult") {
        console.log(event.message.toolName);
        console.log(event.message.content);
    }
});
```

**对应例子：** 这个监听在运行前注册。L2 完成后，输出工具名 `list_meals` 和菜单正文；保存路径由 Session 内部执行，不由这段打印代码触发。

### 5.3 和直接 Agent 的区别

A 的 `agent.subscribe()` 也能收到这份 L2，并且 Agent 已完成第 1 步。A 要将它存成历史，需要应用自己接 Manager；B 已接好第 2～5 步。普通消息、工具结果都分别保存，流式增量不会被每个 token 单独保存为一条历史消息。

本例所有业务消息按送达顺序是：L0 Skill 与选餐要求 → L1 菜单调用 → L2 菜单结果 → L3 新预算 → L4 推荐 → L5 格式要求 → L6 格式化回答。

## 6. 场景五：会话处理，先写清节点和消息，再演示导航

### 6.1 已保存的历史具体是什么

省略初始模型配置 Entry 后，消息与历史节点这样对应：

| Entry ID | parentId | 保存的消息 |
|---|---|---|
| e0 | 初始配置节点 | L0：完整 Skill 块和 20 元要求 |
| e1 | e0 | L1：调用菜单工具 |
| e2 | e1 | L2：完整菜单结果 |
| e3 | e2 | L3：预算改成 15 元 |
| e4 | e3 | L4：推荐蛋炒饭 |
| e5 | e4 | L5：格式要求 |
| e6 | e5 | L6：蛋炒饭，10 元 |

此时 Manager 的 leaf 是 e6，Agent 活动消息是 `[L0, L1, L2, L3, L4, L5, L6]`。Entry ID 不等于消息简称，也不等于 `call_menu` 工具调用 ID。

### 6.2 用户回到菜单结果，并改成30元

运行与消息历史处理都完成后，开发者找到菜单结果的真实 Entry ID，执行下面的调用。这里用 `menuEntryId` 表示该 ID，本次教学编号为 e2：

```ts
const navigation = await session.navigateTree(menuEntryId, { summarize: false });
if (!navigation.cancelled) {
    await session.prompt("预算改成30元，仍选预算内最贵的一份。");
}
```

**对应例子：** `navigateTree()` 先将 Manager leaf 移到 e2，再把 Agent 消息替换成 `[L0, L1, L2]`。L0 中的 Skill 规则仍在，但旧分支的 15 元预算和格式要求已经不在当前上下文里。然后才发送新的 30 元要求。

新记录和旧记录同时存在：

```text
                     ┌→ e3(L3) → e4(L4) → e5(L5) → e6(L6)
e0(L0) → e1 → e2 ───┤
                     └→ b0(30元要求) → b1(牛肉面，30元)
```

新请求的材料是 `systemPrompt + [L0, L1, L2, B0] + 工具定义`。其中 B0 是 b0 保存的新用户消息，它覆盖了 L0 原来的 20 元预算；Skill 要求按最新预算选择，因此这次推荐牛肉面。

### 6.3 重新打开，会恢复哪几条消息

b1 已经保存后，下次用 `SessionManager.open(savedFile)` 和 `createAgentSession(...)` 打开，恢复的当前消息是 `[L0, L1, L2, B0, B1]`。

它包含最初展开的 Skill 正文和菜单历史，不包含旧分支 L3～L6。恢复 L0 时直接使用已记录的正文，不重新展开当时的 `/skill:` 命令，也不查询菜单或请求模型。启动时的资源发现可能重新读取 Skill 文件以建立元数据，但不会替换旧 L0；再次调用 `/skill:choose-lunch ...` 时，才为那次新输入读取并展开当前正文。

A 也能实现同样效果，但应用需要自己读取历史、选分支、替换消息和接回保存监听；B 把这些流程接成现成的会话操作。

## 7. 场景六：compact，对话变长后怎样压缩再继续

### 7.1 什么时候需要压缩

接着 30 元的新分支继续讨论多轮午饭方案，积累了较长的菜单分析与比较。当前分支的 Agent 活动消息是：

```text
[L0, L1, L2, B0, B1, B2, ... , B17, B18, B19]
```

L0 是最初的 Skill 正文与 20 元要求，B0 已改为 30 元。B2～B19 是新分支后续讨论，消息要点如下：

| 范围 | 内容要点 |
|---|---|
| L0～B17 | 选餐规则、菜单价格、预算改为 30 元，以及较长的方案讨论 |
| B18 用户 | “继续按30元预算，帮我确认最终方案。” |
| B19 助手 | “选牛肉面，30元，是预算内最贵的一份。” |

开发者希望把较早讨论整理成摘要，保留近期原文，再继续问。这里固定一个教学压缩结果：`firstKeptEntryId = "b18"`，从 B18 开始保留原文；真实边界由保留 token 预算与消息长度计算，不是在调用中按编号指定。表中只列讨论要点，不能据此推算实际 token 长度。

### 7.2 用户操作：显式要求会话压缩

确认相关历史处理完成后，开发者执行：

```ts
const result = await session.compact(
    "保留当前30元预算、菜单价格、按最新预算选择最贵一份的规则，以及已选牛肉面的结论。",
);
console.log(result.summary);
console.log(result.firstKeptEntryId);
```

**对应例子：** 这是 SDK 手动操作，没有新增界面按钮。`compact()` 取得当前分支，准备压缩范围，默认调用模型生成摘要，然后保存并更新 Agent。调用参数是摘要的额外要求，不是新的选餐 user 消息，也不是要求再推荐一次午饭。

本例假定生成的摘要正文为：

```text
用户需要按当前预算选择价格最高的一份午饭。
菜单：蛋炒饭10元、鸡腿饭20元、牛肉面30元。
当前分支已将预算从20元改为30元，最终选择牛肉面30元。
后续继续遵循最新预算，不必保留早期比较过程的全部原文。
```

这是教学摘要，实际措辞由模型决定。此前的 Skill 正文若落在被压缩范围，就不再逐字出现在活动消息中；要继续遵守的规则需保留在摘要或其他仍有效的上下文中。

### 7.3 保存的不是一条普通 assistant 回答

Manager 在当前历史末尾追加一条 `compaction` Entry，相关字段示意如下：

```json
{
  "type": "compaction",
  "id": "c0",
  "parentId": "b19",
  "summary": "用户按当前预算选最贵午饭；菜单为10、20、30元；当前预算30元，已选牛肉面。",
  "firstKeptEntryId": "b18",
  "tokensBefore": 28000
}
```

上面 `summary` 为便于看结构而缩写，`tokensBefore` 是教学数值；实际保存完整的 `result.summary`，还有时间戳、details 等字段。`firstKeptEntryId` 指向保留原文的起点，不是 compaction 节点自己的 ID。

```text
历史树：L0 → L1 → L2 → B0 → ... → b18(B18) → b19(B19) → c0
        原记录仍保留，没有从文件中删除

Agent 活动消息：
  [C：compactionSummary, B18：user, B19：assistant]
```

C 来自 c0 的摘要；Manager 沿当前路径找到压缩记录，先放入摘要，再加入 b18 及之后需要保留的消息。旧的 15 元分支也仍在历史树中，这次压缩只取当前分支。

### 7.4 压缩后继续提问，模型实际看什么

开发者再执行：

```ts
await session.prompt("现在预算是多少，最终选了什么？");
```

**对应例子：** 新问题记为 B20。下一次请求使用 `systemPrompt + [C, B18, B19, B20] + 工具定义`，模型可依据摘要与近期原文回答“预算30元，选了牛肉面，30元”。不再把 L0～B17 全部原文放进本次请求。

在 Agent 内部，C 的角色是 `compactionSummary`。SDK 的消息转换将它转成模型支持的 user 消息，其正文按当前源码包装为：

```text
The conversation history before this point was compacted into the following summary:

<summary>
用户需要按当前预算选择价格最高的一份午饭。
菜单：蛋炒饭10元、鸡腿饭20元、牛肉面30元。
当前分支已将预算从20元改为30元，最终选择牛肉面30元。
后续继续遵循最新预算，不必保留早期比较过程的全部原文。
</summary>
```

所以需要分清三个形状：**历史中是 `compaction` Entry，Agent 中是 `compactionSummary` 消息，转换给模型后是带摘要正文的 user 消息。** 系统提示词仍单独提供。

### 7.5 和直接 new Agent 的区别

| 直接 Agent | AgentSession |
|---|---|
| Agent 不会自动生成这份历史摘要，也没有 `agent.compact()` 会话接口 | `session.compact()` 组织当前分支的摘要生成与应用 |
| 应用可自己生成摘要，或用 `transformContext` 裁剪单次请求材料 | 会话层将摘要与保留边界写为 compaction Entry |
| 若要重启后仍使用同样压缩结果，应用需接保存、恢复和消息转换 | Manager 重建压缩后的上下文，Session 同步到内部 Agent |

只做单次 `transformContext` 裁剪，不等于已经把历史树和 Agent 当前消息改成上面的压缩状态。这里多的是一整套会话状态处理；具体摘要算法可继续读第 08 讲。

## 8. 场景七：自动重试，模型先返回429，稍后继续成功

### 8.1 用户只发一次追问

从第五个场景已保存的30元分支重新打开，独立演示重试。原历史记为 H，即 `[L0, L1, L2, B0, B1]`；用户问：

> 刚才预算是多少，选了哪一份？

新问题记为 R0。本例假设模型服务第一次没有给出答案，而是返回一次限流错误；第二次服务恢复正常。这里固定推演一次失败，不实际制造服务限流。

| 时刻 | 服务与会话行为 | 用户或宿主看到什么 |
|---|---|---|
| 首次提问 | 模型请求失败，产生 stopReason=error 的助手消息 F0 | 错误信息为 `429 Too Many Requests` |
| 判断可重试 | 会话识别限流，准备第1次重试 | `auto_retry_start`，attempt=1，等待1000ms |
| 等待后 | 删除当前 Agent 末尾的 F0，调用 `agent.continue()` | 不需要重新输入 R0 |
| 再次请求成功 | 模型产生 R1：“预算30元，选了牛肉面” | `auto_retry_end`，success=true |
| 本轮结束 | Agent 循环结束，会话完成相关重试等待 | 本次 `session.prompt()` 继续完成 |

这个场景展示会话级重试。服务商 SDK 或 Provider 内部也可能已做过请求重试；这里讨论的是错误已经表现为 Agent 助手失败消息之后，会话怎样恢复。

### 8.2 先明确配置，再看重试发生什么

此例配置为 `enabled=true`、`maxRetries=3`、`baseDelayMs=1000`，核心创建与事件代码在第二部分第7节给出。

| 连续失败后的额外尝试 | 等待时间 |
|---|---:|
| 第1次重试 | 1000ms |
| 第2次重试 | 2000ms |
| 第3次重试 | 4000ms |

`maxRetries=3` 指最多3次额外重试；若中间一直失败，就是首次请求加最多3次继续请求。本例第1次重试就成功，不会再等待2秒和4秒。重试计数在出现成功的助手响应时重置，不是把整个长会话的失败次数一直相加。

并非所有错误都在这里重试。当前实现先要求助手消息 `stopReason="error"` 且有错误文字，再排除上下文溢出，之后匹配限流、过载、部分服务错误和网络错误等。上下文溢出由上一场景的压缩恢复路径处理，不能只靠相同长上下文不断再发。

### 8.3 失败消息在历史中和 Agent 中有什么不同

F0 的相关字段如下，省略模型和用量等字段：

```json
{
  "role": "assistant",
  "content": [],
  "stopReason": "error",
  "errorMessage": "429 Too Many Requests"
}
```

它也会产生 `message_end`，因此 Session 已将它追加到历史；重试时则将它从活动消息末尾移除：

```text
失败刚到：
  Manager 当前路径 = H → R0 → F0
  Agent messages   = [H中的消息..., R0, F0]

准备重试：
  Manager 当前路径 = H → R0 → F0（保留失败记录）
  Agent messages   = [H中的消息..., R0]（移除末尾失败助手消息）

继续成功后：
  Manager 当前路径 = H → R0 → F0 → R1
  Agent messages   = [H中的消息..., R0, R1]
```

因此，不能要求 Manager 和当前 Agent 的消息永远逐条相等。失败历史可供排查，但不需要作为这次继续生成的最后一条助手消息。

`agent.continue()` 使用已有 R0 和此前历史继续，没有第二次 `prompt(R0)`，所以不会重复追加用户问题。本例菜单早已查询完成，再试的是这次问答，不是从头重跑所有选餐步骤。

### 8.4 和直接 Agent 的区别，以及几个结束信号

| 直接 Agent | AgentSession |
|---|---|
| 可收到 F0 及本次 agent_end；有 `continue()` 可供宿主调用 | 内部识别可重试错误并决定是否继续 |
| 应用自己安排等待、次数上限、失败消息移除与状态通知 | 会话提供退避、计数、auto_retry 事件和取消等待 |
| 宿主若只等最初的 Agent run，会看到这次失败运行已结束 | `session.prompt()` 还会通过 `waitForRetry()` 等待已识别的会话级重试 |

失败运行的 `agent_end` 不代表不会继续重试；`auto_retry_end(success=true)` 表示出现了非 error 的助手响应，本例恰好是最后答案，但其他任务中它还可能提出工具调用。宿主要区分“恢复出一次响应”和“整个任务最终结束”。

若达到上限仍失败，会话发 `auto_retry_end(success=false)` 并结束相关等待；也可用 `abortRetry()` 取消重试等待。最终失败应结合消息和事件判断，不能仅因 `await session.prompt()` 返回就当作已有成功回答。

# 第二部分：按七项能力对照核心代码

## ⭐️核心源码索引

下面行号以增加注释后的源码为准；AgentSession 核心入口优先定位到 `⭐️` 注释。按主线选择方法后可直接跳转；`prompt()` 的12步表也分别链接到对应注释。

| 阅读主线 | 核心入口 | 继续追踪的关键位置 |
|---|---|---|
| 创建与装配 | [createAgentSession](../pi-master/packages/coding-agent/src/core/sdk.ts#L176) → [constructor](../pi-master/packages/coding-agent/src/core/agent-session.ts#L313) | [内部事件入口](../pi-master/packages/coding-agent/src/core/agent-session.ts#L459) |
| 1. 输入与命令 | [prompt](../pi-master/packages/coding-agent/src/core/agent-session.ts#L968) | [扩展命令](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1140) → [Skill 展开](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1174) |
| 2. 运行中调整 | [steer](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1209) | [_queueSteer](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1247) |
| 3. 排队追问 | [followUp](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1230) | [_queueFollowUp](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1265) |
| 4. 事件与保存 | [_handleAgentEvent](../pi-master/packages/coding-agent/src/core/agent-session.ts#L459) → [_processAgentEvent](../pi-master/packages/coding-agent/src/core/agent-session.ts#L508) | [Session 的 appendMessage 调用](../pi-master/packages/coding-agent/src/core/agent-session.ts#L555) → [appendMessage](../pi-master/packages/coding-agent/src/core/session-manager.ts#L860) |
| 5. 历史导航 | [navigateTree](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2747) | [Manager.branch 调用](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2900) → [重建并同步 Agent 消息](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2910) |
| 5. 历史底层 | [branch](../pi-master/packages/coding-agent/src/core/session-manager.ts#L1163) / [buildSessionContext](../pi-master/packages/coding-agent/src/core/session-manager.ts#L1085) | [SessionManager.open](../pi-master/packages/coding-agent/src/core/session-manager.ts#L1325) |
| 6. 上下文压缩 | [compact](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1657) / [_checkCompaction](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1816) | [appendCompaction](../pi-master/packages/coding-agent/src/core/session-manager.ts#L905) → [buildSessionContext](../pi-master/packages/coding-agent/src/core/session-manager.ts#L1085) |
| ⭐️ 压缩后继续运行 | [溢出恢复时 continue](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2048) / [有排队消息时 continue](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2054) | [Agent.continue](../pi-master/packages/agent/src/agent.ts#L346) → [runContinuation](../pi-master/packages/agent/src/agent.ts#L412) → [runAgentLoopContinue](../pi-master/packages/agent/src/agent-loop.ts#L164) |
| 7. 自动重试 | [_isRetryableError](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2476) → [_handleRetryableError](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2495) | [预先建立重试等待](../pi-master/packages/coding-agent/src/core/agent-session.ts#L477) → [waitForRetry](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2587) |
| 停止与显示订阅 | [abort](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1419) / [subscribe](../pi-master/packages/coding-agent/src/core/agent-session.ts#L705) | 事件通知与取消运行的宿主入口 |
| 新建与替换会话 | [newSession](../pi-master/packages/coding-agent/src/core/agent-session-runtime.ts#L186) / [switchSession](../pi-master/packages/coding-agent/src/core/agent-session-runtime.ts#L161) / [fork](../pi-master/packages/coding-agent/src/core/agent-session-runtime.ts#L220) | 当前版本位于 AgentSessionRuntime |
| 对照原来的 Agent | [Agent.prompt](../pi-master/packages/agent/src/agent.ts#L335) | [runPromptMessages](../pi-master/packages/agent/src/agent.ts#L396) → [processEvents](../pi-master/packages/agent/src/agent.ts#L520) |

导航公开入口是 `session.navigateTree()`；`branch` 是其内部调用的 `this.sessionManager.branch()`，分别按源码索引。


**阅读标记：下文加粗的是 AgentSession 这一层新增或接好的处理职责；Agent 原有的循环、执行队列和基本事件能力保持普通文字。**

下面按“调用时机 → 具体代码 → 变量变化 → 可观察结果”展开。源码片段与宿主调用分开阅读，不直接拼成完整脚本。A、B 是两次独立演示，选择其中一种；低层工具与 SDK 工具使用相同菜单数据。模型、认证和项目资源仍按第 13 讲准备。

为便于按 L0～L6 观察，前五个场景假定没有额外扩展消息，关闭自动重试与自动压缩。第六个场景显式调用 `compact()`；关闭自动检查不影响手动压缩。第七个场景另开一次配置了 retry 的演示，观察暂时失败后的恢复。宿主显示和结束监听应在启动 `prompt()` 前注册；按章节讲解不代表把监听注册放到运行之后。

## 1. prompt：同一套执行循环，入口处理不同

### 1.0 先把例子的工具和操作时机准备好

下面给出本例工具。为确保能演示“查询过程中修改要求”，工具先等待宿主放行；这只是课堂控制时机的办法。

```ts
import { Type } from "typebox";
import { defineTool } from "@mariozechner/pi-coding-agent";

const menu = [
    { name: "蛋炒饭", price: 10 },
    { name: "鸡腿饭", price: 20 },
    { name: "牛肉面", price: 30 },
];

let markMenuStarted!: () => void;
let releaseMenu!: () => void;
const menuStarted = new Promise<void>((resolve) => { markMenuStarted = resolve; });
const menuMayReturn = new Promise<void>((resolve) => { releaseMenu = resolve; });

const listMealsTool = {
    name: "list_meals",
    label: "查菜单",
    description: "查询午饭名称和价格。",
    parameters: Type.Object({}),
    async execute() {
        markMenuStarted();
        await menuMayReturn;
        return {
            content: [{ type: "text" as const, text: JSON.stringify(menu) }],
            details: { menu },
        };
    },
};
const listMeals = defineTool({ ...listMealsTool });
```

**对应例子：** 模型调用 `list_meals` 后，工具已经进入 `execute()`，`menuStarted` 完成；但它停在 `await menuMayReturn`，还没有返回价格。宿主此时执行第 2、3 节的补充调用，然后调用 `releaseMenu()`，工具才返回三份菜单。A 用 `listMealsTool`，B 用 `listMeals`，工具业务结果相同。

这两个 Promise 只控制这一次查询。独立演示另一种方式时，从头创建它们。此例按第一部分的轨迹假定模型确实先调用菜单工具。

### 1.1 直接 Agent 与会话入口

调用对照，模型、认证已准备好，工具使用上面的定义。`resourceLoader` 按第 13 讲加载后，应已发现第一部分给出的 `choose-lunch` Skill；传入已创建的加载器前由宿主等待其 `reload()` 完成：

```ts
// 方式 A：应用先手工展开 Skill；下面是完整的 user 消息正文。
const expandedLunchText = `<skill name="choose-lunch" location="/course/lunch/.pi/skills/choose-lunch/SKILL.md">
References are relative to /course/lunch/.pi/skills/choose-lunch.

先调用 list_meals 查询菜单。
在用户当前预算以内，选择价格最高的一份。
用户修改预算后，按最新预算选择。
</skill>

帮我选一份20元以内最贵的午饭，先查菜单。`;

const agent = new Agent({
    initialState: { model, systemPrompt: "先查菜单，再按预算选最贵的一份。", tools: [listMealsTool] },
});
// 若要显示事件，在本行 prompt 前注册第 4 节的监听。
const agentRunning = agent.prompt(expandedLunchText);

// 方式 B：SDK 准备或复用依赖，创建内部 Agent 和 AgentSession。
const manager = SessionManager.create(process.cwd());
const { session } = await createAgentSession({
    sessionManager: manager,
    resourceLoader,
    customTools: [listMeals],
    tools: ["list_meals"],
    settingsManager: SettingsManager.inMemory({
        retry: { enabled: false },
        compaction: { enabled: false },
    }),
});
await session.bindExtensions({});
// 若要显示事件，在本行 prompt 前注册第 4 节的监听。
const sessionRunning = session.prompt(
    "/skill:choose-lunch 帮我选一份20元以内最贵的午饭，先查菜单。",
);
```

**对应例子：** 两种写法是独立对照，实际演示选一种。A 由应用手工准备完整 Skill 块，**B 由 Session 根据 `/skill:` 自动生成相同业务正文**。两者之后都开始查菜单，**B 还接好了会话依赖与内部历史监听**。

具体执行到本例工具等待时：

| 检查点 | A：直接 Agent | B：AgentSession |
|---|---|---|
| 发送之前 | `agent.state.messages = []` | `session.agent.state.messages = []` |
| 发送文字 | 参数是完整 `expandedLunchText` | 参数是 `/skill:choose-lunch ...`，Session 读取正文展开 |
| 模型决定查菜单 | 已有 L0 用户要求、L1 工具调用 | 内部 Agent 也已有 L0、L1 |
| 工具停住 | `agentRunning` 尚未完成，L2 尚未返回 | `sessionRunning` 尚未完成，L2 尚未返回 |
| 会话历史 | 未接保存监听时没有自动文件记录 | Manager 经内部事件处理追加 L0、L1 |

如果此时直接放行菜单、不做后面补充，两者都可以回答“鸡腿饭，20元”。本讲暂不放行，继续演示 15 元预算与 follow-up。

这里先保留运行 Promise，方便在任务仍运行时发送下面的 steering 和 follow-up。若先等待整个任务结束，再追加预算，就成了普通下一次提问。

### 1.2 先看原来的 Agent.prompt：本层只有三个主要动作

入口：[Agent.prompt](../pi-master/packages/agent/src/agent.ts#L335)。下面保留运行冲突检查，将报错文字缩写：

```ts
async prompt(input: string | AgentMessage | AgentMessage[], images?: ImageContent[]) {
    if (this.activeRun) {
        throw new Error("当前已在运行，请用 steer/followUp 排队，或等待完成");
    }
    const messages = this.normalizePromptInput(input, images);
    await this.runPromptMessages(messages);
}
```

**对应例子：** 应用已经准备好 Skill 全文 `expandedLunchText`，调用 `agent.prompt(expandedLunchText)`：先确认没有竞争运行，把字符串包装成 `[L0]`，再进入生命周期与 Agent Loop。若传来的已经是消息数组，规范化函数直接使用该数组。

```text
输入：expandedLunchText（前面的完整 Skill 块＋20元选餐要求）
规范化结果：[{ role: "user", content: [{ type: "text", text: expandedLunchText }], timestamp: t0 }]
接下来：runPromptMessages → runWithLifecycle → runAgentLoop
```

这里没有调用项目的命令注册表、Skill 加载器、ModelRegistry 认证预检或 SessionManager 历史操作。模型请求中的认证解析、执行错误等仍可能在更深层发生；这里说的是这个 `Agent.prompt()` 入口没有 Session 那一串会话预处理。

### 1.3 详细读 AgentSession.prompt：按源码先后逐步执行

入口：[AgentSession.prompt](../pi-master/packages/coding-agent/src/core/agent-session.ts#L968)。先固定正常输入，后面每一步都回答“本次走哪条分支，接下来发生什么”：

```ts
const sessionRunning = session.prompt(
    "/skill:choose-lunch 帮我选一份20元以内最贵的午饭，先查菜单。",
);
```

**对应例子：** 当前 Agent 空闲、聊天消息为空，Skill 已加载，模型与认证已配置，没有额外扩展改写或待注入消息。这次普通路径最后只向 Agent 交 `[L0]`。下面的“变化例子”各自独立，用来说明分支；不把所有情况都叠到同一次任务里。

先看整体顺序，注意中间存在提前返回：

| 顺序 | 实际检查或处理 | 本次 Skill 选餐请求 |
|---|---|---|
| 1 | [读取 options 的默认值](../pi-master/packages/coding-agent/src/core/agent-session.ts#L970) | 默认允许命令、Skill 与模板展开 |
| 2 | **[是否被扩展 `/命令` 接管](../pi-master/packages/coding-agent/src/core/agent-session.ts#L978)** | 没有注册名为 `skill:choose-lunch` 的扩展命令，继续 |
| 3 | **[input 扩展是否接管或改写](../pi-master/packages/coding-agent/src/core/agent-session.ts#L991)** | 没有处理函数，原输入继续 |
| 4 | **[展开 Skill，再展开文件提示词模板](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1009)** | 得到前面展示的完整 Skill 块与选餐文字 |
| 5 | [Agent 是否正在运行](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1018) | 空闲，继续；运行中则入队或报错，并在此结束本次调用 |
| 6 | **[刷新暂存的外部 Bash 结果](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1035)** | 本次没有，继续 |
| 7 | **[检查模型存在与认证配置](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1039)** | 都满足，继续 |
| 8 | **[根据上一条助手消息检查压缩](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1064)** | 新会话没有上一条，跳过 |
| 9 | [构造本次 user 消息与图片](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1075) | 得到 L0 |
| 10 | **[加入待下次发送的自定义消息](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1087)** | 本次没有 |
| 11 | **[before_agent_start 补消息、确定系统提示词](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1094)** | 本次无补充，使用基础系统提示词 |
| 12 | [反馈预检接受，调用 Agent，等待相关重试](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1130) | 原来的 Agent Loop 执行选餐 |

以下核心摘录按原方法顺序排列；省略长错误文案或无关分支时会注明。

#### 1.3.1 第一项：先确定 options，并不立刻请求模型

```ts
const expandPromptTemplates = options?.expandPromptTemplates ?? true;
const preflightResult = options?.preflightResult;
let messages: AgentMessage[] | undefined;
```

**对应例子：** 调用没有传 options，因此 `expandPromptTemplates = true`，`preflightResult = undefined`，局部 `messages` 还没有创建。这时输入仍是一串 `/skill:choose-lunch ...`。

| 选项 | 影响哪一步 | 本例或变化例子 |
|---|---|---|
| `expandPromptTemplates` | 扩展命令尝试、Skill 展开、文件模板展开 | 默认 true；false 时这三处跳过，input 扩展仍运行 |
| `images` | input 扩展及 user 消息内容 | 本例没有图片 |
| `streamingBehavior` | 运行中的排队方式 | 可选 `"steer"` 或 `"followUp"`；空闲时仍走普通新输入 |
| `source` | input 扩展看到的来源 | 默认 `"interactive"`，即使是 SDK 脚本调用也是这个默认值 |
| `preflightResult` | 通知输入预处理是否被接受 | 供 RPC 等内部宿主使用，不代表模型回答成功 |

#### 1.3.2 第二项：是不是扩展注册的斜杠命令

源码核心，省略一条说明注释：

```ts
if (expandPromptTemplates && text.startsWith("/")) {
    const handled = await this._tryExecuteExtensionCommand(text);
    if (handled) {
        preflightResult?.(true);
        return;
    }
}
```

**对应例子：** `/skill:choose-lunch ...` 以斜杠开头，所以**先询问扩展命令注册表**。假定扩展没有注册 `skill:choose-lunch`，返回 false，继续向下，稍后才进入 Skill 展开。

变化例子：假设扩展注册了 `/meal-help`，其处理函数显示“支持查菜单和按预算选餐”。用户发送 `/meal-help` 时，**handler 执行后这里直接返回，不构造普通 L0，也不自动请求模型**。扩展处理函数若另外发起请求，是其自己的操作。

这个检查发生在忙闲判断之前，所以已注册扩展命令即使在 Agent 运行中也能先被处理。直接 `agent.prompt("/meal-help")` 不查这个注册表，只把它当普通文字。

#### 1.3.3 第三项：input 扩展是否接管或改写原输入

源码核心，省略具体结果分支，结果见下面的表：

```ts
let currentText = text;
let currentImages = options?.images;
if (this._extensionRunner.hasHandlers("input")) {
    const inputResult = await this._extensionRunner.emitInput(
        currentText,
        currentImages,
        options?.source ?? "interactive",
    );
    // handled → 反馈接受后返回；transform → 更新 currentText/currentImages。
}
```

**对应例子：** 本次没有 input handler，`currentText` 仍是 `/skill:choose-lunch ...`，`currentImages` 为 undefined。此时 Skill 文件正文还没拼进输入。

变化例子：扩展支持“午饭老规矩”这个口令，三种返回结果会产生不同路径：

| 扩展返回 | 函数下一步 |
|---|---|
| `{ action: "continue" }` | 继续使用当前输入 |
| `{ action: "transform", text: "/skill:choose-lunch 帮我选一份20元以内最贵的午饭，先查菜单。" }` | 以改写后的文字进入下一步 Skill 展开 |
| `{ action: "handled" }` | 反馈接受后直接返回，不走普通模型调用 |

输入是“午饭老规矩”时，原字符串并不包含技能规则；**handler 返回 transform 后，下一步才将它展开为完整 Skill 正文**。`transform` 与 `handled` 不能混为一谈：前者继续，后者结束这条普通路径。

#### 1.3.4 第四项：先展开 Skill，再展开文件提示词模板

```ts
let expandedText = currentText;
if (expandPromptTemplates) {
    expandedText = this._expandSkillCommand(expandedText);
    expandedText = expandPromptTemplate(expandedText, [...this.promptTemplates]);
}
```

**对应例子：** **`_expandSkillCommand()` 读取 choose-lunch，返回前面逐字展示的 `<skill ...>...</skill>` 与 20 元要求**。之后的模板函数没有匹配到模板调用，保持这份完整文字。

这时的关系是：

```text
text / currentText：/skill:choose-lunch 帮我选一份20元以内最贵的午饭，先查菜单。
expandedText：完整 Skill 块＋选餐要求
messages：仍未创建
```

独立的模板例子：项目 `.pi/prompts/lunch.md` 正文就是“帮我选一份20元以内最贵的午饭，先查菜单。”，发送 `/lunch` 时 Skill 函数先保持原文，模板函数再将它替换为文件正文。Skill 与文件模板是顺序调用的两种文本展开。

设置 `expandPromptTemplates: false` 后，本例的 `/skill:` 不在这里展开；该选项名字虽然只写 templates，当前实现实际同时控制前面的扩展命令尝试和 Skill 展开。

#### 1.3.5 第五项：正在运行吗？在这里决定入队或继续

源码摘录，缩写未指定行为时的错误文案：

```ts
if (this.isStreaming) {
    if (!options?.streamingBehavior) {
        throw new Error("Agent 正在运行，需要指定 steer 或 followUp");
    }
    if (options.streamingBehavior === "followUp") {
        await this._queueFollowUp(expandedText, currentImages);
    } else {
        await this._queueSteer(expandedText, currentImages);
    }
    preflightResult?.(true);
    return;
}
```

**对应例子：** 第一条 Skill 请求到来时 Agent 空闲，跳过此分支，继续预检。`isStreaming` 表示整个 Agent 运行状态，查询工具时也可能为 true，不限于屏幕正在显示 token。

变化例子：午饭助手已经在查菜单，再调用下面任何一种方式：

| 调用 | 结果 |
|---|---|
| `session.prompt("预算改成15元。")` | 未指定行为，抛错，不启动竞争运行 |
| `session.prompt("预算改成15元。", { streamingBehavior: "steer" })` | 交给 steering 队列，反馈接受并返回 |
| `session.prompt("选好后，再只输出菜名和价格。", { streamingBehavior: "followUp" })` | 交给 follow-up 队列，反馈接受并返回 |

**入队成功就结束本次 `prompt()` 调用，不再走后面的模型/认证预检、局部消息构造或 before_agent_start**。队列消息由 `_queueSteer()`、`_queueFollowUp()` 自己包装，已有运行继续消费它。

原来的 `agent.prompt()` 也会拒绝竞争运行，但不提供 `streamingBehavior` 这个文字入口；宿主需要另外调用它已有的 `agent.steer(message)` 或 `agent.followUp(message)`。

#### 1.3.6 第六项：先把暂存的外部 Bash 结果放回历史

```ts
this._flushPendingBashMessages();
```

**对应例子：** 本次没有外部命令结果，什么也不追加。注意这行只有 Agent 空闲且没有提前返回时才执行。

变化例子：上一次 Agent 运行期间，宿主另外执行命令取得“今天菜单已更新”，会话为了避免打乱工具调用配对而暂存这条 `bashExecution` 消息。下一次空闲 prompt 到这里时，**先把它加入 Agent messages 和 Manager，再继续处理本次用户输入**。它属于原有活动历史，不会被误当成这次的 user 消息。

这里不是判断模型要不要调用 `bash` 工具，而是在整理宿主已经取得的外部结果。直接 Agent 没有这份 Session 暂存列表。

#### 1.3.7 第七项：先检查模型存在，再检查认证是否有配置

源码核心，缩写报错并合并认证错误的提示分支：

```ts
if (!this.model) {
    throw new Error("未选择模型");
}
if (!this._modelRegistry.hasConfiguredAuth(this.model)) {
    // 原码进一步区分 OAuth 与 API key 提示。
    throw new Error("当前模型没有可用的认证配置");
}
```

**对应例子：** 已选定模型，**ModelRegistry 发现其 provider 有认证来源**，两项都通过。此时仍未构造 L0，更没有发送菜单查询的模型请求。

| 检查结果 | 本次调用停在哪里 |
|---|---|
| `this.model` 为空 | 提示选择模型，后面不继续 |
| 有模型，但 `hasConfiguredAuth()` 为 false | 根据认证方式提示重新登录或配置 key，后面不继续 |
| 都满足 | 继续检查上一轮上下文 |

`hasConfiguredAuth()` 查的是认证来源是否已配置，不是在这里向服务商发验证请求。真正模型请求时，SDK 安装的流函数仍会解析 key、请求头等，因此后面仍可能发生凭据或网络错误。

直接 Agent 依赖应用传入模型与认证回调，并可能在请求阶段失败；**它的 `prompt()` 入口没有这组 ModelRegistry 的会话预检**。

#### 1.3.8 第八项：用上一条助手消息检查是否先压缩

```ts
const lastAssistant = this._findLastAssistantMessage();
if (lastAssistant) {
    await this._checkCompaction(lastAssistant, false);
}
```

**对应例子：** 新会话没有上一条助手消息，直接跳过。若已连续讨论很多轮，这里可能在构造新 user 消息之前处理压缩。

例如上一轮已有很长的菜单比较，Agent 消息是 `[旧消息若干, 上一条助手回答]`。自动压缩开启且满足相应条件时，**这一步可将它重建为 `[摘要C, 保留的近期原文]`**；后面才构造并交给 Agent 本次新要求。最终模型使用的是压缩后的旧历史加新输入。

参数 false 表示不因为上一条响应是 aborted 就直接跳过检查；用户中止过上一次输出，下一次发送时仍有机会处理上下文。本讲前五个演示已关闭自动压缩，所以仍会到达检查点，但 `_checkCompaction()` 读到 enabled=false 后返回。不是每次 prompt 都会生成摘要。

#### 1.3.9 第九项：通过前面检查后，才构造本次 user 消息

```ts
messages = [];
const userContent: (TextContent | ImageContent)[] = [{ type: "text", text: expandedText }];
if (currentImages) {
    userContent.push(...currentImages);
}
messages.push({
    role: "user",
    content: userContent,
    timestamp: Date.now(),
});
```

**对应例子：** `expandedText` 是完整 Skill 块与 20 元要求，所以得到 `[L0]`。若附有菜单照片，content 会是“第一块文字＋后面的图片块”，仍是一条 user 消息。

```text
messages = [L0]
L0.role = user
L0.content[0].text = 完整 Skill 块＋20元选餐要求
agent.state.messages = 此刻的旧活动历史（本次为 []）
agent.state.systemPrompt = 单独保存的系统提示词
```

局部 `messages` 只装本次新输入，不把旧历史读一遍再复制进来。首次是 `[L0]`，后续普通追问也只构造那次的新消息；旧历史由 Agent 在启动运行时取快照。

#### 1.3.10 第十项：有没有等下次输入一起发送的自定义消息

```ts
for (const msg of this._pendingNextTurnMessages) {
    messages.push(msg);
}
this._pendingNextTurnMessages = [];
```

**对应例子：** 普通基线没有 pending 消息，仍是 `[L0]`。变化例子中，宿主在本次 prompt 之前先执行：

```ts
await session.sendCustomMessage(
    { customType: "menu-note", content: "本次菜单价格的单位是人民币元。", display: false },
    { deliverAs: "nextTurn" },
);
```

**对应例子：** **这次调用只把说明暂存，不自行启动选餐**。**到 prompt 的这个位置才将它追加**，令 `messages = [L0, N1]`，其中 N1 是 role=custom 的说明。**列表随后清空，避免每次输入都重复带上它**。

按实际 push 顺序，是 user 消息在前、pending 自定义消息在后；不要根据源码中概述性注释误读成“自定义消息总在用户之前”。SDK 的消息转换还会将这种 custom 消息转换为模型可读消息。

#### 1.3.11 第十一项：开始前扩展可以补上下文，并确定本次系统提示词

源码核心，省略返回消息包装为 role=custom 的循环：

```ts
const result = await this._extensionRunner.emitBeforeAgentStart(
    expandedText,
    currentImages,
    this._baseSystemPrompt,
    this._baseSystemPromptOptions,
);
// 若 result.messages 存在，依次包装为 custom 消息并 push 进 messages。
if (result?.systemPrompt) {
    this.agent.state.systemPrompt = result.systemPrompt;
} else {
    this.agent.state.systemPrompt = this._baseSystemPrompt;
}
```

**对应例子：** 普通 Skill 选餐没有扩展补充，messages 仍是 `[L0]`，系统提示词恢复为基础版本。变化例子：**扩展在启动前补充“今日只提供堂食”，并临时将系统要求增加“本轮只描述堂食方案”**。

如果上一项还有单位说明，本次交接状态就是：

```text
messages = [
  L0：Skill＋用户选餐要求,
  N1：价格单位为人民币元,
  E1：今日只提供堂食
]
agent.state.systemPrompt = 基础系统提示词＋本轮堂食要求
```

扩展的单个 handler 可以返回一条 message，Runner 汇总后由这里的 `result.messages` 逐条追加。系统提示词不是又 push 一条普通 user 消息，而是更新单独的 `systemPrompt` 字段。

这也解释了它和 input 扩展的区别：**input 看到展开前输入，可以改写或接管；before_agent_start 看到展开后文字，在新运行开始前补上下文或调整系统提示词**。若这轮没有返回新系统提示词，就**恢复基础版本，避免上一轮的临时要求不断累积**。

#### 1.3.12 第十二项：反馈、交给 Agent，再等待相关重试

源码结尾：

```ts
if (!messages) {
    return;
}
preflightResult?.(true);
await this.agent.prompt(messages);
await this.waitForRetry();
```

**对应例子：** 正常 Skill 请求走到这里时，messages 已经是 `[L0]`，没有触发前面的提前返回。现在才调用内部 Agent，随后按原来的循环查菜单、处理预算补充、回答。

原方法将前面的输入准备包在 try/catch 中：准备阶段抛错时调用 `preflightResult?.(false)` 后继续抛错。扩展接管、入队接受、准备完成等路径则反馈 true。内部 `agent.prompt()` 与 `waitForRetry()` 在这个准备阶段 try/catch 之后。

| 具体情况 | 可以确认什么 |
|---|---|
| 没模型或运行中缺 streamingBehavior，预处理报错 | 这次输入没有沿正常路径交给 Agent |
| 扩展命令接管后返回 | 命令已被处理，不意味着发生普通模型回答 |
| 运行中入队后返回 | 输入已入队，不意味着已有新回答 |
| `preflightResult(true)` | 会话入口接受了相应操作，不代表模型请求成功 |
| 空闲路径等待内部 Agent 完成 | 当前运行已返回；若识别出相关自动重试，还会继续等待 |

`waitForRetry()` 没有进行中的重试时直接返回。前六个场景的基线关闭自动重试，所以是直接返回；第七个场景开启后，**某些临时错误由会话层协调重试，它避免调用方在相关重试仍进行时就认为本次调用已结束**。

**历史保存来自前面接好的事件监听**，不是这段方法最后统一写文件；这里也没有通用的 `await this._agentEventQueue`。需要刚完成的历史时，宿主仍应等待所需的历史处理阶段。

#### 1.3.13 把两种 prompt 的区别落实到执行顺序

| 阶段 | AgentSession.prompt | 原来的 Agent.prompt |
|---|---|---|
| 识别扩展命令 | 查注册表，接管后可提前返回 | 不查会话命令注册表 |
| 输入拦截与展开 | input 扩展 → Skill → 文件模板 | 不做这些项目资源处理 |
| 运行中收到新文字 | 可根据 streamingBehavior 入队并返回 | prompt 拒绝竞争运行；宿主另用 steer/followUp |
| 整理会话附加状态 | 刷新 Bash 结果、检查模型认证、检查压缩 | 此入口没有对应的会话流程 |
| 准备新消息 | user＋nextTurn＋开始前扩展补充，确定系统提示词 | 规范化宿主已提供的输入 |
| 真正执行 | 委托内部 `agent.prompt(messages)` | 进入 runPromptMessages 与原来的 Loop |
| 相关收尾 | 等待被识别的会话级重试；事件路径另行保存 | 等待本次 Agent 运行及其等待的监听调用 |

因此，对同一个 Skill 请求，A 的宿主需要先准备完整正文与需要的配套流程；B 从原始 `/skill:` 文字开始，把这些步骤安排到会话入口里，最后仍交给原来的 Agent 执行。

### 1.4 对照源码：上面的 Skill 块是哪几行生成的

入口：[_expandSkillCommand](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1174)。已解析出 `skill` 和 `args` 后，核心源码如下：

```ts
const content = readFileSync(skill.filePath, "utf-8");
const body = stripFrontmatter(content).trim();
const skillBlock = `<skill name="${skill.name}" location="${skill.filePath}">\nReferences are relative to ${skill.baseDir}.\n\n${body}\n</skill>`;
return args ? `${skillBlock}\n\n${args}` : skillBlock;
```

**对应例子：** `content` 是带 YAML 头的完整 SKILL.md；`body` 只剩三条选餐规则；`skillBlock` 是第一部分的 `<skill ...>...</skill>`；`args` 是“帮我选一份20元以内最贵的午饭，先查菜单。”。返回值正好是我们逐字展示的 `expandedLunchText`。

如果 Skill 没找到，当前实现保留原输入；读取文件失败也会报告扩展错误并保留输入。本例已加载并可读，所以走成功展开路径。`expandPromptTemplates: false` 会跳过这里，因此不能一边关闭展开，一边期待出现这个 Skill 块。

## 2. steer：相同的执行队列，Session 补上文字与待发送状态

### 2.1 调用对照

在查菜单尚未结束时，分别使用两种入口：

```ts
// 确认工具已经开始，但尚未放行返回。
await menuStarted;

// 方式 A：应用自己构造标准消息。
agent.steer({
    role: "user",
    content: [{ type: "text", text: "预算改成15元。" }],
    timestamp: Date.now(),
});

// 方式 B：会话负责包装。
await session.steer("预算改成15元。");
```

**对应例子：** 两种方式都将新预算送进 steering 队列。原有 Agent Loop 在本例的工具处理结束后取出消息，下一次模型响应都可以改选蛋炒饭。

按上面的代码逐行执行：

1. `await menuStarted` 返回，说明 `execute()` 已开始，并停在等待放行处。
2. A 手工创建 `{ role: "user", content: [...], timestamp: t1 }`；B 收到字符串后创建相同用途的消息。
3. 调用返回时，新预算仍在队列中。Agent 当前已完成消息仍是 L0、L1，工具结果 L2 还没出现。
4. 稍后 `releaseMenu()` 放行，菜单成为 L2；循环取出预算消息，形成 L3。
5. 下一次模型请求看到 L0、L1、L2、L3，预算以新的 15 元为准，选出 10 元蛋炒饭。

因此，“已经入队”和“已经影响下一次模型回答”是两个不同的时刻。

### 2.2 两层实现对照

入口：[Agent.steer](../pi-master/packages/agent/src/agent.ts#L270) 与 [AgentSession._queueSteer](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1247)。以下省略图片分支，并把文本内容数组内联以突出步骤：

```ts
// Agent：负责真正要交给循环的队列。
steer(message: AgentMessage): void {
    this.steeringQueue.enqueue(message);
}

// AgentSession：先维护会话显示状态，再委托给 Agent。
private async _queueSteer(text: string): Promise<void> {
    this._steeringMessages.push(text);
    this._emitQueueUpdate();
    this.agent.steer({
        role: "user",
        content: [{ type: "text", text }],
        timestamp: Date.now(),
    });
}
```

**对应例子：** A 的核心动作是把预算消息入队。**B 还把文字放到 `_steeringMessages`，通知宿主可以显示“预算改成15元，待发送”**；消息真正送达后，**内部事件处理移除这段待发送文字**。

本例中 B 的变化可以按时间观察：

```text
入队前：Session 待调整列表 = []
push 后：Session 待调整列表 = ["预算改成15元。"]
通知：queue_update { steering: ["预算改成15元。"], followUp: [] }
Agent 队列：收到一条 role=user、正文为“预算改成15元”的消息
```

当 L3 的 user `message_start` 后续到达，**Session 将文字从列表移除并再次通知**；L3 的 `message_end` 再触发保存。A 的 `steer()` 只有真正执行队列的入队动作，没有自动提供这份文字显示列表。

**公开 `session.steer()` 还会检查扩展命令、展开 Skill 和模板**，再进入 `_queueSteer()`。真正决定“什么时候改预算”的仍是 [Agent Loop](../pi-master/packages/agent/src/agent-loop.ts)，不是这个会话列表。`await session.steer()` 只确认入队，不表示已经给出新方案。

## 3. followUp：相同的排队时机，Session 管理下一条文字输入

### 3.1 调用对照

同样在选餐尚未结束时调用：

```ts
// 方式 A：应用自己构造标准消息。
agent.followUp({
    role: "user",
    content: [{ type: "text", text: "选好后，再只输出菜名和价格。" }],
    timestamp: Date.now(),
});

// 方式 B：会话负责包装。
await session.followUp("选好后，再只输出菜名和价格。");
console.log(session.getSteeringMessages());
console.log(session.getFollowUpMessages());

// 选用 A 或 B 的两种补充都已入队后，才让工具返回。
releaseMenu();
// A：await agentRunning；B：await sessionRunning。
```

**对应例子：** 两种方式都会先完成当前选餐，再在循环准备结束时送达格式要求，最后输出“蛋炒饭，10元”。观察最终文字，同样可以没有区别。

这里接着第 2 节执行，不另起一次 prompt。B 在放行菜单之前，两个 `console.log` 的示意输出是：

```text
["预算改成15元。"]
["选好后，再只输出菜名和价格。"]
```

此刻 L3、L5 都尚未送达。放行后，循环先查完菜单、接收 L3、给出 L4 蛋炒饭方案；然后发现没有后续工具和 steering，才将格式要求作为 L5 送达，产生 L6“蛋炒饭，10元”。

若把这条格式要求也放进 `steer()`，它会在 steering 检查点进入当前任务。本节专门放入 `followUp()`，用来观察“当前任务准备结束后再处理”的位置。

### 3.2 两层实现对照

入口：[Agent.followUp](../pi-master/packages/agent/src/agent.ts#L275) 与 [AgentSession._queueFollowUp](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1265)。与上一节一样，省略图片分支、内联内容数组：

```ts
// Agent：提供 follow-up 执行队列。
followUp(message: AgentMessage): void {
    this.followUpQueue.enqueue(message);
}

// AgentSession：维护会话的待发送文字，交给内部 Agent。
private async _queueFollowUp(text: string): Promise<void> {
    this._followUpMessages.push(text);
    this._emitQueueUpdate();
    this.agent.followUp({
        role: "user",
        content: [{ type: "text", text }],
        timestamp: Date.now(),
    });
}
```

**对应例子：** **B 可以通过 Session 的待发送列表与 `queue_update` 通知显示这条格式要求**。A 也能做同样界面，但列表、通知及送达后的清理需要应用自己接。

对应 `_queueFollowUp(text)` 的三步是：

| 步骤 | 本例变化 |
|---|---|
| `_followUpMessages.push(text)` | 显示列表加入“选好后，再只输出菜名和价格。” |
| `_emitQueueUpdate()` | 宿主可看到待调整预算与待追问格式这两个列表 |
| `this.agent.followUp(...)` | 把格式要求的 user 消息放入真正的 follow-up 队列 |

L3 送达后，steering 列表先清空，而 follow-up 列表仍保留格式要求。等 L4 已完成、L5 真正送达时，后一个列表才清空。两个列表的清空时间也直接反映两类消息的送达差别。

**公开 `session.followUp()` 同样先做命令检查与文本展开**；Agent Loop 原本就区分 steering 与 follow-up 的消费位置。Session 使用这些已有机制。

直接调用 `session.steer()`、`session.followUp()` 不经过 `prompt()` 的 input 扩展阶段。若用 `session.prompt(text, { streamingBehavior: "steer" })` 或 `"followUp"` 入队，则会先经过该阶段。

## 4. 事件处理：Agent 更新运行状态，Session 协调通知与保存

### 4.1 两种方式都能显示消息

宿主订阅对照：

```ts
// 方式 A：直接监听 Agent。
agent.subscribe((event) => {
    if (event.type === "message_end") {
        console.log(event.message.role, event.message.content);
    }
});

// 方式 B：监听 Session 转发的通知和会话队列变化。
session.subscribe((event) => {
    if (event.type === "queue_update") {
        console.log("待调整：", event.steering);
        console.log("待追问：", event.followUp);
    }
    if (event.type === "message_end") {
        console.log(event.message.role, event.message.content);
    }
});
```

**对应例子：** 运行前注册后，两种方式都能打印 L2 菜单和 L6 回答。换成 `message_update` 也都能观察流式输出。因此，仅展示订阅并打印，并不能说明 Session 的新增职责。

运行时 B 可以打印下面这些信息。这里把 content 数组写成可读文字，L0 中已逐字展示的 Skill 正文用【完整Skill块】缩写，省略流式增量和中间工具事件；这是教学顺序示意。`queue_update` 是同步通知，普通消息通知经过 Session 队列，两类日志在实际运行中可能交错：

```text
user        【完整Skill块】+ 帮我选一份20元以内最贵的午饭，先查菜单。
assistant   ToolCall(list_meals)
待调整： ["预算改成15元。"]
待追问： []
待调整： ["预算改成15元。"]
待追问： ["选好后，再只输出菜名和价格。"]
toolResult  蛋炒饭10元、鸡腿饭20元、牛肉面30元
待调整： []
待追问： ["选好后，再只输出菜名和价格。"]
user        预算改成15元。
assistant   推荐蛋炒饭，因为它符合15元预算。
待调整： []
待追问： []
user        选好后，再只输出菜名和价格。
assistant   蛋炒饭，10元。
```

A 的订阅能收到相同业务消息的事件，但没有 Session 添加的 `queue_update`。如果 A 也要打印“待调整、待追问”，需要宿主自行建立和更新列表。

### 4.2 原来的 Agent 已先更新消息

入口：[Agent.processEvents](../pi-master/packages/agent/src/agent.ts#L520)。源码核心：

```ts
case "message_end":
    this._state.streamingMessage = undefined;
    this._state.messages.push(event.message);
    break;
```

**对应例子：** L2 完成时，Agent 将它追加到 `state.messages`，然后通知监听者。A、B 都有这一步，后续模型请求才能继续使用菜单。这里更新的是运行消息，不是持久化历史树。

以完整菜单结果为断点，状态先后是：

```text
进入 case 前：state.messages = [L0, L1]
event.message = L2（role=toolResult，正文是三份菜单）
push 后：     state.messages = [L0, L1, L2]
```

此时价格已经进入 Agent 保存的消息。B 的 Manager 是否已经追加 L2，还取决于 Session 的事件处理是否走到它。不能因为模型能使用菜单，就推断磁盘历史已经完成写入。

### 4.3 Session 构造时，自动接上内部历史处理

入口：[constructor](../pi-master/packages/coding-agent/src/core/agent-session.ts#L313) / [_handleAgentEvent](../pi-master/packages/coding-agent/src/core/agent-session.ts#L459)。核心摘录，省略其他构造步骤、重试协调与队列错误处理：

```ts
// 构造时注册内部监听。
this._unsubscribeAgent = this.agent.subscribe(this._handleAgentEvent);

// _handleAgentEvent 中将实际工作接在事件处理链后面。
this._agentEventQueue = this._agentEventQueue.then(
    () => this._processAgentEvent(event),
    () => this._processAgentEvent(event),
);
```

**对应例子：** **B 即便没有宿主打印回调，也已接上菜单消息的内部保存路径**。后到事件排在前一事件之后处理。A 如果没有另外编写监听保存逻辑，就只有运行消息数组。

例如 L1 的扩展通知还在等待，L2 的 `message_end` 已经到来：

```text
Agent messages：已经包含 L2
Session 队列：  处理 L1 → 处理 L2 → 处理后续事件
Manager：       可能暂时还没有 L2
```

#### 4.3.1 为什么 then 里面写了两个相同的回调

`Promise.then()` 可以接收两个参数：**第一个是前一个 Promise 成功时执行的回调，第二个是前一个 Promise 失败时执行的回调。一次只会选择其中一个。**

这里可以把原代码这样读，下面仅增加解释性注释：

```ts
this._agentEventQueue = this._agentEventQueue.then(
    // 前一个事件处理成功：接着处理当前 event。
    () => this._processAgentEvent(event),
    // 前一个事件处理失败：也继续处理当前 event。
    () => this._processAgentEvent(event),
);
```

**对应例子：** 当前 event 是 L2 的菜单结果，右侧旧的 `_agentEventQueue` 表示此前已经排入的事件处理。等这条旧 Promise 成功或失败，才执行对应回调处理 L2；`.then()` 返回的新 Promise 再赋回队列，供 L3 等后续事件接在后面。

| 前一个事件的结果 | 本次选择哪个回调 | 当前菜单事件 L2 处理几次 |
|---|---|---|
| 前一个 Promise fulfilled，处理成功 | 第一个回调 | 一次 |
| 前一个 Promise rejected，处理失败 | 第二个回调 | 一次 |
| 前一个 Promise 仍 pending | 两个都先不执行 | 暂时零次，等前项结束 |

为什么失败后也执行同样的处理？例如 L1 的某个扩展处理抛出了异常，但 L2 的菜单结果已经到来。**Session 希望前一事件失败后，后续事件仍能继续进入会话处理，避免整条队列一直跳过消息。**

```text
L1 处理失败 → L1 对应的队列 Promise rejected
    ↓
L2 所在 then 选择第二个回调 → 处理 L2 一次
    ↓ 若 L2 成功
L2 对应的队列 Promise fulfilled
    ↓
L3 所在 then 选择第一个回调 → 处理 L3 一次
```

如果这里只有 `.then(成功回调)`，前项 rejected 后就会跳过当前成功回调，并将 rejected 状态继续传下去；后面若也只接成功回调，后续事件也都不会被处理。

还要分清两个容易误读的地方：

- **第二个回调处理的是前一个 Promise 的失败，不是用来重试第一个回调。** 如果本次第一个回调中的 `_processAgentEvent(L2)` 又抛错，同一个 `.then()` 的第二个回调不会再执行一次 L2；失败会进入这个 `.then()` 返回的新 Promise，后续 L3 再通过自己的失败分支继续。
- 源码后面的 `this._agentEventQueue.catch(() => {})` 用于避免拒绝无人处理。它返回的新 Promise 没有赋回 `_agentEventQueue`，所以并不把队列字段本身改成成功状态；后续事件能继续处理，依赖这里同时提供成功和失败两个入口。

因此，这两个相同回调表达的是：**无论前一事件成功还是失败，轮到当前事件时都尝试处理一次。** 它不自动补做此前失败事件的保存，也不保证当前事件永远成功。

等队列处理到 L2，才执行下一节的通知和保存。**内部订阅在构造时接好，宿主的 console 回调不是保存工作的开关**。

Agent 会等待监听函数返回的 Promise；Session 这个内部监听返回 `void`，把工作安排到自己的链上，所以 Manager 的记录可能短暂落后于 Agent 消息。

### 4.4 Session 收到完整消息后，再通知与保存

入口：[_processAgentEvent](../pi-master/packages/coding-agent/src/core/agent-session.ts#L508)。核心摘录，省略自定义消息与其他事件分支：

```ts
await this._emitExtensionEvent(event);
this._emit(event);

if (event.type === "message_end") {
    if (
        event.message.role === "user" ||
        event.message.role === "assistant" ||
        event.message.role === "toolResult"
    ) {
        this.sessionManager.appendMessage(event.message);
    }
}
```

**对应例子：** L2 已进入 Agent 后，**Session 再依次通知扩展、通知宿主，并把菜单结果写入 Manager**。L0～L6 都分别记录；不只是保存最终菜名。

把 `event` 固定为菜单完成事件，顺着这段代码读：

1. `event.type = "message_end"`，`event.message.role = "toolResult"`，正文是三份菜单。
2. `_emitExtensionEvent(event)` 先让已注册扩展处理它。
3. `_emit(event)` 调用宿主监听，终端打印菜单内容。
4. role 条件命中，执行 `appendMessage(L2)`，菜单成为历史树中的新 Entry。

因此，在第 3 步的宿主回调里读取 Manager，可能还找不到本条菜单；第 4 步才追加。这里也没有等待 L6 最终回答：每一条完整消息分别记录。

如果 A 也要记录同样的历史，应用可以自行编写下面的保存监听：

```ts
// 直接 Agent 场景：应用自行接入 Manager，仅展示标准消息保存。
agent.subscribe((event) => {
    if (
        event.type === "message_end" &&
        (event.message.role === "user" ||
         event.message.role === "assistant" ||
         event.message.role === "toolResult")
    ) {
        manager.appendMessage(event.message);
    }
});
```

**对应例子：** 加上这段以后，A 也能保存菜单和回答。这是应用自己补上了会话层的一部分。**B 内部已有相应处理，宿主不能再重复追加，否则会保存两次**。

若 A 使用一个新建的独立 Manager，事件按本例到来后：

| 完成事件 | 这段监听执行什么 | 已记录的业务消息 |
|---|---|---|
| L0 用户要求 | `manager.appendMessage(L0)` | L0 |
| L1 菜单调用 | `manager.appendMessage(L1)` | L0、L1 |
| L2 菜单结果 | `manager.appendMessage(L2)` | L0、L1、L2 |
| L6 最后回答 | `manager.appendMessage(L6)` | 经过中间追加后，共 L0～L6 |

单独的 `tool_execution_start` 不满足 `message_end` 条件，所以不会被这段代码存成一条消息。这只是标准消息保存示例，尚未补齐 Session 的模板、扩展和待发送列表处理。

**B 的待发送文字清理也在事件处理中**：L3、L5 的 user `message_start` 到达时，从显示列表移除；到 `message_end` 再走保存。宿主收到 `message_end` 通知时，当前这一条的 Manager 追加还在后面。

## 5. 会话处理：应用手工协调，或交给 Session

### 5.1 保存的核心：给消息加上历史位置

入口：[SessionManager.appendMessage](../pi-master/packages/coding-agent/src/core/session-manager.ts#L860)。源码核心：

```ts
const entry: SessionMessageEntry = {
    type: "message",
    id: generateId(this.byId),
    parentId: this.leafId,
    timestamp: new Date().toISOString(),
    message,
};
this._appendEntry(entry);
```

**对应例子：** L2 成为一条有 ID、父节点和时间戳的历史 Entry。**Manager 更新索引和 leaf，启用持久化时写 JSONL**。普通新会话首次写出要等历史中出现 assistant 消息。

假设追加前 `leafId = e1`，新生成 ID 为 `e2`，则本次结果为：

```text
追加前：leafId = e1
新 Entry：{
  type: "message", id: "e2", parentId: "e1",
  message: { role: "toolResult", toolName: "list_meals",
             toolCallId: "call_menu", content: [菜单正文] }
}
追加后：leafId = e2，byId.get("e2") 指向这条 Entry
```

`e2`、`e1` 是教学 ID，实际随机生成；时间戳在这里省略。`toolCallId` 将菜单结果关联到 L1 的工具调用，`parentId` 则将它接到历史树，两个关系各有用途。初始配置 Entry 已在树图中省略。

两种方式都可以使用 Manager；区别在谁连接它。A 由应用编写保存监听，**B 由 Session 内部连接**。消息内容和历史 Entry 是两层数据，Entry ID 也不同于工具调用 ID。

### 5.2 导航的调用对照

以下片段在 Agent 已空闲、相关历史事件已处理完成后执行。先从历史里找到 L2 的真实节点 ID；A 须已接好第 4.4 节的保存监听，B 内部已保存：

```ts
const menuEntry = manager.getBranch().find((entry) =>
    entry.type === "message" &&
    entry.message.role === "toolResult" &&
    entry.message.toolName === "list_meals",
);
if (!menuEntry) throw new Error("本轮没有找到完整菜单结果");
const menuEntryId = menuEntry.id;
```

**对应例子：** Manager 的菜单 Entry 保存着 L2。假设这次生成的 ID 是 `e2`，后续就把实际变量 `menuEntryId` 传给导航方法；不能将教学字符串 `"L2"` 或工具调用 ID `"call_menu"` 当作这个节点 ID。

```ts
// 方式 A：应用接入 Manager 后，手工同步历史位置和 Agent 消息。
manager.branch(menuEntryId);
agent.state.messages = manager.buildSessionContext().messages;
await agent.prompt("预算改成30元，仍选预算内最贵的一份。");

// 方式 B：Session 提供配套操作。
const navigation = await session.navigateTree(menuEntryId, { summarize: false });
if (!navigation.cancelled) {
    await session.prompt("预算改成30元，仍选预算内最贵的一份。");
}
```

**对应例子：** 两者都可恢复 `[L0, L1, L2]`，再选牛肉面。A 需要应用保证“两项修改同时正确”；**B 的 `navigateTree()` 把它们放在一个会话操作中，并处理相应扩展通知等分支**。

按 A、B 任一种方式演示，观察这些状态：

| 操作时刻 | Manager 当前消息路径 | Agent 活动消息 | 模型下一步可用的信息 |
|---|---|---|---|
| 导航前 | L0～L6 | L0～L6 | 菜单、15 元预算、格式要求 |
| 回到 `e2` 后 | L0、L1、L2 | L0、L1、L2 | 原始 20 元要求与菜单 |
| 发送 30 元新要求 | 新分支从 L2 接出 | 原三条加上新 user 消息 | 明确用 30 元覆盖原 20 元要求 |
| 模型回答后 | 新分支继续追加 | 新消息继续增长 | 牛肉面 30 元；旧的 15 元要求不在此分支 |

全部历史中仍有 L3～L6，导航并没有删除它们。模型选择牛肉面，是因为新输入明确修改预算，而不是因为导航本身修改了用户要求。

不能只改 `manager.branch()` 而保留 Agent 的旧消息，否则历史位置回到菜单结果，模型却仍看到后面的 15 元要求。Session 解决的是这类同步问题，并不让 Agent 获得另一种推理能力。

### 5.3 navigateTree 内部为什么要做两步

入口：[navigateTree](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2747)。本例选中工具结果，不生成摘要、不加标签，只提炼对应步骤：

```ts
// 先移动历史当前位置。
this.sessionManager.branch(newLeafId);

// 再重建这个位置的上下文，替换运行消息。
const sessionContext = this.sessionManager.buildSessionContext();
this.agent.state.messages = sessionContext.messages;
```

**对应例子：** `newLeafId` 就是 L2 对应的 Entry ID。旧分支仍保留，Agent 当前只使用菜单结果及之前消息。30 元的新要求接到 L2 后，形成另一条分支。

这三行分别产生以下效果：

```text
branch(e2)                       → Manager.leafId = e2
buildSessionContext()            → sessionContext.messages = [L0, L1, L2]
agent.state.messages = ...       → Agent 同步为 [L0, L1, L2]
```

对照一个只执行第一行的错误用法：Manager 已停在 e2，Agent 却仍含“预算改成15元”的 L3；后续记录会接到 e2 后，而模型输入仍带旧分支内容。**把历史位置和消息替换一起做**，才能正确实现“回到菜单时另选一次”。

这里假定宿主在历史就绪后导航；不能把 `session.prompt()` 返回理解为通用的 Session 事件队列 flush 保证。选中用户节点时还有返回编辑文字等规则，本例使用工具结果节点。

### 5.4 重新打开的调用对照

30 元的新分支记录完成保存后，记下文件路径；下次启动把同一路径作为 `savedFile` 传入。A 可从 `manager.getSessionFile()` 取得，B 可从 `session.sessionFile` 取得。这里假设打印出的路径是项目里的 `.demo-sessions/lunch.jsonl`，实际以运行输出为准。两个片段中的 Agent 模型、认证与工具仍需准备：

```ts
// 方式 A：应用自己打开历史，把重建出的消息交给新 Agent。
const reopened = SessionManager.open(savedFile);
const context = reopened.buildSessionContext();
const agent = new Agent({
    initialState: { model, systemPrompt, tools: [listMealsTool], messages: context.messages },
});
// 若继续记录，还需重新接好前面的保存监听。

// 方式 B：SDK 按已打开的 Manager 恢复并创建会话。
const { session: restored } = await createAgentSession({
    sessionManager: SessionManager.open(savedFile),
    resourceLoader,
    customTools: [listMeals],
    tools: ["list_meals"],
});
await restored.bindExtensions({});
```

**对应例子：** A 也能恢复消息，但这里还没有展示应用如何按历史恢复模型和 thinking 配置、接回保存与扩展；**B 的 SDK 装配流程已包含相应处理**。

假设新分支用户消息叫 B0，助手回答叫 B1，保存后的结构是：

```text
                     ┌→ L3 → L4 → L5 → L6
L0 → L1 → L2 ────────┤
                     └→ B0：30元 → B1：牛肉面30元
```

重新打开后，`reopened.buildSessionContext().messages` 或恢复 Session 中的 Agent 消息应为 `[L0, L1, L2, B0, B1]`。L3～L6 仍在文件中，但不混入当前模型上下文。

恢复之后再发送“刚才选的是哪一份？”，模型可以依据 B1 回答“牛肉面，30元”。打开文件与装回消息本身不发起模型请求，也不执行 `list_meals`；只有后续新任务需要时，模型才可能再次要求查询。

新分支已有记录并写入后，重开会恢复到该分支。恢复菜单结果是恢复历史消息，不是重新查询菜单。只在内存导航、不追加记录就退出，不保证下次仍停在那个位置。

新建、切换、fork 成另一份会话的入口在当前版本的 [AgentSessionRuntime](../pi-master/packages/coding-agent/src/core/agent-session-runtime.ts)；本例集中看同一会话的保存、导航和恢复。

## 6. compact：生成摘要、保存边界、重建活动消息

### 6.1 宿主调用与观察结果

先注册压缩事件观察，再执行手动压缩。此时本例已完成较长讨论，相关历史消息也已保存：

```ts
const unsubscribe = session.subscribe((event) => {
    if (event.type === "compaction_start") {
        console.log("开始压缩：", event.reason);
    }
    if (event.type === "compaction_end") {
        console.log("压缩结果：", event.result?.firstKeptEntryId, event.errorMessage);
    }
});

try {
    const result = await session.compact(
        "保留当前30元预算、菜单价格、选餐规则和已选牛肉面的结论。",
    );
    console.log(result.summary);
    console.log(session.messages.map((message) => message.role));
} finally {
    unsubscribe();
}
```

**对应例子：** 成功时先看到 `compaction_start`，reason 为 `manual`；摘要保存并应用后收到 `compaction_end`，本例边界为 b18。最后的角色数组是 `["compactionSummary", "user", "assistant"]`，分别对应摘要 C 与保留的 B18、B19。它不是简单把所有消息删到只剩一条摘要。

这里前五个场景的 `compaction.enabled = false` 关闭的是自动检查，手动 `session.compact()` 仍会执行。若会话没有可准备的压缩内容，或紧接着上一次压缩还没有新增记录，调用可能失败；不要只给三句很短的对话，就假定一定得到本例边界。

### 6.2 核心代码：先准备，再生成，再落到会话状态

入口：[AgentSession.compact](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1657)。以下为教学简化，省略认证解析、扩展可接管摘要、取消与错误通知等分支；`apiKey`、`headers` 来自当前模型的认证解析：

```ts
// 1. 取得当前分支，计算摘要范围与保留边界。
const pathEntries = this.sessionManager.getBranch();
const settings = this.settingsManager.getCompactionSettings();
const preparation = prepareCompaction(pathEntries, settings);
if (!preparation) throw new Error("没有可准备的压缩内容");

// 2. compact 是导入的压缩函数，内部向模型请求摘要。
const result = await compact(
    preparation, this.model, apiKey, headers,
    customInstructions, this._compactionAbortController.signal, this.thinkingLevel,
);

// 3. 保存摘要及边界，再将 Agent 同步到重建后的上下文。
this.sessionManager.appendCompaction(
    result.summary, result.firstKeptEntryId, result.tokensBefore, result.details, false,
);
const sessionContext = this.sessionManager.buildSessionContext();
this.agent.state.messages = sessionContext.messages;
```

**对应例子：** 第一步取的是 30 元分支，准备结果将 b18 作为保留起点；**第二步生成包含当前预算与菜单的摘要；第三步追加 c0，并把原来的长消息数组替换为 `[C, B18, B19]`**。

| 核心变量 | 本例内容 |
|---|---|
| `pathEntries` | L0、L1、L2 及 B0～B19 对应的当前路径 Entry，另有配置节点 |
| `preparation.messagesToSummarize` | 本教学边界下的较早讨论，假定不在 turn 中间切开 |
| `preparation.firstKeptEntryId` | `b18`，从这里开始保留原文 |
| `result.summary` | 30 元预算、三份菜单、选择规则与牛肉面结论 |
| `sessionContext.messages` | `compactionSummary` 摘要消息 + B18 + B19 |

原方法开始时还会断开内部 Agent 事件监听并调用 `abort()`，在 `finally` 中重新连接；本例选择空闲时操作。模型生成摘要本身也会消耗一次或多次模型请求，并非只做字符串截取。

### 6.3 为什么 appendCompaction 后还要替换 Agent 消息

入口：[appendCompaction](../pi-master/packages/coding-agent/src/core/session-manager.ts#L905) / [buildSessionContext](../pi-master/packages/coding-agent/src/core/session-manager.ts#L1085)。对应核心状态变化：

```text
appendCompaction(...)：
  历史新增 c0，parentId=b19，firstKeptEntryId=b18，leafId=c0

buildSessionContext()：
  找到当前路径上的压缩记录
  → 先构造摘要消息 C
  → 保留 b18、b19 的原文
  → 再加入压缩节点之后的新消息

agent.state.messages = sessionContext.messages：
  当前执行消息替换为 [C, B18, B19]
```

如果只保存 c0，Agent 仍可能保留 L0～B19 的长数组，下次请求依然很长。如果只改 Agent 数组而不存摘要与边界，重启后又无法按这次压缩结果恢复。这个配套关系与 `navigateTree()` 同步历史位置和运行消息的道理相同。

摘要在 [messages.ts：convertToLlm](../pi-master/packages/coding-agent/src/core/messages.ts#L148) 转成模型可读 user 消息。直接 Agent 的默认转换只保留标准角色，应用若自己使用 `compactionSummary` 角色，也要接好相应转换，不能只把这个自定义角色塞进去。

### 6.4 自动压缩与本次手动操作的关系

本例为看清调用时机使用手动 `compact()`。**启用自动压缩后，会话的 `_checkCompaction()` 会结合配置、当前模型与上下文使用量判断是否需要处理**。

接近容量阈值的压缩通常完成后等待下一次输入；上下文溢出后的恢复还可能压缩并继续。二者不能都理解成“压缩后自动重新提问”。更详细的范围选择与摘要算法见[第 08 讲](08_Compaction上下文压缩完整讲义.md)。

### 6.5 ⭐️重点：压缩完以后，谁让 Agent 接着运行

入口：[_runAutoCompaction](../pi-master/packages/coding-agent/src/core/agent-session.ts#L1899)。前面的代码已经保存摘要并替换了 `agent.state.messages`，**这些操作只更新上下文；真正让 Agent 再次请求模型的是下面的 `this.agent.continue()`**。

以下是自动压缩成功后的核心分支，省略移除末尾错误助手消息的检查：

```ts
if (willRetry) {
    setTimeout(() => {
        // ⭐️重点：上下文已经变短，继续回答原来的问题。
        this.agent.continue().catch(() => {});
    }, 100);
} else if (this.agent.hasQueuedMessages()) {
    setTimeout(() => {
        // ⭐️重点：压缩期间有人追加了要求，重新启动循环处理队列。
        this.agent.continue().catch(() => {});
    }, 100);
}
```

**例子一：用户只问一次“刚才选了什么？”，请求因上下文太长失败。** 假设这条问题记为 U，失败助手消息记为 F。Session 先从活动消息中移除 F，压缩较早历史，再把 Agent 消息重建为 `[摘要 C, 近期历史, U]`；此时 `willRetry=true`。调用 `continue()` 后，模型根据这份较短的上下文回答“牛肉面，30元”。**U 已经存在，所以不再调用 `prompt(U)`，也不会多追加一条相同问题。** 这是一次新的模型请求，继续使用当前消息，不是恢复服务端已失败的流式连接。

**例子二：助手已经回答“牛肉面，30元”，阈值压缩期间，用户追加“再只输出菜名”。** 宿主把这句话放进 follow-up 队列。压缩成功后 `willRetry=false`，但队列非空，第二个分支通过 `continue()` 处理这条新要求，模型再输出“牛肉面”。若没有溢出恢复，也没有排队消息，就不调用 `continue()`，等待用户下一次输入。

`setTimeout(..., 100)` 把启动下一轮的动作推迟到后续定时回调，让当前事件处理和运行收尾先有机会完成；它本身不是重试退避策略，也不保证旧运行一定在100ms内结束。`continue()` 仍会检查是否有活动运行。

`.catch(() => {})` 只接住这次 Promise 的拒绝，避免无人处理的异步拒绝，**不会自动再试一次**。正常进入循环后的模型错误会沿消息、`agent_end` 等事件处理；若调用在入口检查时就被拒绝，例如旧运行尚未结束，这个空回调也不会替它补发或报告成功。

### 6.6 continue() 大概怎样实现：已有消息，再跑一轮

先区分职责：**`continue()` 原本就是底层 Agent 的能力；Session 增加的是“何时继续”的策略，以及继续前的压缩、历史同步和错误处理。** 直接 `new Agent()` 的调用方也能调用它，但需要自己准备正确的上下文和调用时机。

入口：[Agent.continue](../pi-master/packages/agent/src/agent.ts#L346)。下面保留核心判断，错误文字简化：

```ts
async continue(): Promise<void> {
    if (this.activeRun) throw new Error("当前仍在运行");

    const last = this._state.messages[this._state.messages.length - 1];
    if (!last) throw new Error("没有可以继续的消息");

    if (last.role === "assistant") {
        const steering = this.steeringQueue.drain();
        if (steering.length > 0) {
            await this.runPromptMessages(steering, { skipInitialSteeringPoll: true });
            return;
        }
        const followUps = this.followUpQueue.drain();
        if (followUps.length > 0) {
            await this.runPromptMessages(followUps);
            return;
        }
        throw new Error("助手已经答完，且没有排队消息");
    }

    await this.runContinuation();
}
```

**对应例子：** 例子一的最后一条是 user 消息 U，直接走 `runContinuation()`。例子二的最后一条是已经完成的 assistant 回答，先检查 steering，再检查 follow-up，取到“再只输出菜名”后走 `runPromptMessages(followUps)`。因此 `continue()` 既能接着未完成的输入运行，也能在已有助手回答时处理排队输入；没有队列时不会凭空让助手再说一句。

`runContinuation()` 内部仍使用正常运行的生命周期：建立本轮运行状态和取消信号，调用循环，最后清理状态。它用 `createContextSnapshot()` 浅复制当前消息与工具数组，再把快照、循环配置和事件回调交给 [runAgentLoopContinue](../pi-master/packages/agent/src/agent-loop.ts#L164)。该函数检查消息非空且末尾不是 assistant 后，核心就是：

```ts
// 不再追加一份 prompts；当前上下文里已经有待处理的 U 或工具结果。
const currentContext: AgentContext = { ...context };
await emit({ type: "agent_start" });
await emit({ type: "turn_start" });
await runLoop(currentContext, newMessages, config, signal, emit, streamFn);
```

**对应例子：** `[C, 近期历史, U]` 直接进入与 `prompt()` 共用的 `runLoop()`，重新请求模型；模型若要求工具，仍会执行工具、追加结果，再继续请求。这里没有再次为原 U 发出输入 `message_start/message_end`，后续新生成的助手消息仍照常发事件，由 Agent 更新状态、Session 保存历史。若通过队列分支带入了新输入，那条新输入仍会正常追加并发出消息事件。

可以顺着这一条链读代码：`Session 决定继续 → Agent.continue() 检查状态与队列 → runContinuation() → runAgentLoopContinue() → 共用 runLoop()`。**压缩与重试策略由 Session 协调，真正执行的仍然是原来的 Agent Loop。** 第七个场景的429重试也复用这个入口，只是继续前做的是退避等待，而非上下文压缩。

## 7. 自动重试：识别临时错误，等待后从当前上下文继续

### 7.1 宿主配置与可观察结果

独立打开已保存的30元分支，启用本例重试配置；资源与工具沿用前文，自动压缩先关闭，避免混淆两条恢复路径：

```ts
const { session: retrySession } = await createAgentSession({
    resourceLoader,
    sessionManager: SessionManager.open(savedFile),
    customTools: [listMeals],
    tools: ["list_meals"],
    settingsManager: SettingsManager.inMemory({
        retry: { enabled: true, maxRetries: 3, baseDelayMs: 1000 },
        compaction: { enabled: false },
    }),
});
await retrySession.bindExtensions({});
const unsubscribe = retrySession.subscribe((event) => {
    if (event.type === "auto_retry_start") {
        console.log("重试：", event.attempt, "等待毫秒：", event.delayMs);
    }
    if (event.type === "auto_retry_end") {
        console.log("恢复响应：", event.success, event.finalError);
    }
    if (event.type === "message_end" && event.message.role === "assistant") {
        console.log(event.message.stopReason, event.message.content);
    }
});
try {
    await retrySession.prompt("刚才预算是多少，选了哪一份？");
} finally {
    unsubscribe();
    await retrySession.abort();
    retrySession.dispose();
}
```

**对应例子：** 用户只发送一次追问。假定服务第一次返回429，宿主先看到错误助手消息，再看到“重试：1，等待毫秒：1000”；恢复成功后看到正常回答与 success=true。这里直接等待 `retrySession.prompt()`，不把首次失败 run 的 agent_end 当作整个恢复流程已结束。

默认设置与此例可不同：当前默认是最多3次重试、基础延迟2000ms。本例改为1000ms，只为使退避计算直观。`maxDelayMs` 限制的是允许的服务端请求等待时长等底层行为，不是此处 `baseDelayMs * 2 ** n` 公式里的显式封顶参数。

### 7.2 触发处：在 agent_end 后检查最后一条助手消息

入口：[_processAgentEvent](../pi-master/packages/coding-agent/src/core/agent-session.ts#L508)。核心摘录，省略取出并清空 `_lastAssistantMessage` 等步骤：

```ts
if (this._isRetryableError(msg)) {
    const didRetry = await this._handleRetryableError(msg);
    if (didRetry) return;
}
this._resolveRetry();
await this._checkCompaction(msg);
```

**对应例子：** msg 是 F0，stopReason=error，错误文字命中429且不是上下文溢出，于是进入 `_handleRetryableError()`。若已开始重试，这次处理返回，不再紧接着启动普通压缩检查。

**分类由 `_isRetryableError()` 完成**，完整匹配条件见源码。上下文溢出会明确返回 false，再进入相应压缩判断；不能把所有错误都归为自动再发一次。

### 7.3 重试核心：计数、退避、移除错误，再调用 continue

入口：[_handleRetryableError](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2495)。以下保留本例成功恢复路径，省略 enabled 检查、次数超限和等待取消分支：

```ts
this._retryAttempt++;
const delayMs = settings.baseDelayMs * 2 ** (this._retryAttempt - 1);
this._emit({
    type: "auto_retry_start",
    attempt: this._retryAttempt,
    maxAttempts: settings.maxRetries,
    delayMs,
    errorMessage: message.errorMessage || "Unknown error",
});

const messages = this.agent.state.messages;
if (messages.length > 0 && messages[messages.length - 1].role === "assistant") {
    this.agent.state.messages = messages.slice(0, -1);
}

this._retryAbortController = new AbortController();
await sleep(delayMs, this._retryAbortController.signal);
// 通过定时调度离开当前会话事件处理链，再启动继续运行。
setTimeout(() => {
    // ⭐️重点：复用已有问题与历史，再次进入 Agent Loop。
    this.agent.continue().catch(() => {});
}, 0);
```

**对应例子：** 第一次 `_retryAttempt=1`，延迟1000ms；**当前末尾的 F0 被移除，但 R0 和菜单历史保留**。等待后 `continue()` 看到最后是 user 消息 R0，继续生成这条追问的答案，没有第二条相同用户输入。

这里与6.5节的溢出恢复共用 `Agent.continue()`；它的状态检查、队列分支和底层循环见6.6节。**会话级重试负责判断错误、等待和整理上下文，`continue()` 负责用整理后的消息重新进入执行。**

**原实现先检查是否启用，计数超过 `maxRetries` 时发最终失败通知并释放等待**；等待本身也能取消。定时调度用来脱离当前事件处理链，不是用同步递归不断调用 `prompt()`。完整错误与取消处理以源码为准。

### 7.4 为什么 prompt 还要等 waitForRetry

入口：[prompt](../pi-master/packages/coding-agent/src/core/agent-session.ts#L968) / [_handleAgentEvent](../pi-master/packages/coding-agent/src/core/agent-session.ts#L459) / [waitForRetry](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2587)。关键衔接为：

```ts
// AgentSession.prompt 的结尾。
await this.agent.prompt(messages);
await this.waitForRetry();

// waitForRetry 的核心：没有重试时直接返回。
if (!this._retryPromise) return;
await this._retryPromise;
await this.agent.waitForIdle();
```

**对应例子：** 最初的 Agent run 因429发出了结束事件，第一行等待可能即将完成。但 **Session 在 `_handleAgentEvent()` 收到该 agent_end 时，已经同步识别错误并创建 `_retryPromise`，之后才排队处理事件**。第二行因此能等到相关重试，不会仅因异步事件队列处理得慢就漏掉这次恢复。

出现非 error 助手消息时，**会话发成功重试通知并重置计数**；后续 agent_end 处理释放对应 Promise。等待期间取消或超过上限也会释放它，调用方再结合消息与 `auto_retry_end` 判断成功或失败。

这一层等待也不等于任意宿主后台任务和整个 Session 事件队列的通用 flush。**它专门解决已经识别出来的会话级重试如何与 prompt 调用衔接**。

上一讲：[13 AgentSession 运行准备](13_AgentSession运行准备完整讲义.md)  
下一讲：[15 多智能体系统原理](15_多智能体系统原理完整讲义.md)
