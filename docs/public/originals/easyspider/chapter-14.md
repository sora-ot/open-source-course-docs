# 14.messageInteraction.js：每条消息怎样把操作台接到流程图

参数篇解决“保存什么”，操作台篇解决“什么时候生成、什么时候确认”，上一篇补了 WebSocket 的连接与收发背景。现在继续追：确认之后，哪些字段会发送？一次输入为什么会发两条消息？为什么同样选了两个元素，有时发送共同 XPath，有时发送路径列表？

源码：[messageInteraction.js](../../Extension/manifest_v3/src/content-scripts/messageInteraction.js)。与前文中文发布版的同名文件相比，核心逻辑一致，主要差别是 import 和 export 的组织方式。下面覆盖所有发送函数、辅助函数、连接回调和六种接收分支。

接收方只追到 [Electron main.js](../../ElectronJS/main.js) 的转发入口和 [流程图 logic.js](../../ElectronJS/src/taskGrid/logic.js) 的 `handleAddElement()`；第 24 篇先讲 Electron 如何发出调试消息，第 25 篇“调试功能详解”逐项讲插件的消息接收、反向标记、路径组合与结果反馈。接下来先在第 15 篇认识任务结构，第 16 篇理解 `executeNode()`、循环/判断、递归和正式执行器；再在第 17 篇学习 Selenium API，逐节先看真实 JSON 参数、再看这些场景的执行实现，并集中讲浏览器历史恢复。到第 17 篇讲完执行阶段。第 18～23 篇沿用第 15 篇构建的节点结构，先区分存储下标与界面编号，再讲渲染与增删改查，随后接入消息，最后讲保存与加载。

## 第一部分：先分清三种容易混淆的 type

### 1. 同一个字段名，在不同对象里意思不同

| 所在位置 | 示例 | 意义 |
|---|---|---|
| 最外层消息 `type` | `0`、`2`、`3` | Electron 用来区分连接、键盘输入、转发等协议 |
| `message.pipe` 内操作对象的 `type` | `singleClick`、`multiCollectWithPattern` | 流程图用来决定添加什么操作 |
| 字段 `contentType` / `nodeType` | `0`、`1`、`2` 等 | 字段的内容读取规则、元素角色 |
| 流程图节点 `option` | `2` 点击、`3` 提取、`8` 循环 | 保存后的节点类别 |

不能把 `type:3` 直接解释为“提取数据节点”：外层 `3` 表示转发，内层可能是点击、输入、移动或采集。

### 2. 一条操作消息装了两层 JSON

所有操作发送函数反复使用这段结构：

```js
let message_action = {
    type: 3,
    from: 0,
    message: {"pipe": JSON.stringify(message)}
};
global.ws.send(JSON.stringify(message_action));
```

假设内层 `message` 是一个点击操作：

```js
const message = {
    type: "singleClick",
    xpath: '//*[@id="buy"]',
    useLoop: false
};
```

上面是用于解释包装的精简对象，真实点击字段见后文。按顺序推：

1. 第一次 `JSON.stringify(message)`，把操作对象转成字符串。
2. 这个字符串放进外层对象的 `message.pipe`，所以 pipe 不是对象。
3. 外层 `from=0` 表示浏览器发往流程图；反方向使用 `from=1`。
4. 第二次 stringify，把外层转成 WebSocket 发送的数据。
5. Electron parse 外层，根据 `type=3`、`from=0`，把 `msg.message.pipe` 直接转发给流程图。
6. 流程图收到的已经是内层字符串，parse 一次就得到 `singleClick` 操作。

这就是为什么抓包里的 pipe 有转义引号，但流程图处理函数读到的 `msg.type` 是字符串操作名。

下面每个发送函数都给出具体的内层消息。**除连接声明和键盘输入外，每个例子都按下面的方式发送**，不能直接把内层对象交给 `ws.send()`：

```js
// message 换成各节给出的完整操作对象；这是源码中重复出现的包装步骤。
const message_action = {
    type: 3,
    from: 0,
    message: {pipe: JSON.stringify(message)}
};
global.ws.send(JSON.stringify(message_action));
```

阅读例子时先看内层 `type`，再看循环范围，最后看字段定位。第 13 节分别展开“提取全部元素”和“提取全部元素带子元素”，第 18 节展开“循环点击单个元素”和两种翻页入口。

### 3. 共用元数据从哪里来

| 字段 | 来源和用途 |
|---|---|
| `history` | 当前 `history.length`，用于记录浏览器历史上下文，不是当前页码 |
| `tabIndex` | 发送函数写 `-1` 占位，不表示它已经知道标签页序号 |
| `id` | `global.id`，用于当前浏览器连接/标签页关联；不是 DOM id |
| `iframe` | 当前内容脚本的 iframe 标志 |
| `xpath` | 单元素通常用 `readXPath(node,0)`，可能优先使用 id/class |
| `allXPaths` | 调用 `getElementXPaths(node)` 得到的备选定位 |
| `useLoop` | 操作是否使用循环项语义 |
| `loopType` | 循环方式，见循环函数部分 |

这里的 `history` 是 `window.history` 的简写，`history.length` 表示当前窗口的会话历史记录条目数，包含当前页面；例如历史中只有 A → B → C 三个条目时，值为 3，即使后退到 B 仍为 3，因此它不是当前页面的序号。

不是每个函数都发送全部这些键。例如 `sendMouseMove()` 没有显式发送 `id`，`collectSingle()` 没有单独发送一个 `xpath`，因为定位在字段对象里。

## 第二部分：连接与每一种接收消息

### 4. onopen：先声明“我是哪个网页连接”

```js
global.ws = new WebSocket("ws://localhost:8084");
global.ws.onopen = function () {
    let message = {
        type: 0,
        message: {id: global.id, title: document.title}
    };
    this.send(JSON.stringify(message));
};
```

1. 模块导入时创建连接，不是用户每点击一次就新建一个连接。
2. 连接打开后读取网页标题和随机连接标识。
3. 发外层 `type=0`，没有 pipe 包装。
4. Electron 的连接处理把流程图连接 id `2` 与网页的 `C...` 标识分开，之后才能转发消息。

