---
title: "21 · 消息到流程图节点"
description: "easyspider · 流程图与执行 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/21.消息到流程图节点.md"
originalUrl: "/originals/easyspider/chapter-21.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 21.消息怎样变成 Flowchart 节点：复用新增与移动入口

> 已经知道怎样从 root 建立数据、怎样画图、怎样增删改查。
>
> 现在回到第 14 篇的消息：接收一个 `batchInputText`，为什么会得到“地区循环 + 输入地区”两个节点？
>
> 每种消息都按“消息案例 → 对应代码与执行含义 → 处理后的案例”展开；修改节点的消息给出处理后的具体对象，复杂消息再逐步列出数组和锚点变化。

---

## 先把消息接到已经学过的编辑入口上

**阅读约定：本篇的消息对象是流程图接收端 JSON.parse 后得到的内层对象，网页地址、XPath 和示例值是教学假设。消息案例之后先给接收与参数代码，再给图结构、参数和正式执行的结果。** 外层 type=3 的通信信封不在每个案例中重复。

本篇覆盖 handleAddElement 的全部 14 种消息：batchInputText 在第 3～10 节完整推演；multiCollectWithPattern、singleCollect、multiCollectNoPattern、loopClickEvery、loopClickNextPage 在第 11～14 节；其余消息在第 15～22 节逐条展开。第 23～25 节补齐 title、notify，以及反向发送的 update_parameter_num。

第 18～20 讲已经能脱离消息完成搭图、渲染和编辑。现在接回第 14 讲：消息提供网页操作的类别与参数，接收端把它转换成刚学过的新增、修改或移动调用。

~~~text
手动操作：选择工具箱选项、插入锚点
                         ↓
                    toolBoxKernel
                         ↑
消息操作：handleAddElement → addElement(op, msg)

共同落点：
    在 nodeList 末尾创建对象
    在父 sequence 中插入稳定下标
    refresh 重建界面
    补默认参数，并在有消息时写入消息参数
~~~

以上是普通新增的共同路径；采集消息也可能只追加已有节点的字段，翻页消息还会移动旧子树。**消息没有带来另一套图结构，它决定怎样调用现有编辑能力。**

这里还要分开两个时刻：**收到操作消息时，下面的接收分支主要修改设计器里的节点与参数；正式运行任务时，Python 才按节点 option 执行保存的操作。** 录制期间对网页的即时操作也有明确入口：Electron 主进程处理外层 type=2 时调用 WebDriver 输入，处理外层 type=3 的点击消息时，在转发给流程图之后调用 WebDriver 点击。消息样例、源码和浏览器变化见 [第 24 讲 16.2 节](/easyspider/chapter-24#electron-browser-actions)。这里的 addElement 负责修改图结构。对应的正式执行入口来自 [easyspider_executestage.py](/source/?file=32b007a0fdf6d20e99.py) 的 executeNode：

| 节点 option | 正式执行函数 | 做什么 |
| --- | --- | --- |
| 1 | openPage | 打开网页并处理打开操作的配置 |
| 2 | clickElement | 定位并点击元素 |
| 3 | getData，随后 saveData | 按字段配置提取并处理输出 |
| 4 | inputInfo | 将固定值或循环值输入文本框 |
| 6 | switchSelect | 切换 select 下拉选项 |
| 7 | moveToElement | 将鼠标移到元素上 |
| 8 | loopExecute | 按循环类型提供本轮值、路径和索引，执行孩子 |

各案例中的执行结果假设页面元素存在、配置有效并正常执行；翻页的异常和退出分支另行说明。设计器中的 id、parentId、pId 仍采用当前源码的 actionSequence 索引规则，不使用第 18 讲“后续优化方向”的替代方案。

为了单独观察一条批量输入消息，下面从只有 root 和“打开网页”的两节点状态重新开始，不继续使用前三讲的五节点图，也不累加第 20 讲练习中的修改。

---

## 先把一次真实操作走完：输入“海淀、朝阳”之后，屏幕为什么多了两块

假设浏览器已经打开房源搜索页，流程图目前只有“打开网页”。你选中地区输入框，选择“批量输入”，输入两行地区：

~~~text
海淀
朝阳
~~~

你希望软件做的是：输入海淀、搜索并处理海淀，然后输入朝阳、搜索并处理朝阳。此刻扩展先负责告诉设计器“这里有一个输入框，要轮流输入这两行文字”。设计器收到消息后，先画出下面这部分结构：

~~~text
root
├─ 1（打开网页）
└─ 2（地区文字循环）
   └─ 3（输入地区）
~~~

**循环负责每轮取一个地区，输入节点负责把本轮地区写进输入框。** 一条批量输入消息生成两块，是因为“重复取值”和“输入动作”需要分别保存。本次消息还没有自动生成搜索、翻页和单间判断，后续要继续搭图。

先按用户能看到的变化，把一次接收拆成六步，再逐步读代码：

| 步骤 | 设计器做什么 | 此时的数据变化 |
| --- | --- | --- |
| 1 | 收到 batchInputText 操作消息 | 消息里有两个地区和输入框 XPath |
| 2 | 创建循环节点 2 | nodeList 末尾增加一个对象 |
| 3 | 把循环接到 root 下 | root.sequence 从 [1] 变成 [1,2]；1=打开网页，2=地区循环 |
| 4 | 把下一次插入位置改到循环内部 | nowArrow 指向循环 2 内第一个孩子之前 |
| 5 | 创建输入节点 3 并接入循环 | 2.sequence 从 [] 变成 [3]；3=输入地区 |
| 6 | 两个节点分别接收参数，再显示选中状态 | 循环存 textList，输入存输入框路径和 useLoop=true |

本篇前半段始终使用这四个节点，避免一上来混入十三节点完整图。为了和前文房源任务对应，正文用“地区循环”“输入地区”作业务名称；源码自动生成的标题分别是“循环输入文字”和工具箱中的输入操作标题，用户也可改名。后半段其他消息各自从说明的起点推演，不把不同例子的新增编号累加。

---

## 第一部分：先确认是谁在接消息

### 1. FlowChart 页面加载的是普通脚本

先想一个最具体的问题：扩展已经发出“批量输入”，应该由哪个页面把它变成方块？接收者是任务设计窗口中的 FlowChart 页面。这个页面加载 logic.js，建立 WebSocket；它又加载 FlowChart.js，提供造节点、插入和重画的函数。浏览器扩展里选中的 DOM 元素不会直接成为流程图里的 DOM 方块。

这里有两个页面：房源网页上的输入框，是要被自动化操作的对象；设计器里的“输入地区”方块，是描述这个操作的数据和界面。消息把前者的定位信息交给后者。

例如主进程收到外层 type=3 的信封后，把 message.pipe 中的操作文本转交给流程图连接。流程图再 JSON.parse，一条 batchInputText 消息才进入 handleAddElement。下面的源码表和接收回调分别对应这两层职责。

查看 [FlowChart_CN.html](/source/?file=9bc3327fb264a3fe95.html)，搜索 `FlowChart.js` 和 `logic.js`。

这部分使用 Vue、jQuery 和普通脚本组织页面；不存在本组讲义假设的 `FlowChart.vue` 文件。

| 源码 | 本篇要看的职责 |
| --- | --- |
| [logic.js](/source/?file=786aaf2ec8ee7dbd78.js) | WebSocket 接收、按消息类型分发、补操作参数 |
| [FlowChart.js](/source/?file=48b61e5e4ebaa6ccf2.js) | 新节点对象、孩子连接、锚点、刷新 |
| [main.js](/source/?file=5b1dab0d6ae24484fc.js) | Electron 主进程转发消息 |
| [messageInteraction.js](/source/?file=1a2b7d0e84fb34fe83.js) | 扩展发送操作消息 |

第 14 篇发送的外层信封经过主进程处理后，流程图接收回调读取操作对象：

~~~js
ws.onmessage = function (evt) {
  evt = JSON.parse(evt.data);
  if (evt["type"] == "title") {
    // 更新任务标题
  } else if (evt["type"] == "notify") {
    // 显示通知
  } else {
    handleAddElement(evt);
  }
};
~~~

这是 `logic.js` 的实际分发结构。`title` 和 `notify` 不会被当成普通操作插入节点。

### 2. 三种 type 再对一下

同样看到 type，先问“现在读的是哪一个对象”。把这次输入操作分开看：

| 所在层 | 具体取值 | 这一层回答什么问题 |
| --- | --- | --- |
| 扩展发出的外层信封 | 数字 3 | 消息应该走哪条通信路由 |
| 信封里的操作对象 | 字符串 batchInputText | 设计器应该创建什么操作组合 |
| 新建循环节点对象 | 数字 1 | newNode 应该画循环框还是普通方块 |
| 新建循环节点的 option | 数字 8 | 正式执行时应该调用哪种执行函数 |

所以“type=1”和“option=8”可以同时出现在同一个循环节点中：前者描述外观类别，后者描述操作类别。不要把外层数字 3 当成“提取数据 option=3”。下面把三个 type 的例子并排写出来。

~~~text
外层消息 type=3：消息路由类型，前面通信篇讲过
操作消息 type="batchInputText"：告诉接收端这是批量输入
流程图节点 type=1：告诉 newNode 画一个循环框
~~~

相同字段名，所在对象不同。`handleAddElement` 主要检查字符串操作类型，再把它映射成数字 `option`。

### 3. batchInputText：消息案例

先对照用户刚才做的动作读字段：value 是两行地区；xpath 是选中的地区输入框；loopType=3 表示固定文本列表；useLoop=true 表示输入动作要取循环本轮提供的值。

这条消息没有 index、父节点和 sequence。发送端知道“操作网页中的哪个元素”，但插到哪个循环、排在谁后面，要由设计器当前锚点决定。下面对象是接收端示意参数，不是完整任务 JSON。

~~~js
const msg = {
  type: "batchInputText",
  value: "海淀\n朝阳",
  loopType: 3,
  xpath: "//input[@id='area']",
  allXPaths: ["//input[@id='area']"],
  useLoop: true,
  history: 1,
  tabIndex: -1,
  iframe: false
};
~~~

这是用于讲解接收端的关键字段对象，省略了发送端可能附带的页面元数据。`value` 里是真实换行，循环节点会把它放进 `textList`。

---

## 第二部分：一条批量输入消息，为什么创建两项

### 4. handleAddElement 没有直接 push 消息

如果只创建一个普通输入节点，它只保存一次输入；如果只创建一个空循环，循环又没有真正输入的动作。因此接收器明确调用两次 addElement。

两次调用都传入同一个 msg，但 op 不同：第一次 op=8，modifyParameters 把 value 当作循环的 textList；第二次 op=4，把 XPath 和 useLoop 写到输入节点。**同一份网页消息，经过不同操作类型的解释，产生不同职责的两个节点。**

两次新增完成后，代码再选中输入节点的父循环，方便用户接着调整循环文本。最后的 click 改的是设计器选中状态，不是去房源网站点击一个按钮。

下面摘取 handleAddElement 的对应 else if 分支；它属于完整接收方法：

~~~js
} else if (msg["type"] == "batchInputText") {
  addElement(8, msg);
  addElement(4, msg);
  let parentNode =
    nodeList[actionSequence[app._data.nowNode["parentId"]]];
  let parentId = parentNode["id"];
  $("#" + parentId).click();
}
~~~

