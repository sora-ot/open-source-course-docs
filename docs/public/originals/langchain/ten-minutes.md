# LangChain 核心实现：从模型适配到 Runnable、封装、继承、多态与组合

> **授课定位：** 参考《LLaMA-Factory 核心实现》的讲法，不从“怎么调用 LangChain”停留在表面，而是追踪：**一个问题如何经过 Prompt、模型适配器和 Parser，最终得到字符串？** 课堂主线约 **10 分钟**；完整代码与离线演示可用于课后复习或继续展开。
>
> **本节不讲：** Agent、RAG、Memory、向量数据库等扩展功能。所有手写类均是**教学版极简实现，并非 LangChain 官方源码**。真实框架与教学版的关键差异见第 9 节。

## 一、先告诉学生：今天究竟要学会什么（第 0—1 分钟）

LLaMA-Factory 最重要的工程思想之一，是把不同的数据、模型及微调方式适配到一条训练流水线：

```text
不同 Dataset / 模型 / Full、Freeze、LoRA
                  ↓
       Adapter / Template / Processor
                  ↓
              Trainer
                  ↓
              统一训练
```

LangChain 对应的思想是：

```text
不同 Prompt / OpenAI、Anthropic 等模型 / 输出处理器
                        ↓
                 统一 Runnable 接口
                        ↓
                  invoke(input)
                        ↓
               用 | 组成执行链
```

**区别：LLaMA-Factory 主要统一“怎样训练”；LangChain 主要统一“怎样调用、组合大模型应用中的组件”。**

今天只需记住三个名字：

1. **Model Adapter：** 隐藏供应商的请求、响应格式差异。
2. **Runnable：** 让不同组件都提供 `invoke(input)` 等统一入口。
3. **RunnableSequence：** 将多个 Runnable 按顺序组合起来。

尤其要讲明白：**模型 Adapter 很重要，但 LangChain 不止做模型适配；更加通用的核心是 Runnable + 组合。**

---

## 二、先看最简单的官方 LangChain 用法（第 1—2 分钟）

先不管内部实现，完成一个任务：“1+1 等于多少？”

```bash
pip install -U langchain langchain-openai
# 使用 OpenAI 时，需要在环境变量中设置 OPENAI_API_KEY
```

```python
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_template(
    "请用一句话回答：{question}"
)
model = init_chat_model("openai:gpt-4o-mini")
parser = StrOutputParser()

# 核心：把三个组件组合起来
chain = prompt | model | parser

# 核心：对整条链统一调用 invoke()
result = chain.invoke({"question": "1+1等于多少？"})
print(result)   # 可能输出：2
```

请学生圈出两行：

```python
chain = prompt | model | parser
result = chain.invoke({"question": "1+1等于多少？"})
```

第一行是**定义执行链**，不是立刻调用模型；第二行才是**真正执行**。

整个执行过程：

```text
① dict: {"question": "1+1等于多少？"}
      ↓ prompt.invoke(...)
② ChatPromptValue：其中包含 HumanMessage("请用一句话回答：1+1等于多少？")
      ↓ model.invoke(...)
③ AIMessage(content="2")
      ↓ parser.invoke(...)
④ str: "2"
```

**关键观察：** Prompt、Model、Parser 做的事完全不同，但在 LangChain 中都可以通过 `invoke()` 调用。

---

## 三、为什么需要 Model Adapter？先不使用 LangChain（第 2—3 分钟）

### 3.1 OpenAI 的原生调用

下面示例使用 OpenAI SDK 的 Chat Completions API：

```python
from openai import OpenAI

client = OpenAI()  # 默认读取 OPENAI_API_KEY
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "回答尽量简短。"},
        {"role": "user", "content": "1+1等于多少？"},
    ],
)

answer = response.choices[0].message.content
```

返回结构（示意）：

```text
response
  └── choices[0]
         └── message
                └── content = "2"
```

### 3.2 Anthropic 的原生调用

```python
from anthropic import Anthropic

client = Anthropic()  # 默认读取 ANTHROPIC_API_KEY
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=128,
    system="回答尽量简短。",
    messages=[
        {"role": "user", "content": "1+1等于多少？"},
    ],
)

answer = "".join(
    block.text
    for block in response.content
    if block.type == "text"
)
```

返回结构（示意）：

```text
response
  └── content
        └── [TextBlock(type="text", text="2")]
```

**相同问题，供应商之间至少有两种差别：**