示例：`{"type":0,"message":{"id":"C123456","title":"图书列表"}}`。这个文件没有实现自动重连或发送排队，下面的发送函数直接调用 `global.ws.send()`。

### 5. onmessage 先 parse，再按六种字符串分发

```js
global.ws.onmessage = function (evt) {
    evt = JSON.parse(evt.data);
    // 根据 evt.type 分支处理
};
```

原来的 `evt` 是 WebSocket 事件；parse 后同一个变量名改为消息对象。各分支按如下顺序判断：

| 接收的 `type` | 示例 | 执行步骤与结果 |
|---|---|---|
| `update_parameter_num` | `{"type":"update_parameter_num","value":6}` | parse → `parseInt(value)` → `chrome.storage.local.set({parameterNum:6})`；下次生成参数从编号 6 开始 |
| `notify` | `{"type":"notify","msg_zh":"已添加","msg_en":"Added","level":"success"}` | 根据 `global.lang` 选中文/英文 → `createNotification(text,level)` 显示通知 |
| `cancelSelection` | `{"type":"cancelSelection"}` | 调用 `clearEl()`，清选中节点、字段和预览并恢复选择样式 |
| `trial` | 后文展示嵌套结构 | 把整个 parse 后的消息传给 `trial(evt)`；本文件不在这个分支解析字段路径 |
| `showAllToolboxes` | `{"type":"showAllToolboxes"}` | 找到当前文档的 `wrapperToolkit`，设 `style.display="block"` |
| `hideAllToolboxes` | `{"type":"hideAllToolboxes"}` | 找到同一容器，设 `style.display="none"` |

“All” 是消息名称。单个内容脚本只操作自己的文档；广播到多少网页连接取决于 Electron 的发送逻辑。显示/隐藏只改容器样式，没有在这两分支清字段。

### 6. 参数编号如何形成闭环

确认添加两个字段后，流程图的 `notifyParameterNum(2)` 增加编号，并发送：

```js
{
    type: 3,
    from: 1,
    message: {
        pipe: JSON.stringify({type: "update_parameter_num", value: parameterNum})
    }
}
```

逐步追踪：扩展发字段 → Electron 转到流程图 → 流程图处理字段并增加 `parameterNum` → 反方向转发 pipe → 扩展收到 `update_parameter_num` → 写 Chrome 存储 → 下次参数生成回调读取新编号。

因此预览时的 `n++` 与确认后的全局编号更新是两件事。反向编号消息也不是对每次发送都带请求 id 的通用成功回执。

## 第三部分：单元素操作的每条发送函数

### 7. input(value,batch)：一次输入发两条消息

普通调用 `input("电脑",false)`，内层操作对象为：

本例控件是独立页面中的 `<body><input id="search"></body>`，没有 class、name 等额外定位属性。

```json
{
  "type": "inputText",
  "history": 3,
  "tabIndex": -1,
  "xpath": "//*[@id=\"search\"]",
  "allXPaths": ["/html/body/input[1]", "//input[contains(., '')]", "id(\"search\")", "/html/body/input"],
  "iframe": false,
  "value": "电脑",
  "useLoop": false,
  "loopType": 3
}
```

示例的 `history:3`、连接标识等取固定教学值；路径按本例页面推演，实际来自当前页面。下面同样如此。代码执行过程：

1. 默认操作名 `inputText`、`useLoop=false`。
2. 若 `batch=true`，改成 `batchInputText`、`useLoop=true`。`loopType=3` 表示文本列表。
3. 从首个已选节点生成路径，保存用户传入的 `value`。
4. 执行 `window.stop()`，尝试停止当前页面加载。
5. 用外层 `type=3` 包装操作，发送给流程图记录输入节点。批量模式会让流程图先建循环，再建输入节点。
6. 再发送一条外层 `type=2` 消息，请 Electron 操控真实网页输入框：

```json
{
  "type": 2,
  "message": {
    "keyboardStr": "电脑",
    "xpath": "//*[@id=\"search\"]",
    "iframe": false,
    "id": "C123456"
  }
}
```

7. 最后调用 `clearAfterSend()`。实际清选择由调用它的 `toolkit.getInput()` 做。

批量例子：`input("电脑\n手机",true)`。本函数只把整段文本装进 value，并设置循环标记；它没有在这里逐行输入两个词。

这次发送的第一条消息，其完整内层对象如下；同样经过第 2 节的 `type:3`、`from:0`、`pipe` 包装：

```json
{
  "type": "batchInputText",
  "history": 3,
  "tabIndex": -1,
  "xpath": "//*[@id=\"search\"]",
  "allXPaths": ["/html/body/input[1]", "//input[contains(., '')]", "id(\"search\")", "/html/body/input"],
  "iframe": false,
  "value": "电脑\n手机",
  "useLoop": true,
  "loopType": 3
}
```

第二条仍是键盘输入消息，但 `keyboardStr` 也是整段文本：

```json
{
  "type": 2,
  "message": {
    "keyboardStr": "电脑\n手机",
    "xpath": "//*[@id=\"search\"]",
    "iframe": false,
    "id": "C123456"
  }
}
```

### 8. sendSingleClick()：记录点击，Electron 再执行点击

选择独立页面中的 `<body><a id="buy">购买</a></body>` 时，完整内层消息是：

```json
{
  "type": "singleClick",
  "id": "C123456",
  "history": 3,
  "tabIndex": -1,
  "useLoop": false,
  "iframe": false,
  "content": "购买",
  "xpath": "//*[@id=\"buy\"]",
  "allXPaths": ["/html/body/a[1]", "//a[contains(., '购买')]", "id(\"buy\")", "/html/body/a"]
}
```

顺序是：读取首个已选 DOM 的 innerText → 生成路径 → 包装 `type=3` → send → 设置发送标志。这个函数没有直接调用 `.click()`。Electron 收到 `singleClick` 后既转发到流程图，又进入 Click 动作分支。

### 9. sendChangeOption(optionMode,optionValue)：传下拉框切换规则

调用 `sendChangeOption(2,"py")`：