两次 `addElement`：

~~~text
addElement(8, msg)：先建立循环
addElement(4, msg)：再建立循环里的输入
~~~

消息对象不是一个可直接执行的完整节点。接收端会补结构字段、公共参数和操作默认值。

### 5. 从已经打开网页的状态开始

先把“现在在哪里插入”算清楚。root 已经有孩子 1（打开网页），所以 root.sequence 长度为 1；最后一个孩子的位置是 0。把锚点放在它后面，就是父节点 root、位置 0。

| 字段 | 当前值 | 代入本例的意思 |
| --- | --- | --- |
| nowArrow.pId | 0 | 父容器的界面 id 为 0，也就是 root |
| nowArrow.position | 0 | 插在父容器第 0 个孩子之后，也就是打开网页之后 |
| position+1 | 1 | 真正传给 splice 的插入下标 |
| nowArrow.num | 0 | 用于界面更新锚点状态，不是要插入的节点编号 |

如果 position=-1，同一个新增操作就会排到打开网页前面；如果 pId 换成某个循环的界面 id，新对象就会进入那个循环。先读下面的起始快照，后面每一步都从它继续。

我们从第 15 篇房源图的前两项起步：

~~~text
nodeList[0] root：sequence=[1]
nodeList[1] 打开网页：sequence=[]

actionSequence=[0,1]
nowArrow={pId:0, position:0, num:0}
~~~

`nowArrow` 表示插入位置：

~~~text
pId=0：插在 root 里面
position=0：插在 root.sequence 的第 0 个孩子之后
~~~

它不是“鼠标坐标”；它是结构中的插入位置。

### 6. addElement 设置操作类型，然后进入 toolBoxKernel

现在执行第一句 addElement(8,msg)。8 是“新增循环”操作号，代码先设置全局工具箱状态 option，再调用统一的 toolBoxKernel。后者同时处理新增、复制和剪切，所以要先进入正确分支。

创建前 nodeList.length=2，新节点取 index=2。push 后，新节点真正位于 nodeList[2]；它的 sequence 还是空的，表示尚无循环体操作。此时 id=0 是临时初始化值，随后的 refresh 会给它当前界面编号。

特别注意，toolBoxKernel 里 option=10 表示剪切工具，而保存到节点对象的 option=10 表示条件分支；两者位于不同语境。本次 option=8 走新增路径，不会进入剪切分支。

~~~js
function addElement(op, param) {
  option = op;
  if (option == 1) {
    title = LANG("打开网页", "Open Page");
  } else {
    title = $(".options")[option - 1].innerHTML;
  }
  toolBoxKernel(null, param);
}
~~~

`addElement(8,msg)` 把工具箱当前操作设成循环。真正造对象在 `toolBoxKernel` 的新增分支：

~~~js
let l = nodeList.length;
let t = {
  id: 0,
  index: l,
  parentId: 0,
  type: 0,
  option: option,
  title: title,
  sequence: [],
  isInLoop: false,
};
nodeList.push(t);
if (option == 8) {
  t["type"] = 1;
}
~~~

此刻：

~~~text
l=2
新循环的 index=2
nodeList.length 从 2 变成 3
~~~

`id:0` 只是刷新前的临时值。它不是说新节点会与 root 永久共用编号。

### 7. 只 push 还不够，还要挂进父节点

可以把“创建对象”和“连到树里”分成两件事：新对象已经存在于数组第 2 项，但如果 root 的孩子列表仍然只有 [1]，从 root 出发就走不到它，刷新也不会把它画出来。

下面这句嵌套下标按四步代入：先用 pId=0 查 actionSequence，得到父数组下标 0；再取 nodeList[0]；再取这个父节点的 sequence；最后在下标 1 插入新孩子 2。

| 操作前 | 本次动作 | 操作后 |
| --- | --- | --- |
| nodeList 有 0（root）、1（打开网页）、2（新循环） | 不移动任何已有对象 | 三个对象数组位置保持原样 |
| root.sequence=[1] | 在位置 1 插入数字 2 | root.sequence=[1,2] |
| 新循环.sequence=[] | 本次还没创建输入孩子 | 仍为 [] |

这也解释了为什么父列表存数字，不再完整拷贝一个循环对象：对象统一放在 nodeList，父节点只记录有序的下标引用。

源码：

~~~js
let position = parseInt(app._data.nowArrow["position"]);
let pId = app._data.nowArrow["pId"];
nodeList[actionSequence[pId]]["sequence"]
  .splice(position + 1, 0, t.index);
refresh();
~~~

代入：

~~~text
pId=0
actionSequence[0]=0
position+1=1
t.index=2
~~~

于是：

~~~js
nodeList[0].sequence.splice(1, 0, 2);
~~~

结果：

~~~text
root.sequence：[1] → [1,2]
循环.sequence：[]
~~~

对象进数组叫“分配存储位置”；下标插进父 `sequence` 才叫“成为当前图的一部分”。

### 8. 新循环把下一次插入位置改到自己内部

第一轮新增结尾，循环已经接入 root，refresh 也已完成。代码把锚点改成“循环里面、第一个孩子之前”，随后第二次 addElement(4,msg) 才发生。

| 时刻 | nowArrow 指向哪里 | 接着新增会得到什么 |
| --- | --- | --- |
| 收到消息之前 | root 内打开网页之后 | 创建地区循环 2，挂到 root |
| 创建循环之后 | 循环 2 内、位置 -1 | 创建输入节点 3，挂到循环 2 |
| 创建输入之后 | 输入节点 3 后面 | 用户下一次手动新增搜索，可接到同一地区循环 |

循环的 id 在这个小图中恰好等于 index=2。第 18、19 讲已经用后来加入的循环演示过两者分开的情况；这里的 pId 同样必须当作界面 id 翻译。下面代码的 position=-1、pId=t.id 两个值缺一不可。

刷新以后，新增分支先补参数，再执行：

~~~js
if (option == 8) {
  app._data.nowArrow = {
    position: -1,
    pId: t["id"],
    num: 0
  };
  $("#" + t["id"]).click();
}
~~~

此时循环 2 在本小图的界面编号也恰好是 2：

~~~text
nowArrow={pId:2, position:-1}
~~~

`position=-1` 意味着在第一个孩子之前插入，`splice(position+1,0,...)` 的位置就是 0。

随后 `addElement(4,msg)` 新建输入 3：

~~~text
nodeList[3] = 输入地区
nodeList[2].sequence.splice(0,0,3)

root.sequence=[1,2]
地区循环.sequence=[3]
~~~

所以“自动包在循环里”的关键，不是看 `useLoop` 猜父节点，而是**循环创建后主动改变了插入锚点**。

---

## 第三部分：参数怎样落到正确节点

### 9. addParameters 先给默认值

接上树还不等于参数已经完整。比如用户手动新增点击时没有发送端消息，但它仍应有点击方式、点击后等待和是否新标签页的初值。因此每个新节点先经过 addParameters。

对于刚才的两个节点，先发生的默认设置是：

| 字段 | 循环 2 的默认值 | 输入 3 的默认值 | 之后是否会被消息覆盖 |
| --- | --- | --- | --- |
| useLoop | false | false | 输入节点会改为 true |
| xpath | 空字符串 | 空字符串 | 两个节点均接收消息中的路径 |
| loopType | 0 | 不适用 | 循环改为 3 |
| textList | 空字符串 | 不适用 | 循环改为两行地区 |
| value | 不适用 | 空字符串 | 输入节点保存消息中的 value |

