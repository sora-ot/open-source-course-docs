# 03 TypeScript 语法速成：从看懂一行代码到读懂 Pi

## 0. 为什么 Pi 和 OpenClaw 要用 TypeScript 来写

**因为 Pi、OpenClaw 主要做的是把模型、工具、消息和界面接起来，而 TypeScript 很适合组织这类应用。** 结合源码，可以从四个方面理解。这里是工程上的分析，不是作者对选型原因的原话。

### 0.1 接口多，类型能帮忙检查有没有接错

模型消息、工具参数、工具结果、流式事件，都有各自的数据格式。`pi/packages/ai/src/types.ts` 就是在规定模型调用涉及的数据应该长什么样。

比如，在 Agent 层，一个可执行工具需要提供 `execute` 函数，返回结果也要符合约定。用 TypeScript，很多漏字段、传错参数的问题，在写代码时就能发现，减少运行到一半才报错的情况。

### 0.2 这类程序经常在等待外部结果，异步写法很合适

调用模型要等网络，模型回答要逐段接收，执行命令要等结果，用户还可能中途取消。JavaScript／TypeScript 的 `Promise`、`async/await` 和异步迭代，很适合组织这些过程。

不过，并发怎么安排、错误怎么处理，仍然需要程序员设计。这些异步能力本身属于 JavaScript，TypeScript 则进一步描述参数、结果和事件的类型。

### 0.3 可以直接使用 JavaScript 和 Node.js 的生态

网络请求、文件操作、启动进程、终端界面，以及各种服务的 SDK，都有大量现成组件。TypeScript 可以使用这些组件，同时给自己的代码加上类型检查。

### 0.4 方便把能力做成包，让其他应用接着用

Pi 把能力拆成 `pi-ai`、`pi-agent-core`、`pi-coding-agent`，其他 TypeScript 程序可以直接导入。类型定义还能让调用者在编辑器里看到参数提示、返回结果和接口说明，OpenClaw 接入时也更容易检查接口是否匹配。

理解了这些用途，再学习后面的语法，就可以把类型、函数、模块和异步写法与它们在项目中的作用联系起来。

## 本章阅读说明

> 标题后面的“（重点）”，表示这里有读 Pi 源码要掌握的 TypeScript 写法。主要对照本地 `pi/pi/packages/` 下各包的 `src/`，重点看 `ai`、`agent`、`coding-agent`，也核对了 `tui` 等包。
>
> `if / else`、普通循环、赋值等基础语法不标。可选链、解构、箭头函数、`async / await` 和生成器本身也属于 JavaScript；本次重点标出新增的类型写法，以及同一个符号在类型位置的新含义。

本章的目的是建立阅读 TypeScript 源码所需的语法基础：**能够分清数据与类型、定义与调用、同步执行与异步等待，并把一段复杂代码拆成可以逐步解释的动作。**

我们从一条最简单的消息开始：用户说“你好”。随后，程序保存这条消息，整理内容，通知监听器，等待异步工作。这些动作可以把函数、回调和异步串起来；其他语法则按类别补齐，不要求读者先熟悉 JavaScript。

短小的“教学示例”用于说明规则；“Pi 源码”取自实际文件，省略内容会明确标出。示例中的输出是对执行结果的推演，不是运行 Pi 的日志。各个小例按所在段落阅读，不需要把整章代码拼成一个程序；相邻片段需要接续时，会在文字中说明。

| 语法类别 | 要解决的阅读困难 |
| --- | --- |
| 值、变量与表达式 | `const`、`let`、引号、反引号、赋值和比较分别做什么 |
| 对象、数组与数据拆装 | `{}`、`[]`、解构、展开、属性简写怎样改变数据 |
| 分支、循环与运算符 | `?`、`?.`、`??`、`&&`、`\|\|` 怎样决定程序走哪一步 |
| 类型与接口 | 冒号、`interface`、`type`、联合类型怎样描述数据 |
| 函数与回调 | 普通函数、箭头、方法、函数类型、嵌套和闭包怎样阅读 |
| 容器与批量处理 | `map`、`filter`、`reduce`、`Set`、`Map` 怎样工作 |
| 模块与类 | `import`、`export`、`class`、`this` 怎样连接文件与对象 |
| 泛型与类型运算 | `<T>`、`extends`、`keyof`、`T[K]` 等怎样组合类型 |
| 异步与流 | `Promise`、`async`、`await`、`yield`、`for await` 怎样安排时间 |
| 综合阅读 | 如何逐层拆开 Pi 的真实函数签名与实现 |

## 1. 一条消息中，哪些是数据，哪些是类型

### 1.1 先从 JavaScript 的动作开始

教学示例：

```js
const text = "你好";
const message = {
  role: "user",
  content: text,
  timestamp: 1000,
};
```

先按顺序理解三件事：

1. 把字符串 `"你好"` 交给名字 `text`。
2. 创建一个对象，里面有 `role`、`content`、`timestamp` 三个属性。
3. 把这个对象交给名字 `message`。

于是可以读取：

```js
message.role;       // "user"
message.content;    // "你好"
message.timestamp;  // 1000
```

`message.content` 的意思是：找到 `message` 指向的对象，再取出它的 `content` 属性。点号不是数学上的乘号。

这里把时间固定为 `1000`，方便观察。Pi 的真实用户消息也有 `role`、`content` 和 `timestamp`，创建消息时会使用实际时间。

### 1.2 TypeScript 在哪里增加了信息（重点）

再看：

```ts
const text: string = "你好";
```

把它分成四块：

```text
const text     : string     =     "你好"
建立名字        类型说明     赋值   实际的值
```

`string` 表示字符串类型。冒号是在说明“这个名字应当接收哪一类值”，没有创建另一个字符串，也没有调用函数。

删除这一处类型标注后，实际动作仍然是：

```js
const text = "你好";
```

因此，读 TypeScript 时，常常可以先找出 **JavaScript 正在做的动作**，再看 **TypeScript 对这些动作提出的类型约束**。类型标注、接口和大多数类型运算不会在运行时替我们检查外部数据；不过，不能把所有 TypeScript 语法都理解成可直接删除，普通 `enum` 等写法还会产生运行代码。

### 1.3 没有写类型，为什么也能看出它是字符串（重点）

```ts
let text = "你好";
text = "请继续";  // 可以
// text = 42;    // 类型检查会指出：这里应当继续放字符串
```

TypeScript 根据初始值推断了类型。这叫**类型推断**。源码没有写满冒号，并不表示它没有类型信息。

常见的值与类型可以先这样对应：

| 值 | 类型或含义 | 阅读时注意 |
| --- | --- | --- |
| `"你好"` | `string` | 引号里面的是内容 |
| `3`、`0.5` | `number` | 普通整数和小数都使用这个类型 |
| `true`、`false` | `boolean` | 两个布尔值，不是字符串 |
| `undefined` | 未提供、未取得或没有返回值等情况 | 读不存在的属性可能得到它 |
| `null` | 显式放入的空值 | 常用于表达“这里现在没有对象” |
| `["你好", "再见"]` | 数组 | 按顺序保存多个元素 |
| `{ text: "你好" }` | 对象 | 按属性名组织内容 |
| `123n` | `bigint` | 大整数，不能直接和普通 `number` 混合运算 |
| `Symbol("event")` | `symbol` | 可作为独特的属性键，异步迭代会用到 |

### 1.4 `const`、`let`、`var`：名字能不能改绑

```ts
let count = 0;
count = count + 1;

const label = "user";
// label = "assistant";  // 不允许给这个 const 名字重新赋值
```

`let` 允许重新赋值；`const` 不允许重新赋值。`var` 是较早的声明方式，它主要按函数划分作用域，与 `let`、`const` 的块作用域不同。阅读现代 Pi 源码时，重点先放在 `let` 和 `const`。

“块”通常由一对大括号围起来：

```ts
let count = 1;

if (true) {
  const count = 2;
  console.log(count); // 2：这里读的是里面的名字
}

console.log(count);   // 1：外面的名字仍然指向 1
```

里面的 `count` 暂时遮住了外面的同名变量。这叫**变量遮蔽**。读函数套函数时，先确定一个名字属于哪一层，才能判断它读写的是谁。

### 1.5 引号、反引号、注释与分号

```ts
const name = "小林";
const a = '你好';
const b = "你好";
const c = `你好，${name}！`;
```

`a` 和 `b` 都是普通字符串；反引号支持 `${表达式}`，先计算表达式，再把结果放进字符串。因此 `c` 是 `"你好，小林！"`。

```ts
// 这一行是注释

/* 这也是注释，
   可以占多行。 */

/** 这种文档注释常用于解释接口和函数。 */
```

注释本身不执行。`//` 在引号里面则只是字符串内容，例如 `"https://example.com"`。

分号通常结束一条语句；对象属性和数组元素之间通常使用逗号。源码会有换行和缩进，但阅读结构时仍要看括号、分号以及关键字。

## 2. 对象、数组、解构与展开：数据怎样组织和拆开

### 2.1 对象中的冒号，是“属性名对应一个值”

```ts
const text = "你好";
const message = { content: text };
```

这里的 `content: text` 表示：属性名叫 `content`，属性值取变量 `text` 的值。

它与前面的 `text: string` 不一样：

```text
const text: string = "你好";
           └ 类型标注

const message = { content: text };
                          └ 属性值
```

**冒号的含义由它所在的位置决定。** 看到冒号，先问自己：现在是在创建对象，还是在说明类型？

### 2.2 属性简写与计算属性

属性名和变量名相同时，可以缩写：

```ts
const text = "你好";
const block = { text };
```

等价于：

```ts
const block = { text: text };
```

再看方括号：

```ts
const key = "content";
const message = { [key]: "你好" };

message[key];       // "你好"
message.content;    // "你好"
```

对象定义中的 `[key]` 表示先计算 `key`，再把得到的字符串当作属性名；访问时的 `message[key]` 也是用变量的值来选择属性。若写 `message.key`，找的就是字面上叫 `key` 的属性。

### 2.3 数组的方括号：创建与索引

```ts
const texts = ["你好", "请继续", "谢谢"];

texts[0];      // "你好"
texts[1];      // "请继续"
texts.length;  // 3
```

数组从下标 `0` 开始。`texts[0]` 读取第一个元素；左边出现赋值时，就会修改对应位置：

```ts
texts[1] = "请详细解释";
texts.push("再见");
```

`push(...)` 是调用数组提供的方法，把参数加入末尾。**名字后面的圆括号，常常意味着现在执行一次调用。**

### 2.4 `const` 固定的是名字，不是对象的内容

```ts
const message = { content: "你好" };
message.content = "请继续"; // 可以修改对象的属性

const messages = [message];
messages.push({ content: "谢谢" }); // 可以修改数组内容
```

不能因此断言 `const` 创建了“不可变对象”。不允许的是给 `message` 或 `messages` 这个名字换绑一个新的值。

赋值对象时通常也不会自动复制内容：

```ts
const first = { content: "你好" };
const second = first;
second.content = "请继续";

first.content; // "请继续"
```

此时两个名字指向同一个对象：

```text
first  ─┐
        ├──→ { content: "请继续" }
second ─┘
```

### 2.5 解构：一次取出需要的属性

```ts
const message = { role: "user", content: "你好", timestamp: 1000 };
const { role, content } = message;
```

把第二行展开，就容易理解：

```ts
const role = message.role;
const content = message.content;
```

解构没有删除原对象的属性，也没有把整个对象复制一遍，只是把指定属性的值取出来，交给新的名字。

还可以改名：

```ts
const { content: text } = message;
```

意思是：**取 `content` 属性，放进名为 `text` 的变量。** 这里的冒号又是另一种用途，不是给 `content` 标注名为 `text` 的类型。

### 2.6 解构默认值：只有拿到 `undefined` 才补默认值

```ts
const options = { title: undefined };
const { title = "新会话" } = options;
```

因为 `title` 的值为 `undefined`，所以解构得到的变量 `title` 采用 `"新会话"`。如果属性值是空字符串 `""`，它会保留空字符串；`null` 也不会触发解构默认值。

数组同样可以解构：

```ts
const [first, second] = ["你好", "请继续"];
// first  = "你好"
// second = "请继续"
```

默认值、改名和数组解构的共同点是：**把已有值拆出来，再给它们安排名字。** [解构语法参考](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/Destructuring)

### 2.7 `...` 放在右边：把已有内容展开

```ts
const previous = ["你好"];
const next = [...previous, "请继续"];
```

结果为：

```text
previous = ["你好"]
next     = ["你好", "请继续"]
```

对象也能展开：

```ts
const original = { role: "user", content: "你好" };
const changed = { ...original, content: "请继续" };
```

同名属性以后出现的值为准。因此 `changed.content` 是 `"请继续"`，`original.content` 仍是 `"你好"`。

顺序换过来，结果也会变：

```ts
const changed = { content: "请继续", ...original };
// 后面展开的 original.content 又覆盖回来，结果是 "你好"
```

### 2.8 展开和 `slice()` 通常只复制最外层

```ts
const first = { content: "你好" };
const oldMessages = [first];
const newMessages = [...oldMessages];

newMessages.push({ content: "谢谢" });
```

现在两个数组的长度分别是 `1` 和 `2`，因为它们已经是不同数组。但两个数组的第一个元素仍然指向同一个 `first`：

```ts
newMessages[0].content = "请继续";
oldMessages[0].content; // "请继续"
```

所以，“复制数组”不等于“递归复制数组里的所有对象”。Pi 准备内部状态时会用 `slice()` 复制数组外层，读到这种代码时，也要保留这一区别。

### 2.9 `...` 放在接收位置：收集剩余内容

```ts
const [first, ...rest] = ["你好", "请继续", "谢谢"];
// first = "你好"
// rest  = ["请继续", "谢谢"]

const { role, ...other } = { role: "user", content: "你好", timestamp: 1000 };
// role  = "user"
// other = { content: "你好", timestamp: 1000 }
```

同样的三个点，方向不同：

| 位置 | 作用 |
| --- | --- |
| `[...oldMessages, newMessage]` | 把旧数组展开 |
| `{ ...oldOptions, timeout: 10 }` | 把旧对象属性展开 |
| `send(...args)` | 把数组元素作为多个实参传进去 |
| `const [first, ...rest] = values` | 把剩余元素收集成数组 |
| `function send(...args) {}` | 把多个实参收集成一个参数数组 |

最后一种是函数的剩余参数，后面读函数时会继续使用。

### 2.10 JSON 与对象长得像，但用途不同

```ts
const message = { content: "你好" }; // JavaScript 对象
const json = JSON.stringify(message); // 字符串：'{"content":"你好"}'
const restored = JSON.parse(json);    // 重新得到一个值
```

JSON 是一种文本格式。它不能直接放函数、注释或 `undefined`，属性名要使用双引号。一个字符串经过 `JSON.parse`，也不代表它自动满足某个 TypeScript 接口；外部数据仍需要实际检查。

## 3. 条件、循环与运算符：程序接下来走哪一步

### 3.1 先分清赋值与比较

```ts
let count = 1;
count = 2;        // 把 2 放进去
count === 2;      // 比较，得到 true
count !== 2;      // 比较，得到 false
```

常见运算可以归成几组：

| 类别 | 常见写法 | 含义 |
| --- | --- | --- |
| 算术 | `+ - * / % **` | 加、减、乘、除、余数、乘方 |
| 大小比较 | `< <= > >=` | 得到布尔值 |
| 严格相等 | `=== !==` | 比较时不做宽松的类型转换 |
| 赋值 | `= += -=` | 保存或更新值 |
| 自增自减 | `++ --` | 把数值增加或减少 1 |
| 逻辑与取反 | `&& \|\| !` | 条件组合、短路和取反 |

`==` 和 `!=` 会进行某些类型转换，例如 `0 == false` 为真；源码里常用 `===` 和 `!==`，把类型差异也保留下来。对象的 `===` 比较的是是否为同一个对象，两个分别创建的 `{}` 不会因为都为空而相等。

`+` 还可以拼接字符串，`"2" + 3` 得到 `"23"`，不是 `5`。`++i` 与 `i++` 都会修改 `i`，但表达式的结果分别取修改后和修改前的值。

### 3.2 `if` 看的是条件的真假，不只接受 `true` 与 `false`

```ts
const text = "你好";

if (text) {
  console.log("有内容");
} else {
  console.log("没有内容");
}
```

在条件位置，`false`、`0`、`-0`、`0n`、`NaN`、`""`、`null`、`undefined` 会被当作假。普通对象和数组，包括 `{}` 和 `[]`，都会被当作真。

因此：