1. 生成 `type:"changeOption"`。
2. 保存 `optionMode:2`、`optionValue:"py"`。
3. 保存首个已选 SELECT 的 `xpath`、`allXPaths`，以及 `history`、`tabIndex:-1`、`useLoop:false`、`iframe`。
4. 包装并发送，最后设置发送标志。

模式 0 下一项；1 索引；2 value；3 显示文字。这条消息传的是切换规则；操作台 `sendChangeSelect()` 发送后还会尝试修改本地 SELECT，两个函数的职责要分开。

假设独立页面中的控件是 `<body><select id="language"><option value="java">Java</option><option value="py">Python</option></select></body>`。选中 SELECT，按 value 切换到 Python。完整内层消息如下，外层使用第 2 节的操作包装：

```json
{
  "type": "changeOption",
  "optionMode": 2,
  "optionValue": "py",
  "history": 3,
  "tabIndex": -1,
  "useLoop": false,
  "iframe": false,
  "xpath": "//*[@id=\"language\"]",
  "allXPaths": ["/html/body/select[1]", "//select[contains(., 'JavaPython')]", "id(\"language\")", "/html/body/select"]
}
```

这里只选模式 2 作具体例子；改为模式 1 时可传 `optionValue:"1"`，改为模式 3 时可传 `optionValue:"Python"`。这些值来自操作台，函数不会把它们统一转换成数字。

### 10. sendMouseMove()：单个元素悬停

例如首个已选节点是“商品详情”链接：

1. 构造 `type:"mouseMove"`、`useLoop:false`。
2. 读取该节点 `innerText` 放进 `content`，同时读取两种路径信息。
3. 添加 `history`、`tabIndex:-1`、`iframe`，包装并发送。
4. Electron 对 Move 操作执行鼠标移动，流程图用 option 7 表示移动节点。

它的消息与单击相似，但没有显式 `id`；不要用一个“通用模板”补出源码没有发的字段。

例如选中独立页面中的 `<body><a id="detail">商品详情</a></body>`，完整内层消息是：

```json
{
  "type": "mouseMove",
  "history": 3,
  "tabIndex": -1,
  "useLoop": false,
  "iframe": false,
  "content": "商品详情",
  "xpath": "//*[@id=\"detail\"]",
  "allXPaths": ["/html/body/a[1]", "//a[contains(., '商品详情')]", "id(\"detail\")", "/html/body/a"]
}
```

发送时外层仍是 `type:3`，不会因为这是鼠标操作就改成外层 `type:7`。

## 第四部分：采集函数怎样带上参数

### 11. collectSingle()：单元素采集

```js
let message = {
    type: "singleCollect",
    history: history.length,
    tabIndex: -1,
    iframe: global.iframe,
    parameters: global.outputParameters
};
```

比如 D 的链接文本、地址已经生成：

1. 直接把两个字段数组赋给 `parameters`，不重新读 D，也不重新调用参数生成函数。
2. stringify 时把字段及样例一起装进 pipe。
3. 流程图按 `singleCollect` 处理提取操作：当前已选流程图节点是提取节点时追加字段，否则新建提取节点。
4. 流程图补充字段配置并通知新编号；操作台发送后清自己的选择。

#### 11.1 一个价格元素的完整消息

为了先看清字段定位，单独用一个更小的页面：`<body><p>￥99</p></body>`。右键选中这个 `p` → 点击“采集该元素的文本” → 等预览生成 → 点击“确认采集”，最后调用 `collectSingle()`。

假设参数编号从 1 开始，完整内层消息如下。`unique_index` 在实际运行时随机生成，这里固定写成 `demo-price` 便于阅读：

```json
{
  "type": "singleCollect",
  "history": 3,
  "tabIndex": -1,
  "iframe": false,
  "parameters": [
    {
      "nodeType": 0,
      "contentType": 0,
      "relative": false,
      "name": "参数1_文本",
      "desc": "",
      "extractType": 0,
      "relativeXPath": "/html/body/p[1]",
      "allXPaths": ["/html/body/p[1]", "//p[contains(., '￥99')]", "/html/body/p"],
      "exampleValues": [{"num": 0, "value": "￥99"}],
      "unique_index": "demo-price",
      "iframe": false
    }
  ]
}
```

这条消息的操作层没有 `xpath`；字段自己带 `relativeXPath`。虽然键名有 relative，`relative:false` 表明这里保存的是绝对路径。包装后，`message_action.message.pipe` 是上面整份对象的 JSON 字符串，流程图得到一个提取字段，示例结果是一行 `￥99`。

### 12. collectMultiNoPattern()：不同位置组成同一记录

它与上面结构相同，只把操作名改为 `multiCollectNoPattern`。例子是 D 链接、E 图片、F 价格，参数数组含四列、各一行样例。

步骤：读取 `outputParameters` → 包装发送 → 流程图进入与 singleCollect 共用的提取分支 → 追加或新建提取节点 → 更新编号。它没有 loopType、共同 xpath 或 pathList，不因为选中节点多就自动创建循环。

#### 12.1 价格与图片组成同一行的完整消息

另一个小页面是 `<body><p>￥99</p><img src="java.jpg"></body>`。按这个顺序选中价格和图片，进入无规律多元素采集分支，预览为“价格、图片地址”两列，确认时发送：

```json
{
  "type": "multiCollectNoPattern",
  "history": 3,
  "tabIndex": -1,
  "iframe": false,
  "parameters": [
    {
      "nodeType": 0,
      "contentType": 0,
      "relative": false,
      "name": "参数1_文本",
      "desc": "",
      "relativeXPath": "/html/body/p[1]",
      "allXPaths": ["/html/body/p[1]", "//p[contains(., '￥99')]", "/html/body/p"],
      "exampleValues": [{"num": 0, "value": "￥99"}],
      "unique_index": "demo-price",
      "iframe": false
    },
    {
      "nodeType": 4,
      "contentType": 0,
      "relative": false,
      "name": "参数2_图片地址",
      "desc": "",
      "relativeXPath": "/html/body/img[1]",
      "allXPaths": ["/html/body/img[1]", "//img[contains(., '')]", "/html/body/img"],
      "exampleValues": [{"num": 0, "value": "java.jpg"}],
      "unique_index": "demo-image",
      "iframe": false
    }
  ]
}
```