实际顺序是先 addParameters，再 modifyParameters；若反过来，默认值会把消息值覆盖掉。下面先看公共默认值，操作专属默认值则在同一个函数按 option 添加。

`toolBoxKernel` 中新节点建立连接、刷新以后：

~~~js
addParameters(t);
if (param != null) {
  modifyParameters(t, param);
}
~~~

`addParameters` 的公共参数包括：

~~~js
t["parameters"] = {
  history: 1,
  tabIndex: 0,
  useLoop: false,
  xpath: "",
  iframe: false,
  wait: 0,
  waitType: 0,
  beforeJS: "",
  beforeJSWaitTime: 0,
  afterJS: "",
  afterJSWaitTime: 0,
  waitElement: "",
  waitElementTime: 10,
  waitElementIframeIndex: 0
};
~~~

循环另外补 `loopType`、`pathList`、`textList`、`exitCount`、`exitElement`、历史等待和脚本退出参数等。输入节点补 `value`、输入框索引等。

这样通过工具箱手动新增、没有传入消息时，也有一套初始参数。

### 10. modifyParameters 分别读同一个消息

进入操作专属分支之前，modifyParameters 先把消息中的公共环境信息写入当前节点：

~~~js
t["parameters"]["history"] = param["history"];
t["parameters"]["tabIndex"] = param["tabIndex"];
t["parameters"]["iframe"] = param["iframe"];
~~~

后文每种新增消息也经过这三行，因此各节只重复展示与该操作有关的参数分支。

现在把同一个 msg 分别交给 option=8 和 option=4 的参数分支。循环需要“这一轮可取哪些文本”，所以写 textList；输入需要“往哪个输入框写、是否用循环值”，所以写 xpath 和 useLoop。

**处理后的节点对象。** 第 3 节的消息处理完后，`nodeList[2]` 和 `nodeList[3]` 如下。这里展示两个节点的完整数据字段，标题使用中文界面自动生成的名称；还没有手动改成“地区循环”和“输入地区”。这是设计器内存中的结果，此时不必先点击保存。

~~~json
[
  {
    "id": 2,
    "index": 2,
    "parentId": 0,
    "position": 1,
    "type": 1,
    "option": 8,
    "title": "循环输入文字",
    "sequence": [3],
    "isInLoop": false,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "useLoop": false,
      "xpath": "//input[@id='area']",
      "iframe": false,
      "wait": 0,
      "waitType": 0,
      "beforeJS": "",
      "beforeJSWaitTime": 0,
      "afterJS": "",
      "afterJSWaitTime": 0,
      "waitElement": "",
      "waitElementTime": 10,
      "waitElementIframeIndex": 0,
      "scrollType": 0,
      "scrollCount": 1,
      "scrollWaitTime": 1,
      "loopType": 3,
      "pathList": "",
      "textList": "海淀\n朝阳",
      "code": "",
      "waitTime": 0,
      "exitCount": 0,
      "exitElement": "//body",
      "historyWait": 2,
      "breakMode": 0,
      "breakCode": "",
      "breakCodeWaitTime": 0,
      "skipCount": 0,
      "allXPaths": ["//input[@id='area']"]
    }
  },
  {
    "id": 3,
    "index": 3,
    "parentId": 2,
    "position": 0,
    "type": 0,
    "option": 4,
    "title": "输入文字",
    "sequence": [],
    "isInLoop": true,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "useLoop": true,
      "xpath": "//input[@id='area']",
      "iframe": false,
      "wait": 0,
      "waitType": 0,
      "beforeJS": "",
      "beforeJSWaitTime": 0,
      "afterJS": "",
      "afterJSWaitTime": 0,
      "waitElement": "",
      "waitElementTime": 10,
      "waitElementIframeIndex": 0,
      "value": "海淀\n朝阳",
      "index": 0,
      "allXPaths": ["//input[@id='area']"]
    }
  }
]
~~~

上面的数组依次展示 `nodeList[2]`、`nodeList[3]`，不是整个 `nodeList`；原来的 root 和打开网页仍在下标 0、1。此时 `nodeList[0].sequence=[1,2]`、`actionSequence=[0,1,2,3]`。循环的 `sequence=[3]` 与输入的 `parentId=2` 对上了；输入的 `isInLoop=true` 是刷新结构得出的，`parameters.useLoop=true` 则是消息写入的执行配置。

**后续案例的展示约定：** 为了集中观察变化，后文节点 JSON 只列结构和本次相关参数，省略的公共默认值仍然存在。它们是处理完成后的对象字段快照，不是重新赋值的代码，也不是完整任务文件。采集字段的默认值在第 11 节完整展示一份，后续重复字段只列关键项。

执行时并不是根据标题猜“最近的循环”。循环 2 取出海淀，调用输入 3 并传入海淀；输入看到 useLoop=true 后使用这个实参。下一轮同一个节点再收到朝阳。这里把“设计时保存参数”和“运行时传当前值”接了起来。

对循环 2：

~~~js
t["parameters"]["loopType"] = param["loopType"];
t["parameters"]["xpath"] = param["xpath"];
t["parameters"]["allXPaths"] = param["allXPaths"];
t["parameters"]["textList"] = param["value"];
~~~

得到：

~~~text
地区循环.parameters.loopType=3
地区循环.parameters.textList="海淀\n朝阳"
~~~

对输入 3：

~~~js
t["parameters"]["value"] = param["value"];
t["parameters"]["xpath"] = param["xpath"];
t["parameters"]["allXPaths"] = param["allXPaths"];
t["parameters"]["useLoop"] = param["useLoop"];
~~~

得到：

~~~text
输入地区.parameters.value="海淀\n朝阳"
输入地区.parameters.xpath=搜索框路径
输入地区.parameters.useLoop=true
~~~

执行时由于 `useLoop=true`，输入函数实际使用当前 `loopValue`，而不是把两行地区一次全部输入。

---

## 第四部分：其他消息怎样转换

### 11. multiCollectWithPattern：有规律采集生成“循环 + 提取”

**消息案例：multiCollectWithPattern。** 页面有 A、B 两张房源卡片，每张卡片里都有“标题”和“租金”。用户选择同类卡片后，希望每张卡片生成一行，行里有两列。示例接收对象如下；字段只列本例相关项，实际发送对象还可带字段描述、候选路径等元数据：

~~~json
{
  "type": "multiCollectWithPattern",
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "loopType": 1,
  "xpath": "//div[@class='house']",
  "allXPaths": ["//div[@class='house']"],
  "isDescendents": true,
  "parameters": [
    {"name":"标题", "nodeType":0, "contentType":0, "extractType":0,
     "relative":true, "relativeXPath":"/h2", "iframe":false,
     "exampleValues":[{"num":0,"value":"A单间"}]},
    {"name":"租金", "nodeType":0, "contentType":0, "extractType":0,
     "relative":true, "relativeXPath":"/span[@class='rent']", "iframe":false,
     "exampleValues":[{"num":0,"value":"2500元"}]}
  ]
}
~~~

**对应代码与执行含义。** 接收器先新增循环，再新增内部提取节点；循环负责当前是哪张卡片，提取节点负责每张卡片里读哪些字段。

先看应得到的职责分工：循环定位所有卡片，决定当前是 A 还是 B；提取节点在当前卡片里读标题和租金，决定这一行有哪些字段。不会为 A、B 分别生成两套固定采集节点，因为下一次页面上可能有更多卡片。

一个字段在消息和节点中的位置经历：

| 阶段 | 标题字段的位置 | 例子 |
| --- | --- | --- |
| 接收消息 | msg.parameters[0] | name=标题、relativeXPath 为卡片内标题路径 |
| 补执行默认值 | 同一个字段对象增加属性 | default=""、recordASField=1、downloadPic=0 |
| 写入提取节点 | 节点.parameters.params[0] | 标题成为这个采集动作的第 1 列 |

注意字段数组和操作参数对象虽然都叫 parameters，层次不同。下面两段原代码分别决定“新增几块”和“字段最终放在哪里”。

~~~js
} else if (msg["type"] == "multiCollectWithPattern") {
  addElement(8, msg);
  addElement(3, msg);
  changeOutputFormat(msg);
  notifyParameterNum(msg["parameters"].length);
}
~~~

循环确定每行的父元素；提取节点记录各列字段。

区别在两个同名 `parameters`：

~~~text
msg.parameters：字段数组
提取节点.parameters：操作参数对象
提取节点.parameters.params：字段数组最终放的位置
~~~

`modifyParameters` 对提取节点：

~~~js
for (let i = 0; i < param["parameters"].length; i++) {
  changeGetDataParameters(param, i);
}
t["parameters"]["params"] = param["parameters"];
~~~

`changeGetDataParameters` 补默认值、字段类型、是否记录、前后脚本、图片下载和分行等执行端需要的设置。

循环的参数由 modifyParameters 的 option=8 分支写入：

~~~js
t["parameters"]["loopType"] = param["loopType"];
t["parameters"]["xpath"] = param["xpath"];
t["parameters"]["allXPaths"] = param["allXPaths"];
~~~

**处理后的案例。** 独立从 root.sequence=[1]（打开网页）开始，收到这一条消息后：

~~~text
root.sequence=[1,2]
nodeList[2] 循环：option=8，sequence=[3]
  parameters.loopType=1
  parameters.xpath="//div[@class='house']"