| 对比项 | OpenAI（此示例） | Anthropic（此示例） |
|---|---|---|
| System 提示词 | 在 `messages` 列表里 | 独立的 `system` 参数 |
| SDK 调用 | `chat.completions.create(...)` | `messages.create(...)` |
| 读出回答 | `choices[0].message.content` | 遍历 `content` 文本块 |

如果上层业务写满这些供应商差异，**一旦切换大模型，就需要修改业务代码**。

所以我们希望在中间增加一层：

```text
              统一消息对象
 [SystemMessage, HumanMessage, AIMessage]
                    │
              model.invoke()
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
     OpenAIAdapter       AnthropicAdapter
         │                     │
      OpenAI API           Anthropic API
         │                     │
         └──────────┬──────────┘
                    ▼
            AIMessage("2")
```

这就是**封装与适配**的直观目标：对外统一接口，对内处理差异。

---

## 四、统一的消息类型与 Runnable 抽象（第 3—4 分钟）

为了从头理解框架，我们先手写一个最小版本。

### 4.1 统一消息类型

```python
from dataclasses import dataclass

@dataclass
class SystemMessage:
    content: str

@dataclass
class HumanMessage:
    content: str

@dataclass
class AIMessage:
    content: str
```

现在模型内部只认这些统一的对象：

```python
messages = [
    SystemMessage("回答尽量简短。"),
    HumanMessage("1+1等于多少？"),
]
```

`AIMessage` 也用于统一输出。**这些是教学版数据类**；真正 LangChain 的消息类还保留工具调用、元数据、复杂内容块等信息。

### 4.2 统一调用接口：Runnable

```python
from abc import ABC, abstractmethod

class Runnable(ABC):
    @abstractmethod
    def invoke(self, value):
        pass

    def __or__(self, other):
        return RunnableSequence([self, other])

class BaseChatModel(Runnable):
    pass
```

这里有两点：

- `invoke(value)` 是**共同接口**，每个具体 Runnable 要能被如此调用。
- `__or__()` 重载 Python 的 `|`，目的是**构造一个组合对象**。

继承关系（简化）：

```text
                   Runnable
                      │
                 BaseChatModel
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
     OpenAIAdapter          AnthropicAdapter
       invoke()                invoke()
```

---

## 五、把两个 Adapter 的 `invoke()` 完整展开（第 4—6 分钟，重点）

### 5.1 OpenAIAdapter：输入转换 → API → 输出转换

假设已经定义好上一节的 `BaseChatModel`、`SystemMessage`、`HumanMessage`、`AIMessage`。

```python
class OpenAIAdapter(BaseChatModel):
    def __init__(self, model="gpt-4o-mini", client=None):
        if client is None:
            from openai import OpenAI
            client = OpenAI()
        self.client = client
        self.model = model

    def invoke(self, messages):
        # 第一步：统一消息对象 -> OpenAI SDK 需要的字典
        api_messages = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                role = "system"
            elif isinstance(msg, HumanMessage):
                role = "user"
            elif isinstance(msg, AIMessage):
                role = "assistant"
            else:
                raise TypeError(f"不支持的消息类型: {type(msg)}")

            api_messages.append({
                "role": role,
                "content": msg.content,
            })

        # 第二步：发出真正的供应商请求
        response = self.client.chat.completions.create(
            model=self.model,
            messages=api_messages,
        )

        # 第三步：从 OpenAI 的返回结构中提取文本
        answer = response.choices[0].message.content or ""

        # 第四步：供应商格式 -> 框架统一的 AIMessage
        return AIMessage(content=answer)
```

假设传入：

```python
[
    SystemMessage("回答尽量简短。"),
    HumanMessage("1+1等于多少？"),
]
```

执行顺序：

```text
统一的 SystemMessage / HumanMessage
           ↓
转换成 {"role": "system" / "user", "content": "..."}
           ↓
client.chat.completions.create(...)
           ↓
response.choices[0].message.content
           ↓
AIMessage(content="2")
```

### 5.2 AnthropicAdapter：同样的接口，内部实现完全不同