```ts
const messages: string[] = [];

if (messages) {
  // 即使数组是空的，这里也会进入
}

if (messages.length > 0) {
  // 这里才是在判断是否至少有一个元素
}
```

### 3.3 `&&` 与 `||`：可能少执行一边，也可能返回一个普通值

```ts
const first = "" || "默认文本";       // "默认文本"
const second = "你好" || "默认文本"; // "你好"
```

`||` 先看左边：左边为真就返回左边，否则才计算右边。

`&&` 则相反：左边为假就返回左边，左边为真才计算右边。例如：

```ts
const text = "你好";
const length = text && text.length; // 2
```

所以它们并不总是返回 `boolean`。这一点与“如果满足条件就执行右边”的常见写法有关：

```ts
if (messages && messages.length > 0) {
  // 两个条件都满足才进入
}
```

### 3.4 `??`：只给 `null` 和 `undefined` 提供后备值（重点）

```ts
const a = 0 || 10;         // 10
const b = 0 ?? 10;         // 0
const c = "" ?? "默认";   // ""
const d = null ?? "默认"; // "默认"
```

假设 `0` 表示用户明确要求“等待 0 毫秒”。用 `||` 会把这个有效设置换掉；`??` 则保留它。

要判断该用哪一个，需要先理解数据里 `0`、空字符串和 `false` 是否是有效值。混合使用 `??` 与 `||`、`&&` 时应加括号，不能不加括号直接拼在一起。

### 3.5 `?.`：对象不存在时，在这里停下来（重点）

下面暂时用 JavaScript 写法，只观察可选链与后备值：

```js
function getTitle(options) {
  return options?.title ?? "新会话";
}
```

分三种输入看：

| 输入 | `options?.title` 的值 | 最终结果 |
| --- | --- | --- |
| 没有传 `options` | `undefined` | `"新会话"` |
| `{}` | `undefined` | `"新会话"` |
| `{ title: "实验记录" }` | `"实验记录"` | `"实验记录"` |

`?.` 只在左侧为 `null` 或 `undefined` 时停止，不会捕获任意异常。链条里哪一层可能缺失，就要留意哪一层受到保护：

```ts
options?.user?.name;
items?.[0];
onUpdate?.("进行中");
```

这三行是写法示意：分别用于属性访问、按下标访问、可选函数调用。`onUpdate?.(...)` 表示函数值存在时才调用；若它存在却不是函数，仍可能报错。

### 3.6 `条件 ? A : B`：从两个结果中选择一个

```ts
const count = 2;
const title = count > 0 ? "有消息" : "空会话";
```

可以展开成：

```ts
let title;
if (count > 0) {
  title = "有消息";
} else {
  title = "空会话";
}
```

它叫**条件表达式**，也常叫三元表达式。这里的 `?` 不是可选参数，冒号也不是类型标注。

### 3.7 循环：重复执行一段动作

```ts
const texts = ["你好", "谢谢"];

for (let i = 0; i < texts.length; i++) {
  console.log(texts[i]);
}
```

由两个分号分隔的三个部分依次是：初始设置、继续条件、每轮后的更新。也可以直接逐个取值：

```ts
for (const text of texts) {
  console.log(text);
}
```

注意 `of` 与 `in`：

```ts
for (const value of texts) { /* value 是 "你好"、"谢谢" */ }
for (const key in texts) { /* key 通常是 "0"、"1" 等可枚举属性名 */ }
```

遍历数组的内容通常读作 `for...of`。`for...in` 遍历可枚举属性，还可能涉及继承的属性，不要把它当成另一种完全等价的数组遍历。

`while (条件)` 在条件成立时重复；`do...while` 至少先执行一次。`break` 结束当前循环，`continue` 跳过这一轮剩余部分，`return` 则离开当前函数。

### 3.8 `switch` 与提前返回

```js
function describeRole(role) {
  switch (role) {
    case "user":
      return "用户消息";
    case "assistant":
      return "助手消息";
    default:
      return "其他消息";
  }
}
```

`case` 对照具体取值。这里每个分支都 `return`，函数会立即结束；如果只是处理一些动作，通常要用 `break` 防止继续落入下一分支。

源码中也常见先处理特殊情况：

```js
function firstText(texts) {
  if (texts.length === 0) return undefined;
  return texts[0];
}
```

读到提前返回后，后面的代码只需要考虑“前面没有退出”的情况。

## 4. 类型与接口：先看值的样子，再给它一个名字

### 4.1 `interface` 描述对象应当有什么（重点）

Pi 用下面的接口描述文本内容块，这里只去掉注释：