nodeList[3] 提取：option=3
  parameters.params=[标题字段,租金字段]
~~~

正式执行时，loopExecute 依次提供 A、B 卡片的定位上下文，getData 在每张卡片内按相对路径读两列。假设 A 为“A单间、2500元”，B 为“B单间、2800元”，结果是两行、每行两列，而不是为 A、B 创建两套提取节点。两列还会通过 notifyParameterNum 通知扩展更新字段编号，详见第 25 节。

**处理后的节点对象（关键字段）。** 下面展开两列字段，并保留 changeGetDataParameters 给每列补出的全部默认项。

~~~json
[
  {
    "id": 2,
    "index": 2,
    "parentId": 0,
    "position": 1,
    "type": 1,
    "option": 8,
    "title": "循环采集数据",
    "sequence": [
      3
    ],
    "isInLoop": false,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "useLoop": false,
      "loopType": 1,
      "xpath": "//div[@class='house']",
      "allXPaths": [
        "//div[@class='house']"
      ]
    }
  },
  {
    "id": 3,
    "index": 3,
    "parentId": 2,
    "position": 0,
    "type": 0,
    "option": 3,
    "title": "提取数据",
    "sequence": [],
    "isInLoop": true,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "useLoop": false,
      "xpath": "",
      "clear": 0,
      "newLine": 1,
      "params": [
        {
          "name": "标题",
          "nodeType": 0,
          "contentType": 0,
          "extractType": 0,
          "relative": true,
          "relativeXPath": "/h2",
          "iframe": false,
          "exampleValues": [
            {
              "num": 0,
              "value": "A单间"
            }
          ],
          "default": "",
          "paraType": "text",
          "recordASField": 1,
          "beforeJS": "",
          "beforeJSWaitTime": 0,
          "JS": "",
          "JSWaitTime": 0,
          "afterJS": "",
          "afterJSWaitTime": 0,
          "downloadPic": 0,
          "splitLine": 0
        },
        {
          "name": "租金",
          "nodeType": 0,
          "contentType": 0,
          "extractType": 0,
          "relative": true,
          "relativeXPath": "/span[@class='rent']",
          "iframe": false,
          "exampleValues": [
            {
              "num": 0,
              "value": "2500元"
            }
          ],
          "default": "",
          "paraType": "text",
          "recordASField": 1,
          "beforeJS": "",
          "beforeJSWaitTime": 0,
          "JS": "",
          "JSWaitTime": 0,
          "afterJS": "",
          "afterJSWaitTime": 0,
          "downloadPic": 0,
          "splitLine": 0
        }
      ]
    }
  }
]
~~~

`parameters.params` 中保存的是两份字段配置对象，不是“标题字段”“租金字段”两个字符串。输入消息中的 `isDescendents` 没有在这里直接成为节点的同名顶层字段。

### 12. singleCollect：单元素采集可能不创建新节点

**消息案例：singleCollect。** 详情页上先选择标题，发送：

~~~json
{
  "type": "singleCollect",
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "parameters": [
    {"name":"标题", "nodeType":0, "contentType":0, "extractType":0,
     "relative":false, "relativeXPath":"//h1[@id='title']", "iframe":false,
     "exampleValues":[{"num":0,"value":"海淀单间"}]}
  ]
}
~~~

**对应代码与执行含义。** logic.js 对 singleCollect 和 multiCollectNoPattern 使用同一个分支，核心处理如下；省略追加后滚动字段表格的 setTimeout：

~~~js
if (msg["type"] == "singleCollect" || msg["type"] == "multiCollectNoPattern") {
  if (app._data.nowNode != null && app._data["nowNode"]["option"] == 3) {
    for (let i = 0; i < msg["parameters"].length; i++) {
      changeGetDataParameters(msg, i);
      app._data["nowNode"]["parameters"]["params"].push(msg["parameters"][i]);
    }
    changeOutputFormat(msg);
    app._data.params.parameters = app._data["nowNode"]["parameters"]["params"];
  } else {
    addElement(3, msg);
    changeOutputFormat(msg);
  }
  notifyParameterNum(msg["parameters"].length);
}
~~~

追加分支直接修改当前提取节点的 params；新建分支经过 addParameters、modifyParameters，把消息字段数组写入新节点的 parameters.params。它们正式运行时都由 option=3 对应的 getData 处理。

**处理后的案例。** 独立从 root.sequence=[1]、尚未选中提取节点开始，先采标题，再采租金：

| 次数 | 收到消息时选中谁 | 设计器的动作 | 结果 |
| --- | --- | --- | --- |
| 第 1 次采标题 | 没有选中提取节点 | 新建一个 option=3 的提取节点 | params 只有标题一列 |
| 第 2 次采租金 | 仍选中这个提取节点 | 在现有 params 数组末尾 push | 同一块提取数据有标题、租金两列 |
| 如果第 2 次先选中点击节点 | 当前 option=2 | 再新建一个 option=3 节点 | 两块独立采集动作 |

前两行对应 root.sequence 始终为 [1,2]：第一次新增提取 2，params=[标题]；第二次只将 nodeList[2].parameters.params 改为 [标题,租金]，nodeList.length 仍为 3。正式执行提取 2 时，一次 getData 按两份字段配置读出“海淀单间、2500元”这一行。

因此“消息的类型和内容”之外，当前 nowNode 也会影响处理结果。这个例子用来解释为什么用户点选状态会改变新增行为；它不是一条消息处理函数完全无状态的流水线。

`singleCollect` 和 `multiCollectNoPattern`：

~~~text
当前选中的 nowNode.option==3：
    给当前提取节点的 params 追加字段
否则：
    addElement(3,msg)，新建提取节点
~~~

例如单间详情页先选标题，再选租金。若当前仍选中同一个提取节点，第二次采集会增加一列，而非一定新增一块“提取数据”。

因此“收到一条消息=新建一个节点”这个规则不成立。

**处理后的节点对象（关键字段）。** 为把第二次采集也落到具体对象上，假设租金元素路径为 `//span[@id='rent']`，第二条 singleCollect 消息携带下面的租金字段。字段默认项沿用第 11 节，这里省略。

~~~json
{
  "第1次处理后：nodeList[2]": {
    "id": 2,
    "index": 2,
    "parentId": 0,
    "position": 1,
    "type": 0,
    "option": 3,
    "title": "提取数据",
    "sequence": [],
    "isInLoop": false,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "clear": 0,
      "newLine": 1,
      "params": [
        {
          "name": "标题",
          "nodeType": 0,
          "contentType": 0,
          "extractType": 0,
          "relative": false,
          "relativeXPath": "//h1[@id='title']",
          "iframe": false,
          "exampleValues": [
            {
              "num": 0,
              "value": "海淀单间"
            }
          ]
        }
      ]
    }
  },
  "第2次处理后：同一个nodeList[2]": {
    "id": 2,
    "index": 2,
    "parentId": 0,
    "position": 1,
    "type": 0,
    "option": 3,
    "title": "提取数据",
    "sequence": [],
    "isInLoop": false,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "clear": 0,
      "newLine": 1,
      "params": [
        {
          "name": "标题",
          "nodeType": 0,
          "contentType": 0,
          "extractType": 0,
          "relative": false,
          "relativeXPath": "//h1[@id='title']",
          "iframe": false,
          "exampleValues": [
            {
              "num": 0,
              "value": "海淀单间"
            }
          ]
        },
        {
          "name": "租金",
          "nodeType": 0,
          "contentType": 0,
          "extractType": 0,
          "relative": false,
          "relativeXPath": "//span[@id='rent']",
          "iframe": false,
          "exampleValues": [
            {
              "num": 0,
              "value": "2500元"
            }
          ]
        }
      ]
    }
  }
}
~~~

第二次只增加 `parameters.params[1]`；两份快照的 `id`、`index`、`parentId` 和 `sequence` 相同，`root.sequence` 都是 `[1,2]`。

#### 12.1 multiCollectNoPattern：同一消息携带多个不规则字段

**消息案例。** 页面标题和页脚电话不属于重复卡片，用户一起选择它们，发送两个绝对定位字段：

~~~json
{
  "type": "multiCollectNoPattern",
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "parameters": [
    {"name":"标题", "nodeType":0, "contentType":0, "extractType":0,
     "relative":false, "relativeXPath":"//h1", "iframe":false,
     "exampleValues":[{"num":0,"value":"房源详情"}]},
    {"name":"电话", "nodeType":0, "contentType":0, "extractType":0,
     "relative":false, "relativeXPath":"//footer/span[@class='phone']", "iframe":false,
     "exampleValues":[{"num":0,"value":"010-12345678"}]}
  ]
}
~~~

**对应代码与执行含义。** 它执行上面同一接收分支，并逐个处理 msg.parameters，不执行 addElement(8,msg)。下面是这个共用分支的追加核心，以及新建时的参数赋值：

~~~js
// 已选中 option=3 的提取节点时，接收分支执行：
for (let i = 0; i < msg["parameters"].length; i++) {
  changeGetDataParameters(msg, i);
  app._data["nowNode"]["parameters"]["params"].push(msg["parameters"][i]);
}

// 未选中提取节点时调用 addElement(3,msg)，modifyParameters 执行：
for (let i = 0; i < param["parameters"].length; i++) {
  changeGetDataParameters(param, i);
}
t["parameters"]["params"] = param["parameters"];
~~~