```python
class AnthropicAdapter(BaseChatModel):
    def __init__(self, model="claude-haiku-4-5-20251001", client=None):
        if client is None:
            from anthropic import Anthropic
            client = Anthropic()
        self.client = client
        self.model = model

    def invoke(self, messages):
        # 第一步：Anthropic 把 system 放在单独参数中
        system_parts = []
        api_messages = []

        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_parts.append(msg.content)
            elif isinstance(msg, HumanMessage):
                api_messages.append({
                    "role": "user",
                    "content": msg.content,
                })
            elif isinstance(msg, AIMessage):
                api_messages.append({
                    "role": "assistant",
                    "content": msg.content,
                })
            else:
                raise TypeError(f"不支持的消息类型: {type(msg)}")

        # 第二步：发出真正的供应商请求
        kwargs = {
            "model": self.model,
            "max_tokens": 128,
            "messages": api_messages,
        }
        if system_parts:
            kwargs["system"] = "\n".join(system_parts)

        response = self.client.messages.create(**kwargs)

        # 第三步：从 content blocks 提取文本
        answer = "".join(
            block.text
            for block in response.content
            if block.type == "text"
        )

        # 第四步：输出统一消息对象
        return AIMessage(content=answer)
```

同样的输入，Anthropic 适配器生成的请求参数却是：

```python
{
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 128,
    "messages": [{"role": "user", "content": "1+1等于多少？"}],
    "system": "回答尽量简短。",
}
```

最后依然返回：

```python
AIMessage(content="2")
```

**请学生注意：两个 `invoke()` 都有同样的四步，但每一步的实现不同。**

```text
统一消息 → 供应商输入适配 → SDK 调用 → 供应商输出适配 → 统一 AIMessage
```

这里用的是**纯文本、简单对话**的教学案例，不代表真实适配器只需处理这些字段。

---

## 六、封装、继承、多态，分别对应哪里？（第 6—7 分钟）

### 6.1 封装（Encapsulation）

SDK 调用及请求/响应转换都在 `OpenAIAdapter` / `AnthropicAdapter` 内部。

业务层只看到：

```python
answer = model.invoke(messages)
```

业务层不再知道 `choices[0]`、`content blocks` 和 `system` 参数的供应商差别。

### 6.2 继承（Inheritance）

```python
class BaseChatModel(Runnable):
    pass

class OpenAIAdapter(BaseChatModel):
    ...

class AnthropicAdapter(BaseChatModel):
    ...
```

两个模型都属于一个抽象类型 `BaseChatModel`，也都遵守 `Runnable` 的通用接口。

### 6.3 多态（Polymorphism）

```python
def ask(model: BaseChatModel, messages):
    return model.invoke(messages)

ask(OpenAIAdapter(), messages)
ask(AnthropicAdapter(), messages)
```

同一行 `model.invoke(messages)`，运行时根据传进来的模型对象调用不同实现。

**多态不只是“两个类有同名方法”，而是“上层程序面对共同接口，具体实现可以替换”。**

注意：上面的 `ask` 若直接运行，会调用真实 API 并需要 Key；无需 Key 的做法见第 10 节的模拟客户端。

---

## 七、`prompt | model | parser` 怎样实现组合？（第 7—9 分钟）

### 7.1 Prompt 本身也是一个 Runnable

```python
class ChatPromptTemplate(Runnable):
    def __init__(self, template):
        self.template = template

    def invoke(self, variables):
        return [
            SystemMessage("回答尽量简短。"),
            HumanMessage(self.template.format(**variables)),
        ]
```

假设调用：

```python
prompt.invoke({"question": "1+1等于多少？"})
```

得到：

```python
[
    SystemMessage(content="回答尽量简短。"),
    HumanMessage(content="请用一句话回答：1+1等于多少？"),
]
```

### 7.2 Parser 也是一个 Runnable

```python
class StrOutputParser(Runnable):
    def invoke(self, ai_message):
        return ai_message.content
```

它将 `AIMessage(content="2")` 转换为普通字符串 `"2"`。

### 7.3 最重要的 RunnableSequence

```python
class RunnableSequence(Runnable):
    def __init__(self, steps):
        self.steps = []
        for step in steps:
            if isinstance(step, RunnableSequence):
                self.steps.extend(step.steps)
            else:
                self.steps.append(step)

    def invoke(self, value):
        for step in self.steps:
            value = step.invoke(value)
        return value
```

而前面 `Runnable` 中的：

```python
def __or__(self, other):
    return RunnableSequence([self, other])
```

使得：

```python
chain = prompt | model | parser
```

本质相当于创建：

```python
chain = RunnableSequence([prompt, model, parser])
```

**注意：** `|` 执行的是“构造组合对象”，不是并行执行，也不是马上发 API 请求。

### 7.4 串成一个完整调用

