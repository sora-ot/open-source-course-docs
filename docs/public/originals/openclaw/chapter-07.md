# 07 Pi 工具系统源码解析：先定义工具，再追顺序执行与结果回传

[第 06 章](06_Pi-AgentLoop源码解析：从prompt到任务结束.md) 讲完整 Agent Loop。本章先定义、接入真实工具，紧接着用 convertTools 把工具说明交给模型，让模型知道有哪些工具可用；再沿模型返回的调用，追到本地查找、执行与结果回传。

**先看顺序执行总览，再定义并接入工具，紧接着讲模型怎样知道工具、怎样返回调用；之后逐句进入本地执行源码。** 阅读时遇到函数就跳入，查清后返回调用点继续。模型请求与 Provider 的完整链路沿用第 05、06 章。

源码以工作区 `pi-master/` 为准。行号包含课堂注释，修改后优先按函数名定位。结构摘录会标明省略，教学示例不是仓库已有文件。求和主线固定追踪 sum-1：参数为 `{ values: [2, 3] }`，结果为 5；内置 write 另用文件写入示例展开。A1、R1 分别表示助手调用消息、工具结果消息。模型输出是给定的教学条件。

想先用一个完整例子串起“工具代码 → 请求 JSON → 模型调用 JSON → find → 执行”，可以直接阅读文末第 16 节，再回来跟读源码。

## 先看全流程：executeToolCallsSequential 一项怎样走完

顺序执行的关键是：**当前这一项从准备到结果消息全部处理完，才开始下一项。** 先按下面的顺序认识函数，暂时不展开内部语句。

```text
模型返回完整助手消息 A1，其中包含 ToolCall
  → executeToolCalls：选择 sequential 分支
  → executeToolCallsSequential：for 取出一项调用
      ① 发 tool_execution_start
      ② prepareToolCall：按 name 找工具 → 准备参数 → Schema 校验
      ③ beforeToolCall：检查是否允许执行
      ④ executePreparedToolCall：调用真实 tool.execute
           └─ 工具可用 onUpdate 报告进度
      ⑤ finalizeExecutedToolCall：运行 afterToolCall，处理最终结果
      ⑥ 发 tool_execution_end，包装 ToolResultMessage
      ⑦ 发 message_start / message_end，收集结果
      ⑧ 处理下一项；整批结束后计算 terminate 并返回
  → runLoop：结果进入上下文
  → 下一次模型调用读到结果，继续回答
```