Pi 源码：[packages/ai/src/types.ts](../pi-master/packages/ai/src/types.ts#L148)

```ts
export interface TextContent {

  type: "text";

  text: string;

  textSignature?: string;
}
```

先创建一个符合要求的值：

```ts
const block: TextContent = {
  type: "text",
  text: "你好",
};
```

逐项对应：

```text
接口要求                 实际对象
-------------------------------------
type 必须是 "text"        type: "text"
text 必须是字符串         text: "你好"
textSignature 可以省略    此处没有提供
```

`interface TextContent` 没有创建一个内容块。`const block = {...}` 才创建了实际对象。接口只是描述这个对象应该具有的形状。

其中 `type: "text"` 比 `type: string` 更严格：前者只允许这个特定字符串，后者允许任意字符串。这样的固定取值叫**字面量类型**。

### 4.2 为什么接口看起来像对象，却不用写属性值（重点）

比较：

```ts
interface Note {
  text: string;
}

const note: Note = {
  text: "你好",
};
```

上面是在说“应该有一个字符串属性”，下面是在放入具体的 `"你好"`。类型中通常用分号分隔成员，实际对象中用逗号分隔属性；它们都使用大括号，但不能因为长得像就混为一谈。

### 4.3 属性后面的 `?` 与 `| undefined` 不一样（重点）

```ts
interface OptionalTitle {
  title?: string;
}

interface RequiredSlot {
  title: string | undefined;
}
```

第一种允许整个属性不提供：

```ts
const a: OptionalTitle = {};
```

第二种要求有 `title` 这个位置，只是它的值可以是 `undefined`：

```ts
const b: RequiredSlot = { title: undefined };
// const c: RequiredSlot = {}; // 缺少必需属性
```

读取可选属性时，仍需要考虑取到 `undefined` 的情况。`?` 不会自动给它一个默认值。

### 4.4 `type`：给一种类型表达式起名字（重点）

```ts
interface TextBlock {
  type: "text";
  text: string;
}

type AnotherTextBlock = {
  type: "text";
  text: string;
};
```

这里两个 `type` 含义不同：`type AnotherTextBlock = ...` 中的 `type` 是定义类型别名的 TypeScript 关键字；`type: "text"` 中的 `type` 是对象属性名，表示这个属性的值只能是字符串 `"text"`。

**如果只是描述对象有哪些属性，`type` 和 `interface` 的用法几乎一样。** 上面的两种类型都可以这样使用：

```ts
const a: TextBlock = { type: "text", text: "你好" };
const b: AnotherTextBlock = { type: "text", text: "你好" };
```

`AnotherTextBlock` 只是为了方便比较而取的名字，没有特殊含义。如果选择 `type` 这种写法，也可以直接命名为 `TextBlock`：

```ts
type TextBlock = {
  type: "text";
  text: string;
};
```

这是前面 `interface TextBlock` 的替代写法，不能把这两个同名定义同时放在同一作用域中。

两者的主要区别，先记住下面两点即可：

| 对比 | `interface` | `type` |
| --- | --- | --- |
| 描述对象的属性结构 | 可以 | 可以 |
| 同名声明自动合并 | 支持，兼容的成员会合并 | 不支持重复声明 |
| 直接表示联合类型，如 `string \| number` | 不支持 | 支持 |

例如，同名接口可以分开补充属性：

```ts
interface UserInfo {
  name: string;
}

interface UserInfo {
  age: number;
}

// 合并后的 UserInfo 同时要求 name 和 age
const user: UserInfo = { name: "小林", age: 20 };
```

`type` 还可以命名联合类型、数组类型、函数类型等：

```ts
type Role = "user" | "assistant";
type Texts = string[];
```

`interface` 常用于对象形状与可扩展接口，`type` 常用于组合类型。两者不是“一个执行、另一个不执行”的区别：这两类类型声明本身都不创建运行时对象。

**定义类型与创建对象是两件事。** 也可以不先声明类型，直接创建对象，让 TypeScript 自动推断：

```ts
const block = { type: "text", text: "你好" };
```

这里的 `const block = {...}` 创建了实际对象。若希望明确检查它是否符合 `TextBlock` 的要求，可以写：

```ts
const block: TextBlock = { type: "text", text: "你好" };
```

这两段是可选写法。第一种写法中，`block.type` 通常会被推断为 `string`，因为对象属性之后仍可以修改；第二种通过类型标注明确要求它只能是 `"text"`。

还要区分代码中两个 `type` 的角色：

```ts
type TextBlock = { // type 是 TypeScript 关键字，用来定义类型别名
  type: "text";   // type 是对象属性名，属性值必须是字符串 "text"
  text: string;   // text 属性的值可以是任意字符串
};
```

还可以让一个接口扩展另一个接口：

```ts
interface Named {
  name: string;
}

interface NamedMessage extends Named {
  text: string;
}

const item: NamedMessage = { name: "小林", text: "你好" };
```

`NamedMessage` 既要求 `name`，也要求 `text`，但这不会自动创建任何实际对象。TypeScript 对这类对象主要看它具有哪些属性以及属性类型；一个值不需要通过“调用接口”才能符合接口。

### 4.5 联合 `|` 与交叉 `&`（重点）

联合表示“可能是其中一种”：

```ts
type Content = string | string[];
```

于是下面两个值都能作为 `Content`：

```ts
const one: Content = "你好";
const many: Content = ["你好", "谢谢"];
```

交叉表示“同时满足这些要求”：

```ts
type Named = { name: string };
type Timed = { timestamp: number };
type NamedAndTimed = Named & Timed;

const item: NamedAndTimed = { name: "消息", timestamp: 1000 };
```

它不是自动把两个对象合并起来；它只是要求一个值同时拥有相应形状。若把互相冲突的要求交叉，例如同一属性同时必须为字符串和数字，可能得到无法实际提供的类型。

### 4.6 数组、元组与联合的括号不能随便去掉（重点）

```ts
type TextsA = string[];            // 字符串数组
type TextsB = Array<string>;       // 同一种数组类型的另一种写法
type MixedItems = (string | number)[]; // 数组的元素可以是字符串或数字
type TextOrNumbers = string | number[]; // 一个字符串，或者一个数字数组
```

`[]` 紧跟谁，就表示谁的数组，因此联合外面的括号很重要。

元组则固定了位置的含义：

```ts
const pair: [string, number] = ["消息数", 3];
```

第一项必须是字符串，第二项必须是数字。`[string, number]` 不是任意长度的字符串或数字数组。

### 4.7 为什么要先检查类型，才能访问属性（重点）

假设输入既可能是字符串，也可能是字符串数组，而我们最终想得到一个字符串：

```ts
function joinContent(content: string | string[]): string {
  if (typeof content === "string") return content;
  return content.join("\n");
}
```

传入 `"你好"` 时，第一处分支直接返回；传入 `["你好", "谢谢"]` 时，走到数组的 `.join("\n")`，得到两行文本。字符串没有数组的 `.join()` 方法，所以必须先确定这一段处理的是数组。

这种根据条件缩小可能类型的过程叫**类型缩小**。常见依据包括 `typeof`、`Array.isArray`、`instanceof`、属性是否存在，以及某个字段的固定取值。

### 4.8 用一个固定字段，区分不同对象（重点）

教学示例：

```ts
type SmallEvent =
  | { type: "text"; text: string }
  | { type: "finished"; count: number };

function describe(event: SmallEvent): string {
  if (event.type === "text") {
    return event.text;
  }
  return `完成了 ${event.count} 条消息`;
}
```

输入 `{ type: "text", text: "你好" }` 时，只进入第一个分支。在这个分支中，程序与类型系统都知道可以使用 `text`。

输入 `{ type: "finished", count: 2 }` 时，走到后面，使用的是 `count`。这叫**可辨识联合**：用一个共同字段的不同固定值，区分不同的数据形状。Pi 的消息和事件大量采用这种组织方式。

### 4.9 `unknown`、`any`、`void`、`never` 各自表达什么（重点）

| 类型 | 自然语言理解 | 典型用途 |
| --- | --- | --- |
| `unknown` | 有一个值，但还不知道它是什么 | 接收外部输入，再检查 |
| `any` | 暂时放弃这部分类型约束 | 某些通用接口或兼容位置；容易漏掉错误 |
| `void` | 这次调用的返回值不供调用方使用 | 通知、记录、回调类型 |
| `never` | 这里不可能产生一个正常的值 | 永远抛错的函数、已排尽的联合分支 |

例如，对 `unknown` 要先检查：

```ts
function describeInput(input: unknown): string {
  if (typeof input === "string") return input;
  return "不是字符串";
}
```

`unknown` 并不意味着这个值无法使用，而是要求先证明你要做的操作适合它。`any` 则往往允许你直接操作，风险是把本应提前发现的问题留到运行时。

### 4.10 `as` 和后缀 `!` 是告诉类型检查器，不是修好数据（重点）

**`as string` 的作用是告诉 TypeScript：“这里你按字符串来检查，我认为它就是字符串。”** 这种写法叫**类型断言**，影响的是类型检查器如何理解这个表达式。

```ts
const value: unknown = "你好";
const text = value as string;
```

`value` 声明为 `unknown`，而 `text` 被视为 `string`，因此可以写 `text.toUpperCase()`。这个例子里，两个变量拿到的实际值都是 `"你好"`。

为什么有时需要这样告诉 TypeScript？先看没有断言的情况：

```ts
function shout(value: unknown) {
  return value.toUpperCase(); // 类型检查报错：value 的类型是 unknown
}
```

`unknown` 表示类型还不确定，TypeScript 无法确认它有没有字符串的 `toUpperCase()` 方法。加上断言后：

```ts
function shout(value: unknown) {
  return (value as string).toUpperCase(); // 类型检查通过
}
```

这相当于告诉类型检查器：“我认定它是字符串，允许我调用字符串方法。”**但这个判断对不对，由写代码的人负责：**

```ts
shout("hello"); // 得到 "HELLO"
shout(42);      // 运行时报错：数字没有 toUpperCase 方法
```

编译成 JavaScript 后，`as string` 会被去掉，实际执行的仍然是：

```js
function shout(value) {
  return value.toUpperCase();
}
```

所以，`as string` 没有检查实际值，也没有调用字符串转换。如果 `value` 实际是 `42`，写 `as string` 不会把它变成 `"42"`。下面三个写法分别做不同的事：

| 写法 | 作用 |
| --- | --- |
| `value as string` | 告诉类型检查器：把这个表达式当作字符串 |
| `String(value)` | 执行字符串转换，例如把 `42` 变成 `"42"` |
| `typeof value === "string"` | 在运行时检查它是不是字符串 |

**当你掌握的信息比 TypeScript 多，能确定某个值的类型时，可以用 `as` 表达这个判断。** 如果你自己也不确定，就应该先检查：

```ts
function shout(value: unknown) {
  if (typeof value === "string") {
    return value.toUpperCase(); // 检查过了，TypeScript 也知道它是字符串
  }
  return "这不是字符串";
}
```

这里通过实际检查缩小了类型，不需要再写 `as string`。

后缀 `!` 常表示：“我在这里确信它不是 `null` 或 `undefined`。”

```ts
function upper(text: string | undefined): string {
  return text!.toUpperCase();
}
```

若实际传入 `undefined`，仍然会出错。它与 `if (text !== undefined)` 不同，后者会真的在运行时检查。

还有一种返回类型写成 `value is SomeType` 的函数，叫类型谓词。它承诺返回 `true` 时可以按 `SomeType` 使用这个值；承诺是否可靠，仍要靠函数体真的完成相应检查。

类型缩小与断言的详细说明见 [类型缩小](https://www.typescriptlang.org/docs/handbook/2/narrowing.html) 和 [基本类型](https://www.typescriptlang.org/docs/handbook/2/everyday-types.html)。

## 5. 函数的各种写法：先找参数，再找返回值和函数体

### 5.1 从一个有输入、有输出的小函数开始

教学示例：

```ts
function greet(name: string): string {
  return `你好，${name}！`;
}

const result = greet("小林");
```

执行过程为：

```text
greet("小林")
      ↓ 把实参交给形参 name
name = "小林"
      ↓ 计算字符串
"你好，小林！"
      ↓ return
result = "你好，小林！"
```

定义中的 `name` 叫**形参**，调用时的 `"小林"` 叫**实参**。`return` 把结果送回调用发生的位置，不会自动把它显示在屏幕上；显示通常需要另一次调用，例如 `console.log(result)`。

### 5.2 “函数名后面的冒号”实际上标注了什么（重点）

```ts
function greet(name: string): string {
  return `你好，${name}！`;
}
```

把结构拆开：

```text
function greet    (name: string)    : string    { ... }
函数名称           参数列表          返回类型    真正执行的内容
```

参数内的冒号说明 `name` 的类型。参数列表右括号后面的冒号说明**整个函数调用得到什么类型的结果**。

返回类型写在前面，并不意味着先执行返回。实际执行顺序仍由函数体里的语句决定。

### 5.3 函数声明、函数表达式与箭头函数

下面三种写法，在这个只做字符串拼接的例子中完成相同工作：

```ts
function greet(name: string): string {
  return `你好，${name}！`;
}
```

```ts
const greet = function (name: string): string {
  return `你好，${name}！`;
};
```

```ts
const greet = (name: string): string => {
  return `你好，${name}！`;
};
```

第一种直接声明函数。第二种创建一个函数值，再把它交给 `greet`。第三种也创建函数值，但使用 `=>` 表示函数体的开始，叫**箭头函数**。

箭头函数不是大小比较符号。`>=` 是“大于等于”，`=>` 是另一种语法。

这些写法在所有场景下并不完全等价，例如箭头函数不会建立自己的 `this`；这里先比较它们共同的输入与输出。

### 5.4 箭头右侧是表达式时，可以不写 `return`

```ts
const greet = (name: string) => `你好，${name}！`;
```

等价于下面这个带函数体的版本：

```ts
const greet = (name: string) => {
  return `你好，${name}！`;
};
```

区别在于箭头右边是什么：

| 箭头右边 | 读法 |
| --- | --- |
| 一个表达式 | 计算表达式，并把结果返回 |
| `{ ... }` 语句块 | 进入函数体，是否返回值要看 `return` |

```ts
const a = (value: number) => value + 1;
const b = (value: number) => { value + 1; };
```

`a(2)` 得到 `3`。`b(2)` 虽然计算过 `2 + 1`，但没有返回它，调用结果是 `undefined`。

### 5.5 为什么返回对象时，会出现 `=> ({ ... })`

```ts
const makeBlock = (text: string) => ({ type: "text", text });
```

外层圆括号告诉解析器：这里的大括号是**对象表达式**，不是函数体。

也可以写得更展开：

```ts
const makeBlock = (text: string) => {
  return { type: "text", text };
};
```

因此：

```text
(text: string)     =>     ({ type: "text", text })
输入参数                   创建并返回一个对象
```

圆括号本身没有制造“另一层特殊函数”。它只是让里面的内容按表达式解释。

### 5.6 一个参数为什么有时没有括号

```ts
const double = (x: number) => x * 2;
const numbers = [1, 2, 3];
const doubled = numbers.map(x => x * 2);
```

`map` 会把数组元素逐个交给这个函数，因此每次都有一个具体数字作为 `x`。第二个箭头函数只有一个没有显式类型标注的简单参数，所以可以省掉参数外面的圆括号。TypeScript 从 `numbers` 推断 `x` 是数字。

如果没有参数、有多个参数，或参数上带类型标注，就需要括号：

```ts
() => 1
(a: number, b: number) => a + b
(x: number) => x * 2
```

这三行展示函数表达式的形式；写进实际程序时，通常会赋给变量或作为其他函数的参数。

### 5.7 对象方法为什么没有 `function`

```ts
const printer = {
  print(text: string): void {
    console.log(text);
  },
};

printer.print("你好");
```

`print(...) { ... }` 是对象中的方法简写。它也有参数、返回类型和函数体。

在这个例子里，也可以写成函数属性：

```ts
const printer = {
  print: (text: string): void => {
    console.log(text);
  },
};
```

后一种先用属性冒号把名字 `print` 与函数值关联起来。两种写法都能被调用，但涉及 `this` 时，要继续区分普通方法与箭头函数。

### 5.8 同一行里为什么会有两个箭头（重点）

```ts
const format: (text: string) => string = (text) => `[${text}]`;
```

先用等号分开：

```text
左边：const format: (text: string) => string
                    └── 对函数形状的要求 ──┘

右边：(text) => `[${text}]`
       └── 真正创建的函数 ──┘
```

左边的箭头属于**函数类型**：接收字符串，返回字符串。它没有函数体，不会执行。

右边的箭头属于**箭头函数表达式**：真正规定收到参数后怎样拼接文本。

也可以先给这种函数类型取名字：

```ts
type Formatter = (text: string) => string;
const format: Formatter = (text) => `[${text}]`;
```

这会把复杂定义缩短，但实际要求没有改变。

### 5.9 方法签名与函数属性签名（重点）

下面两种接口都在描述一个可调用的 `format` 成员：

```ts
interface PrinterA {
  format(text: string): string;
}

interface PrinterB {
  format: (text: string) => string;
}
```

它们都没有真正的函数体。第一种是方法签名，第二种是函数属性签名。阅读功能时可以先理解它们相同的输入输出要求；更细的函数兼容规则存在区别，不应认为所有类型场景下都可以无条件互换。

### 5.10 可选参数、默认参数与必需的空位置（重点）

这里重点看参数后的 `?` 和 `string | undefined`。默认参数 `prefix = "你好"` 本身是 JavaScript 写法。

```ts
function greet(name: string, prefix?: string): string {
  return `${prefix ?? "你好"}，${name}！`;
}
```

`prefix?` 表示调用时可以省略它：

```ts
greet("小林");          // "你好，小林！"
greet("小林", "欢迎");  // "欢迎，小林！"
```

默认参数则把取默认值的动作直接写在参数列表中：

```ts
function greet(name: string, prefix = "你好"): string {
  return `${prefix}，${name}！`;
}
```

省略参数或传入 `undefined` 会使用默认值；传入空字符串不会。

再看：

```ts
function greet(name: string, prefix: string | undefined): string {
  return `${prefix ?? "你好"}，${name}！`;
}
```

这里的第二个参数没有 `?`，类型调用要求仍有这个位置。可以传 `undefined`，但不能因此把它视为一个可省略参数。

### 5.11 剩余参数：`...texts: string[]`

```ts
function joinTexts(...texts: string[]): string {
  return texts.join(" / ");
}

joinTexts("你好", "谢谢", "再见");
```

调用时传入三个参数，函数内部收到一个数组：

```text
texts = ["你好", "谢谢", "再见"]
返回   "你好 / 谢谢 / 再见"
```

如果已有数组，又想拆成多个参数传入：

```ts
const texts = ["你好", "谢谢"];
joinTexts(...texts);
```

定义处的三个点负责“收集”，调用处的三个点负责“展开”。

### 5.12 参数里直接解构，为什么括号突然很多（重点）

这里重点看解构后面追加的对象类型。解构这个动作本身是 JavaScript 写法。

```ts
function formatMessage(
  { text, prefix = ">" }: { text: string; prefix?: string },
): string {
  return `${prefix} ${text}`;
}

formatMessage({ text: "你好" }); // "> 你好"
```

把参数单独拿出来：

```text
{ text, prefix = ">" }     :     { text: string; prefix?: string }
从实参对象中取出两个属性           说明整个实参对象的类型
```

这个函数接收的是**一个对象参数**，不是两个独立参数。

若写成 `function f({ text: string }) { ... }`，其中的 `string` 会被解释为解构出来的新变量名，而不是类型。对象解构里的属性改名与外层类型标注，一定要分开看。

### 5.13 返回值、`void` 与“忽略返回值”（重点）

没有 `return`，或只写 `return;` 的普通函数，运行时会得到 `undefined`。

但函数**类型**写成 `() => void`，重点是“调用方不使用其返回结果”，不保证实际实现从未产生其他值：

```ts
const values: string[] = [];
const add: (text: string) => void = (text) => values.push(text);
```

数组 `push` 实际会返回新长度；这里类型约定让调用方把返回值忽略。它与显式写函数自身的返回类型后，又返回一个数字的写法不同：

```ts
function notify(): void {
  console.log("有新消息");
  // return 3; // 与这里声明的 void 返回类型不符
}
```

Pi 的取消订阅函数正好会用到“实际产生布尔值，但对外不使用这个返回值”的情况。[函数返回类型中的 void](https://www.typescriptlang.org/docs/handbook/2/functions.html#return-type-void)

JavaScript 能在某些位置自动补分号，但阅读时不要把“换行”一律当成语句边界。例如 `return` 后紧跟换行，可能先结束返回语句：

```ts
function wrong() {
  return
  { text: "你好" };
}
```

这个函数返回 `undefined`。希望返回对象时，要把对象放在 `return` 后同一行开始，或使用括号把表达式包起来。


### 5.14 同名函数出现好几行：函数重载（重点）

Pi 的 `prompt` 有两种公开调用形状，下面保留签名，省略实现体：

Pi 源码：[packages/agent/src/agent.ts](../pi-master/packages/agent/src/agent.ts#L332)

```ts
async prompt(message: AgentMessage | AgentMessage[]): Promise<void>;
async prompt(input: string, images?: ImageContent[]): Promise<void>;
async prompt(input: string | AgentMessage | AgentMessage[], images?: ImageContent[]): Promise<void> {
  // ... 实现体省略
}
```

先看前两行：

```text
第一种：传一条消息，或消息数组。
第二种：传字符串，还可以附图片数组。
```

第三行才开始真正实现。它要处理前面支持的输入形式，内部再根据实际输入分支。

这不是运行时同时存在三个独立的 `prompt` 实现。前面的声明让类型检查知道允许怎样调用，后面的一个函数体负责真实执行。

### 5.15 函数套在调用里面，先算哪一个

```ts
const trim = (text: string) => text.trim();
const wrap = (text: string) => `[${text}]`;
const result = wrap(trim(" 你好 "));
```

先算内层调用，把它的返回值作为外层的实参：

```text
trim(" 你好 ") → "你好"
wrap("你好")   → "[你好]"
result         → "[你好]"
```

它与“把函数本身当参数传进去”不同。`wrap(trim(...))` 传进去的是 `trim` 的返回值；只有直接传 `trim` 这个函数值，接收方才有机会决定以后何时调用它。

参数列表、调用列表或对象属性末尾还可能有一个逗号，例如 `fn(a, b,)`。这种尾逗号不代表多传了一个空参数，更多是方便多行排版。

## 6. 函数作为数据：参数、回调、嵌套与闭包

### 6.1 `format` 与 `format("你好")` 是两种东西

```ts
const format = (text: string) => `[${text}]`;

const a = format;
const b = format("你好");
```

结果可以这样读：

```text
a 保存的是函数本身，还能在之后调用。
b 保存的是这一次调用的返回值，也就是 "[你好]"。
```

因此：

```ts
a("谢谢"); // "[谢谢]"
```

源码中的很多复杂写法，都源于一个事实：**函数也是值，可以保存、传给别人、放进对象或数组，也可以作为结果返回。**

### 6.2 函数当参数：把“怎样处理”一起传进去

```ts
function deliver(text: string, handler: (text: string) => void): void {
  handler(text);
}

function printText(text: string): void {
  console.log(text);
}

deliver("你好", printText);
```

按时间展开：

```text
调用 deliver
  ↓
text 接到 "你好"
handler 接到 printText 这个函数
  ↓
deliver 内部执行 handler(text)
  ↓
实际进入 printText("你好")
  ↓
显示 "你好"
```

参数名 `handler` 不具有魔法。之所以调用了 `printText`，是因为 `handler` 这个名字现在保存着它。

下面这种写法完全不同：

```ts
// deliver("你好", printText("你好"));
```

它会先调用 `printText`，再试图把其返回值当成 `handler` 传进去。例子中的 `printText` 没有返回可调用的函数，因此不符合参数要求。

### 6.3 把函数直接写在调用的圆括号里面

```ts
deliver("你好", (text) => {
  console.log(`[收到] ${text}`);
});
```

外层圆括号属于 `deliver(...)` 的调用。逗号后的部分是它的第二个参数，只不过这个参数恰好是一个完整函数。

把它拆出来，就没有嵌套的视觉负担：

```ts
const handler = (text: string) => {
  console.log(`[收到] ${text}`);
};

deliver("你好", handler);
```

“函数写在另一个函数的参数位置”并不表示里面那个函数马上自行执行。它什么时候被调用，要看接收方怎样使用它。

### 6.4 回调不等于异步

前面的 `deliver` 收到函数后，立刻执行 `handler(text)`。这就是一个**同步调用的回调**。

换成登记的写法：

```ts
let savedHandler: ((text: string) => void) | undefined;

function register(handler: (text: string) => void): void {
  savedHandler = handler;
}

function notify(text: string): void {
  savedHandler?.(text);
}

register((text) => console.log(text));
```

到这里，只是把函数保存起来，还没有显示任何文本。后来执行：

```ts
notify("你好");
```

才会真正调用它。

**“回调”描述的是把函数交给别的代码调用这种关系；同步还是异步，取决于它何时被调用、做什么工作。**

### 6.5 函数返回函数 （重点！！！）

```ts
function makeFormatter(prefix: string): (text: string) => string {
  return (text) => `${prefix}${text}`;
}

const format = makeFormatter("[用户] ");
const result = format("你好");
```

这里有两次调用：

```text
第 1 次：makeFormatter("[用户] ")
         返回一个新函数，交给 format。

第 2 次：format("你好")
         返回字符串 "[用户] 你好"。
```

第一次调用没有 `text` 这个实际输入，还不能完成最终拼接。它先准备好一个记住 `prefix` 的函数。

也可以连续写：

```ts
makeFormatter("[用户] ")("你好");
```

先算左边调用，拿到函数；再用右边一对圆括号调用这个返回的函数。连续两对圆括号并不是同一次调用收到了两组参数。

### 6.6 外层已经结束，内层为什么还记得变量

`makeFormatter` 返回后，后续函数仍能访问它创建时所在环境中的 `prefix`。这种函数与其可访问的外部变量之间的联系，叫**闭包**。

闭包可以记住变化中的状态，而不只是一次复制的数值：

```ts
function makeCounter(): () => number {
  let count = 0;
  return () => {
    count += 1;
    return count;
  };
}

const next = makeCounter();
next(); // 1
next(); // 2
```

两次 `next()` 使用的是同一个外层 `count`。再调用一次 `makeCounter()`，会建立另一个独立的 `count`。

```text
makeCounter() 第一次 → count A → nextA()
makeCounter() 第二次 → count B → nextB()
```

### 6.7 函数里面定义函数，与调用函数不是一回事

```ts
function outer(): void {
  const inner = () => console.log("内层执行");
  console.log("外层执行");
  inner();
}
```

调用 `outer()` 后的顺序为：

```text
创建 inner 函数值
显示“外层执行”
执行 inner()
显示“内层执行”
```

如果删掉最后的 `inner()`，内部定义仍然存在，但不会因为被定义了就自动执行。

普通 `function` 声明通常可以在同一作用域中、声明位置之前调用；`const` 保存的函数表达式则不能在执行到初始化之前访问。理解“这里是在声明，还是已经在调用”，比单纯记住括号数量更有用。

回调中的 `return` 也只结束这一次回调，不会越过它直接结束外层函数。比如 `forEach` 的回调返回，不等于整次遍历自动停止。

### 6.8 立即执行函数：末尾那一对 `()` 才是在调用

```ts
const result = (() => {
  const text = "你好";
  return `[${text}]`;
})();
```

由内向外看：

```text
() => { ... }   创建函数
( ... )         把整个函数表达式包起来
( ... )()       立刻调用它
```

最终 `result` 得到 `"[你好]"`。这种写法常叫**立即执行函数表达式**，也常缩写为 IIFE。带上 `async` 后，返回值会变成 Promise，时间顺序仍需单独分析。

## 7. 数组和容器：把一批消息交给函数处理

### 7.1 `map`：每一项分别变成什么

```ts
const texts = ["你好", "谢谢"];
const blocks = texts.map((text) => ({ type: "text", text }));
```

两次回调分别是：

```text
text = "你好" → 返回 { type: "text", text: "你好" }
text = "谢谢" → 返回 { type: "text", text: "谢谢" }
```

`map` 收集返回值，得到新数组：

```ts
[
  { type: "text", text: "你好" },
  { type: "text", text: "谢谢" },
]
```

`map` 不会自动替回调补上缺失的 `return`。若回调带大括号却没有返回值，结果数组的相应项会是 `undefined`。

### 7.2 `filter`：每一项要不要留下

Pi 默认把 Agent 消息转换成模型消息时，使用下面的过滤：

Pi 源码：[packages/agent/src/agent.ts](../pi-master/packages/agent/src/agent.ts#L40)

```ts
function defaultConvertToLlm(messages: AgentMessage[]): Message[] {
  return messages.filter(
    (message) => message.role === "user" || message.role === "assistant" || message.role === "toolResult",
  );
}
```

括号里的函数逐个接收 `message`，检查其角色。条件为真，原元素留下；条件为假，原元素不进入结果数组。

这里的三个 `===` 是三个比较，两个 `||` 把它们连成“满足任意一个就可以”。`filter` 会返回一个新数组，但保留下来的对象仍是原来的对象，并没有深拷贝消息。

### 7.3 几个方法只差一点，返回结果却不同

| 方法 | 回调负责什么 | 整个调用返回什么 |
| --- | --- | --- |
| `map` | 给出每项转换后的值 | 新数组 |
| `filter` | 判断这一项是否保留 | 通过条件的元素组成的新数组 |
| `find` | 判断是否命中 | 第一个命中的元素，或 `undefined` |
| `some` | 判断是否命中 | 是否至少有一项命中 |
| `every` | 判断是否满足 | 是否所有项都满足 |
| `forEach` | 对每项执行动作 | `undefined`，不收集回调结果 |
| `reduce` | 把当前项合入累计结果 | 最终累计结果 |

教学示例：

```ts
const texts = ["你好", "", "谢谢"];

texts.filter((text) => text.length > 0); // ["你好", "谢谢"]
texts.find((text) => text.length === 0); // ""
texts.some((text) => text.length === 0); // true
texts.every((text) => text.length > 0);  // false
```

注意 `find` 找到的可能是 `""`、`0` 等有效值。若用 `if (found)` 判断“有没有找到”，可能把找到的假值误当成未找到。

### 7.4 `reduce`：把隐含的累计过程写出来

```ts
const lengths = [2, 3, 1];
const total = lengths.reduce((sum, length) => sum + length, 0);
```

最后的 `0` 是初始累计值：

| 这一轮 | `sum` | `length` | 回调返回的新 `sum` |
| --- | ---: | ---: | ---: |
| 1 | 0 | 2 | 2 |
| 2 | 2 | 3 | 5 |
| 3 | 5 | 1 | 6 |

最终返回 `6`。相当于：

```ts
let total = 0;
for (const length of lengths) {
  total = total + length;
}
```

读不惯多层箭头时，可以先把这类调用展开成循环。没有初始值时，`reduce` 会采用另一套起点规则；对空数组又没有初始值的情况还会抛错，因此读到最后一个参数时不要忽略它。

### 7.5 哪些数组方法会改动原数组

| 常见方法 | 主要效果 |
| --- | --- |
| `push`、`pop`、`shift`、`unshift` | 改动原数组的头部或尾部 |
| `splice` | 在原数组中删除、插入或替换 |
| `sort`、`reverse` | 改动原数组的排列 |
| `slice` | 返回选定部分的新数组 |
| `map`、`filter` | 返回新数组 |

即使方法返回了新数组，回调如果主动修改元素对象，仍可能影响原对象。因此要把“是否复制数组”与“是否修改元素对象”分开。

### 7.6 `Set`：把同一个值放一次

```ts
const ids = new Set<string>();
ids.add("call-1");
ids.add("call-1");
ids.add("call-2");

ids.size;          // 2
ids.has("call-1"); // true
ids.delete("call-1"); // true：这一次确实删掉了
```

`Set` 常用来记录“不重复的一组值”。它也能保存函数，所以适合保存监听器。同一个函数值重复加入只保留一份；两个分别创建、代码看起来相同的箭头函数，仍是两个不同函数值。

### 7.7 `Map`：按键查找值

```ts
const counts = new Map<string, number>();
counts.set("user", 2);
counts.set("assistant", 1);

counts.get("user");    // 2
counts.get("missing"); // undefined
```

这里 `<string, number>` 在说明键和值的类型。对象属性访问是 `obj.key`，`Map` 通过 `.get(key)`、`.set(key, value)` 操作，不能因为它们都能表达对应关系就混用。

### 7.8 对象也能拆成一组键值对

```ts
const counts = { user: 2, assistant: 1 };

for (const [role, count] of Object.entries(counts)) {
  console.log(role, count);
}
```

`Object.entries(counts)` 提供一组类似 `["user", 2]` 的键值对；每轮用数组解构，把它拆给 `role` 与 `count`。

`Object.keys` 取自有可枚举字符串键，`Object.values` 取对应的值。它们是对象的现成操作接口，并不是新的函数定义语法。

## 8. `import` 与 `export`：名字怎样跨文件传递

### 8.1 `export` 让其他文件能够使用这个名字

教学假设：有一个 `text.ts` 文件：

```ts
export function format(text: string): string {
  return `[${text}]`;
}
```

另一个文件中：

```ts
import { format } from "./text.js";
const result = format("你好");
```

先让 `format` 这个导出名字在当前文件可用，再通过 `format(...)` 调用它。**导出函数不等于执行函数。** 不过，加载模块时会执行该模块必要的顶层代码，所以也不能把导入理解成“绝不发生任何动作”。

Pi 的 `.ts` 源文件中会见到以 `.js` 结尾的相对导入。这类写法指向运行时的模块路径；阅读源码时通常对应同名的 `.ts` 文件，不必把它理解为缺少另一份手写的 `.js`。

### 8.2 花括号导入、改名与整体导入

```ts
import { format } from "./text.js";
import { format as formatText } from "./text.js";
import * as textTools from "./text.js";
```

分别读作：

```text
导入名为 format 的成员。
导入 format，在当前文件中叫 formatText。
把这个模块的导出成员放到 textTools 命名空间对象下使用。
```

第三种对应调用 `textTools.format("你好")`。导入语句中的花括号属于模块语法，不能把它完全当作普通对象解构。

### 8.3 默认导出为什么没有花括号

教学示例：

```ts
export default function format(text: string): string {
  return `[${text}]`;
}
```

另一文件可以写：

```ts
import formatText from "./text.js";
```

默认导出的接收名字可以由导入方选择。一个模块可以有一个默认导出，也可以同时有多个具名导出。

Pi 的扩展示例使用这种形式：

Pi 源码：[packages/coding-agent/examples/extensions/hello.ts](../pi-master/packages/coding-agent/examples/extensions/hello.ts#L26)

```ts
export default function (pi: ExtensionAPI) {
  pi.registerTool(helloTool);
}
```

这里导出的是一个接收 `pi` 的函数。等加载方真正调用它时，函数体才执行 `pi.registerTool(helloTool)`。`export default` 本身不会替加载方传入 `pi`。

### 8.4 `import type`：这里只需要类型说明（重点）

Pi 中可以看到：

Pi 源码：[packages/agent/src/agent.ts](../pi-master/packages/agent/src/agent.ts#L1)

```ts
import {
  type ImageContent,
  type Message,
  type Model,
  type SimpleStreamOptions,
  streamSimple,
  type TextContent,
  type ThinkingBudgets,
  type Transport,
} from "@mariozechner/pi-ai";
```

其中 `streamSimple` 是运行时可以调用的值；`TextContent` 等前面带 `type` 的名字，只用于类型说明。

也可以整行写：

```ts
import type { TextContent } from "@mariozechner/pi-ai";
```

类型导入不会提供一个能在运行时使用的对象。因此，不能写 `new TextContent()`，也不能指望打印出“接口对象”。[TypeScript 模块说明](https://www.typescriptlang.org/docs/handbook/2/modules.html)

### 8.5 `export ... from ...`：把其他文件的名字再向外提供

Pi 的入口会写：

Pi 源码：[packages/agent/src/index.ts](../pi-master/packages/agent/src/index.ts#L2)

```ts
export * from "./agent.js";
export * from "./agent-loop.js";
export * from "./proxy.js";
export * from "./types.js";
```

它把相应模块的具名导出重新提供出去，让调用方不必知道每个实现文件的位置。`export *` 不会顺带重新导出那个模块的默认导出。

具名重导出也很常见：

```ts
export { format } from "./text.js";
export type { TextContent } from "./types.js";
```

`index.ts` 只是常用的入口文件名。真正产生导出关系的是这些语句，不是文件名字本身有特殊执行能力。

## 9. 类、对象与 `this`：同一份定义怎样产生不同实例

### 9.1 `class` 描述一类对象，`new` 创建其中一个

教学示例：

```ts
class MessageBox {
  private messages: string[] = [];

  add(text: string): void {
    this.messages.push(text);
  }

  get count(): number {
    return this.messages.length;
  }
}

const first = new MessageBox();
const second = new MessageBox();
first.add("你好");
```

现在：

```text
first.count  = 1
second.count = 0
```

两次 `new MessageBox()` 创建了两个实例，各自有一份 `messages`。`class` 中的 `add` 是方法，`messages` 是成员字段；这些并不是只能存在于类型说明中的内容。

### 9.2 `this` 是哪一个对象

在 `first.add("你好")` 这样的调用中，方法里的 `this` 指向 `first`，因此修改的是 `first` 的消息数组。

```text
first.add("你好")
    ↓
this = first
    ↓
first 的 messages 增加一项
```

`this` 不是“随便找最近一个变量”，也不总是全局对象。普通方法的接收者与调用方式有关。

### 9.3 把方法单独传走，接收者可能丢失

```ts
const add = first.add;
// add("你好"); // 不能假定这里的 this 仍是 first
```

这里仅取出了函数，没有同时保留 `first.add(...)` 这种调用形式。常见解决方式有：

```ts
const addA = first.add.bind(first);
const addB = (text: string) => first.add(text);
```

`bind` 产生一个绑定了接收者的新函数；后一种则让回调内部仍然通过 `first.add(...)` 调用。

### 9.4 类中的箭头字段，为什么常被用作回调

```ts
class MessagePrinter {
  prefix = "[用户] ";

  print = (text: string): void => {
    console.log(this.prefix + text);
  };
}

const printer = new MessagePrinter();
const callback = printer.print;
callback("你好");
```

箭头函数沿用创建位置的 `this`，不会因 `callback(...)` 这种调用而重新选择接收者。这个实例创建 `print` 时，它关联的就是该实例。

Pi 的会话层也使用箭头字段作为事件处理函数，再把这个函数交给 Agent 订阅。重点是：**函数被传到另一处，不等于它所访问的外层变量和 `this` 都消失了。** [箭头函数与 this](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Functions/Arrow_functions)

### 9.5 `constructor` 与参数属性（重点）

这里重点看 `constructor(public mode: QueueMode)` 这种参数属性。普通的 `constructor` 本身是 JavaScript 写法。

```ts
class NamedBox {
  name: string;

  constructor(name: string) {
    this.name = name;
  }
}
```

创建 `new NamedBox("实验")` 时，构造函数收到 `"实验"`，把它保存到实例字段。

TypeScript 允许缩写为：

```ts
class NamedBox {
  constructor(public name: string) {}
}
```

参数前的 `public` 让它同时成为实例字段。这不只是普通的参数类型标注，还包含创建并赋值成员字段的作用。

Pi 的消息队列也采用这种写法：

Pi 源码：[packages/agent/src/agent.ts](../pi-master/packages/agent/src/agent.ts#L131)

```ts
constructor(public mode: QueueMode) {}
```

这里的 `QueueMode` 表示 `"all"` 或 `"one-at-a-time"` 两种取值。构造函数收到一个模式，同时把它保存为实例的 `mode` 字段；后续就可以读取 `this.mode`。

### 9.6 `public`、`private`、`protected`、`readonly`（重点）

这里重点看 TypeScript 的访问限制和只读标记。表里的 `#value` 则是 JavaScript 自己的私有字段。

| 写法 | 主要含义 |
| --- | --- |
| `public value` | 可以通过实例的公开接口访问；成员通常默认公开 |
| `private value` | TypeScript 限制在声明它的类内部访问 |
| `protected value` | 类内部及其派生类可以访问 |
| `readonly value` | 限制通过这一声明重新赋值 |
| `#value` | JavaScript 的私有字段，运行时也有私有访问限制 |

例如：

```ts
class Listeners {
  private readonly callbacks = new Set<() => void>();

  add(callback: () => void): void {
    this.callbacks.add(callback);
  }
}
```

`readonly callbacks` 不允许给这个字段重新换一个集合，但仍允许调用已有集合的 `.add()`。同样，接口里的 `readonly` 不等于自动调用 `Object.freeze`，也不保证没有其他引用能修改底层对象。

Pi 的 `readonly pendingToolCalls: ReadonlySet<string>` 则在类型接口上只向使用者提供读取集合的能力。**只读接口、字段不能改绑、对象彻底不可变，是不同层次的约束。**

### 9.7 `get` 与 `set`：看起来读属性，实际会执行方法

```ts
class Title {
  private value = "未命名";

  get text(): string {
    return this.value;
  }

  set text(next: string) {
    this.value = next.trim();
  }
}

const title = new Title();
title.text = "  实验记录  ";
title.text; // "实验记录"
```

赋值 `title.text = ...` 时触发 setter；读取 `title.text` 时触发 getter。不需要写成 `title.text()`。

Pi 的 `agent.state` 也是 getter 暴露的状态。看到属性读取时，不能仅凭没有圆括号就断言内部绝不会执行代码。

### 9.8 `extends`、`super` 与 `implements`（重点）

这里重点看 `implements`、`override` 和 `abstract` 等 TypeScript 约束。类继承中的 `extends` 和 `super` 本身也是 JavaScript 写法。

```ts
interface Printable {
  print(text: string): void;
}

class Printer implements Printable {
  print(text: string): void {
    console.log(text);
  }
}

class TaggedPrinter extends Printer {
  override print(text: string): void {
    super.print(`[记录] ${text}`);
  }
}
```

分别看：

- `implements Printable`：检查这个类是否满足接口，不会替你生成 `print` 的实现。
- `extends Printer`：建立类的继承关系，可以复用父类方法。
- `super.print(...)`：调用父类的相应方法。
- `override`：明确说明正在覆盖父类成员，让类型检查帮助发现写错名字等问题。

派生类如果写了自己的构造函数，需要先正确调用 `super(...)`，再访问 `this`。`abstract class` 和 `abstract` 成员则用于声明需要派生类补齐的部分，抽象类不能直接作为普通具体类来实例化。

### 9.9 `static` 与实例成员

```ts
class Counter {
  static description = "消息计数器";
  count = 0;
}
```

`Counter.description` 放在类这一侧；`new Counter().count` 放在某个实例这一侧。看到 `ClassName.method()` 时，可以留意它是否是静态方法，不必先假设存在一个隐藏实例。

## 10. 泛型：先留出类型位置，再代入具体类型

### 10.1 为什么不把所有结果都写成 `unknown`（重点）

教学示例：

```ts
function first<T>(values: T[]): T | undefined {
  return values[0];
}
```

先把 `T` 当成一个待填的类型位置：

```text
传入 string[] → T 取 string → 返回 string 或 undefined
传入 number[] → T 取 number → 返回 number 或 undefined
```

于是：

```ts
first(["你好", "谢谢"]); // 推断结果类型为 string | undefined
first([2, 3]);            // 推断结果类型为 number | undefined
```

泛型的作用是保留输入与输出之间的类型联系。它不是运行时额外传入的一个普通值，也不等于“没有类型”。

### 10.2 `<T>` 与函数调用的 `(...)`（重点）

```ts
first<string>(["你好"]);
```

两组括号负责不同事情：

```text
<string>      指定类型参数
(["你好"])    提供实际数据参数并调用
```

通常可以通过实际参数推断 `T`，不必每次手动填写。接口、类和类型别名也可以留出这样的类型位置。

### 10.3 Pi 的 `AgentToolResult<T>`（重点）

Pi 用下面的泛型接口描述工具结果，删去注释后为：

Pi 源码：[packages/agent/src/types.ts](../pi-master/packages/agent/src/types.ts#L291)

```ts
export interface AgentToolResult<T> {

  content: (TextContent | ImageContent)[];

  details: T;

  terminate?: boolean;
}
```

`content` 是给后续处理使用的文本或图片内容；`details` 则可以携带某个工具自己的结构。

假设我们编写一个计数工具，教学中把详情类型定成：

```ts
type CountDetails = { count: number };
```

代入后，可以提供：

```ts
const result: AgentToolResult<CountDetails> = {
  content: [{ type: "text", text: "一共 2 条消息" }],
  details: { count: 2 },
};
```

在这里，`T` 已经被具体的 `CountDetails` 替代，因此 `details.count` 应当是数字。

这里的 `AgentToolResult<T>` 要求提供详情类型。另一些定义允许省略类型参数，例如下面这个教学接口：

```ts
interface Box<T = unknown> {
  data: T;
}
```

`T = unknown` 是**默认类型参数**：使用 `Box` 时不填写 `T`，就采用默认类型。它不会给 `data` 自动填入一个实际值。Pi 的 `AgentToolUpdateCallback<T = any>` 也使用了这种默认类型参数写法。

### 10.4 `T extends ...` 是约束，不是这里又创建了一个子类（重点！！！）

```ts
function readText<T extends { text: string }>(value: T): string {
  return value.text;
}
```

这要求填给 `T` 的类型至少满足 `{ text: string }`，因此函数可以读取 `.text`。

```ts
readText({ text: "你好", timestamp: 1000 }); // 可以包含更多属性
// readText({ timestamp: 1000 });          // 缺少 text
```

`extends` 在类声明里可以表示继承，在接口里可以扩展形状，在泛型参数里表示约束，后面的条件类型中还会用它作类型关系判断。**相同单词要放回完整语句中解释。**

### 10.5 多个类型参数、默认关系与嵌套（重点）

Pi 的事件流类从这一行开始：

Pi 源码：[packages/ai/src/utils/event-stream.ts](../pi-master/packages/ai/src/utils/event-stream.ts#L4)

```ts
export class EventStream<T, R = T> implements AsyncIterable<T> {
  // ... 类成员省略
}
```

逐项拆开：

```text
T         每次交出的事件是什么类型
R         最后完成时的结果是什么类型
R = T     若不指定 R，就默认与 T 相同
AsyncIterable<T>  这个对象可逐项提供 T 类型的值
```

例如，一个流可能逐次交出“文本片段事件”，最后提供“完整助手消息”。事件类型与最终结果类型没有必要相同。

看到嵌套尖括号时，由内向外替换即可：

```text
Array<AgentToolResult<CountDetails>>
      └ 含 CountDetails 的工具结果 ┘
└ 由这种工具结果组成的数组 ┘
```

连续的 `>>` 在这种类型位置通常只是接连关掉两层泛型括号，不是在执行右移运算。

## 11. 异步：现在返回了什么，之后又完成了什么

### 11.1 普通返回值与 Promise 返回值

```ts
function getText(): string {
  return "你好";
}

async function getTextLater(): Promise<string> {
  return "你好";
}
```

两次调用拿到的东西不同：

```text
getText()       → 字符串 "你好"
getTextLater()  → 一个 Promise，成功结果是字符串 "你好"
```

`Promise<string>` 不是字符串本身，它代表一项将以字符串成功完成、或以错误失败的工作。

`async` 函数即使直接 `return "你好"`，对外仍会交回 Promise。`Promise<void>` 则表示可以等待它结束，但没有需要使用的业务结果。

### 11.2 `new Promise` 里面的函数，什么时候执行（重点！！！）

用“开始做饭，做好后通知”来看执行顺序。`setTimeout(函数, 1000)` 表示安排这个函数在约 1 秒后执行，用来模拟做饭需要时间。

```ts
console.log("1. 准备下单");

const meal = new Promise<string>((resolve) => {
  console.log("2. 厨房开始做饭");

  setTimeout(() => {
    console.log("4. 饭做好了");
    resolve("蛋炒饭");
  }, 1000);
});

meal.then((food) => {
  console.log("5. 拿到：" + food);
});

console.log("3. 我先做别的事");
```

输出顺序是：

```text
1. 准备下单
2. 厨房开始做饭
3. 我先做别的事
（约 1 秒后）
4. 饭做好了
5. 拿到：蛋炒饭
```

逐步看这段代码：

1. 先输出 `1. 准备下单`。
2. 执行 `new Promise(...)` 时，传进去的 `(resolve) => {...}` **立即执行**，所以马上输出 `2. 厨房开始做饭`。这个函数叫 Promise 的**执行器**，其中的 `resolve` 是 Promise 构造器提供的函数。
3. 执行器调用 `setTimeout`，安排稍后的动作，然后执行结束。此时还没有调用 `resolve`，所以 `meal` 仍在等待结果。`meal` 是 Promise，不是蛋炒饭这个字符串。
4. `meal.then(...)` 登记“成功拿到结果后做什么”，并立即返回一个新的 Promise，此时不会执行里面的 `console.log`。程序继续向下，输出 `3. 我先做别的事`。
5. 约 1 秒后，定时器里的函数执行，输出 `4. 饭做好了`，再调用 `resolve("蛋炒饭")`，把 `meal` 的成功结果确定为 `"蛋炒饭"`。
6. 定时器里的函数执行完后，`.then` 登记的处理函数获得机会执行。参数 `food` 收到 `"蛋炒饭"`，于是输出 `5. 拿到：蛋炒饭`。

这段代码有三层函数，要分别看它们什么时候执行：

| 传进去的函数 | 什么时候执行 |
| --- | --- |
| 传给 `new Promise` 的 `(resolve) => { ... }` | 创建 Promise 时立即执行 |
| 传给 `setTimeout` 的 `() => { ... }` | 定时器到期且程序有机会处理时执行 |
| 传给 `meal.then` 的 `(food) => { ... }` | Promise 成功后，等当前同步代码执行完再执行 |

**`new Promise` 不会自动把里面的代码推迟执行。** 本例中，延后的动作是由 `setTimeout` 安排的；Promise 负责表示结果还没到，以及结果到来后通知已登记的处理函数。

**`.then` 是 Promise 对象上的方法，调用 `.then()` 会立即返回一个新的 Promise，但传给它的处理函数会稍后执行。** 沿用前面的 `meal`，把登记处理函数的代码展开来看：

```ts
const next = meal.then((food) => {
  console.log("拿到：" + food);
});

console.log("继续往下执行");
```

这里要分清两个函数：

- **`.then()` 方法**：登记处理函数，立即返回一个新的 Promise，赋给 `next`。`next` 表示后续处理的结果，不是食物字符串。
- **`(food) => { ... }` 处理函数**：等 `meal` 成功后，再安排执行。它的参数 `food` 才会收到 `meal` 的成功结果 `"蛋炒饭"`。

也就是说，**`meal` 和 `next` 都是 Promise，而且是两个不同的 Promise**：`meal` 表示“饭做好”的结果，`next` 表示“后续处理”的结果。因此，准确说法是“`.then()` 的返回值也是一个 Promise”。`next` 还可以继续调用 `.then(...)`，这就是 Promise 能连续串接处理步骤的原因。

所以，上面这段代码会先输出 `继续往下执行`，之后才输出 `拿到：蛋炒饭`。**即使 `meal` 在调用 `.then()` 前就已经成功，处理函数也不会当场执行，而是等当前同步代码执行完。**

可以把 `.then(处理函数)` 理解成：“登记成功后要做的事，登记完就继续往下走。”

**如果没有 `setTimeout`，直接调用 `resolve`，会怎样？** 假设饭已经做好，可以马上提供结果：

```ts
console.log("1. 准备取饭");

const readyMeal = new Promise<string>((resolve) => {
  console.log("2. 饭已经做好");
  resolve("蛋炒饭");
  console.log("3. resolve 后的代码继续执行");
});

const nextStep = readyMeal.then((food) => {
  console.log("5. 拿到：" + food);
});

console.log("4. then 已返回，继续往下执行");
```

输出顺序是：

```text
1. 准备取饭
2. 饭已经做好
3. resolve 后的代码继续执行
4. then 已返回，继续往下执行
5. 拿到：蛋炒饭
```

执行过程是：

1. 先输出 `1`，然后 `new Promise` 立即执行传进去的函数，输出 `2`。
2. `resolve("蛋炒饭")` 立即把 `readyMeal` 的成功结果确定为 `"蛋炒饭"`。它不会结束当前函数，所以接着输出 `3`。
3. 执行器结束，`new Promise` 返回，赋值给 `readyMeal`。此时它已经成功。
4. 调用 `readyMeal.then(...)`，安排稍后执行处理函数，并立即返回另一个 Promise，赋给 `nextStep`。程序继续向下输出 `4`。
5. 当前同步代码执行完，处理函数才执行，输出 `5. 拿到：蛋炒饭`。

**没有定时器，`.then` 的处理函数仍然稍后执行。** 它通过“微任务”机制安排执行，不需要靠 `setTimeout` 延后。这里先记住顺序：当前同步代码先执行完，再执行已安排的 `.then` 处理函数。

再看 Pi 的事件流：它不使用定时器，而是在构造器中先保存 `resolve`，等后续事件带来最终结果时再调用它。

Pi 源码：[packages/ai/src/utils/event-stream.ts](../pi-master/packages/ai/src/utils/event-stream.ts#L11)

```ts
constructor(
  private isComplete: (event: T) => boolean,
  private extractResult: (event: T) => R,
) {
  this.finalResultPromise = new Promise((resolve) => {
    this.resolveFinalResult = resolve;
  });
}
```

这里的 `T` 表示逐项事件类型，`R` 表示最终结果类型；`isComplete` 与 `extractResult` 是传入并保存的两个函数。创建 Promise 时，执行器立即执行 `this.resolveFinalResult = resolve`，把完成函数保存到字段中。**保存函数不等于调用函数**，所以此时 Promise 仍在等待；后续调用 `this.resolveFinalResult(最终结果)` 时，才提供成功结果。

相应字段这样声明：

Pi 源码：[packages/ai/src/utils/event-stream.ts](../pi-master/packages/ai/src/utils/event-stream.ts#L9)

```ts
private resolveFinalResult!: (result: R) => void;
```

字段名后面的 `!` 叫确定赋值断言，是向类型检查器承诺“使用前会把它赋好值”。它不会生成一个完成函数，也不会替代构造器里的实际赋值。这里并不是逻辑取反。

**都是“把函数传进去”，`new Promise` 的执行器与 `.then` 的处理函数却不是在同一时刻调用。** [Promise 构造器](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/Promise)

### 11.3 `resolve` 和 `reject` 不是普通的变量赋值

Promise 构造器还会提供 `reject`：

```ts
const pending = new Promise<string>((resolve, reject) => {
  const allowed = false;
  if (!allowed) {
    reject(new Error("不允许处理"));
    return;
  }
  resolve("你好");
});
```

`resolve` 让 Promise 朝成功完成的方向确定结果，`reject` 让它失败。对于这里的字符串值，调用 `resolve("你好")` 后成功结果就是这个字符串；若传入另一个 Promise，则会跟随它的最终状态。

`resolve` 或 `reject` 不等于 `return`，不会自动结束当前函数，所以示例中失败后另外写了 `return`。一个 Promise 的结果一旦确定，也不会因之后又调用一次完成函数而变成另一份结果。

### 11.4 `await` 等待的是表达式得到的结果

**在同一个 `async` 函数里，逐步调用异步操作并 `await`，可以理解为串行执行：前一步成功完成，再往下执行下一步。** `async / await` 让异步流程也能按从上到下的顺序来阅读。

```ts
async function printText(): Promise<void> {
  const text = await getTextLater();
  console.log(text);
}
```

先执行 `getTextLater()`，得到 Promise，再等待它。成功后，`await` 表达式的值是 `"你好"`，交给变量 `text`。

若该 Promise 失败，就会在 `await` 所在位置抛出错误。

```text
调用 getTextLater()
   ↓ 立刻取得 Promise
await 等它完成
   ↓ 成功时取出结果
text = "你好"
   ↓
继续执行 console.log
```

再看连续等待两个操作的例子。假设 `cookRice()` 和 `fryEgg()` 分别表示煮饭和炒蛋，都返回 Promise：

```ts
async function prepareMeal(): Promise<void> {
  await cookRice(); // 先开始煮饭，等煮饭完成
  await fryEgg();   // 然后才开始炒蛋，等炒蛋完成
  console.log("可以吃饭了");
}
```

这段函数内部的成功执行顺序是：

```text
调用 cookRice() → 等煮饭完成
                         ↓
调用 fryEgg()  → 等炒蛋完成
                         ↓
输出“可以吃饭了”
```

这里 `fryEgg()` 要等 `cookRice()` 成功完成后才会被调用，这就是这段代码的**串行执行**。`async` 允许在函数中使用 `await`，每个 `await` 则让当前函数等到这一步有结果后再继续；只写 `async`，或者调用操作时没有写 `await`，不会自动获得这样的等待顺序。

**串行描述的是这个函数内部各步骤的顺序。** 等待暂停的是当前异步函数的后续部分，程序中的其他代码仍可以运行；它不会让整个程序停止，也不等于自动启动另一个线程。[async 函数](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/async_function)

### 11.5 一段能按顺序推演的异步代码

**调用 `work()` 后，执行流程会在 `await` 处切回调用方，让调用方继续输出 `C`。** 从表现上看，像是两条流程交错推进；但本例没有新开线程，也没有一个 Promise 在后台执行代码。Promise 是表示完成状态和结果的对象，代码执行到哪里，要看函数调用和 `await` 的位置。

```ts
console.log("A");

async function work(): Promise<void> {
  console.log("B");                 // 调用 work() 时立即执行
  await Promise.resolve("你好");    // 暂停 work 的后续部分
  console.log("D");                 // 稍后恢复执行
}

const pending = work(); // 先进入 work，执行到 await，再拿到它返回的 Promise
console.log("C");      // 调用方没有 await work()，所以继续往下执行
```

预期显示顺序为：

```text
A
B
C
D
```

逐步看程序执行到哪里：

1. 最外层先输出 `A`。此时 `work` 只是定义好了，还没有执行。
2. 执行 `work()`，立即进入函数体，输出 `B`。这一段仍然在当前执行过程中运行。
3. 执行 `Promise.resolve("你好")`，得到一个已经成功、结果为 `"你好"` 的 Promise。遇到 `await`，`work` 仍会暂停后续部分，把输出 `D` 的步骤安排为稍后的微任务。
4. 调用方拿到 `work()` 返回的 Promise，赋给 `pending`。此时 `work` 还没执行完，所以 `pending` 仍在等待。它和 `Promise.resolve("你好")` 创建的 Promise 是两个不同的对象。
5. 调用方没有写 `await work()`，因此继续输出 `C`，最外层同步代码执行完毕。
6. 接着处理已安排的微任务，恢复 `work`，输出 `D`。函数正常结束后，`pending` 才成功完成。由于 `work` 没有返回业务值，它的成功结果是 `undefined`。

可以把执行路线画成：

```text
最外层：输出 A → 调用 work()
                      ↓
work 内：         输出 B → 遇到 await，暂停后续步骤
                                      ↓
最外层：拿到 pending → 输出 C → 同步代码结束
                                      ↓
work 内：                       恢复执行 → 输出 D → 结束
```

**这里是同一条执行线程先后处理不同片段：先执行 `work` 的前半段，再执行调用方，最后恢复 `work` 的后半段。** `work` 暂停期间，本例没有另一条线程同时执行 `D`。

这也对应上一节的“串行”：`work` 内部始终是先输出 `B`，等待后再输出 `D`；调用方是否等待 `work`，取决于调用方有没有写 `await`。

如果希望调用方也等 `work` 完成后再输出 `C`，可以把原例最后两行替换为：

```ts
async function main(): Promise<void> {
  await work();     // 等 work 整个执行完
  console.log("C");
}

main();
```

此时整个例子的输出顺序就变成 `A → B → D → C`。`main` 内部也按“等前一步完成，再执行下一步”的顺序推进。

若一个 `async` 函数在第一次 `await` 前做了很长的同步计算，这段计算仍然会占用当前执行过程。仅仅加上 `async`，不会让它自动变成后台线程。

### 11.6 `.then`、`.catch` 与 `.finally` 都会继续形成 Promise 链

```ts
const lengthPromise = getTextLater()
  .then((text) => text.length)
  .catch(() => 0)
  .finally(() => {
    console.log("处理结束");
  });
```

成功路径：先得到 `"你好"`，再得到长度 `2`，最后做收尾。若前面的调用或 `.then` 处理失败，`.catch` 可以返回 `0`，让后续链恢复为成功结果 `0`。

每一环都会返回新的 Promise。`.then` 和 `.catch` 的回调若返回 Promise，它们产生的新 Promise 会跟随这个结果；回调若抛错，新 Promise 会失败。

`.finally` 也会等待清理函数返回的 Promise，但清理正常完成时仍保留此前的业务结果或错误，不会拿清理函数的成功值替换它。若清理本身抛错或返回失败的 Promise，则会影响后续状态。

### 11.7 `try / catch / finally`：把失败也放进执行顺序

Pi 的运行生命周期中有下面这段：

Pi 源码：[packages/agent/src/agent.ts](../pi-master/packages/agent/src/agent.ts#L479)

```ts
try {
  await executor(abortController.signal);
} catch (error) {
  await this.handleRunFailure(error, abortController.signal.aborted);
} finally {
  this.finishRun();
}
```

先尝试执行并等待 `executor(...)`。它正常完成，就进入 `finally`；它失败，则进入 `catch`，等待错误处理，再执行 `finally`。

三个关键词的职责分别是：

```text
try       尝试执行
catch     处理这里捕获到的错误
finally   离开这段流程前做收尾
```

`finally` 中通常不应随意 `return`，因为这可能覆盖之前准备返回的值或原本应该继续抛出的错误。

处理未知错误时，Pi 还会使用：

```ts
error instanceof Error ? error.message : String(error)
```

意思是：若确实是 `Error` 实例，读取其 `.message`；否则把这个值转成字符串。`throw` 可以抛出不同种类的值，不能未经判断就假设捕获的对象总有 `.message`。

### 11.8 为什么少写一个 `return`，等待关系就变了

假设 `saveText` 是一个返回 `Promise<void>` 的教学函数：

```ts
const first = (text: string) => saveText(text);

const second = (text: string) => {
  saveText(text);
};
```

第一种把 `saveText` 返回的 Promise 原样交回调用方；第二种启动保存工作，但函数自己返回 `undefined`。

因此：

```text
await first("你好")   → 等待 saveText 对应的 Promise
await second("你好")  → 拿到 undefined，不能据此等待保存完成
```

可以把第二种改成显式返回，或在异步函数内部等待：

```ts
const third = (text: string) => {
  return saveText(text);
};

const fourth = async (text: string) => {
  await saveText(text);
};
```

读回调时，**不仅要找 `async`，还要追踪它交回了哪个 Promise，以及谁继续等待这个 Promise。**

### 11.9 Pi 中等待监听器的实际调用位置

Pi 的 Agent 从登记的集合里逐个取监听器，再调用并等待：

Pi 源码：[packages/agent/src/agent.ts](../pi-master/packages/agent/src/agent.ts#L564)

```ts
for (const listener of this.listeners) {
  await listener(event, signal);
}
```

所以一个监听器返回的 Promise，会影响下一个监听器何时开始。

但不能因此推断所有名为 `emit` 的方法都会等待。Pi 的会话层还有这种调用：

Pi 源码：[packages/coding-agent/src/core/agent-session.ts](../pi-master/packages/coding-agent/src/core/agent-session.ts#L440)

```ts
private _emit(event: AgentSessionEvent): void {
  for (const l of this._eventListeners) {
    l(event);
  }
}
```

这里仅调用 `l(event)`，没有等待返回的 Promise。回调内部若启动异步工作，那项工作可能仍在继续。

这两段的区别就在实际调用语句，不在“监听器”“事件”“回调”这些名称上。

### 11.10 顺序等待与一批等待

假设 `runA`、`runB` 是两个会启动工作的异步函数。顺序写：

```ts
const a = await runA();
const b = await runB();
```

先启动 A，等 A 结束，再启动 B。

改成：

```ts
const [a, b] = await Promise.all([runA(), runB()]);
```

先求值数组中的两个函数调用，让两项工作都有机会推进，再等待这一组 Promise。结果数组保持输入顺序，不按完成先后排列。

`Promise.all([runA, runB])` 不会自动调用这两个函数。真正启动动作的是这里的 `runA()` 和 `runB()`，不是 `Promise.all` 猜出函数用途后替你执行。

某一项失败时，`Promise.all` 会失败，但不会自动取消其他任务。[Promise.all](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Promise/all)

### 11.11 为什么 `forEach(async ...)` 不等于逐项等待

教学中的易错写法：

```ts
texts.forEach(async (text) => {
  await saveText(text);
});
```

每个回调自己会等待保存，但 `forEach` 不收集它们返回的 Promise，也不会等所有回调结束。给整个 `forEach(...)` 外面加一个 `await`，也不会改变这一点。

需要逐项完成：

```ts
for (const text of texts) {
  await saveText(text);
}
```

需要先启动一组，再统一等待：

```ts
await Promise.all(texts.map((text) => saveText(text)));
```

这几段应放在可使用 `await` 的异步环境中。选择哪一种，取决于任务是否允许并发。[forEach 的异步边界](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/forEach)

### 11.12 `void task()`：执行以后丢弃结果，不是禁止执行

Pi 的流式接口中会出现这一类结构，下面保留真实调用与返回，删去注释：

Pi 源码：[packages/agent/src/agent-loop.ts](../pi-master/packages/agent/src/agent-loop.ts#L40)

```ts
void runAgentLoop(
  prompts,
  context,
  config,
  async (event) => {
    stream.push(event);
  },
  signal,
  streamFn,
).then((messages) => {
  stream.end(messages);
});

return stream;
```

`runAgentLoop(...)` 已经被调用。外层不等待整个循环结束，就把 `stream` 交给调用方；循环成功后，`.then` 中的函数再获得最终消息。

开头的 `void` 是 JavaScript 运算符，意思是计算右侧表达式后丢弃其结果。它不是返回类型标注，也不会自动捕获失败，更不会取消工作。

### 11.13 立即执行的异步函数

下面是 Pi 模型服务代码中的结构简图，省略了请求和事件处理的细节：

```ts
const stream = new AssistantMessageEventStream();

(async () => {
  // ... 发起请求，等待响应，把事件交给 stream ...
})();

return stream;
```

它对应 [Pi 的流式响应实现](../pi-master/packages/ai/src/providers/openai-responses.ts#L62)。

内部的 `async` 函数被末尾的 `()` 立刻调用，会先执行到需要让出的等待位置；外部随后可以返回 `stream`。**外层返回 stream，与内部异步工作完成，是两个不同的时间点。**

### 11.14 `AbortSignal` 是协作取消机制，不是一种新的语法

`AbortController`、`AbortSignal` 是 API 提供的对象和类型名，不是像 `return` 那样的语言关键字。调用 `controller.abort()` 发出取消信号；真正执行的函数需要观察这个信号，或把它传给支持取消的 API，才会相应停止。

同样，`Promise` 本身不保证有一个“强制停止所有内部工作”的方法。读到 `signal?: AbortSignal`，先理解为“可以额外传入一个取消信号”，再看函数体怎样使用它。

## 12. 迭代与生成器：一次交出一个值

### 12.1 普通函数返回一次，生成器可以分多次交出内容

教学示例：

```ts
function* words() {
  yield "你";
  yield "好";
}

const iterator = words();
```

这里的 `*` 表示生成器。调用 `words()` 只得到迭代器，函数体此时尚未开始执行。第一次调用 `.next()`，才从函数体开头运行到第一个 `yield`。

```ts
iterator.next(); // { value: "你", done: false }
iterator.next(); // { value: "好", done: false }
iterator.next(); // { value: undefined, done: true }
```

每次 `.next()` 推进到下一次 `yield`。`yield` 交出一个值并暂停，`return` 则结束这次迭代。

### 12.2 `for...of` 帮我们反复取下一项

```ts
for (const word of words()) {
  console.log(word);
}
```

可以把它理解为不断向迭代器取下一项，直到 `done` 为真。数组、`Set`、`Map` 等也支持这种可迭代约定。

普通 `for...of` 消费的是每次 `yield` 的值。若生成器最后 `return` 另一个值，这个终止结果不会自动成为循环中的又一个元素。

### 12.3 下一项还没准备好，就需要异步迭代

```ts
async function* wordsLater() {
  yield "你";
  await Promise.resolve();
  yield "好";
}
```

它同时使用了两种能力：

```text
async   可以等待异步结果
*       可以通过 yield 分次交出值
```

消费时可以写：

```ts
async function consume(): Promise<void> {
  for await (const word of wordsLater()) {
    console.log(word);
  }
}
```

`for await` 每次等待下一项出现，再执行循环体。它不要求先收齐全部数据，也不代表所有循环体会自动并发。

### 12.4 `[Symbol.asyncIterator]`：这一串方括号是方法名

Pi 的事件流提供下面的方法：

Pi 源码：[packages/ai/src/utils/event-stream.ts](../pi-master/packages/ai/src/utils/event-stream.ts#L49)

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

先只看第一行：

```text
async * [Symbol.asyncIterator] () : AsyncIterator<T>
等待   生成器     方法名       参数    返回类型
```

`Symbol.asyncIterator` 是异步迭代约定所使用的特殊键；方括号把这个键的值作为方法名。它不是在这里读取数组下标，也不是类型里的 `T[K]`。

这个方法让事件流可以被 `for await...of` 逐项读取。

### 12.5 没有新事件时，这段代码在等谁

把方法体按三种情况分开：

| 条件 | 做什么 |
| --- | --- |
| 队列里有事件 | 取出一项，用 `yield` 交给消费者 |
| 队列为空，而且流已结束 | `return`，结束迭代 |
| 队列为空，流还没结束 | 创建 Promise，把它的完成函数存起来，等待后来有人通知 |

最复杂的是这一行：

```ts
const result = await new Promise<IteratorResult<T>>(
  (resolve) => this.waiting.push(resolve),
);
```

注意 `push(resolve)`：保存的是完成函数，尚未调用它。以后有事件被放入流时，Pi 会取出等待者并调用：

Pi 源码：[packages/ai/src/utils/event-stream.ts](../pi-master/packages/ai/src/utils/event-stream.ts#L29)

```ts
const waiter = this.waiting.shift();
if (waiter) {
  waiter({ value: event, done: false });
} else {
  this.queue.push(event);
}
```

把两处连起来：

```text
消费者要下一项，但队列为空
  ↓
把 Promise 的 resolve 保存到 waiting
  ↓
当前异步迭代器等待
  ↓
后来 push 收到一个 event
  ↓
取出保存的 waiter，调用 waiter({ value: event, done: false })
  ↓
Promise 完成，await 恢复
  ↓
yield result.value
  ↓
消费者的 for await 收到 event
```

这些语句并不是写在一起就同时发生。**保存函数、真正调用函数、Promise 完成、等待者恢复、事件交给消费者，是几个相互连接的时刻。**

### 12.6 流中的事件与最终结果，是两种读取方式

事件流还能返回最终结果的 Promise：

Pi 源码：[packages/ai/src/utils/event-stream.ts](../pi-master/packages/ai/src/utils/event-stream.ts#L63)

```ts
result(): Promise<R> {
  return this.finalResultPromise;
}
```

这个方法没有在里面重新启动工作，它只是交回保存的 Promise。逐项读取事件适合观察过程；等待 `result()` 可以拿到这条流约定的最终结果 `R`，助手消息流的结果是一条完整消息，其他流也可以使用别的结果类型。

最终结果已经可用，也不等于消费者已经逐条处理完所有事件。看到两个接口时，要分别问“此刻会得到下一条事件，还是约定的整体结果”。

## 13. 类型运算：把已有类型拆开，再组合成新类型

这一组写法主要出现在类型定义和复杂接口中。它们通常不改变运行时数据，阅读时可以像代入公式一样，每次只处理一层。

### 13.1 `typeof` 在运行位置与类型位置做不同的事（重点）

运行时：

```ts
const options = { title: "实验", retries: 2 };
const kind = typeof options; // 字符串 "object"
```

类型位置：

```ts
type Options = typeof options;
```

这时得到的是 `options` 的类型形状，类似：

```ts
type Options = { title: string; retries: number };
```

后一个 `typeof` 不会生成字符串 `"object"`。判断依据是它出现在一个实际表达式中，还是类型声明里。

### 13.2 `keyof T`：取出类型中的属性名（重点）

```ts
type Options = { title: string; retries: number };
type OptionKey = keyof Options;
```

在这个例子中，`OptionKey` 相当于：

```ts
type OptionKey = "title" | "retries";
```

这是属性名组成的类型，不是运行时的数组。若想真正得到对象的键数组，要使用 `Object.keys(options)` 等实际调用。

### 13.3 `T[K]`：取字段的类型，不是取字段的值（重点）

```ts
type Title = Options["title"];    // string
type Retry = Options["retries"];  // number
type Values = Options[keyof Options]; // string | number
```

把最后一行拆开：

```text
keyof Options                    → "title" | "retries"
Options["title" | "retries"]     → string | number
```

还可以提取数组元素类型：

```ts
type Texts = string[];
type Text = Texts[number]; // string
```

类型中的 `[number]` 表示“这个数组里数值索引对应的元素类型”，不是读取下标恰好名为 `number` 的元素。

### 13.4 `Record`、`Partial`、`Pick`、`Omit`（重点）

先看一个完整类型：

```ts
type Options = {
  title: string;
  retries: number;
  enabled: boolean;
};
```

这些工具分别改写类型形状：

| 类型工具 | 在这个例子中的含义 |
| --- | --- |
| `Partial<Options>` | 三个属性都可以省略 |
| `Required<Partial<Options>>` | 把这些可选属性要求为必需 |
| `Pick<Options, "title" \| "enabled">` | 只挑出两个属性的类型 |
| `Omit<Options, "retries">` | 去掉 `retries` 属性的类型要求 |
| `Readonly<Options>` | 通过这一类型使用时，属性不可重新赋值 |
| `Record<"user" \| "assistant", number>` | 要求这两个键各对应一个数字 |

例如：

```ts
const patch: Partial<Options> = { enabled: false };
const counts: Record<"user" | "assistant", number> = {
  user: 2,
  assistant: 1,
};
```

`Partial<Options>` 不会真的修改 `Options`，也不会自动合并配置；`Pick` 不会真的从某个对象中复制属性。它们操作的是类型说明。[常用类型工具](https://www.typescriptlang.org/docs/handbook/utility-types.html)

### 13.5 两层工具嵌套时，从里面向外读（重点）

Pi 的一个配置字段写成：

Pi 源码：[packages/ai/src/types.ts](../pi-master/packages/ai/src/types.ts#L274)

```ts
reasoningEffortMap?: Partial<Record<ThinkingLevel, string>>;
```

先看里面：

```text
Record<ThinkingLevel, string>
每一种 ThinkingLevel 对应一个字符串
```

再看外面：

```text
Partial<...>
允许只提供其中一部分键
```

最外侧的 `reasoningEffortMap?` 还表示：整个字段也可以不提供。

教学上可以想成只提供其中两项映射：

```ts
const mapping = { low: "low", high: "high" };
```

这是解释类型形状的小例子；它没有自动执行模型设置，也没有因为存在一份映射就发出请求。

### 13.6 `Parameters`、`ReturnType` 与 `Awaited`（重点）

这三个工具都根据已有类型推导出新类型。先用一句话区分：

| 工具 | 从哪里取 | 得到什么 |
| --- | --- | --- |
| `Parameters<函数类型>` | 函数的参数列表 | 描述整组参数的元组类型 |
| `ReturnType<函数类型>` | 函数的返回类型 | 调用这个函数会得到什么类型 |
| `Awaited<类型>` | Promise 等类型 | 成功等待后会得到什么类型 |

先看一个计算总价的普通函数：

```ts
function calculateTotal(price: number, quantity: number): number {
  return price * quantity;
}

const total = calculateTotal(10, 3); // 实际调用，得到 30
```

**`Parameters`：取出“调用时要传哪些参数”的类型。**

```ts
type TotalArgs = Parameters<typeof calculateTotal>;

// 推导结果相当于：
// type TotalArgs = [price: number, quantity: number];

const args: TotalArgs = [10, 3]; // 两个位置都必须是数字
// const wrong: TotalArgs = [10, "3"]; // 报错：第二项应是数字

const totalFromArgs = calculateTotal(...args); // 相当于 calculateTotal(10, 3)，得到 30
```

逐层读 `Parameters<typeof calculateTotal>`：

```text
typeof calculateTotal
  ↓ 在类型位置取得函数的类型
(price: number, quantity: number) => number
  ↓ Parameters<...> 取出参数列表的类型
[price: number, quantity: number]
```

这里得到的是一个元组类型，说明“第一项是单价，第二项是数量，都是数字”。它没有读取某次调用传入的 `10` 和 `3`；`args` 中的实际值是我们自己填写的。`...args` 则把元组中的两项展开为两个实参。

**`ReturnType`：取出“调用后返回什么”的类型。**

```ts
type TotalResult = ReturnType<typeof calculateTotal>;

// 推导结果相当于：
// type TotalResult = number;

const result: TotalResult = calculateTotal(10, 3); // 30
// const wrong: TotalResult = "30"; // 报错：应是数字
```

`Parameters` 和 `ReturnType` 都没有调用函数。使用它们的好处是不用重复手写参数类型、返回类型：以后原函数的类型改变，推导出来的类型也会随之改变。

**`Awaited<T>` 表示：“如果等待一个 `T` 类型的值，成功后会拿到什么类型？”** 它不是在认定“这个类型是异步类型”，也不是把普通类型变成异步类型。

```ts
type TextTask = Promise<string>;     // Promise 的成功结果是字符串
type TextValue = Awaited<TextTask>;  // string：等待成功后拿到的类型
```

这两个类型描述的是不同阶段：

- `Promise<string>`：调用后先拿到的 Promise 对象的类型。
- `Awaited<Promise<string>>`：成功等待后拿到的结果类型，也就是 `string`。

普通类型也可以传给 `Awaited`，结果仍然是原类型：

```ts
type PlainNumber = Awaited<number>; // number，不会变成 Promise<number>
```

所以不要把 `Awaited` 理解成“标记为异步”，而要理解成“推导等待后的结果类型”。换成异步函数来看：

```ts
async function getTotal(): Promise<number> {
  return 30;
}

type TotalPromise = ReturnType<typeof getTotal>; // Promise<number>
type FinalTotal = Awaited<TotalPromise>;         // number
```

注意这两层结果不同：

```text
调用 getTotal()          → 先拿到 Promise<number>
成功等待这个 Promise    → 再拿到 number，实际值是 30
```

对应到实际代码：

```ts
async function printTotal(): Promise<void> {
  const pending: TotalPromise = getTotal(); // 调用函数，拿到 Promise
  const total: FinalTotal = await pending;  // 真正等待，拿到数字 30
  console.log(total);
}
```

**大写的 `Awaited<...>` 只推导类型，小写的 `await` 才是函数执行时的等待操作。** 单独写 `type FinalTotal = Awaited<...>` 不会发起工作，也不会等待任何实际任务。

再回看 Pi 的 `Parameters<typeof streamSimple>` 和 `ReturnType<typeof streamSimple>`，就可以分别理解成“沿用 `streamSimple` 的参数列表类型”和“沿用它的返回类型”。

### 13.7 `Extract` 与 `Exclude`：筛选联合类型（重点）

**联合类型用 `|` 列出几种可能；`Extract` 保留符合条件的成员，`Exclude` 去掉符合条件的成员。** 它们处理的是类型，不会遍历实际数组。

```ts
type Role = "user" | "assistant" | "toolResult";
type HumanRole = Extract<Role, "user">;  // "user"
type OtherRole = Exclude<Role, "user">;  // "assistant" | "toolResult"
```

可以把它理解为逐项筛选：

| `Role` 中的成员 | `Extract<Role, "user">` | `Exclude<Role, "user">` |
| --- | --- | --- |
| `"user"` | 保留 | 去掉 |
| `"assistant"` | 去掉 | 保留 |
| `"toolResult"` | 去掉 | 保留 |

得到的新类型，可以像普通类型一样约束变量：

```ts
const human: HumanRole = "user";
// const wrongHuman: HumanRole = "assistant"; // 报错

const other1: OtherRole = "assistant";
const other2: OtherRole = "toolResult";
// const wrongOther: OtherRole = "user"; // 报错
```

条件也可以包括多个成员：

```ts
type ChatRole = Extract<Role, "user" | "assistant">;
// 结果："user" | "assistant"
```

**筛选对象联合时，保留的是整个对象类型。** 例如，内容块有三种可能：

```ts
type DemoContent =
  | { type: "text"; text: string }
  | { type: "thinking"; thinking: string }
  | { type: "toolCall"; name: string; arguments: { city: string } };

type DemoToolCall = Extract<DemoContent, { type: "toolCall" }>;

// 结果相当于保留完整的这一支：
// type DemoToolCall = {
//   type: "toolCall";
//   name: string;
//   arguments: { city: string };
// };
```

第二个参数 `{ type: "toolCall" }` 表示筛选条件：这一支必须具有 `type` 属性，而且值只能是 `"toolCall"`。工具调用这一支符合条件，所以连同 `name`、`arguments` 等属性一起保留；另外两支被排除。

实际使用时，仍然需要自己创建对象：

```ts
const call: DemoToolCall = {
  type: "toolCall",
  name: "getWeather",
  arguments: { city: "北京" },
};

console.log(call.name);           // "getWeather"
console.log(call.arguments.city); // "北京"

// const wrong: DemoToolCall = { type: "text", text: "你好" }; // 报错：不是工具调用
```

如果使用 `Exclude`，结果恰好保留另外两支：

```ts
type DemoNonToolContent = Exclude<DemoContent, { type: "toolCall" }>;
// 结果：
// { type: "text"; text: string }
// | { type: "thinking"; thinking: string }
```

再看 Pi 中的实际写法，它在筛选前，先取出了内容块的联合类型：

Pi 源码：[packages/agent/src/types.ts](../pi-master/packages/agent/src/types.ts#L39)

```ts
export type AgentToolCall = Extract<AssistantMessage["content"][number], { type: "toolCall" }>;
```

逐层替换：

```text
AssistantMessage["content"]
  ↓ 取出助手消息的 content 类型
内容块数组
  ↓ 再用 [number] 取数组元素类型
TextContent | ThinkingContent | ToolCall
  ↓ Extract<..., { type: "toolCall" }>
保留 type 为 "toolCall" 的那一支
```

其中 `[number]` 表示“数组元素的类型”，不是读取数组某个下标的实际值；`Extract` 再从这些可能的元素类型中保留工具调用这一支。筛选规则和前面的 `DemoToolCall` 相同。

这整行没有遍历消息数组，也没有取出某一次真实工具调用，它只定义 `AgentToolCall` 这个类型名。对比上面的 `const call = {...}`：`type` 定义要求，`const` 才创建这里用来演示的实际对象。

### 13.8 `as const` 与 `satisfies`：保留具体形状，同时检查要求（重点）

教学示例：

```ts
const block = { type: "text" as const, text: "你好" };
```

`as const` 让这里的 `type` 保持特定字面量 `"text"`，避免仅被看作一般的 `string`。Pi 转换内容块时也有这种写法。

对整个字面量使用时：

```ts
const roles = ["user", "assistant"] as const;
```

TypeScript 会按只读元组理解它；但这不是在运行时自动冻结数组。

再看 `satisfies`：

```ts
const block = {
  type: "text",
  text: "你好",
} satisfies TextContent;
```

它检查表达式是否满足 `TextContent`，同时保留这个表达式自身更具体的类型信息，而不是简单把变量整体声明成目标类型。具体推断仍会受到上下文影响，所以也不能理解成“对推断完全没有影响”。

`as` 是类型断言，`satisfies` 是符合性检查；二者都不会在运行时把错误数据修好。[satisfies 说明](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-4-9.html#the-satisfies-operator)

### 13.9 条件类型：这次问号在类型里（重点）

教学示例：

```ts
type Label<T> = T extends string ? "text" : "other";

type A = Label<string>; // "text"
type B = Label<number>; // "other"
```

它判断的是类型关系，不会执行一个运行时 `if`。Pi 的模型接口中有下面的可选字段：

Pi 源码：[packages/ai/src/types.ts](../pi-master/packages/ai/src/types.ts#L412)

```ts
compat?: TApi extends "openai-completions"
  ? OpenAICompletionsCompat
  : TApi extends "openai-responses"
    ? OpenAIResponsesCompat
    : never;
```

先不要把两种问号混在一起：

```text
compat?                        整个字段可以不提供
TApi extends ... ? ... : ...   根据类型选择字段允许的类型
```

如果 API 类型满足第一种要求，就选择第一种兼容设置；否则继续判断第二种；都不满足时得到 `never`。

条件类型使用裸类型参数判断联合类型时，常会分别作用于各个成员，再把结果合起来。这属于更深入的类型规则，读这类接口时先抓住“条件针对类型，结果也是类型”。

### 13.10 `infer`：匹配成功后，给其中一部分类型起个临时名字（重点）

先把 `infer` 理解成：**“匹配一个类型结构，把其中某一部分的类型找出来，暂时起个名字。”**

例如，我们有两种“包装”，都用 `data` 属性装数据：

```ts
type TextPackage = { data: string };
type NumberPackage = { data: number };

const textPackage: TextPackage = { data: "你好" };
const numberPackage: NumberPackage = { data: 42 };
```

现在希望定义一个类型工具：给它包装的类型，它就告诉我们“里面的 `data` 是什么类型”。

```ts
type ReadData<T> = T extends { data: infer D } ? D : never;

type TextData = ReadData<TextPackage>;     // string
type NumberData = ReadData<NumberPackage>; // number
```

**`infer D` 的意思是：“这里的具体类型由 TypeScript 从传入类型中推导，先把它叫作 `D`。”** `D` 是类型的临时名字，可以换成其他名字；它不是存放 `"你好"` 或 `42` 的变量。

把这一行拆开读：

| 片段 | 含义 |
| --- | --- |
| `ReadData<T>` | 接收一个类型，暂时叫作 `T` |
| `T extends { data: infer D }` | 检查 `T` 能否匹配具有必需 `data` 属性的结构；匹配成功就把该属性的类型叫作 `D` |
| `? D` | 匹配成功，使用刚推导出的 `D` 作为结果类型 |
| `: never` | 匹配失败，这个工具没有可提供的结果类型 |

这里的 `extends` 用来判断类型是否符合结构；`? ... : ...` 是条件类型的两个分支，不是属性的可选标记。

例如 `ReadData<TextPackage>` 的推导过程是：

```text
输入的类型 T：{ data: string }
要匹配的结构：{ data: infer D }
                       ↑
               这个位置对应 string
                       ↓
               推导出 D = string
                       ↓
               选择 ? 后面的 D
                       ↓
               最终得到 string
```

所以，推导出的类型就能这样使用：

```ts
const text: TextData = "你好"; // TextData 就是 string
const count: NumberData = 42;  // NumberData 就是 number

// const wrong: TextData = 42; // 报错：数字不能赋给 string
```

如果传入的类型没有 `data` 属性，就匹配失败，走 `: never` 分支：

```ts
type MissingData = ReadData<{ message: string }>; // never
```

`never` 在这里表示没有可提供的结果类型，不是运行时返回了 `undefined`。整个推导过程也没有读取 `textPackage.data`，更没有创建或修改对象；**`infer` 提取的是属性的类型 `string`，实际读取 `textPackage.data` 才会得到值 `"你好"`。**

Pi 的模型类型中也使用了同样的思路：

Pi 源码：[packages/ai/src/models.ts](../pi-master/packages/ai/src/models.ts#L15)

```ts
type ModelApi<
  TProvider extends KnownProvider,
  TModelId extends keyof (typeof MODELS)[TProvider],
> = (typeof MODELS)[TProvider][TModelId] extends { api: infer TApi } ? (TApi extends Api ? TApi : never) : never;
```

其中 `{ api: infer TApi }` 和刚才的 `{ data: infer D }` 是同一个思路：刚才提取 `data` 属性的类型，这里提取 `api` 属性的类型，并暂时叫作 `TApi`。

这行很长，但步骤有限：先选中某个提供方、某个模型对应的类型；再看它能否匹配出 `api` 属性；把该属性的类型暂时叫作 `TApi`；最后通过 `TApi extends Api ? TApi : never` 检查这个类型是否符合允许的 API 类型。符合就保留，否则得到 `never`。

这个阶段的阅读目标是能区分每一层在处理什么，不必把它误认为模型调用流程。[条件类型与 infer](https://www.typescriptlang.org/docs/handbook/2/conditional-types.html)

### 13.11 映射类型：按已有属性名生成新形状（重点）

下面是补充教学例子，用来理解 `Partial` 一类工具：

```ts
type MakeOptional<T> = {
  [K in keyof T]?: T[K];
};
```

套进 `{ title: string; retries: number }`：

```text
keyof T       → "title" | "retries"
K 依次代表键   → 为每个键建立一个属性
T[K]          → 保留原属性的值类型
?             → 新属性可以省略
```

这里的 `in` 是类型生成语法，与运行时的 `"title" in obj` 不同。

Pi 里可以对照 [tui 的按键类型](../pi-master/packages/tui/src/keys.ts)：`[M in RemainingModifiers]` 就是映射类型。

另外，`-?` 可以移除可选标记，`-readonly` 可以移除只读标记；`[K in keyof T as ...]` 可以进一步改写键名。它们都是对类型形状的改写，不会遍历并修改实际对象。[映射类型](https://www.typescriptlang.org/docs/handbook/2/mapped-types.html)

### 13.12 空接口、声明合并与 `declare`（重点）

Pi 允许应用扩展自定义消息类型，因此有一个起初没有字段的接口，并在消息类型里引用它：

Pi 源码：[packages/agent/src/types.ts](../pi-master/packages/agent/src/types.ts#L246)

```ts
export interface CustomAgentMessages {
}

export type AgentMessage = Message | CustomAgentMessages[keyof CustomAgentMessages];
```

`keyof CustomAgentMessages` 先取扩展接口的键，再通过索引访问取出这些键对应的消息类型。接口还没有成员时，这部分不会凭空增加一种实际消息。

TypeScript 的接口声明可以在允许的位置合并；`declare module` 可以描述某个模块的类型补充。**增加类型声明不等于向运行中的 Agent 注册消息或监听器。** 真正的数据仍然需要由实际代码创建、保存和处理。

文件名以 `.d.ts` 结尾时，通常是在描述运行代码的类型接口，而不是提供相应运行实现。`declare function ...`、`declare const ...` 也常表达“这个东西由别处提供，我在这里说明它的类型”。

## 14. 回到 Pi：把长函数定义逐层拆开

### 14.1 第一段：一行里面，外层函数接收函数，再返回函数

现在读 Pi 的完整 `subscribe`：

Pi 源码：[packages/agent/src/agent.ts](../pi-master/packages/agent/src/agent.ts#L237)

```ts
subscribe(listener: (event: AgentEvent, signal: AbortSignal) => Promise<void> | void): () => void {
  this.listeners.add(listener);
  return () => this.listeners.delete(listener);
}
```

不要从左到右把所有符号一次背下来。先只保留最外层：

```text
subscribe(listener): 取消订阅函数
```

再拆 `listener` 的要求：

```text
输入：event 和 signal
结果：Promise<void> 或 void
含义：允许异步处理，也允许同步处理
```

再看 `subscribe` 自己的返回类型：

```text
() => void
不接收参数的函数；调用方不依赖它的返回值
```

最后读真正执行的两行：

```ts
this.listeners.add(listener);
return () => this.listeners.delete(listener);
```

调用 `subscribe(listener)` 当场做两件事：保存监听器；创建并返回一个取消函数。它没有当场执行 `delete`，因为 `delete` 位于返回的箭头函数体内。

教学调用，假定 `agent` 是已经创建的 Pi Agent：

```ts
const seen: string[] = [];

const stop = agent.subscribe((event) => {
  seen.push(event.type);
});
```

现在只是登记，所以 `seen` 仍为空。以后 Agent 运行并调用监听器时，事件类型才进入数组。再执行：

```ts
stop();
```

才会从集合中删除这次登记的函数。它不会清空 `seen`，也不等于取消整个 Agent 运行。

```text
登记时：subscribe(listener)
          ├─ 保存 listener
          └─ 返回 stop

有事件时：Agent 调用 listener(event, signal)
          └─ seen 增加事件类型

取消时：stop()
          └─ 删除同一个 listener
```

取消函数靠闭包继续访问 `listener`，并通过箭头函数保留实例的 `this`。`Set.delete` 运行时还会产生布尔值；这里对外写成 `() => void`，表示调用方不把该布尔值作为接口结果使用。

回调只写了一个 `event` 参数也可以：它可以不使用调用方提供的第二个 `signal`，不表示调用方没有传第二个参数。

### 14.2 第二段：工具执行为什么有泛型、回调和 Promise（重点）

Pi 的 `AgentTool` 接口先声明了两个类型参数：`TParameters` 表示参数描述的类型，`TDetails` 表示结果中详情的类型。接口里的 `execute` 使用这两个位置，定义为：

Pi 源码：[packages/agent/src/types.ts](../pi-master/packages/agent/src/types.ts#L316)

```ts
execute: (
  toolCallId: string,
  params: Static<TParameters>,
  signal?: AbortSignal,
  onUpdate?: AgentToolUpdateCallback<TDetails>,
) => Promise<AgentToolResult<TDetails>>;
```

它在接口内部，是一个**函数属性的类型要求**，没有执行体。可以分成五层：

| 层次 | 片段 | 自然语言读法 |
| --- | --- | --- |
| 属性 | `execute:` | 这个属性保存一个函数 |
| 输入一 | `toolCallId: string` | 传入本次调用的字符串标识 |
| 输入二 | `params: Static<TParameters>` | 传入由工具参数描述对应出的参数类型 |
| 可选输入 | `signal?`、`onUpdate?` | 可以提供取消信号和中途更新回调 |
| 输出 | `Promise<AgentToolResult<TDetails>>` | 返回 Promise，成功后得到携带指定详情类型的工具结果 |

`Static` 来自 TypeBox，是类型工具，**不是 TypeScript 的关键字，也不是运行时校验函数**。运行时检查参数是否真的符合要求，需要另外的实际代码。

再拆 `onUpdate`：

Pi 源码：[packages/agent/src/types.ts](../pi-master/packages/agent/src/types.ts#L304)

```ts
export type AgentToolUpdateCallback<T = any> = (partialResult: AgentToolResult<T>) => void;
```

它接收一份阶段性工具结果；工具执行时需要报告中途进展，就调用这个函数。把回调作为参数传入，不等于它已经报告了一次进度。

### 14.3 同样叫 `execute`，另一层接口多了什么（重点）

Pi 扩展层的 `ToolDefinition` 使用另一种签名：

Pi 源码：[packages/coding-agent/src/core/extensions/types.ts](../pi-master/packages/coding-agent/src/core/extensions/types.ts#L451)

```ts
execute(
  toolCallId: string,
  params: Static<TParams>,
  signal: AbortSignal | undefined,
  onUpdate: AgentToolUpdateCallback<TDetails> | undefined,
  ctx: ExtensionContext,
): Promise<AgentToolResult<TDetails>>;
```

它是方法签名，因此参数列表后使用冒号说明返回类型。相比前一段：

- `signal` 与 `onUpdate` 没有 `?`，它们的值可以是 `undefined`，但参数位置仍然存在。
- 多了第五个参数 `ctx`，表示扩展执行时使用的上下文。
- 末尾仍是分号，没有函数体。

所以，不能仅因为两处名字都是 `execute`，就认为参数完全一样。先看它属于哪个接口，再看外层结构与每个参数位置。

### 14.4 第三段：从另一个函数推导出完整函数类型（重点）

Pi 的 `StreamFn` 定义是：

Pi 源码：[packages/agent/src/types.ts](../pi-master/packages/agent/src/types.ts#L24)

```ts
export type StreamFn = (
  ...args: Parameters<typeof streamSimple>
) => ReturnType<typeof streamSimple> | Promise<ReturnType<typeof streamSimple>>;
```

按顺序替换：

```text
typeof streamSimple
  → 已有 streamSimple 的函数类型

Parameters<typeof streamSimple>
  → 它所接收的参数元组

...args: 上面的参数元组
  → 这个新函数使用对应的参数列表

ReturnType<typeof streamSimple>
  → 它原本返回的类型

原返回类型 | Promise<原返回类型>
  → 新函数允许直接返回，也允许异步返回
```

整个定义没有调用 `streamSimple`。它借用已有函数的输入输出形状，避免重复写一份容易不一致的参数类型。

### 14.5 第四段：多个函数值怎样变成一组并发结果

Pi 处理工具结果时有这段代码：

Pi 源码：[packages/agent/src/agent-loop.ts](../pi-master/packages/agent/src/agent-loop.ts#L545)

```ts
const orderedFinalizedCalls = await Promise.all(
  finalizedCalls.map((entry) => (typeof entry === "function" ? entry() : Promise.resolve(entry))),
);
```

先看最里面：

```ts
typeof entry === "function" ? entry() : Promise.resolve(entry)
```

数组中有些项是待调用的函数，有些项已经是结果。是函数就调用它；已经是结果，就通过 `Promise.resolve` 包装成可以统一等待的形式。

再看外面：

```text
map       对每一项进行上面的处理
Promise.all  等这一组结果
await     等待后取得保持原输入顺序的结果数组
```

这里同时出现类型判断、条件表达式、函数调用、回调与 Promise。每一层单独理解后，长表达式就不再需要整体死记。

### 14.6 第五段：带问号和点号的状态准备

Pi 准备初始消息时有：

Pi 源码：[packages/agent/src/agent.ts](../pi-master/packages/agent/src/agent.ts#L82)

```ts
let messages = initialState?.messages?.slice() ?? [];
```

假设传入的 `initialState.messages` 是一个有两条消息的数组：

```text
initialState 存在
  ↓
messages 存在
  ↓
slice() 创建一个新的数组外层
  ↓
左边得到数组，不是 null 或 undefined
  ↓
?? 不使用右边的 []
```

若没有提供 `initialState`，或没有提供 `messages`，可选链给出 `undefined`，再使用右边的新空数组。

这一行完成的是“有则复制数组外层，无则使用空数组”。问号分别参与可选链和空值后备，不应逐个看成同一种符号。

## 15. 完整读一段小程序：Pi 的 hello 工具

下面这份示例把前面的语法放在同一段实际代码中。只去掉文件头注释，保留代码：

Pi 源码：[packages/coding-agent/examples/extensions/hello.ts](../pi-master/packages/coding-agent/examples/extensions/hello.ts#L5)

```ts
import { Type } from "@mariozechner/pi-ai";
import { defineTool, type ExtensionAPI } from "@mariozechner/pi-coding-agent";

const helloTool = defineTool({
  name: "hello",
  label: "Hello",
  description: "A simple greeting tool",
  parameters: Type.Object({
    name: Type.String({ description: "Name to greet" }),
  }),

  async execute(_toolCallId, params, _signal, _onUpdate, _ctx) {
    return {
      content: [{ type: "text", text: `Hello, ${params.name}!` }],
      details: { greeted: params.name },
    };
  },
});

export default function (pi: ExtensionAPI) {
  pi.registerTool(helloTool);
}
```

先按执行时间分成两段。

**文件被加载时**，嵌套调用按具体求值顺序展开：

```text
Type.String(...) 先产生 name 的参数描述
  ↓
把结果放进 { name: ... } 对象
  ↓
Type.Object(...) 得到这整个对象，产生工具的参数描述
  ↓
完整的工具对象准备好，其中包含 execute 方法
  ↓
defineTool(...) 接收这个工具对象
```

`defineTool` 会把传入对象原样返回，同时帮助 TypeScript 保留 `params` 等位置的类型信息；它的实现见 [Pi 的 defineTool](../pi-master/packages/coding-agent/src/core/extensions/types.ts#L480)。对象中的 `execute` 此时只是被保存下来，没有因为出现 `async execute` 就执行一次问候。

**默认导出的函数被加载方调用时**，它收到 `pi`，执行 `pi.registerTool(helloTool)`。登记工具仍不等于工具已经执行。

以后工具运行时，才会调用 `execute`。假设一次合法的教学输入为：

```ts
params = { name: "小林" };
```

这里是说明参数内容，不是另一个真实赋值位置。函数体会组织出：

```ts
{
  content: [{ type: "text", text: "Hello, 小林!" }],
  details: { greeted: "小林" },
}
```

因为 `execute` 是 `async` 方法，调用方直接拿到的是 Promise；上面这个对象是其成功完成时的结果。

逐项回看那些容易让人卡住的写法：

| 写法 | 在这段代码中的作用 |
| --- | --- |
| `import { Type }` | 取得运行时构造参数描述的工具 |
| `type ExtensionAPI` | 只导入类型说明 |
| `defineTool({ ... })` | 把一个对象当参数传给函数 |
| `parameters: Type.Object({ ... })` | 属性值来自函数调用的结果 |
| `async execute(...) { ... }` | 对象中的异步方法 |
| `_toolCallId`、`_signal` | 普通参数名；前导下划线常用来提示本例未使用它 |
| `params.name` | 读取这次实参对象的属性 |
| 反引号与 `${...}` | 把名字嵌入问候字符串 |
| `return { ... }` | 从方法返回一个对象，由 async 包装成异步结果 |
| `export default function (pi: ExtensionAPI)` | 默认导出一个带类型标注的函数 |

`Type`、`defineTool`、`registerTool` 是库或对象提供的接口名称；`import`、`async`、`return` 才是语言本身的语法。分清两者后，就知道哪些含义能从语法判断，哪些需要继续看这个接口的实现。

## 16. 再补齐几种容易被误认的写法

### 16.1 `typeof`、`in` 与 `instanceof` 是不同的运行检查

```ts
typeof "你好";                    // "string"
"content" in { content: "你好" }; // true
new Error("失败") instanceof Error; // true
```

- `typeof` 判断基本的运行时种类。`typeof null` 会得到 `"object"`，数组也不是靠 `typeof` 单独识别的。
- `in` 检查对象自身或其原型链上是否有这个属性，不要求属性值为真。
- `instanceof` 检查对象与构造函数原型之间的关系，常用来区分错误等实例。

只想检查对象自身的属性时，可以留意 `Object.hasOwn(obj, key)`，不要把它与 `key in obj` 完全等同。

### 16.2 类型谓词把检查结果连接到分支中的类型（重点）

```ts
function isText(value: unknown): value is string {
  return typeof value === "string";
}

function display(value: unknown): string {
  if (isText(value)) {
    return value.toUpperCase();
  }
  return "不是文本";
}
```

`isText` 在运行时仍然返回布尔值。返回类型的 `value is string` 告诉 TypeScript：若结果为真，可以在相应分支把 `value` 按字符串使用。

类似的 `asserts value is SomeType` 声明，表示函数正常返回后应满足相应类型要求；函数实现应在条件不成立时抛错，不能把这种声明当成自动校验器。

### 16.3 短路赋值：条件满足时才写回

| 写法 | 可以怎样理解 |
| --- | --- |
| `value ??= fallback` | 当前为 `null` 或 `undefined`，才把后备值写入 |
| `value \|\|= fallback` | 当前为假值，才把后备值写入 |
| `value &&= next` | 当前为真值，才把右边结果写入 |

这些是实际赋值操作，右侧在不需要时不会计算。例如：

```ts
let retries: number | undefined;
retries ??= 3;
// retries 现在是 3
```

### 16.4 正则表达式、位运算与模板字面量类型

```ts
const hasSpace = /\s+/.test("你好 世界"); // true
```

这里的一对 `/.../` 创建正则表达式，`\s` 表示空白字符，`+` 表示重复一次或多次。它与数字之间的 `/` 除法不是同一种用途。反斜线出现在字符串中又可能是转义字符，例如 `"\n"` 表示换行。

`|`、`&` 在类型里可以表示联合与交叉，在运行表达式里则可能是按位或、按位与；`<<`、`>>`、`>>>` 也可能是位移操作。它们与 `||`、`&&` 的短路逻辑不同。

#### 模板字面量类型（重点）

反引号还可能出现在类型位置：

```ts
type Role = "user" | "assistant";
type EventName = `${Role}_message`;
```

这里得到的是 `"user_message" | "assistant_message"` 这种类型组合，不是在生成运行时字符串。

Pi 里也有实际用法：[tui 的尺寸类型](../pi-master/packages/tui/src/tui.ts) 用 `` `${number}%` `` 表示百分比形式的字符串类型。

### 16.5 `enum`、命名空间与 JSX

`enum` 可以给一组值起名字；普通枚举还会有运行时表示，因此不应把它一律当作接口那样删除。

```ts
enum Phase {
  Ready = "ready",
  Done = "done",
}

const phase = Phase.Ready;
```

`namespace` 可以把名字组织在一个命名空间下；现代模块代码更常通过文件的 `import`、`export` 组织名字。看到 `declare namespace` 时，还要判断它是否只是在声明类型。

`.tsx` 文件可能包含 `<Panel />` 这样的 JSX，它通常用于描述界面元素，不是泛型调用或大小比较。普通 `.ts` 的核心 Agent 代码并不需要先掌握一整套界面语法；先结合文件类型和位置辨认即可。

### 16.6 不带花括号的导入与动态导入

```ts
import "./setup.js";
```

这是模块写法示意：不取某个导出名字，主要是为了让模块的顶层初始化发生。

`import("./module.js")` 则是一种异步模块加载表达式，返回 Promise，成功后得到模块的导出对象。它与类型位置中的 `import("某个模块").SomeType` 不是同一种用途；后者只在类型表达式里引用类型，不会因为这段类型文字而加载运行模块。

这里只用于辨认已有代码，并不意味着项目鼓励在任何位置都采用动态导入。

## 17. 符号回查：同一个符号，放回位置再读

| 符号与位置 | 含义 | 小例子 |
| --- | --- | --- |
| 变量或参数后的 `:` | 类型标注 | `text: string` |
| 参数列表后的 `:` | 返回类型 | `read(): string` |
| 对象中的 `:` | 属性和值的对应 | `{ text: "你好" }` |
| 解构中的 `:` | 取属性并改名 | `const { text: content } = value` |
| 条件表达式中的 `:` | 否则的分支 | `ok ? "是" : "否"` |
| 属性或参数后的 `?` | 可以省略 | `signal?: AbortSignal` |
| `?.` | 左侧不是 `null` 或 `undefined` 才继续 | `options?.title` |
| `??` | 为 `null` 或 `undefined` 时使用后备值 | `title ?? "未命名"` |
| 运行表达式中的 `? :` | 按条件选一个值 | `ready ? a : b` |
| 类型中的 `extends ... ? ... : ...` | 按类型关系选择类型 | `T extends string ? A : B` |
| 实现位置的 `=>` | 创建箭头函数 | `(text) => text.length` |
| 类型位置的 `=>` | 描述函数输入输出 | `(text: string) => number` |
| `()` 在函数定义中 | 参数列表 | `function read(text) {}` |
| `()` 跟在函数值后 | 现在调用 | `read("你好")` |
| `()` 包围表达式 | 分组或明确表达式含义 | `() => ({ text: "你好" })` |
| `{}` 在运行表达式中 | 创建对象 | `const x = { text: "你好" }` |
| `{}` 在函数或分支后 | 语句块 | `if (ok) { ... }` |
| `{}` 在类型中 | 对象形状 | `type X = { text: string }` |
| `{}` 在赋值左边 | 对象解构 | `const { text } = x` |
| `{}` 在 import/export 中 | 选择具名成员 | `import { Type } from "..."` |
| `[]` 在值的位置 | 数组 | `["你好"]` |
| `[]` 跟在对象值后 | 按键或下标读取 | `messages[0]` |
| `[]` 跟在类型后 | 数组类型 | `Message[]` |
| `[K]` 在类型表达式中 | 索引访问类型 | `Message["content"]` |
| `[name]` 在成员声明中 | 计算属性名 | `[Symbol.asyncIterator]()` |
| `[]` 包围固定位置类型 | 元组 | `[string, number]` |
| `<T>` | 声明或传入类型参数，依位置判断 | `Result<T>` |
| `!value` | 运行时逻辑取反 | `!ready` |
| `value!` | 告诉检查器该值非空 | `queue.shift()!` |
| `field!:` | 确定赋值断言 | `resolveFinalResult!: (...) => void` |
| `...` 在构造或调用处 | 展开已有内容 | `[...items]`、`fn(...args)` |
| `...` 在接收位置 | 收集剩余内容 | `(...args)`、`[first, ...rest]` |
| 类型中的 `\|` 与 `&` | 联合与交叉 | `A \| B`、`A & B` |
| `*` 跟在 function 或 async 后 | 生成器 | `function* values()` |
| `as` 在类型表达式旁 | 类型断言 | `value as TextContent` |
| `as` 在 import 中 | 导入改名 | `import { x as y }` |
| `in` 在运行检查中 | 检查属性是否存在 | `"text" in value` |
| `in` 在映射类型中 | 按键生成属性 | `[K in keyof T]` |

看到复杂代码时，可以按固定次序拆：

1. **先找外层。** 这是声明变量、定义类型、定义函数、调用函数，还是一个类成员？
2. **用等号和函数体分界。** 哪些只是类型说明，哪些会真的执行？
3. **列输入和结果。** 每个参数是什么值，返回的是普通值、函数、Promise，还是迭代器？
4. **追踪函数值。** 它现在被保存了，还是出现调用括号、已经被执行了？
5. **追踪时间。** 谁等待哪个 Promise，哪里交出事件，哪里只登记了后续动作？

例如，读 `return () => this.listeners.delete(listener)` 时，先看出外层在返回一个函数；再知道删除动作位于内层函数体；最后就能确定“这次返回”与“以后取消订阅”发生在不同时间。复杂符号因此可以逐步还原成具体行为。