```python
prompt = ChatPromptTemplate("请用一句话回答：{question}")
model = OpenAIAdapter()   # 也可以替换为 AnthropicAdapter()
parser = StrOutputParser()

chain = prompt | model | parser
result = chain.invoke({"question": "1+1等于多少？"})
print(result)
```

等价于人工逐步执行：

```python
x = {"question": "1+1等于多少？"}
x = prompt.invoke(x)  # dict -> 消息列表
x = model.invoke(x)   # 消息列表 -> AIMessage
x = parser.invoke(x)  # AIMessage -> str
```

**这个 `for step in self.steps: value = step.invoke(value)` 就是整个简单执行链的核心。**

---

## 八、用一条数据把所有流程串起来（第 9—10 分钟）

用户原始输入：

```python
{"question": "1+1等于多少？"}
```

完整调用：

```text
chain.invoke({"question": "1+1等于多少？"})
      │
      ▼
RunnableSequence.invoke()
      │
      ├─ 1. ChatPromptTemplate.invoke()
      │       输入：dict
      │       输出：[SystemMessage(...), HumanMessage(...)]
      │
      ├─ 2. model.invoke()
      │       OpenAI：转换 messages → OpenAI SDK → 提取 choices[0]
      │       Anthropic：拆 system → Anthropic SDK → 提取文本块
      │       最终统一输出：AIMessage(content="2")
      │
      └─ 3. StrOutputParser.invoke()
              输入：AIMessage(content="2")
              输出："2"
```

最后可以让学生回答两个问题：

**Q1：为什么换了 OpenAI、Anthropic，`chain.invoke(...)` 不需要改？**

因为对外模型都是 `Runnable` / `BaseChatModel` 抽象，上层只调用共同接口；供应商差异由具体实现封装。

**Q2：为什么 Prompt、Model、Parser 能用 `|` 串起来？**

因为它们都可调用 `invoke()`，`|` 创建 `RunnableSequence`，后者按顺序将前一步输出交给下一步。

---

## 九、回到真正的 LangChain：教学版与官方实现不能混淆

上面的 `OpenAIAdapter` 和 `AnthropicAdapter` 是**我们自己写的教学类**，不是真实类名。对应关系：

| 教学版 | 真正 LangChain 中的相关类型 |
|---|---|
| `Runnable` | `langchain_core.runnables.Runnable` |
| `RunnableSequence` | `langchain_core.runnables.RunnableSequence` |
| `BaseChatModel` | `langchain_core.language_models.chat_models.BaseChatModel` |
| `OpenAIAdapter` | `langchain_openai.ChatOpenAI` |
| `AnthropicAdapter` | `langchain_anthropic.ChatAnthropic` |
| `ChatPromptTemplate` | `langchain_core.prompts.ChatPromptTemplate` |
| `StrOutputParser` | `langchain_core.output_parsers.StrOutputParser` |

**一个特别重要的区别：** 为便于学生理解，教学版让两个适配器直接实现公开的 `invoke()`；真实 LangChain 的 `BaseChatModel` 已经提供 `invoke()` 等通用功能，而具体 Chat Model 通常通过 `_generate()` 等接口实现自己的底层请求。抽象上可理解为：

```text
        model.invoke(messages)         ← 对外公共入口
                 │
                 ▼
         BaseChatModel 通用处理
                 │
                 ▼
     具体模型实现自己的 _generate()
                 │
          ┌──────┴───────┐
          ▼              ▼
      ChatOpenAI     ChatAnthropic
          │              │
       OpenAI API      Anthropic API
          │              │
          └──────┬───────┘
                 ▼
             AIMessage
```

正式框架还要处理异步、流式输出、重试、工具调用、复杂消息类型、用量与调用元数据等工程细节。

真正的 LangChain 业务代码可以写成：

```bash
pip install -U langchain-core langchain-openai langchain-anthropic
```

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

prompt = ChatPromptTemplate.from_messages([
    ("system", "回答尽量简短。"),
    ("human", "请用一句话回答：{question}"),
])

# 两者二选一，下面的调用链保持不变
model = ChatOpenAI(model="gpt-4o-mini")
# model = ChatAnthropic(model="claude-haiku-4-5-20251001")