**处理后的案例。** 独立从 root.sequence=[1]、未选中提取节点开始，会新增 nodeList[2]，option=3、params=[标题,电话]，root.sequence=[1,2]。正式执行一次 getData，按两个绝对路径得到“房源详情、010-12345678”这一行。若事先选中的提取节点已有“租金”，则不新增节点，而是将其 params 从 [租金] 变成 [租金,标题,电话]。**无规律多元素是多个字段，不会自动变成逐卡片循环。**

**处理后的节点对象（关键字段）。** 这里展示未选中提取节点、走新建分支时的结果；字段默认项沿用第 11 节。

~~~json
{
  "id": 2,
  "index": 2,
  "parentId": 0,
  "position": 1,
  "type": 0,
  "option": 3,
  "title": "提取数据",
  "sequence": [],
  "isInLoop": false,
  "parameters": {
    "history": 1,
    "tabIndex": -1,
    "iframe": false,
    "clear": 0,
    "newLine": 1,
    "params": [
      {
        "name": "标题",
        "nodeType": 0,
        "contentType": 0,
        "extractType": 0,
        "relative": false,
        "relativeXPath": "//h1",
        "iframe": false,
        "exampleValues": [
          {
            "num": 0,
            "value": "房源详情"
          }
        ]
      },
      {
        "name": "电话",
        "nodeType": 0,
        "contentType": 0,
        "extractType": 0,
        "relative": false,
        "relativeXPath": "//footer/span[@class='phone']",
        "iframe": false,
        "exampleValues": [
          {
            "num": 0,
            "value": "010-12345678"
          }
        ]
      }
    ]
  }
}
~~~

### 13. loopClickEvery：循环点击为什么把点击 XPath 清空

**消息案例：loopClickEvery。** 列表里有 A、B 两个链接，用户希望逐个点击：

~~~json
{
  "type": "loopClickEvery",
  "id": 7,
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "useLoop": true,
  "loopType": 1,
  "content": "",
  "xpath": "//a[@class='house']",
  "allXPaths": ""
}
~~~

这里消息的 id 是发送端的连接标识，不是新节点的 index 或界面 id。如果循环和点击各自都固定点击第一个匹配元素，每轮都可能又点 A。

**对应代码与执行含义。** 先保存列表路径，再清空消息中的 XPath，供内部点击使用：

正确的保存分工是：外层循环保存列表路径；内部点击 useLoop=true、xpath 为空，使用循环传下来的路径和索引。A 那轮 index=0，B 那轮 index=1，点的目标才会变化。

| 处理时刻 | msg.xpath | 已建循环的 parameters.xpath | 点击节点将保存什么 |
| --- | --- | --- | --- |
| 收到消息 | 房源列表路径 | 尚未创建 | 尚未创建 |
| addElement(8,msg) 返回后 | 房源列表路径 | 已保存房源列表路径 | 尚未创建 |
| 清空 msg.xpath 后 | 空字符串 | 之前保存的字符串保持原值 | 创建时得到空 XPath |

这里复制的是字符串值，所以后面把 msg.xpath 改成空串，不会把已经写进循环参数的 XPath 也清空。下面原代码的先后顺序就是这个目的。

`loopClickEvery` 的接收逻辑：

~~~js
addElement(8, msg);
msg["xpath"] = "";
addElement(2, msg);
~~~

第一次创建循环时，路径已经写进循环的 `parameters.xpath`。随后把消息的路径清空，再创建内部点击。

语义是：

~~~text
循环找出所有房源链接；
内部点击使用当前循环链接的定位上下文。
~~~

`modifyParameters` 还会为 `loopClickEvery` 的点击设置 `newTab=1`。

~~~js
// modifyParameters 的 option=2 分支
t["parameters"]["xpath"] = param["xpath"];
t["parameters"]["useLoop"] = param["useLoop"];
t["parameters"]["allXPaths"] = param["allXPaths"];
if (param["type"] == "loopClickEvery") {
  t["parameters"]["newTab"] = 1;
}
~~~

**处理后的案例。** 独立从 root.sequence=[1] 开始，得到 root.sequence=[1,2]、循环 2.sequence=[3]。循环 2 保存 loopType=1 和列表路径；点击 3 保存 xpath=""、useLoop=true、newTab=1。正式执行时，loopExecute 提供当前列表索引，clickElement 第一轮点击 A、第二轮点击 B，并按 newTab 配置在新标签页打开。后续如果要采详情，还需在循环内添加提取等操作。

注意 `msg` 被修改过；不能把调用完成后的 `msg.xpath` 当成收到时的原值。

**处理后的节点对象（关键字段）。**

~~~json
[
  {
    "id": 2,
    "index": 2,
    "parentId": 0,
    "position": 1,
    "type": 1,
    "option": 8,
    "title": "循环点击每个元素",
    "sequence": [
      3
    ],
    "isInLoop": false,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "useLoop": false,
      "loopType": 1,
      "xpath": "//a[@class='house']",
      "allXPaths": ""
    }
  },
  {
    "id": 3,
    "index": 3,
    "parentId": 2,
    "position": 0,
    "type": 0,
    "option": 2,
    "title": "点击元素",
    "sequence": [],
    "isInLoop": true,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "xpath": "",
      "allXPaths": "",
      "useLoop": true,
      "newTab": 1
    }
  }
]
~~~

循环仍保留原 XPath，点击的 `xpath` 已是空串；点击的 `allXPaths` 仍保留消息中的原值（本例为空串），清空语句只改了 `msg.xpath`。

### 14. loopClickNextPage：翻页消息重新组织之前的子树

**消息案例：loopClickNextPage。** 假设已有 root.sequence=[1,2]，1 是打开网页，2 是卡片采集循环，2.sequence=[3]，3 是提取标题与租金。刚完成有规律采集，锚点仍在采集循环内，用户接着选择“下一页”：

~~~json
{
  "type": "loopClickNextPage",
  "id": 7,
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "useLoop": true,
  "loopType": 0,
  "nextPage": true,
  "lastAction": "collectDataWithLoop",
  "content": "下一页",
  "xpath": "//a[@id='next']",
  "allXPaths": ["//a[@id='next']"]
}
~~~

lastAction 来自扩展的交互状态。本例包含 WithLoop，表示接收端需要先把插入位置移到已有采集循环外面。这个字段不能在本消息中随意省略，因为源码会直接调用 msg.lastAction.includes；不含 WithLoop 的字符串则走另一条路径，要求插入锚点已经处于合适的外层位置。

**对应代码与执行含义。** 下面保留 logic.js 这一分支的处理语句，省略原注释并补上分步说明：

~~~js
} else if (msg["type"] == "loopClickNextPage") {
  // 1. 若前一次采集有循环，将锚点移到该循环后面
  let withLoop = msg.lastAction.includes("WithLoop");
  if (withLoop) {
    let loopElementId = app._data.nowArrow["pId"];
    let loopElement = $("#" + loopElementId);
    app._data.nowArrow["position"] = loopElement.attr("position");
    app._data.nowArrow["pId"] = loopElement.attr("pId");
  }
  // 2. 新建翻页循环和内部点击
  addElement(8, msg);
  msg["xpath"] = "";
  addElement(2, msg);

  // 3. 从新点击找到翻页循环，再找翻页循环之前的采集段
  let parentNode = nodeList[actionSequence[app._data.nowNode["parentId"]]];
  let parent_position = parentNode["position"];
  let last_collect_data_node_position = parent_position - 1;
  let parent_parentId = parentNode["parentId"];
  let last_collect_data_node_index =
    nodeList[actionSequence[parent_parentId]]["sequence"][last_collect_data_node_position];
  let last_collect_data_node = nodeList[last_collect_data_node_index];
  $("#" + last_collect_data_node["id"]).click();

  // 4. 把采集段剪切到翻页循环开头
  app._data.nowArrow['position'] = -1;
  option = 10;
  toolBoxKernel(null, null);

  // 5. 最后选中翻页循环，方便配置参数
  parentNode = nodeList[actionSequence[app._data.nowNode["parentId"]]];
  let parentId = parentNode["id"];
  $("#" + parentId).click();
}
~~~

modifyParameters 先将消息的 loopType=0 和原 XPath 写入循环；nextPage=true 使循环标题变成“循环点击下一页”。内部点击取得清空后的 XPath 和 useLoop=true。`option=10` 在这里是剪切工具，会复用第 20 讲的移动逻辑；它没有创建条件分支。

**处理后的案例。** 这一条消息执行前后的数组变化如下：

| 阶段 | root 的孩子 | 新翻页循环的孩子 | 原采集循环的孩子 |
| --- | --- | --- | --- |
| 原图 | [1,2]：打开网页、采集循环 | 尚不存在 | 2.sequence=[3]：提取 |
| 先建立新循环 4 | [1,2,4]：打开网页、采集循环、翻页循环 | 4.sequence=[] | 仍为 [3] |
| 再建下一页点击 5 | 仍为 [1,2,4] | [5]：点击下一页 | 仍为 [3] |
| 把前面的采集循环 2 移进去 | [1,4]：打开网页、翻页循环 | [2,5]：先采本页，再翻页 | 仍为 [3] |

**被移动的是整段采集子树的入口 2，它的孩子 3 跟随保留原关系。** 因此不用逐个搬运所有采集字段，也不用复制一份采集节点到每页。

这里使用的是独立小例子的编号，4、5 不对应前文十三节点图的搜索和页面循环。实际源码先调整锚点，再新增两项，最后用 option=10 的剪切工具移动前一个操作；下面按这四个动作理解即可。