这里两个字段的样例 `num` 都是 0，表示同一行，不是“第一行价格，第二行图片”。没有循环范围；两个字段各用自己的绝对路径。`generateMultiParameters()` 生成的这两个字段没有 `extractType`，发送函数也不会补上它。

### 13. collectMultiWithPattern()：先确定循环，再带字段

核心初始对象：

```js
let message = {
    type: "multiCollectWithPattern",
    history: history.length,
    tabIndex: -1,
    loopType: 1,
    iframe: global.iframe,
    xpath: "",
    allXPaths: "",
    isDescendents: global.app._data.selectedDescendents,
    parameters: global.outputParameters
};
```

以 B、C 两个商品块为例，一步步推：

1. 初始化 `loopType=1`，准备按一个共同 XPath 找到循环项。
2. `isDescendents=true` 表示字段来自块内遍历，参数路径如 `/a[1]`、`/p[1]`。
3. 遍历全部字段，把每个 `exampleValues` 缩成只保留原来的第一条：

```js
global.outputParameters[i]["exampleValues"] = [
    global.outputParameters[i]["exampleValues"][0]
];
```

4. `message.parameters` 与全局字段数组共享引用，所以这一步同时改变消息数据和全局数据，不是只处理一份发送副本。
5. 调用 `detectAllSelected()`。若共同路径匹配的全部元素已选，保留 `loopType=1`，把 `nowPath`、`nowAllPaths` 放进消息。
6. 否则改成 `loopType=2`，逐个读取已选节点路径放入 `pathList`；初始 `xpath`、`allXPaths` 仍为空字符串。
7. 包装发送。流程图先 `addElement(8,msg)` 建循环，再 `addElement(3,msg)` 建循环中的提取操作。

假设共同路径为 `/html/body/section[1]/article`，两块都选中，则关键定位字段为：

```json
{
  "type": "multiCollectWithPattern",
  "loopType": 1,
  "xpath": "/html/body/section[1]/article",
  "isDescendents": true
}
```

这是定位部分的摘录，完整消息还带前面列出的元数据和参数数组。如果原来第一块没有促销，促销的第一条样例是 `{num:1,value:"促销"}`，缩减后仍保留 num 1，不会重新编号为 0。

#### 13.1 提取全部元素：三个价格，一列数据

先用一个不带复杂子元素的页面，HTML 如下：

```html
<body>
  <section><p>￥99</p><p>￥88</p><p>￥79</p></section>
</body>
```

操作过程是：右键选中第一个价格 → “选中全部”，使三个 `p` 都进入 `nodeList` → 等预览生成 → “采集数据”。多元素菜单调用 `confirmCollectMultiAndDescendents()`，再调用 `collectMultiWithPattern()`；即使没有选择子元素，也使用这个确认方法。

假设共同路径已经确定为 `/html/body/section[1]/p`，它匹配 3 个元素，已选数量也是 3。发送前的关键状态为：

```js
global.nodeList.length === 3;
global.app._data.nowPath === "/html/body/section[1]/p";
global.app._data.selectedDescendents === false;
// 一列参数，预览中有三条样例：
global.outputParameters[0].exampleValues;
// [{num:0,value:"￥99"}, {num:1,value:"￥88"}, {num:2,value:"￥79"}]
```

确认时 `detectAllSelected()` 为 true，所以使用 `loopType:1`。样例先缩减到第一条，再发送下面的完整内层消息；编号从 1 开始，随机标识仍用固定教学值：

```json
{
  "type": "multiCollectWithPattern",
  "history": 3,
  "tabIndex": -1,
  "loopType": 1,
  "iframe": false,
  "xpath": "/html/body/section[1]/p",
  "allXPaths": ["/html/body/section[1]/p[1]", "//p[contains(., '￥99')]", "/html/body/section/p[last()-2]"],
  "isDescendents": false,
  "parameters": [
    {
      "nodeType": 0,
      "contentType": 0,
      "relative": true,
      "name": "参数1_文本",
      "desc": "",
      "extractType": 0,
      "relativeXPath": "",
      "allXPaths": "",
      "exampleValues": [{"num": 0, "value": "￥99"}],
      "unique_index": "demo-price",
      "iframe": false
    }
  ]
}
```

本例操作层的 `allXPaths` 按首个价格的备选路径展示，它来自 `nowAllPaths`，不保证每条备选都匹配全部价格。决定本例循环范围的是共同 `xpath`。

将上面的 JSON 对象赋给 `message`，实际发送的外层为：

```js
const message_action = {
    type: 3,
    from: 0,
    message: {pipe: JSON.stringify(message)}
};
global.ws.send(JSON.stringify(message_action));
```

流程图创建的结构和预期提取结果为：

```text
循环（option=8，loopType=1，xpath=/html/body/section[1]/p）
└── 提取数据（option=3）
    └── 参数1_文本：relative=true，relativeXPath=""

第1个循环项 p → ￥99
第2个循环项 p → ￥88
第3个循环项 p → ￥79
```

**字段路径为空表示“取当前循环项自身”。** 三个已选元素提供三行，`parameters` 只有一列。消息只保留一个示例值，不表示任务只采第一行；实际提取范围由父循环决定。

#### 13.2 提取全部元素带子元素：两个商品块，三列数据

这次选中的循环项是整个 `article`，字段来自它内部的链接和价格。用下面的简化页面对应第 10 篇的商品块案例：

```html
<body>
  <section>
    <article id="java"><a href="/java">Java入门</a><p>￥99</p></article>
    <article id="python"><a href="/python">Python入门</a><p>￥88</p></article>
  </section>
</body>
```

操作过程是：选中第一个商品块 → “选中全部”，使两个 `article` 都进入 `nodeList` → “选中子元素（应选尽选）” → 等三列、两行预览出现 → “采集数据”。`handleDescendents(0)` 设置 `selectedDescendents=true`，生成块内字段。

