---
title: "消息与事件源码补充"
description: "openclaw · 源码补充 · 课程讲义"
project: "openclaw"
sourcePath: "OpenClaw/OpenClaw-Course/x.Pi消息系统与事件系统源码解析：数据、通知与异步交接.md"
originalUrl: "/originals/openclaw/messages-events.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# x. Pi 消息系统与事件系统源码解析：数据、通知与异步交接（选读）

**选读材料：有需要的同学可自行阅读，不计入主线讲义编号。**

一条助手回复至少会出现在两个位置：它作为消息进入对话历史，也会随事件交给订阅者。前者决定下一次模型能读到什么，后者让应用知道运行发生了什么变化。**消息是保存和传递的数据，事件是描述消息或运行状态变化的通知；事件可以携带消息，但两者有各自的类型、创建位置和消费方式。**

[第 05 章](/openclaw/chapter-05) 介绍了模型流，[第 06 章](/openclaw/chapter-06) 解释了 Agent Loop，[第 07 章](/openclaw/chapter-07) 追到了工具结果回传。本章把这些过程中的消息和事件连接起来，并继续追到编码会话：一份数据何时进入 Agent 历史，何时转换成模型输入，何时被会话记录，又在何时交给监听函数。

```text
消息用于模型输入：
用户输入 / 工具结果 / 应用消息
  → Agent.state.messages 与循环 context.messages
  → transformContext
  → convertToLlm
  → pi-ai Context.messages
  → 模型调用

模型输出产生消息与通知：
AssistantMessageEventStream
  → streamAssistantResponse 更新循环中的助手消息
  → emit(AgentEvent)
  → Agent.processEvents：更新状态，再调用 Agent listener
      └─ AgentSession._handleAgentEvent：将事件加入会话队列
          → _processAgentEvent
              ├─ await 扩展生命周期通知
              ├─ 通知 session.subscribe 的 listener
              └─ message_end 时追加会话记录
```

图中最后三步适用于 Agent 事件进入会话队列的正常处理路径。会话也有直接追加自定义消息的入口，它的通知顺序不同，第 9 节将单独展开。`context`、`tool_call` 等扩展钩子则由模型或工具处理函数直接等待，不能全部归入上面的生命周期通知路径。

源码摘录保留执行语句，删去注释并调整缩进；省略范围会在正文中说明。例子中的消息、输出文字和时间线用于说明给定条件下的变化，不是运行日志。`U`、`A`、`R` 表示消息对象的简称；只列局部字段时会注明。

| 阅读部分 | 要解决的问题 |
| --- | --- |
| 1—2 | Message 与内容块怎样组成；三份消息数组何时改变 |
| 3—4 | 模型事件怎样变成 AgentEvent；emit、state、subscribe 怎样相连 |
| 5 | 应用消息从哪里产生，怎样经过转换进入模型输入 |
| 6—7 | AgentSession 怎样排队、记录与转发；pi.on 怎样收到生命周期事件 |
| 8—10 | 改写上下文的钩子、自定义消息入口和独立事件总线 |
| 11 | 怎样自己添加消息类型、转换函数和订阅处理 |
| 12—13 | 对照等待与完成边界，并沿 IDE 走完实际调用链 |

源码链接使用相对文件路径；标签中的行号用于 IDE 的“转到行”，链接本身只负责打开文件。本文目录到 Pi 源码根目录的相对位置为 `../../pi-master/`。移动讲义时需保留这一目录关系，或在 Pi 项目中按 `packages/...` 路径打开文件，再转到标出的行号。讲义间链接使用当前文件名；选读讲义按具体名称区分，不依赖旧主线编号。


## 章节索引