`loopClickNextPage` 比普通新增更复杂：

1. 根据 `lastAction.includes("WithLoop")` 决定是否先把锚点从已有采集循环内部移到外面；
2. 建立单元素循环和内部下一页点击；
3. 找到新翻页循环之前的操作；
4. 调用剪切逻辑，把该操作移入翻页循环、放到点击之前。

目的对应第 15 篇的结构：

~~~text
页面循环
├─ 原来的采集操作或采集循环
└─ 点击下一页
~~~

这段代码依赖“前一个操作就是要包进来的采集段”这样的交互前提。它不是根据任意业务图自动推断所有循环层级；复杂房源图还需要用户选锚点、插入判断、配置分支。

在新增点击 5 后、剪切之前，actionSequence=[0,1,2,4,3,5]，翻页循环存于 nodeList[4]，界面 id=3；点击 5 的 parentId=3，需要 actionSequence[3]=4 才能找到它。不能把这里的 parentId=3 直接当作存储下标。

正式执行的正常顺序是“第 1 页采集子树 2 → 点击下一页 5 → 第 2 页采集子树 2 → 再点击下一页 5”。退出还取决于循环次数、页面变化和元素是否存在。单元素循环在找不到下一页时另有补执行循环体的异常分支，不能仅按这张结构图推断所有情况下的采集次数。

**处理后的节点对象（关键字段）。** 下面按 root、翻页循环、采集循环、下一页点击、提取节点的顺序展示，数组顺序用于阅读，不表示改写 nodeList 的存储顺序。原采集字段仅保留名称与相对定位项。

~~~json
[
  {
    "index": 0,
    "sequence": [
      1,
      4
    ]
  },
  {
    "id": 2,
    "index": 4,
    "parentId": 0,
    "position": 1,
    "type": 1,
    "option": 8,
    "title": "循环点击下一页",
    "sequence": [
      2,
      5
    ],
    "isInLoop": false,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "useLoop": false,
      "loopType": 0,
      "xpath": "//a[@id='next']",
      "allXPaths": [
        "//a[@id='next']"
      ]
    }
  },
  {
    "id": 3,
    "index": 2,
    "parentId": 2,
    "position": 0,
    "type": 1,
    "option": 8,
    "title": "循环采集数据",
    "sequence": [
      3
    ],
    "isInLoop": true,
    "parameters": {
      "loopType": 1,
      "xpath": "//div[@class='house']"
    }
  },
  {
    "id": 4,
    "index": 5,
    "parentId": 2,
    "position": 1,
    "type": 0,
    "option": 2,
    "title": "点击下一页",
    "sequence": [],
    "isInLoop": true,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "xpath": "",
      "allXPaths": [
        "//a[@id='next']"
      ],
      "useLoop": true,
      "newTab": 0
    }
  },
  {
    "id": 5,
    "index": 3,
    "parentId": 3,
    "position": 0,
    "type": 0,
    "option": 3,
    "title": "提取数据",
    "sequence": [],
    "isInLoop": true,
    "parameters": {
      "clear": 0,
      "newLine": 1,
      "params": [
        {
          "name": "标题",
          "relative": true,
          "relativeXPath": "/h2"
        },
        {
          "name": "租金",
          "relative": true,
          "relativeXPath": "/span[@class='rent']"
        }
      ]
    }
  }
]
~~~

最终 `actionSequence=[0,1,4,2,5,3]`。例如提取节点仍存于 `nodeList[3]`，界面 `id` 已变成 5；它的 `parentId=3` 指向界面 id 为 3 的采集循环，即 `nodeList[actionSequence[3]]=nodeList[2]`。

## 第五部分：其余操作消息也逐条走一遍

本部分每节独立恢复起点，不累加上一节新增的编号。除 openPage 从仅有 root 的空图开始外，普通示例都从 root.sequence=[1]（打开网页）开始，锚点为 `{pId:0, position:0}`，即放在打开网页之后。

### 15. openPage：新增打开网页操作

**消息案例。** 下面是与接收分支匹配的教学对象，展示网址参数如何进入节点，不代表当前扩展的某次完整发包记录：

~~~json
{
  "type": "openPage",
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "url": "https://example.com/houses",
  "links": "https://example.com/houses"
}
~~~

**对应代码与执行含义。** handleAddElement 选择 option=1；modifyParameters 的相应分支写入网址，并同步任务表单：

~~~js
// handleAddElement
if (msg["type"] == "openPage") {
  addElement(1, msg);
}

// modifyParameters 的 t.option==1 分支
t["parameters"]["url"] = param["url"];
t["parameters"]["links"] = param["links"];
$("#serviceDescription").val(param["url"]);
$("#url").val(param["url"]);
~~~

**处理后的案例。** 从 root.sequence=[] 开始，新建 nodeList[1]，option=1，root.sequence=[1]。parameters.url、links 都保存示例网址。正式运行时 executeNode 调用 openPage；该函数根据 useLoop、url 和任务链接池选择本次网址，再调用浏览器打开。消息没有为网页里所有按钮自动造节点。

**处理后的节点对象（关键字段）。** `nodeList[1]` 如下，root 的 `sequence` 为 `[1]`。

~~~json
{
  "id": 1,
  "index": 1,
  "parentId": 0,
  "position": 0,
  "type": 0,
  "option": 1,
  "title": "打开网页",
  "sequence": [],
  "isInLoop": false,
  "parameters": {
    "history": 1,
    "tabIndex": -1,
    "iframe": false,
    "useLoop": false,
    "url": "https://example.com/houses",
    "links": "https://example.com/houses",
    "cookies": "",
    "maxWaitTime": 10
  }
}
~~~

### 16. singleClick：新增一次点击

**消息案例。** 用户在房源页选择“搜索”按钮：

~~~json
{
  "type": "singleClick",
  "id": 7,
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "useLoop": false,
  "content": "搜索",
  "xpath": "//button[@id='search']",
  "allXPaths": ["//button[@id='search']"]
}
~~~

**对应代码与执行含义。** 接收器新增点击节点，参数分支记录定位方式：

~~~js
// handleAddElement 的 singleClick 分支
addElement(2, msg);

// modifyParameters 的 t.option==2 分支
t["parameters"]["xpath"] = param["xpath"];
t["parameters"]["useLoop"] = param["useLoop"];
t["parameters"]["allXPaths"] = param["allXPaths"];
if (param["type"] == "loopClickEvery") {
  t["parameters"]["newTab"] = 1;
}
~~~

本例 type 是 singleClick，最后的 if 不成立，newTab 保持默认值；公共参数 history、tabIndex、iframe 也由 modifyParameters 写入。

**处理后的案例。** 新建 nodeList[2]，option=2、xpath 为搜索按钮路径、useLoop=false，root.sequence=[1,2]。正式运行时 clickElement 按自己的 XPath 找到搜索按钮并点击一次。消息中的 content 是网页文字，不会作为本例点击节点的业务执行条件。

**处理后的节点对象（关键字段）。** `nodeList[2]` 如下，root 的 `sequence` 为 `[1,2]`。

~~~json
{
  "id": 2,
  "index": 2,
  "parentId": 0,
  "position": 1,
  "type": 0,
  "option": 2,
  "title": "点击搜索",
  "sequence": [],
  "isInLoop": false,
  "parameters": {
    "history": 1,
    "tabIndex": -1,
    "iframe": false,
    "xpath": "//button[@id='search']",
    "allXPaths": [
      "//button[@id='search']"
    ],
    "useLoop": false,
    "clickWay": 0,
    "newTab": 0,
    "wait": 2
  }
}
~~~

### 17. inputText：新增一次固定文字输入

**消息案例。** 用户给地区输入框输入“海淀”：

~~~json
{
  "type": "inputText",
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "useLoop": false,
  "loopType": 3,
  "value": "海淀",
  "xpath": "//input[@id='area']",
  "allXPaths": ["//input[@id='area']"]
}
~~~

**对应代码与执行含义。** 与 batchInputText 不同，这个分支只调用一次 addElement：

~~~js
// handleAddElement 的 inputText 分支
addElement(4, msg);

// modifyParameters 的 t.option==4 分支
t["parameters"]["value"] = param["value"];
t["parameters"]["xpath"] = param["xpath"];
t["parameters"]["allXPaths"] = param["allXPaths"];
t["parameters"]["useLoop"] = param["useLoop"];
~~~

**处理后的案例。** 新建 nodeList[2]，option=4、value="海淀"、useLoop=false，root.sequence=[1,2]。正式运行时 inputInfo 使用自己的 value，向输入框写入海淀。虽然发送对象也带 loopType=3，这个分支并未创建循环，该字段不会凭空让输入重复执行。

**处理后的节点对象（关键字段）。** `nodeList[2]` 如下。对照第 10 节，节点自身没有 loopType，root 下也没有额外的循环。

~~~json
{
  "id": 2,
  "index": 2,
  "parentId": 0,
  "position": 1,
  "type": 0,
  "option": 4,
  "title": "输入文字",
  "sequence": [],
  "isInLoop": false,
  "parameters": {
    "history": 1,
    "tabIndex": -1,
    "iframe": false,
    "xpath": "//input[@id='area']",
    "allXPaths": [
      "//input[@id='area']"
    ],
    "useLoop": false,
    "value": "海淀",
    "index": 0
  }
}
~~~