本例 DFS 用栈，孩子按倒序压栈，弹出时仍先处理前面的链接，所以先建立链接文本和链接地址，再建立价格字段。块本身没有直接文字，不另建一列整块文本。预览为：

| 行 | 参数1_链接文本 | 参数2_链接地址 | 参数3_文本 |
|---:|---|---|---|
| 0 | Java入门 | `/java` | ￥99 |
| 1 | Python入门 | `/python` | ￥88 |

假设 `nowPath="/html/body/section[1]/article"`，匹配的两个商品块都已选中；`nowAllPaths` 保存首个块的备选路径。发送函数将每列样例缩成第一条，完整内层消息如下：

```json
{
  "type": "multiCollectWithPattern",
  "history": 3,
  "tabIndex": -1,
  "loopType": 1,
  "iframe": false,
  "xpath": "/html/body/section[1]/article",
  "allXPaths": ["/html/body/section[1]/article[1]", "//article[contains(., 'Java入门￥99')]", "id(\"java\")", "/html/body/section/article[last()-1]"],
  "isDescendents": true,
  "parameters": [
    {
      "nodeType": 1,
      "contentType": 0,
      "relative": true,
      "name": "参数1_链接文本",
      "desc": "",
      "relativeXPath": "/a[1]",
      "allXPaths": ["/a[1]", "//a[contains(., 'Java入门')]", "/html/body/section/article[last()-1]/a"],
      "exampleValues": [{"num": 0, "value": "Java入门"}],
      "unique_index": "/a[1]",
      "iframe": false
    },
    {
      "nodeType": 2,
      "contentType": 0,
      "relative": true,
      "name": "参数2_链接地址",
      "desc": "",
      "relativeXPath": "/a[1]",
      "allXPaths": ["/a[1]", "//a[contains(., 'Java入门')]", "/html/body/section/article[last()-1]/a"],
      "exampleValues": [{"num": 0, "value": "/java"}],
      "unique_index": "/a[1]",
      "iframe": false
    },
    {
      "nodeType": 0,
      "contentType": 1,
      "relative": true,
      "name": "参数3_文本",
      "desc": "",
      "relativeXPath": "/p[1]",
      "allXPaths": ["/p[1]", "//p[contains(., '￥99')]", "/html/body/section/article[last()-1]/p"],
      "exampleValues": [{"num": 0, "value": "￥99"}],
      "unique_index": "/p[1]",
      "iframe": false
    }
  ]
}
```

仍把上面的对象赋给 `message`，实际发送为：

```js
const message_action = {
    type: 3,
    from: 0,
    message: {pipe: JSON.stringify(message)}
};
global.ws.send(JSON.stringify(message_action));
```

流程图创建一个商品块循环，里面是一个包含三列的提取节点：

```text
循环（option=8，xpath=/html/body/section[1]/article）
└── 提取数据（option=3）
    ├── /a[1]：链接文本（nodeType=1，contentType=0）
    ├── /a[1]：链接地址（nodeType=2，contentType=0）
    └── /p[1]：价格直接文本（nodeType=0，contentType=1）
```

手工展开定位：第一个循环项是 `article[1]`，价格对应 `/html/body/section[1]/article[1]/p[1]`；第二个循环项是 `article[2]`，价格对应 `/html/body/section[1]/article[2]/p[1]`。链接的两列使用同一个元素路径，靠 `nodeType` 区分读取文字还是 href。

**`isDescendents:true` 记录子元素模式，真正说明每列如何定位的是字段的 `relative`、`relativeXPath`。** `collectMultiWithPattern()` 不再遍历子元素，它只发送预览阶段已经生成的参数。这里的子元素字段没有 `extractType`，也没有流程图随后补充的 `default`、`beforeJS` 等键。

#### 13.3 只选部分元素：同一个函数改发 pathList

回到第 13.1 节三个价格的页面，若只保留第一个和第三个 `p`，共同路径仍匹配 3 个，但 `nodeList.length=2`，所以 `detectAllSelected()` 为 false。此时完整内层消息为：

```json
{
  "type": "multiCollectWithPattern",
  "history": 3,
  "tabIndex": -1,
  "loopType": 2,
  "iframe": false,
  "xpath": "",
  "allXPaths": "",
  "isDescendents": false,
  "parameters": [
    {
      "nodeType": 0,
      "contentType": 0,
      "relative": true,
      "name": "参数1_文本",
      "desc": "",
      "extractType": 0,
      "relativeXPath": "",
      "allXPaths": "",
      "exampleValues": [{"num": 0, "value": "￥99"}],
      "unique_index": "demo-price",
      "iframe": false
    }
  ],
  "pathList": ["/html/body/section[1]/p[1]", "/html/body/section[1]/p[3]"]
}
```

外层仍按第 2 节包装。`pathList` 在扩展发送时是数组；流程图保存循环节点时才用 `join("\n")` 转成多行字符串。预期只提取 `￥99`、`￥79` 两行。

如果部分选择的是商品块，循环范围同样改成 `pathList`，`isDescendents:true` 和块内 `/p[1]`、`/a[1]` 字段继续保留。例如第 13.2 节商品块有 id，`readXPath(node,0)` 可生成 `//*[@id="java"]` 等路径。

#### 13.4 三种采集消息对照

| 操作 | 内层 type | 循环范围 | 字段 relativeXPath | 结果含义 |
|---|---|---|---|---|
| 单元素或无规律多元素 | singleCollect / multiCollectNoPattern | 本次消息不新建循环 | 各字段的绝对路径 | 多列组成同一条记录 |
| 提取全部价格元素 | multiCollectWithPattern | loopType 1，共同 xpath | `""` | 每个循环项自身提供一行 |
| 提取全部商品块的子元素 | multiCollectWithPattern | loopType 1，商品块 xpath | `/p[1]`、`/a[1]` | 每个商品块提供一行、多列 |
| 只提取部分价格或商品块 | multiCollectWithPattern | loopType 2，pathList | 自身为空，子元素为块内路径 | 按明确列出的循环项提取 |

“选中全部”先改变选择状态，确认采集才发送操作消息；它没有一个叫 `collectAll` 的独立消息类型。

### 14. detectAllSelected()：实际只比较数量