chain = prompt | model | StrOutputParser()
print(chain.invoke({"question": "1+1等于多少？"}))
```

另一种写法是让 `init_chat_model()` 负责模型提供商选择；切换 `openai:...` 和 `anthropic:...` 后，后面仍然是 `prompt | model | parser`。

---

## 十、无需 API Key 的课堂演示（补充 2 分钟，或课后练习）

为了课堂演示不依赖网络或付费调用，我们可以**模拟 SDK 的返回对象**，但保留两个 Adapter 内部真正的参数转换过程。

将第 11 节的完整教学代码存为 `langchain_core_teaching.py`，另建 `langchain_mock_demo.py`：

```python
from types import SimpleNamespace
from langchain_core_teaching import (
    ChatPromptTemplate,
    OpenAIAdapter,
    AnthropicAdapter,
    StrOutputParser,
)

class FakeOpenAIClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=self)

    def create(self, **request):
        print("[OpenAI 收到的请求]", request)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content="2"))
            ]
        )

class FakeAnthropicClient:
    def __init__(self):
        self.messages = self

    def create(self, **request):
        print("[Anthropic 收到的请求]", request)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="2")]
        )

prompt = ChatPromptTemplate("请用一句话回答：{question}")
parser = StrOutputParser()

for model in (
    OpenAIAdapter(client=FakeOpenAIClient()),
    AnthropicAdapter(client=FakeAnthropicClient()),
):
    chain = prompt | model | parser
    print("最终结果：", chain.invoke({"question": "1+1等于多少？"}))
```

运行：

```bash
python langchain_mock_demo.py
```

关键输出（空格、字典格式可能略有不同）：

```text
[OpenAI 收到的请求] {
  'model': 'gpt-4o-mini',
  'messages': [
    {'role': 'system', 'content': '回答尽量简短。'},
    {'role': 'user', 'content': '请用一句话回答：1+1等于多少？'}
  ]
}
最终结果： 2