### 18. changeOption：新增下拉选项切换

**消息案例。** 页面有地区下拉框，用户要求按选项文本切换到“海淀”：

~~~json
{
  "type": "changeOption",
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "useLoop": false,
  "xpath": "//select[@id='area']",
  "allXPaths": ["//select[@id='area']"],
  "optionMode": 3,
  "optionValue": "海淀"
}
~~~

**对应代码与执行含义。** 新建 option=6 节点，将下拉框位置、切换方式和目标值存起来：

~~~js
// handleAddElement 的 changeOption 分支
addElement(6, msg);

// modifyParameters 的 t.option==6 分支
t["parameters"]["xpath"] = param["xpath"];
t["parameters"]["allXPaths"] = param["allXPaths"];
t["parameters"]["optionMode"] = param["optionMode"];
t["parameters"]["optionValue"] = param["optionValue"];
~~~

optionMode 的含义为 0=下一个、1=按索引、2=按 value、3=按显示文本。不要把消息名 changeOption、节点 option=6 和参数 optionMode=3 当成同一个编号。

**处理后的案例。** 新建 nodeList[2]，root.sequence=[1,2]，节点参数保存 optionMode=3、optionValue="海淀"。正式运行时 switchSelect 对找到的 select 调用按可见文本选择的分支。若改为 optionMode=1、optionValue="1"，则表示选择索引为 1 的第二项。

**处理后的节点对象（关键字段）。** `nodeList[2]` 如下。

~~~json
{
  "id": 2,
  "index": 2,
  "parentId": 0,
  "position": 1,
  "type": 0,
  "option": 6,
  "title": "切换下拉选项",
  "sequence": [],
  "isInLoop": false,
  "parameters": {
    "history": 1,
    "tabIndex": -1,
    "iframe": false,
    "xpath": "//select[@id='area']",
    "allXPaths": [
      "//select[@id='area']"
    ],
    "useLoop": false,
    "optionMode": 3,
    "optionValue": "海淀",
    "index": 0
  }
}
~~~

### 19. mouseMove：新增一次鼠标悬停

**消息案例。** 用户选择“更多筛选”菜单，想在执行时把鼠标移上去展开它：

~~~json
{
  "type": "mouseMove",
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "useLoop": false,
  "content": "更多筛选",
  "xpath": "//div[@id='more-filter']",
  "allXPaths": ["//div[@id='more-filter']"]
}
~~~

**对应代码与执行含义。** 接收器创建 option=7 操作，保存悬停目标：

~~~js
// handleAddElement 的 mouseMove 分支
addElement(7, msg);

// modifyParameters 的 t.option==7 分支
t["parameters"]["xpath"] = param["xpath"];
t["parameters"]["useLoop"] = param["useLoop"];
t["parameters"]["allXPaths"] = param["allXPaths"];
~~~

**处理后的案例。** 新建 nodeList[2]，option=7、useLoop=false，root.sequence=[1,2]。正式运行时 moveToElement 定位菜单，再执行 ActionChains(...).move_to_element(...).perform()。是否出现菜单取决于网页的悬停行为；这个节点本身不等于点击菜单，也不自动采集弹出的文字。

**处理后的节点对象（关键字段）。** `nodeList[2]` 如下。

~~~json
{
  "id": 2,
  "index": 2,
  "parentId": 0,
  "position": 1,
  "type": 0,
  "option": 7,
  "title": "移动到更多筛选",
  "sequence": [],
  "isInLoop": false,
  "parameters": {
    "history": 1,
    "tabIndex": -1,
    "iframe": false,
    "xpath": "//div[@id='more-filter']",
    "allXPaths": [
      "//div[@id='more-filter']"
    ],
    "useLoop": false
  }
}
~~~

### 20. loopMouseMove：对列表中的每项悬停

**消息案例。** 这次只选两张指定卡片，使用 loopType=2 的固定元素列表，展示 pathList 与单个公共 XPath 的区别：

~~~json
{
  "type": "loopMouseMove",
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "useLoop": true,
  "loopType": 2,
  "content": "",
  "xpath": "",
  "allXPaths": "",
  "pathList": ["//div[@id='house-A']", "//div[@id='house-B']"]
}
~~~

**对应代码与执行含义。** 创建循环后，再创建使用本轮定位的悬停孩子：

~~~js
// handleAddElement 的 loopMouseMove 分支
addElement(8, msg);
msg["xpath"] = "";
addElement(7, msg);

// modifyParameters 的 t.option==8 分支中的相关语句
t["parameters"]["loopType"] = param["loopType"];
t["parameters"]["xpath"] = param["xpath"];
if (param["loopType"] == 2) {
  t["parameters"]["pathList"] = param["pathList"].join("\n");
}

// t.option==7 分支还会写入 xpath、useLoop、allXPaths，见上一节
~~~

本例收到时 xpath 就是空串，循环靠 pathList 定位。若 loopType=1，则循环保存公共 xpath，后面的清空语句只影响悬停孩子，原理与第 13 节相同。

**处理后的案例。** root.sequence=[1,2]，循环 2.sequence=[3]。循环 2 保存 loopType=2、pathList="//div[@id='house-A']\n//div[@id='house-B']"；悬停 3 保存 xpath=""、useLoop=true。正式运行时 loopExecute 先提供 A 的路径，再提供 B 的路径，moveToElement 分别悬停 A、B。如果需要每次悬停后采集浮层，还要在同一循环内接上提取节点。

**处理后的节点对象（关键字段）。**

~~~json
[
  {
    "id": 2,
    "index": 2,
    "parentId": 0,
    "position": 1,
    "type": 1,
    "option": 8,
    "title": "循环移动到每个元素",
    "sequence": [
      3
    ],
    "isInLoop": false,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "useLoop": false,
      "xpath": "",
      "allXPaths": "",
      "loopType": 2,
      "pathList": "//div[@id='house-A']\n//div[@id='house-B']"
    }
  },
  {
    "id": 3,
    "index": 3,
    "parentId": 2,
    "position": 0,
    "type": 0,
    "option": 7,
    "title": "移动到元素",
    "sequence": [],
    "isInLoop": true,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "xpath": "",
      "allXPaths": "",
      "useLoop": true
    }
  }
]
~~~

消息中的 `pathList` 是数组，循环保存的 `parameters.pathList` 已经是用换行连接的字符串；悬停孩子没有复制这份列表。

### 21. loopClickSingle：反复点击同一个元素

**消息案例。** 页面有一个“加载更多”按钮，用户选择循环点击：

~~~json
{
  "type": "loopClickSingle",
  "id": 7,
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "useLoop": true,
  "loopType": 0,
  "nextPage": false,
  "lastAction": "collectData",
  "content": "加载更多",
  "xpath": "//button[@id='more']",
  "allXPaths": ["//button[@id='more']"]
}
~~~

**对应代码与执行含义。** 接收器创建单元素循环与内部点击，并把后续插入位置调整到点击之前：

~~~js
// handleAddElement 的 loopClickSingle 分支
addElement(8, msg);
msg["xpath"] = "";
addElement(2, msg);
app._data.nowArrow["position"] = -1;

// modifyParameters 的 t.option==8 分支先保存：
t["parameters"]["loopType"] = param["loopType"];
t["parameters"]["xpath"] = param["xpath"];
// 同一分支还用 param.content 生成“循环点击：加载更多”标题
// t.option==2 分支保存清空后的 xpath 和 useLoop=true
~~~

**处理后的案例。** 得到 root.sequence=[1,2]、循环 2.sequence=[3]。循环 2 保存 loopType=0、原按钮 XPath；点击 3 保存 xpath=""、useLoop=true。锚点最终为 `{pId:2, position:-1}`，下一次新增提取会放在点击之前。正式运行时 loopExecute 每轮重新定位该按钮，clickElement 使用循环的定位上下文点击它。消息不带固定点击次数，次数和退出条件来自循环默认参数及用户后续设置；若后来把 exitCount 设为 2，且按钮持续存在，正常路径会执行两轮。

本例与 loopClickNextPage 的区别是：**它只创建循环和点击，不会自动把前面的采集子树搬进来。**

**处理后的节点对象（关键字段）。**

~~~json
[
  {
    "id": 2,
    "index": 2,
    "parentId": 0,
    "position": 1,
    "type": 1,
    "option": 8,
    "title": "循环点击：加载更多",
    "sequence": [
      3
    ],
    "isInLoop": false,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "useLoop": false,
      "loopType": 0,
      "xpath": "//button[@id='more']",
      "allXPaths": [
        "//button[@id='more']"
      ],
      "exitCount": 0
    }
  },
  {
    "id": 3,
    "index": 3,
    "parentId": 2,
    "position": 0,
    "type": 0,
    "option": 2,
    "title": "点击加载更多",
    "sequence": [],
    "isInLoop": true,
    "parameters": {
      "history": 1,
      "tabIndex": -1,
      "iframe": false,
      "xpath": "",
      "allXPaths": [
        "//button[@id='more']"
      ],
      "useLoop": true,
      "newTab": 0
    }
  }
]
~~~

这是刚收到消息时的结果，`exitCount` 仍为默认值 0；若用户再设为 2，修改的是 `nodeList[2].parameters.exitCount`，不会再新增一个循环或点击节点。

### 22. GetCookies：更新已有打开网页节点

**消息案例。** 主进程把读到的 Cookie 文本发回流程图，下面使用虚构值：