```js
if (global.app._data.nowPath == "") {
    return false;
}
// evaluate(nowPath)，iterateNext() 枚举全部匹配，累计 num
return num == global.nodeList.length;
```

| 当前共同路径匹配数 | 已选数 | 返回 | 后续消息 |
|---:|---:|---|---|
| 3 | 3 | true | loopType 1，共同 xpath |
| 3 | 2 | false | loopType 2，明确 pathList |
| 路径为空 | 任意 | false | loopType 2 |

它没有逐个比较节点身份，只比较数量。所以要结合前面的选择算法保证已选节点确实属于这个范围。函数也没有在这里 try/catch 无效 XPath。

普通同类多元素参数的 `relativeXPath=""`，代表循环项自身；商品块内部字段的路径如 `/p[1]`，代表循环项内的价格。两种情况都可以通过这个采集函数传输，但含义不同。

## 第五部分：三个循环发送函数的基本逻辑与例子

### 15. 循环类型先统一记清

| `loopType` | 含义 | 常见发送函数 |
|---:|---|---|
| 0 | 反复操作单个元素 | `sendLoopClickSingle()` |
| 1 | 共同 XPath 决定的不固定元素列表 | 有规律采集、逐个点击、逐个移动 |
| 2 | 逐条 pathList 决定的固定元素列表 | 未选中共同范围的全部元素时 |
| 3 | 文本列表 | `input(value,true)` |

这些是操作消息中的循环类型，不是树的层数，也不是字段 nodeType。

### 16. sendLoopMouseMove()：给每个循环项悬停

例子：共同路径能找到三张卡片，当前选了其中两张。

1. 初始化 `type:"loopMouseMove"`、`useLoop:true`、`loopType:1`，`xpath`、`allXPaths`、`content` 均为空字符串。
2. `detectAllSelected()` 返回 false，改 `loopType=2`。
3. 创建 `pathList=[]`，按已选顺序写入这两张卡片的 `readXPath(node,0)`。
4. 发送固定列表循环移动消息。流程图建循环 option 8，再把内部移动节点 xpath 设为空，添加 option 7。

若三张都已选，保留 loopType 1，并把 `nowPath` 写进 xpath。**这个函数没有像有规律采集那样填入 nowAllPaths**；allXPaths 保持空字符串。

#### 16.1 只悬停第一张和第三张卡片，消息是什么

假设三张卡片没有 id 和 class，路径分别为 `/html/body/section[1]/article[1]` 至 `article[3]`。当前只选择第 1、3 张，完整内层消息为：

```json
{
  "type": "loopMouseMove",
  "history": 3,
  "tabIndex": -1,
  "xpath": "",
  "allXPaths": "",
  "content": "",
  "useLoop": true,
  "iframe": false,
  "loopType": 2,
  "pathList": ["/html/body/section[1]/article[1]", "/html/body/section[1]/article[3]"]
}
```

外层按第 2 节包装。如果三张全部选中，完整内层对象则为：

```json
{
  "type": "loopMouseMove",
  "history": 3,
  "tabIndex": -1,
  "xpath": "/html/body/section[1]/article",
  "allXPaths": "",
  "content": "",
  "useLoop": true,
  "iframe": false,
  "loopType": 1
}
```

全选分支没有 `pathList` 键。流程图的循环保存这些卡片路径，内部移动节点使用 `useLoop:true`、`xpath:""`，表示悬停当前卡片。

### 17. sendLoopClickEvery()：逐个点击列表中的元素

例子：选择 D、G 两个商品链接。

1. 初始化 `type:"loopClickEvery"`、`id`、`useLoop:true`、`loopType:1` 和元数据。
2. 同样通过 `detectAllSelected()` 选择共同 XPath 或固定路径列表。
3. 全选时写 `xpath=nowPath`；部分选择时填 `pathList`。
4. 发送后流程图先建循环，再将消息中的内部 xpath 清空并创建点击节点 option 2。

这里空的内部 xpath 表示点击当前循环项。发送函数只记录循环范围，没有在浏览器中用 JavaScript for 循环逐个 `.click()`。

#### 17.1 两个商品链接全部选中时的完整消息

用第 13.2 节的两个商品块，选中的是块内两个 `a`，共同路径为 `/html/body/section[1]/article/a`。点击“循环点击每个链接”后，完整内层消息为：

```json
{
  "type": "loopClickEvery",
  "id": "C123456",
  "history": 3,
  "tabIndex": -1,
  "xpath": "/html/body/section[1]/article/a",
  "allXPaths": "",
  "content": "",
  "useLoop": true,
  "iframe": false,
  "loopType": 1
}
```

外层按第 2 节包装。若页面有三个商品链接，仍只选第 1、3 个，固定列表分支的完整内层消息为：

```json
{
  "type": "loopClickEvery",
  "id": "C123456",
  "history": 3,
  "tabIndex": -1,
  "xpath": "",
  "allXPaths": "",
  "content": "",
  "useLoop": true,
  "iframe": false,
  "loopType": 2,
  "pathList": ["//*[@id=\"java\"]/a[1]", "//*[@id=\"third\"]/a[1]"]
}
```

这里假设第 1、3 个商品块的 id 分别为 java、third。即使 `a` 本身没有 id，`readXPath(a,0)` 递归到有 id 的父块时，也会生成这种路径。流程图最终得到“遍历链接 → 点击当前链接”的结构，`loopClickEvery` 的内部点击节点还会设置 `newTab:1`。

### 18. sendLoopClickSingle(name)：单元素循环与翻页

这个函数不使用 `detectAllSelected()`，总是从首个已选节点取路径：

```js
// 初始关键字段
type: "loopClickSingle",
useLoop: true,
loopType: 0,
nextPage: false,
lastAction: global.app._data.lastAction
```

还带 `id`、`history`、`tabIndex`、`iframe`、`content`、`xpath`、`allXPaths`。