[Anthropic 收到的请求] {
  'model': 'claude-haiku-4-5-20251001',
  'max_tokens': 128,
  'messages': [
    {'role': 'user', 'content': '请用一句话回答：1+1等于多少？'}
  ],
  'system': '回答尽量简短。'
}
最终结果： 2
```

**要观察的是：底层请求参数不同，最终 `chain.invoke(...)` 输出却相同。** 模拟程序不会访问实际模型，也不代表真实模型一定回答“2”。

---

## 十一、完整教学版源码：可复制为一个 `.py` 文件

前面为了讲解而把类拆开了。这里给出**真正可以直接复制成一个 Python 文件**的整合版本；它与上面各段代码的逻辑一致，适合课后阅读。

```python
"""教学版极简 LangChain：封装、继承、多态、组合。
真实请求需 pip install openai anthropic 并设置对应 API Key。
演示可通过替换 client 使用模拟客户端，无须联网。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


# 1. 统一消息类型
@dataclass
class SystemMessage:
    content: str


@dataclass
class HumanMessage:
    content: str


@dataclass
class AIMessage:
    content: str


# 2. 统一调用接口，以及 | 运算符
class Runnable(ABC):
    @abstractmethod
    def invoke(self, value):
        pass

    def __or__(self, other):
        return RunnableSequence([self, other])


class RunnableSequence(Runnable):
    def __init__(self, steps):
        self.steps = []
        for step in steps:
            if isinstance(step, RunnableSequence):
                self.steps.extend(step.steps)
            else:
                self.steps.append(step)

    def invoke(self, value):
        for step in self.steps:
            value = step.invoke(value)
        return value


# 3. Prompt 本身也是一个 Runnable
class ChatPromptTemplate(Runnable):
    def __init__(self, template):
        self.template = template

    def invoke(self, variables):
        return [
            SystemMessage("回答尽量简短。"),
            HumanMessage(self.template.format(**variables)),
        ]


# 4. 模型共同基类
class BaseChatModel(Runnable):
    pass


# 5. OpenAI 模型适配器
class OpenAIAdapter(BaseChatModel):
    def __init__(self, model="gpt-4o-mini", client=None):
        if client is None:
            from openai import OpenAI
            client = OpenAI()  # 默认读取环境变量 OPENAI_API_KEY
        self.client = client
        self.model = model

    def invoke(self, messages):
        # (1) LangChain 风格的消息对象 -> OpenAI 请求格式
        api_messages = []
        for message in messages:
            if isinstance(message, SystemMessage):
                role = "system"
            elif isinstance(message, HumanMessage):
                role = "user"
            elif isinstance(message, AIMessage):
                role = "assistant"
            else:
                raise TypeError(f"不支持的消息类型: {type(message)}")
            api_messages.append({"role": role, "content": message.content})

        # (2) 真正发起 OpenAI SDK 请求
        response = self.client.chat.completions.create(
            model=self.model,
            messages=api_messages,
        )

        # (3) OpenAI 的返回对象 -> 统一 AIMessage
        answer = response.choices[0].message.content or ""
        return AIMessage(content=answer)


# 6. Anthropic 模型适配器
class AnthropicAdapter(BaseChatModel):
    def __init__(self, model="claude-haiku-4-5-20251001", client=None):
        if client is None:
            from anthropic import Anthropic
            client = Anthropic()  # 默认读取环境变量 ANTHROPIC_API_KEY
        self.client = client
        self.model = model

    def invoke(self, messages):
        # (1) Anthropic 的 system 单独作为顶层字段
        system_parts = []
        api_messages = []
        for message in messages:
            if isinstance(message, SystemMessage):
                system_parts.append(message.content)
            elif isinstance(message, HumanMessage):
                api_messages.append({"role": "user", "content": message.content})
            elif isinstance(message, AIMessage):
                api_messages.append({"role": "assistant", "content": message.content})
            else:
                raise TypeError(f"不支持的消息类型: {type(message)}")

        # (2) 真正发起 Anthropic SDK 请求
        kwargs = {
            "model": self.model,
            "max_tokens": 128,
            "messages": api_messages,
        }
        if system_parts:
            kwargs["system"] = "\n".join(system_parts)
        response = self.client.messages.create(**kwargs)

        # (3) Anthropic 的 content blocks -> 统一 AIMessage
        answer = "".join(
            block.text
            for block in response.content
            if block.type == "text"
        )
        return AIMessage(content=answer)


# 7. 输出解析器
class StrOutputParser(Runnable):
    def invoke(self, ai_message):
        return ai_message.content


# 8. 应用层：只改这一行，即可换模型
if __name__ == "__main__":
    prompt = ChatPromptTemplate("请用一句话回答：{question}")
    model = OpenAIAdapter()   # 改成 AnthropicAdapter() 即可
    parser = StrOutputParser()

    chain = prompt | model | parser
    result = chain.invoke({"question": "1+1等于多少？"})
    print(result)
```

想调用真实模型：

```bash
pip install openai anthropic
# 配置相应的 OPENAI_API_KEY / ANTHROPIC_API_KEY 后运行
python langchain_core_teaching.py
```

想完全离线演示：把第 10 节保存为 `langchain_mock_demo.py`，与上面文件放在同一目录，然后执行 `python langchain_mock_demo.py`。

---

## 十二、最后总结：和 LLaMA-Factory 的核心思想对应

| | LLaMA-Factory | LangChain |
|---|---|---|
| 主要任务 | 训练 / 微调模型 | 调用与编排模型应用组件 |
| 不同来源 | 数据格式、模型、训练方式 | 供应商 API、Prompt、Parser 等组件 |
| 核心抽象 | Data Adapter、Model Adapter、Template、Trainer | Model Adapter、Runnable、RunnableSequence |
| 对上层的价值 | 用统一配置走训练流水线 | 用统一接口走执行流水线 |

**最后只留两行代码给学生：**

```python
# 不同实现：对外都可以这样调用
model.invoke(messages)

# 不同组件：对外可以这样组合
(prompt | model | parser).invoke({"question": "1+1等于多少？"})
```

> **一句话收尾：LLaMA-Factory 把不同训练配置适配成统一训练流程；LangChain 把不同模型和组件抽象成 Runnable，再用 `RunnableSequence` 把它们组织成执行流水线。**

### 资料（供教师课后核对）

- [LangChain Runnable / RunnableSequence](https://reference.langchain.com/python/langchain-core/runnables/base)
- [LangChain BaseChatModel](https://reference.langchain.com/python/langchain-core/language_models/chat_models/BaseChatModel)
- [LangChain ChatPromptTemplate](https://reference.langchain.com/python/langchain-core/prompts/chat/ChatPromptTemplate)
- [LangChain init_chat_model](https://reference.langchain.com/python/langchain/chat_models/base/init_chat_model)
- [LangChain OpenAI Integration](https://docs.langchain.com/oss/python/integrations/chat/openai)
- [LangChain Anthropic Integration](https://docs.langchain.com/oss/python/integrations/chat/anthropic)
- [OpenAI API](https://developers.openai.com/api/reference/resources/chat)
- [Anthropic Messages API](https://platform.claude.com/docs/en/api/python/messages/create)
