# 05 pi-agent-core 源码讲解：从 prompt 一路追到 OpenAI 流式调用

这一章我们换一种读源码的方式：从一段能看懂的使用代码开始，碰到一个函数，就去找它的定义，看看它又调用了谁。

我们要弄清楚的是：**写下 `await agent.prompt("Hello!")` 以后，程序怎样把这句话交给模型，又怎样把模型逐段返回的文字送到屏幕上。**

本章对照当前工作区的 `pi-master/` 源码，包版本为 `0.69.0`。下面的行号按当前这份文件标注，后续修改源码时可能移动，可以同时搜索函数名。为了方便阅读，源码摘录会去掉注释；截取的是函数中的一段时，正文会说明范围。另行编写的例子标为“教学示例”，不把它当作原仓库代码。

先从 `ai/src/models.ts` 把模型配置登记进 Map 讲起，看 `getModel()` 怎样查出配置并交给 Agent；再顺着 `prompt()` 往下走，一直看到 OpenAI SDK 发出请求，最后沿返回的内容往上走。第 1—12 节沿入口追到具体 Provider，第 13 节把 SDK 请求、事件转换和返回值连起来，第 14 节集中讲 `subscribe`、`emit` 和 `processEvents`，已有的事件例子也放在那里。

**例子怎么读：**从开头就固定使用 OpenAI Chat Completions：用户输入 `Hello!`，假设模型分两次返回 `H` 和 `i!`。每次跳进函数，都先对上“调用处的实参 → 定义处的形参”，再找它使用的字段和下一次调用。U、A、H1 等只是消息对象的简称，其中 A 表示助手消息；模型配置统一叫 `model`，不要把两者混在一起。例子用于读源码，不是实际请求日志，示例 Key 也只是占位文字。

## 1. 从 OpenAI 使用代码开始：先追清 model 到底是什么