| 调用 | 判断步骤 | 最终变化 |
|---|---|---|
| `sendLoopClickSingle()` | name 为空，两个特殊判断都不满足 | 保留 loopClickSingle，nextPage false |
| `sendLoopClickSingle("下一页元素")` | 命中中文名称判断 | nextPage true，type 仍是 loopClickSingle |
| `sendLoopClickSingle("nextPageFromIndexPage")` | 命中特殊入口名称 | nextPage true，type 改为 loopClickNextPage |

最后一种例子：刚完成有规律采集，`lastAction="collectDataWithLoop"`；用户指定下一页按钮并确认，操作台传特殊名称。流程图收到 `loopClickNextPage` 后，根据 lastAction 是否含 `WithLoop`，调整插入位置，把已有采集操作放入合适的翻页循环结构。

不能只看到 nextPage true 就认定两个消息完全一样：内层 type 不同，流程图走的处理分支也不同。

#### 18.1 循环点击“加载更多”：反复定位同一个按钮

独立的小页面为 `<body><button id="more">加载更多</button></body>`。右键选中按钮 → 点击“循环点击该按钮”，操作台调用 `loopClickSingleElement()`，本例名称不是“下一页元素”，消息函数相当于调用 `sendLoopClickSingle("按钮")`。

假设发送前 `lastAction="collectData"`，完整内层消息为：

```json
{
  "type": "loopClickSingle",
  "id": "C123456",
  "history": 3,
  "tabIndex": -1,
  "useLoop": true,
  "iframe": false,
  "content": "加载更多",
  "xpath": "//*[@id=\"more\"]",
  "allXPaths": ["/html/body/button[1]", "//button[contains(., '加载更多')]", "id(\"more\")", "/html/body/button"],
  "loopType": 0,
  "nextPage": false,
  "lastAction": "collectData"
}
```

将它赋给 `message` 后，发送步骤是：

```js
const message_action = {
    type: 3,
    from: 0,
    message: {pipe: JSON.stringify(message)}
};
global.ws.send(JSON.stringify(message_action));
```

真正传给 `ws.send()` 的字符串内容如下。为了直接看转义，这里展示紧凑的线上 JSON；`pipe` 的值是一段字符串：

```json
{"type":3,"from":0,"message":{"pipe":"{\"type\":\"loopClickSingle\",\"id\":\"C123456\",\"history\":3,\"tabIndex\":-1,\"useLoop\":true,\"iframe\":false,\"content\":\"加载更多\",\"xpath\":\"//*[@id=\\\"more\\\"]\",\"allXPaths\":[\"/html/body/button[1]\",\"//button[contains(., '加载更多')]\",\"id(\\\"more\\\")\",\"/html/body/button\"],\"loopType\":0,\"nextPage\":false,\"lastAction\":\"collectData\"}"}}
```

流程图先创建循环，再把消息中的 `xpath` 清空给内部点击节点使用：

```text
循环（option=8，loopType=0，xpath=//*[@id="more"]）
└── 点击元素（option=2，useLoop=true，xpath=""）
```

父循环保存“加载更多”的定位；内部点击操作使用当前循环项。这里记录的是“反复定位并点击同一个位置”，而逐个点击列表用的是 `loopClickEvery`、`loopType:1/2`。

发送函数只发这一条操作消息，没有点击次数、间隔或退出条件字段。执行多少次、什么时候退出，要继续查看流程图循环参数和执行器。消息中的 `lastAction` 是发送前的值，操作台发送后才把它改成 `clickElementWithLoop`。

#### 18.2 直接循环点击“下一页”：type 仍为 loopClickSingle

换成 `<body><a id="next" href="?page=2">下一页</a></body>`，选中它后直接点击循环点击入口。操作台 `tname()` 返回“下一页元素”，调用 `sendLoopClickSingle("下一页元素")`。完整内层消息为：

```json
{
  "type": "loopClickSingle",
  "id": "C123456",
  "history": 3,
  "tabIndex": -1,
  "useLoop": true,
  "iframe": false,
  "content": "下一页",
  "xpath": "//*[@id=\"next\"]",
  "allXPaths": ["/html/body/a[1]", "//a[contains(., '下一页')]", "id(\"next\")", "/html/body/a"],
  "loopType": 0,
  "nextPage": true,
  "lastAction": "collectData"
}
```

外层按第 2 节包装。相对于“加载更多”例子，按钮路径、文字换了，`nextPage` 变为 true，内层 `type` 仍为 `loopClickSingle`。流程图将循环标题设为“循环点击下一页”，并创建内部点击节点。

#### 18.3 采集后进入“设置翻页操作”：type 为 loopClickNextPage

先完成第 13.2 节的商品块采集，再从空选择界面进入“设置翻页操作” → 选中同一个下一页链接 → “确认设置翻页操作”。入口链为：

```text
confirmNextPage()
→ loopClickSingleElement("nextPageFromIndexPage")
→ sendLoopClickSingle("nextPageFromIndexPage")
```

此前有规律采集留下 `lastAction="collectDataWithLoop"`，所以完整内层消息是：

```json
{
  "type": "loopClickNextPage",
  "id": "C123456",
  "history": 3,
  "tabIndex": -1,
  "useLoop": true,
  "iframe": false,
  "content": "下一页",
  "xpath": "//*[@id=\"next\"]",
  "allXPaths": ["/html/body/a[1]", "//a[contains(., '下一页')]", "id(\"next\")", "/html/body/a"],
  "loopType": 0,
  "nextPage": true,
  "lastAction": "collectDataWithLoop"
}
```

外层仍为 `type:3`、`from:0`，`message.pipe=JSON.stringify(message)`。同一个下一页链接，由不同操作台入口产生不同的操作类型。流程图在 `loopClickNextPage` 分支判断 `lastAction.includes("WithLoop")`，调整插入位置，并将已有商品块采集循环剪切到翻页循环中，形成：

```text
翻页循环（loopType=0，定位“下一页”）
├── 商品块循环（loopType=1，遍历当前页 article）
│   └── 提取价格、链接文本、链接地址
└── 点击下一页（useLoop=true，xpath=""）
```

如果上次是普通采集，`lastAction` 会是 `collectData`，流程图按没有已有采集循环的情况安排位置。`nextPage:true` 自身没有携带商品字段；已有采集操作通过流程图编辑逻辑移入翻页循环。