beforeToolCall 位于 prepareToolCall 内部，afterToolCall 位于 finalizeExecutedToolCall 内部。图中将它们单独列出，是为了先看清前后顺序；源码位置见 [agent-loop.ts:447](../pi-master/packages/agent/src/agent-loop.ts#L447)、[625](../pi-master/packages/agent/src/agent-loop.ts#L625)、[709](../pi-master/packages/agent/src/agent-loop.ts#L709)。

| 环节 | 主要任务 | 本例正常路径 |
| --- | --- | --- |
| find + 参数检查 | 把模型工具名对上本地对象，取得可用参数 | 找到 sumNumbersTool，values 为 `[2, 3]` |
| beforeToolCall | 执行前检查，可返回 block/reason 阻止 | 记录日志，放行 |
| tool.execute | 运行我们写好的业务函数 | 计算得到 5 |
| afterToolCall | 读取结果，可覆盖 content/details/isError/terminate | 记录日志，保留结果 |
| 结果消息 | 把最终结果关联回调用 ID | R1 对应 sum-1 |

也要先记住三条分支：

- 找不到工具、参数检查失败、before 阻止：得到 immediate 错误，跳过 execute 和 after。
- execute 抛错：执行层转成错误结果，仍进入 after。
- 未配置 before 或 after：跳过对应钩子；start/end 事件仍由批次函数处理。

这里的 beforeToolCall、afterToolCall 是 Agent 配置中的函数。扩展中的 tool_call、tool_result 由上层桥接到它们，后面的第 12 节再展开。

## 1. 先把工具定义与接入示例放在眼前

### 1.1 我们自己写的 sum-tool.ts

先定义我们自己编写的求和工具，教学文件名为 `sum-tool.ts`：

```ts
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { Type } from "typebox";

export const sumParameters = Type.Object(
  {
    values: Type.Array(
      Type.Number({ minimum: -1_000_000, maximum: 1_000_000 }),
      { minItems: 1, maxItems: 100, description: "需要相加的数字" },
    ),
  },
  { additionalProperties: false },
);

export interface SumDetails {
  count: number;
  total: number;
}

export const sumNumbersTool: AgentTool<typeof sumParameters, SumDetails> = {
  name: "sum_numbers",
  label: "数字求和",
  description: "计算一组数字的总和。需要准确相加时使用，参数 values 为数字数组。",
  parameters: sumParameters,
  executionMode: "parallel",

  async execute(_toolCallId, { values }, signal, _onUpdate) {
    if (signal?.aborted) {
      throw new Error("求和已取消");
    }

    console.log("[execute] 开始求和");
    const total = values.reduce((sum, value) => sum + value, 0);
    return {
      content: [{ type: "text", text: `总和为 ${total}` }],
      details: { count: values.length, total },
    };
  },
};
```

`parameters` 保存 Schema；`Static<typeof sumParameters>` 帮助推导编写 execute 时的参数类型。模型传来的真实数据，仍要在执行前做运行时检查。

execute 是函数属性。创建对象只保存函数，尚未计算总和。四个参数如何传入，后面沿 Agent Loop 的实际调用逐项对齐。

### 1.2 把工具交给 Agent，并装上 before/after

教学文件 `run-sum.ts`：

```ts
import { Agent } from "@mariozechner/pi-agent-core";
import type { Api, Model } from "@mariozechner/pi-ai";
import { sumNumbersTool } from "./sum-tool.js";

export async function runSumExample(model: Model<Api>, apiKey: string) {
  const agent = new Agent({
    initialState: {
      model,
      systemPrompt: "计算数字总和时使用 sum_numbers，再根据工具结果回答。",
      tools: [sumNumbersTool],
    },
    getApiKey: () => apiKey,
    toolExecution: "sequential",
    beforeToolCall: async ({ toolCall, args }) => {
      console.log("[beforeToolCall]", toolCall.name, args);
      return undefined; // 本例检查后放行。
    },
    afterToolCall: async ({ toolCall, result, isError }) => {
      console.log("[afterToolCall]", toolCall.name, result, isError);
      return undefined; // 本例保留执行结果。
    },
  });

  let text = "";
  const unsubscribe = agent.subscribe((event) => {
    if (
      event.type === "message_update" &&
      event.assistantMessageEvent.type === "text_delta"
    ) {
      text += event.assistantMessageEvent.delta;
    }
  });

  try {
    await agent.prompt("请调用 sum_numbers 计算 2 与 3 的总和，并给出结果。");
    return {
      text,
      messages: agent.state.messages,
      errorMessage: agent.state.errorMessage,
    };
  } finally {
    unsubscribe();
  }
}
```

后面要跟读的 `toolExecution: "sequential"` 就在这里。工具自身的 parallel 声明不会覆盖全局 sequential。

调用方提供模型与凭据，并调用 `runSumExample(model, apiKey)` 才会运行。工具是否真的被调用，要看模型最终 content；本章固定按 A1 提出 sum-1 推演。

beforeToolCall 与 afterToolCall 都由应用传入。这里用日志观察顺序，分别返回 undefined，表示放行调用、保留结果。
模型若只提出一次 sum-1，正常执行会依次出现 beforeToolCall、execute、afterToolCall 的日志。
参数检查失败时还没有进入 before；before 阻止时不会进入 execute 和 after。

### 1.3 用内置 write 作为第二个例子

**read 和 write 都有，来自 pi-coding-agent；裸的 new Agent() 默认没有工具。** 由应用选工具、放进工具数组，当前运行才能使用。

| 内置能力 | 工厂函数 | 代码位置 |
| --- | --- | --- |
| 读取文件 | createReadTool(cwd) | [read.ts:274](../pi-master/packages/coding-agent/src/core/tools/read.ts#L274) |
| 写入文件 | createWriteTool(cwd) | [write.ts:279](../pi-master/packages/coding-agent/src/core/tools/write.ts#L279) |

[createCodingTools:168](../pi-master/packages/coding-agent/src/core/tools/index.ts#L168) 会创建 read、bash、edit、write 四个工具。本章用 write 演示真实文件操作，可以只接入 write，教学文件 `run-write.ts` 如下：

```ts
import { Agent } from "@mariozechner/pi-agent-core";
import type { Api, Model } from "@mariozechner/pi-ai";
import { createWriteTool } from "@mariozechner/pi-coding-agent";

export async function runWriteExample(model: Model<Api>, apiKey: string, cwd: string) {
  const writeTool = createWriteTool(cwd);
  const agent = new Agent({
    initialState: {
      model,
      tools: [writeTool],
    },
    getApiKey: () => apiKey,
    toolExecution: "sequential",
  });

  await agent.prompt("请调用 write，将 Hello Pi 写入 output/hello.txt，然后告诉我写入结果。");
  return agent.state.messages;
}
```

调用方提供模型、凭据与工作目录。createWriteTool 只创建工具对象；模型提出 write 调用以后，执行层才会创建父目录并写入文件，已有文件会被覆盖。这个示例的文件名为 output/hello.txt，正文为 Hello Pi。

自定义 sum_numbers 与内置 write 最后都进入同一个 currentContext.tools，都由下面这句连接模型调用与真实函数：

```ts
const tool = currentContext.tools?.find((t) => t.name === toolCall.name);
```

**工具对象准备好后，先进入第 2 节，把工具说明交给模型、看清调用数据怎样返回；再从第 3 节逐句追本地执行，内置 write 的源码在第 13 节展开。**

## 2. 工具定义好后：先让模型知道工具，再看调用与结果回传

**convertTools 的作用：把本地工具的名称、描述和参数 Schema 转换成模型接口要求的工具说明，让大模型知道有这个工具可用、它能做什么、该传什么参数；真正的 execute 函数仍留在本地。**

**这一节只追同一个例子：用户要求求和，模型提出 sum-1，本地算出 5，模型再回答。**

先固定条件：应用已接入第 1 节的 sumNumbersTool，使用 OpenAI Chat Completions 路径。下面省略系统提示、用量等无关字段；协议兼容选项按普通情况演示，模型输出是给定的教学数据。

先看四份东西怎样接起来：

```text
① 本地工具对象：sumNumbersTool，里面保存真实 execute 函数
       ↓ convertTools 只取说明字段
② 发给模型的 tools：工具名、描述、参数 Schema
       ↓ 模型按说明提出一次调用
③ 模型返回 tool_calls：工具名 sum_numbers，参数字符串
       ↓ Provider 拼接、解析
④ Pi 的 ToolCall：name="sum_numbers"，arguments 为对象
       ↓ find 按 name 找回①，再校验、执行
   工具结果“总和为 5”
       ↓ 包装消息，放进第二次请求
   模型读到结果，给出最终回答
```

### 2.1 起点：我们手里的是工具对象，里面有函数

回看第 1.1 节的定义。只摘出本节要用的字段：

```ts
// 本地对象的结构摘录，Schema 与函数体沿用第 1.1 节。
const sumNumbersTool = {
  name: "sum_numbers",
  description: "计算一组数字的总和。需要准确相加时使用，参数 values 为数字数组。",
  parameters: sumParameters,
  async execute(_toolCallId, { values }, signal, _onUpdate) {
    // 检查取消信号等步骤省略。
    const total = values.reduce((sum, value) => sum + value, 0);
    return {
      content: [{ type: "text", text: `总和为 ${total}` }],
      details: { count: values.length, total },
    };
  },
};
```

应用把它放进 `initialState.tools`，本次运行再取得工具快照。
因此当前 `currentContext.tools` 包含这个真实对象。

模型第一次被调用前，我们已有求和函数；此时还没有运行它。
接下来要做的是：把这项能力的名称、用途和参数要求交给模型。

### 2.2 第一次请求：从本地对象中提取模型能读的工具说明

先回 [agent-loop.ts:324](../pi-master/packages/agent/src/agent-loop.ts#L324)：

```ts
const llmContext: Context = {
  systemPrompt: context.systemPrompt,
  messages: llmMessages,
  tools: context.tools,
};
```

**buildParams 的 context 来自 Agent Loop 创建的 llmContext：它作为第二个实参，经过模型流分发和 Provider 包装层，一路传到 buildParams。**

#### 先在 buildParams 的调用处，对齐第二个实参

打开 [buildParams:435](../pi-master/packages/ai/src/providers/openai-completions.ts#L435)，context 是它的第二个形参。先回到同文件 [142 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L142) 的直接调用处：

```ts
let params = buildParams(model, context, options, compat, cacheRetention);
```

这一句位于 [streamOpenAICompletions:110](../pi-master/packages/ai/src/providers/openai-completions.ts#L110) 内部。这里传入的 context，来自该 Provider 函数的第二个形参 `context: Context`。
所以先记住最近一层：**streamOpenAICompletions 接收到什么 context，就把同一个对象传给 buildParams。**

#### 再回 Agent Loop，找到 llmContext 的创建与传入

本节上面那段 llmContext 在 [streamAssistantResponse:324](../pi-master/packages/agent/src/agent-loop.ts#L324) 中创建。这个函数自身接收的 context，又来自 [runLoop:237](../pi-master/packages/agent/src/agent-loop.ts#L237)：

```ts
const message = await streamAssistantResponse(currentContext, config, signal, emit, streamFn);
```

所以 streamAssistantResponse 内的 `context`，接住的就是 runLoop 的 `currentContext`。
它先处理消息，再建立新的请求对象 llmContext：

| llmContext 中的字段 | 从哪里取得 |
| --- | --- |
| systemPrompt | `currentContext.systemPrompt` |
| messages | 经可选 transformContext、convertToLlm 处理后的消息 |
| tools | 直接沿用 `currentContext.tools` |

然后在 [agent-loop.ts:336](../pi-master/packages/agent/src/agent-loop.ts#L336) 把 llmContext 放在第二个实参的位置：

```ts
const response = await streamFunction(config.model, llmContext, {
  ...config,
  apiKey: resolvedApiKey,
  signal,
});
```

**这里实际交给模型流函数的是新建的 llmContext；它的 tools 仍指向当前工具数组，其中有我们接入的真实工具对象。**

#### 中间各层怎样把这个对象继续传下去

下面按默认流函数、`model.api === "openai-completions"` 的路径看。应用若自己提供 streamFn，应沿那份函数继续追。

| 经过哪一层 | 传参语句或行为 | 第二个参数 |
| --- | --- | --- |
| Agent Loop | `streamFunction(config.model, llmContext, ...)` | llmContext |
| [streamSimple:43](../pi-master/packages/ai/src/stream.ts#L43) | `provider.streamSimple(model, context, options)` | 沿用收到的 context |
| [wrapStreamSimple:54](../pi-master/packages/ai/src/api-registry.ts#L54) | 检查 model.api，调用已注册的流函数 | 沿用 context |
| [延迟加载函数:189](../pi-master/packages/ai/src/providers/register-builtins.ts#L189) | 加载模块后调用 `module.streamSimple(model, context, options)` | 沿用 context |
| [streamSimpleOpenAICompletions:368](../pi-master/packages/ai/src/providers/openai-completions.ts#L368) | 调用 `streamOpenAICompletions(model, context, ...)` | 沿用 context |
| [streamOpenAICompletions:142](../pi-master/packages/ai/src/providers/openai-completions.ts#L142) | `buildParams(model, context, ...)` | 沿用 context |

注册表怎样对应到真正函数，可对照 [register-builtins.ts:373](../pi-master/packages/ai/src/providers/register-builtins.ts#L373) 的注册项，以及 [303 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L303) 的模块加载映射：模块的 streamSimple 指向真正的 streamSimpleOpenAICompletions。
这些层会整理选项、加载模块或转发事件流，**本例中传递的第二个参数始终是同一个 llmContext 对象**。

把对象和局部变量名对起来：

```text
runLoop 的 currentContext
  → streamAssistantResponse 的形参 context
      → 创建新对象 llmContext
          systemPrompt：取当前系统提示词
          messages：取整理后的消息
          tools：沿用当前工具数组
      → streamFunction(..., llmContext, ...)
          → streamSimple 的 context
          → 注册表包装与延迟加载的 context
          → streamSimpleOpenAICompletions 的 context
          → streamOpenAICompletions 的 context
          → buildParams 的 context
```

**同名 context 不代表每处都在重新创建对象。** 新建请求对象发生在 llmContext 那一句；后续包装层在这条默认路径中传递它的引用。

#### 现在返回 buildParams，继续看 tools 转换

到这里，buildParams 中的 `context.tools` 就能对上 Agent Loop 的 `llmContext.tools`，再对上 `currentContext.tools`。
它们沿用同一份工具数组，本例里面的对象就是 sumNumbersTool。

接着看 [buildParams:475](../pi-master/packages/ai/src/providers/openai-completions.ts#L475)：

```ts
params.tools = convertTools(context.tools, compat);
```

**停在这里，对齐输入与输出：输入是本地工具对象数组，输出是请求中的工具说明数组。**

进入 [convertTools:894](../pi-master/packages/ai/src/providers/openai-completions.ts#L894)：

```ts
function convertTools(
  tools: Tool[],
  compat: ResolvedOpenAICompletionsCompat,
): OpenAI.Chat.Completions.ChatCompletionTool[] {
  return tools.map((tool) => ({
    type: "function",
    function: {
      name: tool.name,
      description: tool.description,
      parameters: tool.parameters as any,
      ...(compat.supportsStrictMode !== false && { strict: false }),
    },
  }));
}
```

map 为每项工具创建一个新说明对象。看看哪些字段被取出：

| 本地工具中的字段 | 请求中的位置 |
| --- | --- |
| `tool.name` | `function.name` |
| `tool.description` | `function.description` |
| `tool.parameters` | `function.parameters` |
| `tool.execute` | 留在本地，未被取入请求 |

协议中的 `function` 是一个字段名，其内容是工具说明。
真正求和的函数保存在本地 sumNumbersTool.execute 中。

假设当前兼容配置允许附带 strict 字段，则本例 `params.tools` 对应下面的 JSON。这里展开第 1 节的 Schema，方便看到模型收到的实际参数要求：

```json
[
  {
    "type": "function",
    "function": {
      "name": "sum_numbers",
      "description": "计算一组数字的总和。需要准确相加时使用，参数 values 为数字数组。",
      "parameters": {
        "type": "object",
        "properties": {
          "values": {
            "type": "array",
            "items": {
              "type": "number",
              "minimum": -1000000,
              "maximum": 1000000
            },
            "minItems": 1,
            "maxItems": 100,
            "description": "需要相加的数字"
          }
        },
        "required": ["values"],
        "additionalProperties": false
      },
      "strict": false
    }
  }
]
```

模型由此知道：有个工具叫 sum_numbers，用于求和，调用参数应有 values 数字数组。
**Schema 描述“参数应该长什么样”；这次具体的 `[2, 3]` 还要由模型填入调用。**

返回 buildParams，再回 [openai-completions.ts:142](../pi-master/packages/ai/src/providers/openai-completions.ts#L142) 附近。参数构造完后，实际发出请求的位置在 [147 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L147)：

```ts
const { data: openaiStream, response } = await client.chat.completions
  .create(params, { signal: options?.signal })
  .withResponse();
```

源码中还允许 onPayload 改写请求；本例没有配置这项改写。
第一次请求的 messages 中有用户问题 U，tools 中有上面的求和说明。

### 2.3 模型第一次返回：先看到协议里的 tool_calls

假设用户要求“请调用 sum_numbers 计算 2 与 3 的总和，并给出结果”，模型决定调用该工具。
响应通过多个 chunk 返回。本例只展示两段 `choices[0].delta.tool_calls`，省略 chunk 其他字段。

第一段：给出调用 ID、工具名，以及参数字符串前半段。

```ts
[
  {
    index: 0,
    id: "sum-1",
    type: "function",
    function: {
      name: "sum_numbers",
      arguments: '{"values":[2,',
    },
  },
]
```

第二段：补完同一项调用的参数字符串。

```ts
[
  {
    index: 0,
    function: {
      arguments: '3]}',
    },
  },
]
```

注意三点：

- `function.name` 是这次准备调用的工具名。
- `function.arguments` 此时是 JSON **字符串片段**。
- 第二段可以只补参数，不重复名称和 ID。

把字符串拼起来才是完整参数：

```text
'{"values":[2,' + '3]}'
               ↓
'{"values":[2,3]}'
```

**模型返回的是“调用 sum_numbers，参数是这组数据”。它还没有在我们的电脑上执行 reduce。**

### 2.4 Provider 把 SDK 增量拼成 Pi 的 ToolCall

现在对上实际接收位置：[openai-completions.ts:281](../pi-master/packages/ai/src/providers/openai-completions.ts#L281)。

```ts
if (choice?.delta?.tool_calls) {
  for (const toolCall of choice.delta.tool_calls) {
    // 处理这一段 SDK 工具调用增量。
  }
}
```

这里循环变量 toolCall 是 **SDK 增量对象**；currentBlock 才是正在组装的 **Pi 内容块**。这两个名字代表的数据结构不同。

第一次收到增量，currentBlock 还没有建立，因此进入创建分支。下面摘录 [288 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L288) 附近的关键语句：

```ts
currentBlock = {
  type: "toolCall",
  id: toolCall.id || "",
  name: toolCall.function?.name || "",
  arguments: {},
  partialArgs: "",
};
output.content.push(currentBlock);
```

代入第一段数据，name 就是 sum_numbers，id 就是 sum-1。
output 是本次助手消息，content 数组现在放入了这个调用块。

然后进入 [303 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L303) 附近的参数处理：

```ts
delta = toolCall.function.arguments;
currentBlock.partialArgs += toolCall.function.arguments;
currentBlock.arguments = parseStreamingJson(currentBlock.partialArgs);
```

按两段数据走一遍：

| 收到哪一段 | partialArgs 累计字符串 | arguments |
| --- | --- | --- |
| 第一段 | `'{"values":[2,'` | 容错解析出的临时对象 |
| 第二段 | `'{"values":[2,3]}'` | `{ values: [2, 3] }` |

第二段继续更新同一个 currentBlock，不再新建第二项调用。
因为 output.content 中保存的是这个对象引用，字段更新也就体现在助手消息里。

parseStreamingJson 能容忍未完成 JSON，见 [json-parse.ts:104](../pi-master/packages/ai/src/utils/json-parse.ts#L104)。中间值用于流式更新；**读出一个临时对象，不代表参数已收齐，也不代表通过了工具 Schema 校验。**

流结束时，[finishCurrentBlock:172](../pi-master/packages/ai/src/providers/openai-completions.ts#L172) 附近会再次解析完整字符串，删除临时 partialArgs，并发出 toolcall_end。
最终留在 A1.content 中的就是：

```ts
{
  type: "toolCall",
  id: "sum-1",
  name: "sum_numbers",
  arguments: { values: [2, 3] },
}
```

到这里，SDK 的参数字符串已变成 Pi 的参数对象。
toolcall_start、toolcall_delta、toolcall_end 描述的是模型调用数据的接收过程；本地执行阶段的 tool_execution_start/end 还在后面。

### 2.5 完整消息回到 runLoop，才进入本地工具执行

Provider 把工具调用的停止原因映射成 toolUse，见 [mapStopReason:948](../pi-master/packages/ai/src/providers/openai-completions.ts#L948)。正常收尾在 [347 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L347) 附近交出包含 output 的 done 事件。

回到 [agent-loop.ts:379](../pi-master/packages/agent/src/agent-loop.ts#L379)：

```ts
const finalMessage = await response.result();
// 更新上下文、发送完成消息事件等语句省略。
return finalMessage;
```

这里取到完整 A1，runLoop 才继续。只看相关字段，A1 是：

```ts
{
  role: "assistant",
  content: [
    {
      type: "toolCall",
      id: "sum-1",
      name: "sum_numbers",
      arguments: { values: [2, 3] },
    },
  ],
  stopReason: "toolUse",
}
```

完整 AssistantMessage 还包括模型、用量、时间等字段，以上仅展示本例相关部分。

本节先看这段本地执行的输入输出；具体函数将在第 3—10 节逐句展开：

```text
runLoop 从 A1.content 筛出 ToolCall
  → 进入 sequential
  → find 比较本地 t.name 与模型返回的 toolCall.name
  → "sum_numbers" 匹配，取出开头的 sumNumbersTool
  → 参数检查 → before → execute → after
  → 得到工具结果 R1：“总和为 5”
```

**模型提供名称和参数；find 找到真实对象；execute 才运行我们写好的函数。**

### 2.6 第二次请求：把调用和工具结果一起带回模型

本地执行得到的 R1，省略时间戳后为：

```ts
{
  role: "toolResult",
  toolCallId: "sum-1",
  toolName: "sum_numbers",
  content: [{ type: "text", text: "总和为 5" }],
  details: { count: 2, total: 5 },
  isError: false,
}
```

它被加入 currentContext.messages。于是第二次模型调用的消息历史已经是：

```text
[U, A1, R1]
 U：用户的问题
 A1：助手提出 sum-1
 R1：本地工具返回 sum-1 的结果
```

Provider 又进入 [convertMessages:658](../pi-master/packages/ai/src/providers/openai-completions.ts#L658)，把 Pi 消息转换成请求协议：

- A1 的 ToolCall 在 [785 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L785) 变成 assistant.tool_calls，arguments 重新 JSON.stringify 成字符串。
- R1 在 [820 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L820) 进入工具结果分支，文本正文被合成字符串，toolCallId 写入 tool_call_id。

忽略系统提示与其他兼容字段，普通兼容设置下，第二次请求的 messages 就是下面这种形式：

```json
[
  {
    "role": "user",
    "content": "请调用 sum_numbers 计算 2 与 3 的总和，并给出结果。"
  },
  {
    "role": "assistant",
    "content": null,
    "tool_calls": [
      {
        "id": "sum-1",
        "type": "function",
        "function": {
          "name": "sum_numbers",
          "arguments": "{\"values\":[2,3]}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "sum-1",
    "content": "总和为 5"
  }
]
```

两个 sum-1 把调用与结果对应起来：

```text
assistant.tool_calls[0].id = "sum-1"
                          ↕ 同一次调用
tool.tool_call_id          = "sum-1"
```

这一次模型才看到“总和为 5”。假设它随后返回普通文字“2 与 3 的总和是 5”，这就是最终助手回复 A2。
第二次请求仍可带工具说明，模型也可能继续提出调用；本例固定按完成回答的路径说明。

R1.details 留给应用使用，这条 Provider 路径不会自动把它作为正文发送。模型需要读取的信息应放入 content。
不同兼容设置可能将 assistant 的空内容改为字符串，或给工具结果加 name；本例省略这些差异，核心关联仍是调用 ID 与结果 ID。

### 2.7 先把数据对应起来，再进入本地执行

| 看到的字段 | 本例数据 | 表示什么 |
| --- | --- | --- |
| 请求 `tools` | sum_numbers 的名称、描述、Schema | 模型可使用的能力说明 |
| 返回 `delta.tool_calls` | name 与参数字符串片段 | 模型这次提出的调用增量 |
| Pi `ToolCall` | name 与解析后的参数对象 | 执行层接收的调用数据 |
| 本地 `tool.execute` | 我们写好的求和函数 | 实际业务执行 |
| 下次请求 `role: "tool"` | sum-1 的结果“总和为 5” | 交回模型的执行结果 |

**name 负责把调用对上工具；id 负责把结果对上这次调用。**

先记住下面这条数据路线，随后进入执行层时，再逐个跳入函数查看：

```text
本地 sumNumbersTool
  → llmContext.tools
  → buildParams → convertTools → 返回请求参数
  → SDK 发出第一次请求
  → SDK chunk → Provider 拼出 A1 → 返回 runLoop
  → find → execute → R1
  → 下一轮 buildParams → convertMessages → [U, A1, R1]
  → SDK 发出第二次请求 → 最终文字 A2
```

换其他模型 API 时，由对应 Provider 适配工具说明、调用和结果的协议格式；本地 find、校验、execute 和前后置钩子仍沿同一套 Agent Loop。

工具说明、模型调用和结果的数据形状已经对齐。下一节回到 runLoop，从筛选完整 ToolCall 开始，逐句进入本地执行函数。

## 3. 从 runLoop 的 toolCall 开始

### 3.1 先看筛选，再看下一次函数调用

打开 [agent-loop.ts:247](../pi-master/packages/agent/src/agent-loop.ts#L247)。此时 `streamAssistantResponse` 已返回完整助手消息 `message`，error/aborted 分支也已排除：

```ts
const toolCalls = message.content.filter((c) => c.type === "toolCall");

const toolResults: ToolResultMessage[] = [];
hasMoreToolCalls = false;
if (toolCalls.length > 0) {
  const executedToolBatch = await executeToolCalls(currentContext, message, config, signal, emit);
  toolResults.push(...executedToolBatch.messages);
  hasMoreToolCalls = !executedToolBatch.terminate;

  for (const result of toolResults) {
    currentContext.messages.push(result);
    newMessages.push(result);
  }
}
```

先看第一句：`message.content` 是内容块数组，`filter` 取出其中 `type === "toolCall"` 的项。它得到调用数据，还没有执行工具。

本例 A1 的 content 中有这一项：

```ts
{
  type: "toolCall",
  id: "sum-1",
  name: "sum_numbers",
  arguments: { values: [2, 3] },
}
```

所以 `toolCalls.length > 0` 成立。接下来真正要进入的是 `executeToolCalls(currentContext, message, config, signal, emit)`。

### 3.2 只补当前需要的类型，然后立即返回

若不清楚调用块有哪些字段，跳到 [ToolCall:170](../pi-master/packages/ai/src/types.ts#L170)：

```ts
export interface ToolCall {
  type: "toolCall";
  id: string;
  name: string;
  arguments: Record<string, any>;
  thoughtSignature?: string; // Google-specific: opaque signature for reusing thought context
}
```

这里 `id` 标识本次调用，`name` 用于找工具，`arguments` 是本次参数。**调用块中没有 execute 函数。** `thoughtSignature` 是部分 Provider 的协议信息，本例没有。

执行层写的 `AgentToolCall` 则在 [agent/src/types.ts:39](../pi-master/packages/agent/src/types.ts#L39)：

```ts
export type AgentToolCall = Extract<AssistantMessage["content"][number], { type: "toolCall" }>;
```

`[number]` 取 content 的元素类型；`Extract` 选出工具调用分支。这是类型别名，没有在运行时再创建一份调用。

模型 chunk 怎样变成调用块，已在第 2.3—2.5 节看过。现在将完整 ToolCall 对上这里的 filter，再返回 runLoop 的 `executeToolCalls(...)` 继续。

## 4. 进入 executeToolCalls，先确定走哪个分支

### 4.1 对齐实参与形参

打开 [executeToolCalls:424](../pi-master/packages/agent/src/agent-loop.ts#L424)：

```ts
async function executeToolCalls(
  currentContext: AgentContext,
  assistantMessage: AssistantMessage,
  config: AgentLoopConfig,
  signal: AbortSignal | undefined,
  emit: AgentEventSink,
): Promise<ExecutedToolCallBatch> {
  const toolCalls = assistantMessage.content.filter((c) => c.type === "toolCall");
  const hasSequentialToolCall = toolCalls.some(
    (tc) => currentContext.tools?.find((t) => t.name === tc.name)?.executionMode === "sequential",
  );
  if (config.toolExecution === "sequential" || hasSequentialToolCall) {
    return executeToolCallsSequential(currentContext, assistantMessage, toolCalls, config, signal, emit);
  }
  return executeToolCallsParallel(currentContext, assistantMessage, toolCalls, config, signal, emit);
}
```

| 调用处实参 | 函数内形参 | 本例含义 |
| --- | --- | --- |
| `currentContext` | `currentContext` | 本次上下文，内有可用工具 |
| `message` | `assistantMessage` | A1，整条助手消息 |
| `config` | `config` | 执行模式及前后置钩子 |
| `signal` | `signal` | 本次运行的取消信号 |
| `emit` | `emit` | 第 06 章追过的事件出口 |

注意第二个参数传的是整条 A1。函数内部再次 filter，得到本批要执行的工具调用。

### 4.2 先让教学例子进入 sequential

圈出 `hasSequentialToolCall`。`some` 检查本批是否至少有一个工具声明 `executionMode: "sequential"`。查找仍然按调用块的 name 进行。

进入顺序分支有两个条件，满足其一即可：

- `config.toolExecution === "sequential"`。
- 本批某个工具要求 sequential。

**只要一个工具要求 sequential，整批顺序执行。** 不是只把这一项单独排队。

本例创建 Agent 时显式传入 `toolExecution: "sequential"`，因此现在直接进入 `executeToolCallsSequential(...)`。配置如何传进来，沿 [agent.ts:445](../pi-master/packages/agent/src/agent.ts#L445) 可看到 `toolExecution: this.toolExecution`。

未传选项时，Agent 在 [agent.ts:223](../pi-master/packages/agent/src/agent.ts#L223) 使用 `parallel`。这里先选顺序路径方便逐句阅读，默认行为仍是并行。

## 5. 进入 executeToolCallsSequential，停在 prepareToolCall

### 5.1 多接住一个 toolCalls 数组

打开 [agent-loop.ts:447](../pi-master/packages/agent/src/agent-loop.ts#L447)。与上一层相比，这里多了第三个形参 `toolCalls`，接住刚刚筛出的数组。下面是完整函数体：

```ts
async function executeToolCallsSequential(
  currentContext: AgentContext,
  assistantMessage: AssistantMessage,
  toolCalls: AgentToolCall[],
  config: AgentLoopConfig,
  signal: AbortSignal | undefined,
  emit: AgentEventSink,
): Promise<ExecutedToolCallBatch> {
  const finalizedCalls: FinalizedToolCallOutcome[] = [];
  const messages: ToolResultMessage[] = [];

  for (const toolCall of toolCalls) {
    await emit({
      type: "tool_execution_start",
      toolCallId: toolCall.id,
      toolName: toolCall.name,
      args: toolCall.arguments,
    });

    const preparation = await prepareToolCall(currentContext, assistantMessage, toolCall, config, signal);
    let finalized: FinalizedToolCallOutcome;
    if (preparation.kind === "immediate") {
      finalized = {
        toolCall,
        result: preparation.result,
        isError: preparation.isError,
      };
    } else {
      const executed = await executePreparedToolCall(preparation, signal, emit);
      finalized = await finalizeExecutedToolCall(
        currentContext,
        assistantMessage,
        preparation,
        executed,
        config,
        signal,
      );
    }

    await emitToolExecutionEnd(finalized, emit);
    const toolResultMessage = createToolResultMessage(finalized);
    await emitToolResultMessage(toolResultMessage, emit);
    finalizedCalls.push(finalized);
    messages.push(toolResultMessage);
  }

  return {
    messages,
    terminate: shouldTerminateToolBatch(finalizedCalls),
  };
}
```

先不急着往下读所有辅助函数，沿本次 `sum-1` 逐句停：

```text
for 取出 sum-1
  → emit(tool_execution_start)
  → await prepareToolCall(...)      ← 现在停在这里
  → 判断 immediate / prepared
  → execute、后置处理
  → 结束事件、结果消息
  → 下一项调用
```

`tool_execution_start` 只说明开始处理本项调用。此时还没有查找工具和检查参数，不能由 start 断言业务函数已经执行。

### 5.2 先记住两个数组的用途

`finalizedCalls` 收集本批完成结果，用于最后判断 terminate。
`messages` 收集要交回 runLoop 的 `ToolResultMessage`。

本例只有一项；若同一条助手消息提出两项，循环会把第一项的准备、执行和结果处理全部 await 完，再开始第二项。两项参数都已在 A1 中给出，第一项结果不会自动替模型改写第二项参数。

现在从 `await prepareToolCall(...)` 跳进去。五个实参沿用原上下文、A1、本项 toolCall、配置和信号。

## 6. 进入 prepareToolCall，遇到 tools 就回查来源

### 6.1 重点：这一行把模型返回的工具名，对上我们写好的真实工具

打开 [prepareToolCall:606](../pi-master/packages/agent/src/agent-loop.ts#L606)，先停在 [604 行](../pi-master/packages/agent/src/agent-loop.ts#L613)：

```ts
const tool = currentContext.tools?.find((t) => t.name === toolCall.name);
if (!tool) {
  return {
    kind: "immediate",
    result: createErrorToolResult(`Tool ${toolCall.name} not found`),
    isError: true,
  };
}
```

**这一行是模型调用数据与本地工具函数的连接点：用模型返回的工具名，找到我们预先写好、注册并启用的工具对象。**

把左右两边分开看：

| 代码中的值 | 从哪里来 | 本例是什么 |
| --- | --- | --- |
| `toolCall.name` | 模型响应经 Provider 解析后的调用数据 | 字符串 `"sum_numbers"` |
| `currentContext.tools` | 应用提供、本次运行可用的工具对象数组 | 包含开头第 1.1 节定义的 `sumNumbersTool` |
| `t` | find 依次检查的一个本地工具对象 | 带有 name、Schema、execute 的对象 |
| `t.name` | 我们定义工具时填写的名称 | 字符串 `"sum_numbers"` |
| 返回的 `tool` | 首个名称匹配的本地对象 | `sumNumbersTool` 本身，包含真正的 execute 函数 |

核心就是比较：

```ts
// 我们注册的工具名       模型返回的工具名
       t.name       ===     toolCall.name
//   "sum_numbers"  ===     "sum_numbers"
```

名称匹配以后，find **返回已有工具对象的引用**。后面拿到它的 execute，才能进入我们自己编写的求和代码。

```text
模型返回：name = "sum_numbers"，arguments = { values: [2, 3] }
                         ↓ 按 name 匹配
我们提供：{ name: "sum_numbers", parameters: ..., execute: 求和函数 }
                         ↓ find 返回这个真实对象
局部 tool → 准备结果中的 prepared.tool → prepared.tool.execute(...)
                         ↓
执行我们写好的代码，算出 2 + 3 = 5
```

**模型提供“调用哪个工具、传什么参数”；我们提供“这个工具具体怎样执行”。两者靠 name 在这一行接上。**

这里按 `name` 严格相等查找；`label` 用于显示，`id` 用于关联本次调用与结果。登记和启用的完整过程见第 12 节，最终都要让对象进入本次 `currentContext.tools`。

这一行只负责找到对象。接下来先检查参数、经过前置钩子，再到第 8.1 节真正调用 execute。
若数组不存在或没有同名项，就走上面的 immediate 错误分支，不会执行工具。

开头已经把 sumNumbersTool 交给 Agent。现在沿 currentContext.tools 回查，确认这个对象怎样到达 find 所在的位置。

### 6.2 从 currentContext.tools 回到 createContextSnapshot

第 6 章已看到：`runAgentLoop` 用对象展开建立 currentContext，只替换 messages，tools 沿用传入快照的数组。回到 [agent.ts:425](../pi-master/packages/agent/src/agent.ts#L425)：

```ts
private createContextSnapshot(): AgentContext {
  return {
    systemPrompt: this._state.systemPrompt,
    messages: this._state.messages.slice(),
    tools: this._state.tools.slice(),
  };
}
```

工具来自 `this._state.tools`。再沿构造函数的 `createMutableAgentState(options.initialState)`，找到 [agent.ts:78](../pi-master/packages/agent/src/agent.ts#L78) 中的初始化：

```ts
let tools = initialState?.tools?.slice() ?? [];
```

所以裸 Agent 的这条路径是：

```text
应用传入 initialState.tools
  → Agent 状态中的 tools
  → createContextSnapshot 的 tools
  → currentContext.tools
  → find 按 sum_numbers 找对象
```

slice 只复制外层数组，工具对象及其 execute 函数仍共享引用。本次快照取出后，给状态赋另一份工具数组，不会替换已取出的快照数组。

### 6.3 沿元素类型找到 AgentTool

`AgentContext.tools` 的元素类型是 AgentTool，定义见 [types.ts:307](../pi-master/packages/agent/src/types.ts#L307)。省去注释后：

```ts
export interface AgentTool<TParameters extends TSchema = TSchema, TDetails = any>
  extends Tool<TParameters> {
  label: string;
  prepareArguments?: (args: unknown) => Static<TParameters>;
  execute: (
    toolCallId: string,
    params: Static<TParameters>,
    signal?: AbortSignal,
    onUpdate?: AgentToolUpdateCallback<TDetails>,
  ) => Promise<AgentToolResult<TDetails>>;
  executionMode?: ToolExecutionMode;
}
```

继续沿 `extends Tool`，到 [ai/src/types.ts:228](../pi-master/packages/ai/src/types.ts#L228)：

```ts
export interface Tool<TParameters extends TSchema = TSchema> {
  name: string;
  description: string;
  parameters: TParameters;
}
```

至此可以把两种对象分清：

| 对象 | 本例保存什么 | 用途 |
| --- | --- | --- |
| ToolCall | sum-1、sum_numbers、values=[2,3] | 表示这一次调用 |
| AgentTool | 名称、描述、Schema、execute | 提供可调用的能力 |

同一个工具可被调用多次，每次有自己的 ID 和参数。模型返回调用数据，本地工具对象保存实际函数。

## 7. 返回 prepareToolCall，逐步得到可执行参数

### 7.1 先准备参数，再做 Schema 校验

继续看 [agent-loop.ts:623](../pi-master/packages/agent/src/agent-loop.ts#L623)：

```ts
const preparedToolCall = prepareToolCallArguments(tool, toolCall);
const validatedArgs = validateToolArguments(tool, preparedToolCall);
```

先跳 [prepareToolCallArguments:591](../pi-master/packages/agent/src/agent-loop.ts#L591)：

```ts
function prepareToolCallArguments(tool: AgentTool<any>, toolCall: AgentToolCall): AgentToolCall {
  if (!tool.prepareArguments) {
    return toolCall;
  }
  const preparedArguments = tool.prepareArguments(toolCall.arguments);
  if (preparedArguments === toolCall.arguments) {
    return toolCall;
  }
  return {
    ...toolCall,
    arguments: preparedArguments as Record<string, any>,
  };
}
```

没有 `prepareArguments` 就原样返回，本例走这一条。
若工具提供了该函数，就先用它整理参数，再交给 Schema 检查。

例如兼容旧字段：`{ file_path: "a.txt" } → { path: "a.txt" }`。
返回新参数对象时，这里浅复制 ToolCall，只替换 arguments；若预处理主动修改原对象，则也可能影响原调用。这个函数没有提前深复制。

返回下一句 `validateToolArguments(...)`，跳到 [validation.ts:292](../pi-master/packages/ai/src/utils/validation.ts#L292)。先抓住常规对象参数的处理顺序：

```text
structuredClone(toolCall.arguments)
  → 转换参数副本中的值
  → 按 tool.parameters 取得 validator
  → validator.Check(args)
  → 通过就返回 args；失败则整理原因并抛错
```

函数同时兼容 TypeBox 与普通 JSON Schema。应以转换后的数据为准，不能仅凭原参数里出现字符串就断言必然失败。非对象 JSON Schema 还有特殊返回分支，阅读时以实际源码为准；这里的教学工具使用对象 Schema。

本例 `{ values: [2, 3] }` 通过检查，得到 validatedArgs。
`{ values: [] }` 不满足 minItems，会进入准备函数的 catch。

**TypeScript 类型、JSON 解析、运行时校验分别发生在不同阶段。** Schema 通过也不等于业务权限通过，具体范围限制仍由工具或应用处理。

### 7.2 遇到 beforeToolCall，先看谁提供这个函数

返回 [agent-loop.ts:625](../pi-master/packages/agent/src/agent-loop.ts#L625)：

```ts
if (config.beforeToolCall) {
  const beforeResult = await config.beforeToolCall(
    {
      assistantMessage,
      toolCall,
      args: validatedArgs,
      context: currentContext,
    },
    signal,
  );
  if (beforeResult?.block) {
    return {
      kind: "immediate",
      result: createErrorToolResult(beforeResult.reason || "Tool execution was blocked"),
      isError: true,
    };
  }
}
```

调用者先组织参数对象，再 await 钩子。它同时提供原始 toolCall 与 validatedArgs，供应用检查。

函数值由 Agent 的选项保存，再在 [createLoopConfig:446](../pi-master/packages/agent/src/agent.ts#L446) 放入 config。未提供时跳过 if，不是默认阻止。

一个局部配置例子，假设 model 和 writeTool 已提供：

```ts
const agent = new Agent({
  initialState: { model, tools: [writeTool] },
  beforeToolCall: async ({ toolCall }) => {
    if (toolCall.name === "write") {
      return { block: true, reason: "此会话只允许读取" };
    }
    return undefined;
  },
});
```

返回 undefined 表示继续；`block: true` 表示返回错误结果。
钩子抛错也由准备阶段 catch 处理。开头示例提供的 before 只记录日志并放行，继续往下。

### 7.3 看返回形状，再回到 sequential 的 if

成功返回的位置在 [agent-loop.ts:644](../pi-master/packages/agent/src/agent-loop.ts#L644)：

```ts
return {
  kind: "prepared",
  toolCall,
  tool,
  args: validatedArgs,
};
```

成功对象中，tool 是找到的工具，args 是校验后的参数。
toolCall 仍保留原始调用块，供事件与结果关联使用。

本例返回值可记成：

```ts
{
  kind: "prepared",
  toolCall: C,                // A1 中原有的 sum-1
  tool: sumNumbersTool,       // find 找到的本地对象
  args: { values: [2, 3] },  // 校验后的参数副本
}
```

现在返回 [sequential:466](../pi-master/packages/agent/src/agent-loop.ts#L466) 的 await 后面。

| preparation.kind | 下一步 |
| --- | --- |
| `immediate` | 已有错误结果，跳过 execute 与 after |
| `prepared` | 进入 executePreparedToolCall |

本例为 prepared，所以接着进入第 475 行的执行调用。

## 8. 进入 executePreparedToolCall，真正调用 execute

### 8.1 把四个实参代入自己的求和函数

打开 [agent-loop.ts:660](../pi-master/packages/agent/src/agent-loop.ts#L660)：

```ts
async function executePreparedToolCall(
  prepared: PreparedToolCall,
  signal: AbortSignal | undefined,
  emit: AgentEventSink,
): Promise<ExecutedToolCallOutcome> {
  const updateEvents: Promise<void>[] = [];

  try {
    const result = await prepared.tool.execute(
      prepared.toolCall.id,
      prepared.args as never,
      signal,
      (partialResult) => {
        updateEvents.push(
          Promise.resolve(
            emit({
              type: "tool_execution_update",
              toolCallId: prepared.toolCall.id,
              toolName: prepared.toolCall.name,
              args: prepared.toolCall.arguments,
              partialResult,
            }),
          ),
        );
      },
    );
    await Promise.all(updateEvents);
    return { result, isError: false };
  } catch (error) {
    await Promise.all(updateEvents);
    return {
      result: createErrorToolResult(error instanceof Error ? error.message : String(error)),
      isError: true,
    };
  }
}
```

终于看到真正启动业务函数的语句：`await prepared.tool.execute(...)`。
**回扣第 6.1 节：find 用模型返回的 `"sum_numbers"` 找到了我们提供的 sumNumbersTool；准备结果把这个对象保存在 prepared.tool，这里才调用它真实的 execute 函数。**

| 传入的实参 | sum-tool.ts 中的形参 | 本例的值 |
| --- | --- | --- |
| `prepared.toolCall.id` | `_toolCallId` | `"sum-1"` |
| `prepared.args` | `{ values }` | values 为 `[2, 3]` |
| `signal` | `signal` | 本次取消信号 |
| 现场创建的回调 | `_onUpdate` | 用于报告阶段结果 |

`as never` 是静态类型断言，不会在运行时转换参数。运行时处理已在准备阶段完成。

进入自己的 execute，reduce 计算得到 5，return 交出：

```ts
{
  content: [{ type: "text", text: "总和为 5" }],
  details: { count: 2, total: 5 },
}
```

这对应 [AgentToolResult:291](../pi-master/packages/agent/src/types.ts#L291)：content 是要交给模型的正文；details 是结构化详情，供应用或界面使用；terminate 是可选的批次终止提示。

### 8.2 遇到回调，再看 onUpdate 什么时候调用

执行层把回调作为第四个实参交给工具。只有工具主动调用它，才会进入 `tool_execution_update` 的 emit。

需要进度时，工具可在执行中这样做：

```ts
onUpdate?.({
  content: [{ type: "text", text: "正在计算" }],
  details: { count: values.length, total: 0 },
});
```

回调发出的 Promise 被收进 updateEvents；函数在成功、异常路径都会等待这些通知。
但 **onUpdate 不会替你拼出最终结果**，最后仍要 return 完整 AgentToolResult。

本例的求和函数没有调用 `_onUpdate`，因此没有 update 事件。

### 8.3 看成功与异常怎样返回，再回到批次

正常结束返回 `{ result, isError: false }`。
工具抛错则由 catch 变成错误正文，并返回 `isError: true`。

失败应抛出异常；仅在 content 中写“失败”，不会自动让执行层设置 isError。
取消信号也需要工具配合：开始时检查 signal，长任务监听 abort，或传给支持取消的 I/O。

现在返回 sequential 的 `const executed = await ...` 后面。下一句是 `finalizeExecutedToolCall(...)`，继续进入后置处理。

## 9. 进入 finalize，再返回批次生成结果消息

### 9.1 afterToolCall 可以覆盖结果

打开 [finalizeExecutedToolCall:698](../pi-master/packages/agent/src/agent-loop.ts#L698)。函数先取 executed.result 与 isError，然后处理配置钩子；下面摘录钩子调用及覆盖逻辑：

```ts
let result = executed.result;
let isError = executed.isError;

if (config.afterToolCall) {
  try {
    const afterResult = await config.afterToolCall(
      {
        assistantMessage,
        toolCall: prepared.toolCall,
        args: prepared.args,
        result,
        isError,
        context: currentContext,
      },
      signal,
    );
    if (afterResult) {
      result = {
        content: afterResult.content ?? result.content,
        details: afterResult.details ?? result.details,
        terminate: afterResult.terminate ?? result.terminate,
      };
      isError = afterResult.isError ?? isError;
    }
  } catch (error) {
    result = createErrorToolResult(error instanceof Error ? error.message : String(error));
    isError = true;
  }
}

return {
  toolCall: prepared.toolCall,
  result,
  isError,
};
```

`afterToolCall` 的来源同样是 Agent 配置，经 [agent.ts:447](../pi-master/packages/agent/src/agent.ts#L447) 进入 config。
它能读取原调用、校验后参数、执行结果和当前上下文。

`??` 表示只有 null/undefined 才沿用原值。因此 isError 可以明确改为 false，terminate 也可以明确改为 false。
未设置钩子时保留执行结果；钩子抛错时改为错误结果。

准备阶段的 immediate 路径没有进入 execute，也不会进入这里的 after。
执行阶段抛错则仍会走 finalize，after 可以看到 isError。

函数最终返回 `{ toolCall, result, isError }`。开头示例的 after 只记录日志，返回 undefined；result 仍是“总和为 5”。

### 9.2 返回 sequential，先发结束事件

回到 [agent-loop.ts:486](../pi-master/packages/agent/src/agent-loop.ts#L486)：

```ts
await emitToolExecutionEnd(finalized, emit);
const toolResultMessage = createToolResultMessage(finalized);
await emitToolResultMessage(toolResultMessage, emit);
finalizedCalls.push(finalized);
messages.push(toolResultMessage);
```

先跳 [emitToolExecutionEnd:750](../pi-master/packages/agent/src/agent-loop.ts#L750)：

```ts
async function emitToolExecutionEnd(finalized: FinalizedToolCallOutcome, emit: AgentEventSink): Promise<void> {
  await emit({
    type: "tool_execution_end",
    toolCallId: finalized.toolCall.id,
    toolName: finalized.toolCall.name,
    result: finalized.result,
    isError: finalized.isError,
  });
}
```

这是工具生命周期的结束通知，事件中 result 仍是 AgentToolResult。
发完返回，进入下一句 `createToolResultMessage`。

### 9.3 把函数结果包装为 ToolResultMessage

打开 [agent-loop.ts:761](../pi-master/packages/agent/src/agent-loop.ts#L761)：

```ts
function createToolResultMessage(finalized: FinalizedToolCallOutcome): ToolResultMessage {
  return {
    role: "toolResult",
    toolCallId: finalized.toolCall.id,
    toolName: finalized.toolCall.name,
    content: finalized.result.content,
    details: finalized.result.details,
    isError: finalized.isError,
    timestamp: Date.now(),
  };
}
```

本例得到 R1，省略实际时间戳后是：

```ts
{
  role: "toolResult",
  toolCallId: "sum-1",
  toolName: "sum_numbers",
  content: [{ type: "text", text: "总和为 5" }],
  details: { count: 2, total: 5 },
  isError: false,
}
```

`toolCallId` 对上 A1 中的 id，表明这是谁的结果。
`toolName` 保存工具名称。函数返回值被包装成消息，才能放进对话历史。

再返回下一句，打开 [emitToolResultMessage:773](../pi-master/packages/agent/src/agent-loop.ts#L773)：

```ts
async function emitToolResultMessage(toolResultMessage: ToolResultMessage, emit: AgentEventSink): Promise<void> {
  await emit({ type: "message_start", message: toolResultMessage });
  await emit({ type: "message_end", message: toolResultMessage });
}
```

第 6 章追过的 [processEvents:530](../pi-master/packages/agent/src/agent.ts#L530) 会在 message_end 中执行 `this._state.messages.push(event.message)`。所以 R1 在这里进入 Agent 的状态历史。

`tool_execution_end` 负责工具状态通知；`message_end` 负责完成消息入历史。两种事件不能互相替代。

### 9.4 回到两个 push，再看 terminate

结果消息发完后，sequential 将 finalized、R1 分别收进两个数组。本项至此完成，for 才会处理下一项。

所有项完成后，返回 `{ messages, terminate }`。
terminate 的计算在 [agent-loop.ts:587](../pi-master/packages/agent/src/agent-loop.ts#L587)：

```ts
function shouldTerminateToolBatch(finalizedCalls: FinalizedToolCallOutcome[]): boolean {
  return finalizedCalls.length > 0 && finalizedCalls.every((finalized) => finalized.result.terminate === true);
}
```

非空批次中，**每项结果都明确设置 terminate: true**，批次才要求终止。一个 true 不够；普通错误结果也不会自动停止整个 run。

它在整批完成后统一计算，不会使 sequential 在中间提前 break。本例没有设置 terminate，得到 false。

## 10. 返回最初的 runLoop，闭合结果回传

### 10.1 批次返回以后，下一句做什么

回到 [agent-loop.ts:252](../pi-master/packages/agent/src/agent-loop.ts#L252)：

```ts
const executedToolBatch = await executeToolCalls(currentContext, message, config, signal, emit);
toolResults.push(...executedToolBatch.messages);
hasMoreToolCalls = !executedToolBatch.terminate;

for (const result of toolResults) {
  currentContext.messages.push(result);
  newMessages.push(result);
}
```

`executedToolBatch.messages` 是 `[R1]`。
先把它放进局部 toolResults；terminate 为 false，所以 hasMoreToolCalls 变成 true。

两个 push 分别更新本次循环历史和本次新增消息。
Agent 状态历史则已由前面的 message_end 更新。**不是一个 push 自动同步三个数组。**

下一轮 streamAssistantResponse 会读到 R1，再由模型生成最终文字 A2。正常轨迹是：

```text
U：用户要求计算 2 + 3
A1：助手提出 ToolCall(sum-1)
R1：工具结果“总和为 5”
A2：助手根据结果回答
```

这是一次用户提问、两次模型调用、一次工具执行。
工具 execute 本身不调用模型，工具返回值也不会自动成为 A2。

### 10.2 terminate 只先控制工具续跑条件

`hasMoreToolCalls = !terminate` 控制是否因本批工具结果继续调模型。它不是马上 return；runLoop 之后仍会处理 turn_end、steering 与 follow-up。

队列有消息时仍可能继续运行，完整控制关系回看第 06 章。本章先闭合工具输入输出，再看其他执行策略与来源。

## 11. 返回 executeToolCalls，第二遍再走 parallel

### 11.1 从另一个 return 进入并行函数

回 [executeToolCalls:438](../pi-master/packages/agent/src/agent-loop.ts#L438)。既无全局 sequential，也无工具要求 sequential 时，进入 [executeToolCallsParallel:500](../pi-master/packages/agent/src/agent-loop.ts#L500)。

此时 prepare、execute、finalize 都已认识，只需看它们的安排位置：

```text
第一个 for：逐项发 start，await prepare
  → immediate：直接得到错误结果并发 end
  → prepared：保存一个尚未调用的 async 函数

Promise.all：逐项调用保存的函数，启动 execute + finalize

第二个 for：按原调用顺序创建、发送 ToolResultMessage
```

关键启动点在 [agent-loop.ts:545](../pi-master/packages/agent/src/agent-loop.ts#L545)：

```ts
const orderedFinalizedCalls = await Promise.all(
  finalizedCalls.map((entry) => (typeof entry === "function" ? entry() : Promise.resolve(entry))),
);
```

`entry()` 才启动之前保存的执行函数。map 在这里调用所有执行项，然后 Promise.all 等它们完成。
因此第一轮准备仍是逐项 await，业务执行才并发；不能把整个函数说成“从头到尾全部并行”。

Promise.all 返回数组的顺序与输入一致，与谁先完成无关。end、update 通知可能按实际完成顺序交错，最终工具消息按原调用顺序发出。

### 11.2 两项调用时怎样看出差别

假设同一 A1 中有 C1、C2：

| 阶段 | sequential | parallel |
| --- | --- | --- |
| 准备 | 准备 C1 后执行 C1 | 先准备 C1、C2 |
| 执行 | C1 全部处理完再处理 C2 | 两项执行都启动，再统一等待 |
| 结果消息 | 每项完成即发送 | 等待完成后按 C1、C2 发送 |

两种路径共用 prepare、execute、finalize 与结果消息函数。
需要互斥的操作可声明 sequential；允许并发的工具仍要自己保证业务行为正确。

## 12. 从工具数组的另一种来源，追到 SDK 与扩展

### 12.1 遇到 ToolDefinition，先看四参为什么变五参

前面直接把 AgentTool 放入 initialState.tools。
编码会话的另一条路径使用 ToolDefinition，定义见 [extensions/types.ts:422](../pi-master/packages/coding-agent/src/core/extensions/types.ts#L422)。

它同样有名称、Schema 和 execute，还可包含 promptSnippet、promptGuidelines 与渲染信息。最关键的差别是 execute 多接收会话上下文 ctx。

进入 [wrapToolDefinition:6](../pi-master/packages/coding-agent/src/core/tools/tool-definition-wrapper.ts#L6)：

```ts
export function wrapToolDefinition<TDetails = unknown>(
  definition: ToolDefinition<any, TDetails>,
  ctxFactory?: () => ExtensionContext,
): AgentTool<any, TDetails> {
  return {
    name: definition.name,
    label: definition.label,
    description: definition.description,
    parameters: definition.parameters,
    prepareArguments: definition.prepareArguments,
    executionMode: definition.executionMode,
    execute: (toolCallId, params, signal, onUpdate) =>
      definition.execute(toolCallId, params, signal, onUpdate, ctxFactory?.() as ExtensionContext),
  };
}

```

包装器返回 AgentTool。Agent Loop 仍按四参调用；包装函数在被调用时执行 ctxFactory，再把第五个参数补给 definition.execute。

ctxFactory 的实际来源见 [extensions/wrapper.ts:18](../pi-master/packages/coding-agent/src/core/extensions/wrapper.ts#L18)：它使用 `() => runner.createContext()`。创建包装对象时没有马上取得 ctx，执行到这一次调用时才创建。

### 12.2 先定义，再登记，再启用

`defineTool()` 帮助保留类型推导并返回定义对象，见 [extensions/types.ts:480](../pi-master/packages/coding-agent/src/core/extensions/types.ts#L480)。
`pi.registerTool()` 把定义登记到扩展工具表，见 [extensions/loader.ts:208](../pi-master/packages/coding-agent/src/core/extensions/loader.ts#L208)。两者都不会当场执行求和。

会话在 [_refreshToolRegistry:2297](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2297) 汇总内置定义、扩展登记项与 SDK customTools，生成定义表和包装后的执行表。
再看 [setActiveToolsByName:819](../pi-master/packages/coding-agent/src/core/agent-session.ts#L819)：

```ts
setActiveToolsByName(toolNames: string[]): void {
  const tools: AgentTool[] = [];
  const validToolNames: string[] = [];
  for (const name of toolNames) {
    const tool = this._toolRegistry.get(name);
    if (tool) {
      tools.push(tool);
      validToolNames.push(name);
    }
  }
  this.agent.state.tools = tools;

  // Rebuild base system prompt with new tool set
  this._baseSystemPrompt = this._rebuildSystemPrompt(validToolNames);
  this.agent.state.systemPrompt = this._baseSystemPrompt;
}
```

这里才把实际启用的工具对象写入 `agent.state.tools`，同时重建系统提示词。后续运行取得新快照，就能被前面的 find 找到。

定义表保存完整说明与元信息；执行表保存可以交给 Agent Loop 调用的对象。仅登记但未启用的工具，不会自动进入当前请求。

```text
工具定义
  → registerTool / SDK customTools
  → 会话汇总与包装
  → setActiveToolsByName
  → agent.state.tools
  → 下一次运行的 currentContext.tools
  → prepareToolCall 的 find
```

正在运行的循环仍使用已取出的快照；状态数组赋新值，不会直接替换这一份数组。工具对象内部仍共享引用。

### 12.3 用同一个求和函数接 SDK

教学文件 `sum-definition.ts`：

```ts
import { defineTool } from "@mariozechner/pi-coding-agent";
import { sumNumbersTool } from "./sum-tool.js";

export const sumNumbersDefinition = defineTool({
  name: sumNumbersTool.name,
  label: sumNumbersTool.label,
  description: sumNumbersTool.description,
  parameters: sumNumbersTool.parameters,
  executionMode: sumNumbersTool.executionMode,
  promptSnippet: "计算数字数组的总和",
  promptGuidelines: ["求和时使用 sum_numbers，并根据结果回答。"],

  async execute(toolCallId, params, signal, onUpdate, _ctx) {
    return sumNumbersTool.execute(toolCallId, params, signal, onUpdate);
  },
});
```

这里显式写出五参 execute，最后再调用原来的四参函数。求和逻辑只有一份；用不到 ctx 就不读取它。

教学文件 `run-session-sum.ts`：

```ts
import type { Api, Model } from "@mariozechner/pi-ai";
import {
  type AuthStorage,
  createAgentSession,
  SessionManager,
} from "@mariozechner/pi-coding-agent";
import { sumNumbersDefinition } from "./sum-definition.js";

export async function runSessionSum(model: Model<Api>, authStorage: AuthStorage) {
  const { session } = await createAgentSession({
    model,
    authStorage,
    tools: ["sum_numbers"],
    customTools: [sumNumbersDefinition],
    sessionManager: SessionManager.inMemory(),
  });

  try {
    await session.prompt("请调用 sum_numbers 计算 2 与 3 的总和。");
    return session.agent.state.messages;
  } finally {
    session.dispose();
  }
}
```

`customTools` 提供定义，`tools` 提供允许启用的名称。调用方需提供模型与能解析凭据的 AuthStorage。

省略 tools 时按默认规则与其他工具共存；`tools: []` 会连自定义工具一起排除。SessionManager.inMemory 只在内存保存示例会话，定义见 [session-manager.ts:1325](../pi-master/packages/coding-agent/src/core/session-manager.ts#L1325)。

### 12.4 改用扩展入口时，先看登记动作

扩展文件 `index.ts`：

```ts
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { sumNumbersDefinition } from "./sum-definition.js";

export default function sumExtension(pi: ExtensionAPI) {
  pi.registerTool(sumNumbersDefinition);
}
```

将 index.ts、sum-definition.ts、sum-tool.ts 放在项目 `.pi/extensions/sum/` 目录，由扩展加载器发现入口。目录约定见 [extensions.md](../pi-master/packages/coding-agent/docs/extensions.md)。

加载入口时执行 registerTool；模型以后提出调用时，才执行工具的 execute。SDK 与扩展是两种接入方式，同一项工具通常选一种。

同名时要看实际登记顺序：本地 find 取首个匹配；会话 Map 中自定义工具覆盖同名内置项，SDK 自定义项后写入，可覆盖同名扩展项。相关写入见 [_refreshToolRegistry](../pi-master/packages/coding-agent/src/core/agent-session.ts#L2297)。选用明确、不冲突的工具名更容易追踪。

### 12.5 再沿 before/after 看扩展事件桥接

回到第 7、9 节出现的两个配置钩子。编码会话在 [_installAgentToolHooks:382](../pi-master/packages/coding-agent/src/core/agent-session.ts#L382) 给它们安装函数：

```text
beforeToolCall
  → runner.emitToolCall({ type: "tool_call", input: args, ... })
  → 扩展 pi.on("tool_call", handler)
  → 返回 block/reason 可阻止执行

afterToolCall
  → runner.emitToolResult({ type: "tool_result", content, details, ... })
  → 扩展 pi.on("tool_result", handler)
  → 返回覆盖字段，再回 finalize
```

扩展的 input 来自准备后的 args。before 桥接还会等待会话事件队列，保证此前事件已处理；具体代码见 [agent-session.ts:389](../pi-master/packages/coding-agent/src/core/agent-session.ts#L389)。

这里有三类名字，按所在位置区分：

| 名称 | 所在层 | 含义 |
| --- | --- | --- |
| `toolCall` | 助手 content | 模型提出的调用块 |
| `tool_execution_*` | Agent 事件 | 开始、进度、结束通知 |
| `tool_call` / `tool_result` | 扩展钩子 | 执行前干预、执行后修改 |

包装器负责补 ctx；before/after 桥接负责行为干预。它们在不同位置发挥作用。

## 13. 展开内置 write：从工具定义到真实文件写入

**本节固定一个例子：让 write 把 `Hello Pi` 写入 `output/hello.txt`，然后告诉用户写入结果。**

假设工作目录 cwd 为 `/course-demo`，模型正常提出调用，没有取消，也没有钩子阻止或改写结果。

### 13.1 从 createWriteTool(cwd) 找到定义与包装器

第 1.3 节已把 writeTool 放进 Agent。现在从创建位置跳到 [write.ts:279](../pi-master/packages/coding-agent/src/core/tools/write.ts#L279)：

```ts
export function createWriteTool(cwd: string, options?: WriteToolOptions): AgentTool<typeof writeSchema> {
  return wrapToolDefinition(createWriteToolDefinition(cwd, options));
}
```

先调用 createWriteToolDefinition，得到工具定义；再经第 12 节的包装器转成 AgentTool。

```text
createWriteTool("/course-demo")
  → createWriteToolDefinition("/course-demo")
  → wrapToolDefinition(定义)
  → 返回带 name、parameters、execute 的 writeTool
  → 应用把 writeTool 放进 initialState.tools
```

**创建工具对象时只保存函数；真正写文件，要等模型提出调用后再进入 execute。**

继续打开 [createWriteToolDefinition:181](../pi-master/packages/coding-agent/src/core/tools/write.ts#L181)，先对照熟悉的三个字段：

| 字段 | 自定义求和工具 | 内置 write |
| --- | --- | --- |
| name | sum_numbers | write |
| parameters | values 数字数组 | path、content 两个字符串 |
| execute | reduce 求和 | 创建目录、写入文件 |

参数 Schema 在 [write.ts:14](../pi-master/packages/coding-agent/src/core/tools/write.ts#L14)：

```ts
const writeSchema = Type.Object({
  path: Type.String({ description: "Path to the file to write (relative or absolute)" }),
  content: Type.String({ description: "Content to write to the file" }),
});
```

path 与 content 都必填。convertTools 将这份 Schema 连同名称、描述交给模型，让它知道 write 的用途和调用参数。

### 13.2 模型返回 write 调用，再用 name 找回真实对象

本例用户要求：

> 请调用 write，将 Hello Pi 写入 output/hello.txt，然后告诉我写入结果。

Provider 解析完模型响应后，A1.content 中包含：

```ts
{
  type: "toolCall",
  id: "write-1",
  name: "write",
  arguments: {
    path: "output/hello.txt",
    content: "Hello Pi",
  },
}
```

再停一次第 6.1 节的关键语句：

```ts
const tool = currentContext.tools?.find((t) => t.name === toolCall.name);
```

这次比较的是 `"write" === "write"`。find 返回第 1.3 节接入的 writeTool，其中保存真正的 execute 函数。

接下来校验 path、content；若配置了 beforeToolCall，则等待它放行。准备成功后，执行层传入：

```ts
await prepared.tool.execute(
  "write-1",
  { path: "output/hello.txt", content: "Hello Pi" },
  signal,
  onUpdate,
);
```

工具包装器再进入 write 定义的 execute。name 负责匹配工具，write-1 负责关联这一项调用与最终结果。

### 13.3 进入 execute：参数来自模型，cwd 来自闭包

打开 [write.ts:194](../pi-master/packages/coding-agent/src/core/tools/write.ts#L194)。先只看参数和路径处理，后续步骤暂时省略：

```ts
async execute(
  _toolCallId,
  { path, content }: { path: string; content: string },
  signal?: AbortSignal,
  _onUpdate?,
  _ctx?,
) {
  const absolutePath = resolveToCwd(path, cwd);
  const dir = dirname(absolutePath);
  // 接下来排队、创建目录、写入文件、返回结果。
}
```

这是定义对象中的方法摘录。
path、content 来自本次 arguments；cwd 则在创建工具定义时传入，由闭包保留。

| 变量 | 本例的值 | 来源 |
| --- | --- | --- |
| path | `"output/hello.txt"` | 模型返回的参数 |
| content | `"Hello Pi"` | 模型返回的参数 |
| cwd | `"/course-demo"` | 应用创建工具时传入 |
| absolutePath | `"/course-demo/output/hello.txt"` | resolveToCwd 计算 |
| dir | `"/course-demo/output"` | dirname 计算 |

相对路径与 cwd 如何拼接，可跳到 [path-utils.ts:54](../pi-master/packages/coding-agent/src/core/tools/path-utils.ts#L54) 的 resolveToCwd，再返回 write 的下一句。

### 13.4 先经过文件变更队列，再开始实际 I/O

接下来看 [write.ts:203](../pi-master/packages/coding-agent/src/core/tools/write.ts#L203)：

```ts
return withFileMutationQueue(
  absolutePath,
  // 原源码的第二个参数返回一个负责写入的 Promise。
  () => new Promise((resolve, reject) => {
    // 检查取消、创建目录、写入内容，最后 resolve 或 reject。
  }),
);
```

这段保留调用结构，内部写入步骤下一节再展开。

跳到 [file-mutation-queue.ts:19](../pi-master/packages/coding-agent/src/core/tools/file-mutation-queue.ts#L19)。这里为文件路径取得队列键，等待之前的操作，再调用传入的函数：

```text
取得当前文件的队列键
  → 找出它之前的 currentQueue
  → 为本项登记后续等待关系
  → await currentQueue
  → await fn()：现在才运行本项写入
  → finally 释放后续等待者，清理已完成队列
```

本例只有一次写入，没有前项可等，就继续执行。
如果当前模块中两次操作命中同一个队列键，后一次要等前一次结束；不同键的操作可以并行。

这里与 Agent 批次的 sequential 要分开看：

| 机制 | 控制范围 |
| --- | --- |
| executeToolCallsSequential | 本批调用一项接一项处理 |
| withFileMutationQueue | 按文件队列键安排文件变更，即使来自并发调用也先等待前项 |

队列控制先后，具体文件内容仍由接下来传入的写入函数决定。

### 13.5 沿 ops 进入 mkdir 与 writeFile

定义开头 [write.ts:185](../pi-master/packages/coding-agent/src/core/tools/write.ts#L185) 选择文件操作实现：

```ts
const ops = options?.operations ?? defaultWriteOperations;
```

本例没有传入 operations，使用 [write.ts:32](../pi-master/packages/coding-agent/src/core/tools/write.ts#L32)：

```ts
const defaultWriteOperations: WriteOperations = {
  writeFile: (path, content) => fsWriteFile(path, content, "utf-8"),
  mkdir: (dir) => fsMkdir(dir, { recursive: true }).then(() => {}),
};
```

fsWriteFile、fsMkdir 从 fs/promises 导入，见 [write.ts:3](../pi-master/packages/coding-agent/src/core/tools/write.ts#L3)。现在已经对上真实文件系统函数。

回到 execute 的 Promise 内部，先检查 signal、安装 abort 监听，然后在 [write.ts:221](../pi-master/packages/coding-agent/src/core/tools/write.ts#L221) 附近执行：

```ts
await ops.mkdir(dir);
if (aborted) return;
await ops.writeFile(absolutePath, content);
if (aborted) return;
```

代入本例：

```text
ops.mkdir("/course-demo/output")
  → 递归创建父目录；已有目录则继续

ops.writeFile("/course-demo/output/hello.txt", "Hello Pi")
  → 用 UTF-8 写入正文
  → 文件不存在时创建，存在时覆盖
```

**真正把内容写到文件中的，是这里的 ops.writeFile；前面的模型输出和 find 只是确定要调用什么、传入什么。**

执行结束后，本例文件的正文为：

```text
Hello Pi
```

工具只写入 content 字符串，本例没有追加换行。operations 也可以由应用替换，但本例沿默认本地写入实现阅读。

### 13.6 写入结束后，返回的是成功说明

接着看 [write.ts:227](../pi-master/packages/coding-agent/src/core/tools/write.ts#L227) 附近。清理监听后，通过 resolve 交出结果：

```ts
resolve({
  content: [
    { type: "text", text: `Successfully wrote ${content.length} bytes to ${path}` },
  ],
  details: undefined,
});
```

本例 `"Hello Pi".length` 为 8，所以实际成功正文为：

```text
Successfully wrote 8 bytes to output/hello.txt
```

注意同一个名字 content 在两处的含义：

| 位置 | 类型与本例的值 | 用途 |
| --- | --- | --- |
| 输入参数 content | 字符串 `"Hello Pi"` | 要写进文件的正文 |
| 返回对象 content | 包含成功说明的内容块数组 | 要交回模型的工具结果 |

正常返回后，执行层标记 isError: false；经过可选 afterToolCall，再包装成结果消息。省略 timestamp：

```ts
{
  role: "toolResult",
  toolCallId: "write-1",
  toolName: "write",
  content: [
    { type: "text", text: "Successfully wrote 8 bytes to output/hello.txt" },
  ],
  details: undefined,
  isError: false,
}
```

创建目录或写入抛错时，工具会 reject，执行层把它变成错误结果，再进入后置处理。取消与正常结束时的 abort 监听清理，也在这份实现中完成。

### 13.7 结果交回模型，再闭合整条写入路径

结果消息发出 message_end，并进入 currentContext.messages。下一次模型请求包含：

```text
U：请把 Hello Pi 写入 output/hello.txt
A1：ToolCall(write-1)，参数是 path 与 content
R1：write-1 的结果，“Successfully wrote 8 bytes ...”
```

两个 write-1 把调用和结果对应起来，转换过程沿用第 2.6 节。模型读到成功说明后，可以生成最终答复“已将 Hello Pi 写入 output/hello.txt”。

课堂按下面顺序逐次跳入、逐次返回：

```text
第 1.3 节：createWriteTool(cwd)，放进工具数组
  → convertTools：让模型知道 write 的名称、用途和参数
  → 模型返回 ToolCall(name="write", id="write-1")
  → find：按 name 找到真实 writeTool
  → 参数检查 → beforeToolCall
  → 包装后的 execute → write 定义的 execute
  → resolveToCwd、dirname：确定文件和父目录
  → withFileMutationQueue：等待同文件的前项
  → ops.mkdir → ops.writeFile：真正创建目录、写入文件
  → resolve 工具结果 → afterToolCall → ToolResultMessage
  → 下一次模型请求 → 最终文字回答
```

## 14. 走完源码后，用固定模型响应验证同一条路径

### 14.1 先分清直接调用与经过 Agent Loop

直接运行下面这句，只是调用工具函数：

```ts
const result = await sumNumbersTool.execute("direct-1", { values: [2, 3] });
```

它不会自动进行 prepare、Schema 校验、before/after、事件通知或消息入历史。要验证这些环节，应让真实 Agent Loop 收到一条助手 ToolCall。

### 14.2 固定两次响应，保留真实工具执行

复用第 1.1 节的 sum-tool.ts，另建教学文件 `verify-tools.ts`。
streamFn 第一次返回 sum-1，第二次返回结束消息。这里只替换模型响应，工具链仍由仓库代码执行，不需要连接模型服务或提供密钥。

getModel 只读取模型描述。reply 只发 done 终态，不验证 HTTP 与文字增量显示。

```ts
import assert from "node:assert/strict";
import { Agent, type AgentTool, type StreamFn } from "@mariozechner/pi-agent-core";
import {
  AssistantMessageEventStream,
  getModel,
  type AssistantMessage,
  type Message,
} from "@mariozechner/pi-ai";
import { sumNumbersTool, sumParameters, type SumDetails } from "./sum-tool.js";

const model = getModel("openai", "gpt-4.1-mini");

function reply(
  content: AssistantMessage["content"],
  reason: "toolUse" | "stop",
): AssistantMessageEventStream {
  const stream = new AssistantMessageEventStream();
  const message: AssistantMessage = {
    role: "assistant",
    content,
    api: model.api,
    provider: model.provider,
    model: model.id,
    usage: {
      input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
    },
    stopReason: reason,
    timestamp: 0,
  };
  stream.push({ type: "done", reason, message });
  return stream;
}

async function checkLoop(
  values: number[],
  block: boolean,
  expected: { before: number; execute: number; after: number; isError: boolean },
) {
  const calls = { before: 0, execute: 0, after: 0 };
  const requests: Message[][] = [];
  const events: string[] = [];
  const trackedTool: AgentTool<typeof sumParameters, SumDetails> = {
    ...sumNumbersTool,
    async execute(...args) {
      calls.execute += 1;
      return sumNumbersTool.execute(...args);
    },
  };
  const streamFn: StreamFn = (_model, context) => {
    requests.push(context.messages.slice());
    if (requests.length === 1) {
      return reply([{
        type: "toolCall", id: "sum-1", name: "sum_numbers",
        arguments: { values },
      }], "toolUse");
    }
    return reply([{ type: "text", text: "工具结果已收到" }], "stop");
  };
  const agent = new Agent({
    initialState: { model, tools: [trackedTool] },
    streamFn,
    toolExecution: "sequential",
    beforeToolCall: async () => {
      calls.before += 1;
      return block ? { block: true, reason: "此用例阻止执行" } : undefined;
    },
    afterToolCall: async () => {
      calls.after += 1;
      return undefined;
    },
  });
  const unsubscribe = agent.subscribe((event) => { events.push(event.type); });
  try {
    await agent.prompt("运行一次求和工具");
  } finally {
    unsubscribe();
  }

  assert.equal(agent.state.errorMessage, undefined);
  assert.equal(requests.length, 2);
  assert.deepEqual(calls, {
    before: expected.before, execute: expected.execute, after: expected.after,
  });
  assert.deepEqual(agent.state.messages.map((m) => m.role), [
    "user", "assistant", "toolResult", "assistant",
  ]);
  const result = agent.state.messages.find((m) => m.role === "toolResult");
  assert.ok(result?.role === "toolResult");
  assert.equal(result.toolCallId, "sum-1");
  assert.equal(result.toolName, "sum_numbers");
  assert.equal(result.isError, expected.isError);
  const text = result.content
    .filter((part) => part.type === "text")
    .map((part) => part.text).join("\n");
  if (!expected.isError) {
    assert.equal(text, "总和为 5");
    assert.deepEqual(result.details, { count: 2, total: 5 });
  } else if (block) {
    assert.equal(text, "此用例阻止执行");
  } else {
    assert.match(text, /Validation failed for tool "sum_numbers"/);
  }
  const suppliedToModel = requests[1].find((m) => m.role === "toolResult");
  assert.deepEqual(suppliedToModel, result);
  assert.equal(events.filter((type) => type === "tool_execution_start").length, 1);
  assert.equal(events.filter((type) => type === "tool_execution_end").length, 1);
  assert.equal(events.at(-1), "agent_end");
}

const direct = await sumNumbersTool.execute("direct-1", { values: [2, 3] });
assert.deepEqual(direct.details, { count: 2, total: 5 });

await checkLoop([2, 3], false, { before: 1, execute: 1, after: 1, isError: false });
await checkLoop([], false, { before: 0, execute: 0, after: 0, isError: true });
await checkLoop([2, 3], true, { before: 1, execute: 0, after: 0, isError: true });
console.log("工具函数与三组 Agent 工具链断言通过");
```

每组新建 Agent，避免上一组历史干扰。本例显式选择 sequential，与第一遍源码阅读一致。

| 输入条件 | before | execute | after | 工具结果 |
| --- | ---:| ---:| ---:| --- |
| `[2, 3]`，放行 | 1 | 1 | 1 | 总和为 5 |
| `[]`，参数不合格 | 0 | 0 | 0 | Schema 错误 |
| `[2, 3]`，before 阻止 | 1 | 0 | 0 | 阻止原因 |

脚本还检查第二次模型输入是否真的包含 R1。prompt 完成后检查状态与消息，避免只凭最终一句文字判断执行成功。

### 14.3 在哪里运行、在哪里设断点

将 sum-tool.ts 与 verify-tools.ts 放入 Pi 项目的 `packages/coding-agent/examples/sdk/course-tools/`。已有项目依赖与可用 Node 环境时，从 Pi 根目录运行：

```sh
./node_modules/.bin/tsx --tsconfig tsconfig.json packages/coding-agent/examples/sdk/course-tools/verify-tools.ts
```

根 tsconfig 的路径映射让包名指向项目源码。离线检查覆盖固定程序分支；再运行第 1.2 节的真实模型入口，才能观察模型是否按描述提出工具调用。

| 暂停位置 | 要看什么 |
| --- | --- |
| `executeToolCalls` | 配置如何选中 sequential |
| `prepareToolCall` 的 find | name 能否找到工具对象 |
| `validateToolArguments` | 原参数与校验后副本 |
| `beforeToolCall` 返回处 | 是否 block |
| `prepared.tool.execute` | 四个实参是否对上 |
| 自己的 execute | values 是否为 `[2, 3]` |
| `createToolResultMessage` | ID、content、isError |
| streamFn 第二次调用 | 模型输入中是否已有 R1 |

以上是可运行的教学脚本；示例输出只有实际执行成功后才会打印。

## 15. 再回起点，按 IDE 跳转顺序重走一遍

这次不倒推整条模型请求。只带着 sum-1，从上一章停下的位置向前：

```text
runLoop：filter 得到 toolCall
  → executeToolCalls：判断执行模式
    → executeToolCallsSequential：for 取出 sum-1
      → emit start
      → prepareToolCall
        → find：用模型返回的 name 匹配真实工具对象，再回查 tools 来源
        ← 返回 find 后面
        → prepareToolCallArguments
        ← 返回 validateToolArguments，校验得到 args
        → beforeToolCall
        ← 返回 prepared
      ← 返回 sequential 的 kind 判断
      → executePreparedToolCall
        → sumNumbersTool.execute(id, args, signal, onUpdate)
        ← 返回 content/details
      ← 返回 sequential 的 executed
      → finalizeExecutedToolCall：可选 after
      ← 返回 finalized
      → emitToolExecutionEnd
      → createToolResultMessage
      → emitToolResultMessage：message_end 保存 Agent 历史
      → 收集 finalized 与 R1
    ← 返回 messages/terminate
  ← 返回 runLoop，追加 currentContext/newMessages
  → 下一次模型请求读到 R1，生成 A2
```

遇到问题时，先找数据在哪一步改变：模型没提出调用，看 A1.content；找不到工具，看当前工具数组和 name；没有进 execute，看准备阶段；模型不知道结果，看 R1.content 与下一次请求。

Provider 负责协议转换，执行层负责调用本地能力，会话层负责汇总与启用。每个跳转都能对上输入和返回值，整条工具路径就连起来了。

## 16. 单节总结：一个工具怎样从代码变成 JSON，再被找到并执行

本节可以独立阅读。只看一个任务：用户要求计算 `2 + 3`，我们提供 `sum_numbers` 工具，模型提出调用，本地执行后得到 `5`。

固定使用本仓库的 **OpenAI Chat Completions** 路径。以下 JSON 只展示相关字段，调用 ID `sum-1` 和模型响应为教学示例，不是实际请求记录。这里所说的 invoke 是“调用工具函数”这个动作，**Pi 源码中的方法名是 `execute`**，对应的实际语句是 `await prepared.tool.execute(...)`。

### 16.1 第一步：我们写出来的是一个带 execute 函数的工具对象

下面把第 1.1 节的工具重新放在一起，便于直接对照后面的 JSON；参数约束与求和逻辑保持一致：

```ts
import type { AgentTool } from "@mariozechner/pi-agent-core";
import { Type } from "typebox";

const sumParameters = Type.Object(
  {
    values: Type.Array(
      Type.Number({ minimum: -1_000_000, maximum: 1_000_000 }),
      { minItems: 1, maxItems: 100, description: "需要相加的数字" },
    ),
  },
  { additionalProperties: false },
);

const sumNumbersTool: AgentTool<
  typeof sumParameters,
  { count: number; total: number }
> = {
  name: "sum_numbers",
  label: "数字求和",
  description: "计算一组数字的总和。需要准确相加时使用，参数 values 为数字数组。",
  parameters: sumParameters,
  executionMode: "parallel",

  async execute(_toolCallId, { values }, signal, _onUpdate) {
    if (signal?.aborted) throw new Error("求和已取消");
    const total = values.reduce((sum, value) => sum + value, 0);
    return {
      content: [{ type: "text", text: `总和为 ${total}` }],
      details: { count: values.length, total },
    };
  },
};
```

应用通过 `initialState: { tools: [sumNumbersTool], ... }` 把它交给 Agent，完整接入代码见第 1.2 节。此时，程序内存中的关系是：

```text
工具数组
  └─ sumNumbersTool
       ├─ name："sum_numbers"
       ├─ description：用途说明
       ├─ parameters：参数 Schema 对象
       └─ execute：真正执行 reduce 的函数
```

**这时只是保存了函数，还没有计算。** Agent 创建运行快照时，用 `tools.slice()` 复制数组，数组元素仍引用这些工具对象，见 [agent.ts:425](../pi-master/packages/agent/src/agent.ts#L425)。

### 16.2 第二步：程序提取说明字段，生成发给 OpenAI 的 JSON

[buildParams](../pi-master/packages/ai/src/providers/openai-completions.ts#L435) 中执行：

```ts
params.tools = convertTools(context.tools, compat);
```

[convertTools](../pi-master/packages/ai/src/providers/openai-completions.ts#L894) 为每个工具创建协议对象，核心字段映射如下；这里省略兼容判断，直接写出本例支持的 `strict: false`：

```ts
// 转换逻辑示意：从工具对象中选取字段，构造新的说明对象。
{
  type: "function",
  function: {
    name: tool.name,
    description: tool.description,
    parameters: tool.parameters,
    strict: false,
  },
}
```

`convertTools` 返回的是 JavaScript 对象数组，SDK 随后把请求参数序列化成 HTTP 请求中的 JSON 文本。第一次请求的相关部分长这样，`model` 的值取自调用方选定的 `model.id`，下面以 `gpt-4.1-mini` 示意：

```json
{
  "model": "gpt-4.1-mini",
  "stream": true,
  "messages": [
    {
      "role": "user",
      "content": "请调用 sum_numbers 计算 2 与 3 的总和，并给出结果。"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "sum_numbers",
        "description": "计算一组数字的总和。需要准确相加时使用，参数 values 为数字数组。",
        "parameters": {
          "type": "object",
          "properties": {
            "values": {
              "type": "array",
              "items": {
                "type": "number",
                "minimum": -1000000,
                "maximum": 1000000
              },
              "minItems": 1,
              "maxItems": 100,
              "description": "需要相加的数字"
            }
          },
          "required": ["values"],
          "additionalProperties": false
        },
        "strict": false
      }
    }
  ]
}
```

模型由 `name` 知道工具叫什么，由 `description` 知道何时使用，由 `parameters` 知道参数结构和约束。具体的 `[2, 3]` 由模型根据用户问题填入下一步的调用。

**发出去的是工具说明；`execute` 函数仍保存在本地对象里。** `label`、`executionMode` 也没有进入这份工具说明。这里并非把整个对象转成 JSON 后丢弃原对象，而是另外构造了一份供模型读取的数据。

### 16.3 第三步：OpenAI 返回 JSON，表示要调用哪个工具、传什么参数

Pi 这条路径设置了 `stream: true`，实际接收的是流式响应。为了看清结构，假设本例在一个 chunk 中给齐工具名和参数；下面是该 chunk 的相关 JSON 字段：

```json
{
  "choices": [
    {
      "index": 0,
      "delta": {
        "tool_calls": [
          {
            "index": 0,
            "id": "sum-1",
            "type": "function",
            "function": {
              "name": "sum_numbers",
              "arguments": "{\"values\":[2,3]}"
            }
          }
        ]
      },
      "finish_reason": null
    }
  ]
}
```

后续结束 chunk 的相关字段可以是：

```json
{
  "choices": [
    {
      "index": 0,
      "delta": {},
      "finish_reason": "tool_calls"
    }
  ]
}
```

这表示：“我要调用 `sum_numbers`，本次调用 ID 为 `sum-1`，参数是 `{"values":[2,3]}`。”其中 **`function.arguments` 是字符串**，外层 JSON 中的双引号因此需要转义。它也可能分多个 chunk 到达，详细拼接过程见第 2.3—2.4 节。

模型到这里给出的是调用请求，求和函数尚未执行。

### 16.4 第四步：Provider 把协议数据解析为 Pi 的 ToolCall

[Provider 的接收逻辑](../pi-master/packages/ai/src/providers/openai-completions.ts#L281) 汇总增量，并用 `parseStreamingJson` 解析参数。等助手消息完整返回，Pi 的 `content` 中就有下面这个调用块：

```ts
const toolCall = {
  type: "toolCall",
  id: "sum-1",
  name: "sum_numbers",
  arguments: { values: [2, 3] },
};
```

这时 `arguments` 已经是对象，可以用于后续参数检查。字段对应关系是：

| OpenAI 响应中的字段 | Pi 调用块中的字段 | 本例的值 |
| --- | --- | --- |
| `tool_calls[i].id` | `toolCall.id` | `"sum-1"` |
| `tool_calls[i].function.name` | `toolCall.name` | `"sum_numbers"` |
| `tool_calls[i].function.arguments` | 解析后的 `toolCall.arguments` | `{ values: [2, 3] }` |

### 16.5 第五步：find 按名称找到本地原对象，再调用它的 execute

进入 [prepareToolCall](../pi-master/packages/agent/src/agent-loop.ts#L606)，关键就是用户关注的这一行：

```ts
const tool = currentContext.tools?.find((t) => t.name === toolCall.name);
```

把本例的值代进去：

```ts
// currentContext.tools 中有第一步交给 Agent 的 sumNumbersTool。
// 模型返回的 toolCall.name 为 "sum_numbers"。
const tool = currentContext.tools?.find((t) => t.name === "sum_numbers");

// 在本例未替换工具的前提下：
tool === sumNumbersTool; // true
```

**`find` 返回数组中那个已有的工具对象，因此也拿到了它保存的 `execute` 函数。** 这里没有根据 JSON 重新生成工具代码。

找到工具后，源码先准备、校验参数，并运行可选的 `beforeToolCall`；通过后返回准备结果。下面是相关语句摘录，中间处理省略：

```ts
const preparedToolCall = prepareToolCallArguments(tool, toolCall);
const validatedArgs = validateToolArguments(tool, preparedToolCall);
// 如果配置了 beforeToolCall，在这里等待检查并确认未阻止执行。
return {
  kind: "prepared",
  toolCall,
  tool,
  args: validatedArgs,
};
```

接着在 [executePreparedToolCall](../pi-master/packages/agent/src/agent-loop.ts#L660) 中执行。下列调用保留源码四个实参的位置，省略进度回调内部的事件发送：

```ts
const result = await prepared.tool.execute(
  prepared.toolCall.id,
  prepared.args as never,
  signal,
  (partialResult) => {
    // 源码在这里发送 tool_execution_update 事件。
  },
);
```

对于本例，它调用的就是第一步定义的 `sumNumbersTool.execute`，也就是下面这个函数：

```ts
  async execute(_toolCallId, { values }, signal, _onUpdate) {
    if (signal?.aborted) throw new Error("求和已取消");
    const total = values.reduce((sum, value) => sum + value, 0);
    return {
      content: [{ type: "text", text: `总和为 ${total}` }],
      details: { count: values.length, total },
    };
  },
```

第一个参数为 `"sum-1"`，第二个参数为 `{ values: [2, 3] }`，其余两个参数是取消信号和进度回调。`as never` 只是 TypeScript 类型断言，不改变运行时参数。

**这次函数调用才进入我们写的函数体**，运行 `values.reduce(...)`，返回：

```ts
{
  content: [{ type: "text", text: "总和为 5" }],
  details: { count: 2, total: 5 },
}
```

### 16.6 第六步：把执行结果发回模型，让它完成回答

本地结果经过可选的 `afterToolCall`，包装成工具结果消息并加入历史。下一次请求中，调用和结果的相关消息会转换成：

```json
[
  {
    "role": "assistant",
    "tool_calls": [
      {
        "id": "sum-1",
        "type": "function",
        "function": {
          "name": "sum_numbers",
          "arguments": "{\"values\":[2,3]}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "sum-1",
    "content": "总和为 5"
  }
]
```

上面只摘出消息历史中的调用与结果；完整请求还带用户问题和工具说明。`tool_call_id` 把结果对应到本次 `sum-1` 调用，模型读到结果后，就可以回答“2 与 3 的总和是 5”。本例发送给模型的是 `content` 正文，`details` 留给本地应用使用。

把整个过程放在一条线上：

```text
我们定义 sumNumbersTool（对象内保存 execute 函数）
  → convertTools 提取 name、description、parameters
  → SDK 将工具说明序列化为请求 JSON，发给 OpenAI
  → 模型返回 tool_calls：name="sum_numbers"，arguments 为 JSON 字符串
  → Provider 拼接、解析，得到 Pi 的 toolCall，arguments 变成对象
  → find 按 name 找到原来的 sumNumbersTool 对象
  → 参数准备、校验、可选 before 检查
  → prepared.tool.execute(...) 调用我们写好的函数，算出 5
  → 结果以 role="tool"、tool_call_id="sum-1" 发回模型
  → 模型根据工具结果生成最终回答
```