原始 Quick Start 在 [pi-master/packages/agent/README.md，第 14 行](../pi-master/packages/agent/README.md#L14)。原文选择的是 Claude。本章根据它改成下面这段**教学示例**，从第一步就固定 OpenAI 分支，后面不再中途换模型：

```ts
import { Agent } from "@mariozechner/pi-agent-core";
import { getModel, type Model } from "@mariozechner/pi-ai";

const catalogModel = getModel("openai", "gpt-4o-mini");
const model: Model<"openai-completions"> = {
  ...catalogModel,
  api: "openai-completions",
  compat: {},
};

const agent = new Agent({
  initialState: {
    systemPrompt: "You are a helpful assistant.",
    model,
  },
});

agent.subscribe((event) => {
  if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
    // Stream just the new text chunk
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});

await agent.prompt("Hello!");
```

先把这段代码分成三件事：准备模型配置并创建 Agent、登记监听函数、调用 `prompt`。我们先把第一件事展开：在 `getModel()` 查模型之前，模型配置已经在哪里准备好了？先看登记，再看查询，否则后面读到 `model.api` 就会不知道它从哪里来。

### 1.1 models.ts 怎样注册模型：先把模型表装进两层 Map

打开 [pi-master/packages/ai/src/models.ts，第 1—13 行](../pi-master/packages/ai/src/models.ts#L1)。下面去掉了类型导入和注释，保留导入模型表、创建 Map 和初始化的代码：

```ts
import { MODELS } from "./models.generated.js";

const modelRegistry: Map<string, Map<string, Model<Api>>> = new Map();

for (const [provider, models] of Object.entries(MODELS)) {
  const providerModels = new Map<string, Model<Api>>();
  for (const [id, model] of Object.entries(models)) {
    providerModels.set(id, model as Model<Api>);
  }
  modelRegistry.set(provider, providerModels);
}
```

**这里的“注册模型”，就是把本地已有的模型配置对象放进 Map，供后面的代码查询。** 当前这份 `models.ts` 通过文件顶层的循环完成内置模型登记，没有一个供这里调用的 `registerModel()` 函数。也不需要把模型权重下载到本机；配置里保存的是模型名称、协议、服务地址、能力和价格等信息。

数据来自 [models.generated.ts，第 6 行](../pi-master/packages/ai/src/models.generated.ts#L6) 导出的 `MODELS` 对象。它按“服务商 → 模型 ID → 配置对象”组织。用本章要找的模型表示，结构是下面这样，其他项省略：

```text
MODELS
  └─ "openai"                       服务商名称
       └─ "gpt-4o-mini"              模型 ID
            ├─ id: "gpt-4o-mini"
            ├─ api: "openai-responses"
            ├─ provider: "openai"
            ├─ baseUrl: "https://api.openai.com/v1"
            └─ 其他模型配置字段
```

现在把这组数据代进循环，逐句看两个 `.set(...)` 在做什么：

| 源码中的位置 | 遍历到 OpenAI 这一组时的值或动作 |
| --- | --- |
| `Object.entries(MODELS)` | 把外层对象转成一组组键值对；当前 `provider` 是 `"openai"`，`models` 是这一家的模型配置集合 |
| `new Map<string, Model<Api>>()` | 为这一家创建一张模型 Map，保存在 `providerModels` 中 |
| `Object.entries(models)` | 继续遍历这家提供的模型；当前 `id` 是 `"gpt-4o-mini"`，`model` 是它的配置对象 |
| `providerModels.set(id, model as Model<Api>)` | 用模型 ID 作键，把配置对象存进这家自己的 Map |
| `modelRegistry.set(provider, providerModels)` | 等这一家的模型都放好后，用服务商名称作键，把整张模型 Map 存进总表 |

`Map<string, Map<string, Model<Api>>>` 看着长，按外层和内层拆开就能读懂：外层通过服务商名称找到一张 Map，内层再通过模型 ID 找到配置对象。最终的数据关系如下：

```text
modelRegistry                          外层 Map
  └─ "openai" → providerModels         内层 Map
                    └─ "gpt-4o-mini" → 模型配置对象
```

为什么要分两层？因为模型是在某家服务商下面选择的。即使两家服务提供相同的模型 ID，它们的服务地址、凭据和配置也可能不同。用服务商和模型 ID 一起定位，就能区分这些配置。

还有一个容易忽略的地方：**这段循环写在模块顶层，首次加载 `models.ts` 对应模块时就会执行。** 它没有包在 `getModel()` 里面。通过包入口导入 `getModel` 时，相关模块会先完成初始化；业务代码执行 `getModel(...)` 时，内置模型已经登记好了。

`model as Model<Api>` 是类型断言，存进去的仍是模型表里的那个对象，没有复制，也没有在这里改写 `api`。初始化完成后，下一步就是根据两个键把对象取出来。

### 1.2 getModel 的两个参数，分别到哪里去了

`getModel` 从包入口 [pi-master/packages/ai/src/index.ts，第 6 行](../pi-master/packages/ai/src/index.ts#L6) 导出：

```ts
export * from "./models.js";
```

所以按住 `getModel` 跳转，要进入 [pi-master/packages/ai/src/models.ts，第 20 行](../pi-master/packages/ai/src/models.ts#L20)。完整函数如下：

```ts
export function getModel<TProvider extends KnownProvider, TModelId extends keyof (typeof MODELS)[TProvider]>(
  provider: TProvider,
  modelId: TModelId,
): Model<ModelApi<TProvider, TModelId>> {
  const providerModels = modelRegistry.get(provider);
  return providerModels?.get(modelId as string) as Model<ModelApi<TProvider, TModelId>>;
}
```

把教学示例的调用和函数定义按位置对上：

| 调用处的实参 | 定义处的形参 | 使用位置 | 本次结果 |
| --- | --- | --- | --- |
| `"openai"` | `provider` | [models.ts，第 24 行](../pi-master/packages/ai/src/models.ts#L24)：`modelRegistry.get(provider)` | 取出 OpenAI 的模型 Map |
| `"gpt-4o-mini"` | `modelId` | [models.ts，第 25 行](../pi-master/packages/ai/src/models.ts#L25)：`providerModels?.get(modelId as string)` | 从这张 Map 取出模型配置对象 |

这里传进去的是两个字符串，返回的是一个对象。`getModel` 的参数里没有 `api`；`api` 在返回的对象里面。它不下载模型、不发送请求，也没有在函数体中根据 `"openai"` 临时计算协议。

把刚才的登记和现在的查询放在一起，就是一组对应操作：

```text
加载模块时登记：
  providerModels.set("gpt-4o-mini", 模型配置对象)
  modelRegistry.set("openai", providerModels)

业务代码中查询：
  getModel("openai", "gpt-4o-mini")
    → modelRegistry.get("openai")
    → providerModels.get("gpt-4o-mini")
    → 返回先前登记的模型配置对象
```

**教学示例：先选模型，再交给 Agent。** 下面只是演示配置的使用方式，不发起模型请求：

```ts
const selectedModel = getModel("openai", "gpt-4o-mini");

console.log(selectedModel.id);       // "gpt-4o-mini"
console.log(selectedModel.provider); // "openai"
console.log(selectedModel.api);      // "openai-responses"

const selectedAgent = new Agent({
  initialState: { model: selectedModel },
});
```

`getModel()` 完成“选中哪份配置”，`initialState.model` 完成“把配置交给 Agent”。这个小例子保留模型表中的 Responses 协议；本章开头为了讲 Chat Completions，还会在两步之间复制配置并覆盖 `api`，下一小节接着解释。

同文件还有两个配套查询：[models.ts，第 28 行](../pi-master/packages/ai/src/models.ts#L28) 的 `getProviders()` 列出外层 Map 的服务商名称，[第 32 行](../pi-master/packages/ai/src/models.ts#L32) 的 `getModels("openai")` 则取出这家内层 Map 中的所有模型配置。它们和 `getModel` 读取的是同一份登记结果。

这里也先和后面的 API 注册表划清职责：`modelRegistry` 保存“服务商、模型 ID 对应哪份配置”，后面要看的 `apiProviderRegistry` 保存“协议名称对应哪些调用函数”。所以程序先用 `getModel` 选配置，再根据配置里的 `api` 找到实际调用实现。这是前后衔接的两次查询。

### 1.3 返回对象里的 api，是谁先写进去的

刚才登记进去的模型配置，来自导入的 `MODELS`。接下来具体看它的 `api` 字段。

进入 [models.generated.ts，第 5685 行](../pi-master/packages/ai/src/models.generated.ts#L5685)，找到 `"openai"` 分组，再到 [第 5839 行](../pi-master/packages/ai/src/models.generated.ts#L5839) 找到 `"gpt-4o-mini"`。下面只摘录决定调用方向的字段，其他字段省略：

```ts
"gpt-4o-mini": {
  id: "gpt-4o-mini",
  name: "GPT-4o mini",
  api: "openai-responses",
  provider: "openai",
  baseUrl: "https://api.openai.com/v1",
  // 其余字段省略
}
```

**本地这份模型表的 `api` 在第 5842 行已经写成了 `"openai-responses"`。** 模块初始化时把这个对象放入 Map；`getModel` 只是把对象取出来。不要因为第一参数是 `"openai"`，就以为 `api` 也等于 `"openai"`。

如果再问“生成文件里的值是谁决定的”，可以继续看 [scripts/generate-models.ts，第 281 行](../pi-master/packages/ai/scripts/generate-models.ts#L281)：处理 OpenAI 模型时，第 289 行设置 `api: "openai-responses"`；[第 1586 行](../pi-master/packages/ai/scripts/generate-models.ts#L1586) 把 `model.api` 写入生成内容，[第 1618 行](../pi-master/packages/ai/scripts/generate-models.ts#L1618) 写出 `src/models.generated.ts`。这是生成模型表的过程，普通 `getModel(...)` 调用不会重新运行生成脚本。

因此开头的教学示例分了两步：

```ts
const catalogModel = getModel("openai", "gpt-4o-mini");
// catalogModel.api === "openai-responses"，来自模型表。

const model: Model<"openai-completions"> = {
  ...catalogModel,
  api: "openai-completions",
  compat: {},
};
// model.api === "openai-completions"，来自教学示例的显式赋值。
```

对象展开先复制已有字段，后面的 `api` 覆盖前面的值；得到的是新对象，原模型表里的对象保持原值。`compat: {}` 让新配置不沿用另一协议的兼容选项。这样做是为了明确阅读 Chat Completions 这条实现，实际调用还需要服务端支持相应协议。

`Model<"openai-completions">` 是类型约束，定义在 [pi-master/packages/ai/src/types.ts，第 394 行](../pi-master/packages/ai/src/types.ts#L394)，其中第 397 行是 `api: TApi`。类型标注负责检查字段；运行时的字符串值来自对象里的 `api: "openai-completions"` 赋值。

### 1.4 initialState.model 又怎样进入 Agent 内部

开头的 `initialState: { model }` 是属性简写，等价于 `initialState: { model: model }`。把刚准备好的模型对象作为构造选项传进去。

打开 [agent.ts，第 207 行](../pi-master/packages/agent/src/agent.ts#L207)：

```ts
constructor(options: AgentOptions = {}) {
  this._state = createMutableAgentState(options.initialState);
  // 后续初始化省略
}
```

再进 [agent.ts，第 78 行](../pi-master/packages/agent/src/agent.ts#L78) 的 `createMutableAgentState`，看它返回对象中的 [第 86 行](../pi-master/packages/agent/src/agent.ts#L86)：

```ts
model: initialState?.model ?? DEFAULT_MODEL,
```

本例已经传了 `initialState.model`，所以选它。这里直接保存模型对象的引用，没有重新调用 `getModel`，也没有改写 `api`。后面 `this._state.model` 就是教学示例准备的那个对象。

到这里先记下模型的来路：

```text
models.generated.ts:5842       原始 api = "openai-responses"
  → models.ts:10、12            模块初始化：放进模型 Map
  → models.ts:24、25            getModel("openai", "gpt-4o-mini") 取回对象
  → 教学示例的对象展开与赋值     新对象的 api = "openai-completions"
  → new Agent({ initialState: { model } })
  → agent.ts:208、85            保存为 this._state.model
```

### 1.5 保存监听函数，然后才调用 prompt

模型配置准备好后，**第二件事是登记一个接收通知的函数。** `agent.subscribe(...)` 的意思是：“后面运行中有什么变化，就调用这个函数告诉我。”此时只是登记，还没有向模型提问。

这几行先记住用途：拿到模型新增的文字，把它写到终端。两个 `type` 为什么要这样判断，放到第 13—14 节讲；现在先沿着 `prompt()` 看请求怎么发出去。

**第三件事，交入用户消息，开始运行。** 真正推动本次任务的是最后一行：

```ts
await agent.prompt("Hello!");
```

注意它返回的是 `Promise<void>`，不是一个回答字符串。回答会在运行中通过事件送出来，完成的消息也会进入 Agent 的状态。这里的 `await` 是等这一轮 Agent 运行及其需要等待的处理收尾。

**例子：假设模型这次回答了“Hi!”。** 创建 `agent`、查询模型、登记回调这几步，都还没有发送 `Hello!`。执行到最后的 `prompt("Hello!")`，才开始请求。正常结束后，`agent.state.messages` 里有用户的 `Hello!` 和助手的 `Hi!`；`await agent.prompt(...)` 本身得到的是 `undefined`，回答保存在消息里。

后面统一沿开头的 `model` 推演：`id` 是 `"gpt-4o-mini"`，`provider` 是 `"openai"`，`api` 是 `"openai-completions"`。每遇到一个同名形参，都要核对调用方是不是把这个对象继续传下来了。

## 2. 按住 prompt 往里跳：为什么会看到三个定义

现在打开 [agent.ts，第 332 行](../pi-master/packages/agent/src/agent.ts#L332)。`prompt` 的完整方法是：

```ts
async prompt(message: AgentMessage | AgentMessage[]): Promise<void>;
async prompt(input: string, images?: ImageContent[]): Promise<void>;
async prompt(input: string | AgentMessage | AgentMessage[], images?: ImageContent[]): Promise<void> {
  if (this.activeRun) {
    throw new Error(
      "Agent is already processing a prompt. Use steer() or followUp() to queue messages, or wait for completion.",
    );
  }
  const messages = this.normalizePromptInput(input, images);
  await this.runPromptMessages(messages);
}
```

先看前三行。不是写了三个各干各的 `prompt`，而是 TypeScript 的**函数重载**：前两行告诉调用者有哪些合法用法，第三行开始才是真正的实现。

**这里要特别注意：外部调用只认前两条重载声明，不能拿第三行的实现签名来凑一种新用法。** 第三行把几种输入合在一起，是为了让同一个方法体处理它们；它不会增加外部允许的调用方式。这也是 [TypeScript 官方文档对重载的规定](https://www.typescriptlang.org/docs/handbook/2/functions.html#overload-signatures-and-the-implementation-signature)。

```ts
await agent.prompt("Hello!");     // 匹配第二条声明：string，图片可选。
await agent.prompt(aMessage);     // 匹配第一条声明：AgentMessage。
await agent.prompt(messageList);  // 匹配第一条声明：AgentMessage[]。
```

上面三行是教学用法，`aMessage`、`messageList` 需要由调用方事先准备。文字输入还可以带图片，所以第二个声明有可选的 `images` 参数。

这里顺便认一下 `images?: ImageContent[]`：**参数名后面的 `?` 表示“有它没它都行”，也就是这个参数可传可不传。** 后面的 `: ImageContent[]` 则说明，传了就要是图片数组。

```ts
await agent.prompt("Hello!");              // 匹配第二条声明，不传 images。
await agent.prompt("看看这张图", [image]);  // 仍匹配第二条声明，image 是准备好的图片块。
```

这两种写法都合法，因为第二条重载本身就写了 `images?`。不传时，方法收到的 `images` 就是 `undefined`；传了图片数组，就按带图片的输入继续处理。**“图片可传可不传”是第二条重载给字符串输入的用法，不是说所有输入都能再加一个图片数组。**

**反例：消息对象后面再加图片，就匹配不上。** 假设 `aMessage` 是一条完整消息，`image` 是准备好的图片块：

```ts
// 错误写法，取消注释就会产生类型错误：
// await agent.prompt(aMessage, [image]);
```

第一条重载只允许一个消息参数；第二条虽然能接两个参数，但第一个必须是字符串。这个调用两边都不符合，即使第三行的实现签名看起来能接，也不能调用。图片要么配合字符串输入传入，要么提前放进消息对象的 `content`。

还有一个容易踩坑的情况：变量的类型本身就是 `string | AgentMessage`。下面是教学示例，沿用前面的 `agent`：

```ts
function send(input: string | AgentMessage) {
  // 错误：编译器还不知道它是字符串还是消息，匹配不上某一条重载。
  // return agent.prompt(input);

  if (typeof input === "string") {
    return agent.prompt(input); // 已确定是字符串，匹配第二条。
  }
  return agent.prompt(input);   // 已确定是消息，匹配第一条。
}
```

两条分支最后虽然都调用 `prompt(input)`，但分支内已经确定了参数类型。外面先按重载检查能不能调用，通过后，运行时才进入同一个方法体。

再看方法体，它先检查 `this.activeRun`。如果这个 Agent 还在处理上一次任务，直接再调用 `prompt` 会报错；需要先等它完成，或者通过 `steer`、`followUp` 把补充要求放进队列。这能避免两个任务同时修改同一份对话状态。

通过检查后，只剩两步：

```ts
const messages = this.normalizePromptInput(input, images);
await this.runPromptMessages(messages);
```

第一步，把不同形式的输入统一成消息数组。第二步，拿着这组消息开始运行。

**例子：把三种写法里的变量补齐。** 下面任选一种调用，就能提交同样的用户内容：

```ts
const aMessage = {
  role: "user" as const,
  content: "Hello!",
  timestamp: Date.now(),
};
const messageList = [aMessage];

// 三种调用方式任选一种：
await agent.prompt("Hello!");
// await agent.prompt(aMessage);
// await agent.prompt(messageList);
```

第一种由 Agent 帮你创建消息；第二种用你准备好的消息；第三种用你准备好的消息数组。三种最后都进同一个方法体，区别只是输入怎么整理。

不过，先停一下。我们在函数签名里已经多次看到了 `AgentMessage`，它到底是什么？这正好是理解 Pi 为什么要定义接口的一个入口。

## 3. 穿插看 AgentMessage：为什么不能一直只传字符串

### 3.1 先找到它的定义

打开 [types.ts，第 246 行](../pi-master/packages/agent/src/types.ts#L246) 和 [types.ts，第 255 行](../pi-master/packages/agent/src/types.ts#L255)。去掉注释，关键定义是：

```ts
export interface CustomAgentMessages {
}

export type AgentMessage = Message | CustomAgentMessages[keyof CustomAgentMessages];
```

我们把它先读成人话：**Agent 能接收的消息，包括基础模型消息，也允许应用增加自己的消息种类。**

这里的 `Message` 从 `pi-ai` 导入。继续跳到 [types.ts，第 224 行](../pi-master/packages/ai/src/types.ts#L224)：

```ts
export type Message = UserMessage | AssistantMessage | ToolResultMessage;
```

也就是说，基础消息已经分成三种：用户输入、助手回复、工具结果。

为什么不能都当字符串？因为“用户问了什么”和“工具执行后返回了什么”不能只靠一段文字区分。工具结果还要知道它对应哪次调用，助手回复也可能包含文字、思考内容或工具调用。

例如，用户消息在 [types.ts，第 195 行](../pi-master/packages/ai/src/types.ts#L195) 中这样定义：

```ts
export interface UserMessage {
  role: "user";
  content: string | (TextContent | ImageContent)[];
  timestamp: number;
}
```

这份 `interface` 相当于先把约定写清楚：“用户消息的 `role` 必须是 `user`，内容可以是文字，也可以是一组文字和图片块，还要有时间戳。”

这样，后面的函数就能接收一份结构明确的数据，而不用每个地方重新猜：“这个参数里面到底放了什么？”

**例子：用户消息实际长这样。**

```ts
const userMessage: UserMessage = {
  role: "user",
  content: "Hello!",
  timestamp: 1,
};
```

这段沿用本节的 `UserMessage` 类型，`1` 只代替示例时间戳。程序看到 `role: "user"` 就知道是用户说的，读取 `content` 得到 `Hello!`。如果换成工具返回数字 5，消息就得用 `role: "toolResult"`，还得带 `toolCallId`，才能和之前那次工具调用对上。单独一个字符串 `"5"` 说不清这些事。

### 3.2 为什么还要再套一层 AgentMessage

因为 Agent 运行时想保留的东西，可能比模型调用需要的消息更多。

比如，一个应用想在内部记录一条“正在整理文件”的提示。它对界面有用，却未必应该直接发给模型。我们希望运行层能处理这类消息，同时又不用为了每个应用修改 Pi 的基础消息类型。

下面是一个**教学示例**，展示应用怎样通过声明合并扩充消息：

```ts
import type { AgentMessage } from "@mariozechner/pi-agent-core";

interface NoticeMessage {
  role: "notice";
  text: string;
  timestamp: number;
}

declare module "@mariozechner/pi-agent-core" {
  interface CustomAgentMessages {
    notice: NoticeMessage;
  }
}

const notice: AgentMessage = {
  role: "notice",
  text: "正在整理文件",
  timestamp: Date.now(),
};
```

`declare module` 在这里是补充已有模块的类型声明，不是运行时加载插件。加进去的 `notice: NoticeMessage` 表示：给自定义消息映射增加一个名为 `notice` 的条目，它对应的类型是 `NoticeMessage`。

回头再读这一段就容易了：

```ts
CustomAgentMessages[keyof CustomAgentMessages]
```

`keyof` 先取出所有登记的名字，再用这些名字取出对应类型。如果登记了多种消息，就把这些类型合在一起。默认接口为空，没有自定义类型时，`AgentMessage` 就只包含基础的 `Message`。

于是，Pi 的运行层不必提前知道每个应用会增加什么消息，应用也不必改框架源码。

### 3.3 类型允许接收，不等于模型认识这种消息

这里有个容易误会的地方：定义了 `NoticeMessage`，模型服务并不会自动认识 `role: "notice"`。

真正请求模型前，还要经过 `convertToLlm`。可以把它理解成：“把程序内部的消息整理成模型调用层接受的消息。”

默认转换函数在 [agent.ts，第 40 行](../pi-master/packages/agent/src/agent.ts#L40)：

```ts
function defaultConvertToLlm(messages: AgentMessage[]): Message[] {
  return messages.filter(
    (message) => message.role === "user" || message.role === "assistant" || message.role === "toolResult",
  );
}
```

它只保留 `user`、`assistant`、`toolResult`。刚才的 `notice` 默认会被过滤。如果应用希望把某种自定义记录转成模型可读的内容，就要提供自己的转换函数。

这样就可以同时满足两个需求：程序内部能保留自己需要的记录，发给模型时又遵守统一格式。

**例子：一条界面提示和一条用户消息一起进入转换。** 沿用上节的 `notice`，再准备一条 `userMessage`：

```ts
const messages: AgentMessage[] = [notice, userMessage];
const llmMessages = messages.filter(
  (m) => m.role === "user" || m.role === "assistant" || m.role === "toolResult",
);
// llmMessages 里只剩 userMessage，也就是 Hello!。
```

`notice` 里的“正在整理文件”被筛掉了。它可以留在应用的消息里，但不会因为扩充了类型，就自动变成模型请求的一部分。

### 3.4 接口到底帮了什么忙

拿这个例子来说，接口把“大家必须约定好的部分”写了出来。

写消息的人知道需要提供什么字段，处理消息的人知道能读取什么字段。以后增加消息种类，也有明确的扩充位置。编辑器还能据此给提示，类型检查器能提前发现一部分接错参数、漏写字段的问题。

不过，**类型只负责描述和检查，不会自己执行工作。** `interface` 和类型别名不会在运行时自动生成消息、转换格式或发请求。这些事情，还是得靠下面读到的函数实现。

顺便澄清一下术语：这里说“抽象出接口”，是指先约定数据和行为；不代表一定写成 TypeScript 的 `abstract class`。本章会看到 `interface`、`type` 和真正能创建对象的 `class`，它们要分开认。

**例子：少写一个字段，编辑器就能提醒你。**

```ts
// 正确：UserMessage 要的三个字段都有。
const good: UserMessage = { role: "user", content: "Hello!", timestamp: 1 };

// 错误写法：如果去掉注释，会因为缺少 timestamp 而产生类型错误。
// const bad: UserMessage = { role: "user", content: "Hello!" };
```

但 `good` 只是一个对象。你还得把它交给 `agent.prompt(good)`，程序才会开始处理。写对数据和开始执行，是两步。

### 3.5 放到整个 Pi 框架里，还有哪些主要约定

先按三层把最关键的一组放在一起。不是要在这里背完所有导出类型，而是知道后面遇到一个名字，它在约定什么。

| 所在层 | 主要类型或接口 | 约定什么 | 具体工作由谁完成 | 拿一件具体的事来对照 |
| --- | --- | --- | --- | --- |
| `pi-ai` | `Model` | 模型 ID、服务商、API 协议、地址和能力 | 模型表提供数据，Provider 根据它调用服务 | `id: "gpt-4o-mini"`，`api: "openai-completions"` |
| `pi-ai` | `Message`，以及各类内容块 | 用户、助手、工具结果及文字、图片等内容的格式 | 调用方创建消息，Provider 转换请求与响应 | 用户说 Hello!，正文块就是 `{ type: "text", text: "Hello!" }` |
| `pi-ai` | `Context` | 一次模型请求有哪些规则、消息和工具说明 | 上层准备，模型调用实现使用 | 把“用中文回答”、用户的 Hello!、本次工具列表放在一起 |
| `pi-ai` | `Tool` | 给模型看的工具名称、说明和参数格式 | Provider 转为服务商接受的工具说明 | `sum` 的说明和参数要求：a、b 都是数字 |
| `pi-ai` | `StreamOptions`、`SimpleStreamOptions` | 调用参数、取消信号、回调和统一推理选项 | 各个流式调用函数读取和适配 | `temperature: 0`、`maxTokens: 128`，以及取消信号 |
| `pi-ai` | `StreamFunction`、`ApiProvider` | 调用函数怎么接参数、返回什么，协议入口如何登记 | 各 Provider 函数和注册表 | 登记 openai-completions 对应的 `streamSimple` 函数 |
| `pi-ai` | `AssistantMessageEvent` | 一次模型输出有哪些增量事件和结束事件 | Provider 产生事件，事件流交给上层 | 模型新增 H，交出一条 `text_delta`；细节在第 13.3 节 |
| `pi-agent-core` | `AgentMessage`、`CustomAgentMessages` | 运行层接受哪些消息，应用怎样扩充 | 应用创建或扩充，`convertToLlm` 整理后交给模型 | 内部同时保留用户的 Hello! 和 notice“正在整理文件” |
| `pi-agent-core` | `AgentOptions`、`AgentState` | Agent 怎么配置，运行中保存什么状态 | `Agent` 类及其状态实现 | 配置模型；运行时读取 `isStreaming` 是否为 true |
| `pi-agent-core` | `AgentContext`、`AgentLoopConfig` | 循环需要哪些材料、模型和行为配置 | `Agent` 准备，循环函数使用 | context 带旧消息，config 带 model 和消息转换函数 |
| `pi-agent-core` | `AgentTool`、`AgentToolResult` | 工具怎样执行、结果怎样返回 | 具体工具的 `execute` 函数 | `sum.execute(...)` 算出 2 + 3，返回正文“5”和 details |
| `pi-agent-core` | `StreamFn` | 运行层怎样调用可替换的模型流式函数 | 默认用 `streamSimple`，也可以由应用提供 | 换成先打印模型名、再调用 `streamSimple` 的日志函数 |
| `pi-agent-core` | `AgentEvent`、`AgentEventSink` | 运行中报告什么，接收通知的函数怎么写 | 循环发事件，`processEvents` 或其他接收函数处理 | 循环报告工具开始，界面据此显示进度；细节在第 14 节 |
| `pi-coding-agent` | `ToolDefinition` | 工具怎样接入编码会话、提示词和显示 | 会话层包装后交给运行层，具体工具负责执行 | 扩展提供一个 sum 工具，交给编码会话使用 |
| `pi-coding-agent` | `ResourceLoader` | 怎样取得技能、扩展、项目说明等资源 | `DefaultResourceLoader` 或自定义加载器 | 读取某个 SKILL.md，让会话拿到该技能的说明 |
| `pi-coding-agent` | `ExtensionAPI`、`ExtensionContext` | 扩展能注册什么，执行时能访问哪些会话能力 | 扩展系统提供接口的具体实现 | 扩展注册一个命令，执行时访问当前会话提供的能力 |
| `pi-coding-agent` | `AgentSessionConfig`、`AgentSessionEvent` | 编码会话怎么配置，向外报告什么变化 | `AgentSession` 组织会话，`SessionManager` 管理记录 | 创建编码会话时传入配置，界面再接收会话变化通知 |

最后一列里的 `Agent`、`DefaultResourceLoader`、`AgentSession`、`SessionManager` 是实现类；前面大部分名字则是类型约定。**约定告诉双方怎么接，实现才让事情真的发生。**

这一轮先认到这里。现在回到 `prompt`，接着看那句 `Hello!` 往哪里走。

## 4. normalizePromptInput：先把 Hello 包成消息

打开 [agent.ts，第 376 行](../pi-master/packages/agent/src/agent.ts#L376)：

```ts
private normalizePromptInput(
  input: string | AgentMessage | AgentMessage[],
  images?: ImageContent[],
): AgentMessage[] {
  if (Array.isArray(input)) {
    return input;
  }

  if (typeof input !== "string") {
    return [input];
  }

  const content: Array<TextContent | ImageContent> = [{ type: "text", text: input }];
  if (images && images.length > 0) {
    content.push(...images);
  }
  return [{ role: "user", content, timestamp: Date.now() }];
}
```

这段可以按三个分支读：传来数组就直接用，传来单条消息就包成数组，传来字符串就新建一条用户消息。

对于我们的 `"Hello!"`，最后得到的数据大致如下。这里是**按源码推演的形状**，时间戳用变量代替：

```ts
[
  {
    role: "user",
    content: [{ type: "text", text: "Hello!" }],
    timestamp: 当前时间戳,
  },
]
```

后面的程序就不用反复判断“这次传的是文字、图片还是现成消息”。它只管处理 `AgentMessage[]`。

**例子：三个输入分支分别会得到什么。** U 表示一条已经准备好的完整用户消息：

| 传给 `prompt` 的输入 | `normalizePromptInput` 怎么处理 | 返回值 |
| --- | --- | --- |
| `"Hello!"` | 新建带 role、content、timestamp 的用户消息 U | `[U]` |
| `U` | 消息本身不用重建，外面包数组 | `[U]` |
| `[U]` | 已经是数组，直接返回原数组 | `[U]` |
| `"看这张图"`，再传入一个图片块 | 新建用户消息，content 先放文字，再放图片 | `[含文字和图片的用户消息]` |

所以字符串分支要做的事情最多：它得把“只给了一句话”补成一条消息。

准备好以后，回到 `prompt` 第 336 行：

```ts
await this.runPromptMessages(messages);
```

我们接着跳进去。

## 5. runPromptMessages：先套上生命周期管理，再启动循环

打开 [agent.ts，第 396 行](../pi-master/packages/agent/src/agent.ts#L396)：

```ts
private async runPromptMessages(
  messages: AgentMessage[],
  options: { skipInitialSteeringPoll?: boolean } = {},
): Promise<void> {
  await this.runWithLifecycle(async (signal) => {
    await runAgentLoop(
      messages,
      this.createContextSnapshot(),
      this.createLoopConfig(options),
      (event) => this.processEvents(event),
      signal,
      this.streamFn,
    );
  });
}
```

这里已经看到我们后面要追的 `runAgentLoop`。但先别跳过外面的这一层：

```ts
await this.runWithLifecycle(async (signal) => {
  // 在这里运行本次任务
});
```

这一小段是为了看清结构而写的示意。它表达的是：“把本次要做的工作作为一个函数交进去，运行前后的公共事情由 `runWithLifecycle` 统一处理。”

**例子：把这一问代进去。** `prompt("Hello!")` 整理出的消息数组，先成为这里的 `messages`。随后程序把 `async (signal) => { ... }` 这段函数交给 `runWithLifecycle`。这时可以把它读成一句话：“请先准备好运行状态，然后用这个 signal 执行里面的 `runAgentLoop`，最后帮我收尾。”下面就用两次提问看这层管理到底做了什么。

### 5.1 为什么不能直接调用 runAgentLoop

这里多包一层 `runWithLifecycle`，就是为了：**当前任务没结束，先别开下一次；执行中出了问题，有地方处理；最后把状态清理好。**

**比如用户问“解释一下闭包”，Agent 开始回答。这时用户又提交了一个问题，程序得知道“上一问还没完”，不能让两次运行一起改同一份对话。回答结束，或者中途出了错，也得有人把“正在运行”的标记清掉，否则下一问就进不来了。**

先看代码。[agent.ts，第 463 行](../pi-master/packages/agent/src/agent.ts#L463) 的完整方法如下，去掉原注释，补上几句中文说明：

```ts
private async runWithLifecycle(executor: (signal: AbortSignal) => Promise<void>): Promise<void> {
  // 上一次还没结束，就先拒绝这次调用。
  if (this.activeRun) {
    throw new Error("Agent is already processing.");
  }

  // 准备本次运行的取消信号，以及给 waitForIdle() 用的 Promise。
  const abortController = new AbortController();
  let resolvePromise = () => {};
  const promise = new Promise<void>((resolve) => {
    resolvePromise = resolve;
  });
  this.activeRun = { promise, resolve: resolvePromise, abortController };

  // 记下“现在正在运行”，清掉上一次留下的临时消息和错误。
  this._state.isStreaming = true;
  this._state.streamingMessage = undefined;
  this._state.errorMessage = undefined;

  try {
    await executor(abortController.signal); // 执行这次任务，等它结束。
  } catch (error) {
    await this.handleRunFailure(error, abortController.signal.aborted); // 意外出错，交给错误处理。
  } finally {
    this.finishRun(); // 成功也好，失败也好，最后都收尾。
  }
}
```

其中 `executor` 就是前面传入的 `async (signal) => { ... }`，里面调用 `runAgentLoop(...)`。所以，读到 `await executor(...)`，可以直接理解成：“开始跑刚才交进来的 Agent 任务，并等它做完。”

**拿两次提问走一遍。** 下面是教学示例，假设 `agent` 已配置好模型，第一问正常完成：

```ts
const firstRun = agent.prompt("解释一下闭包");
console.log(agent.state.isStreaming); // true：第一问已经开始。

// 第一问还没结束，就又提交第二问。
try {
  await agent.prompt("再举个例子");
} catch {
  console.log("上一问还没结束，暂时不能再开一问");
}

await firstRun; // 等第一问真正结束，包括它需要等待的事件处理。
console.log(agent.state.isStreaming); // false：已经收尾。

await agent.prompt("现在再举个例子"); // 这次就可以开始了。
```

第一行没有马上写 `await`，所以拿到 `firstRun` 后，下面的代码还会继续走。但 Agent 内部已经登记了 `activeRun`，也把 `isStreaming` 设成了 `true`。紧接着再调用 `prompt()`，它一看已有 `activeRun`，就拒绝第二问；第一问照常执行。

等到 `await firstRun` 结束，说明第一问已经做完了最后的收尾。再调用一次 `prompt()`，就能开始新任务。**第二问被拒绝后不会自动排队，上面是等第一问结束后重新调用。**

**那第一问中途出错呢？** 如果执行过程中有意外异常一路抛到 `await executor(...)`，就进入 `catch`。`handleRunFailure(...)` 会把错误记成失败消息，保存错误信息，再通知订阅者这次运行结束。处理完后，仍然进入 `finally` 收尾。模型已经通过错误事件报告的失败，则可以在循环里处理，不一定走到这个 `catch`。

最后的 `finishRun()` 也给出来，见 [agent.ts，第 505 行](../pi-master/packages/agent/src/agent.ts#L505)：

```ts
private finishRun(): void {
  this._state.isStreaming = false;
  this._state.streamingMessage = undefined;
  this._state.pendingToolCalls = new Set<string>();
  this.activeRun?.resolve();
  this.activeRun = undefined;
}
```

它做的事很直接：把“正在运行”改回 `false`，清掉临时状态，告诉等空闲的调用方“这次结束了”，再清除 `activeRun`。下一问就能正常进来了。

### 5.2 这里几层 await 分别在等什么

不要把 `await` 只理解成“等网络”。这里一层一层等待，目的是让外面的函数知道里面的工作什么时候真正做完。

```text
prompt 等 runPromptMessages
    runPromptMessages 等 runWithLifecycle
        runWithLifecycle 等 executor
            executor 等 runAgentLoop
        执行结束或异常处理后，finally 统一收尾
```

`await` 让当前异步函数等结果，不会把 JavaScript 线程一直占住。如果这里不等待就直接收尾，模型和工具还没结束，Agent 就可能已经被标成空闲。

**例子：应用只有等完这一句，才打印“结束”。**

```ts
console.log("开始提问");
await agent.prompt("Hello!");
console.log("这次结束了");
```

假设模型正常回答 `Hi!`，顺序就是：先打印“开始提问”，中间执行模型请求、处理回复，完成收尾，最后才打印“这次结束了”。删掉中间的 `await`，最后一句就可能在模型还没回答时打印出来。

## 6. runAgentLoop：先认清传进去的六样东西

回到 [agent.ts，第 401 行](../pi-master/packages/agent/src/agent.ts#L401)，这次看里面的调用：

```ts
await runAgentLoop(
  messages,
  this.createContextSnapshot(),
  this.createLoopConfig(options),
  (event) => this.processEvents(event),
  signal,
  this.streamFn,
);
```

先把六个参数认清楚，再跳到函数体里：

| 参数 | 这次传进去的是什么 |
| --- | --- |
| `messages` | 本次新交进来的消息，比如刚包装好的 `Hello!` |
| `this.createContextSnapshot()` | 系统提示词、此前的历史消息、可执行工具 |
| `this.createLoopConfig(options)` | 模型、调用选项、消息转换函数、队列读取函数、工具钩子等 |
| `(event) => this.processEvents(event)` | 循环报告变化时调用的接收函数 |
| `signal` | 从生命周期管理那里一路传下来的取消信号 |
| `this.streamFn` | 真正用来调用模型的流式函数，默认是 `streamSimple` |

`createContextSnapshot` 在 [agent.ts，第 425 行](../pi-master/packages/agent/src/agent.ts#L425)。它复制消息和工具数组的最外层，让循环能维护自己的数组；里面的消息、工具对象没有全部做深拷贝。

`createLoopConfig` 在 [agent.ts，第 434 行](../pi-master/packages/agent/src/agent.ts#L434)。它把 Agent 目前的模型、回调和配置整理给循环，还提供读取 `steer`、`followUp` 队列的函数。

**现在专门追模型：`config.model` 正是在这个函数里装进去的。** 看 [agent.ts，第 437 行](../pi-master/packages/agent/src/agent.ts#L437)，下面摘录返回对象中的模型字段：

```ts
return {
  model: this._state.model,
  // 其余配置字段省略
};
```

左边的 `model` 是新建 config 对象的属性名，右边是第 1.4 节保存在 Agent 里的模型对象。新建的是配置容器，里面的模型仍然是同一个对象。不要把 `createContextSnapshot()` 和它混淆：模型放在第三个实参 config 里，不在第二个实参 context 里。

接下来按位置核对三个函数之间的传递，调用处与定义处都列出来：

| 调用处 | 实参 | 接收它的定义处 | 接收到什么 |
| --- | --- | --- | --- |
| [agent.ts，第 404 行](../pi-master/packages/agent/src/agent.ts#L404) | `this.createLoopConfig(options)`，第 3 个实参 | [agent-loop.ts，第 99 行](../pi-master/packages/agent/src/agent-loop.ts#L99)：`config: AgentLoopConfig` | 包含 `model` 属性的配置对象 |
| [agent-loop.ts，第 160 行](../pi-master/packages/agent/src/agent-loop.ts#L160) | `config`，第 3 个实参 | [agent-loop.ts，第 204 行](../pi-master/packages/agent/src/agent-loop.ts#L204)：`config: AgentLoopConfig` | 原配置对象继续传入 `runLoop` |
| [agent-loop.ts，第 237 行](../pi-master/packages/agent/src/agent-loop.ts#L237) | `config`，第 2 个实参 | [agent-loop.ts，第 290 行](../pi-master/packages/agent/src/agent-loop.ts#L290)：`config: AgentLoopConfig` | 原配置对象继续传入 `streamAssistantResponse` |

这几步没有再查模型表，也没有重新设置 `model.api`。`config.model.api` 因而一直保持开头赋的 `"openai-completions"`。第 9 节会把 `config.model` 单独作为第一个参数交给模型调用函数。

这里先抓住一个区别：**context 主要是这次运行拿来用的材料，config 主要是模型选择和运行做法。**

**例子：把本次的六个参数填上具体内容。** 假设没有旧消息、没有工具，模型用第 1 节选好的配置：

| 参数 | 这次的具体值 | 这次怎么用 |
| --- | --- | --- |
| `messages` | `[U]`，U 是用户的 `Hello!` | 作为本次新提问加入历史 |
| context | `{ systemPrompt: "用中文回答", messages: [], tools: [] }` | 告诉循环当前有哪些材料 |
| config | `model` 为选好的模型，`convertToLlm` 为默认过滤函数 | 决定调用哪个模型、怎样整理消息 |
| emit 回调 | `(event) => this.processEvents(event)` | 运行需要报告进度时调用，后面再展开 |
| signal | 本次 `AbortController` 的 `signal` | 调用取消后，这个信号会变成已取消 |
| streamFn | 默认的 `streamSimple` 函数 | 到请求模型那一步，实际调用这个函数 |

再看“复制数组”是什么意思。下面用字符串代替消息，只演示数组关系：

```ts
const history = ["旧消息"];
const snapshot = history.slice();
snapshot.push("Hello!");
console.log(history);  // ["旧消息"]
console.log(snapshot); // ["旧消息", "Hello!"]
```

所以循环可以往自己的数组加消息，不会因为这次 `push` 就改掉原来的数组。若数组里放的是对象，对象本身仍然可能共享。

第四个参数先记成“接收运行通知的函数”，里面怎么处理留到第 14 节。现在先进入 `runAgentLoop`，继续追模型调用。

## 7. runAgentLoop 的函数体：把新消息接上历史，再进入 runLoop

接着把 [agent-loop.ts，第 96 行](../pi-master/packages/agent/src/agent-loop.ts#L96) 的实现连着看一遍：

```ts
export async function runAgentLoop(
  prompts: AgentMessage[],
  context: AgentContext,
  config: AgentLoopConfig,
  emit: AgentEventSink,
  signal?: AbortSignal,
  streamFn?: StreamFn,
): Promise<AgentMessage[]> {
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

前两段数组代码，分别在准备不同用途的数据。

`newMessages` 先放入本次新交进来的用户消息，后面继续收集本次新增的助手回复和工具结果。它不是此前所有历史。

`currentContext.messages` 则把历史消息和新消息拼起来，供这次循环使用。这里新建了数组，没直接在调用方原来的顶层数组上追加。

中间几行 `await emit(...)` 在报告“Agent 开始、本轮开始、用户消息已就绪”。这里先认出它们是通知语句，完整实现保留在代码里，具体怎么到达订阅者放到第 14 节。当前继续看最后的 `runLoop(...)`，模型调用就在它里面。

最后进入：

```ts
await runLoop(currentContext, newMessages, config, signal, emit, streamFn);
```

`runAgentLoop` 负责把新提示接进来并报告开始，`runLoop` 才负责接下来一轮轮调用模型、处理工具。

**例子：已有两条历史，这次又问了 `Hello!`。** 设 H1 是上一问、H2 是上一答、U 是本次用户消息，下面只是消息对象的简称：

```text
调用前 context.messages： [H1, H2]
本次 prompts：             [U]
创建 newMessages 后：      [U]
创建 currentContext 后：   [H1, H2, U]
模型正常回复 A 后：
  currentContext.messages：[H1, H2, U, A]
  newMessages：            [U, A]
```

这就能看清两个数组的区别：请求模型要带上旧历史，所以用 `[H1, H2, U]`；本次返回的新增消息只收 `[U, A]`。

## 8. runLoop：为什么这里会有循环

打开 [agent-loop.ts，第 201 行](../pi-master/packages/agent/src/agent-loop.ts#L201)。先别被两层 `while` 吓到，我们先在里面找一句：

```ts
const message = await streamAssistantResponse(currentContext, config, signal, emit, streamFn);
```

它在第 237 行。意思是：“根据目前的上下文，请模型产生下一条助手消息，过程中持续报告更新，最后拿到完整消息。”

拿到以后，程序会检查错误和取消。如果失败，就发出结束事件并退出。正常情况下，再找这条消息有没有要求使用工具：

```ts
const toolCalls = message.content.filter((c) => c.type === "toolCall");
```

如果有，就进入第 252 行的 `executeToolCalls(...)`。执行结果追加进上下文，后面模型才有机会看到结果、继续判断。具体执行函数最后会走到 [agent-loop.ts，第 668 行](../pi-master/packages/agent/src/agent-loop.ts#L668) 的 `prepared.tool.execute(...)`。

所以它需要循环，不是因为一段文字要一个字一个字地问模型，而是因为一个任务可能需要这样的往返：

```text
第一次问模型：模型要求读配置
    ↓
程序执行读取工具，把文件内容加入上下文
    ↓
第二次问模型：模型根据文件内容给出回答
```

一次模型请求内部的逐段输出，由后面的流式读取处理；这里的循环是在组织多轮模型与工具交互。

**例子：用户问“2 + 3 等于多少”，模型先要求调用 `sum`。** 假设完整助手消息的 `content` 里有这样一个块：

```ts
const toolCall = {
  type: "toolCall" as const,
  id: "call_1",
  name: "sum",
  arguments: { a: 2, b: 3 },
};
```

`filter(c => c.type === "toolCall")` 就会把它挑出来。程序找到 `sum` 工具，用参数 `{ a: 2, b: 3 }` 执行，得到结果 5。然后把“助手要求算什么”和“工具算出什么”都留在上下文，再请求一次模型，让它回答“2 + 3 = 5”。这次调用了模型两次；如果模型第一回就给出纯文字答案，没有工具调用块，就不用这次工具往返。

### 8.1 两层 while 分别在管什么

源码中的内层循环是：

```ts
while (hasMoreToolCalls || pendingMessages.length > 0) {
  // 处理待加入的消息、调用模型、执行工具，再决定是否继续
}
```

这是结构示意，不是完整源码。内层主要管工具往返和 `steering` 消息。`steering` 可以理解成运行途中用户补进来的新要求，会在下一次模型调用前加入。

外层则在任务本来可以结束时，再看看有没有 `follow-up`，也就是排队等当前工作结束后再处理的消息。有就继续，没有才真正退出。

本章的 `Hello!` 例子没设置工具，也没补充消息。在正常回复的情况下，模型调用一次，就可以发出 `turn_end`、`agent_end` 并结束。

真实工具批次还可以通过 `terminate` 提示跳过自动的下一次模型调用，错误、取消也会结束运行。先知道有这些出口，不要把循环理解成“永远执行到任务成功”。

**例子：一边做任务，一边补要求。** 下面的消息都是完整的用户消息，假设本次任务正常运行：

```ts
const running = agent.prompt("帮我整理这段说明");
agent.steer({ role: "user", content: "请用中文", timestamp: 2 });
agent.followUp({ role: "user", content: "整理完再写一句摘要", timestamp: 3 });
await running;
```

“请用中文”先进入 steering 队列，在下一次模型调用前加入；“再写一句摘要”先等着，只有当前工作原本可以结束时，外层才取出来继续处理。若既没有工具、也没有这两条补充，正常回答一次就能结束。

另外两种退出也代入这次任务看：如果模型消息的 `stopReason` 是 `"error"` 或 `"aborted"`，循环会直接走结束分支；如果这一批每个工具的最终结果都带 `terminate: true`，就不再因为工具结果自动请求下一轮模型。后者仍会检查补充消息，没有补充才结束。

现在沿着第 237 行，进入 `streamAssistantResponse`。

## 9. streamAssistantResponse：准备模型能用的消息，再选择调用函数

打开 [agent-loop.ts，第 288 行](../pi-master/packages/agent/src/agent-loop.ts#L288)。先读这个函数前半段：

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

const streamFunction = streamFn || streamSimple;

const resolvedApiKey =
  (config.getApiKey ? await config.getApiKey(config.model.provider) : undefined) || config.apiKey;

const response = await streamFunction(config.model, llmContext, {
  ...config,
  apiKey: resolvedApiKey,
  signal,
});
```

这里前面穿插的 `AgentMessage`，终于和实际调用接起来了。

第一步，如果应用提供了 `transformContext`，先整理内部消息。例如可以删去较早的内容，或者加入外部资料。这里做什么，取决于传入的实现，不是这个名字自动保证完成压缩。

第二步，调用 `convertToLlm`，把 `AgentMessage[]` 转成 `pi-ai` 接受的 `Message[]`。前面讲的自定义消息，就在这里被转换或过滤。

第三步，把系统提示词、整理好的消息和工具放进 `llmContext`。

这里的 `tools: context.tools` 可以来自可执行的 `AgentTool` 对象，但模型看到的是工具描述。Provider 会取名称、说明、参数格式来构造请求，不会把 `execute` 函数正文发给模型。

**例子：真正调用模型之前，消息怎么变。** 假设进入函数时有旧消息 H1、H2，一条界面提示 N，以及用户的 `Hello!`（U）；应用提供的 `transformContext` 这次只保留最后两条：

```text
context.messages：          [H1, H2, N, U]
transformContext 返回：     [N, U]
默认 convertToLlm 过滤 N：   [U]
llmContext.messages：       [U]
```

随后组装的关键数据就相当于下面这样。代码里的 `userMessage` 是内容为 `Hello!` 的完整用户消息：

```ts
const llmContext = {
  systemPrompt: "用中文回答",
  messages: [userMessage],
  tools: [],
};
```

这次只把 U 交给模型。转换函数如果只是返回新数组，没有改原数组，`context.messages` 仍可保留原来的四条。

凭据的选择也代个值：`getApiKey` 返回 `"<本次Key>"` 时采用它；没提供这个函数，或它返回空值时，才用 `config.apiKey`。这两个字符串只是占位说明。若配置了工具，比如 `sum`，`llmContext.tools` 里会有它的描述，Provider 再把名称和参数要求放进请求。

接下来是我们要追的关键一行：

```ts
const streamFunction = streamFn || streamSimple;
```

### 9.1 为什么先看 streamFn，再看 streamSimple

意思很直接：**如果上面提供了流式调用函数，就用它；否则使用 `pi-ai` 的通用入口 `streamSimple`。**

这也是函数可以作为参数传递的实际用途。运行循环需要“一个能调用模型并返回事件流的函数”，并不需要把每家模型的网络请求都写在自己里面。

对于第 1 节教学示例创建出来的 Agent，构造函数已经在 [agent.ts，第 211 行](../pi-master/packages/agent/src/agent.ts#L211) 设置：

```ts
this.streamFn = options.streamFn ?? streamSimple;
```

所以我们没有自定义 `streamFn` 时，传到这里的函数通常已经是 `streamSimple`。循环里的 `|| streamSimple` 还为直接调用底层循环、不传函数的情况保留默认入口。

`StreamFn` 的约定在 [types.ts，第 24 行](../pi-master/packages/agent/src/types.ts#L24)：

```ts
export type StreamFn = (
  ...args: Parameters<typeof streamSimple>
) => ReturnType<typeof streamSimple> | Promise<ReturnType<typeof streamSimple>>;
```

这里的 `Parameters` 复用 `streamSimple` 的参数类型，`ReturnType` 复用它的返回类型，并允许自定义函数异步返回这个结果。这能让调用接口保持一致。

但“函数不得把模型失败直接抛出来”等行为约定，还需要实现者遵守，TypeScript 不能仅靠这个函数类型检查所有运行行为。

**例子：给默认调用加一句日志，就可以换成自己的函数。** 沿用前面的 `Agent` 和 `model`，补充这两个导入：

```ts
import { streamSimple } from "@mariozechner/pi-ai";
import type { StreamFn } from "@mariozechner/pi-agent-core";

const loggedStream: StreamFn = (model, context, options) => {
  console.log("本次调用：", model.id, context.messages.length);
  return streamSimple(model, context, options);
};

const agent = new Agent({ initialState: { model }, streamFn: loggedStream });
```

调用这个 Agent 时，循环用的是 `loggedStream`：先打印模型名和消息条数，再交给默认的 `streamSimple`。不传 `streamFn`，就直接用默认函数。

### 9.2 await streamFunction，不代表完整答案已经回来了

看调用处：

```ts
const response = await streamFunction(config.model, llmContext, {
  ...config,
  apiKey: resolvedApiKey,
  signal,
});
```

这里得到的 `response` 是**可以持续读取的模型事件流**。默认 `streamSimple` 同步返回流对象；自定义函数也可以先返回一个 Promise，因此这一层统一使用 `await`。

拿到流对象，只表示后面可以开始读事件，并不表示模型已经回答完。完整回复要在后面的 `for await` 中逐步接收。

**例子：拿到流和拿到完整回答，是两个时刻。** 假设输入是 `Hello!`，模型最后回答 `Hi!`：

```ts
const response = await streamFunction(config.model, llmContext, {
  ...config,
  apiKey: resolvedApiKey,
  signal,
});
console.log("已经拿到流，可以等模型输出了");

const answer = await response.result();
console.log("完整回答已经拿到", answer.content);
```

第一句日志出现时，模型可能还没开始返回文字；第二句日志要等最终消息。这里单独等待 `result()` 是为了比较两个时刻；真实的 `streamAssistantResponse` 中间还会逐条读事件，代码放在第 13.7 节。

我们先顺着调用往下追，等看见模型输出以后，再回来接这段读取代码。

### 9.3 跳进 streamSimple 前，先把三个参数对上

调用发生在 [agent-loop.ts，第 336—340 行](../pi-master/packages/agent/src/agent-loop.ts#L336)。默认路径中的 `streamFunction` 就是 `streamSimple`；该函数从包入口 [pi-ai/src/index.ts，第 19 行](../pi-master/packages/ai/src/index.ts#L19) 导出，定义在 [pi-ai/src/stream.ts，第 43 行](../pi-master/packages/ai/src/stream.ts#L43)。

| 第几个参数 | 调用处传入的实参 | `streamSimple` 的形参 | 到底从哪里来 |
| --- | --- | --- | --- |
| 1 | `config.model` | 第 44 行的 `model` | 第 6 节追过：教学示例 → Agent 状态 → `createLoopConfig` → 循环 config |
| 2 | `llmContext` | 第 45 行的 `context` | [agent-loop.ts，第 324—328 行](../pi-master/packages/agent/src/agent-loop.ts#L324) 新建：系统提示词、转换后的消息、工具 |
| 3 | `{ ...config, apiKey: resolvedApiKey, signal }` | 第 46 行的 `options` | 第 336—340 行新建；复制 config，再覆盖本次 Key 和取消信号 |

**形参名称变了，传入的值没有因此改变。** `streamSimple` 里的 `model` 就是调用处的 `config.model`，所以它读到的 `model.api` 是 `"openai-completions"`。`context` 则接住 `llmContext`，不是 `runAgentLoop` 最初收到的那个 context 容器。

第三个参数是新对象，但 `...config` 只做浅层复制；它不会自动把模型对象改成别的值。虽然 options 也会带上展开得到的 `model` 等额外字段，下一层选择协议用的是**第一个参数**的 `model.api`。

本例未给 Agent 配置 `getApiKey`，`createLoopConfig` 也没有设置 `apiKey`，所以此处 `resolvedApiKey` 是 `undefined`。后面具体 OpenAI 入口才会尝试读取环境变量；不要误以为 `getModel` 的返回值里自带 Key。

## 10. streamSimple：看 model.api，找到对应协议的实现

打开 [stream.ts，第 43 行](../pi-master/packages/ai/src/stream.ts#L43)，源码是：

```ts
export function streamSimple<TApi extends Api>(
  model: Model<TApi>,
  context: Context,
  options?: SimpleStreamOptions,
): AssistantMessageEventStream {
  const provider = resolveApiProvider(model.api);
  return provider.streamSimple(model, context, options);
}
```

先读函数声明里的 `TApi extends Api`，再往下追函数体里的两行：

```ts
const provider = resolveApiProvider(model.api);
return provider.streamSimple(model, context, options);
```

它们分别在 [stream.ts，第 48 行](../pi-master/packages/ai/src/stream.ts#L48) 和 [第 49 行](../pi-master/packages/ai/src/stream.ts#L49)。第一行拿字符串查实现对象，第二行调用对象里保存的函数。下面先认清字符串有哪些含义，再把每个值追到来源。

### 10.1 先看 TApi extends Api：协议名称和服务商名称是两回事

把光标放到 `Api` 上，跳到 [types.ts，第 5—17 行](../pi-master/packages/ai/src/types.ts#L5)：

```ts
export type KnownApi =
  | "openai-completions"
  | "mistral-conversations"
  | "openai-responses"
  | "azure-openai-responses"
  | "openai-codex-responses"
  | "anthropic-messages"
  | "bedrock-converse-stream"
  | "google-generative-ai"
  | "google-gemini-cli"
  | "google-vertex";

export type Api = KnownApi | (string & {});
```

`KnownApi` 列出仓库已知的协议名称。`Api` 在这些名称之外，还允许自定义字符串，给扩展实现留下位置。这里的 `string & {}` 是类型写法，不是运行时把字符串和对象拼在一起；实际传递的仍是 `"openai-completions"` 这样的字符串。

再回来看：

```ts
export function streamSimple<TApi extends Api>(
  model: Model<TApi>,
  // 后续参数省略
)
```

这是**函数声明的局部摘录**。`TApi` 是这次调用所使用的协议类型，`extends Api` 限定它必须符合 `Api`，`Model<TApi>` 则要求模型对象的 `api` 字段与它一致。本章传入 `Model<"openai-completions">`，这里的 `TApi` 就可以推断为 `"openai-completions"`。这是类型检查中的约束，没有创建一个继承 `Api` 的类；运行时选哪条路，仍然要看函数体读取的 `model.api`。

往下再看 [types.ts，第 19—44 行](../pi-master/packages/ai/src/types.ts#L19)，还有另一组名称：

```ts
export type KnownProvider =
  | "amazon-bedrock"
  | "anthropic"
  | "google"
  | "google-gemini-cli"
  | "google-antigravity"
  | "google-vertex"
  | "openai"
  | "azure-openai-responses"
  | "openai-codex"
  | "github-copilot"
  | "xai"
  | "groq"
  | "cerebras"
  | "openrouter"
  | "vercel-ai-gateway"
  | "zai"
  | "mistral"
  | "minimax"
  | "minimax-cn"
  | "huggingface"
  | "fireworks"
  | "opencode"
  | "opencode-go"
  | "kimi-coding";
export type Provider = KnownProvider | string;
```

这组说的是服务商身份，也允许自定义名称。两组类型都出现在 [types.ts，第 394 行](../pi-master/packages/ai/src/types.ts#L394) 的模型接口里，下面只摘录相关字段：

```ts
export interface Model<TApi extends Api> {
  id: string;
  name: string;
  api: TApi;
  provider: Provider;
  baseUrl: string;
  // 其余字段省略
}
```

**用本章的模型配置代进去：**

| 字段 | 本章的值 | 读到这里时怎样理解 |
| --- | --- | --- |
| `model.provider` | `"openai"` | 由哪家服务商提供服务，例如后面按它查找环境变量 Key |
| `model.api` | `"openai-completions"` | 使用哪种协议，由它在 API 注册表中选择调用函数 |
| `model.id` | `"gpt-4o-mini"` | 具体请求哪个模型，后面进入 SDK 的请求参数 |
| `model.baseUrl` | `"https://api.openai.com/v1"` | 请求发往哪个服务地址，后面交给 SDK 客户端 |

所以读到 `resolveApiProvider(model.api)`，要带进去的是 `"openai-completions"`。同一家 OpenAI 也有 `"openai-responses"` 这条协议；只知道服务商是 `"openai"`，还不能确定要读哪个实现文件。反过来，使用兼容协议的其他服务商，也可能复用 Chat Completions 的实现。

类型名称的列表本身不会登记函数。自定义一个 `api` 字符串以后，还需要有人把对应实现放进注册表，否则下一步查找仍会报错。现在带着这个区别回到函数体。

### 10.2 model.api 到底是谁传过来的

第 44 行的 `model` 是形参，调用方是 [agent-loop.ts，第 336 行](../pi-master/packages/agent/src/agent-loop.ts#L336)：

```ts
const response = await streamFunction(config.model, llmContext, {
  ...config,
  apiKey: resolvedApiKey,
  signal,
});
```

第 9.1 节已经确认默认 `streamFunction === streamSimple`，所以这里的第一个实参 `config.model` 被第 44 行的形参 `model` 接住。不是谁另外传了一次 `api`，而是把**含有 `api` 属性的整个模型对象**传了进来。

如果只从这里往上找，按这张表倒着跳：

| 当前看到的值 | 往上一处找 | 那一处怎样得到它 |
| --- | --- | --- |
| `streamSimple` 的 `model.api` | [agent-loop.ts，第 336 行](../pi-master/packages/agent/src/agent-loop.ts#L336) | 第一个实参传入 `config.model` |
| `config.model` | [agent.ts，第 437 行](../pi-master/packages/agent/src/agent.ts#L437) | `createLoopConfig` 设置 `model: this._state.model`；中间传递见第 6 节 |
| `this._state.model` | [agent.ts，第 208 行](../pi-master/packages/agent/src/agent.ts#L208)、[第 86 行](../pi-master/packages/agent/src/agent.ts#L86) | 构造函数接收 `options.initialState`，状态函数取 `initialState.model` |
| 教学示例的 `initialState.model` | 第 1 节的 `new Agent({ initialState: { model } })` | 调用方把自己准备的 `model` 对象传进去 |
| 教学示例的 `model.api` | 第 1 节的 `api: "openai-completions"` | 在 `getModel` 返回的配置基础上显式覆盖 |
| 未覆盖前的 `catalogModel.api` | [models.ts，第 24—25 行](../pi-master/packages/ai/src/models.ts#L24) → [models.generated.ts，第 5842 行](../pi-master/packages/ai/src/models.generated.ts#L5842) | 查表得到原值 `"openai-responses"` |

因此本次第 48 行可以代入为 `resolveApiProvider("openai-completions")`。如果你自己的代码只有 `model: getModel("openai", "gpt-4o-mini")`，没有本章的覆盖步骤，那么按当前模型表代入的应该是 `resolveApiProvider("openai-responses")`，会走另一条实现。

### 10.3 resolveApiProvider 返回的 provider 究竟是什么

打开 [stream.ts，第 17—23 行](../pi-master/packages/ai/src/stream.ts#L17)，函数完整实现是：

```ts
function resolveApiProvider(api: Api) {
  const provider = getApiProvider(api);
  if (!provider) {
    throw new Error(`No API provider registered for api: ${api}`);
  }
  return provider;
}
```

`model.api` 的字符串值变成这里的形参 `api`。第 18 行把它交给 `getApiProvider`。这个函数由 [stream.ts，第 3 行](../pi-master/packages/ai/src/stream.ts#L3) 导入，定义在 [api-registry.ts，第 80—82 行](../pi-master/packages/ai/src/api-registry.ts#L80)：

```ts
export function getApiProvider(api: Api): ApiProviderInternal | undefined {
  return apiProviderRegistry.get(api)?.provider;
}
```

`apiProviderRegistry` 在 [api-registry.ts，第 40 行](../pi-master/packages/ai/src/api-registry.ts#L40) 创建：

```ts
const apiProviderRegistry = new Map<string, RegisteredApiProvider>();
```

它就是一张 Map：键是协议字符串，值是登记记录。`.get(api)` 先取登记记录，`?.provider` 再取记录里的实现对象；没有记录就返回 `undefined`，上一层随后报错。

本次把值代进去，就是 `apiProviderRegistry.get("openai-completions")?.provider`。查找方法本身没有 OpenAI 的特殊分支，接下来要找的是：**谁调用 `.set(...)`，往这张表里放入了 OpenAI 的函数？**

**这里同样叫 provider 的两个东西要分清：**

| 表达式 | 本次是什么 | 用途 |
| --- | --- | --- |
| `model.provider` | 字符串 `"openai"` | 服务商身份，例如用于取环境变量凭据 |
| `resolveApiProvider(model.api)` 的返回值 | 一个包含 `api`、`stream`、`streamSimple` 属性的对象 | 保存该协议的调用函数 |

所以 `provider.streamSimple(...)` 是调用对象属性里存的函数，不是调用字符串 `"openai"` 上的方法，也不是必须去找某个 `Provider` 类的同名方法。

### 10.4 对象的 streamSimple 属性，是登记时放进去的

在 IDE 中搜索 `apiProviderRegistry` 的引用：刚才看到的是 `.get(...)`，现在要找往里写数据的 `.set(...)`。它位于 `registerApiProvider` 中。这样就从“谁取出函数”追到了“谁保存函数”。

先看登记对象的约定，在 [api-registry.ts，第 23 行](../pi-master/packages/ai/src/api-registry.ts#L23)：

```ts
export interface ApiProvider<TApi extends Api = Api, TOptions extends StreamOptions = StreamOptions> {
  api: TApi;
  stream: StreamFunction<TApi, TOptions>;
  streamSimple: StreamFunction<TApi, SimpleStreamOptions>;
}
```

这只规定“要有这些属性”，不产生运行时实现。真正存入 Map 的代码在 [api-registry.ts，第 66—78 行](../pi-master/packages/ai/src/api-registry.ts#L66)：

```ts
export function registerApiProvider<TApi extends Api, TOptions extends StreamOptions>(
  provider: ApiProvider<TApi, TOptions>,
  sourceId?: string,
): void {
  apiProviderRegistry.set(provider.api, {
    provider: {
      api: provider.api,
      stream: wrapStream(provider.api, provider.stream),
      streamSimple: wrapStreamSimple(provider.api, provider.streamSimple),
    },
    sourceId,
  });
}
```

注意 [第 74 行](../pi-master/packages/ai/src/api-registry.ts#L74)：放进表的 `streamSimple` 属性，实际是 `wrapStreamSimple(...)` 返回的函数。登记方传来的原函数又被包了一层。

继续打开 [api-registry.ts，第 54—64 行](../pi-master/packages/ai/src/api-registry.ts#L54)：

```ts
function wrapStreamSimple<TApi extends Api>(
  api: TApi,
  streamSimple: StreamFunction<TApi, SimpleStreamOptions>,
): ApiStreamSimpleFunction {
  return (model, context, options) => {
    if (model.api !== api) {
      throw new Error(`Mismatched api: ${model.api} expected ${api}`);
    }
    return streamSimple(model as Model<TApi>, context, options);
  };
}
```

这里有两次不同的调用：

1. **登记时**执行 `wrapStreamSimple(api, streamSimple)`，传两个参数。它创建并返回箭头函数；返回函数记住登记的协议字符串和原入口函数，此时没有请求模型。
2. **每次调用模型时**执行 `provider.streamSimple(model, context, options)`，传三个参数。这时才进入第 58 行返回的函数，由第 59 行检查 `model.api`，再由第 62 行调用原入口。

对于本例，函数记住的 `api` 是 `"openai-completions"`；第 62 行的 `streamSimple` 来自登记时传入的函数。`as Model<TApi>` 只是类型断言，不会创建新模型或替换 `api`。

因此，读第 49 行不能直接跳过注册表包装：

```text
stream.ts:49      provider.streamSimple(model, context, options)
  → api-registry.ts:58     进入登记时返回的箭头函数
  → api-registry.ts:59     检查 model.api 与登记的 api 一致
  → api-registry.ts:62     调用登记方最初传来的 streamSimple
```

下一步就要找：**是谁执行 `registerApiProvider`，给它传了哪个 `streamSimple`？** 先沿实际函数找到 OpenAI 文件，等看到具体实现后，第 13.8 节再回头解释这里的 `StreamFunction` 和 `ApiStreamSimpleFunction` 为什么写法不同。

## 11. 内置实现怎么登记：中间还有一层延迟加载

对 `registerApiProvider` 使用“查找所有引用”，会找到 `providers/register-builtins.ts` 中的多处登记。先根据 `api: "openai-completions"` 找到本章这一项，再看它传入的函数值。这里按协议字符串定位，才不会误入同一家服务商的 Responses 分支。

打开 [stream.ts，第 1 行](../pi-master/packages/ai/src/stream.ts#L1)，文件开头有：

```ts
import "./providers/register-builtins.js";
```

这不是导入一个变量，而是让这个模块的初始化代码执行。继续看 [register-builtins.ts，第 433 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L433)，模块最后会调用 `registerBuiltInApiProviders()`。

其中 OpenAI Chat Completions 的登记在 [register-builtins.ts，第 373 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L373)：

```ts
registerApiProvider({
  api: "openai-completions",
  stream: streamOpenAICompletions,
  streamSimple: streamSimpleOpenAICompletions,
});
```

看起来像是已经把具体函数放进去了，但再看 [register-builtins.ts，第 359 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L359)：

```ts
export const streamOpenAICompletions = createLazyStream(loadOpenAICompletionsProviderModule);
export const streamSimpleOpenAICompletions = createLazySimpleStream(loadOpenAICompletionsProviderModule);
```

这两个名字在当前文件里，实际上是**延迟加载的包装函数**。它们和具体 Provider 文件里的导出同名，但不是同一个函数对象。

这里的 `streamSimple: streamSimpleOpenAICompletions` 也是“属性名: 属性值”：左边提供统一属性名，右边放入当前文件第 360 行得到的函数。不是因为属性叫 `streamSimple`，JavaScript 就会自动寻找某个同名实现。

### 11.1 先分清登记时创建函数，与请求时执行函数

打开 [register-builtins.ts，第 189—210 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L189)，完整的简化入口包装如下：

```ts
function createLazySimpleStream<
  TApi extends Api,
  TOptions extends StreamOptions,
  TSimpleOptions extends SimpleStreamOptions,
>(loadModule: () => Promise<LazyProviderModule<TApi, TOptions, TSimpleOptions>>): StreamFunction<TApi, TSimpleOptions> {
  return (model, context, options) => {
    const outer = new AssistantMessageEventStream();

    loadModule()
      .then((module) => {
        const inner = module.streamSimple(model, context, options);
        forwardStream(outer, inner);
      })
      .catch((error) => {
        const message = createLazyLoadErrorMessage(model, error);
        outer.push({ type: "error", reason: "error", error: message });
        outer.end(message);
      });

    return outer;
  };
}
```

第 360 行执行 `createLazySimpleStream(loadOpenAICompletionsProviderModule)` 时，传进去的是**函数本身**，不是模块加载的结果。参数位置这样对：

| 时机 | 调用位置与传入值 | 接收位置 | 此时发生什么 |
| --- | --- | --- | --- |
| 模块初始化 | [第 360 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L360) 传入 `loadOpenAICompletionsProviderModule` | 第 193 行的 `loadModule` | 创建第 194 行的箭头函数，记住加载函数 |
| 模块初始化 | [第 376 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L376) 把上一步返回函数放入登记对象 | `registerApiProvider` 的 `provider.streamSimple` | 再经过第 10.4 节的包装后存入 Map |
| 本次模型调用 | [api-registry.ts，第 62 行](../pi-master/packages/ai/src/api-registry.ts#L62) 传入 `model, context, options` | register-builtins.ts 第 194 行箭头函数的三个形参 | 现在才开始创建外层流、执行第 197 行 `loadModule()` |

第 197 行的 `loadModule()` 因而就是调用 `loadOpenAICompletionsProviderModule()`。这一步的来源是第 360 行传入的函数引用，不是临时按名称查找出来的。

为什么包这一层？因为只调用一家模型时，没有必要提前把每一家的实现和 SDK 都加载进来。先登记轻量入口，需要时再加载对应模块。

**例子：第一次发出 `Hello!` 时，先碰到哪个同名函数。**

```text
stream.ts:49 调用注册表返回对象的 streamSimple 属性
  → api-registry.ts:58、62 检查协议，调用登记的原函数
  → register-builtins.ts:194 进入延迟入口
  → register-builtins.ts:197 调用先前记住的 loadModule
  → register-builtins.ts:306 开始加载 openai-completions.js
  → register-builtins.ts:199 调用加载结果的 streamSimple 属性
  → openai-completions.ts:368 进入具体简化实现
```

名字虽然相同，位置和作用不同。读到注册表里的名字，先跟到包装函数；读到加载出来的模块，再进入真正处理 OpenAI 参数的函数。

### 11.2 loadModule 的返回对象，又是谁组装的

加载函数在 [register-builtins.ts，第 303 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L303)：

```ts
function loadOpenAICompletionsProviderModule(): Promise<
  LazyProviderModule<"openai-completions", OpenAICompletionsOptions, SimpleStreamOptions>
> {
  openAICompletionsProviderModulePromise ||= import("./openai-completions.js").then((module) => {
    const provider = module as OpenAICompletionsProviderModule;
    return {
      stream: provider.streamOpenAICompletions,
      streamSimple: provider.streamSimpleOpenAICompletions,
    };
  });
  return openAICompletionsProviderModulePromise;
}
```

这里才看到真正的文件：`./openai-completions.js`。源码是 `.ts`，导入写 `.js`，对应编译后的模块路径。

`||=` 的作用是保留已经创建的加载 Promise，后续调用复用它，不重复发起同一份模块加载。

加载完成后，把具体导出的函数整理成统一形状：`stream` 对应完整入口，`streamSimple` 对应简化入口。

特别注意，这段也有一个局部变量 `provider`，但它与 `stream.ts` 第 48 行的 `provider` 含义不同：

| 位置 | 变量来自哪里 | `.streamSimple` 或对应导出是什么 |
| --- | --- | --- |
| [stream.ts，第 48 行](../pi-master/packages/ai/src/stream.ts#L48) 的 `provider` | API 注册表返回的对象 | 包着协议检查的函数 |
| [register-builtins.ts，第 307 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L307) 的 `provider` | `import("./openai-completions.js")` 得到的模块对象 | 用完整导出名访问 `provider.streamSimpleOpenAICompletions` |
| [register-builtins.ts，第 198 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L198) 的 `module` | 加载函数第 308—311 行返回的新对象 | `module.streamSimple` 指向上行那个具体导出 |

第 307 行的 `as OpenAICompletionsProviderModule` 只提供类型说明，声明见 [register-builtins.ts，第 72—75 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L72)。实际函数来自导入模块在 [openai-completions.ts，第 368 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L368) 的导出；类型断言不负责生成函数。

**例子：连续取两次模块，加载 Promise 只建一次。** 把调用放在源码所在模块中理解：

```ts
const first = loadOpenAICompletionsProviderModule();
const second = loadOpenAICompletionsProviderModule();
console.log(first === second); // true：复用同一个加载 Promise。
```

第一次 `||=` 右边会执行；第二次左边已经有值，就直接返回它。这里只复用了模块加载，每次提问仍然可以发出新的模型请求，不是把第一次回答拿来重复用。

### 11.3 module.streamSimple 的三个参数，仍然来自上层

加载完成后，包装函数在 `.then(...)` 中执行这一行，见 [register-builtins.ts，第 199 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L199)：

```ts
const inner = module.streamSimple(model, context, options);
```

这里的 `module.streamSimple`，就是上面加载函数返回的 `provider.streamSimpleOpenAICompletions`。所以接下来该打开 `openai-completions.ts`，继续看真正的调用函数。

把各层按“调用处 → 函数体”连起来。下面每一行是实际源码的位置，括号里的三个值一路透传：

```text
agent-loop.ts:336
  streamFunction(config.model, llmContext, 新建的选项对象)
    ↓ 默认函数是 streamSimple
stream.ts:43、49
  provider.streamSimple(model, context, options)
    ↓ 注册表存的是检查函数
api-registry.ts:58、62
  streamSimple(model as Model<TApi>, context, options)
    ↓ 登记时的原函数是延迟入口
register-builtins.ts:194、197
  loadModule() → loadOpenAICompletionsProviderModule()
    ↓ 第 306 行导入具体模块，第 310 行取具体导出
register-builtins.ts:199
  module.streamSimple(model, context, options)
    ↓ 加载结果的 streamSimple 属性指向具体导出
openai-completions.ts:368
  streamSimpleOpenAICompletions(model, context, options)
```

到第 368 行为止，第一个参数仍是 Agent 的那份模型对象，第二个参数仍是 `llmContext`，第三个参数仍是第 331 行新建的选项对象。查表、检查协议和加载模块都没有把这三个对象重建成别的内容；真正整理 options 的代码在下一节。

如果没有第 1 节对 `api` 的覆盖，这次查到 `"openai-responses"`，相应位置改为 [register-builtins.ts，第 385—389 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L385) 的登记、[第 362 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L362) 的延迟入口、[第 316—327 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L316) 的加载函数，最后进入 [openai-responses.ts，第 137 行](../pi-master/packages/ai/src/providers/openai-responses.ts#L137) 的 `streamSimpleOpenAIResponses`。这能用来核对自己的 IDE 为什么跳到了另一份文件。

**例子：这一行拿到的就是前面准备好的消息。** 假设 `model.id` 是 `gpt-4o-mini`，`context.messages` 只有用户的 `Hello!`，`options.apiKey` 已提供，那么这次调用可以按参数展开成：

```text
module.streamSimple(
  model：gpt-4o-mini，api 为 openai-completions，
  context：包含用户消息 Hello!，
  options：包含本次 API Key
)
  → 进入具体文件里的 streamSimpleOpenAICompletions
```

加载模块这一步没有替你换消息，也没有生成回答；它只是找到了真正该执行的函数，把原来的参数交过去。

包装层还会把模型输出转交给上层，这部分放到第 13.6 节讲。现在先跟着调用走到请求发出去的位置。

## 12. streamSimpleOpenAICompletions：整理选项，交给完整实现

现在进入 [openai-completions.ts，第 368 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L368)。这次是在 `providers/openai-completions.ts` 文件里，看到了真正的简化入口：

```ts
export const streamSimpleOpenAICompletions: StreamFunction<"openai-completions", SimpleStreamOptions> = (
  model: Model<"openai-completions">,
  context: Context,
  options?: SimpleStreamOptions,
): AssistantMessageEventStream => {
  const apiKey = options?.apiKey || getEnvApiKey(model.provider);
  if (!apiKey) {
    throw new Error(`No API key for provider: ${model.provider}`);
  }

  const base = buildBaseOptions(model, options, apiKey);
  const reasoningEffort = supportsXhigh(model) ? options?.reasoning : clampReasoning(options?.reasoning);
  const toolChoice = (options as OpenAICompletionsOptions | undefined)?.toolChoice;

  return streamOpenAICompletions(model, context, {
    ...base,
    reasoningEffort,
    toolChoice,
  } satisfies OpenAICompletionsOptions);
};
```

这段先找 API Key，找不到就报错；再用 `buildBaseOptions` 整理通用选项；根据模型能力处理推理强度，最后调用：

```ts
return streamOpenAICompletions(model, context, {
  ...base,
  reasoningEffort,
  toolChoice,
} satisfies OpenAICompletionsOptions);
```

`satisfies` 在这里让 TypeScript 检查这个选项对象符合要求，不会在运行时给对象加功能。

这层没有重新写一套发送和解析逻辑。它把统一参数调整成具体实现要用的参数，就把工作交给 `streamOpenAICompletions`。

这次调用的参数来源也逐个对上：调用在 [openai-completions.ts，第 382—386 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L382)，接收它的函数定义在 [第 110—114 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L110)。

| 调用处的实参 | 完整入口的形参 | 这一层有没有改变 |
| --- | --- | --- |
| `model` | 第 111 行的 `model` | 原模型对象继续传入，`api` 仍为 `"openai-completions"` |
| `context` | 第 112 行的 `context` | 原 `llmContext` 继续传入，里面有 `Hello!` 的用户消息 |
| `{ ...base, reasoningEffort, toolChoice }` | 第 113 行的 `options` | **新建**具体协议使用的选项对象，不再是上层那份 options 容器 |

`buildBaseOptions` 从哪里来的？看 [openai-completions.ts，第 38 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L38) 的导入，再跳到 [providers/simple-options.ts，第 3—17 行](../pi-master/packages/ai/src/providers/simple-options.ts#L3)。它把 `temperature`、`signal`、Key、回调等逐项放进返回对象；第 6 行在未指定 `maxTokens` 时，使用 `Math.min(model.maxTokens, 32000)`，前提是模型上限大于 0。本例模型上限来自 [models.generated.ts，第 5854 行](../pi-master/packages/ai/src/models.generated.ts#L5854) 的 `16384`，因此默认得到 `16384`。

凭据则在 [openai-completions.ts，第 373 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L373) 取 `options?.apiKey || getEnvApiKey(model.provider)`。传给 `getEnvApiKey` 的是服务商字符串 `"openai"`；函数定义在 [env-api-keys.ts，第 65 行](../pi-master/packages/ai/src/env-api-keys.ts#L65)，[第 113 行](../pi-master/packages/ai/src/env-api-keys.ts#L113) 将 `openai` 对应到 `OPENAI_API_KEY`。这与前面按 `model.api` 查协议实现，是两次不同的查找。

**例子：传入的选项，最后怎样交给下一层。** 假设显式提供了下面这些选项，Key 只是占位文字：

```ts
const options = {
  apiKey: "<示例Key>",
  temperature: 0,
  maxTokens: 128,
  reasoning: "medium" as const,
};
```

对照源码逐项看：

| 传进来的值 | 这一层做什么 | 下一层拿到什么 |
| --- | --- | --- |
| `apiKey: "<示例Key>"` | 已有显式 Key，不再取环境变量 | `apiKey: "<示例Key>"` |
| `temperature: 0` | `buildBaseOptions` 保留它 | `temperature: 0` |
| `maxTokens: 128` | 已指定上限，就用这个值 | `maxTokens: 128` |
| `reasoning: "medium"` | 整理成具体入口的选项名 | `reasoningEffort: "medium"` |

“传过去”不等于每个模型都使用推理强度，后面的实现还会看模型能力。若完全没指定 `maxTokens`，`buildBaseOptions` 才根据模型上限算默认值；既没有显式 Key、环境变量也没 Key，就在前面的 `if (!apiKey)` 报错。

`satisfies` 也拿这次数据看：它会检查 `maxTokens: 128` 这样的字段类型；如果把它写成字符串 `"128"`，类型检查就会提醒你。它不会替你把字符串转换成数字。

如果直接调用这个具体文件中的简化函数，缺少 Key 会同步抛错；通过前面登记的延迟入口调用时，包装层会把同步错误转成外层流的错误事件。这段 `catch` 的代码放在第 13.6 节，先继续看正常情况下怎么发请求。

## 13. streamOpenAICompletions：从 SDK 请求到流式事件，再回到 Agent

这一节把请求和返回接在一起讲：先看 SDK 怎么用，再看请求怎么发、chunk 怎么变成 Pi 事件、事件怎么回到 Agent。代码走完以后，再回看函数类型、具体返回值，以及为什么要这样分工。

**先直接用 OpenAI SDK，看看 chunk 到底怎么读。** 假设项目已安装 `openai`，并配置了 `OPENAI_API_KEY`，下面这段就是一个最简的文字流式调用示例，放在支持顶层 `await` 的 Node.js ES 模块中使用。它沿用本章的 `gpt-4o-mini`，运行时会发起一次实际请求：

```ts
import OpenAI from "openai";

const client = new OpenAI(); // 默认从 OPENAI_API_KEY 读取 Key。

const openaiStream = await client.chat.completions.create({
  model: "gpt-4o-mini",
  messages: [{ role: "user", content: "Hello!" }],
  stream: true,
});

let answer = "";
for await (const chunk of openaiStream) {
  const delta = chunk.choices[0]?.delta.content ?? "";
  answer += delta;
  process.stdout.write(delta);
}

console.log("\n完整回答：", answer);
```

先抓住三步：`new OpenAI()` 创建客户端；`create({ ..., stream: true })` 发起请求并返回后续可读取的流；`for await` 每次取出一个 SDK 已解析好的 `chunk` 对象。这里的 `await create(...)` 结束时，整段回答还没有全部生成，后面还要继续读流。这种调用和读取方式可对照 [OpenAI 官方流式调用示例](https://developers.openai.com/api/docs/guides/streaming-responses)。

`chunk` 不是一段可以直接打印的字符串。假设这次新增的正文是 `H`，拿到的对象可以简化成下面这样，省略其他字段：

```json
{
  "id": "chatcmpl-example",
  "choices": [
    {
      "index": 0,
      "delta": { "content": "H" },
      "finish_reason": null
    }
  ]
}
```

因此，示例里的取值过程就是：

```text
chunk                    本次收到的整个对象
  → choices[0]           本次回答的第一个候选项
  → delta                这一次新增的信息
  → content              其中新增的正文："H"
```

**假设最终回答是 `Hi!`，它可能按下面的顺序到达。** 这里只是教学示意，实际分段不固定，一个 chunk 可能带多个字符，也可能没有正文：

| 收到的 chunk | `choices[0].delta` 的示意 | `finish_reason` | 示例代码的效果 |
| --- | --- | --- | --- |
| 第 1 个 | `{ role: "assistant", content: "" }` | `null` | 没有新增正文，暂时不显示文字 |
| 第 2 个 | `{ content: "H" }` | `null` | 输出 `H`，`answer` 变成 `"H"` |
| 第 3 个 | `{ content: "i!" }` | `null` | 输出 `i!`，`answer` 变成 `"Hi!"` |
| 第 4 个 | `{}` | `"stop"` | 没有新增正文，表示这次生成正常停止 |

`delta.content` 给的是**这一次增加的文字**。因此代码用 `answer += delta` 累计完整回答，用 `process.stdout.write(delta)` 立即显示新增部分。`?? ""` 把缺少正文或正文为 `null` 的情况当作空字符串；`choices[0]?.` 则容许没有候选项的 chunk，例如开启用量统计后可能出现的用量 chunk。字段含义可对照 [OpenAI 官方 chunk 定义](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events)。

现在再看 Pi 文件就容易对上了：[openai-completions.ts，第 147 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L147) 也是调用 SDK 的 `.create(...)`，[第 187 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L187) 也是 `for await (const chunk of openaiStream)`。不同的是，Pi 要把结果继续交给 Agent，所以在 [第 228 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L228) 累计 `currentBlock.text`，再把新增文字包装为 `text_delta` 事件，放进自己的事件流。SDK 的 chunk 和 Pi 的事件，就在这里接起来了。

**再看 Pi 怎么封装这次调用。** 沿用第 1 节准备的 `model`，假设已配置 `OPENAI_API_KEY`，我们可以直接调用具体模块的导出，观察这个函数接收什么、交回什么。下面是教学示例，不是让 Agent 在主流程中多发一次请求；实际运行它会发起一次模型请求：

```ts
import type { Context } from "@mariozechner/pi-ai";
import { streamOpenAICompletions } from "@mariozechner/pi-ai/openai-completions";

const context: Context = {
  systemPrompt: "You are a helpful assistant.",
  messages: [{ role: "user", content: "Hello!", timestamp: Date.now() }],
};

const events = streamOpenAICompletions(model, context, { maxTokens: 128 });

for await (const event of events) {
  if (event.type === "text_delta") {
    process.stdout.write(event.delta);
  }
}

const answer = await events.result();
console.log(answer.stopReason);
```

调用时传入模型配置、对话上下文和选项，立即拿回 `events` 这个流对象。假设模型分两次返回 `H` 和 `i!`，`for await` 就能逐次读到新增文字，终端合起来显示 `Hi!`；`result()` 则取得最终的助手消息。示例直接读取的是 Pi 模型事件，所以判断 `text_delta` 即可；开头 Agent 的订阅回调外面还有一层 `message_update`，回程部分再接上。

现在打开 [openai-completions.ts，第 110 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L110)，函数开头是：

```ts
export const streamOpenAICompletions: StreamFunction<"openai-completions", OpenAICompletionsOptions> = (
  model: Model<"openai-completions">,
  context: Context,
  options?: OpenAICompletionsOptions,
): AssistantMessageEventStream => {
  const stream = new AssistantMessageEventStream();
  // 后续实现省略
```

这段是**函数开头的局部摘录**。把例子和形参对上：`model` 接住第 1 节的模型对象，`context` 接住包含 `Hello!` 的上下文，`options` 接住 `{ maxTokens: 128 }`。返回类型就是例子中可以逐条读取、也可以等待最终结果的流。

接着看整体结构，下面是**省略细节后的教学示意**：

```ts
const stream = new AssistantMessageEventStream();

(async () => {
  // 创建本次助手消息 output，初始内容为空
  try {
    // 创建客户端，整理请求，读取模型返回内容
    // 一边更新 output，一边 stream.push(...) 发出事件
  } catch (error) {
    // 把失败整理成错误消息和事件
  }
})();

return stream;
```

`output` 保存到目前为止已经累计好的回答；`stream` 用来向外传递变化。外层函数返回的是 `stream`，不是最终的 `output`。

这里的 `(async () => { ... })()` 是定义完立刻执行的异步函数。它会运行到需要等待的位置，再在后续恢复；外层则可以先把流对象交回去。它不代表另开了一个 JavaScript 线程。

**例子：这次输入 `Hello!`，函数先交回来什么。**

```text
创建 stream，同时准备空的助手消息 output
  → 内部异步函数开始准备客户端、等待请求响应
  → 外层先 return stream，调用方拿到可以读取的流
  → 后续模型返回 Hi!，内部继续更新 output
```

所以“函数已经返回”不等于“回答已经完成”。这里先拿到的是接收后续内容的流，回答还在后面逐步到达。

接下来先看请求怎么准备、由哪一行发出去。模型返回后的事件处理接在第 13.3 节继续讲。

### 13.1 准备客户端和请求参数

在 [openai-completions.ts，第 137—142 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L137)，函数依次取得 Key、兼容配置和缓存设置，再由第 141、142 行调用：

```ts
const client = createClient(model, context, apiKey, options?.headers, cacheSessionId, compat);
let params = buildParams(model, context, options, compat, cacheRetention);
```

`createClient` 的实现从 [openai-completions.ts，第 389 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L389) 开始。最后用 `new OpenAI(...)` 创建 SDK 客户端，把 API Key、`model.baseUrl` 和请求头传进去。

`buildParams` 从 [openai-completions.ts，第 435 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L435) 开始。它通过 `convertMessages` 转换消息，再设置 `model: model.id`、`messages`、`stream: true` 等请求字段；有工具时，也会把工具说明转换进请求。

到这里，最初那个模型对象的字段终于分别用到具体位置：

| 字段或参数 | 当前值／来源 | 消费它的位置 | 生成什么 |
| --- | --- | --- | --- |
| `model.api` | 教学示例赋值 `"openai-completions"` | [stream.ts，第 48 行](../pi-master/packages/ai/src/stream.ts#L48) | 选择具体协议入口，已经在前面完成 |
| `model.provider` | 模型表中的 `"openai"` | [openai-completions.ts，第 373 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L373) | 供 `getEnvApiKey` 查凭据 |
| `model.baseUrl` | 模型表中的 `"https://api.openai.com/v1"` | [openai-completions.ts，第 429 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L429) | `new OpenAI` 的 `baseURL` |
| `model.id` | 模型表中的 `"gpt-4o-mini"` | [openai-completions.ts，第 446 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L446) | 请求参数 `params.model` |
| `context` | `streamAssistantResponse` 创建的 `llmContext` | [openai-completions.ts，第 442 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L442) | `convertMessages` 转为 OpenAI 消息，放入第 447 行 `params.messages` |
| `options.signal` | 生命周期创建后一路传入的取消信号 | [openai-completions.ts，第 148 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L148) | SDK `.create` 第二个参数中的 `signal` |

这也说明了为什么 `api`、`provider`、`id` 不能当成同一个东西：它们分别选择协议实现、标识服务商、指定请求的模型。

为什么已经转成 `Message[]`，现在还要转一次？因为前面 `convertToLlm` 得到的是 **Pi 的统一模型消息格式**，不是 OpenAI 的网络请求格式。到这里，Provider 才把它变成 OpenAI 接口使用的 `role`、`content`、`tool_calls` 等结构。

```text
Agent 内部消息 AgentMessage[]
    ↓ convertToLlm
Pi 统一消息 Message[]
    ↓ OpenAI Provider 中的 convertMessages
OpenAI 请求里的 messages
```

这两次转换各有用途。上面的 Agent 逻辑不用为每家模型单独整理应用消息，下面的 Provider 也不用认识每个应用自定义的记录。

发送前还会经过 `onPayload`。调用方如果提供这个回调，就有机会检查或替换最终请求参数；没有替换值时保留原参数。

**例子：`Hello!` 最后变成什么请求参数。** 从 `prompt("Hello!")` 的字符串输入走起，第 4 节会把正文包成文本块数组。假设是本章选定的非推理模型 `gpt-4o-mini`，系统提示词是“用中文回答”，只展示这次请求的主要字段，省略其他选项：

```ts
const params = {
  model: "gpt-4o-mini",
  messages: [
    { role: "system", content: "用中文回答" },
    { role: "user", content: [{ type: "text", text: "Hello!" }] },
  ],
  stream: true,
};
```

`model.id` 变成请求里的 `model`，系统提示词变成第一条消息，用户内容变成第二条消息。Pi 消息里的 `timestamp` 是程序内部记录用的，不会原样作为这个用户消息的字段发出去。SDK 客户端拿着 Key 和地址负责发送，`params` 装的是“这次具体问什么”。

如果想看发送前的参数，可以给 Agent 配置下面的回调。沿用前面准备好的 `model`：

```ts
const agent = new Agent({
  initialState: { model },
  onPayload: (payload) => {
    console.log(payload);
    // 不返回替换值，继续发送原来的参数。
  },
});
```

调用 `prompt("Hello!")` 时，这个回调能看到整理后的请求数据。

### 13.2 真正发起请求的是哪一行

看 [openai-completions.ts，第 147 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L147)：

```ts
const { data: openaiStream, response } = await client.chat.completions
  .create(params, { signal: options?.signal })
  .withResponse();
await options?.onResponse?.({ status: response.status, headers: headersToRecord(response.headers) }, model);
stream.push({ type: "start", partial: output });
```

这里调用 OpenAI SDK 的 `client.chat.completions.create(...)`，SDK 再负责实际的 HTTP 传输。

`signal` 继续往下传，用户取消任务时，底层请求也有机会被取消。`withResponse()` 让程序同时拿到 SDK 数据流 `openaiStream`，以及 HTTP 的 `response`，后者可以用来查看状态码和响应头。

这个 `await` 结束，也不表示整段答案生成完了，只是拿到了后面可以继续读取的数据流。随后执行响应回调，再推入一条 Pi 的 `start` 事件。

**例子：把请求和返回值对上。** 假设这次服务正常接收请求：

```text
发送：params.model = "gpt-4o-mini"
      params.messages 里有 Hello!
      params.stream = true

拿到：response.status，例如 200
      response.headers，HTTP 响应头
      openaiStream，接下来用它逐段读取回答
```

这里的 HTTP `response` 和第 9 节变量名叫 `response` 的 Pi 事件流不是同一个对象。SDK 给的 `openaiStream` 要继续读，才能知道模型具体回答了什么。

取消也能接到这次请求：外层 `agent.abort()` 会触发本轮 signal；这个 signal 一路传到 `.create(params, { signal })`，SDK 因而有机会中止 HTTP 请求。

走到这里，调用模型的这条线就接上了：`prompt → runAgentLoop → runLoop → streamAssistantResponse → streamSimple → OpenAI Provider → client.chat.completions.create(...)`。下面沿着返回的数据继续看：chunk 怎样变成 Pi 事件，事件怎样交回 Agent，最后再回看函数类型和整条调用链的设计。

### 13.3 模型的新增文字，在哪一行变成 Pi 事件

请求已经发出，也拿到了 `openaiStream`。现在顺着回程看：先读 OpenAI 返回的内容，转成 Pi 的模型事件，再交回 Agent。这里会碰到 `push` 和 `emit`；先看数据经过哪几层，第 14 节再把订阅、通知和等待的代码讲透。

**例子：先认清这次回程中的三个东西。** 假设服务返回了 `"H"`、`"i!"` 两段文字：OpenAI SDK 先交出包含这两段内容的 chunk；Pi Provider 把它们转成 `text_delta`；Agent 再把它们包成 `message_update`。文字还是这两段，只是每层要交给下一层的数据格式不同。下面逐层把代码和数据放在一起看。

在 [openai-completions.ts，第 187 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L187)，程序开始：

```ts
for await (const chunk of openaiStream) {
  // 逐段处理 SDK 交回来的数据
}
```

这段是循环结构示意。SDK 把底层流式响应解析后，交出一个个 chunk；Pi 再从里面读取内容、工具调用、用量和结束原因。

注意，一个 chunk 不保证刚好是一个字或一个词，也不等于网络上一次接收到的数据包。

当前适配器取出第一个 `choice`。如果里面有新增正文，就在对应分支里累计文字。[openai-completions.ts，第 228 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L228) 的关键语句是：

```ts
currentBlock.text += choice.delta.content;
stream.push({
  type: "text_delta",
  contentIndex: blockIndex(),
  delta: choice.delta.content,
  partial: output,
});
```

这里同时做了两件事：

- `currentBlock.text += ...`：把新文字接到已累计内容的后面，最后得到完整回答。
- `stream.push(...)`：报告“这次新增了这一段文字”，让上层可以马上处理。

比如先收到 `"Hel"`，再收到 `"lo"`，累计文字会从 `"Hel"` 变成 `"Hello"`，而两次 `delta` 分别还是 `"Hel"`、`"lo"`。这是说明数据变化的假设例子，不是一次真实请求记录。

所以，README 写的是 `event.assistantMessageEvent.delta`。如果每次把累计全文都直接追加到终端，就可能把已经显示过的内容重复输出。

模型如果返回工具调用，这个文件也会把片段拼起来，产生统一的工具调用事件，但它不在这里直接执行工具。等完整助手消息返回到前面的 `runLoop`，才进入工具执行阶段。

**例子：把 `choice.delta.content` 的值直接代进去。** 下面只列每次要看的几个字段：

```text
第一次：choice.delta.content = "H"
        currentBlock.text 从 "" 变成 "H"
        text_delta 的 delta = "H"

第二次：choice.delta.content = "i!"
        currentBlock.text 从 "H" 变成 "Hi!"
        text_delta 的 delta = "i!"
```

每次向终端追加 `delta`，最后得到 `Hi!`。若每次追加累计全文，就会先写 `H`、再写 `Hi!`，结果显示成 `HHi!`。

### 13.4 成功和失败怎样结束

成功路径在 [openai-completions.ts，第 347 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L347)：

```ts
stream.push({ type: "done", reason: output.stopReason, message: output });
stream.end();
```

失败时会给 `output` 写入错误或取消原因，再在 [openai-completions.ts，第 360 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L360) 推入：

```ts
stream.push({ type: "error", reason: output.stopReason, error: output });
stream.end();
```

成功、失败事件都携带最后的助手消息。上层看到的是 Pi 统一后的事件，不必直接识别 OpenAI SDK 的所有字段。

**例子：同一条提问有两种结束方式。** 下面只展示最终消息中与结果有关的字段：

```text
正常回答：content = [{ type: "text", text: "Hi!" }]
          stopReason = "stop"
          → push({ type: "done", message: 这条最终消息, ... })

中途失败：stopReason = "error"
          errorMessage = "这次失败的原因"
          → push({ type: "error", error: 这条失败消息, ... })
```

所以收到流的最终结果后，还要看 `stopReason`。拿到了一个最终消息对象，只说明这次调用已经结束，不保证它给出了成功回答。

### 13.5 AssistantMessageEventStream：事件可以逐条读，最终消息也可以等

流对象的实现位于 [event-stream.ts，第 4 行](../pi-master/packages/ai/src/utils/event-stream.ts#L4)。`AssistantMessageEventStream` 则在 [event-stream.ts，第 68 行](../pi-master/packages/ai/src/utils/event-stream.ts#L68)，它是一个真正的类，继承 `EventStream`。

`EventStream<T, R>` 的两个类型参数分别表示“每次交付的事件”和“最终结果”。子类把它们确定为 `AssistantMessageEvent` 和 `AssistantMessage`：过程中读到许多事件，最后拿到一条完整助手消息。先看三个方法的配合，再顺手读一下它们背后的实现：

| 用法 | 干什么 |
| --- | --- |
| `stream.push(event)` | 生产者放入一条事件；有人在等就交给它，否则先排队 |
| `for await (const event of stream)` | 消费者逐条读取；当前没有新事件时，异步等待 |
| `await stream.result()` | 等待最终助手消息，成功或失败都可能以消息形式返回 |

`AssistantMessageEventStream` 知道 `done`、`error` 是终态，会从相应事件取出最终消息，完成 `result()` 等待的 Promise。它不负责发网络请求，也不自己把文字拼成完整回答；累计工作已经由 Provider 更新 `output` 完成了。

**第一步，看它保存了什么。** [event-stream.ts，第 5—9 行](../pi-master/packages/ai/src/utils/event-stream.ts#L5) 的字段是：

```ts
private queue: T[] = [];
private waiting: ((value: IteratorResult<T>) => void)[] = [];
private done = false;
private finalResultPromise: Promise<R>;
private resolveFinalResult!: (result: R) => void;
```

`queue` 保存已经到达、还没被取走的事件；`waiting` 保存“有人在等下一条事件”时那个 Promise 的 `resolve` 函数。`done` 标记是否结束，最后两个字段则单独保存最终结果的 Promise，以及完成它的函数。

因此，[第 20 行](../pi-master/packages/ai/src/utils/event-stream.ts#L20) 的 `push(event)` 有两种交付方式：如果 `waiting` 中有人等，就取出一个 `resolve`，把事件交给它；否则先放进 `queue`。用 `H` 这一段文字代进去，就是：

```text
事件先到：push(E_H) → queue 暂存 → 消费者来取 → 取出 E_H
读取先到：消费者等待 → waiting 保存 resolve → push(E_H) → 唤醒消费者
```

**第二步，看为什么能用 `for await`。** 关键是 [第 49—61 行](../pi-master/packages/ai/src/utils/event-stream.ts#L49) 的异步迭代器：

```ts
async *[Symbol.asyncIterator](): AsyncIterator<T> {
  while (true) {
    if (this.queue.length > 0) {
      yield this.queue.shift()!;
    } else if (this.done) {
      return;
    } else {
      const result = await new Promise<IteratorResult<T>>((resolve) => this.waiting.push(resolve));
      if (result.done) return;
      yield result.value;
    }
  }
}
```

`async *` 表示异步生成器，`yield` 每次交出一条事件。`for await` 会通过这个迭代器逐条取值：有排队的事件就取；队列空了且已经结束，就退出；否则创建 Promise，把 `resolve` 存进 `waiting`，等下一次 `push` 唤醒。等待时没有不停检查队列，也不会卡住整个 JavaScript 线程。

**第三步，看最终结果怎样完成。** 构造函数在 [第 14—17 行](../pi-master/packages/ai/src/utils/event-stream.ts#L15) 创建 `finalResultPromise`，并把它的 `resolve` 保存下来。`result()` 在 [第 63 行](../pi-master/packages/ai/src/utils/event-stream.ts#L63) 只是返回这个 Promise，不会重新读取或拼接事件。

父类通过构造参数 `isComplete` 判断终态，通过 `extractResult` 提取结果。子类传入的规则就是：`done` 取 `event.message`，`error` 取 `event.error`。所以 Provider 推入终态事件时，`push` 先完成最终结果的 Promise，再把这条事件正常交付出去；`result()` 不需要等调用方把所有事件读完才有结果。

紧接着 Provider 调用的 `end()`，对应 [第 37 行](../pi-master/packages/ai/src/utils/event-stream.ts#L37)：标记结束，并唤醒仍在等待的读取，让它们退出。已经进入 `queue` 的事件仍会被读出，因为迭代器先检查队列，再检查结束标记。这里不传结果的 `end()` 本身不会完成最终结果的 Promise；正常路径前面的终态事件已经完成了它，也可以通过 `end(result)` 显式提供结果。

**例子：读增量，同时保留最后的完整消息。** 假设 `response` 是本次 `Hello!` 请求返回的 Pi 模型事件流：

```ts
for await (const event of response) {
  if (event.type === "text_delta") {
    console.log("这次新增：", event.delta);
  }
}
const finalMessage = await response.result();
console.log("最终消息：", finalMessage.content);
```

按上面的假设，会依次看到新增 `H`、新增 `i!`，最后拿到正文为 `Hi!` 的消息。`push` 是 Provider 往里放，`for await` 是这里往外取，`result()` 则等最后那条消息；它不会再请求一次模型。

前面第 11 节还留下了一个问题：模块延迟加载时，调用方拿到的流和具体 Provider 返回的流怎么接起来？接下来就看这段转发代码。

### 13.6 回到延迟加载那一层：inner 的事件怎样转给 outer

看 [register-builtins.ts，第 194 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L194)，下面摘取 `createLazySimpleStream` 返回的函数：

```ts
return (model, context, options) => {
  const outer = new AssistantMessageEventStream();

  loadModule()
    .then((module) => {
      const inner = module.streamSimple(model, context, options);
      forwardStream(outer, inner);
    })
    .catch((error) => {
      const message = createLazyLoadErrorMessage(model, error);
      outer.push({ type: "error", reason: "error", error: message });
      outer.end(message);
    });

  return outer;
};
```

它先建一个 `outer` 事件流，启动模块加载，然后马上返回 `outer`。模块加载完成后，再调用具体函数，拿到 `inner` 流。

`forwardStream` 在 [register-builtins.ts，第 138 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L138)：

```ts
function forwardStream(target: AssistantMessageEventStream, source: AsyncIterable<AssistantMessageEvent>): void {
  (async () => {
    for await (const event of source) {
      target.push(event);
    }
    target.end();
  })();
}
```

它逐条读取 `inner` 里的事件，推到 `outer`。所以调用方不需要先学会怎样等模块加载，它拿到一个流，就能统一地等后面的事件。

```text
streamSimple 按协议找到延迟入口
    ↓
先返回 outer，让调用方可以等待事件
    ↓
对应模块加载完成
    ↓
调用具体 streamSimpleOpenAICompletions，得到 inner
    ↓
把 inner 中的事件逐条转发到 outer
```

`outer` 和 `inner` 都是进程内的 Pi 事件流。它们不是两次模型请求，也不是两个 HTTP 连接。模块加载失败，包装层会往 `outer` 放入错误事件并结束。

**例子：`inner` 里的一条文字事件，怎么到 `outer`。**

```text
inner 产生 E：{ type: "text_delta", delta: "H", ... }
  → forwardStream 的 for await 取出 E
  → target.push(E)，这里的 target 就是 outer
  → 等待 outer 的上层代码读到 E
```

这段转发没有重新生成文字，而是把同一条事件交到外层流。如果加载模块就失败了，`inner` 还没创建，包装函数的 `catch` 会直接向 `outer` 放一个 `error` 事件；上层仍从已经拿到的 `outer` 读到失败。

### 13.7 回到 streamAssistantResponse，看它怎样包一层 Agent 事件

重新打开 [agent-loop.ts，第 350 行](../pi-master/packages/agent/src/agent-loop.ts#L350)。这个函数拿到 `response` 后，会用 `for await` 读取底层事件。

收到 `start` 时，把初始助手消息加入循环上下文，再发出 Agent 层的 `message_start`。

收到文字、思考或工具调用的更新时，走下面这一段。摘录位置是 [agent-loop.ts，第 368 行](../pi-master/packages/agent/src/agent-loop.ts#L368)：

```ts
if (partialMessage) {
  partialMessage = event.partial;
  context.messages[context.messages.length - 1] = partialMessage;
  await emit({
    type: "message_update",
    assistantMessageEvent: event,
    message: { ...partialMessage },
  });
}
```

这一步是整条回传路线的关键。底层事件原本是：

```text
type: "text_delta"
delta: 这次新增的文字
```

到了 Agent 层，会变成：

```text
type: "message_update"
assistantMessageEvent: 刚才那条 text_delta 事件
message: 当前已累计的助手消息
```

所以开头需要连续检查两个 `type`，因为它们处在两层：外面报告 Agent 的消息更新，里面保留具体是哪种模型输出更新。

这里更新的是正在生成的那条消息，不是每收到一段文字就向历史追加一条新消息。代码里的 `{ ...partialMessage }` 也是浅拷贝，不是把所有嵌套内容深拷贝一份。

收到 `done` 或 `error` 时，函数等待 `response.result()`，用最终消息替换上下文里的临时消息，再发出 `message_end`，把最终助手消息返回给 `runLoop`。

**例子：收到第二段 `"i!"` 时，内外两层放什么。** 下面只展示关心的字段，省略消息的模型、用量和时间等信息：

```text
外层 AgentEvent：
  type = "message_update"
  message.content = [{ type: "text", text: "Hi!" }]
  assistantMessageEvent：
    type = "text_delta"
    delta = "i!"
```

要把新文字追加到终端，就取里面的 `delta`，得到 `i!`；要重画整条消息，就读外面的 `message.content`，得到当前完整的 `Hi!`。

浅拷贝也代个值。下面只演示普通对象的引用关系：

```ts
const partial = { content: [{ type: "text", text: "H" }] };
const copied = { ...partial };
partial.content[0].text = "Hi!";
console.log(copied.content[0].text); // "Hi!"
```

所以 `{ ...partialMessage }` 不会把里面的数组一起冻结成旧版本。若要保存当时的独立记录，还得复制需要保留的数据。

### 13.8 回到 provider.streamSimple：它与 StreamFunction 是什么关系

第 10 节的调用是：

```ts
return provider.streamSimple(model, context, options);
```

现在我们已经找到实际执行的函数，再看 IDE 给这个属性显示的类型。`getApiProvider` 返回的内部对象使用 [api-registry.ts，第 29—33 行](../pi-master/packages/ai/src/api-registry.ts#L29) 的约定：

```ts
interface ApiProviderInternal {
  api: Api;
  stream: ApiStreamFunction;
  streamSimple: ApiStreamSimpleFunction;
}
```

继续跳到同文件 [第 17—21 行](../pi-master/packages/ai/src/api-registry.ts#L17)：

```ts
export type ApiStreamSimpleFunction = (
  model: Model<Api>,
  context: Context,
  options?: SimpleStreamOptions,
) => AssistantMessageEventStream;
```

读成人话，就是：“这是一个函数，收模型、上下文和可选的统一选项，返回助手消息事件流。”那么具体实现上的 `StreamFunction` 又是什么？定义在 [types.ts，第 136—140 行](../pi-master/packages/ai/src/types.ts#L136)：

```ts
export type StreamFunction<TApi extends Api = Api, TOptions extends StreamOptions = StreamOptions> = (
  model: Model<TApi>,
  context: Context,
  options?: TOptions,
) => AssistantMessageEventStream;
```

它把两个位置留给使用方填写：`TApi` 决定模型的协议类型，`TOptions` 决定选项类型。`= Api`、`= StreamOptions` 是未填写类型参数时的默认值。把不同位置使用的类型展开，就能看出区别：

| 出现的位置 | 函数类型 | 模型参数 | 选项参数 |
| --- | --- | --- | --- |
| 注册表取回的 `provider.streamSimple` | `ApiStreamSimpleFunction` | `Model<Api>` | `SimpleStreamOptions` |
| 登记时 `ApiProvider` 的简化入口 | `StreamFunction<TApi, SimpleStreamOptions>` | `Model<TApi>` | `SimpleStreamOptions` |
| OpenAI 文件中的简化入口 | `StreamFunction<"openai-completions", SimpleStreamOptions>` | `Model<"openai-completions">` | `SimpleStreamOptions` |
| OpenAI 文件中的完整入口 | `StreamFunction<"openai-completions", OpenAICompletionsOptions>` | `Model<"openai-completions">` | `OpenAICompletionsOptions` |

四种都返回 `AssistantMessageEventStream`。从函数签名看，`ApiStreamSimpleFunction` 就相当于把 `StreamFunction` 填成 `StreamFunction<Api, SimpleStreamOptions>`。不过源码是单独写出这个类型别名的，没有通过继承产生它，也不会因为写了类型就自动生成一个实现。

**为什么具体实现限定一个协议，注册表却写成 `Model<Api>`？** 因为这张 Map 要统一存放各种协议的入口。写 OpenAI 实现时，可以明确知道自己处理的是 `"openai-completions"`；从 Map 取回对象时，公共类型只知道它是某个 `Api` 的实现。

这也解释了第 10.4 节为什么有 `wrapStreamSimple`。再看它最关键的三处：

```ts
function wrapStreamSimple<TApi extends Api>(
  api: TApi,
  streamSimple: StreamFunction<TApi, SimpleStreamOptions>,
): ApiStreamSimpleFunction {
  return (model, context, options) => {
    if (model.api !== api) {
      throw new Error(`Mismatched api: ${model.api} expected ${api}`);
    }
    return streamSimple(model as Model<TApi>, context, options);
  };
}
```

它接收一个限定协议的函数，返回一个供注册表统一存储的函数。新函数先比较实际的 `model.api` 与登记时记住的 `api`；一致以后，再用类型断言把模型交给原入口。断言本身不会检查或改写模型，运行时的检查来自前面的 `if`。

**把本次调用代进去：** 登记时记住 `api = "openai-completions"` 和延迟简化入口；调用时收到本章的 `model`，检查通过，再继续加载模块并调用具体简化入口。如果把其他协议的模型误交给这份注册对象，包装函数会在这里报错。

还要分清两个不同动作：`wrapStreamSimple` 负责检查协议并转交原参数；第 12 节的 `streamSimpleOpenAICompletions` 才负责整理选项。后者把统一的 `reasoning` 整理成具体入口使用的 `reasoningEffort`，然后调用完整实现。`SimpleStreamOptions` 定义在 [types.ts，第 122 行](../pi-master/packages/ai/src/types.ts#L122)，`OpenAICompletionsOptions` 定义在 [openai-completions.ts，第 76 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L76)，两者都扩展通用的 `StreamOptions`。

所以 **Simple 说的是输入选项统一，返回值仍然是流**。最后把函数与类型一起连起来：

```text
stream.ts 的 streamSimple
  → 查注册表，取得 provider.streamSimple：ApiStreamSimpleFunction
  → 包装函数检查协议，再调用登记的延迟简化入口
  → 加载 openai-completions.js，取得具体简化入口
  → streamSimpleOpenAICompletions：
      StreamFunction<"openai-completions", SimpleStreamOptions>
  → 整理 options，再调用 streamOpenAICompletions：
      StreamFunction<"openai-completions", OpenAICompletionsOptions>
  → 创建 SDK 请求，返回 AssistantMessageEventStream
```

沿着 `provider.streamSimple` 找实现，要追的是对象中保存的函数值；沿着 `ApiStreamSimpleFunction` 找定义，看到的是这个函数允许怎样调用。现在这两条线已经对上。下一小节再用一次完整的返回过程，把“流对象”和“最终消息”分清楚。

### 13.9 把返回值摆出来：流对象、文字回答和工具调用

前面已经看过事件怎样产生和转发，现在把实际拿到的值摆出来。

**先看返回的 stream 对象长什么样。** 回到 [agent-loop.ts，第 336 行](../pi-master/packages/agent/src/agent-loop.ts#L336) 的 `streamAssistantResponse`，刚才的调用结果被这里的 `response` 接住：

```ts
const response = await streamFunction(config.model, llmContext, {
  ...config,
  apiKey: resolvedApiKey,
  signal,
});
```

此时 `response` 是一个 `AssistantMessageEventStream` 实例。假设流刚创建、还没有事件到达，也还没有人开始读取，内部状态可以示意成这样：

```text
AssistantMessageEventStream {
  queue: [],                         暂存还没被取走的事件
  waiting: [],                       暂存等下一条事件的 resolve 函数
  done: false,                       目前还没结束
  finalResultPromise: Promise { <pending> },
  resolveFinalResult: [Function],
  isComplete: [Function],             判断事件是否为 done 或 error
  extractResult: [Function]           从终态事件取出助手消息
}
```

这是根据 [event-stream.ts，第 4—18 行](../pi-master/packages/ai/src/utils/event-stream.ts#L4) 画出的对象结构示意，不是 JSON，也不是某次请求的真实打印。`push()`、`end()`、`result()` 和异步迭代器这些方法定义在原型上，因此没有作为数据字段列进去。**拿到这个对象，只表示拿到了后续读取事件的入口，里面还没有一份已经完成的 `Hi!`。**

当前默认的延迟加载路径中，OpenAI 函数里创建的 `stream` 是内层流，`response` 拿到的是延迟入口返回的外层流；两者都是这种类的实例。内层产生的事件会转到外层，第 13.6 节已经展开了这段转发。

**接着看，这个对象会让上层读到什么。** 假设本次仍然回答 `Hi!`，在 [agent-loop.ts，第 350 行](../pi-master/packages/agent/src/agent-loop.ts#L350) 的 `for await` 中，先后读到的事件可以示意为：

```text
start        → 开始一条助手消息，带有 partial
text_start   → 开始第 0 个文字块，带有 partial
text_delta   → delta: "H"，带有 partial
text_delta   → delta: "i!"，带有 partial
text_end     → content: "Hi!"，带有 partial
done         → reason: "stop"，message: 最终助手消息
```

这是事件的先后顺序，不是说 `response` 本身就是这样一个数组。事件可以一边产生、一边被取走；`partial` 携带当前累计的助手消息，也不保证每次都深拷贝出一个独立对象。

**最后看，`streamAssistantResponse` 自己返回什么。** 读到 `done` 后，函数在 [第 381 行](../pi-master/packages/agent/src/agent-loop.ts#L381) 执行 `await response.result()`，得到完整助手消息。假设这次正常结束，消息对象可以长这样；用量、费用、ID 和时间都只是教学占位值：

```json
{
  "role": "assistant",
  "content": [{ "type": "text", "text": "Hi!" }],
  "api": "openai-completions",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "responseId": "chatcmpl-example",
  "usage": {
    "input": 0,
    "output": 0,
    "cacheRead": 0,
    "cacheWrite": 0,
    "totalTokens": 0,
    "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0 }
  },
  "stopReason": "stop",
  "timestamp": 1
}
```

函数把这条消息写回上下文，在 [第 390 行](../pi-master/packages/agent/src/agent-loop.ts#L390) 发出 `message_end`，等事件处理完成后，在第 391 行 `return finalMessage`。所以返回到 [runLoop 的第 237 行](../pi-master/packages/agent/src/agent-loop.ts#L237) 时：

```ts
const message = await streamAssistantResponse(currentContext, config, signal, emit, streamFn);
```

这里的 `message` 就是上面那条助手消息对象。可以直接看 `message.content` 和 `message.stopReason`，然后决定后面有没有工具要执行。它已经不是流对象，也不是只含 `"Hi!"` 的字符串。

把三个值最后对一下：

```text
streamFunction(...) 返回的 response     → 可以逐条读取的流对象
await response.result()                → 一条完整的 AssistantMessage
await streamAssistantResponse(...)     → 返回这条 AssistantMessage，交给 runLoop
```

**如果模型这次要调用工具，返回的对象又长什么样？** 假设用户问：“请用 `sum` 工具算一下 2 加 3。”Agent 已经配置了名为 `sum` 的工具，参数是数字 `a`、`b`；下面假设模型选择调用它，工具成功返回 `5`，也没有其他要求让本轮提前终止。仍然只看教学数据，不把它当成真实请求记录。

流对象还是前面那种 `AssistantMessageEventStream`，改变的是里面交付的事件。假设这一轮没有额外的说明文字，只有一个工具调用，那么事件可以示意为：

```text
start          → 开始一条助手消息
toolcall_start → 开始第 0 个工具调用块
toolcall_delta → delta: '{"a":2,'
toolcall_delta → delta: '"b":3}'
toolcall_end   → toolCall: { type: "toolCall", id: "call_sum_1", name: "sum", arguments: { a: 2, b: 3 } }
done           → reason: "toolUse"，message: 带有上述工具调用的助手消息
```

`toolcall_delta` 的 `delta` 是逐段到达的参数字符串，最终 `arguments` 则是解析后的对象。具体分段不固定。可以对照 [openai-completions.ts，第 282—315 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L282)：Provider 累计参数字符串，解析参数并推入工具调用事件。结束一个工具调用块时，还会移除内部暂存的 `partialArgs`，所以最终消息里不需要保存它。

读到终态后，`await response.result()` 取得、再由 `streamAssistantResponse` 返回的完整消息可以长这样，用量等字段仍用教学占位值：

```json
{
  "role": "assistant",
  "content": [
    {
      "type": "toolCall",
      "id": "call_sum_1",
      "name": "sum",
      "arguments": { "a": 2, "b": 3 }
    }
  ],
  "api": "openai-completions",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "responseId": "chatcmpl-tool-example",
  "usage": {
    "input": 0,
    "output": 0,
    "cacheRead": 0,
    "cacheWrite": 0,
    "totalTokens": 0,
    "cost": { "input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0 }
  },
  "stopReason": "toolUse",
  "timestamp": 1
}
```

先看两处变化：`content` 中的块变成了 `toolCall`，`stopReason` 变成了 `"toolUse"`。这条消息仍是助手消息，意思是“模型提出了一个工具调用”，此时还没有工具的计算结果。消息也可以同时带文字块和工具调用块，只是这个例子为了看清结构省去了文字。

**这里的 `done` 只表示这一次模型返回结束，整次 Agent 任务还可以继续。** 回到 `runLoop`，它在 [agent-loop.ts，第 247 行](../pi-master/packages/agent/src/agent-loop.ts#L247) 这样找工具调用：

```ts
const toolCalls = message.content.filter((c) => c.type === "toolCall");
```

所以它实际找的是 `content` 里的工具调用块，不是只看 `stopReason` 就执行工具。本例会找到 `call_sum_1`，再在 [第 252 行](../pi-master/packages/agent/src/agent-loop.ts#L252) 交给 `executeToolCalls`。完成工具查找、参数检查等准备后，[第 668 行](../pi-master/packages/agent/src/agent-loop.ts#L668) 才真正调用工具的 `execute`。

假设这个 `sum` 工具把正文 `"5"` 和空的附加信息 `{}` 作为结果返回，[第 761 行](../pi-master/packages/agent/src/agent-loop.ts#L761) 的 `createToolResultMessage` 会把它整理成下面这样的工具结果消息：

```json
{
  "role": "toolResult",
  "toolCallId": "call_sum_1",
  "toolName": "sum",
  "content": [{ "type": "text", "text": "5" }],
  "details": {},
  "isError": false,
  "timestamp": 2
}
```

`toolCallId` 对应前面工具调用的 `id`，表示“这个 `5` 是哪次调用的结果”。工具结果会加入上下文，循环再请求一次模型。本例中模型接着回答“2 加 3 等于 5”，第二次 `streamAssistantResponse` 返回的助手消息就又是文字回复；下面只展示关键字段，其余模型信息和用量字段省略：

```json
{
  "role": "assistant",
  "content": [{ "type": "text", "text": "2 加 3 等于 5。" }],
  "stopReason": "stop"
}
```

把这次完整的过程串起来：

```text
用户提问：请用 sum 计算 2 加 3
  → 第一次调用模型：返回 assistant 消息，content 中有 toolCall
  → streamAssistantResponse 返回这条消息，stopReason 为 toolUse
  → runLoop 找到工具调用，Agent 执行 sum({ a: 2, b: 3 })
  → 生成 toolResult 消息，通过 toolCallId 对上这次调用，正文是 5
  → 把工具结果交回模型，再生成一条正文为“2 加 3 等于 5。”的 assistant 消息
  → 没有新的工具调用或其他待处理消息，本次任务结束
```

因此，一次 `prompt` 中可以多次进入 `streamAssistantResponse`：第一次拿到工具调用要求，执行工具后，第二次再拿到面向用户的回答。`streamOpenAICompletions` 负责把模型提出的工具调用交回来，实际执行工具的是 Agent。

接下来再回答一个很自然的问题：为什么要分这么多层？

### 13.10 为什么要用接口、分这么多文件：这样写到底方便在哪里

前面为了找到一次 OpenAI 调用，我们跳了不少文件。读到这里，很容易想：“我直接写个函数，调用 SDK，再把结果打印出来，不就行了吗？”先把这些接口和文件带来的好处一条条说清楚，再回头看这个问题。

**先说接口有什么好处。** 这里说的接口，包括源码里的 `interface`、`type` 和函数类型。它们都在帮我们说明一件事：调用时要给什么，调用后能拿到什么。

1. **不用猜参数怎么传。** 比如看到 `StreamFunction`，就知道要给它模型配置、对话上下文和选项，拿回来的是助手消息事件流。调用者不用先把 OpenAI 那几百行实现读完，才知道这个函数怎么用。

2. **很多错误可以提前发现。** 比如 `maxTokens` 应该是数字，你却传了字符串，TypeScript 就能提醒你。模型配置缺字段、函数返回的东西不对，也有机会在检查代码时发现。当然，它不能保证网络一定成功，运行时该检查的地方仍然要检查。

3. **换模型时，前面的流程可以接着用。** Agent 可以一直按“传入上下文、读取事件”的方式工作。下面换成 Claude 的实现，只要仍按 Pi 约定交回事件，前面组织对话、处理工具的主要代码就能继续用。具体支持哪些能力，还得看新模型。

4. **显示回答的代码也能共用。** OpenAI 返回的是它自己的 chunk，其他服务有其他格式。各家实现先把新增文字整理成 Pi 的 `text_delta`，上面显示文字的代码就不用为每家重新写一套。这也是开头那个订阅回调能保持简单的原因。

5. **几个人可以分头写。** 一个人写 Agent 循环，一个人接 OpenAI，另一个人接其他服务。大家先约定好传什么、返回什么，就可以分别实现，不用等一个人把整个框架全部写完，其他人才开始。

6. **测试时容易换一个可控制的实现。** 比如想检查“模型提出工具调用以后，Agent 有没有执行工具”，可以给 `streamFn` 传入一个自己写的函数，让它按约定返回工具调用事件。这样就能检查 Agent 的处理过程，不必每次都请求真实模型，也不用等模型碰巧给出我们想测试的回答。

**光说“方便扩展、方便复用”还不够，我们拿四件具体的事来试一试。** 下面的代码是教学示例，重点看需求变了以后，哪些地方要改，哪些地方还能接着用。

**例子一：原来用 OpenAI，现在换成 Claude，显示文字的代码要重写吗？**

原来的模型配置是 `getModel("openai", "gpt-4o-mini")`。如果改用模型表中的 Claude，可以这样创建 Agent；下面只演示配置和订阅，不发请求：

```ts
import { Agent } from "@mariozechner/pi-agent-core";
import { getModel } from "@mariozechner/pi-ai";

const demoAgent = new Agent({
  initialState: {
    model: getModel("anthropic", "claude-sonnet-4-20250514"),
  },
});

demoAgent.subscribe((event) => {
  if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
    process.stdout.write(event.assistantMessageEvent.delta);
  }
});
```

看下面的 `subscribe`，是不是和开头一样？它没有增加“如果是 Claude，就这样读文字”的判断。为什么能这样？直接去看两份源码就知道：

- [openai-completions.ts，第 228—233 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L228) 从 `choice.delta.content` 取新增文字，再交出 Pi 的 `text_delta` 事件。
- [anthropic.ts，第 511—520 行](../pi-master/packages/ai/src/providers/anthropic.ts#L511) 从 `event.delta.text` 取新增文字，也交出 Pi 的 `text_delta` 事件。

两家取文字的方式不一样，但上层收到的事件格式一样。因此，这次主要改的是模型选择，并准备对应服务的凭据；显示代码和 Agent 的主要循环可以继续用。**统一事件格式的好处，就体现在这里：下面换一家，上面不用再学一套取文字的方法。**

**例子二：学校自己做了一个模型服务，怎么接进来？**

假设它使用一种新的协议，我们已经写好了 `streamCampus` 和 `streamSimpleCampus`，分别符合完整入口和简化入口的函数约定。接下来可以按 [api-registry.ts，第 66 行](../pi-master/packages/ai/src/api-registry.ts#L66) 的方式登记，下面是登记部分的教学片段：

```ts
registerApiProvider({
  api: "campus-api",
  stream: streamCampus,
  streamSimple: streamSimpleCampus,
});
```

再给 Agent 提供一份 `api: "campus-api"` 的模型配置。[stream.ts，第 48—49 行](../pi-master/packages/ai/src/stream.ts#L48) 原来的两行代码就能根据这个名称取出我们登记的函数。它不需要增加 `if (model.api === "campus-api")`，Agent 循环也不需要知道学校的服务器怎么收发数据。

当然，具体的请求、消息转换和认证还是要写；登记 API 函数也不会自动把模型加入 `getModel` 的内置模型表。**省下来的是重复修改公共调用流程的工作。** 如果学校服务使用已有的兼容协议，还可能复用已有实现，通过模型配置指定地址。

**例子三：今天没有模型服务，能不能先检查 Agent 会不会处理回答？**

可以。仓库已经提供了模拟实现：[faux.ts，第 391 行](../pi-master/packages/ai/src/providers/faux.ts#L391) 的 `registerFauxProvider`。下面是一个使用它的教学示例：

```ts
import { Agent } from "@mariozechner/pi-agent-core";
import { fauxAssistantMessage, registerFauxProvider } from "@mariozechner/pi-ai";

const faux = registerFauxProvider();
try {
  faux.setResponses([fauxAssistantMessage("Hi!")]);

  const testAgent = new Agent({ initialState: { model: faux.getModel() } });
  await testAgent.prompt("Hello!");

  console.log(testAgent.state.messages.at(-1)?.content);
  // 最后一条消息的正文是 [{ type: "text", text: "Hi!" }]。
} finally {
  faux.unregister();
}
```

这里先把预定回答 `Hi!` 放进去，再照常调用 `prompt`。模拟实现不会请求真实模型，它会把准备好的回答作为 Pi 事件交回来。Agent 仍然走原来的消息处理流程，最后把助手消息放进历史。

为什么不需要给 Agent 再写一个“测试专用的 prompt”？因为 [faux.ts，第 467—470 行](../pi-master/packages/ai/src/providers/faux.ts#L467) 也按同样的 `stream`、`streamSimple` 约定登记入口。**真实服务和模拟服务做事的方法不同，但对 Agent 来说，它们的调用方式相同。** 这就能把“Agent 会不会处理消息”和“网络、凭据、模型服务是否正常”分开检查。

**例子四：同学把参数写错了，什么时候能发现？**

下面是一个故意写错的教学片段，`SimpleStreamOptions` 来自 `pi-ai`：

```ts
const options: SimpleStreamOptions = {
  maxTokens: "128", // 类型错误：这里要求 number，不能传字符串。
};
```

`maxTokens` 的类型在 [types.ts，第 68 行](../pi-master/packages/ai/src/types.ts#L68) 已经约定为数字，因此 TypeScript 能在检查这段代码时指出问题。改成 `maxTokens: 128` 就符合这个字段的要求。接口在这里省下的是“带着错误参数一路运行，等到底层报错后再往回查”的排查过程；它不会替我们把字符串自动转成数字。

**再说为什么分文件：每个文件只管自己这一摊，出了问题比较容易找到地方。** 把前面看过的代码重新摆一下：

- **`models.generated.ts` 管“有哪些模型”。** 模型名称、协议、地址和能力放在这里，查模型资料时有一个集中的地方。
- **`models.ts` 管“怎么找到模型”。** 把配置放进 Map，再提供 `getModel` 等查询函数。调用者知道服务商和模型 ID，就能查配置，不必自己遍历整张模型表。
- **`types.ts` 管“数据和函数应该长什么样”。** 大家都看同一份定义，少一些“你以为这个字段是字符串，我以为它是对象”的误会。
- **`stream.ts` 管“从哪里开始调用模型”。** 上层使用统一入口，把具体选哪种协议的事情交给它，不必到处写服务商判断。
- **`api-registry.ts` 管“协议名称对应哪个函数”。** 新实现通过登记接进来，包装函数再检查模型协议有没有传错。查找和检查集中处理，各家不用反复写同样的代码。
- **`register-builtins.ts` 管“把自带的实现登记好，等需要时再加载”。** 用哪种协议，就去加载对应实现，不必在这条调用路径一开始就把所有服务的 SDK 都加载进来。
- **`openai-completions.ts` 管“具体怎么和 OpenAI 通信”。** 参数怎么拼、SDK 怎么调、chunk 怎么读，都放在这里。将来 SDK 用法变了，可以先到这里改；只要交给上层的 Pi 事件还一样，上面的显示和循环代码就能继续使用。
- **`agent-loop.ts` 管“这一轮对话接下来做什么”。** 调模型、看有没有工具调用、执行工具、决定要不要继续。这套流程可以给不同模型共用。
- **`event-stream.ts` 管“事件怎么逐条交出去”。** 排队、等待、结束和最终结果这些事情实现一次，各家 Provider 就可以使用同一种事件流。

这样分工以后，**改起来有地方找，重复的代码少一些，也不容易为了改一家的参数，顺手碰坏另一家的处理。** 当然，如果公共约定本身变了，相关文件仍然要一起调整。

**最后说，为什么不直接把功能写出来就完了。**

如果目标就是“给固定模型发一句话，把回答打印出来”，直接用本节开头那段 SDK 示例就够了。没有规定一定要先设计一堆接口，也没有规定一个函数必须拆成好几个文件。

但 Pi 还要继续做很多事情。先接 OpenAI，再接 Claude；先输出文字，再支持工具调用；终端要显示回答，网页也要显示。假如一开始全写在一个大函数里，每加一家服务，就要进去加一批判断；每换一种返回格式，就要再检查显示、工具和对话流程有没有跟着写错。功能越多，这个函数就越难改。

所以它先把共同的部分定下来：“模型配置怎么传，消息怎么放，结果以什么事件交回来。”再让各家的实现按这个约定干活。**这就是这里的抽象：先把大家共同的用法说清楚，再分别写具体怎么做。**

接口和拆文件也不是同一件事。接口负责说清楚怎么调用，拆文件负责把代码放到容易管理的位置；写了接口，不代表一定得拆这么多文件。TypeScript 的类型在编译后会被擦除，我们跳去看类型定义，也不代表程序运行时真的多执行了一步。查 Map、检查协议、加载模块这些包装函数，才是在运行时做事情。

代价我们已经体会到了：第一次读源码，确实要来回跳。好处要等到后面加功能、换模型、改 SDK、多人协作时才更明显。熟悉分工后，也不用每次都从头追到底：改模型配置去看模型文件，改 OpenAI 请求去看 OpenAI 实现，改工具循环就去看 `agent-loop.ts`。

**讲到这里，就能看出一个长期维护的专业仓库，和我们平时写大作业时常见的做法，有什么区别了。**

写大作业时，我们很容易先想：“题目要求的功能做出来了吗？演示能不能跑通？”这是合理的起点。但一个仓库要长期给别人用，还要往后多想几步：

1. **今天能跑，明天改需求还好不好改？** 大作业这次只要求调用 OpenAI，把请求和显示写在一起，也可以完成任务。仓库以后还要接其他模型，就得考虑怎样换掉具体服务，同时继续使用原来的对话流程。前面那些接口、注册表和分文件，正是在为后续修改留位置。

2. **自己看得懂，别人接手时看不看得懂？** 自己刚写完的代码，参数是什么意思、哪些函数要先调用，可能都记得。但换一个没参与过的人，他要从哪里开始？明确的类型、各有分工的文件和使用文档，能让他先知道“我应该传什么、去哪里改”，不用全靠问原作者。过几个月再回头看的自己，也需要这些说明。

3. **正常情况能用，出问题时能不能收好尾？** 演示时模型很快回答了，看不出什么问题。真正使用时，可能没 Key、网络断了、用户中途取消、工具执行失败。仓库要考虑错误怎么交给上层、等待的人怎样退出、任务状态怎样恢复。前面看到的 `signal`、错误事件和 `runWithLifecycle` 的清理代码，就是在处理这些情况。

4. **新功能加上了，怎么知道旧功能没被改坏？** 自己手动问一句，回答正常，只能说明这一种情况能跑。仓库还需要检查不同输入、工具调用、失败和取消等情况。统一接口让这些检查更容易组织；像 `faux` 这样的模拟实现，还能提供可控制的回答，方便反复验证。

5. **这段代码能不能让更多地方接着用？** 大作业里可能只在一个终端显示结果，直接 `console.log` 就够了。Pi 还要供终端、网页或其他应用使用，所以先交出统一的消息和事件，由使用它的人决定怎么显示。这样，一份模型调用代码可以支持多种应用。

所以，**把功能做出来以后，还要考虑别人能不能用、后来的人能不能改、出问题能不能查、改完以后能不能确认原来的功能还正常。** 这些额外的要求，才是这里很多接口和文件分工的来由。

**把这些要求放进一张表，就更容易和我们写大作业时的习惯对上了。** 下面说的是大型团队长期维护项目时应考虑的工程要求，不是某家公司的统一规定。“大作业中的常见写法”也只是容易出现的情况，课程项目同样可以按这些要求练习。

| 比较的方面 | 大作业中容易出现的写法 | 长期维护的大型项目更看重什么 | 在本章中怎么理解 |
| --- | --- | --- | --- |
| 封装：内部的东西谁能改 | 哪个地方需要，就直接改那个对象里的字段 | 明确哪些操作对外提供，内部状态由负责它的代码管理，减少到处修改同一份数据 | `EventStream` 把队列和等待者放在内部，通过 `push`、`end`、迭代器等方法交接事件 |
| 继承与复用：共同逻辑怎么少写几遍 | 每个地方各写一份，类似代码复制过去再改 | 找到真正共用的部分，通过函数、组合或合适的继承复用，避免几份代码越改越不一样 | `AssistantMessageEventStream` 继承 `EventStream`，复用排队和等待的逻辑，只补充怎样识别终态、提取结果 |
| 多态：能不能换一种实现 | 调用处直接写死某家 SDK，换一家就跟着改调用代码 | 按同一份约定调用，让具体实现可以替换 | 注册表中的 OpenAI、Claude 或 `faux` 函数都可以接到统一入口；这里通过函数实现替换，不要求都继承同一个类 |
| 接口与类型：两边怎样配合 | 参数先传过去，缺什么字段运行时再补 | 明确输入、输出和数据结构，让调用者和实现者都知道要遵守什么，并提前检查类型错误 | `Model`、`Context`、`StreamFunction` 和 `ApiProvider` 把模型调用的要求写清楚 |
| 设计模式：反复遇到的问题怎么组织 | 遇到一个需求加一个判断，重复代码不断增加 | 根据问题选择成熟的组织方法，让新增功能有地方接入，也让团队容易理解 | 协议选择可以按“策略”的思路理解，协议格式转换可以按“适配器”的思路理解，`subscribe` 的通知可以按“观察者”的思路理解 |
| 文件与模块分工：改功能去哪里找 | 请求、显示、工具执行都挤在一个文件里 | 每个模块有明确职责，修改一种功能时，尽量少碰其他功能 | 模型查询在 `models.ts`，协议登记在 `api-registry.ts`，OpenAI 通信在 `openai-completions.ts`，轮次处理在 `agent-loop.ts` |
| 扩展方式：以后再加一种怎么办 | 新需求来了，就去公共流程里继续加分支 | 为已经明确会变化的部分提供接入位置，尽量复用公共流程 | 新协议按约定实现并登记，上层仍可以调用 `streamSimple`；模型配置和认证也要相应准备 |
| 异常与资源清理：失败以后怎么办 | 主要验证正常演示，失败时打印一句错误 | 考虑失败、取消和收尾，保证等待能结束、状态能恢复，错误能交给使用者 | `signal` 传递取消要求，错误事件交付失败信息，`runWithLifecycle` 在 `finally` 中清理运行状态 |
| 测试与回归：怎么证明改完还能用 | 手动跑几组数据，能演示就认为完成 | 有可重复执行的检查，覆盖关键流程和失败情况，修改后能检查旧功能是否被影响 | `faux` 能提供预定回答，让 Agent 流程的验证不必依赖真实模型服务 |
| 代码检查与协作：多人修改怎么合在一起 | 每个人按自己的习惯写，合并后再集中解决问题 | 约定代码风格和检查命令，提交前做自动检查，合入前由其他人审阅 | 类型检查帮助发现调用错误；仓库中的开发规则说明代码检查和协作要求 |
| 文档与交接：别人怎样开始使用 | 主要靠作者现场讲，报告交完后不再更新 | 提供入口示例、接口说明、配置方法和贡献说明，让新人能自己开始 | README 的使用示例负责带人入门，类型和源码注释继续解释具体约定 |
| 版本与兼容：改了以后谁会受影响 | 本组重新改一下调用代码就可以 | 考虑其他使用者是否受影响，对外接口变化要说明，必要时安排迁移 | `streamSimple` 这样的公共入口一旦被其他应用使用，修改参数和事件格式就要考虑调用方 |
| 配置与安全：换环境怎样部署 | 地址和 Key 直接写进代码，换电脑再手动修改 | 把环境差异作为配置管理，妥善处理凭据，避免把 Key 提交到仓库或输出到日志 | 模型配置保存服务地址，调用选项或环境变量提供 API Key；安全要求还需要结合整个应用检查 |

注意表里的继承、多态和设计模式：**大型项目确实需要认真解决复用、替换和协作这些问题，但不代表每个地方都必须写继承，也不代表设计模式用得越多越好。** 比如 Pi 有的地方通过类继承复用代码，有的地方只是把函数放进 Map，就实现了按协议替换。表中提到的模式，是帮助我们理解代码组织的角度，不表示作者必须写一个同名的模式类。

专业程度要看这些设计有没有解决实际问题：接新服务是否容易，修改会不会牵连一大片，出错时能不能找到原因，新人能不能接手。我们从这个仓库里要学的是：当代码开始被多处使用、被多人修改，或者经常要换一种实现时，怎样把共用部分和合作约定整理好。这个思路，也可以从我们自己的大作业开始练习。

模型调用和返回的主线已经接上。下一节专门展开 `subscribe`、`emit` 和 `processEvents`，把事件怎样交到监听函数手里讲透。

## 14. Event 讲透：从 subscribe 注册，到 emit、processEvents 与监听器执行

第 13 节已经看到，模型的新增文字被包成 `message_update`，再通过 `emit` 交出去。现在回到第 6 节传入的 `(event) => this.processEvents(event)`，把它与开头登记的 `subscribe` 接起来：**应用先登记监听函数；循环在运行到某个位置时创建事件对象，调用 `emit`；Agent 先根据事件更新状态，再依次执行已登记的监听函数。**

本节继续对照当前工作区的 `pi-master/packages/agent/src`。这里的 `emit` 是函数参数名，`subscribe` 和 `processEvents` 是 Agent 类的方法。按“注册发生在前，事件发生在后”的时间顺序看，关系如下：

```text
① 应用启动：登记函数
   agent.subscribe(listenerA) ──→ agent.listeners = Set { listenerA }
   agent.subscribe(listenerB) ──→ agent.listeners = Set { listenerA, listenerB }
                                此时没有调用 A、B，也没有生成事件

② 应用提交：await agent.prompt(...)
   Agent 调用 runAgentLoop(..., (event) => this.processEvents(event), ...)
                               └─────────────┬──────────────────────┘
                                   底层用形参 emit 接住这个函数

③ 循环运行到某个通知点
   await emit({ type: "message_end", message: A })
       │          此处创建事件对象 E
       ▼
   processEvents(E)
       ├─ 先更新 agent.state，例如把 A 加入 messages
       ├─ await listenerA(E, signal)
       └─ await listenerB(E, signal)
       │
       ▼
   processEvents 的 Promise 完成 → await emit(E) 完成 → 循环继续
```

**例子：开头那个终端回调，这次会在哪里执行。** 模型传回新增文字 `"H"` 后，Agent 得到的 E 是一条携带 `text_delta("H")` 的 `message_update`。调用 `emit(E)`，回到 `processEvents(E)`，最后执行事先登记的终端回调，写出 `H`。`subscribe` 是提前把这个回调存起来，真正写字发生在后面的这次调用。

### 14.1 `event`、`listener`、`subscribe`、`emit` 分别是什么

| 名称 | 在这里是什么 | 何时起作用 |
| --- | --- | --- |
| `AgentEvent` | TypeScript 联合类型，规定允许的事件名及字段 | 类型检查时约束代码；不会自动产生运行时事件 |
| `event` | 一次运行中创建的普通对象，例如 `{ type: "agent_start" }` | 作为函数实参传递，说明刚刚发生了什么 |
| `listener` | 应用提供的函数，例如更新界面或记录日志的函数 | 注册时保存引用，收到事件时才执行 |
| `listeners` | 某个 Agent 实例自己的 `Set` 集合 | 保存这个实例当前登记的监听函数 |
| `subscribe(listener)` | 把监听函数放入集合的方法 | 通常在 `prompt()` 之前调用 |
| `emit(event)` | 调用底层收到的事件接收函数 | 循环需要通知外部时调用 |
| `processEvents(event)` | Agent 的私有方法 | 先更新内部状态，再通知监听函数 |

所以“注册 event”在这里更准确地说是**注册事件监听函数**。注册时既没有创建将来的事件对象，也没有让模型开始生成。

例如下面登记的函数接收所有 `AgentEvent`，然后自己筛选感兴趣的类型：

```ts
// agent 是已创建的 Agent；本段只演示登记。
const stopListening = agent.subscribe((event) => {
  if (event.type === "tool_execution_start") {
    console.log("准备执行工具：", event.toolName, event.args);
  }
});
```

`event` 是回调参数，此时还没有值。等 Agent 将来调用这个函数时，才把当次事件对象传进去。`event.type` 的判断也在那时执行。`subscribe` 没有事件名参数，不会替应用按 `type` 分组；上面的函数同样会收到 `agent_start` 等事件，只是直接返回。

`AgentEvent` 的定义见 [types.ts，第 349 行](../pi-master/packages/agent/src/types.ts#L349)。它是可辨识联合类型：判断 `event.type === "tool_execution_start"` 后，TypeScript 才知道这一分支可以读取 `toolName` 和 `args`。这是类型收窄，实际通知仍要靠函数调用。

从 `AgentEvent` 中摘出开头示例会用到的成员，省略 turn 和工具事件：

```ts
type AgentEvent =
  | { type: "agent_start" }
  | { type: "agent_end"; messages: AgentMessage[] }
  | { type: "message_start"; message: AgentMessage }
  | {
      type: "message_update";
      message: AgentMessage;
      assistantMessageEvent: AssistantMessageEvent;
    }
  | { type: "message_end"; message: AgentMessage };
```

这里没有需要 `new` 的 `AgentEvent` 类。运行时用普通对象报告变化，联合类型约束对象有哪些字段。README 连续判断外层 `message_update` 和内层 `text_delta`，就是分别识别 Agent 消息更新与具体模型内容更新。

**例子：事件对象和接收它的函数，可以分开写。**

```ts
const event = { type: "agent_start" as const };
const listener = (event: { type: string }) => {
  console.log("收到：", event.type);
};

listener(event); // 真正执行，打印“收到：agent_start”。
```

先有一个普通对象，再把它交给函数。Agent 做的是把这个调用安排在合适的运行位置，并提前通过 `subscribe` 保存要调用的函数。

### 14.2 `subscribe()` 保存函数，并交回取消订阅的函数

源码摘录：[agent.ts，第 237 行](../pi-master/packages/agent/src/agent.ts#L237)。

```ts
subscribe(listener: (event: AgentEvent, signal: AbortSignal) => Promise<void> | void): () => void {
  this.listeners.add(listener);
  return () => this.listeners.delete(listener);
}
```

`this.listeners` 在 [agent.ts，第 176 行](../pi-master/packages/agent/src/agent.ts#L176) 初始化为 `Set`，元素是接收 `(event, signal)` 的函数。`Set.add(listener)` 保存函数引用，注册当下没有调用这个函数。

返回值 `() => this.listeners.delete(listener)` 又是一个函数。以后调用它，才从同一个 Set 删除先前登记的函数。

```ts
// agent 是已经创建的 Agent。
const seen: string[] = [];
const listener = (event: { type: string }) => { seen.push(event.type); };

const unsubscribe = agent.subscribe(listener);
// 到这里 seen 仍为空：只登记了函数。
// ... 后续运行产生事件时，Agent 才调用 listener。
unsubscribe();
// 此后不再通过这项登记接收新事件。
```

`Set` 按插入顺序迭代，同一个函数对象重复 `add` 不会出现两份。但重新创建的两个箭头函数是不同对象，即使函数体相同，也可以成为两项登记。删除登记不会倒退已执行的回调，也不会撤销它已经启动的工作。

注意返回类型中的两个箭头：`listener: (...) => Promise<void> | void` 规定传入的监听函数；整个 `subscribe(...): () => void` 则规定返回一个取消订阅函数。**`unsubscribe` 不是本次事件处理的结果，而是一个供以后调用的操作入口。** 返回的箭头函数通过闭包记住这次传入的 `listener` 和当前 Agent 的 `this`。

订阅建立后会跨多次 `prompt()` 保留，直到显式取消；源码没有在一次运行结束时清空 `listeners`，也没有在注册时重放过去的事件。因此通常先 `subscribe`，再 `prompt`。

**例子：取消订阅之后，第二次提问就不再通知这个函数。**

```ts
const unsubscribe = agent.subscribe((event) => {
  if (event.type === "agent_start") console.log("开始了一次运行");
});
await agent.prompt("Hello!"); // 本次开始时打印一次。
unsubscribe();
await agent.prompt("再打个招呼"); // 不再由这个监听器打印。
```

取消的是“以后还要不要调用这个函数”，第一次已经打印出来的文字不会被撤回。

### 14.3 `emit` 从哪里来：把第四个实参与形参对上

只读 `emit(...)` 的使用位置，很容易误以为它是某个框架内置的事件广播函数。沿着参数来源往上找，第 5—6 节看到的连接发生在 [runPromptMessages，agent.ts，第 396 行](../pi-master/packages/agent/src/agent.ts#L396)：

```ts
await runAgentLoop(
  messages,
  this.createContextSnapshot(),
  this.createLoopConfig(options),
  (event) => this.processEvents(event),
  signal,
  this.streamFn,
);
```

第四个实参是一个箭头函数。**创建这个函数时不执行 `processEvents`；它把“将来拿到事件后怎么处理”交给底层。** 箭头函数还保留当前 Agent 的 `this`，让事件回到这个实例的状态和监听集合。

对应的低层函数签名见 [agent-loop.ts，第 96 行](../pi-master/packages/agent/src/agent-loop.ts#L96)，这里只摘声明与第一条通知语句，省略中间的上下文初始化和后续流程：

```ts
export async function runAgentLoop(
  prompts: AgentMessage[],
  context: AgentContext,
  config: AgentLoopConfig,
  emit: AgentEventSink,
  signal?: AbortSignal,
  streamFn?: StreamFn,
): Promise<AgentMessage[]> {
  // ... 初始化 newMessages 和 currentContext
  await emit({ type: "agent_start" });
  // ... 其余事件和循环流程
}
```

形参类型定义在 [agent-loop.ts，第 25 行](../pi-master/packages/agent/src/agent-loop.ts#L25)：

```ts
export type AgentEventSink = (event: AgentEvent) => Promise<void> | void;
```

这说明 `emit` 保存的是函数值。就本次 Agent 调用而言，可以将关系展开为下面的等价理解；这段用于解释参数绑定，不是额外的源码：

```ts
const emit = (event: AgentEvent) => this.processEvents(event);
const event: AgentEvent = { type: "agent_start" };
await emit(event);
// 本次绑定下，执行效果相当于 await this.processEvents(event)。
```

`(event) => this.processEvents(event)` 是表达式形式的箭头函数，会**隐式返回** `processEvents` 的 Promise。这一点决定了 `await emit(...)` 能否等到监听器处理完成。若改成带大括号却不写 `return` 的 `(event) => { this.processEvents(event); }`，函数会返回 `undefined`，等待链就断了。

后续 `runLoop`、`streamAssistantResponse` 和工具执行函数继续接收同一个 `emit` 函数值。它们用不同的事件对象调用它，都会沿这条连接回到 Agent。`emit` 的具体接收动作由传入的函数实现。

这样设计的意义是：循环只负责报告生命周期与进度，调用方可以选择把报告交给 Agent 状态处理，也可以在其他入口把报告放进事件流。底层循环不用知道界面怎样绘制、日志怎样保存。

**例子：把本次的 E 代入箭头函数。** E 是 `{ type: "agent_start" }`，调用过程就相当于下面这样，代码只表示已有活动运行里的函数绑定：

```ts
const emit = (event: AgentEvent) => this.processEvents(event);
await emit({ type: "agent_start" });
// 箭头函数拿到这个对象，执行 this.processEvents(这个对象)，并返回它的 Promise。
```

如果以后改成 `(event) => stream.push(event)`，同样是调用 `emit(E)`，接收动作就变成入队。`emit` 这个名字本身不决定事件怎么处理，保存进去的函数才决定。

### 14.4 完整读 `processEvents`：前半段改状态，后半段调监听器

下面是当前 [agent.ts，第 520 行](../pi-master/packages/agent/src/agent.ts#L520) 的完整方法，调整缩进，保留全部执行语句。虽然名字是复数 `processEvents`，**每次调用只处理一个 `event` 对象**。

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

第一部分 `switch` 根据事件类型更新 `_state`，可看成一次状态归并：给定当前状态和这条事件，执行对应的状态变化。第二部分取得本次活动运行的取消信号，再遍历 `listeners`。`signal` 来自 `runWithLifecycle` 创建的 `activeRun`；没有活动运行却进入通知会抛错。传入信号让监听器能够配合取消，但 `await` 本身不会因为信号被取消就自动终止监听器。

**`break` 只跳出 `switch`，没有退出整个方法。** 所以每个 case 完成后都会继续进入下面的监听器循环；没有专门 case 的 `agent_start`、`turn_start`、`tool_execution_update` 也会到达所有监听器。源码没有 `default` 分支，并不等于这些事件被丢弃。

状态修改与通知分工如下：

| 接收到的事件 | Agent 内部修改 |
| --- | --- |
| `agent_start`、`turn_start` | switch 中没有专门修改；仍会通知订阅者 |
| `message_start`、`message_update` | `streamingMessage = event.message` |
| `message_end` | 清 `streamingMessage`，向 `messages` 追加该消息 |
| `tool_execution_start` | 复制当前待处理 ID 的 Set，加入 `toolCallId`，替换状态中的 Set |
| `tool_execution_update` | switch 中不保存阶段结果；将事件交给订阅者 |
| `tool_execution_end` | 复制 Set，删除 `toolCallId`，替换状态中的 Set |
| `turn_end` | 若助手消息带有非空 `errorMessage`，保存到状态 |
| `agent_end` | 清 `streamingMessage`；此处还不把 `isStreaming` 改成 `false` |

`pendingToolCalls` 表示“收到 start、尚未收到 end 的调用 ID”。start 发在查找工具与校验参数之前，所以集合中的项目也可能正在准备，甚至最终被阻止；是否进入 `execute`，还取决于准备结果。

`message_end` 中先 `push(event.message)` 再通知。因此监听器一收到它，就能在 `agent.state.messages` 里找到该完整消息。监听器应直接读取结果或更新界面，无须再把同一条消息追加到 Agent 历史，否则会造成重复。

`streamingMessage` 的类型是 `AgentMessage | undefined`，用户消息和工具结果的 `message_start` 也会设置它；连续的 `message_update` 才专属于助手流式输出。`tool_execution_update` 的阶段结果则不存进该字段，应用通过事件里的 `partialResult` 接收。

**例子：用户消息结束时，状态已经替监听器改好了。** 假设开始时历史为空，用户消息 U 的内容是 `Hello!`：

```text
收到 message_start(U)： streamingMessage = U，messages = []
收到 message_end(U)：   streamingMessage = undefined，messages = [U]
然后通知监听器：        此时再读 agent.state.messages，已经能找到 U
```

工具也是一样：收到 `tool_execution_start`，先把 `call_1` 加进 `pendingToolCalls`；收到 `tool_execution_end`，先删掉 `call_1`，再通知界面更新。所以监听器读到的是本条事件已经处理过的状态。

### 14.5 为什么写 `await emit(...)`：把执行顺序一直等回循环

设 A、B 是按顺序登记的两个监听器。一条主线事件的调用和返回路径是：

```text
发出方：await emit(E)
          ↓ 调用
        (event) => this.processEvents(event)
          ↓ 调用，并返回同一个处理 Promise
        processEvents(E)
          ① 按 E.type 更新状态
          ② await listenerA(E, signal)
          ③ await listenerB(E, signal)
          ④ 方法完成
          ↑ Promise 完成
发出方：await emit(E) 完成，继续下一条语句
```

这里 `for...of` 从 Set 里取出的 `listener`，就是当初 `subscribe(listener)` 保存的同一个函数引用；`listener(event, signal)` 才是它真正执行的地方。对于这一条事件，A 返回的 Promise 没有完成，B 就不会开始；B 没有完成，`processEvents` 的 Promise 就不会完成。

例如 `streamAssistantResponse` 在助手终态处依次执行 `await emit({ type: "message_end", message: finalMessage })` 和 `return finalMessage`。因此顺序是：**助手消息进入 Agent 历史 → 这一条事件的监听器完成 → 返回完整助手消息 → `runLoop` 才判断和执行工具。** 监听器的耗时因此会影响后续推进，这就是这条路径上的等待与背压。

`agent_end` 也要走这条等待链。它表示循环发出了结束事件；只有它的监听器全部完成，控制权才经入口回到 `runWithLifecycle` 的 `finally`，由 [finishRun，agent.ts，第 505 行](../pi-master/packages/agent/src/agent.ts#L505) 把 `isStreaming` 设为 `false` 并解除空闲等待。因此在 `agent_end` 监听器内部，`agent.state.isStreaming` 仍然为 `true`。

这与第 5 节的生命周期等待相接：循环主线等待事件处理，生命周期外壳等待整个循环；两层等待都完成后，外壳才能把本次运行标为空闲。

**例子：先登记 A，再登记 B，这一条事件就先等 A。** `saveMessage` 是应用提供的异步保存函数：

```ts
agent.subscribe(async (event) => {
  if (event.type !== "message_end") return;
  console.log("A：开始保存");
  await saveMessage(event.message);
  console.log("A：保存完成");
});
agent.subscribe((event) => {
  if (event.type === "message_end") console.log("B：收到消息");
});
```

假设没有其他事件并发进来，处理这一条 `message_end` 时，打印顺序是“A：开始保存 → A：保存完成 → B：收到消息”。随后 `await emit(...)` 才结束，循环才往下走。

### 14.6 两个例子：一次文本回答，以及一次工具调用

**例子 A：两个订阅者观察同一次回答。** 假设 `agent` 已配置好模型，初始历史为空；本次没有工具与排队消息，模型最终回答“你好”。`persistMessage` 是应用提供的异步保存函数。下面演示真实 API 的使用方式，事件时间线用于解释给定条件，不是实际请求日志。

```ts
const unsubscribeView = agent.subscribe((event) => {
  if (event.type === "message_update") {
    const modelEvent = event.assistantMessageEvent;
    if (modelEvent.type === "text_delta") {
      console.log("新增文字：", modelEvent.delta);
    }
  }

  if (event.type === "message_end") {
    console.log("消息完成：", event.message.role);
    console.log("历史已包含它：", agent.state.messages.includes(event.message));
  }
});

const unsubscribeSave = agent.subscribe(async (event, signal) => {
  if (event.type === "message_end" && event.message.role === "assistant") {
    await persistMessage(event.message, signal);
  }
});

await agent.prompt("打个招呼");
// 正常完成到这里：助手 message_end 的保存任务已经完成。
unsubscribeView();
unsubscribeSave();
```

注册时只把两个函数放入 Set，以上所有 `console.log` 都不会因注册而执行。随后 `prompt` 触发的关键事件如下；表中省略内容块的 start/end，只列与理解过程有关的项：

| 循环交出的事件 | `processEvents` 先做什么 | 随后监听器做什么 |
| --- | --- | --- |
| `agent_start`、`turn_start` | 无专门 switch 修改；此前运行入口已设置 `isStreaming=true` | 两个函数都被调用，但条件不匹配，直接返回 |
| 用户 `message_start(U)` | `streamingMessage=U` | 两个函数均直接返回 |
| 用户 `message_end(U)` | 清当前消息，历史变成 `[U]` | View 打印 `user`、`true`；Save 直接返回 |
| 助手 `message_start(A部分)` | `streamingMessage=A部分` | 两个函数均直接返回 |
| 助手 `message_update`，内层 `text_delta("你")` | 更新当前累计助手消息 | View 打印“你”；Save 直接返回 |
| 助手 `message_update`，内层 `text_delta("好")` | 更新当前累计助手消息 | View 打印“好”；Save 直接返回 |
| 助手 `message_end(A完整)` | 清当前消息，历史变成 `[U, A完整]` | View 打印 `assistant`、`true`；随后 Save 开始保存，并等待保存完成 |
| `turn_end`、`agent_end` | 按对应分支处理，`agent_end` 清当前消息 | 两个函数均直接返回；之后才进入 `finishRun` |

两次 `text_delta` 表示假设的分块方式，实际分块数量由模型流决定。外层 `message_update` 描述“Agent 的助手消息更新了”，内层 `assistantMessageEvent` 描述“具体更新了什么”。同一条助手消息可以经历许多 update，但在 `state.messages` 中由 `message_end` 追加一次。

**例子 B：`emit` 报告工具生命周期，执行语句推进工具工作。** 假设本轮助手给出调用 `sum(2, 3)`，ID 为 `c1`，工具返回 5，而且没有要求提前终止：

```text
助手 message_end(A1)       state.messages = [U, A1]
        ↓ runLoop 从 A1.content 提取 ToolCall
tool_execution_start(c1)    pendingToolCalls = { c1 }，然后通知监听器
        ↓ 查找工具、校验参数、按需调用 beforeToolCall
tool.execute(...)          真正执行 sum，算出 5
        ├─ 若调用 onUpdate → tool_execution_update → 监听器收到阶段结果
        ↓ 按需调用 afterToolCall
tool_execution_end(c1)      pendingToolCalls = {}，然后通知监听器
message_start(R1)           streamingMessage = R1
message_end(R1)             state.messages = [U, A1, R1]
turn_end                   本轮完成
        ↓ 循环把工具结果交给下一次模型调用
下一 turn 的助手消息 A2    例如“2 + 3 = 5”
```

`await emit({ type: "tool_execution_start", ... })` 的直接作用是交出 start 事件、更新待处理集合并通知订阅者；随后独立的 `tool.execute(...)` 语句才执行工具。即使没有任何订阅者，事件仍会先更新 Agent 状态，循环仍会照常执行工具。

`tool_execution_end` 让应用结束某个工具的进度展示，`message_end(R1)` 则让完整工具结果进入对话历史。它们描述两个不同动作，所以不能只靠前者推断工具结果已经进入 `state.messages`。下一轮模型能使用结果，还依赖循环把 R1 加入 `currentContext.messages`，见第 7—8 节对循环上下文和续跑的说明。

### 14.7 返回 Promise 与另行排队，是两种承诺

下面两种写法的差别在于是否返回保存任务的 Promise。`save` 是调用方提供的异步保存函数：

```ts
agent.subscribe(async (event) => {
  await save(event);
});
```

这段监听器返回的 Promise 要等 `save` 完成，所以 Agent 也会等待。

```ts
agent.subscribe((event) => {
  void save(event);
});
```

第二段启动 `save` 后返回 `void`。`await listener(...)` 只等到了 `undefined`，无法追踪未返回的保存任务。`void` 不取消异步任务，只丢弃这个表达式的结果。

这个差别同样适用于事件队列、渲染与网络发送：能否在 `prompt()` 完成时确认它们已完成，取决于订阅者是否把相应 Promise 纳入返回链。

开头的 `process.stdout.write` 发起写入，也不等于此时终端已经完成所有显示。Agent 能等待的是监听函数实际返回的 Promise。

**例子：只差有没有把保存任务返回来，等待结果就不同。** 两种写法任选一种，`saveMessage` 返回 Promise：

```ts
// 写法一：返回保存任务，Agent 会等它。
agent.subscribe((event) => {
  if (event.type === "message_end") return saveMessage(event.message);
});

// 写法二：只启动任务，函数马上返回，Agent 不会自动等保存完成。
agent.subscribe((event) => {
  if (event.type === "message_end") void saveMessage(event.message);
});
```

第一种能把“保存完成”算进本次等待，第二种只能说明“保存已经启动”。实际选哪种，要看应用是否要求保存完再继续。

### 14.8 深入：每条事件内部的等待，不等于全局事件串行

主线经常写 `await emit(E1); await emit(E2)`，所以在这条调用路径中 E1 的处理完成后才开始 E2。但工具进度回调会立即调用 emit，把其 Promise 收集起来，稍后一起等；并行工具也可分别产生事件。

于是不同的 `processEvents` 调用可能重叠：某个事件的监听器 A 正在 await 时，另一个工具可以发出下一条事件。源码没有一个包住所有 `processEvents` 的全局互斥队列。

准确的保证是：**单次 `processEvents(event)` 内，监听函数按登记顺序被调用并等待；事件之间是否等待前一个全部处理完，要看发出事件的代码有没有等待。** 工具进度和并行批次的具体实现见 [第 07 章](07_Pi工具系统源码解析：定义、接入、执行与自定义工具.md) 的第 8—9、11 节。

这也意味着监听器如果先 `await`，再读取共享 `agent.state`，期间状态可能已经被另一事件更新。需要关联某一次调用时，应读取这条事件自己的 `toolCallId` 等字段。

另外，`processEvents` 对每个 listener 的调用没有单独的 `try/catch`。如果前一个监听器抛错或返回被拒绝的 Promise，这一次遍历就会中断，后面的监听器不会正常接着执行；异常会沿 `await emit` 传回调用方，Agent 外壳会进入第 5 节所讲的 `runWithLifecycle` 异常处理。不能把本实现理解成“某个监听器失败也必然通知完其他所有监听器”。

**例子：两个工具都在发进度，事件处理可以交错。** 假设工具 A、B 并行运行，同一个监听器收到更新后要异步保存：

```text
A 发出 update(A) → 进入监听器，正在 await 保存 A 的进度
B 发出 update(B) → 也进入监听器，开始保存 B 的进度
A 的保存完成    → 继续处理 update(A) 后面的监听器
B 的保存完成    → 继续处理 update(B) 后面的监听器
```

这条时间线只是其中一种可能顺序，B 也可能先保存完。`await listener(...)` 管的是这一次事件内部的顺序，没有把所有工具的事件锁成一条队列。异步恢复后如果要知道自己处理的是哪次工具调用，要拿当前事件的 `toolCallId`。

### 14.9 第二种实现：把事件放进一个可读取的流

为什么要把 `emit` 作为参数传进来，而不在循环里写死 `this.processEvents`？因为有的调用方不想用 `Agent` 类，只想自己读取循环事件。

同文件中的 `agentLoop` 就是另一个实际接法。看 [agent-loop.ts，第 40 行](../pi-master/packages/agent/src/agent-loop.ts#L40)，它传给 `runAgentLoop` 的第四个参数是：

```ts
async (event) => {
  stream.push(event);
}
```

这样，事件就进入 `EventStream`，调用者可以用 `for await` 逐条读取。

两种接法符合相同的 `AgentEventSink` 约定，但实现不同：一种更新 Agent 状态并通知订阅者，另一种把事件放进流。**底下的循环只管报告发生了什么，不用知道上面是终端、网页，还是另一个应用。**

别把名字混了：我们当前从 `Agent.prompt` 进入的是 `runAgentLoop`，不是先经过那个返回事件流的 `agentLoop` 包装函数。

**例子：不用 Agent 类，自己逐条读循环通知。** 假设 `context`、`config`、`signal` 已按前面的内容准备好，U 是本次完整用户消息：

```ts
import { agentLoop } from "@mariozechner/pi-agent-core";

const events = agentLoop([U], context, config, signal);
for await (const event of events) {
  console.log(event.type);
}
const newMessages = await events.result();
```

正常无工具的一问中，会读到 `agent_start`、`turn_start`、用户和助手的消息事件，最后是 `agent_end`。`newMessages` 则是本次新增的 `[U, A]`。这种入口由调用方读取流，没有经过 `Agent.subscribe`。

### 14.10 把三种事件交付方式放在一起对照

| 对象或机制 | 生产者 | 消费者 | 交付内容与等待含义 |
| --- | --- | --- | --- |
| `AssistantMessageEventStream` | pi-ai 或自定义 `streamFn` | `streamAssistantResponse` | 模型 start/内容/终态事件；`result()` 得一条助手消息 |
| `AgentEventSink` 回调 | agent-loop 调用 `emit` | Agent 的 `processEvents`，再到订阅者 | Agent 生命周期事件；等待回调返回的 Promise |
| `agentLoop()` 返回的 `EventStream<AgentEvent, AgentMessage[]>` | 包装器中的 `stream.push` 回调 | 直接使用此 API 的 `for await` 调用方 | Agent 事件；`result()` 得本次新增消息数组 |

`Agent.prompt()` 使用第二种回调机制；第三种事件流机制则是另一种公开入口。它们复用同一个底层循环，外部消费方式不同。

14.5—14.8 节解释的等待关系适用于 `Agent.prompt()` 的回调路径。改用 `agentLoop()` 时，`emit` 接到的是 `stream.push(event)`；生产者等待入队回调完成，不会因此等待外部 `for await` 循环中的异步业务完成。14.9 节给出的包装器就是这个入口。

**到这里先记住：**

- `subscribe` 先保存函数；`emit` 发生时才沿回调进入 `processEvents`，最终调用它。
- Agent 先更新状态，再通知订阅者；`message_end` 是完成消息进入 Agent 历史的位置。
- 被等待的是监听器返回的 Promise，未返回的后台工作另有完成时机。
- 单条事件内有监听顺序，工具并发阶段不保证全局事件处理互斥。

**读完这一节，应能从两端接上同一次调用：** `subscribe` 负责事先保存函数；`emit(E)` 把当下创建的事件交给回调；`processEvents(E)` 先更新状态再调用那些函数；`await` 把监听器承诺完成的工作一直等回发出事件的位置。事件解释过程发生了什么，消息保留对话说了什么，两者通过事件携带的 `message` 相连。

**例子：同样一句“Hi!”，三个返回值分别是什么。**

| 使用方式 | 过程里读到什么 | 完成后拿到什么 |
| --- | --- | --- |
| Pi 模型事件流 | 新增文字 `H`、`i!` 等模型事件 | `response.result()` 得到一条助手消息 A，正文是 `Hi!` |
| `Agent.prompt("Hello!")` | 订阅者收到用户、助手、轮次等 Agent 事件 | `await prompt(...)` 得到 `undefined`，完成消息在 Agent 状态中 |
| `agentLoop([U], ...)` | `for await` 读到 Agent 事件 | `events.result()` 得到本次新增消息 `[U, A]` |

所以看到 `result()`，先认清拿的是哪一种流：模型流等一条助手消息，Agent 循环流等一组本次新增消息。

### 14.11 最后落到终端输出

`message_update` 沿 `emit` 回到 `Agent.processEvents`，再进入 `listeners`。第 14.4 节已经展开了先更新状态、再通知的实现，第 14.6 节给出了完整例子。现在接回开头的终端回调：

```ts
if (event.type === "message_update" && event.assistantMessageEvent.type === "text_delta") {
  process.stdout.write(event.assistantMessageEvent.delta);
}
```

把这条回程连起来，就是：

```text
OpenAI SDK 交回新增内容 chunk
    ↓
streamOpenAICompletions 累计 output，push(text_delta)
    ↓
Pi 模型事件流，必要时经过延迟加载层转发
    ↓
streamAssistantResponse 读事件，emit(message_update)
    ↓
Agent.processEvents 更新状态、调用订阅者
    ↓
README 的回调取出 delta，写到终端
```

现在也能回答一个问题：模型换成 Claude，终端回调为什么还可以用？因为底下虽然换了 Provider，但交给上层的仍然是同一套 Pi 事件约定。具体服务商的差异在底下处理，上面的显示代码可以继续接收 `message_update` 和 `text_delta`。

**例子：终端到底会写几次。** 假设先收到 `text_delta("H")`，后收到 `text_delta("i!")`：

```text
第一次回调：process.stdout.write("H")
第二次回调：process.stdout.write("i!")
终端合起来：Hi!
```

收到 `agent_start` 时，外层 `type` 对不上，不写字；收到携带 `thinking_delta` 的 `message_update` 时，内层 `type` 对不上，也不写字。这两个判断把“新增正文”挑了出来。

### 14.12 文字显示出来以后，prompt 什么时候才算完成

生成一段文字和整次任务结束，是不同的时刻。

`streamAssistantResponse` 返回完整消息后，`runLoop` 还要判断有没有工具要执行、有没有补充消息。没有后续工作，才发 `agent_end`。

Agent 会等待这条结束事件的订阅者处理完。随后 `runWithLifecycle` 进入 `finally`，调用 `finishRun()` 清理活动任务，外层等待的 `prompt` 才完成正常收尾。

因此，收到 `agent_end` 时，订阅者自身的异步工作可能还在进行；`await agent.prompt(...)` 和 `waitForIdle()` 的等待范围还包括需要等待的收尾处理。当前实现也会把许多失败转换成消息和错误状态，所以 Promise 完成不一定表示模型成功回答，还要看消息的 `stopReason` 或 Agent 的错误状态。

**例子：回答已经显示出来，但最后还要保存。** `saveConversation` 是应用提供的异步保存函数：

```ts
agent.subscribe(async (event) => {
  if (event.type === "agent_end") {
    await saveConversation(agent.state.messages);
  }
});

await agent.prompt("Hello!");
console.log("保存也完成了，可以处理下一步");
```

假设本次没有异常，屏幕上可能已经显示 `Hi!`，保存却还没结束。这时 `prompt` 继续等；保存结束，执行 `finishRun()`，才打印最后一句。

## 15. 再顺着源码走一遍：每次跳转要找什么

第二遍阅读时，可以用这张表定位。先找函数，再看“它收到什么、交给谁、什么时候返回”，比一开始逐行研究所有分支更容易保持主线。

| 顺序 | 文件与起始行 | 这一步要看清什么 |
| --- | --- | --- |
| 1 | [README.md，第 14 行](../pi-master/packages/agent/README.md#L14) 与本章第 1 节教学示例 | 原文是 Claude；教学示例从开头固定 OpenAI Chat Completions |
| 2 | [models.ts，第 1—13 行](../pi-master/packages/ai/src/models.ts#L1) | 模块初始化时遍历 `MODELS`，先按模型 ID 存入内层 Map，再按服务商名称存入外层 Map |
| 3 | [models.ts，第 20—25 行](../pi-master/packages/ai/src/models.ts#L20)、[models.generated.ts，第 5839—5855 行](../pi-master/packages/ai/src/models.generated.ts#L5839) | `getModel` 用两个参数查回配置；原始 `api` 是 `openai-responses`，教学示例复制后显式覆盖 |
| 4 | [agent.ts，第 208 行](../pi-master/packages/agent/src/agent.ts#L208)、[第 86 行](../pi-master/packages/agent/src/agent.ts#L86) | `options.initialState.model` 保存为 `this._state.model` |
| 5 | [agent.ts，第 332 行](../pi-master/packages/agent/src/agent.ts#L332)、[第 376 行](../pi-master/packages/agent/src/agent.ts#L376) | `prompt` 接收输入，把字符串变成用户消息 |
| 6 | [agent.ts，第 396 行](../pi-master/packages/agent/src/agent.ts#L396)、[第 463 行](../pi-master/packages/agent/src/agent.ts#L463) | 消息进入生命周期包装，再交给循环 |
| 7 | [agent.ts，第 404 行](../pi-master/packages/agent/src/agent.ts#L404)、[第 437 行](../pi-master/packages/agent/src/agent.ts#L437) | 调用 `createLoopConfig`，把模型对象放进 `config.model` |
| 8 | [agent-loop.ts，第 96 行](../pi-master/packages/agent/src/agent-loop.ts#L96)、[第 160 行](../pi-master/packages/agent/src/agent-loop.ts#L160)、[第 237 行](../pi-master/packages/agent/src/agent-loop.ts#L237) | config 依次传入 `runAgentLoop`、`runLoop`、`streamAssistantResponse` |
| 9 | [agent-loop.ts，第 324—340 行](../pi-master/packages/agent/src/agent-loop.ts#L324) | 组装 `llmContext`，把 `config.model`、上下文、选项作为三个实参传下去 |
| 10 | [stream.ts，第 43—49 行](../pi-master/packages/ai/src/stream.ts#L43) | 形参 `model` 接住 `config.model`，读取 `model.api` |
| 10a | [types.ts，第 5—44 行](../pi-master/packages/ai/src/types.ts#L5) | 第 10.1 节：`Api` 表示协议，`Provider` 表示服务商；类型列表本身不会登记实现 |
| 11 | [stream.ts，第 17 行](../pi-master/packages/ai/src/stream.ts#L17)、[api-registry.ts，第 80 行](../pi-master/packages/ai/src/api-registry.ts#L80) | 按协议字符串查 Map，返回带函数属性的实现对象 |
| 12 | [register-builtins.ts，第 373—377 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L373)、[api-registry.ts，第 66—78 行](../pi-master/packages/ai/src/api-registry.ts#L66) | 找到谁登记了 `streamSimple`，确认登记时包了一层检查 |
| 13 | [api-registry.ts，第 54—64 行](../pi-master/packages/ai/src/api-registry.ts#L54) | `provider.streamSimple` 先进入这里返回的函数，再调用登记的原入口 |
| 14 | [register-builtins.ts，第 360 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L360)、[第 189—210 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L189) | 原入口是延迟函数，记住 `loadModule`，模型调用时才执行它 |
| 15 | [register-builtins.ts，第 303—314 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L303)、[第 199 行](../pi-master/packages/ai/src/providers/register-builtins.ts#L199) | 导入具体模块，用其导出组装 `module.streamSimple`，透传三个参数 |
| 16 | [openai-completions.ts，第 368—387 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L368)、[simple-options.ts，第 3 行](../pi-master/packages/ai/src/providers/simple-options.ts#L3) | 整理统一选项，构造新 options，交给完整实现 |
| 17 | [openai-completions.ts，第 110 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L110)、[第 389 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L389)、[第 435 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L435) | 创建流、SDK 客户端和请求参数，分别使用模型各字段 |
| 18 | [openai-completions.ts，第 147—149 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L147) | SDK `.create(params, { signal })` 发起请求 |
| 18a | [api-registry.ts，第 17 行](../pi-master/packages/ai/src/api-registry.ts#L17)、[types.ts，第 136 行](../pi-master/packages/ai/src/types.ts#L136) | 第 13.8 节：回看 `ApiStreamSimpleFunction` 与 `StreamFunction`，区分函数约定与包装、参数整理这些实际操作 |
| 19 | [openai-completions.ts，第 187 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L187)、[第 228 行](../pi-master/packages/ai/src/providers/openai-completions.ts#L228) | 读取 chunk，累计文字，产生 `text_delta` |
| 20 | [agent-loop.ts，第 350 行](../pi-master/packages/agent/src/agent-loop.ts#L350)、[agent.ts，第 520 行](../pi-master/packages/agent/src/agent.ts#L520) | 模型事件变成 Agent 事件，再由 `processEvents` 通知订阅者 |

先把模型配置的来源接到入口前面，再把请求与回程合起来：

```text
MODELS.openai["gpt-4o-mini"]             models.generated.ts:5839，api 原值见 5842
  → getModel("openai", "gpt-4o-mini")   models.ts:20、24、25
  → 教学示例复制配置，显式设置 api: "openai-completions"
  → new Agent({ initialState: { model } })
  → this._state.model                  agent.ts:208、85

agent.prompt("Hello!")                 agent.ts:332
  → 统一消息格式
  → runPromptMessages
  → runWithLifecycle
  → createLoopConfig → config.model = this._state.model（agent.ts:437）
  → runAgentLoop
  → runLoop
  → streamAssistantResponse
  → streamFunction(config.model, llmContext, options)（agent-loop.ts:336）
  → 默认 streamSimple 读取 model.api（stream.ts:48）
  → resolveApiProvider → getApiProvider → 查 API 注册表（api-registry.ts:81）
  → provider.streamSimple → 协议检查包装（api-registry.ts:58、62）
  → 延迟入口调用 loadModule（register-builtins.ts:194、197）
  → import 具体模块，用导出组装 streamSimple 属性（register-builtins.ts:306、310）
  → module.streamSimple(model, context, options)（register-builtins.ts:199）
  → streamSimpleOpenAICompletions（openai-completions.ts:368）
  → streamOpenAICompletions
  → OpenAI SDK 发请求、逐段返回内容
  → text_delta
  → message_update
  → processEvents
  → subscribe 回调
  → process.stdout.write(delta)
```

读到这里，可以自己沿源码回答：`getModel` 返回对象里的 `api` 最早写在哪？本章在哪里覆盖了它？它如何从 `initialState.model` 变成 `streamSimple` 的形参？`provider.streamSimple` 属性又先后对应哪几层函数？每次跳转都能对上实参与形参，再继续追请求和返回。

**例子：第二遍只带着 `Hello!` 走，逐个核对值。** 按表里的顺序，在 IDE 中看这几个位置就够了：

```text
prompt 的 input：                         "Hello!"
normalizePromptInput 返回：               [U]
streamAssistantResponse 的 llmMessages：  [U]
streamSimple 读取的 model.api：           "openai-completions"
SDK create 的 params.messages：          包含用户的 Hello!
假设返回的两次正文增量：                  "H"、"i!"
订阅者最终写到终端：                      Hi!
```

在哪一步不清楚，就回到那一节，把示例里的值代进当前函数看。先看清这一问怎么走完，再换成有历史、有工具的情况。