## 第六部分：发送后与反向试运行入口

### 19. clearAfterSend() 当前只设置一个标志

```js
function clearAfterSend() {
    global.justSend = true;
    // 原有延迟 clearEl 的代码已经注释
}
```

它不关闭 WebSocket、不清选择、不等回执。实际清选择由 toolkit 的确认方法、点击方法等完成。`trial.js` 中原来根据 `justSend` 忽略试运行的分支也已注释，因此不能把标志解释成有效的防重复机制。

### 20. 通知清理定时器

本模块每 3000ms 检查 `notification_of_easyspider` 元素；按 `dataset.timestamp` 计算年龄，超过 10000ms 且父节点仍为 body 时删除。通知正常退出动画在 `trial.js` 的 `createNotification()` 中，这里是额外清理。

`getElementsByClassName()` 返回实时集合，正序遍历时删除元素可能使紧邻的旧通知在这一轮被跳过，下一轮再清理。它不处理采集字段，也不会删除流程图节点。

### 21. trial 消息只在这里转交，标记定位留到第 25 篇

下面是“标记提取字段”的消息结构示例：

```json
{
  "type": "trial",
  "message": {
    "type": 4,
    "message": {
      "type": 0,
      "node": "{\"option\":3,\"parameters\":{\"params\":[{\"relative\":true,\"relativeXPath\":\"/p[1]\"}]}}",
      "parentNode": "{\"parameters\":{\"loopType\":1,\"xpath\":\"/html/body/section[1]/article\"}}"
    }
  }
}
```

1. 扩展 onmessage parse 最外层，识别 type trial。
2. 调用 `trial(evt)`，仍传完整对象。
3. `trial.js` 再 parse `evt.message.message.node` 与 `parentNode`，得到流程图节点及父循环。
4. 内层 `type=0` 表示标记；字段定位由 `/html/body/section[1]/article` 和 `/p[1]` 组合。

这里的字段与父节点对象只保留本例定位需要的键，用于讲清嵌套层级。第 25 篇会区分“页面标记”与“Electron 真正试运行”，不能把两者都归成扩展执行器。

## 第七部分：把扩展完整串成一条线

### 22. 有规律采集的正向与反向闭环

```text
网页节点 B、C 被选中
          │
          ▼
global.js：handleDescendents → outputParameters → generateValTable
          │
          ▼
toolkit.vue：展示预览 → 用户确认
          │
          ▼
messageInteraction.js：collectMultiWithPattern
          │ 外层 type=3，from=0，pipe=操作 JSON
          ▼
Electron main.js：转发 pipe
          │
          ▼
流程图 logic.js：handleAddElement
          │
          ├── 添加循环 option=8 与提取 option=3
          └── 增加字段编号 → from=1 → Electron → 扩展存储
```

走到这里，扩展的选择、匹配、字段生成、预览、确认、消息传输已经连上。第 24 篇先看 Electron 怎样处理调试请求和发送结果，第 25 篇再追插件怎样接收消息、标回网页并显示条件与通知。

### 23. 对照源码的练习

1. 普通 input 的两条消息分别交给谁、有什么不同的外层 type？
2. 共同路径匹配 5 个节点，用户只选 3 个，有规律采集的 loopType、xpath、pathList 怎么填？
3. collectMultiWithPattern 缩减样例时，原来的全局数组是否改变？
4. 字段生成从编号 6 开始，确认新增 4 列后，编号消息怎样走回扩展？
5. sendLoopMouseMove 和 collectMultiWithPattern 在全选时，都有完整 allXPaths 吗？
6. 收到 trial 消息时，本文件自己会执行点击、采集或条件判断吗？请继续读第 25 篇“调试功能详解”。

## 第八部分：补充两条从 MV2 迁移到 MV3 的开发背景

### 24. 为什么每个标签页都有一个 ID，并各自建立 WebSocket

按照项目作者的开发经历，原本准备让扩展后台常驻，由后台统一与 Electron 通信：标签页先把消息交给后台，再由后台转发。后来从 Manifest V2 迁移到 Manifest V3 时，原先依赖常驻后台的方案没有继续沿用，项目最终改为每个标签页各自建立 WebSocket，直接与 Electron 收发消息。

这样 Electron 就会同时面对多个网页连接，需要知道消息来自哪个标签页，也需要把后续操作关联到对应网页。因此内容脚本生成 `global.id`，连接打开时通过 `type:0` 消息声明这个 ID，点击等操作消息也会携带它。这里的 ID 是项目自己生成的连接标识，不是 DOM 元素的 id，也不是 Chrome 提供的标签页 tabId。

所以，“每个标签页一个 ID”和“每个标签页一个 WebSocket”要放在同一次通信方案调整中理解：原先计划由后台集中转发，后来改为网页连接直接对接 Electron。这是本项目迁移时形成的实现选择。

### 25. 为什么共享变量改成 global.xxx

项目早期直接定义全局变量，各脚本按这种方式访问 `nodeList`、`outputParameters`、`ws` 等共享状态。后来迁移到 MV3，代码引入了模块化与打包过程。打包后，原先依赖的外部变量不再能按旧方式直接识别和访问，于是把这些共享变量包装进一个对象，在 `global.js` 中导出，再由需要它的模块导入。

因此现在看到的是 `global.nodeList`、`global.outputParameters`、`global.ws`：`global.js` 保存共享对象，`toolkit.vue`、`messageInteraction.js` 等模块通过 import 访问同一个对象。例如操作台更新 `global.outputParameters`，消息模块就能读取这些参数，并通过 `global.ws.send()` 发送。

这里的 `global` 是项目自己定义并导出的普通对象。它把跨模块共享状态集中起来，使各模块通过明确的导入关系访问这些状态；这种写法来自本项目适应模块化和打包的调整，并不是 MV3 规定变量必须叫 `global`。

---

返回目录：[README.md](README.md) ｜ 上一篇：[13.WebSocket：三进程实时通信的桥梁](13.WebSocket详解.md) ｜ 下一篇：[15.Flowchart 基本原理：消息到了，顺序、循环和判断怎样存](15.Flowchart基本原理.md)