| 章节与跳转 |
| --- |
| [1. 从一条消息和一条事件开始](#x-messages-01) |
| [2. 消息从哪里进入历史，事件在什么位置产生](#x-messages-02) |
| [3. 模型事件怎样变成 Agent 的消息事件](#x-messages-03) |
| [4. emit 怎样更新 Agent 状态并调用订阅者](#x-messages-04) |
| [5. 应用消息怎样转换成模型输入](#x-messages-05) |
| [6. AgentSession 怎样接收、排队和转发事件](#x-messages-06) |
| [7. 扩展怎样通过 pi.on 接收生命周期事件](#x-messages-07) |
| [8. 能改变输入和工具结果的事件，由谁直接等待](#x-messages-08) |
| [9. 自定义消息怎样产生、排队与发出通知](#x-messages-09) |
| [10. pi.events：扩展之间的独立事件总线](#x-messages-10) |
| [11. 自己添加消息和订阅处理](#x-messages-11) |
| [12. 用短时间线核对消息、通知与完成边界](#x-messages-12) |
| [13. 跟着 IDE 阅读消息与事件源码](#x-messages-13) |

<a id="x-messages-01"></a>

## 1. 从一条消息和一条事件开始

用户提交“你好”以后，可以得到一条用户消息：

```ts
const message = {
  role: "user",
  content: [{ type: "text", text: "你好" }],
  timestamp: 0,
};
```

这里用 0 代替创建时间。循环随后可以把这份消息放进事件对象：

```ts
const event = { type: "message_end", message };
```

`message.role` 说明数据由哪一种角色产生，`event.type` 说明程序正在报告哪一种变化。这个对象可以交给函数，也可以进入事件流；创建普通对象本身不会自动通知任何订阅者，真正的通知发生在后面的函数调用中。

### 1.1 pi-ai 的三种标准消息

源码摘录：[types.ts:195](/source/?file=a8f4ce943bcfc7dd27.ts#L195)，第 195—224 行。

```ts
export interface UserMessage {

  role: "user";

  content: string | (TextContent | ImageContent)[];

  timestamp: number;
}

export interface AssistantMessage {

  role: "assistant";

  content: (TextContent | ThinkingContent | ToolCall)[];

  api: Api;

  provider: Provider;

  model: string;

  responseId?: string;

  usage: Usage;

  stopReason: StopReason;

  errorMessage?: string;

  timestamp: number;
}

export interface ToolResultMessage<TDetails = any> {

  role: "toolResult";

  toolCallId: string;

  toolName: string;

  content: (TextContent | ImageContent)[];

  details?: TDetails;

  isError: boolean;

  timestamp: number;
}

export type Message = UserMessage | AssistantMessage | ToolResultMessage;
```

`Message` 是 UserMessage、AssistantMessage 与 ToolResultMessage 的联合。接收方通过 `role` 区分分支，再读取该角色允许的字段。

| 消息 | 主要由谁创建 | 保存在哪里 | 下一步由谁使用 |
| --- | --- | --- | --- |
| UserMessage | 输入规范化或应用转换函数 | Agent 历史、循环上下文，或本次模型输入数组 | 模型请求转换函数 |
| AssistantMessage | pi-ai Provider 累计模型响应；也可能由运行失败处理创建 | 流式阶段占循环中的一个位置，完成后进入 Agent 历史 | 工具判断、显示逻辑、下一次模型请求 |
| ToolResultMessage | 工具结果包装函数 | Agent 历史与循环上下文 | 下一次模型调用及应用消费者 |

AssistantMessage 除了 content，还记录 api、provider、model、usage、stopReason 等信息。即使只显示文字，程序仍需依靠这些字段判断响应是否失败、是否结束，以及它来自哪个模型。

`systemPrompt` 则放在 Context 的独立字段中，见 [types.ts:234](/source/?file=a8f4ce943bcfc7dd27.ts#L234)。Pi 的这个 Message 联合没有单独的 system 角色；Provider 会按自己的协议把系统提示词放进请求。

### 1.2 content 中有哪些块，哪些角色可以使用

源码摘录：[types.ts:148](/source/?file=a8f4ce943bcfc7dd27.ts#L148)，第 148—176 行。

```ts
export interface TextContent {

  type: "text";

  text: string;

  textSignature?: string;
}

export interface ThinkingContent {

  type: "thinking";

  thinking: string;

  thinkingSignature?: string;

  redacted?: boolean;
}

export interface ImageContent {

  type: "image";

  data: string;

  mimeType: string;
}

export interface ToolCall {

  type: "toolCall";

  id: string;

  name: string;

  arguments: Record<string, any>;

  thoughtSignature?: string;
}
```

这些类型分别表达正文、推理内容、图片和调用意图。角色允许的组合不同：

| 位置 | 允许的 content 形状 |
| --- | --- |
| UserMessage | 字符串，或 TextContent/ImageContent 数组 |
| AssistantMessage | TextContent/ThinkingContent/ToolCall 数组 |
| ToolResultMessage | TextContent/ImageContent 数组 |

`ImageContent.data` 是 Base64 数据，`mimeType` 描述格式。ThinkingContent 的可读字段是 `thinking`；与签名相关的字段供 Provider 保留协议信息，不能把不透明签名当成正文。ToolCall 的 `arguments` 是已经解析的对象，其业务参数仍需经过第 07 章的准备与校验。

例如，一条助手消息可以包含两种块。下面只列 content：

```ts
[
  { type: "text", text: "我先读取配置。" },
  { type: "toolCall", id: "read-1", name: "read", arguments: { path: "config.json" } },
]
```

这里仍只有一条 AssistantMessage。文字和工具调用是这条消息的内容块，ToolCall 自身不是独立的消息角色。

### 1.3 调用与结果通过什么关联

对上面的 `read-1`，工具结果消息可能是：

```ts
{
  role: "toolResult",
  toolCallId: "read-1",
  toolName: "read",
  content: [{ type: "text", text: "{\"port\":8080}" }],
  details: {},
  isError: false,
  timestamp: 0,
}
```

假设工具读取后得到示例中的文本。`toolCallId` 对应原 ToolCall 的 `id`，`toolName` 对应 `name`。同名工具被调用两次时，依靠不同调用 ID 区分结果。

```text
assistant.content 中的 ToolCall(id="read-1")
                         │
                         └── toolResult.toolCallId="read-1"
```

这类配对应在消息转换和裁剪时保留。只留下工具结果而移除对应调用，可能使后续 Provider 无法构造符合其协议的历史。内容转换可以改变消息表示，但不能任意破坏调用关系。

### 1.4 `AgentMessage` 扩大了哪些范围

源码摘录：[types.ts:246](/source/?file=d51aa2ef0fa6575e26.ts#L246)，第 246—255 行。

```ts
export interface CustomAgentMessages {

}

export type AgentMessage = Message | CustomAgentMessages[keyof CustomAgentMessages];
```

基础包中的 `CustomAgentMessages` 是空接口。应用可以通过声明合并增加条目；`keyof` 取得条目的键，方括号取得对应值类型，再与标准 Message 合并。

因此，AgentMessage 可以容纳应用自己的消息，而 pi-ai Message 仍限定为标准三种角色。应用消息准备进入模型时，要经过 `convertToLlm`，变成 Provider 能处理的表示。类型声明只扩大编译时约定，运行时的对象创建、数组追加和事件发送仍要由代码完成。

**到这里先记住：**

- `message.role` 区分消息，内容块的 `type` 区分块；content 为数组时，可通过 `message.content[i].type` 读取块类型。`event.type` 区分通知。
- ToolCall 属于助手内容；ToolResultMessage 通过调用 ID 与它配对。
- AgentMessage 允许应用扩充；进入模型前仍需转换成标准 Message。

<a id="x-messages-02"></a>

## 2. 消息从哪里进入历史，事件在什么位置产生

一条输入会同时影响运行上下文和 Agent 状态。这两份数组并非同一个对象：循环需要随时追加或替换消息，Agent 则通过事件维护已完成的消息记录。本节从输入进入循环开始，把数组变化与事件放在同一条执行路径上。

### 2.1 用户输入怎样变成消息

`Agent.prompt()` 在 [agent.ts:341](/source/?file=3688aa044ebb960834.ts#L341) 调用 `normalizePromptInput`。字符串分支如下；处理数组和单条已有消息的前置分支省略：

源码摘录：[agent.ts:388](/source/?file=3688aa044ebb960834.ts#L388)，第 388—393 行。

```ts
  const content: Array<TextContent | ImageContent> = [{ type: "text", text: input }];
  if (images && images.length > 0) {
    content.push(...images);
  }
  return [{ role: "user", content, timestamp: Date.now() }];
}
```

`content` 先放文字块，再按顺序追加可选图片。函数用 `Date.now()` 创建时间戳，最终返回一条 UserMessage 组成的数组。传入已有消息数组时，规范化函数直接返回该数组；传入单条消息则包成数组，见 [agent.ts:376](/source/?file=3688aa044ebb960834.ts#L376)。

此时尚未写入 Agent 的历史。调用方将规范化结果与旧历史快照一起交给 `runAgentLoop()`：

源码摘录：[agent-loop.ts:104](/source/?file=6adbf9ab77a3572a2f.ts#L104)，第 104—162 行。

```ts
  const newMessages: AgentMessage[] = [...prompts];
  const currentContext: AgentContext = {
    ...context,
    messages: [...context.messages, ...prompts],
  };

  await emit({ type: "agent_start" });
  await emit({ type: "turn_start" });
  for (const prompt of prompts) {
    await emit({ type: "message_start", message: prompt });
    await emit({ type: "message_end", message: prompt });
  }

  await runLoop(currentContext, newMessages, config, signal, emit, streamFn);
  return newMessages;
}
```

`newMessages` 从本次提示开始；`currentContext.messages` 则把旧历史与本次提示拼成新数组。随后先发运行和 turn 的开始事件，再逐条发提示消息的 start/end。

### 2.2 三份数组分别收集什么

假设旧历史是 `[H1, H2]`，本次提交 U，正常事件处理不抛错：

| 执行位置 | Agent.state.messages | currentContext.messages | newMessages |
| --- | --- | --- | --- |
| 调用前 | `[H1,H2]` | 尚未建立 | 尚未建立 |
| runAgentLoop 建立数组后 | `[H1,H2]` | `[H1,H2,U]` | `[U]` |
| `message_end(U)` 经 processEvents 后 | `[H1,H2,U]` | `[H1,H2,U]` | `[U]` |

数组内容相近，职责却不同。Agent.state.messages 保存实例的历史，currentContext.messages 供正在运行的循环使用，newMessages 用来汇总这次 run 新增的消息。它们经常共享消息对象引用，但追加数组元素发生在不同语句。

### 2.3 助手和工具消息的追加位置不同

助手消息在 `streamAssistantResponse()` 内进入 currentContext；函数返回后，`runLoop` 在 [agent-loop.ts:238](/source/?file=6adbf9ab77a3572a2f.ts#L238) 才把最终助手消息加入 newMessages。

工具结果则先由批次函数创建并发消息事件，整批返回后，循环再追加：

源码摘录：[agent-loop.ts:252](/source/?file=6adbf9ab77a3572a2f.ts#L252)，第 252—260 行。

```ts
const executedToolBatch = await executeToolCalls(currentContext, message, config, signal, emit);
toolResults.push(...executedToolBatch.messages);
hasMoreToolCalls = !executedToolBatch.terminate;

for (const result of toolResults) {
  currentContext.messages.push(result);
  newMessages.push(result);
}
```

因此，某项工具结果已经通过 `message_end` 进入 Agent.state，不代表它此刻已进入下一项工具钩子能读取的 currentContext。当前批次全部返回，是这段 context 追加的前置条件。

### 2.4 排队消息什么时候进入数组

steering 和 follow-up 的完整调度见第 06 章。对消息系统而言，关键边界是入队、取出和注入：调用 `steer` 或 `followUp` 只写队列，`runLoop` 取到消息后才在后续 turn 中处理它们。

源码摘录：[agent-loop.ts:226](/source/?file=6adbf9ab77a3572a2f.ts#L226)，第 226—234 行。

```ts
if (pendingMessages.length > 0) {
  for (const message of pendingMessages) {
    await emit({ type: "message_start", message });
    await emit({ type: "message_end", message });
    currentContext.messages.push(message);
    newMessages.push(message);
  }
  pendingMessages = [];
}
```

这里先等待消息 start/end 事件，再把消息追加到循环的两个数组。在 Agent 路径中，订阅者处理 message_end 时，Agent.state 已更新，而这段代码的 context 追加还在后面。

| 消息来源 | 正常路径中的顺序 |
| --- | --- |
| 初始 prompt | 建立循环数组 → 发消息事件 → Agent 更新历史 |
| pending 消息 | 发消息事件 → Agent 更新历史 → 追加循环数组 |
| 流式助手 | 在循环数组中追加/替换 → 完成消息事件 → Agent 更新历史 → runLoop 收集到 newMessages |
| 工具结果 | 创建结果消息 → 消息事件更新 Agent 历史 → 批次返回 → 追加循环数组 |

“消息已存好”必须对应具体数组；不同阶段并没有一个同时更新所有容器的操作。

<a id="x-messages-03"></a>

## 3. 模型事件怎样变成 Agent 的消息事件

模型流交出的是 AssistantMessageEvent，循环向外发出的是 AgentEvent。`streamAssistantResponse()` 消费前者、创建后者，同时维护 context 中的一条助手消息。这是消息数据与事件通知最直接的连接位置。

### 3.1 模型事件携带增量，也携带部分消息

AssistantMessageEvent 定义于 [types.ts:248](/source/?file=a8f4ce943bcfc7dd27.ts#L248)，包含下列事件：

| 模型事件 | 主要字段 | 描述的变化 |
| --- | --- | --- |
| `start` | partial | 一次助手响应开始 |
| `text_start/text_delta/text_end` | contentIndex、partial；delta 带 delta，end 带 content | 某个正文块开始、增加文本、完成 |
| `thinking_start/thinking_delta/thinking_end` | contentIndex、partial；delta 带 delta，end 带 content | 某个推理块的变化 |
| `toolcall_start/toolcall_delta/toolcall_end` | contentIndex、partial；delta 带 delta，end 带 toolCall | 某个工具调用块及其参数的变化 |
| `done` | reason、message | 正常停止、长度停止或工具调用停止 |
| `error` | reason、error | 响应错误或取消；error 字段本身是一条 AssistantMessage |

例如，文字增量分支的真实类型是：

源码摘录：[types.ts:251](/source/?file=a8f4ce943bcfc7dd27.ts#L251)，第 251 行。

```ts
| {

    type: "text_delta";

    contentIndex: number;

    delta: string;

    partial: AssistantMessage;
  }
```

这是联合中的一个分支，前后的 `|` 与大括号属于联合类型结构。`contentIndex` 指向助手 content 数组中的块位置；`delta` 是本次增加的文字；`partial` 是已经累积到此刻的助手消息。读取增量和读取累计结果是两种选择。

假设正文先后到来“你”和“好”：

```text
Provider产生第一条增量时：delta="你"，partial.content[0].text="你"
Provider产生第二条增量时：delta="好"，partial.content[0].text="你好"
```

如果界面采用追加文字的方式，应追加 delta；如果每次都追加 partial 的完整文字，就会重复前面内容。

delta 的粒度由流式实现决定，可以包含多个字符，不保证与单个 token 一一对应。toolcall_end 则表示工具调用块已经形成；参数 Schema 检查和真正 execute 仍在后续工具阶段。

### 3.2 一块连续源码：读流、改消息、发通知

下面摘出事件处理主体。输入转换、模型函数调用以及迭代结束后的兜底处理不在这段中。它的三个位置分别是：367 追加助手位置，383 替换该位置，403—404 交付最终消息并返回。

源码摘录：[agent-loop.ts:345](/source/?file=6adbf9ab77a3572a2f.ts#L345)，第 345—394 行。

```ts
let partialMessage: AssistantMessage | null = null;
let addedPartial = false;

for await (const event of response) {
  switch (event.type) {
    case "start":
      partialMessage = event.partial;
      context.messages.push(partialMessage);
      addedPartial = true;
      await emit({ type: "message_start", message: { ...partialMessage } });
      break;

    case "text_start":
    case "text_delta":
    case "text_end":
    case "thinking_start":
    case "thinking_delta":
    case "thinking_end":
    case "toolcall_start":
    case "toolcall_delta":
    case "toolcall_end":
      if (partialMessage) {
        partialMessage = event.partial;
        context.messages[context.messages.length - 1] = partialMessage;
        await emit({
          type: "message_update",
          assistantMessageEvent: event,
          message: { ...partialMessage },
        });
      }
      break;

    case "done":
    case "error": {
      const finalMessage = await response.result();
      if (addedPartial) {
        context.messages[context.messages.length - 1] = finalMessage;
      } else {
        context.messages.push(finalMessage);
      }
      if (!addedPartial) {
        await emit({ type: "message_start", message: { ...finalMessage } });
      }
      await emit({ type: "message_end", message: finalMessage });
      return finalMessage;
    }
  }
}
```

正常收到 `start` 时，循环先把 partial 放进 context.messages，设置 addedPartial，再发送 Agent 的 message_start。随后九种内容块事件都进入同一个更新分支：替换 context 的最后一项，构造 message_update，并把原模型事件放入 assistantMessageEvent 字段。

```text
pi-ai text_delta
  {type:"text_delta", contentIndex:0, delta:"好", partial:A}
                         ↓
Agent message_update
  {type:"message_update", message:{...A}, assistantMessageEvent:上面的事件}
```

A 代表有效的 AssistantMessage，这里省略其模型、用量和时间等字段。外层说明 Agent 的一条消息发生更新，内层保留具体是文字、推理还是工具参数的哪种变化。**message_update 并不只对应 text_delta，也不等于新增一条消息。**

收到 done 或 error 后，函数等待 response.result()，把最终助手消息替换到原位置；如果之前没有收到 start，则补入消息并补发 message_start。最后等待 message_end，再 return finalMessage。

### 3.3 一个助手位置怎样变化

设模型调用前 context 为 `[U]`，输出只有一个正文块。下面假设每条事件被消费时，Provider 尚未向共享消息追加下一段文字；表中省略内容块的 start/end，只观察消息数组的变化。若事件在队列中积压，partial 的共享内容可能已经继续增长，引用关系见下一小节。

| 模型阶段 | context.messages | 发出的 Agent 事件 |
| --- | --- | --- |
| start | `[U,A部分]` | message_start |
| text_delta“你” | `[U,A("你")]` | message_update，携带这次 text_delta |
| text_delta“好” | `[U,A("你好")]` | message_update，携带这次 text_delta |
| done | `[U,A最终]` | message_end |

数组中的助手位置只增加一次，后续更新替换该位置。Agent.state.messages 通常到 message_end 才加入最终助手消息；流式过程中，正在显示的消息保存在 state.streamingMessage。

### 3.4 深入：`{ ...partialMessage }` 复制了什么

对象展开只创建新的外层消息对象，content 数组和内容块仍可能共享：

```ts
const copied = { ...partialMessage };
// copied !== partialMessage
// copied.content === partialMessage.content
```

因此，把 event.message 保存下来，并不自动得到不可变的历史快照。需要保存某次增量时，可以保存内层 delta 字符串；需要保存完整快照时，由消费方明确复制所需数据。

函数末尾 [agent-loop.ts:396](/source/?file=6adbf9ab77a3572a2f.ts#L396) 还有迭代已经结束却未从终态分支返回时的兜底：取得 result、修正消息位置、发 message_end，然后返回。它不是第二次模型请求。

**到这里先记住：**

- 模型事件描述内容块变化，Agent 消息事件描述一条消息的生命周期。
- message_update 同时携带部分消息和原模型事件，两个 type 属于不同层。
- 流式输出更新同一个助手位置；最终消息交出后，runLoop 才继续工具判断。

<a id="x-messages-04"></a>

## 4. emit 怎样更新 Agent 状态并调用订阅者

循环创建事件后，需要有人接收。Agent 路径中的 emit 是调用方传入的函数，它把事件交给 processEvents；后者先修改状态，再调用 subscribe 保存的 listener。

### 4.1 emit 是哪个函数

源码摘录：[agent-loop.ts:25](/source/?file=6adbf9ab77a3572a2f.ts#L25)，第 25 行。

```ts
export type AgentEventSink = (event: AgentEvent) => Promise<void> | void;
```

`AgentEventSink` 接收 AgentEvent，返回 void 或 Promise<void>。在 `runPromptMessages()` 的 [agent.ts:405](/source/?file=3688aa044ebb960834.ts#L405)，传入的是：

```ts
(event) => this.processEvents(event)
```

因此 `await emit(E)` 的实际路径是：

```text
创建事件 E
  → 调用上述箭头函数
  → processEvents(E)，取得 Promise
  → 箭头函数把该 Promise 返回
  → emit 的调用者等待它完成
  → 回到原来的 await 后面
```

这里没有使用独立 EventEmitter。第 10 节会介绍扩展自定义事件总线，它使用另一套发送与登记对象。

### 4.2 AgentEvent 的十种通知由哪里创建

AgentEvent 定义在 [types.ts:349](/source/?file=d51aa2ef0fa6575e26.ts#L349)。它描述 run、turn、消息和工具调用四类变化：

| type | 主要数据 | 典型创建位置 |
| --- | --- | --- |
| agent_start | 只有 type | [agent-loop.ts:139](/source/?file=6adbf9ab77a3572a2f.ts#L139) |
| agent_end | 本次新增 messages | [agent-loop.ts:280](/source/?file=6adbf9ab77a3572a2f.ts#L280)；失败入口可能只交出失败消息 |
| turn_start | 只有 type | 首轮 [agent-loop.ts:140](/source/?file=6adbf9ab77a3572a2f.ts#L140)，后续 [agent-loop.ts:220](/source/?file=6adbf9ab77a3572a2f.ts#L220) |
| turn_end | message、toolResults | [agent-loop.ts:263](/source/?file=6adbf9ab77a3572a2f.ts#L263)；模型失败分支也会发 |
| message_start | message | 用户输入 [agent-loop.ts:156](/source/?file=6adbf9ab77a3572a2f.ts#L156)、助手 [agent-loop.ts:356](/source/?file=6adbf9ab77a3572a2f.ts#L356)、工具 [agent-loop.ts:774](/source/?file=6adbf9ab77a3572a2f.ts#L774) |
| message_update | message、assistantMessageEvent | [agent-loop.ts:371](/source/?file=6adbf9ab77a3572a2f.ts#L371) |
| message_end | message | 用户输入 [agent-loop.ts:157](/source/?file=6adbf9ab77a3572a2f.ts#L157)、助手 [agent-loop.ts:390](/source/?file=6adbf9ab77a3572a2f.ts#L390)、工具 [agent-loop.ts:775](/source/?file=6adbf9ab77a3572a2f.ts#L775) |
| tool_execution_start | toolCallId、toolName、原 args | 串行 [agent-loop.ts:459](/source/?file=6adbf9ab77a3572a2f.ts#L459)，并行 [agent-loop.ts:511](/source/?file=6adbf9ab77a3572a2f.ts#L511) |
| tool_execution_update | toolCallId、toolName、原 args、partialResult | [agent-loop.ts:675](/source/?file=6adbf9ab77a3572a2f.ts#L675) |
| tool_execution_end | toolCallId、toolName、result、isError | [agent-loop.ts:750](/source/?file=6adbf9ab77a3572a2f.ts#L750) |

例如，消息更新的类型分支明确包含两份数据：

源码摘录：[types.ts:359](/source/?file=d51aa2ef0fa6575e26.ts#L359)，第 359 行。

```ts
| {

    type: "message_update";

    message: AgentMessage;

    assistantMessageEvent: AssistantMessageEvent;
  }
```

AgentEvent 的 turn_start 没有 turnIndex 或 timestamp 字段。后文扩展事件中出现这些字段时，是会话桥接函数另外增加的。

### 4.3 先改状态，再调用 listener

源码摘录：[agent.ts:520](/source/?file=3688aa044ebb960834.ts#L520)，第 520—567 行。

```ts
private async processEvents(event: AgentEvent): Promise<void> {
  switch (event.type) {
    case "message_start":
      this._state.streamingMessage = event.message;
      break;

    case "message_update":
      this._state.streamingMessage = event.message;
      break;

    case "message_end":

      this._state.streamingMessage = undefined;
      this._state.messages.push(event.message);
      break;

    case "tool_execution_start": {
      const pendingToolCalls = new Set(this._state.pendingToolCalls);
      pendingToolCalls.add(event.toolCallId);
      this._state.pendingToolCalls = pendingToolCalls;
      break;
    }

    case "tool_execution_end": {
      const pendingToolCalls = new Set(this._state.pendingToolCalls);
      pendingToolCalls.delete(event.toolCallId);
      this._state.pendingToolCalls = pendingToolCalls;
      break;
    }

    case "turn_end":
      if (event.message.role === "assistant" && event.message.errorMessage) {
        this._state.errorMessage = event.message.errorMessage;
      }
      break;

    case "agent_end":
      this._state.streamingMessage = undefined;
      break;
  }

  const signal = this.activeRun?.abortController.signal;
  if (!signal) {
    throw new Error("Agent listener invoked outside active run");
  }
  for (const listener of this.listeners) {

    await listener(event, signal);
  }
}
```

前半段 switch 处理状态，后半段遍历 listener。两者的先后意味着：订阅者收到 message_end 时，读取 Agent.state.messages，已经能找到这条消息。

| 事件 | 状态变化 |
| --- | --- |
| message_start/update | streamingMessage 指向事件中的消息 |
| message_end | 清 streamingMessage，向 messages 追加消息 |
| tool_execution_start | 复制待处理 ID 的 Set，加入 toolCallId，再替换原 Set |
| tool_execution_end | 复制 Set，移除 toolCallId，再替换原 Set |
| turn_end | 助手有 errorMessage 时写入状态 |
| agent_end | 清 streamingMessage；此处尚未释放 activeRun |
| agent_start、turn_start、tool_execution_update | switch 不专门修改状态，仍通知 listener |

streamingMessage 的类型是 `AgentMessage | undefined`，用户、工具和应用消息也可能在 message_start 时短暂进入它。pendingToolCalls 则表示已收到 start、尚未收到 end 的调用；工具查找、校验和阻止检查都在 start 之后，所以它不等同于“当前已经进入 execute 的函数集合”。

### 4.4 subscribe 保存函数，返回取消登记函数

源码摘录：[agent.ts:237](/source/?file=3688aa044ebb960834.ts#L237)，第 237—240 行。

```ts
subscribe(listener: (event: AgentEvent, signal: AbortSignal) => Promise<void> | void): () => void {
  this.listeners.add(listener);
  return () => this.listeners.delete(listener);
}
```

`listeners` 是 Set，初始化位置在 [agent.ts:176](/source/?file=3688aa044ebb960834.ts#L176)。登记同一个函数对象两次只保留一项；两个分别创建的箭头函数则是不同对象。调用返回的函数，会删除对应登记，已经启动的异步工作仍有自己的完成过程。

订阅者可以只提取自己需要的数据。例如，直接保存正文增量：

```ts
const textPieces: string[] = [];
const stop = agent.subscribe((event) => {
  if (
    event.type === "message_update" &&
    event.assistantMessageEvent.type === "text_delta"
  ) {
    textPieces.push(event.assistantMessageEvent.delta);
  }
});
// 不再接收后续通知时，调用 stop()。
```

第一次判断区分 Agent 的消息更新，第二次判断区分这次更新中的模型事件。推理和工具参数更新不会加入 textPieces；两次 delta 为“你”“好”时，数组为 `["你", "好"]`，需要完整正文时再 join。这里保存的是字符串，不会因 partial 的共享内容继续增长而变化。

若应用希望 Agent 等待记录动作，可以让 listener 返回对应 Promise：

```ts
agent.subscribe(async (event) => {
  await record(event);
});
```

这里假设 record 是应用提供的异步函数。若改成下面的写法，返回链只到事件进入后台任务为止：

```ts
agent.subscribe((event) => {
  void record(event);
});
```

`processEvents` 等待的是 listener 的返回值。直接写 `return record(event)` 也能交回同一份 Promise，不要求 listener 一定声明为 async。外层函数里出现 await，并不能使它追踪 listener 没有返回的其他 Promise。

一次 processEvents 内的 listener 按登记顺序调用和等待；不同 processEvents 调用仍可能重叠。工具 onUpdate 会立即发事件、保存 Promise，之后一起等待；并行工具也可以同时发出通知。同步或异步错误如何进入 Agent 的失败处理，以及何时 finishRun，见第 06 章第 9.4 节。

### 4.5 两种流对象与一个回调

| 对象 | 生产者 | 消费者 | result 或返回值 |
| --- | --- | --- | --- |
| AssistantMessageEventStream | pi-ai Provider 或自定义模型函数 | streamAssistantResponse 的 for await | result() 得一次响应的 AssistantMessage |
| AgentEventSink 回调 | Agent Loop 调 emit | Agent.processEvents，或其他调用方提供的接收器 | emit 返回 void/Promise<void> |
| `agentLoop()` 的 EventStream | 包装器通过 stream.push 接收 AgentEvent | 直接使用该 API 的 for await 调用方 | result() 得本次新增 AgentMessage[] |

`Agent.prompt()` 使用回调路径。另一个公开入口 agentLoop 的包装实现见 [agent-loop.ts:31](/source/?file=6adbf9ab77a3572a2f.ts#L31)，其 emit 回调只执行 stream.push；将事件放进流，并不等于流消费者已经处理完事件。这与第 05 章的队列、终态和 result 机制相同，事件数据类型与最终结果类型则不同。

<a id="x-messages-05"></a>

## 5. 应用消息怎样转换成模型输入

编码会话需要保存一些标准三角色之外的信息，例如用户执行命令的结果、扩展提交的提示和历史摘要。这些数据先以 AgentMessage 保存，模型调用前再经过 transformContext 与 convertToLlm。本节从这些消息的来源一直追到 pi-ai Context。

### 5.1 coding-agent 增加的四种消息

源码摘录：[messages.ts:29](/source/?file=2d4c32a97bc465b1f2.ts#L29)，第 29—77 行。

```ts
export interface BashExecutionMessage {
  role: "bashExecution";

  command: string;

  output: string;

  exitCode: number | undefined;

  cancelled: boolean;

  truncated: boolean;

  fullOutputPath?: string;

  timestamp: number;

  excludeFromContext?: boolean;
}

export interface CustomMessage<T = unknown> {
  role: "custom";

  customType: string;

  content: string | (TextContent | ImageContent)[];

  display: boolean;

  details?: T;

  timestamp: number;
}

export interface BranchSummaryMessage {
  role: "branchSummary";

  summary: string;

  fromId: string;

  timestamp: number;
}

export interface CompactionSummaryMessage {
  role: "compactionSummary";

  summary: string;

  tokensBefore: number;

  timestamp: number;
}

declare module "@mariozechner/pi-agent-core" {
  interface CustomAgentMessages {
    bashExecution: BashExecutionMessage;
    custom: CustomMessage;
    branchSummary: BranchSummaryMessage;
    compactionSummary: CompactionSummaryMessage;
  }
}
```

声明合并将四种角色加入 AgentMessage。各自的生产入口如下：

| 消息 | 主要字段 | 创建或恢复位置 |
| --- | --- | --- |
| bashExecution | command、output、exitCode、cancelled、truncated、可选完整输出路径与 excludeFromContext | [agent-session.ts:2659](/source/?file=24209413646c397dc9.ts#L2659) 的 recordBashResult |
| custom | customType、content、display、可选 details | [agent-session.ts:1306](/source/?file=24209413646c397dc9.ts#L1306) 的 sendCustomMessage；会话恢复使用 [messages.ts:123](/source/?file=2d4c32a97bc465b1f2.ts#L123) |
| branchSummary | summary、fromId | [messages.ts:100](/source/?file=2d4c32a97bc465b1f2.ts#L100) 创建，[session-manager.ts:394](/source/?file=043f6d188e65e3207b.ts#L394) 从分支摘要记录恢复 |
| compactionSummary | summary、tokensBefore | [messages.ts:109](/source/?file=2d4c32a97bc465b1f2.ts#L109) 创建，[session-manager.ts:400](/source/?file=043f6d188e65e3207b.ts#L400) 从压缩记录组织成上下文消息 |

`bashExecution` 记录用户命令执行结果；模型调用 bash 工具产生的结果仍是 ToolResultMessage。两者的触发来源与消息角色不同。

摘要消息保存的是已经生成的 summary，消息构造函数只把它放入对象并转换时间戳。摘要怎样计算、会话分支怎样选择属于各自功能，本章只追踪消息表示与消费。

### 5.2 Message 与会话记录的 ID 分别是什么

Agent 历史是一组消息对象。SessionManager 还会给保存的记录增加条目 ID、父条目 ID 和记录时间：

源码摘录：[session-manager.ts:860](/source/?file=043f6d188e65e3207b.ts#L860)，第 860—870 行。

```ts
appendMessage(message: Message | CustomMessage | BashExecutionMessage): string {

  const entry: SessionMessageEntry = {
    type: "message",
    id: generateId(this.byId),
    parentId: this.leafId,
    timestamp: new Date().toISOString(),
    message,
  };
  this._appendEntry(entry);
  return entry.id;
}
```

`entry.id` 标识会话记录，`entry.parentId` 用来组织记录关系；ToolCall.id 和 ToolResultMessage.toolCallId 则关联一次工具调用。这两类 ID 解决不同问题。

例如，一条工具结果 `R` 的局部字段是 `{ role: "toolResult", toolCallId: "read-1", ... }`。设当前叶条目为“条目 A”，appendMessage 生成的新条目 ID 为“条目 B”；这里只用文字代替真实 ID：

```text
传入消息 R
  role = "toolResult"
  toolCallId = "read-1"

创建记录 entry
  type = "message"
  id = "条目 B"
  parentId = "条目 A"
  timestamp = 记录创建时间的 ISO 字符串
  message = R
    └─ toolCallId 仍为 "read-1"

appendMessage(R) 返回 "条目 B"
```

方法把原消息放到 `entry.message` 中，没有把 ToolCall ID 改成会话 ID。恢复普通消息时，[session-manager.ts:387](/source/?file=043f6d188e65e3207b.ts#L387) 读取 `entry.message`；工具调用与结果继续通过 read-1 配对。外层 timestamp 描述记录创建时间，消息自己的 timestamp 仍留在 R 中。

custom 消息使用专门的 custom_message 记录。恢复上下文时，[session-manager.ts:386](/source/?file=043f6d188e65e3207b.ts#L386) 按 entry.type 取普通 message，或调用 createCustomMessage 等函数重新构造应用消息。会话记录与模型请求数组之间有这个组织过程，并非把文件里的每个条目原样交给模型。

### 5.3 transformContext 与 convertToLlm 的先后关系

源码摘录：[agent-loop.ts:314](/source/?file=6adbf9ab77a3572a2f.ts#L314)，第 314—328 行。

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

`messages` 最初引用 context.messages。可选 transformContext 处理仍属于 AgentMessage 的数组；必需的 convertToLlm 再返回标准 Message 数组，放入 llmContext。代码没有把回调返回值写回 context.messages。

```text
循环历史 context.messages： [U, Custom, Assistant, ToolResult]
          │
          ↓ transformContext（若配置）
此次请求要采用的 AgentMessage[]
          ↓ convertToLlm
标准 Message[]
          ↓
llmContext.messages
```

回调返回一个新数组，只改变本次请求继续使用的材料。直接修改传入数组或共享对象则可能影响原历史，是否隔离取决于具体回调有没有复制数据。

直接 Agent 默认采用的转换很简单：

源码摘录：[agent.ts:40](/source/?file=3688aa044ebb960834.ts#L40)，第 40—44 行。

```ts
function defaultConvertToLlm(messages: AgentMessage[]): Message[] {
  return messages.filter(
    (message) => message.role === "user" || message.role === "assistant" || message.role === "toolResult",
  );
}
```

它保留标准三角色，过滤其他角色。编码会话在 [sdk.ts:315](/source/?file=07502145bf1ffa712b.ts#L315) 换成自己的转换函数，因此 coding-agent 的应用消息不会仅因角色不同就全部丢弃。

### 5.4 coding-agent 的转换怎样改变角色与正文

源码摘录：[messages.ts:148](/source/?file=2d4c32a97bc465b1f2.ts#L148)，第 148—195 行。

```ts
export function convertToLlm(messages: AgentMessage[]): Message[] {
  return messages

    .map((m): Message | undefined => {
      switch (m.role) {

        case "bashExecution":

          if (m.excludeFromContext) {
            return undefined;
          }
          return {
            role: "user",
            content: [{ type: "text", text: bashExecutionToText(m) }],
            timestamp: m.timestamp,
          };

        case "custom": {

          const content = typeof m.content === "string" ? [{ type: "text" as const, text: m.content }] : m.content;
          return {
            role: "user",
            content,
            timestamp: m.timestamp,
          };
        }

        case "branchSummary":
          return {
            role: "user",
            content: [{ type: "text" as const, text: BRANCH_SUMMARY_PREFIX + m.summary + BRANCH_SUMMARY_SUFFIX }],
            timestamp: m.timestamp,
          };

        case "compactionSummary":
          return {
            role: "user",
            content: [
              { type: "text" as const, text: COMPACTION_SUMMARY_PREFIX + m.summary + COMPACTION_SUMMARY_SUFFIX },
            ],
            timestamp: m.timestamp,
          };

        case "user":
        case "assistant":
        case "toolResult":
          return m;
        default:

          const _exhaustiveCheck: never = m;
          return undefined;
      }
    })

    .filter((m) => m !== undefined);
}
```

这个函数先 map，再过滤 undefined。每种角色的结果如下：

| 输入 | 输出给模型的内容 |
| --- | --- |
| 标准 user/assistant/toolResult | 返回原消息对象 |
| bashExecution，excludeFromContext 为真 | 返回 undefined，随后过滤 |
| 其余 bashExecution | 转为 user，content 为命令、输出和相关状态组成的文字 |
| custom | 转为 user；字符串变为一个 text 块，内容块数组直接使用 |
| branchSummary | 转为 user，在 summary 前后加固定说明与标签 |
| compactionSummary | 同样转为 user，采用压缩摘要的固定说明与标签 |

例如：

```text
输入：
{role:"custom", customType:"note", content:"回答使用中文",
 display:false, details:{source:"extension"}, timestamp:0}

输出：
{role:"user", content:[{type:"text",text:"回答使用中文"}], timestamp:0}
```

display 不参与这里的过滤。`display: false` 可以表达不显示这条自定义消息，但默认转换仍把正文交给模型；customType 和 details 也不会自动拼进正文。需要模型使用的内容，应明确写进 content。

bashExecution 的 `excludeFromContext` 则是另一种行为：它影响这次转换是否保留该消息，不会因此删除 Agent 历史或已有会话记录。

bashExecution 的正文由下面的完整函数生成：

源码摘录：[messages.ts:82](/source/?file=2d4c32a97bc465b1f2.ts#L82)，第 82—98 行。

```ts
export function bashExecutionToText(msg: BashExecutionMessage): string {
  let text = `Ran \`${msg.command}\`\n`;
  if (msg.output) {
    text += `\`\`\`\n${msg.output}\n\`\`\``;
  } else {
    text += "(no output)";
  }
  if (msg.cancelled) {
    text += "\n\n(command cancelled)";
  } else if (msg.exitCode !== null && msg.exitCode !== undefined && msg.exitCode !== 0) {
    text += `\n\nCommand exited with code ${msg.exitCode}`;
  }
  if (msg.truncated && msg.fullOutputPath) {
    text += `\n\n[Output truncated. Full output: ${msg.fullOutputPath}]`;
  }
  return text;
}
```

调用者是 convertToLlm 的 bashExecution 分支；传入参数 `msg` 就是那条应用消息。函数先写 command，再检查 output 是否有内容；没有输出时写 `(no output)`。cancelled 优先于非零 exitCode，因此取消与失败退出码不会在这个分支中同时追加。截断提示则还要求 fullOutputPath 存在，函数只把路径写入文字，不读取该文件。

例如，给定以下数据；command 和 output 均为示例字段，不表示这里执行过该命令：

```ts
{
  role: "bashExecution",
  command: "example-command",
  output: "ok",
  exitCode: 0,
  cancelled: false,
  truncated: false,
  timestamp: 0
}
```

`bashExecutionToText` 返回命令与输出组成的字符串，convertToLlm 将它放进一个 text 块：

```ts
{
  role: "user",
  content: [{ type: "text", text: "Ran `example-command`\n```\nok\n```" }],
  timestamp: 0
}
```

从这一步起，模型看到的是命令及结果的文字说明；原消息的 command、exitCode 等字段仍保留在 Agent 历史中。

| 仅改变输入中的哪一项 | 转换结果 |
| --- | --- |
| `output: ""` | 正文中的代码块改为 `(no output)` |
| `exitCode: 2`，保持未取消 | 正文末尾追加 `Command exited with code 2` |
| `cancelled: true` | 正文末尾追加 `(command cancelled)`，不再追加退出码分支 |
| `excludeFromContext: true` | convertToLlm 提前返回 undefined，不调用正文转换；随后被 filter 移除 |

最后一种情况只移除本次模型输入中的该项。假设转换前为 `[U, B排除, C自定义, A工具调用, R工具结果]`，则 map 的中间结果为 `[U, undefined, C转成的user, A, R]`，filter 后为四条消息。A 和 R 的调用配对没有改变，消息在新数组中的索引却因过滤发生了移动。因此跨消息关联应依靠 toolCallId，而不应把某个固定数组下标当作调用标识。

### 5.5 深入：新数组与对象复用

map/filter 创建了新的外层数组，但标准消息分支直接 return m；custom 已经是内容块数组时，也直接复用 m.content。它不是整份深拷贝。

```text
标准消息：converted[i] === originalMessage
custom：  converted[i] 是新外层对象
          若原 content 是数组，两个外层可能共用这份数组
```

类型转换关注消息表示，引用隔离则需要另看复制语句。第 8 节的扩展 context 钩子会先 structuredClone，这属于那个入口额外提供的处理。

### 5.6 SDK 的图片过滤发生在标准转换之后

SDK 在 [sdk.ts:268](/source/?file=07502145bf1ffa712b.ts#L268) 定义 convertToLlmWithBlockImages，先调用上面的 convertToLlm，再读取图片设置。关闭图片读取时，对 user 与 toolResult 的图片块进行替换。下面是替换与相邻提示合并部分，外层角色判断和函数收尾省略：

源码摘录：[sdk.ts:281](/source/?file=07502145bf1ffa712b.ts#L281)，第 281—296 行。

```ts
const filteredContent = content
  .map((c) =>
    c.type === "image" ? { type: "text" as const, text: "Image reading is disabled." } : c,
  )
  .filter(
    (c, i, arr) =>

      !(
        c.type === "text" &&
        c.text === "Image reading is disabled." &&
        i > 0 &&
        arr[i - 1].type === "text" &&
        (arr[i - 1] as { type: "text"; text: string }).text === "Image reading is disabled."
      ),
  );

return { ...msg, content: filteredContent };
```

例如，content 原来是 `[文字, 图片1, 图片2]`，替换后为 `[文字, "Image reading is disabled."]`；连续的同样提示会被合并。带图片的消息通过 `{ ...msg, content: filteredContent }` 创建新外层，其余内容块仍可能复用。

这一步改变本次交给模型的表示，不把 Agent 历史中的图片消息改写为提示文字。完整网络图片编码已在第 05 章说明。

**到这里先记住：**

- 应用消息先在 AgentMessage 范围内保存，再转换为标准 Message。
- transformContext 选择或整理本次请求材料，convertToLlm 负责模型可接受的表示。
- display、excludeFromContext、details 的用途不同；模型实际看到什么，要追到转换函数的返回值。

<a id="x-messages-06"></a>

## 6. AgentSession 怎样接收、排队和转发事件

AgentSession 使用 Agent 提供的订阅接口，把运行事件接入会话逻辑。它需要继续处理扩展通知、会话监听器和记录追加，因此增加了一条 Promise 队列。理解这一层的关键，是区分“Agent 已调用接收函数”与“会话队列已处理完事件”。

### 6.1 登记到 Agent 的是哪一个函数

会话构造函数在 [agent-session.ts:331](/source/?file=24209413646c397dc9.ts#L331) 执行：

```ts
this._unsubscribeAgent = this.agent.subscribe(this._handleAgentEvent);
```

返回的取消函数保存在 `_unsubscribeAgent`。以后 Agent.processEvents 遍历 listeners 时，会调用这个 `_handleAgentEvent`。

源码摘录：[agent-session.ts:459](/source/?file=24209413646c397dc9.ts#L459)，第 459—474 行。

```ts
private _handleAgentEvent = (event: AgentEvent): void => {

  this._createRetryPromiseForAgentEnd(event);

  this._agentEventQueue = this._agentEventQueue.then(
    () => this._processAgentEvent(event),
    () => this._processAgentEvent(event),
  );

  this._agentEventQueue.catch(() => {});
};
```

这段接收函数的返回类型是 void。453 行先建立可能需要的重试等待状态；455 行把事件接到 `_agentEventQueue` 后面；461 行为拒绝附加处理。它没有 return 队列 Promise。

`_agentEventQueue` 在 [agent-session.ts:252](/source/?file=24209413646c397dc9.ts#L252) 初始化为 `Promise.resolve()`。每次 `.then` 返回一个新 Promise，重新赋给同一字段，使以后到来的事件接在它后面。

```text
初始 P0 = 已完成的 Promise
收到 E1：P1 = P0.then(() => process(E1), () => process(E1))
收到 E2：P2 = P1.then(() => process(E2), () => process(E2))

_handleAgentEvent 当下只保存 P1/P2，返回 undefined
前一项完成或拒绝后，后一项的处理才进入执行
```

两个 then 回调分别对应成功与失败，都会处理下一条事件。这样，前一个队列项失败后，后续事件仍有机会继续；失败项中已经跳过的步骤不会因此被补做。

这里有两条不同的返回关系。`_handleAgentEvent` 不返回队列 Promise，所以 Agent 不等会话处理完成；但 then 内的箭头函数**会返回** `_processAgentEvent(event)` 的 Promise，所以会话队列的下一项确实等待这一项处理结束。

表达式形式的箭头函数等价于下面这段局部写法：

```ts
// 与源码中的 then 回调等价，展开 return 便于观察等待关系。
() => {
  return this._processAgentEvent(event);
}
```

假设 E1 是一条 message_end，其扩展 handler 正在等待尚未完成的记录操作：

| 时间点 | 保存的队列尾 | 处理进度 |
| --- | --- | --- |
| 接收 E1 | P1 | then 回调开始后，P1 等待 process(E1) 返回的 Promise |
| E1 仍未完成时接收 E2 | P2 | E2 已登记在 P1 后面，还没有进入 process(E2) |
| E1 的扩展记录完成 | P2 | E1 继续普通会话通知和消息记录，再结束 process(E1) |
| P1 完成 | P2 | 才进入 process(E2)；P2 等待它的处理 Promise |

如果把 then 回调改成 `{ this._processAgentEvent(event); }` 却漏掉 return，回调会返回 undefined，队列就失去等待该项处理的关系。源码使用表达式箭头，正是通过这个返回值将各项处理串起来。若 P1 拒绝，则由 then 的第二个回调启动 E2；这不会重试 E1，也不会补做 E1 抛错之后跳过的消息记录。

### 6.2 Agent 的 await 停在哪里

```text
Agent.processEvents(E)
  → 更新 Agent.state
  → await _handleAgentEvent(E)
       → 将 E 排到会话队列
       → 返回 undefined
  → 这个 listener 的等待完成，Agent 可以继续

会话队列：稍后进入 _processAgentEvent(E)，继续处理扩展、通知与记录
```

会话任务有时可能很快开始，但“处理完会话队列”没有通过这个 listener 的返回值交回 Agent。判断是否等待应看返回的 Promise，而不能只看上层出现了 `await listener(...)`。

**深入：**461 行的 catch 没有把 catch 返回的新 Promise 再赋给 `_agentEventQueue`。它避免原 Promise 的拒绝无人处理，但不把字段中的失败状态改成成功；后续继续处理靠的是 then 的第二个回调。

### 6.3 会话处理顺序：扩展、普通监听器、记录追加

`_processAgentEvent()` 首先在 user 的 message_start 分支处理显示队列，随后进入下面的主干。这里省略此前的队列文字匹配，以及后面的重试和压缩处理：

源码摘录：[agent-session.ts:532](/source/?file=24209413646c397dc9.ts#L532)，第 532—556 行。

```ts
await this._emitExtensionEvent(event);

this._emit(event);

if (event.type === "message_end") {

  if (event.message.role === "custom") {

    this.sessionManager.appendCustomMessageEntry(
      event.message.customType,
      event.message.content,
      event.message.display,
      event.message.details,
    );
  } else if (
    event.message.role === "user" ||
    event.message.role === "assistant" ||
    event.message.role === "toolResult"
  ) {

  this.sessionManager.appendMessage(event.message);
  }
// ... message_end 内的后续处理及外层函数收尾省略。
```

三段动作依次发生：

1. 等待 `_emitExtensionEvent(event)`，把生命周期通知交给扩展。
2. 调用 `_emit(event)`，同步调用会话普通 listener。
3. 若为 message_end，按消息角色追加会话记录。

custom 进入 `appendCustomMessageEntry`；标准 user、assistant、toolResult 进入 `appendMessage`。这些位置负责会话记录，模型请求中的数组转换则是第 5 节的另一条路径。

对一条正常完成的助手消息 A，可以观察到：

| 停点 | Agent.state.messages | 这条消息的 SessionManager 追加 |
| --- | --- | --- |
| Agent.processEvents 已处理 message_end | 已有 A | 会话队列未必走到该项 |
| 扩展生命周期 handler 正在处理 | 已有 A | 尚未执行下面的追加语句 |
| session.subscribe 的同步回调开始 | 已有 A | 仍在 `_emit` 之后等待执行 |
| 872 的 appendMessage 返回 | 已有 A | 本次记录已交给 SessionManager |

追加记录与写入文件还需区分，具体持久化条件由 SessionManager 处理。本章的通知不能单独证明文件已经写入。

### 6.4 `session.subscribe()` 与 `agent.subscribe()` 的不同

源码摘录：[agent-session.ts:705](/source/?file=24209413646c397dc9.ts#L705)，第 705—715 行。

```ts
subscribe(listener: AgentSessionEventListener): () => void {
  this._eventListeners.push(listener);

  return () => {
    const index = this._eventListeners.indexOf(listener);
    if (index !== -1) {
      this._eventListeners.splice(index, 1);
    }
  };
}
```

会话 listener 保存在数组中，`push` 会保留重复登记；取消函数通过 indexOf 找到第一项匹配的函数，再用 splice 移除。相比之下，Agent 的 Set 会对同一个函数对象去重。

实际派发只有几行：

源码摘录：[agent-session.ts:440](/source/?file=24209413646c397dc9.ts#L440)，第 440—444 行。

```ts
private _emit(event: AgentSessionEvent): void {
  for (const l of this._eventListeners) {
    l(event);
  }
}
```

它调用 `l(event)`，不等待返回的 Promise。async listener 的同步前半段仍会执行，但其 await 之后的工作不属于 `_emit` 的等待范围。

```text
会话 listener 开始
  → 执行到自身的 await，返回 Promise
  → _emit 忽略该 Promise，调用下一 listener
  → _processAgentEvent 继续记录追加
  → 先前 listener 的异步任务之后再完成
```

因此，普通会话监听器若要完成网络发送或写库，需要应用自己组织完成信号与错误处理。同步抛错会直接中断 `_emit` 和当前处理步骤；async 函数返回的拒绝则不会由这个同步循环自动接住。

队列还保存了事件对象的引用，桥接时多数嵌套消息也继续共享。延迟读取 event.message 或共享 Agent 状态，不保证看到事件产生当时的一份独立快照。

### 6.5 会话额外通知有哪些

源码摘录：[agent-session.ts:114](/source/?file=24209413646c397dc9.ts#L114)，第 114—134 行。

```ts
export type AgentSessionEvent =
  | AgentEvent
  | {
      type: "queue_update";
      steering: readonly string[];
      followUp: readonly string[];
    }
  | { type: "compaction_start"; reason: "manual" | "threshold" | "overflow" }
  | {
      type: "compaction_end";
      reason: "manual" | "threshold" | "overflow";
      result: CompactionResult | undefined;
      aborted: boolean;
      willRetry: boolean;
      errorMessage?: string;
    }
  | { type: "auto_retry_start"; attempt: number; maxAttempts: number; delayMs: number; errorMessage: string }
  | { type: "auto_retry_end"; success: boolean; attempt: number; finalError?: string };

export type AgentSessionEventListener = (event: AgentSessionEvent) => void;
```

AgentSessionEvent 直接包含 AgentEvent，另外增加五种 type：

| 事件 | 数据用途 |
| --- | --- |
| queue_update | 会话 steering、followUp 文字显示队列的副本 |
| compaction_start | 报告压缩开始及原因 |
| compaction_end | 压缩结果、取消、是否将重试和可能的错误 |
| auto_retry_start | 重试次数、上限、延迟和错误原因 |
| auto_retry_end | 成功与否、次数和可能的最终错误 |

`queue_update` 的创建位置是 [agent-session.ts:446](/source/?file=24209413646c397dc9.ts#L446)。它报告会话保存的两份文字数组，其中的项目在会话处理用户 message_start 时才按文字移除，与 Agent 队列和 runLoop.pendingMessages 并非同步更新。因此，某条消息已经被 Agent 取走，其文字仍可能短暂留在会话显示队列中。nextTurn 消息或直接排入 Agent 队列的 custom 消息，也不会自动登记到这两份文字数组。

这些会话通知由相应会话功能主动调用 `_emit`，并不要求先经过 Agent Loop。普通 session.subscribe 收到的 turn_start 仍是原 AgentEvent，只有 type；下一节扩展 turn_start 的字段有所不同。

**到这里先记住：**

- AgentSession 的 Agent listener 入队后返回 void，Agent 不借这个返回值等待会话队列完成。
- 正常会话消息事件先交扩展，再交普通订阅者，随后才追加会话记录。
- Session 普通 listener 不被 await；它与 Agent listener 的等待约定不同。

<a id="x-messages-07"></a>

## 7. 扩展怎样通过 pi.on 接收生命周期事件

扩展可以用 pi.on 登记运行通知。这个登记入口保存的是另一张 handlers 表，AgentSession 在处理自己的事件队列时，将 AgentEvent 转成相应扩展事件，再交给 ExtensionRunner 调用处理器。

### 7.1 `pi.on` 保存事件名与 handler 的对应关系

源码摘录：[loader.ts:200](/source/?file=d170abdf93d664a78b.ts#L200)，第 200—205 行。

```ts
on(event: string, handler: HandlerFn): void {
  runtime.assertActive();

  const list = extension.handlers.get(event) ?? [];

  list.push(handler);

  extension.handlers.set(event, list);
},
```

每个扩展有自己的 Map，键是事件名，值是 handler 数组。扩展工厂加载时调用 pi.on 只完成登记；实际 event 和 ExtensionContext 将在以后派发时传入。

handler 的类型在 [types.ts:1062](/source/?file=baffea2d47e73908cd.ts#L1062)：

```ts
(event: E, ctx: ExtensionContext) => Promise<R | void> | R | void
```

R 随事件契约变化。生命周期通知通常不读取业务返回值；需要改变行为的钩子有专门的结果类型与处理函数。`pi.on` 本身返回 void，没有与 subscribe 相同的取消函数。

一个使用生命周期数据的例子如下。它是供扩展工厂调用的辅助函数，`record` 由应用提供：

```ts
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export function registerTurnRecorder(
  pi: ExtensionAPI,
  record: (row: { turnIndex: number; toolResults: number; cwd: string }) => Promise<void>,
): void {
  pi.on("turn_end", async (event, ctx) => {
    await record({
      turnIndex: event.turnIndex,
      toolResults: event.toolResults.length,
      cwd: ctx.cwd,
    });
  });
}
```

扩展工厂取得 pi 后调用 `registerTurnRecorder(pi, record)`，此时只是登记函数；以后会话桥创建 turn_end，runner 才把它传给 handler。第一轮的 turnIndex 为 0，toolResults 数值来自该轮已经汇总的结果数组。event 携带本次通知的数据，ctx.cwd 则来自 runner 提供的 ExtensionContext；工作目录不是 turn_end 事件自身的字段。

这个 handler 返回的 Promise 使 runner 等待 record；record 完成后，同次派发才进入后面的 handler。等待属于会话事件处理链，不能因此扩大成 Agent 主循环也等待整个会话队列。record 的业务返回数据也不会被当成新的消息或工具结果；这个例子的返回契约是通知处理完成。

### 7.2 从 AgentEvent 构造扩展事件

桥接函数 `_emitExtensionEvent()` 位于 [agent-session.ts:628](/source/?file=24209413646c397dc9.ts#L628)。下面摘录运行与 turn 的分支，其余消息和工具分支接后表：

源码摘录：[agent-session.ts:628](/source/?file=24209413646c397dc9.ts#L628)，第 628—649 行。

```ts
private async _emitExtensionEvent(event: AgentEvent): Promise<void> {
  if (event.type === "agent_start") {
    this._turnIndex = 0;
    await this._extensionRunner.emit({ type: "agent_start" });
  } else if (event.type === "agent_end") {
    await this._extensionRunner.emit({ type: "agent_end", messages: event.messages });
  } else if (event.type === "turn_start") {
    const extensionEvent: TurnStartEvent = {
      type: "turn_start",
      turnIndex: this._turnIndex,
      timestamp: Date.now(),
    };
    await this._extensionRunner.emit(extensionEvent);
  } else if (event.type === "turn_end") {
    const extensionEvent: TurnEndEvent = {
      type: "turn_end",
      turnIndex: this._turnIndex,
      message: event.message,
      toolResults: event.toolResults,
    };
    await this._extensionRunner.emit(extensionEvent);
    this._turnIndex++;
// ... 后续消息与工具事件分支及函数收尾省略。
```

agent_start 重置会话维护的 `_turnIndex`。扩展 turn_start 在原来的 type 之外增加 turnIndex 和处理时的时间戳；turn_end 带同一索引，并在等待扩展处理完成后递增。

```text
AgentEvent：    {type:"turn_start"}
扩展事件示例： {type:"turn_start", turnIndex:0, timestamp:...}
```

这里省略 timestamp 的具体数值。它在桥接处理时调用 Date.now 得到，不是核心事件中原有的时间字段。

消息和工具分支也创建新的事件外层：

| Agent 通知 | 复制到扩展事件的数据 | 桥接位置 |
| --- | --- | --- |
| agent_end | messages | [agent-session.ts:633](/source/?file=24209413646c397dc9.ts#L633) |
| message_start/end | message | [agent-session.ts:650](/source/?file=24209413646c397dc9.ts#L650)、[agent-session.ts:663](/source/?file=24209413646c397dc9.ts#L663) |
| message_update | message、assistantMessageEvent | [agent-session.ts:656](/source/?file=24209413646c397dc9.ts#L656) |
| tool_execution_start | toolCallId、toolName、原 args | [agent-session.ts:669](/source/?file=24209413646c397dc9.ts#L669) |
| tool_execution_update | 上述调用信息与 partialResult | [agent-session.ts:677](/source/?file=24209413646c397dc9.ts#L677) |
| tool_execution_end | toolCallId、toolName、result、isError | [agent-session.ts:686](/source/?file=24209413646c397dc9.ts#L686) |

新建事件外层不代表深复制消息内容。普通 session.subscribe 使用的是原来的 event；扩展得到的是这里构造的对象，两者不能仅凭 type 同名就当成同一个类型声明。

### 7.3 runner 怎样找到 handler 并等待

源码摘录：[runner.ts:682](/source/?file=1a64f1a2d3fca70128.ts#L682)，第 682—714 行。

```ts
async emit<TEvent extends RunnerEmitEvent>(event: TEvent): Promise<RunnerEmitResult<TEvent>> {
  const ctx = this.createContext();

  let result: SessionBeforeEventResult | undefined;

  for (const ext of this.extensions) {
    const handlers = ext.handlers.get(event.type);

    if (!handlers || handlers.length === 0) continue;

    for (const handler of handlers) {
      try {

        const handlerResult = await handler(event, ctx);

        if (this.isSessionBeforeEvent(event) && handlerResult) {
          result = handlerResult as SessionBeforeEventResult;

          if (result.cancel) {
            return result as RunnerEmitResult<TEvent>;
          }
        }
      } catch (err) {

        const message = err instanceof Error ? err.message : String(err);
        const stack = err instanceof Error ? err.stack : undefined;
        this.emitError({
          extensionPath: ext.path,
          event: event.type,
          error: message,
          stack,
        });
      }
    }
  }

  return result as RunnerEmitResult<TEvent>;
}
```

runner 先创建 ExtensionContext，再按扩展数组顺序读取 `handlers.get(event.type)`，在各扩展内部按登记顺序调用并等待 handler。

对生命周期通知，handler 返回一个对象不会自动替换消息。代码只对 session_before 类事件读取对应控制结果；其他需要输入或结果转换的事件会走下一节的专用函数。

单个 handler 的错误通常被捕获并交给 emitError，随后继续其他处理器。这是普通派发函数的处理方式；工具前置钩子等专用路径有自己的错误传播规则。

```text
Session队列中的 _processAgentEvent(E)
  → await _emitExtensionEvent(E)
    → await runner.emit(扩展事件)
      → await handler A(event, ctx)
      → await handler B(event, ctx)
  → 回到 _processAgentEvent，执行普通 _emit 与记录追加
```

这条链会等待扩展 handler，但它开始于会话队列。不能据此推断 Agent 主循环一定也在等待该队列；第 6 节的 void 返回边界仍然存在。

### 7.4 pi.on 接受哪些事件

ExtensionEvent 联合位于 [types.ts:939](/source/?file=baffea2d47e73908cd.ts#L939)，登记重载集中在 [types.ts:1073](/source/?file=baffea2d47e73908cd.ts#L1073)。事件可按来源和返回用途分组：

| 类别 | 实际事件名 | 返回值用途 |
| --- | --- | --- |
| Agent 生命周期 | agent_start/end、turn_start/end、message_start/update/end、tool_execution_start/update/end | 通知，不读取一般业务返回对象 |
| 会话结果通知 | session_start、session_compact、session_shutdown、session_tree | 通知 |
| 模型与请求通知 | model_select、after_provider_response | 通知 |
| 会话操作前置 | session_before_switch、session_before_fork、session_before_compact、session_before_tree | 可取消；其他结果字段由相应操作读取 |
| 输入与本次运行准备 | input、before_agent_start | 转换/处理输入，或返回附加消息与系统提示词 |
| 模型输入与请求准备 | context、before_provider_request | 替换本次消息数组或请求 payload |
| 工具与用户命令 | tool_call、tool_result、user_bash | 阻止工具、覆盖结果，或提供用户命令的操作/结果 |
| 资源发现 | resources_discover | 增加技能、提示词和主题路径 |

这些事件不全部来自 AgentEvent。context 是模型输入准备函数主动派发，tool_call/tool_result 由工具 before/after 派发，其他操作也有自己的创建位置。会话附加通知中的 queue_update、compaction_start 等名字，则不属于这组 pi.on 重载。

这里列出范围，是为了在 IDE 中判断应该查哪一个派发函数。具体会话切换、资源加载和压缩算法不需要在消息事件主线中继续展开。

<a id="x-messages-08"></a>

## 8. 能改变输入和工具结果的事件，由谁直接等待

有些扩展事件需要读取 handler 的返回值，才能继续下一步。它们直接接在模型或工具处理函数上，等待边界与会话生命周期队列不同。context 钩子最能体现“事件返回值改变本次消息数据”的过程。

### 8.1 context 从 transformContext 进入

SDK 提供给 Agent 的回调如下：

源码摘录：[sdk.ts:350](/source/?file=07502145bf1ffa712b.ts#L350)，第 350—354 行。

```ts
transformContext: async (messages) => {
  const runner = extensionRunnerRef.current;
  if (!runner) return messages;
  return runner.emitContext(messages);
},
```

`streamAssistantResponse` 在 [agent-loop.ts:316](/source/?file=6adbf9ab77a3572a2f.ts#L316) 等待 transformContext。SDK 读取 runner；有 runner 时，返回 emitContext 的 Promise，使等待一直连到 context handlers。

源码摘录：[runner.ts:822](/source/?file=1a64f1a2d3fca70128.ts#L822)，第 822—852 行。

```ts
async emitContext(messages: AgentMessage[]): Promise<AgentMessage[]> {

  const ctx = this.createContext();

  let currentMessages = structuredClone(messages);

  for (const ext of this.extensions) {

    const handlers = ext.handlers.get("context");

    if (!handlers || handlers.length === 0) continue;

    for (const handler of handlers) {
      try {

        const event: ContextEvent = { type: "context", messages: currentMessages };

        const handlerResult = await handler(event, ctx);

        if (handlerResult && (handlerResult as ContextEventResult).messages) {

          currentMessages = (handlerResult as ContextEventResult).messages!;
        }
      } catch (err) {

        const message = err instanceof Error ? err.message : String(err);
        const stack = err instanceof Error ? err.stack : undefined;
        this.emitError({
          extensionPath: ext.path,
          event: "context",
          error: message,
          stack,
        });
      }
    }
  }

  return currentMessages;
}
```

811 行先 structuredClone 输入消息，得到本次处理的副本。每个 handler 接收 `{ type: "context", messages: currentMessages }` 和 ExtensionContext；返回 `{ messages: ... }` 时，外层 currentMessages 改用新数组，后一位 handler 再处理这个结果。空数组也会生效。

最后返回的是 AgentMessage[] 本身。它交回 loop 中的局部 messages，再进入 convertToLlm，没有自动写回 Agent 历史或 SessionManager。

### 8.2 返回数组、修改数组和改 event 字段的区别

| handler 中的动作 | 对后续 context 处理的影响 |
| --- | --- |
| `return { messages: newArray }` | 外层 currentMessages 改为 newArray |
| `event.messages.push(M)` | 修改当前副本数组，后续 handler 能看到 |
| `event.messages = newArray`，不返回 | 只改变本次 event 的字段，不重新赋值外层 currentMessages |

例如，过滤专门用于界面提示的 custom 消息：

```ts
pi.on("context", async (event) => ({
  messages: event.messages.filter(
    (message) => !(message.role === "custom" && message.customType === "ui-note"),
  ),
}));
```

假设输入 `[U, Custom(ui-note), A, R]`，返回 `[U,A,R]`。该例只过滤指定应用消息，保留已有助手调用与工具结果的对应关系。原 Agent 历史中的 ui-note 仍然存在。

开始时的一次 structuredClone 不等于每位 handler 都获得独立副本。后面的处理器继续使用前面留下的 currentMessages；若处理器抛错前已经就地修改副本，catch 也不会自动回滚这些修改。

### 8.3 tool_call 与 tool_result 的不同来源

第 07 章已分析工具执行，本节只把等待链与事件数据对齐：

```text
prepareToolCall：await config.beforeToolCall(...)
  → AgentSession安装的前置函数
  → 有tool_call处理器时，先await当时的_agentEventQueue
  → await runner.emitToolCall({type:"tool_call", input:args, ...})
  ← block/reason交回准备分支

finalizeExecutedToolCall：await config.afterToolCall(...)
  → AgentSession安装的后置函数
  → await runner.emitToolResult({type:"tool_result", content, details, isError, ...})
  ← 覆盖字段交回最终工具结果
```

前置桥的完整位置是 [agent-session.ts:382](/source/?file=24209413646c397dc9.ts#L382)，其中 [agent-session.ts:389](/source/?file=24209413646c397dc9.ts#L389) 特别等待会话队列；后置桥 [agent-session.ts:407](/source/?file=24209413646c397dc9.ts#L407) 没有相同等待语句。两者都等待自己的扩展 handler，但不能把前置的队列屏障推广到所有扩展钩子。

| 名称 | 参数来源与含义 | 能改变什么 |
| --- | --- | --- |
| tool_execution_start.args | 原 ToolCall.arguments | 通知中的原始参数 |
| tool_call.input | 准备、校验之后的 args | 返回 block/reason 可阻止执行；参数对象仍可能共享 |
| tool_execution_update.partialResult | 工具 onUpdate 提交的对象 | 阶段通知，不自动累计最终正文 |
| tool_result.content/details/isError | execute 后的结果 | 返回字段覆盖最终工具结果 |
| ToolResultMessage | 最终结果包装出的消息 | 进入历史与下一次模型输入 |

tool_call handler 抛错会传播到工具准备层，形成错误结果；准备失败或被阻止会跳过 execute 与 after，因此仍有工具结束通知和结果消息，却没有该项的扩展 tool_result。真实 execute 抛错后形成的结果则仍会进入后置处理。

### 8.4 其他返回值也由具体派发函数解释

| 事件 | 实际处理函数 | 返回约定的重点 |
| --- | --- | --- |
| input | [runner.ts:1006](/source/?file=1a64f1a2d3fca70128.ts#L1006) emitInput | continue/transform/handled；transform 逐步更新输入，handled 提前结束 |
| before_agent_start | [runner.ts:889](/source/?file=1a64f1a2d3fca70128.ts#L889) emitBeforeAgentStart | 附加 message 被收集；systemPrompt 在处理器之间传递 |
| before_provider_request | [runner.ts:854](/source/?file=1a64f1a2d3fca70128.ts#L854) emitBeforeProviderRequest | 非 undefined 返回值作为新 payload；不是固定的 `{payload:...}` 包装 |
| user_bash | [runner.ts:791](/source/?file=1a64f1a2d3fca70128.ts#L791) emitUserBash | 第一个有效返回对象交给调用方，提供 operations 或 result |
| resources_discover | [runner.ts:956](/source/?file=1a64f1a2d3fca70128.ts#L956) emitResourcesDiscover | 汇总 skillPaths、promptPaths、themePaths |

这些函数的位置说明“读取返回值”不是 pi.on 登记时统一完成的动作。handler 被谁调用、返回值如何合并或短路，都由具体派发函数决定。深入这些功能时，应从对应调用点进入，读完返回原操作，不把它们接成一次模型运行必经的连续链。

**到这里先记住：**

- 生命周期 handler 通常由会话队列等待；context 等钩子直接由模型或工具路径等待。
- context 处理的是 AgentMessage[]，随后才转换成标准 Message[]。
- 同样由 pi.on 登记，不代表返回值、异常传播或队列等待方式相同。

<a id="x-messages-09"></a>

## 9. 自定义消息怎样产生、排队与发出通知

coding-agent 提供 sendCustomMessage，让应用把 custom 消息交给会话。它既可以触发模型，也可以只保存消息，还可以把消息留给之后的输入。这里必须按实际分支判断：同一消息类型并不只有一种事件来源。

### 9.1 先补成 CustomMessage，再选择去向

源码摘录：[agent-session.ts:1306](/source/?file=24209413646c397dc9.ts#L1306)，第 1306—1339 行。

```ts
async sendCustomMessage<T = unknown>(
  message: Pick<CustomMessage<T>, "customType" | "content" | "display" | "details">,
  options?: { triggerTurn?: boolean; deliverAs?: "steer" | "followUp" | "nextTurn" },
): Promise<void> {

  const appMessage = {
    role: "custom" as const,
    customType: message.customType,
    content: message.content,
    display: message.display,
    details: message.details,
    timestamp: Date.now(),
  } satisfies CustomMessage<T>;
  if (options?.deliverAs === "nextTurn") {

    this._pendingNextTurnMessages.push(appMessage);
  } else if (this.isStreaming) {

    if (options?.deliverAs === "followUp") {
      this.agent.followUp(appMessage);
    } else {
      this.agent.steer(appMessage);
    }
  } else if (options?.triggerTurn) {

    await this.agent.prompt(appMessage);
  } else {

    this.agent.state.messages.push(appMessage);
    this.sessionManager.appendCustomMessageEntry(
      message.customType,
      message.content,
      message.display,
      message.details,
    );
    this._emit({ type: "message_start", message: appMessage });
    this._emit({ type: "message_end", message: appMessage });
  }
}
```

调用方提供 customType、content、display 与可选 details；方法补上 role 和 timestamp。它随后按下面的优先级选择路径：

| 判断条件 | 当下做什么 | 何时进入 Agent 历史 |
| --- | --- | --- |
| deliverAs 为 nextTurn | 放入 `_pendingNextTurnMessages` | 后续 Session.prompt 组装输入并由 Agent 消费时 |
| 否则，会话正在运行 | followUp 选 Agent.followUp，其余选 Agent.steer | 循环后来注入消息并处理 message_end 时 |
| 否则，triggerTurn 为真 | await Agent.prompt(appMessage) | 该次运行处理提示消息时 |
| 其余空闲情况 | 直接追加 Agent 历史和会话记录，再通知普通会话 listener | 就在这个函数内 |

前两个分支当下没有发 message_start/end，也没有在这里追加消息记录。`triggerTurn: true` 不能越过优先判断的 nextTurn 或运行中分支。

### 9.2 nextTurn 在哪里被取出

名称中的 turn 容易与 Agent Loop 内部 turn 混淆。这个数组的消费位置是 Session.prompt 组装新输入的阶段：

源码摘录：[agent-session.ts:1087](/source/?file=24209413646c397dc9.ts#L1087)，第 1087—1090 行。

```ts
for (const msg of this._pendingNextTurnMessages) {
  messages.push(msg);
}
this._pendingNextTurnMessages = [];
```

因此，nextTurn 等的是后续 Session.prompt 到达这个组装位置，不是让当前 runLoop 在执行完一批工具后自动取出它。它与 Agent 的 steering/follow-up 队列是不同容器。

消费 pending 数组之前，Session.prompt 已经把这次输入放进 messages。将前后语句连起来看：

源码摘录：[agent-session.ts:1071](/source/?file=24209413646c397dc9.ts#L1071)，第 1071—1090 行。

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
for (const msg of this._pendingNextTurnMessages) {
  messages.push(msg);
}
this._pendingNextTurnMessages = [];
```

例如，先调用 `sendCustomMessage(C, { deliverAs: "nextTurn" })`，后面再提交一条普通用户输入 U；假设输入未被命令或 input 钩子提前处理，后续钩子也没有附加消息：

| 执行位置 | `_pendingNextTurnMessages` | 本次 prompt 的局部 messages | Agent 历史 |
| --- | --- | --- | --- |
| sendCustomMessage 入队后 | `[C]` | 尚未组装 | 尚未加入 C |
| 其间原 runLoop 因工具进入下一 turn | `[C]` | 尚未组装 | 仍不会仅因此加入 C |
| 后续 Session.prompt 的 1041 行 | `[C]` | `[U]` | 新输入尚未通过 Agent.prompt 消费 |
| 1048—1051 行 | `[]` | `[U,C]` | 同上 |
| 后面调用 Agent.prompt | `[]` | `[U,C]` 交给 Agent | 经各自 message_end 追加 U、C |

C 是 sendCustomMessage 补齐 role 和 timestamp 后的 CustomMessage。U 排在 C 前面，由这两次 push 的先后决定；它们不是按原来提交的时间戳重新排序。若 `before_agent_start` 另外返回附加消息，1061—1069 行还会把它们继续放到 C 后面。

选择 steer/followUp 的自定义消息会进入 Agent 队列，但没有经过会话文字显示队列的维护函数，因此不会自动产生 queue_update。nextTurn 则保存在另一份 `_pendingNextTurnMessages` 中。

### 9.3 空闲且不触发运行：记录先于通知

假设会话空闲，调用：

```ts
await session.sendCustomMessage({
  customType: "course-note",
  content: "下一次回答请使用中文。",
  display: false,
  details: { source: "application" },
});
```

它走函数最后的直接追加分支：

```text
创建 appMessage
  → Agent.state.messages.push(appMessage)
  → SessionManager.appendCustomMessageEntry(...)
  → Session._emit(message_start)
  → Session._emit(message_end)
```

这条路径不启动 Agent，没有 agent_start、turn_start，也没有经过 Agent.processEvents 和扩展生命周期桥。因此，普通 session.subscribe 能收到这两条消息通知，`pi.on("message_end")` 却不会仅因这条直接分支自动被调用。

它与第 6 节正常 message_end 的顺序恰好不同：正常路径先通知普通会话监听器，再追加记录；这里先调用追加记录，再通知。准确判断应从事件生产位置出发，不能只根据 type 字符串概括所有路径。

### 9.4 pi.sendMessage 为什么不能用 await 等模型结束

扩展 API 的入口只是转发：

源码摘录：[loader.ts:261](/source/?file=d170abdf93d664a78b.ts#L261)，第 261—264 行。

```ts
sendMessage(message, options): void {
  runtime.assertActive();
  runtime.sendMessage(message, options);
},
```

会话绑定的函数如下：

源码摘录：[agent-session.ts:2216](/source/?file=24209413646c397dc9.ts#L2216)，第 2216—2224 行。

```ts
sendMessage: (message, options) => {
  this.sendCustomMessage(message, options).catch((err) => {
    runner.emitError({
      extensionPath: "<runtime>",
      event: "send_message",
      error: err instanceof Error ? err.message : String(err),
    });
  });
},
```

它启动 sendCustomMessage，附加错误报告，然后返回 void。没有把内部 Promise return 出去。因此，即使写 `await pi.sendMessage(...)`，也不会等待内部可能启动的模型运行。

直接调用 `await session.sendCustomMessage(...)` 则等待该方法选择的分支：如果只是排队，等待到入队完成；如果调用 Agent.prompt，等待那次 Agent 运行。它仍不因此保证普通会话订阅者的后台任务和整个会话事件队列全部完成。

<a id="x-messages-10"></a>

## 10. pi.events：扩展之间的独立事件总线

扩展除了响应宿主事件，也可能需要在彼此之间交换自定义数据。pi.events 提供字符串频道与 unknown 数据的接口，它和 pi.on 保存的生命周期 handlers 表没有自动连接。

### 10.1 总线的生产者与消费者

源码摘录：[event-bus.ts:1](/source/?file=6982c4638dc60fbe73.ts#L1)，第 1—36 行。

```ts
import { EventEmitter } from "node:events";

export interface EventBus {
  emit(channel: string, data: unknown): void;
  on(channel: string, handler: (data: unknown) => void): () => void;
}

export interface EventBusController extends EventBus {
  clear(): void;
}

export function createEventBus(): EventBusController {
  const emitter = new EventEmitter();
  return {
    emit: (channel, data) => {
      emitter.emit(channel, data);
    },
    on: (channel, handler) => {
      const safeHandler = async (data: unknown) => {
        try {
          await handler(data);
        } catch (err) {
          console.error(`Event handler error (${channel}):`, err);
        }
      };
      emitter.on(channel, safeHandler);
      return () => emitter.off(channel, safeHandler);
    },
    clear: () => {
      emitter.removeAllListeners();
    },
  };
}
```

`createEventBus()` 创建一个 Node EventEmitter，并返回 emit、on、clear。扩展 API 暴露的是 EventBus 的 emit/on，位置在 [loader.ts:341](/source/?file=d170abdf93d664a78b.ts#L341)；clear 属于控制器接口。

on 为外部 handler 创建 safeHandler，保存的是这个包装函数。返回的取消函数移除同一个 safeHandler。emit 则调用 emitter.emit 并返回 void。

### 10.2 safeHandler 有 await，外层 emit 仍不等待

```text
pi.events.emit(channel, data)
  → EventEmitter 调用各 safeHandler(data)
      → 调用外部 handler(data)
      → safeHandler 内等待并捕获处理器错误
  → emit 不收集这些 Promise，返回 void
```

safeHandler 内的 await 负责把异步拒绝纳入 catch，不会使外层 emit 变成可等待的整体完成结果。多个 handler 的异步工作可以重叠；移除登记也不会取消已经开始的工作。

例如，两个扩展约定使用 `course:progress` 频道，就可以通过该频道传递 `{ completed: 1 }`。这个名称由扩展自行约定，属于总线数据；它不是 AgentEvent 或 ExtensionEvent 中新增的正式 type。

一次最小的登记、发送和取消可以直接使用这三个方法：

```ts
const received: unknown[] = [];
const off = pi.events.on("course:progress", (data) => {
  received.push(data);
});

pi.events.emit("course:progress", { completed: 1 });
off();
pi.events.emit("course:progress", { completed: 2 });
```

这里的 pi 来自扩展工厂。第一个 emit 调用 safeHandler，再同步进入外部 handler，完成 push；第二个 emit 发生在取消登记之后，因此不会再调用这位 handler。按这段代码的先后，received 最终只有 `[{ completed: 1 }]`。总线传递的是原 data，未做消息包装，也没有自动深复制它。

这个例子选择同步 handler，所以 push 在 emit 返回前发生。若外部 handler 先 `await someWork()` 再 push，push 就不属于 emit 的同步完成范围。两次发送都不会自动追加 AgentMessage，也不会触发 pi.on 的登记表；需要写入消息时，接收方必须显式调用相应消息 API。

| 写法 | 保存位置 | 由谁触发 |
| --- | --- | --- |
| `pi.on("message_end", handler)` | 扩展自己的 handlers Map | 宿主生命周期桥与 runner |
| `pi.events.on("course:progress", handler)` | EventEmitter 中的 safeHandler | 对同一总线调用 events.emit 的代码 |
| `agent.subscribe(listener)` | Agent 的 Set | Agent.processEvents |
| `session.subscribe(listener)` | AgentSession 的数组 | AgentSession._emit |

即使用 `pi.events.emit("agent_end", data)`，触发的也是总线上的同名频道，不会自动进入 `pi.on("agent_end")` 的 handlers 表。事件名相同不足以确定它属于哪条调用关系。

<a id="x-messages-11"></a>

## 11. 自己添加消息和订阅处理

扩展消息需要同时解决两件事：让应用能够保存它，并规定模型该读到什么。下面分别使用独立 Agent 的新角色，以及编码会话已有的 custom 角色。两个例子是替代接入方式，不要求组合到同一个程序里。

### 11.1 独立 Agent：新角色与模型转换一起定义

下面是完整模块示例。模型与凭据由调用方提供，沿用第 05 章的配置方式：

```ts
import { Agent, type AgentMessage } from "@mariozechner/pi-agent-core";
import type { Api, Message, Model } from "@mariozechner/pi-ai";

interface CourseNote {
  role: "courseNote";
  text: string;
  timestamp: number;
}

declare module "@mariozechner/pi-agent-core" {
  interface CustomAgentMessages {
    courseNote: CourseNote;
  }
}

function convertCourseMessages(messages: AgentMessage[]): Message[] {
  return messages.flatMap((message): Message[] => {
    switch (message.role) {
      case "courseNote":
        return [{
          role: "user",
          content: [{ type: "text", text: `补充说明：${message.text}` }],
          timestamp: message.timestamp,
        }];
      case "user":
      case "assistant":
      case "toolResult":
        return [message];
      default:
        return [];
    }
  });
}

export async function runWithNote(model: Model<Api>, apiKey: string) {
  const agent = new Agent({
    initialState: { model },
    getApiKey: () => apiKey,
    convertToLlm: convertCourseMessages,
  });

  const completedRoles: string[] = [];
  const unsubscribe = agent.subscribe((event) => {
    if (event.type === "message_end") {
      completedRoles.push(event.message.role);
    }
  });

  try {
    await agent.prompt([
      { role: "courseNote", text: "使用简洁中文。", timestamp: Date.now() },
      { role: "user", content: "解释 Message 与 Event 的区别。", timestamp: Date.now() },
    ]);
    return { messages: agent.state.messages, completedRoles };
  } finally {
    unsubscribe();
  }
}
```

CourseNote 的字段由示例自行定义，前面标准 Message 并没有这个角色。声明合并让它进入 AgentMessage；真正的转换发生在 convertCourseMessages 被模型请求阶段调用时。

```text
Agent历史中的输入：
  [courseNote("使用简洁中文。"), user("解释区别")]

此次模型请求中的输入：
  [user("补充说明：使用简洁中文。"), user("解释区别")]
```

转换没有把历史中的 courseNote 改成 user。正常响应完成后，Agent 历史仍保存原输入，再追加助手消息；completedRoles 可以观察到消息结束顺序。如果正常得到一条助手回复，数组依次为 courseNote、user、assistant。

flatMap 允许每条输入返回零条、一条或多条模型消息。该示例的 default 明确过滤不支持的其他角色；如果同一应用还加入别的消息类型，应为它们补上转换规则。直接使用 Agent 默认转换时，courseNote 会被过滤，因此“定义了类型”与“模型实际能看到内容”需要一起实现。

### 11.2 编码会话：使用已有 custom，不必再声明新 role

下面是一个完整扩展入口。`course-note` 是用户命令名，`course-note` 与 `ui-note` 则是这个扩展约定的 customType 值：

```ts
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export default function courseMessages(pi: ExtensionAPI) {
  pi.registerCommand("course-note", {
    description: "为后续输入附加一条课程提示",
    handler: async (args) => {
      pi.sendMessage({
        customType: "course-note",
        content: args || "回答时说明关键数据从哪里来、交给谁。",
        display: false,
      }, { deliverAs: "nextTurn" });
    },
  });

  pi.on("context", async (event) => ({
    messages: event.messages.filter(
      (message) => !(message.role === "custom" && message.customType === "ui-note"),
    ),
  }));
}
```

命令 handler 收到命令参数后，调用 pi.sendMessage，把 course-note 暂存为下一次 Session.prompt 的输入材料；它没有在命令中立即请求模型。后续输入进入 Agent 时，该 custom 消息照常参与事件和历史；模型请求前，context 处理器只过滤 ui-note，course-note 会继续由 coding-agent 的 convertToLlm 转成 user。

因此，两种自定义消息在这里有明确区别：course-note 的正文交给模型，即使 display 为 false；ui-note 则被这个扩展的 context 规则从本次模型输入中过滤。customType 只是应用分类，具体行为由这些显式判断赋予。

registerCommand 的公开签名见 [types.ts:1125](/source/?file=baffea2d47e73908cd.ts#L1125)，其 options 省略了登记时补入的 name 和 sourceInfo；handler 的结构见 [types.ts:1044](/source/?file=baffea2d47e73908cd.ts#L1044)，扩展工厂签名见 [types.ts:1357](/source/?file=baffea2d47e73908cd.ts#L1357)。扩展工厂的登记与加载见[选读《Pi 技能与扩展源码解析》第 4—5 节](/openclaw/skills-extensions#x-skills-04)，命令调用见[该讲义第 7.1 节](/openclaw/skills-extensions#x-skills-command)。这个例子只扩充消息处理，不定义模型工具，也不把命令执行称为 ToolCall。

### 11.3 让 Agent 等待自己的订阅工作

一个独立的订阅函数可以明确表达它承诺的等待范围：

```ts
import type { Agent, AgentEvent } from "@mariozechner/pi-agent-core";

export function attachRecorder(
  agent: Agent,
  record: (event: AgentEvent) => Promise<void>,
): () => void {
  return agent.subscribe(async (event) => {
    await record(event);
  });
}
```

调用方提供 record，保存返回的取消函数，在不需要监听时调用它。因为 record 的 Promise 被 listener 返回链包含，Agent 的事件处理会等待它。若同样的 async 函数登记到 session.subscribe，Session._emit 并不会自动等待，因此不能只替换对象名就假设等待约定相同。

这个等待也影响运行推进速度：message_update 上的慢记录动作会延后当前事件处理的完成。是否在每个增量上执行昂贵操作，应由应用按需要选择；一旦改为后台排队，完成保证也要由应用另外表达。

### 11.4 订阅会话通知，并处理自己的异步工作

会话普通订阅适合观察已转发的消息通知和会话专有通知。下面的函数由持有 session 的应用调用，返回观察数据与取消函数：

```ts
import type { AgentMessage } from "@mariozechner/pi-agent-core";
import type { AgentSession } from "@mariozechner/pi-coding-agent";

export function observeSession(session: AgentSession) {
  const completed: AgentMessage[] = [];
  const queueSizes: { steering: number; followUp: number }[] = [];
  const unsubscribe = session.subscribe((event) => {
    if (event.type === "message_end") {
      completed.push(structuredClone(event.message));
    } else if (event.type === "queue_update") {
      queueSizes.push({
        steering: event.steering.length,
        followUp: event.followUp.length,
      });
    }
  });
  return { completed, queueSizes, unsubscribe };
}
```

例如，`const observed = observeSession(session)` 完成登记；每次收到 message_end，completed 才追加一条快照。收到 `{ type: "queue_update", steering: ["补充要求"], followUp: [] }` 时，queueSizes 追加 `{ steering: 1, followUp: 0 }`。调用 `observed.unsubscribe()` 后，停止接收后续通知，已经保存的数组内容仍由应用持有。

这里使用 structuredClone，是为了在收到事件时保存消息数据。它的时间基准是“会话 listener 收到通知”，不是更早的模型增量生成时刻。queueSizes 只记录会话报告的显示队列长度；其含义仍遵循第 6.5 节，不能据此推断 Agent 队列中恰好有同样数量的消息。

如果观察动作还要调用异步写入函数，应同时处理它返回的 Promise。以下辅助函数明确采用后台记录，record 与 reportError 都由应用提供：

```ts
import type { AgentSession, AgentSessionEvent } from "@mariozechner/pi-coding-agent";

export function attachSessionRecorder(
  session: AgentSession,
  record: (event: AgentSessionEvent) => Promise<void>,
  reportError: (error: unknown) => void,
): () => void {
  return session.subscribe((event) => {
    const snapshot = structuredClone(event);
    void Promise.resolve()
      .then(() => record(snapshot))
      .catch(reportError);
  });
}
```

Promise.then 启动记录，使 record 的同步异常和异步拒绝都进入 catch；Session._emit 仍只等到 listener 的同步部分返回。不同事件的记录可能并行完成，取消登记也不会取消已经启动的记录。如果应用要求有序写入或等待全部写入完成，就需要自行保存任务、串联队列并提供相应的完成 Promise；Session 普通订阅没有替应用完成这些工作。

与第 11.3 节对照：Agent 记录器返回 record 的等待链，Agent.processEvents 会等待；会话后台记录器自行接住错误，Session._emit 不等待记录。两者不能只凭 callback 都使用 async 或 Promise 就视作相同契约。

**到这里先记住：**

- 新角色需要类型声明、对象创建和模型转换三部分；它们分别解决不同问题。
- coding-agent 的 custom 已提供通用容器，customType 便于应用决定显示与转换策略。
- 等待自己的异步工作，需要把相应 Promise 放进真正被调用方等待的返回链。

<a id="x-messages-12"></a>

## 12. 用短时间线核对消息、通知与完成边界

消息已经形成、通知已经发出、监听器已经完成、会话记录已经追加，是不同的观察点。下面把几条常见路径放在一起对照，避免只用一个“结束”概括所有工作。

### 12.1 正常助手消息：哪些先后关系可以确定

假设直接 Agent 的普通事件处理不抛错，助手正常返回 A：

```text
模型终态 → response.result() 得 A
  → 替换 currentContext 中的助手位置
  → await emit(message_end(A))
      → Agent.state.messages 加入 A
      → 按序调用、等待 Agent listener
  → streamAssistantResponse 返回 A
  → runLoop 把 A 加入 newMessages
  → 继续工具判断或本轮收尾
```

若 listener 是 AgentSession._handleAgentEvent，等待只到该回调入队返回。会话中的扩展通知、普通监听器和记录追加，继续沿会话队列处理。

### 12.2 工具进度：发出 update 不等于写入结果消息

```text
tool.execute 调用 onUpdate(P)
  → 立即 emit(tool_execution_update，partialResult=P)
  → 执行层收集这个 emit 返回的 Promise
  → 工具继续工作
工具 Promise 完成
  → 执行层等待已报告的 update Promise
  → afterToolCall
  → tool_execution_end
  → 创建并发出 ToolResultMessage 的消息事件
  → 批次返回后追加循环上下文
```

工具进度的等待范围仍由 emit 返回链决定。即使执行层等过 update Promise，也不能据此认定会话队列中的全部进度显示已完成。进度对象不会被自动追加到 messages，最终消息来自工具 return 和后置处理。

### 12.3 正常模型 error 与外壳异常是两条路径

| 情况 | 消息与事件怎样处理 |
| --- | --- |
| pi-ai 返回 error 终态 | streamAssistantResponse 取得最终助手消息，发 message_end；runLoop 发 turn_end 与 agent_end |
| Agent 外壳捕获未按模型流协议交付的异常 | [agent.ts:488](/source/?file=3688aa044ebb960834.ts#L488) 创建失败助手消息，636 直接追加状态，638 只调用 processEvents(agent_end) |

第二条路径没有补齐 message_start/message_end/turn_end。因此，message_end 是正常流路径中完成消息进入 Agent 历史的位置，但不是所有状态写入的唯一入口。自定义消息直接追加也已在第 9 节展示。

### 12.4 等待与完成关系对照

| 调用位置 | 等待什么 | 不由这句保证的工作 |
| --- | --- | --- |
| `await streamFunction(...)` | 取得模型事件流对象，兼容异步返回流的函数 | 整条助手消息尚需消费事件或等待 result |
| `await response.result()` | 一次模型响应的最终 AssistantMessage | 工具执行、整个 Agent run |
| Agent `await listener(event, signal)` | listener 返回的 Promise | listener 未返回的后台任务 |
| Session `_handleAgentEvent` | 本身同步入队，返回 void | `_agentEventQueue` 中该事件的全部处理 |
| Session `_emit` | 同步调用普通 listener | async listener 的后续 Promise |
| runner 的生命周期 emit | 本次派发中的 handler Promise | Agent 主循环是否等这次派发，取决于上层返回链 |
| runner.emitContext | 本次 context handlers，并返回最终数组 | 自动改写或保存原历史 |
| `pi.events.emit` | 启动总线监听函数的调用 | 全部异步处理器完成 |
| `pi.sendMessage` | 启动转发或入队动作，返回 void | 内部可能启动的模型运行 |

`agent_end` 在 Agent 的 finishRun 之前发出。正常 `Agent.prompt()` 等到所需事件处理与运行清理，`waitForIdle()` 则等待该 Agent 的活动运行结束。它们不包含 listener 未返回的工作。

AgentSession.prompt 在 [agent-session.ts:1131](/source/?file=24209413646c397dc9.ts#L1131) 等 Agent.prompt，然后在 1104 等 waitForRetry。后者定义于 [agent-session.ts:2587](/source/?file=24209413646c397dc9.ts#L2587)，涉及已有重试 Promise 与 Agent 空闲；这些位置没有等待整个 `_agentEventQueue`。因此 session.prompt 返回也不能被当作所有会话监听任务、记录或渲染都已完成的统一信号。

<a id="x-messages-13"></a>

## 13. 跟着 IDE 阅读消息与事件源码

阅读时可以从一条用户输入开始，先走到模型消息和 Agent 状态，再沿订阅进入会话。自定义消息与扩展钩子作为有明确出发点和返回点的支线加入，不需要先通读完整 AgentSession。

### 13.1 Step 1：确认正在读的是消息、块还是事件

**【打开】** [types.ts:195](/source/?file=a8f4ce943bcfc7dd27.ts#L195) 的 UserMessage。接着看 201 的 AssistantMessage、214 的 ToolResultMessage 和 224 的 Message 联合。

**【跳转定义】** content 中遇到 TextContent、ThinkingContent、ImageContent、ToolCall，分别到 [types.ts:148](/source/?file=a8f4ce943bcfc7dd27.ts#L148)、[types.ts:154](/source/?file=a8f4ce943bcfc7dd27.ts#L154)、[types.ts:164](/source/?file=a8f4ce943bcfc7dd27.ts#L164)、[types.ts:170](/source/?file=a8f4ce943bcfc7dd27.ts#L170)。只看 type 和必需字段，返回原角色的 content 联合，核对它允许哪些块。

**【停止下钻】** Model、Usage 和 Provider 协议已在第 05 章说明；这里保留它们作为消息字段的用途即可。

**【继续】** 打开 [types.ts:255](/source/?file=d51aa2ef0fa6575e26.ts#L255) 的 AgentMessage；到 246 确认开放的 CustomAgentMessages。应用扩展的具体角色留到 Step 6。实际主线从 [agent.ts:335](/source/?file=3688aa044ebb960834.ts#L335) 的 prompt 开始。

### 13.2 Step 2：从 prompt 跟到消息数组与第一条事件

在 [agent.ts:341](/source/?file=3688aa044ebb960834.ts#L341) 遇到 normalizePromptInput，跳到 [agent.ts:376](/source/?file=3688aa044ebb960834.ts#L376)，看数组、单条消息和字符串三个分支；字符串在 386—384 生成 UserMessage。

**【返回主线】** 回 340 得到 messages，继续 341 → [agent.ts:396](/source/?file=3688aa044ebb960834.ts#L396)。398 调 runAgentLoop，400 的 createContextSnapshot 跳到 [agent.ts:425](/source/?file=3688aa044ebb960834.ts#L425)，只看 424 复制旧消息数组；回 400 后进入 [agent-loop.ts:96](/source/?file=6adbf9ab77a3572a2f.ts#L96)。

**【只看数组】** 103 创建 newMessages，133—136 创建 currentContext，135 合并旧历史与 prompts。138—156 创建开始与提示消息事件。

**【遇到 emit】** 记住原事件语句，可以使用 Step 4 的规则短跳；看完回事件的 await 后继续。初始消息事件处理完成后，159 才进入 runLoop。

### 13.3 Step 3：一次模型输入与输出怎样改变消息

**【打开】** [agent-loop.ts:237](/source/?file=6adbf9ab77a3572a2f.ts#L237)，进入 [agent-loop.ts:288](/source/?file=6adbf9ab77a3572a2f.ts#L288)。先读 310—323：局部 messages → transformContext → convertToLlm → llmContext。

**【暂定边界】** 直接 Agent 的 convertToLlm 来源在 [agent.ts:40](/source/?file=3688aa044ebb960834.ts#L40)；编码会话的转换见 Step 6。第一次先记住此处必须得到标准 Message[]，再继续 337 的 streamFunction 调用。

取得 response 后看 [agent-loop.ts:350](/source/?file=6adbf9ab77a3572a2f.ts#L350) 的 for await：347—352 追加助手消息并发 start，354—372 把九种内容事件转成 message_update，374—386 取得最终消息并返回。

**【查事件字段】** text_delta 到 [types.ts:251](/source/?file=a8f4ce943bcfc7dd27.ts#L251)，toolcall_end 到 [types.ts:258](/source/?file=a8f4ce943bcfc7dd27.ts#L258)，done/error 到 [types.ts:259](/source/?file=a8f4ce943bcfc7dd27.ts#L259)。确认 partial、delta、toolCall、message、error 各装什么后，立即回对应 case。

**【返回主线】** 386 返回后回 235，继续 236 加入 newMessages。若产生工具，消息创建点在 [agent-loop.ts:761](/source/?file=6adbf9ab77a3572a2f.ts#L761)，消息通知在 [agent-loop.ts:773](/source/?file=6adbf9ab77a3572a2f.ts#L773)；工具内部执行回查第 07 章，不再从这里进入文件操作实现。

### 13.4 Step 4：追 emit 的实际函数与状态变化

**【来源】** 类型 [agent-loop.ts:25](/source/?file=6adbf9ab77a3572a2f.ts#L25) 只规定函数签名；Agent 路径实际函数值在 [agent.ts:405](/source/?file=3688aa044ebb960834.ts#L405)，是 `(event) => this.processEvents(event)`。

**【跳转定义】** 到 [agent.ts:520](/source/?file=3688aa044ebb960834.ts#L520)。先读与当前事件对应的 switch，尤其 524—527 的 message_end；再读 554—559，确认 signal 来源与 listener 的 await。

**【listener 从哪里来】** 到 [agent.ts:237](/source/?file=3688aa044ebb960834.ts#L237) 的 subscribe，看函数进入 Set 与取消函数的返回。Set 的字段创建在 [agent.ts:176](/source/?file=3688aa044ebb960834.ts#L176)。

**【返回主线】** 看完回原来的 emit 位置。例如助手终态从 [agent-loop.ts:390](/source/?file=6adbf9ab77a3572a2f.ts#L390) 发出，就回 385 的 await 后读 386；工具消息从 762 发出，helper 完成后回串行批次的 [agent-loop.ts:488](/source/?file=6adbf9ab77a3572a2f.ts#L488) 或并行批次的 [agent-loop.ts:551](/source/?file=6adbf9ab77a3572a2f.ts#L551)，继续下一行的结果收集。事件通知不会重新启动一个 turn。

### 13.5 Step 5：把 Agent 的 listener 追到会话队列

**【打开】** [agent-session.ts:331](/source/?file=24209413646c397dc9.ts#L331)，确认登记的是 `_handleAgentEvent`。跳到 [agent-session.ts:459](/source/?file=24209413646c397dc9.ts#L459)，看 460 的重试准备和 462—465 的 then；再看函数返回类型 void。

**【队列来源】** 字段在 [agent-session.ts:252](/source/?file=24209413646c397dc9.ts#L252) 初始化。这里无需进入 Promise 库内部，只需理解 then 返回的新 Promise 成为下一个事件的前序任务。

**【继续到消费位置】** 从 then 回调进入 [agent-session.ts:508](/source/?file=24209413646c397dc9.ts#L508) 的 `_processAgentEvent`。504—522 处理用户消息对应的显示队列，随后重点按 525 → 528 → 531—548 的顺序读。

| 遇到的调用 | 跳转与阅读重点 | 返回位置 |
| --- | --- | --- |
| 518 `_emitExtensionEvent` | [agent-session.ts:628](/source/?file=24209413646c397dc9.ts#L628)，看消息/工具/turn 字段怎样组成扩展事件；处理器调用见 Step 7 | 回 525 的 await 后，继续 528 |
| 521 `_emit` | [agent-session.ts:440](/source/?file=24209413646c397dc9.ts#L440)，确认直接 l(event)；登记来源 [agent-session.ts:705](/source/?file=24209413646c397dc9.ts#L705) 是数组 push | 回 528，继续 531 |
| 540 `appendMessage` | [session-manager.ts:860](/source/?file=043f6d188e65e3207b.ts#L860)，看记录补 id/parentId/timestamp 并保存 message | 回 545，记录格式边界到此为止 |
| 528 `appendCustomMessageEntry` | [session-manager.ts:976](/source/?file=043f6d188e65e3207b.ts#L976)，看 custom 消息专用条目 | 回 533 调用结束位置，再继续本事件处理 |

**【核对队列等待】** 返回 455—458 行，观察两个箭头函数都把 `_processAgentEvent` 的返回值交给 then；不要把这里与外层 `_handleAgentEvent` 的 void 返回混在一起。第 6.1 节的时间表对应这两个返回边界。普通会话订阅的使用可对照第 11.4 节：listener 同步收集数据后返回，后台记录的 Promise 不会在 431 行被等待。

**【停止下钻】** SessionManager 的文件布局、分支选择、压缩与重试算法属于各自功能。这里确认“通知在追加记录之前”以及函数没有等待普通监听器 Promise 即可。

### 13.6 Step 6：应用消息怎样回到模型输入

**【打开】** [messages.ts:29](/source/?file=2d4c32a97bc465b1f2.ts#L29) 到 77，按四种角色和声明合并理解应用消息。需要找生产者时，custom 到 [agent-session.ts:1306](/source/?file=24209413646c397dc9.ts#L1306)，bashExecution 到 [agent-session.ts:2659](/source/?file=24209413646c397dc9.ts#L2659)；摘要只看 [messages.ts:100](/source/?file=2d4c32a97bc465b1f2.ts#L100) 与 [messages.ts:109](/source/?file=2d4c32a97bc465b1f2.ts#L109) 的构造和 [session-manager.ts:394](/source/?file=043f6d188e65e3207b.ts#L394)、[session-manager.ts:400](/source/?file=043f6d188e65e3207b.ts#L400) 的调用。

**【回到模型请求】** 从 [agent-loop.ts:320](/source/?file=6adbf9ab77a3572a2f.ts#L320) 追 convertToLlm 的实际配置。SDK 在 [sdk.ts:315](/source/?file=07502145bf1ffa712b.ts#L315) 指定 convertToLlmWithBlockImages，定义在 [sdk.ts:268](/source/?file=07502145bf1ffa712b.ts#L268)，266 调用 [messages.ts:148](/source/?file=2d4c32a97bc465b1f2.ts#L148)。

**【在转换里看什么】** bash 分支 154 判断过滤，custom 分支 163 转正文，摘要分支 170—183 包装文本，184—187 保留标准对象，194 过滤 undefined。注意新数组与原对象引用的区别。

**【正文转换支线】** 在 messages.ts 的 159 行遇到 `bashExecutionToText(m)`，跳到 [messages.ts:82](/source/?file=2d4c32a97bc465b1f2.ts#L82)。依次看 83 写 command、84—88 选输出形式、89—95 附加状态；这里不执行命令，也不读取 fullOutputPath。97 返回字符串后回 159，把它放入 text 块，再继续 map/filter。

**【对照例子】** 第 5.4 节的排除消息可在 154 行停下，观察该项返回 undefined；到 194 行再观察数组长度减少。标准助手和工具结果仍是原对象，调用关联仍保存在 ToolCall.id 与 ToolResultMessage.toolCallId 中。

**【返回】** 回 SDK 的 266，按 268 的图片设置选择直接返回或进入 272—297 的图片替换。然后回 [agent-loop.ts:320](/source/?file=6adbf9ab77a3572a2f.ts#L320) 的 llmMessages 赋值，继续 319—323 构造本次模型 Context。

### 13.7 Step 7：区分扩展生命周期与 context 钩子

**【登记端】** [loader.ts:200](/source/?file=d170abdf93d664a78b.ts#L200) 把 handler 放入 Map；[types.ts:1073](/source/?file=baffea2d47e73908cd.ts#L1073) 的重载说明允许事件与返回类型。登记完成后回真正的派发端。

**【生命周期派发】** 从 Session 的 [agent-session.ts:640](/source/?file=24209413646c397dc9.ts#L640) 等位置进入 [runner.ts:682](/source/?file=1a64f1a2d3fca70128.ts#L682)。682 按扩展遍历，683 取对应 handler 数组，688 await handler。看完返回 629，完成 `_emitExtensionEvent` 后再回 522，继续普通会话通知。

**【context 支线】** 从模型路径 [agent-loop.ts:316](/source/?file=6adbf9ab77a3572a2f.ts#L316) 查到 SDK 的 [sdk.ts:350](/source/?file=07502145bf1ffa712b.ts#L350)，再进入 [runner.ts:822](/source/?file=1a64f1a2d3fca70128.ts#L822)。817 复制，825 创建 ContextEvent，826 等 handler，829 接收新数组，844 返回最终数组。

**【返回主线】** emitContext 返回后，SDK 回调的 Promise 完成；回 171 更新局部 messages，再到 171 convertToLlm。不要回到会话的 518：context 的出发点是模型输入路径。

**【工具支线】** 从 [agent-loop.ts:626](/source/?file=6adbf9ab77a3572a2f.ts#L626) 到 [agent-session.ts:383](/source/?file=24209413646c397dc9.ts#L383)，再到 [runner.ts:768](/source/?file=1a64f1a2d3fca70128.ts#L768)；返回 block/reason 后回 loop 的 630。后置从 [agent-loop.ts:711](/source/?file=6adbf9ab77a3572a2f.ts#L711) 到 [agent-session.ts:407](/source/?file=24209413646c397dc9.ts#L407)、[runner.ts:717](/source/?file=1a64f1a2d3fca70128.ts#L717)，返回覆盖后回 loop 的 715—721。只在前置桥存在处理器时读到 [agent-session.ts:389](/source/?file=24209413646c397dc9.ts#L389) 的队列等待。

### 13.8 Step 8：追一条主动提交的 custom 消息

**【打开】** [agent-session.ts:1306](/source/?file=24209413646c397dc9.ts#L1306)。1274—1281 创建消息，随后按 1282、1284、1290、1292 的实际优先级读分支。

- nextTurn：1269 暂存后返回；下次从 [agent-session.ts:1087](/source/?file=24209413646c397dc9.ts#L1087) 消费，再继续当次 prompt。
- 运行中：1272 或 1274 交给 Agent 队列；后续注入回查 [agent-loop.ts:226](/source/?file=6adbf9ab77a3572a2f.ts#L226)。
- 空闲并 triggerTurn：1277 等 Agent.prompt；回到 Step 2 的主线。
- 空闲且不 trigger：1279 状态追加，1280 记录追加，1286—1287 直接 `_emit`；只进入 Step 5 中普通会话监听器的那一小段。

**【核对输入次序】** 读 nextTurn 时从 [agent-session.ts:1071](/source/?file=24209413646c397dc9.ts#L1071) 开始，观察 1054 先 push 用户消息，再到 1061 push 暂存消息、1064 清空暂存数组。之后 1076 还可能追加 before_agent_start 返回的消息。看完返回 1103 的 Agent.prompt 调用，继续 Step 2；不要回到 runLoop 的工具续跑判断。

**【扩展入口的返回值】** 从 [loader.ts:261](/source/?file=d170abdf93d664a78b.ts#L261) 的 pi.sendMessage 到 [agent-session.ts:2216](/source/?file=24209413646c397dc9.ts#L2216) 的绑定函数，看没有 return 内部 Promise。读完回扩展调用位置，区分 void 转发与直接等待 Session 方法。

### 13.9 Step 9：识别另一套事件总线，再核对结束边界

pi.events 来源在 [loader.ts:341](/source/?file=d170abdf93d664a78b.ts#L341)。跳到 [event-bus.ts:15](/source/?file=6982c4638dc60fbe73.ts#L15)，先看 emit 只调用 EventEmitter，再看 on 保存 safeHandler、返回取消函数。内部 await 的位置是 21，外层 emit 没有等待集合。

对照第 10.2 节的小例子：第一次 emit 从 event-bus.ts 的 15 行进入监听包装函数，20—21 行调用接收者；off 沿 27 行移除当初登记的 safeHandler。第二次 emit 不会再找到这位处理器。读到外部 handler 的异步工作时，回看 15—16 行即可确认外层没有收集或返回它的 Promise。

**【停止下钻】** 不需要进入 Node EventEmitter 的完整实现；对本章而言，返回类型、实际回调和 Promise 是否被收集已经确定其等待范围。看完回原 pi.events.emit/on 调用。

最后从 [agent.ts:484](/source/?file=3688aa044ebb960834.ts#L484) 的 finally 进入 [agent.ts:505](/source/?file=3688aa044ebb960834.ts#L505)，确认 finishRun 清状态与完成空闲 Promise。若调用方是 AgentSession，再看 [agent-session.ts:1131](/source/?file=24209413646c397dc9.ts#L1131)、1104 和 [agent-session.ts:2587](/source/?file=24209413646c397dc9.ts#L2587)；不要把这些等待自动扩成会话队列排空。

### 13.10 完整阅读路线与变量定位

```text
主线：
Message / 内容块
  → Agent.prompt → normalizePromptInput → runPromptMessages
  → runAgentLoop 建立消息数组并发输入事件
  → streamAssistantResponse
      → transformContext → convertToLlm → 模型流
      → 更新助手消息 → emit(AgentEvent)
  → Agent.processEvents 更新状态 → Agent listener
  → AgentSession._handleAgentEvent 入队后返回
  → 会话队列 _processAgentEvent
      → 扩展生命周期桥 → runner.emit → pi.on handler
      → Session._emit → session.subscribe listener
      → message_end 对应的记录追加

输入改写支线：
streamAssistantResponse → SDK transformContext
  → runner.emitContext → pi.on("context")
  → 返回 AgentMessage[] → coding-agent convertToLlm → Message[]

主动消息支线：
pi.sendMessage → 绑定函数 → Session.sendCustomMessage
  → 暂存 / 入Agent队列 / Agent.prompt / 直接追加与会话通知

独立总线：
pi.events.emit → EventEmitter → safeHandler → 自定义频道handler
```

| 在源码中看到 | 去哪里定位 | 它保存或交出什么 |
| --- | --- | --- |
| message.role | [types.ts:195](/source/?file=a8f4ce943bcfc7dd27.ts#L195)、[messages.ts:29](/source/?file=2d4c32a97bc465b1f2.ts#L29) | 消息种类；不同角色拥有不同字段 |
| contentIndex | [types.ts:251](/source/?file=a8f4ce943bcfc7dd27.ts#L251) | 助手 content 数组里的块位置 |
| toolCallId | [types.ts:214](/source/?file=a8f4ce943bcfc7dd27.ts#L214) | 对应 ToolCall.id 的调用编号 |
| AgentContext.messages | [types.ts:333](/source/?file=d51aa2ef0fa6575e26.ts#L333) | 本次循环可读取和更新的 AgentMessage[] |
| llmMessages | [agent-loop.ts:320](/source/?file=6adbf9ab77a3572a2f.ts#L320) | 转换后供本次模型调用的 Message[] |
| streamingMessage | [agent.ts:523](/source/?file=3688aa044ebb960834.ts#L523)、[agent.ts:527](/source/?file=3688aa044ebb960834.ts#L527) | 最近消息 start/update 交来的对象 |
| emit | [agent-loop.ts:25](/source/?file=6adbf9ab77a3572a2f.ts#L25)、[agent.ts:405](/source/?file=3688aa044ebb960834.ts#L405) | 调用方传入的 AgentEvent 接收函数 |
| `_agentEventQueue` | [agent-session.ts:252](/source/?file=24209413646c397dc9.ts#L252)、[agent-session.ts:467](/source/?file=24209413646c397dc9.ts#L467) | 连接会话处理任务的 Promise |
| `_eventListeners` | [agent-session.ts:705](/source/?file=24209413646c397dc9.ts#L705) | 普通会话订阅函数数组 |
| extension.handlers | [loader.ts:200](/source/?file=d170abdf93d664a78b.ts#L200) | 按事件名保存扩展 handler 的 Map |
| currentMessages | [runner.ts:824](/source/?file=1a64f1a2d3fca70128.ts#L824) | context 钩子继续处理的消息副本或返回数组 |
| `_pendingNextTurnMessages` | [agent-session.ts:1319](/source/?file=24209413646c397dc9.ts#L1319)、[agent-session.ts:1087](/source/?file=24209413646c397dc9.ts#L1087) | 留给后续 Session.prompt 的应用消息 |
| SessionEntry.id | [session-manager.ts:863](/source/?file=043f6d188e65e3207b.ts#L863) | 会话记录编号，与工具调用 ID 分开 |

沿主线阅读，可以说明一条消息怎样产生、进入状态并触发通知；沿各条支线回到原调用点，则能进一步说明输入怎样被修改、应用消息怎样加入，以及哪些异步工作真正被等待。