~~~json
{
  "type": "GetCookies",
  "message": "session=demo-session\ncity=haidian"
}
~~~

**对应代码与执行含义。** 这个分支不走 addElement，而是从头查找第一个 option=1 的节点：

~~~js
} else if (msg["type"] == "GetCookies") {
  for (let node of nodeList) {
    if (node["option"] == 1) {
      node["parameters"]["cookies"] = msg["message"];
      $("#pageCookies").val(msg["message"]);
      break;
    }
  }
}
~~~

**处理后的案例。** 若 nodeList[1] 是第一个打开网页节点，它的 parameters.cookies 变成两行 Cookie 文本，nodeList.length 和 root.sequence 都不变。正式运行 openPage 时，会在打开网页后按 cookies 配置添加 Cookie。注意这里按数组从前往后找，不按当前选中节点找；源码也没有检查 node.id!=-1，因此不应将它描述成“更新第一个未删除的打开节点”。找不到 option=1 时，这个分支不会自动新建节点。

**处理后的节点对象（关键字段）。** 假设原 cookies 为空。下面只截取同一个打开网页节点的 Cookie 字段，网址等已有配置继续保留。

~~~json
{
  "处理前：nodeList[1]（关键字段）": {
    "index": 1,
    "option": 1,
    "parameters": {
      "cookies": ""
    }
  },
  "处理后：同一个nodeList[1]（关键字段）": {
    "index": 1,
    "option": 1,
    "parameters": {
      "cookies": "session=demo-session\ncity=haidian"
    }
  }
}
~~~

## 第六部分：不新增节点的界面消息，以及反向回传

### 23. title：更新任务信息，不创建“标题节点”

**消息案例。** 这是主进程发给流程图的标题通知：

~~~json
{"type":"title", "data":{"title":"房源搜索页"}}
~~~

**对应代码与执行含义。** 它由 ws.onmessage 直接处理，不进入 handleAddElement：

~~~js
if (evt["type"] == "title") {
  if (old_title == "新任务 | New Task") {
    $("#serviceName").val(evt.data.title);
    $("#create_time").val(formatDateTime(new Date()));
  }
  old_title = evt.data.title;
}
~~~

**处理后的案例。** 假设先收到 `{"type":"title","data":{"title":"新任务 | New Task"}}`，old_title 从初值空串变成这个标题；再收到上面的“房源搜索页”，内层条件成立，任务名变成“房源搜索页”，创建时间同步更新。若接着收到“房源详情页”，由于 old_title 已不是“新任务 | New Task”，这次只更新 old_title，不再覆盖任务名。**条件判断的是上一次标题，而不是无条件采用第一条消息。** 全程不修改 nodeList 和 sequence，也没有对应的 Python 操作节点。

### 24. notify：显示提示，不创建操作节点

**消息案例。** 主进程发来一条信息提示：

~~~json
{
  "type": "notify",
  "level": "info",
  "msg_zh": "请先选择要操作的元素",
  "msg_en": "Please select an element first"
}
~~~

**对应代码与执行含义。** 同样由 ws.onmessage 分流，按级别显示提示：

~~~js
} else if (evt["type"] == "notify") {
  if (evt["level"] == "success") {
    showSuccess(LANG(evt["msg_zh"], evt["msg_en"]));
  } else if (evt["level"] == "info") {
    showInfo(LANG(evt["msg_zh"], evt["msg_en"]));
  } else if (evt["level"] == "error") {
    showError(LANG(evt["msg_zh"], evt["msg_en"]));
  }
}
~~~

**处理后的案例。** 中文界面调用 showInfo，显示“请先选择要操作的元素”；level 改成 success 或 error，则分别走成功或错误提示。nodeList.length、参数和孩子列表均不变。当前流程图接收器只列出这三个级别，不能直接把其他接收端支持的 warning 也算进来。

### 25. update_parameter_num：采集后回传字段编号

**消息案例。** 方向是“流程图 → 扩展”。假设新增采集字段前 parameterNum=1，这次收到两列采集字段，则发回的内层消息是：

~~~json
{"type":"update_parameter_num", "value":3}
~~~

**对应代码与执行含义。** 上面的采集分支调用 notifyParameterNum(msg.parameters.length)，logic.js 的函数为：

~~~js
function notifyParameterNum(num) {
  parameterNum += num;
  let message = {
    type: 3,
    from: 1,
    message: {"pipe": JSON.stringify({"type": "update_parameter_num", "value": parameterNum})}
  };
  ws.send(JSON.stringify(message));
}
~~~

主进程转发内层消息后，扩展 messageInteraction.js 的接收回调执行：

~~~js
if (evt["type"] == "update_parameter_num") {
  chrome.storage.local.set({"parameterNum": parseInt(evt["value"])});
  console.log("更新参数添加索引值为：" + evt["value"]);
}
~~~

**处理后的案例。** 本次新增“标题、租金”两列，parameterNum 从 1 加到 3，扩展本地存储中的 parameterNum 也变成 3，后续生成字段名称时可继续使用更新的编号。这是字段编号同步，不会让图里多出一个 option=3 节点；提取节点或字段的新增已经由之前的采集消息完成。它不属于 handleAddElement 的输入消息，不应反向送进那个分发函数。

## 第七部分：把消息、结构与执行重新接起来

### 26. 从消息到执行，中间究竟新增了什么

回到最初的批量输入：你现在应能逐项指出消息缺少什么，以及谁补上它。

| 问题 | 本例答案 | 应查哪里 |
| --- | --- | --- |
| 为什么有两个节点 | 一条 batchInputText 调两次 addElement | handleAddElement |
| 为什么新循环是数组第 2 项 | 创建前 nodeList.length=2 | toolBoxKernel |
| 为什么输入在循环里面 | 新循环把锚点改到自己的内部 | toolBoxKernel 新增收尾 |
| 为什么不是一次输入两行 | 输入 useLoop=true，执行时逐轮传地区文字 | modifyParameters 与第 17 讲 inputInfo |
| 为什么屏幕能看到这两块 | refresh 为可达节点编号并创建 DOM | 第 19 讲 |

可以停下来手算一个反例：只把输入 3 移到 root 下，保持 useLoop=true，地区循环 2 就不再负责调用它。root 默认没有为它准备海淀或朝阳，输入参数虽然还写“使用循环”，也得不到原来的地区值。下面的全链路把这些职责放到一起。

~~~text
消息提供：
    操作类别、网页定位、输入文本、采集字段、循环配置

接收逻辑决定：
    一条消息创建几个节点，或者只追加字段

节点构造决定：
    新 index、option/type、公共默认参数

锚点决定：
    挂进哪个父 sequence、插在哪个位置

refresh 决定：
    当前界面 id、parentId、position、isInLoop，并重画

保存后：
    graph 保留数组与孩子下标

正式执行：
    按 option 递归解释这份结构
~~~

#### 26.1 换一种网页操作时，还是先判消息，再决定改几项

下面是 handleAddElement 的消息分支总对照。先按用户动作预测结果，再回到同名源码分支找调用：

| 用户操作 / 消息 type | 接收端的主要处理 | 结果 |
| --- | --- | --- |
| 打开网页 / openPage | addElement(1,msg) | 1 个打开网页节点 |
| 点击一次 / singleClick | addElement(2,msg) | 1 个点击节点 |
| 输入一次 / inputText | addElement(4,msg) | 1 个输入节点 |
| 输入多行 / batchInputText | 先 8 再 4 | 循环与输入孩子 |
| 切换下拉选项 / changeOption | addElement(6,msg) | 1 个下拉框操作 |
| 悬停一次 / mouseMove | addElement(7,msg) | 1 个鼠标移动节点 |
| 对每项悬停 / loopMouseMove | 先 8，清空 msg.xpath，再 7 | 循环与使用循环定位的移动孩子 |
| 反复点击单个元素 / loopClickSingle | 先 8，清空 msg.xpath，再 2；最后将插入位置调到点击前 | 单元素循环，便于把采集插到点击之前 |
| 逐个点击列表 / loopClickEvery | 先 8，清空 msg.xpath，再 2 | 列表循环与新标签页点击孩子 |
| 点击下一页 / loopClickNextPage | 创建循环和点击，再剪切前一采集段 | 先采本页再翻页的嵌套结构 |
| 单字段或不规律多字段 / singleCollect、multiCollectNoPattern | 当前选中提取则追加字段，否则新建 3 | 可能只改 params，不增加节点 |
| 有规律多字段 / multiCollectWithPattern | 先 8 再 3 | 每项一行，内部按字段数组采集 |
| 读取 Cookie / GetCookies | 找到第一个 option=1 的节点，更新 cookies | 改已有打开网页节点，不新建采集节点 |

表里数字为操作 option：1=打开、2=点击、3=提取、4=输入、6=下拉、7=移动、8=循环。自动新增的数量不是消息类型编号，而是接收分支写了几次 addElement；例如末尾的 GetCookies 完全没有新增调用。

练习：把输入 3 从 `2.sequence` 移到 `0.sequence`，`useLoop=true` 不变，会发生什么？

参考答案：它已经不属于地区循环，root 不会为它提供海淀/朝阳的文本上下文。`useLoop` 不能凭空找到“最近的地区循环”；结构与传参必须一起成立。

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[20.流程图的增删改查](/easyspider/chapter-20) ｜ 下一篇：[22.循环采集子元素与 Vue 参数栏](/easyspider/chapter-22)
