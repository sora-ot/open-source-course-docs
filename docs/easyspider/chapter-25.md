---
title: "25 · 调试功能"
description: "easyspider · 工程实践 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/25.调试功能详解.md"
originalUrl: "/originals/easyspider/chapter-25.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 25.调试功能详解：Electron 发消息，浏览器插件接收与调试

上一篇认识了 Electron 主进程及调试消息出口。本篇先顺着一次“标记/试运行”请求，看主进程向插件发什么，再逐条解释内容脚本怎样接收、解析、定位和反馈。每个定位场景仍按“消息与参数 → 路径推演 → 源码 → 页面结果”展开。

本篇讲软件提供给用户的调试功能。需要设置源码断点、连接 Electron inspector、打开流程图或扩展 DevTools，以及配置 Python 调试器时，先看 [第 27 篇的开发环境与源码调试部分](/easyspider/chapter-27)。本篇的标记与试运行主要经过 Electron 和扩展，Python 正式执行器的断点不会因此自动命中。

源码：[Electron main.js](/source/?file=5b1dab0d6ae24484fc.js)、[流程图 logic.js](/source/?file=786aaf2ec8ee7dbd78.js)、[messageInteraction.js](/source/?file=1a2b7d0e84fb34fe83.js)、[trial.js](/source/?file=4db0929e51763364f3.js)。`trial.js` 是源码文件名，课程标题用“调试功能详解”；这里的调试包括目标标记、条件预览和单步试运行的结果反馈。实际 Selenium 试运行由 Electron 主进程完成，正式批量执行阶段已在第 15–17 篇讲完。

## 第一部分：先追 Electron 怎样向插件发送调试消息

### 1. 点击调试入口：请求包含操作和父循环上下文

例如标记价格字段，流程图调用 `trialElement(node,0)`；试运行该字段则传 1。先看消息内承载的教学定位参数：

```json
{
  "node": {"option": 11, "parameters": {"index": 0, "params": [
    {"name": "价格", "relative": true, "relativeXPath": "/p[1]", "iframe": false}
  ]}},
  "parentNode": {"option": 8, "parameters": {
    "loopType": 1, "xpath": "/html/body/section[1]/article", "iframe": false
  }}
}
```

这是展示 node 与 parentNode 的教学容器，不是直接上网发送的对象。请求里这两个值还要各自 stringify，外层协议 type=4，内层 type 表示标记还是试运行。完整包装见第 4 节；试运行字段还需配置 contentType、nodeType、前后置 JS 等，具体读取分支见第 29 节。

### 2. 主进程收到请求：标记与实际试运行走两条路径

```js
// main.js 标记/试运行分支的骨架
let node = JSON.parse(msg.message.node);
let type = msg.message.type;
if (type == 0) {
    // 按 node.option 定位、滚动，必要时计算 JS 条件结果
    send_message_to_browser(JSON.stringify({type: "trial", message: msg}));
} else {
    // 设计阶段使用 Selenium 执行动作或读取字段
    // notify_browser(...) 发送状态与结果
}
```

以价格为例：标记时主进程帮助定位到第一处价格并滚动，再把请求包成 trial 给插件；插件可以继续标出全部匹配价格。试运行时主进程读出某一字段的值，再发 notify；浏览器插件显示值。JavaScript 条件 class 5/7 的计算在主进程完成，result 写进 trial 消息供插件显示。

### 3. 主进程发送：消息到网页连接，插件在各自文档处理

`send_message_to_browser(message)` 先发 socket_window，再遍历 allWindowSockets。它接收已序列化字符串，当前函数不是按节点 ID 只发给一个连接；详见[第 24 篇的发送函数](/easyspider/chapter-24)。内容脚本收到同一消息后，只能操作自己所在的 document。

两种到达插件的消息形态不同：trial 包含原调试请求，notify 直接带文字与级别。例如成功读取价格后的消息是：

```json
{"type":"notify","level":"success","msg_zh":"获取的内容：￥99","msg_en":"Content obtained: ￥99"}
```

接下来先把 trial 的嵌套对象拆清，再进入浏览器的接收入口。

### 4. 从流程图请求到扩展收到的 evt

流程图的 [logic.js](/source/?file=786aaf2ec8ee7dbd78.js) 使用 `trialElement(node,type=1)`。标记时传 `type=0`，实际试运行时传 `type=1`：

```js
updateParentNode();
let message = {
    type: 4,
    from: 1,
    message: {
        type: type,
        node: JSON.stringify(node),
        parentNode: JSON.stringify(app._data.parentNode)
    }
};
ws.send(JSON.stringify(message));
```

`updateParentNode()` 从当前流程图位置获取上下文，并在条件分支等结构下调整父节点。字段只保存 `/p[1]` 时，传来的父节点必须提供商品块循环范围，才能组合出网页定位。

以“标记两个商品块的价格”为例，流程图发给 Electron 的消息可以写成下面这样。这里完整展示定位所需的对象，省略保存任务时其他无关的节点配置：

```json
{
  "type": 4,
  "from": 1,
  "message": {
    "type": 0,
    "node": "{\"option\":3,\"parameters\":{\"params\":[{\"name\":\"价格\",\"relative\":true,\"relativeXPath\":\"/p[1]\",\"iframe\":false}]}}",
    "parentNode": "{\"option\":8,\"parameters\":{\"loopType\":1,\"xpath\":\"/html/body/section[1]/article\",\"iframe\":false}}"
  }
}
```

Electron 在标记分支处理定位等工作后，用下面的方式发回浏览器：

```js
send_message_to_browser(JSON.stringify({type: "trial", message: msg}));
```

所以扩展的 `messageInteraction.js` parse 之后，传给 `trial(evt)` 的对象多了一层：

```json
{
  "type": "trial",
  "message": {
    "type": 4,
    "from": 1,
    "message": {
      "type": 0,
      "node": "{\"option\":3,\"parameters\":{\"params\":[{\"name\":\"价格\",\"relative\":true,\"relativeXPath\":\"/p[1]\",\"iframe\":false}]}}",
      "parentNode": "{\"option\":8,\"parameters\":{\"loopType\":1,\"xpath\":\"/html/body/section[1]/article\",\"iframe\":false}}"
    }
  }
}
```

逐层读：外层字符串 `"trial"` 决定调用扩展函数；中间数字 `4` 是 Electron 协议；最内层数字 `0` 才表示本次要标记。`node`、`parentNode` 都是字符串，扩展还要分别 parse。

### 5. 后文怎样展示完整消息而不反复写转义

下面用一个教学辅助函数表示刚才的包装。它不是仓库新增的通信函数，只用于把每个例子中的节点对象转换成 `trial()` 实际接收的结构：

```js
function makeTrialEvent(node, parentNode, type = 0, result) {
    const request = {
        type: 4,
        from: 1,
        message: {
            type,
            node: JSON.stringify(node),
            parentNode: JSON.stringify(parentNode)
        }
    };
    if (result !== undefined) {
        request.message.result = result;
    }
    return {type: "trial", message: request};
}
```

每个例子都先给出 `node`、`parentNode`，再用 `makeTrialEvent(node,parentNode)` 表示完整输入。实际通信时流程图发送的是 `request`，Electron 包装后才产生外层 `"trial"`，不是流程图直接调用扩展函数。

进入 `trial()` 后，源码首先执行：

```js
let node = JSON.parse(evt["message"]["message"]["node"]);
let parentNode = JSON.parse(evt["message"]["message"]["parentNode"]);
let parameters = node.parameters;
let type = evt["message"]["message"]["type"];
```

即使本次节点不用循环路径，`parentNode` 也会先 parse，不能省成 undefined。非循环例子统一传 `{option:0,parameters:{}}` 作为教学上下文。

## 第二部分：浏览器插件怎样接收，怎样选中处理分支

### 6. 内容脚本建立连接：Electron 的消息怎样进入 onmessage

```js
// messageInteraction.js 的接收入口
global.ws = new WebSocket("ws://localhost:8084");
global.ws.onopen = function () {
    this.send(JSON.stringify({
        type: 0,
        message: {id: global.id, title: document.title}
    }));
};
global.ws.onmessage = function (evt) {
    evt = JSON.parse(evt.data);
    if (evt.type == "update_parameter_num") {
        chrome.storage.local.set({parameterNum: parseInt(evt.value)});
    } else if (evt.type == "notify") {
        createNotification(LANG(evt.msg_zh, evt.msg_en), evt.level);
    } else if (evt.type == "cancelSelection") {
        clearEl();
    } else if (evt.type == "trial") {
        trial(evt);
    } else if (evt.type == "showAllToolboxes") {
        document.getElementById("wrapperToolkit").style.display = "block";
    } else if (evt.type == "hideAllToolboxes") {
        document.getElementById("wrapperToolkit").style.display = "none";
    }
};
```

onopen 的数字 type=0 是连接声明，与收到的 trial 内层 type=0“标记”处于不同对象层次。WebSocket 帧先到 evt.data，以 JSON 字符串形式存在；parse 后才按外层字符串 type 分发。浏览器不直接对最外层判断 node.option，也不是 Chrome background 用 tabs.sendMessage 转交的这条链路。

### 7. 六种收到的消息，分别做什么

#### 7.1 trial：解析节点，进入标记和条件预览

使用第 4 节的完整 trial 消息。onmessage 把整个对象交给 trial(evt)，后者分别 parse `evt.message.message.node`、parentNode，取 parameters 与最内层 type。先清旧 markElements 和坐标圆点，再在 `type==0` 下按 option 分发；后面从第 11 节开始逐项展开。

即使手工传入内层 type=1，trial 的主要标记分支也不会执行真实点击或批量采集。实际试运行已经在 Electron 完成，正常结果通过下一种消息回来。

#### 7.2 notify：把已算出的结果显示出来

```json
{"type":"notify","level":"success","msg_zh":"获取的内容：￥99","msg_en":"Content obtained: ￥99"}
```

接收后 `LANG` 按语言选文字，createNotification 创建通知。这里没有 node、XPath 和 contentType，插件无需重新查询价格。进度、条件结果或错误也能复用这个消息；通知显示和清理见第 29–32 节。

#### 7.3 cancelSelection：试运行后的选择清理

```json
{"type":"cancelSelection"}
```

主进程部分点击试运行路径发送这条消息；插件调用 clearEl()，清本地选择、字段和预览等状态。它不撤销刚才发生的真实点击，也不是让网页返回上一步。

#### 7.4 showAllToolboxes：恢复操作台显示

```json
{"type":"showAllToolboxes"}
```

主进程收到协议 type=30 后广播此消息；每个内容脚本将本地 wrapperToolkit 的 display 设为 block。“All” 依赖主进程发给哪些连接，单个脚本没有跨文档遍历全部标签页。

#### 7.5 hideAllToolboxes：隐藏操作台

```json
{"type":"hideAllToolboxes"}
```

主进程收到 type=31 后转换为这条消息；本地设 display=none。这里只改显示，不执行 clearEl，也不删除流程图节点。wrapperToolkit 不存在时，这段源码没有额外的空值保护。

#### 7.6 update_parameter_num：设计状态同步

```json
{"type":"update_parameter_num","value":6}
```

按 parseInt(value) 更新 chrome.storage.local.parameterNum，供下次生成字段编号使用。它不是标记或执行某个节点的命令；完整编号闭环见第 14 篇。将六个接收分支分清后，下面集中讲 trial 与 notify 这两条调试反馈链。

### 8. 沿用第 8 篇的商品树

假设内容脚本所在文档的 `body` 中有下面的内容：

```html
<section>
  <article id="p1">
    <a href="/java"><span>Java 入门</span></a>
    <img src="java.jpg">
    <p>￥99</p>
  </article>
  <article id="p2">
    <a href="/python"><span>Python 入门</span></a>
    <img src="python.jpg">
    <p>￥88</p>
    <strong>促销</strong>
  </article>
</section>
<button id="more">加载更多</button>
<a id="next" href="?page=2">下一页</a>
<input id="search">
<select id="language"><option value="java">Java</option><option value="py">Python</option></select>
```

先只画商品区；B、C 是商品块，F、I 是价格，J 是只出现在第二块里的促销：

```text
                              A(section)
                                   │
                 ┌─────────────────┴─────────────────┐
                 │                                   │
            B(article，p1)                      C(article，p2)
                 │                                   │
     ┌───────────┼───────────┐           ┌───────────┼───────────┬───────────┐
     │           │           │           │           │           │           │
   D(a)       E(img)       F(p)        G(a)       H(img)       I(p)      J(strong)
     │         java.jpg     ￥99          │         python.jpg   ￥88         促销
  K(span)                             L(span)
  Java 入门                           Python 入门
```

后文约定语言为中文、`iframe=false`。字母代表真实 DOM 引用，不能把字符串 `"F"` 当作 DOM 元素传进函数。

| 对象 | 结构 XPath | 相对于所属商品块的路径 |
|---|---|---|
| B，第一块 | `/html/body/section[1]/article[1]` | `""` |
| C，第二块 | `/html/body/section[1]/article[2]` | `""` |
| D，第一块链接 | `/html/body/section[1]/article[1]/a[1]` | `/a[1]` |
| F，第一块价格 | `/html/body/section[1]/article[1]/p[1]` | `/p[1]` |
| I，第二块价格 | `/html/body/section[1]/article[2]/p[1]` | `/p[1]` |
| J，第二块促销 | `/html/body/section[1]/article[2]/strong[1]` | `/strong[1]` |

共同商品路径 `/html/body/section[1]/article` 匹配 B、C；在它后面加 `/p[1]`，就得到能匹配 F、I 的路径。

### 9. “标记价格”和“试运行价格”，先看结果有什么不同

| 用户动作 | 网页上看到什么 | 主要工作由谁完成 |
|---|---|---|
| 标记提取节点中的价格位置 | 两个价格元素出现蓝色细边框 | `trial()` 枚举 XPath 匹配并设置阴影 |
| 标记普通点击节点 | 相应网页元素进入选择状态 | `trial()` 定位后调用 `clearEl(true)`、`addEl()` |
| 试运行某一个价格字段 | 页面出现类似“获取的内容：￥99”的通知 | Electron 读取内容，扩展显示通知 |
| 标记“第一块是否有促销”条件 | 提示条件未满足 | `trial()` 检查第一块，并调用 `createNotification()` |

蓝框说明“字段将从哪里读取”，通知中的价格说明“本次读到了什么”。`trial()` 的主要处理体被 `if (type == 0)` 包住，不能因为函数名是 trial 就把它理解成整个任务的执行器。

### 10. DOM、流程图节点与标记记录分别保存什么

| 名称 | 例子 | 保存什么 |
|---|---|---|
| `node` | `{option:3,parameters:{params:[...]}}` | 流程图操作配置；它不是网页 DOM |
| `parentNode` | `{option:8,parameters:{loopType:1,xpath:...}}` | 操作所属的流程图上下文；它不是 DOM 的 parentNode |
| `global.nodeList` | `{node:F,xpath:...,step:...}` | 第 8 篇讲过的网页选择记录 |
| `global.markElements` | `{element:F,bgColor:"",boxShadow:""}` | 批量标记提取位置时保存的 DOM 引用和样式 |

前两种对象可以 JSON 序列化；后两种含真实 DOM 引用，留在内容脚本内。这里的 `node.parameters.params` 已经是流程图节点格式，不能换成第 14 篇发送操作时的顶层 `message.parameters`。

## 第三部分：每次标记之前，先撤掉上一批反馈

### 11. 先清 markElements，再清坐标圆点

假设上次标记了价格，现在记录为：

```js
global.markElements = [
    {element: F, bgColor: "", boxShadow: ""},
    {element: I, bgColor: "", boxShadow: ""}
];
// F、I 当前的 style.boxShadow 都是 "0 0 0 1px #00a8ff"。
```

本次 `trial()` parse 消息之后，先执行这一段公共清理：

```js
for (let node of global.markElements) {
    let element = node.element;
    element.style.boxShadow = "none";
}
let elements = document.getElementsByClassName('highlight_of_easyspider');
while (elements.length > 0) {
    elements[0].parentNode.removeChild(elements[0]);
}
global.markElements = [];
```

按例子推：先把 F、I 的阴影设为 `none`，再删除上次 `point(x,y)` 创建的圆点，最后重置标记数组。`getElementsByClassName()` 是实时集合，删除第 0 个后，后面的元素自动成为新的第 0 个，因此这里用 while。

虽然记录里保存了旧 `boxShadow`，这里实际没有恢复该值，而是统一写 `none`。背景色也没有在这段修改。

### 12. clearEl(true) 又清哪些东西

后续各分支还可能调用 [global.js](/source/?file=f93e2dd77faf5042a2.js) 中的 `clearEl(true)`：恢复已选元素的样式，清 `readyList`、字段、预览、`nodeList`，重置步骤以及操作台的 option、page。

当前 `clearEl(trial=false)` 的实现没有使用参数 `trial` 做分支判断。因此 `true` 不能解释成“保留旧字段”或“只清颜色”。

后面的分支分成两条路：

```text
标记点击、输入、单字段、循环项
    clearEl(true) → addEl(null, element) → 进入网页选择逻辑

标记整个提取节点
    clearEl(true) → markElements.push(...) → 给匹配元素设置蓝色细阴影
```

`addEl()` 会调用 `handleElement()`，可能重新匹配候选、生成字段；批量提取标记则不调用 `addEl()`，只记录字段位置。它们产生的本地状态不同。

## 第四部分：点击、输入、下拉框和移动目标怎样标记

### 13. 点击、输入、下拉框与移动：逐个标记动作目标

标记“点击下一页”节点时，输入对象为：

```js
const node = {
    option: 2,
    title: "点击下一页",
    parameters: {
        xpath: '//*[@id="next"]',
        useLoop: false,
        iframe: false
    }
};
const parentNode = {option: 0, parameters: {}};
const evt = makeTrialEvent(node, parentNode);
```

先手工推：`useLoop=false`，所以没有父路径拼接；XPath 找到下一页链接。随后执行 `clearEl(true)`，再把这个链接交给 `addEl(null,element)`。网页选择提示切换到“下一页”，这里没有执行链接的 `.click()`。

对应源码为：

```js
if (option == 2 || option == 4 || option == 6 || option == 7) {
    let xpath = parameters.xpath;
    if (parameters.useLoop && option != 4 && option != 6) {
        // 根据父循环组合路径，下一节展开
    }
    // 坐标定位的处理，见第 15 节
    let element = document.evaluate(
        xpath, document, null,
        XPathResult.FIRST_ORDERED_NODE_TYPE, null
    ).singleNodeValue;
    if (element != null) {
        clearEl(true);
        addEl(null, element);
    }
}
```

这段摘录省略了坐标处理，只展示普通元素流程。`FIRST_ORDERED_NODE_TYPE` 只返回第一个匹配元素；返回 null 时，本分支不执行上述 clear/add。

输入、下拉框、移动也进入同一外层分支，以下是各自的完整定位配置：

```js
const inputNode = {
    option: 4,
    parameters: {xpath: '//*[@id="search"]', useLoop: false, iframe: false}
};
const selectNode = {
    option: 6,
    parameters: {xpath: '//*[@id="language"]', useLoop: false, iframe: false}
};
const moveNode = {
    option: 7,
    parameters: {xpath: '//*[@id="p1"]/a[1]', useLoop: false, iframe: false}
};
const parentNode = {option: 0, parameters: {}};
// 分别包装为三个独立的标记事件：
makeTrialEvent(inputNode, parentNode);
makeTrialEvent(selectNode, parentNode);
makeTrialEvent(moveNode, parentNode);
```

分别标记搜索框、语言下拉框、Java 链接。标记输入不会输入文字，标记 SELECT 不会切换选项，标记移动不会调用 Selenium 的鼠标移动。

### 14. 循环点击与循环移动：父路径与操作路径怎样合并

先给出“循环点击当前商品链接”的定位输入：

```js
const node = {
    option: 2,
    parameters: {xpath: "", useLoop: true, iframe: false}
};
const parentNode = {
    option: 8,
    parameters: {
        loopType: 1,
        xpath: "/html/body/section[1]/article/a",
        iframe: false
    }
};
const evt = makeTrialEvent(node, parentNode);
```

手工拼接：

```text
parentXPath = /html/body/section[1]/article/a
操作 xpath = ""
最终 xpath = /html/body/section[1]/article/a
FIRST_ORDERED_NODE_TYPE → D，即 Java 链接
```

空的操作路径表示循环项自身。但本分支用的是“第一个匹配”，因此只把 D 交给 `addEl()`，没有逐个点击 D、G。

如果父循环改为商品块范围，操作路径改成 `/a[1]`，最终是 `/html/body/section[1]/article/a[1]`，仍先找到 D。把 option 改成 7，就用同样的规则标记循环移动目标。

固定列表例子换成以下父节点：

```js
const parentNode = {
    option: 8,
    parameters: {
        loopType: 2,
        pathList: '//*[@id="p2"]\n//*[@id="p1"]',
        iframe: false
    }
};
const node = {
    option: 2,
    parameters: {xpath: "/a[1]", useLoop: true, iframe: false}
};
const evt = makeTrialEvent(node, parentNode);
```

这次源码取 `pathList.split("\n")[0].trim()`，得到 `//*[@id="p2"]`，再拼 `/a[1]`，标记 G，即 Python 链接。它按列表首条确定范围，不按网页顺序先取 B。

输入 option 4、下拉框 option 6 被 `option != 4 && option != 6` 明确排除：即使 `useLoop=true`，本地标记也直接使用它们的 xpath，不在这里拼父循环路径。批量输入的文本循环，不能照搬循环点击的定位规则。

### 15. point(120,240)：画一个位置圆点

输入是一个坐标点击节点：

```js
const node = {
    option: 2,
    parameters: {xpath: "point(120,240)", useLoop: false, iframe: false}
};
const parentNode = {option: 0, parameters: {}};
const evt = makeTrialEvent(node, parentNode);
```

执行顺序如下：

1. 发现定位字符串含 `point(`，把用于 XPath evaluate 的路径改成 `//body`。
2. 原来的 `parameters.xpath` 仍是 `point(120,240)`。
3. 用 `substring(6,point.length-1)` 取出 `120,240`，按逗号拆分，再 parseInt。
4. 调用 `highlightAt(120,240)`，不走普通元素的 clear/add 分支。

`highlightAt()` 新建一个 div，主要结果为：

```js
element.className = "highlight_of_easyspider";
element.style.position = "absolute";
element.style.left = "120px";
element.style.top = "240px";
element.style.width = "10px";
element.style.height = "10px";
element.style.backgroundColor = "blue";
element.style.borderRadius = "50%";
element.style.pointerEvents = "none";
element.style.animation = "blinkAnimation 2s infinite";
document.body.appendChild(element);
```

页面出现一个 10×10 的闪烁蓝圆点，不产生点击事件。动画定义在 [toolkit.css](/source/?file=d099273d8c29eb0147.css)：开始和结束时透明度 1，中间时透明度 0。

这个函数直接把 x、y 写进 absolute 的 left/top，没有加 scrollX、scrollY，也没有转换为 viewport 坐标。分析页面滚动后的落点时，应按它的实际 CSS 定位方式理解。圆点不加入 `markElements`，下一次 trial 的公共清理通过 class 删除它。

## 第五部分：提取节点怎样把字段位置全部标出来

### 16. 两个商品块、三个字段：先看完整定位输入

先给出要标记的提取节点。参数数组有链接文本、链接地址、价格三列；以下完整展示本例使用的字段定位配置，而不是保存任务时所有 beforeJS、默认值等执行配置：

```json
{
  "option": 3,
  "title": "提取商品信息",
  "parameters": {
    "params": [
      {
        "name": "链接文本",
        "nodeType": 1,
        "contentType": 0,
        "relative": true,
        "relativeXPath": "/a[1]",
        "iframe": false
      },
      {
        "name": "链接地址",
        "nodeType": 2,
        "contentType": 0,
        "relative": true,
        "relativeXPath": "/a[1]",
        "iframe": false
      },
      {
        "name": "价格",
        "nodeType": 0,
        "contentType": 1,
        "relative": true,
        "relativeXPath": "/p[1]",
        "iframe": false
      }
    ]
  }
}
```

父循环的输入为：

```json
{
  "option": 8,
  "title": "循环采集商品块",
  "parameters": {
    "loopType": 1,
    "xpath": "/html/body/section[1]/article",
    "iframe": false
  }
}
```

把这两个对象分别作为 `node`、`parentNode`，`makeTrialEvent(node,parentNode)` 就是本次的完整事件。不是把字段直接放进 `evt.parameters`。

### 17. 先逐列推演结果，再拆源码

先按字段数组顺序，写出每轮路径和匹配结果：

| 字段下标 i | 字段 | 最终 XPath | snapshot 匹配 |
|---:|---|---|---|
| 0 | 链接文本 | `/html/body/section[1]/article/a[1]` | D、G |
| 1 | 链接地址 | `/html/body/section[1]/article/a[1]` | D、G |
| 2 | 价格 | `/html/body/section[1]/article/p[1]` | F、I |

按顺序记录下来，结果快照为：

```js
global.markElements = [
    {element: D, bgColor: "", boxShadow: ""},
    {element: G, bgColor: "", boxShadow: ""},
    {element: D, bgColor: "", boxShadow: "0 0 0 1px #00a8ff"},
    {element: G, bgColor: "", boxShadow: "0 0 0 1px #00a8ff"},
    {element: F, bgColor: "", boxShadow: ""},
    {element: I, bgColor: "", boxShadow: ""}
];
```

这里假设 `clearEl(true)` 后目标元素的内联背景色与阴影都是空字符串。D、G 第二次进入数组时，保存的阴影已经是第一列设置的蓝框。代码没有去重，所以 **6 条标记记录对应 4 个不同 DOM 元素**。两个链接各承担两列字段，页面上并不会因此出现两个不同的链接。

本分支不把 D、G、F、I 加进 `nodeList`，也不读它们的文字或 href。`nodeType`、`contentType` 虽然告诉执行器怎样读字段，但这里决定标记范围的是 `relative`、`relativeXPath` 与父路径。

### 18. 源码的三层循环分别遍历什么

第一层遍历字段，第二层遍历该字段的最终 XPath，第三层遍历一条 XPath 的全部匹配：

```text
for i：params 中每一列字段
    └── for j：这个字段应执行的每一条 XPath
            └── for k：这条 XPath 的每个 snapshot 匹配
                    └── 保存 DOM 引用与样式，再画蓝框
```

先看第一层中如何构造路径列表：

```js
let xpath = param.relativeXPath;
let parentXPaths = "";
let xpaths = [];
if (param.relative) {
    if (parentNode.parameters.loopType <= 1) {
        parentXPaths = [parentNode.parameters.xpath];
    } else if (parentNode.parameters.loopType == 2) {
        parentXPaths = parentNode.parameters.pathList.split("\n");
    }
    for (let j = 0; j < parentXPaths.length; j++) {
        let parentXPath = parentXPaths[j];
        let realXPath = parentXPath + xpath;
        xpaths.push(realXPath);
    }
} else {
    xpaths.push(xpath);
}
```

对价格字段，本例只有一个父路径字符串，因此：

```js
parentXPaths = ["/html/body/section[1]/article"];
xpaths = ["/html/body/section[1]/article/p[1]"];
```

只有一条最终 XPath，但它能匹配两个价格。不要把 `xpaths.length=1` 理解成只标一个元素。

然后执行 snapshot 枚举：

```js
let elementList = document.evaluate(
    xpath, document, null,
    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
);
for (let k = 0; k < elementList.snapshotLength; k++) {
    let element = elementList.snapshotItem(k);
    if (element != null) {
        global.markElements.push({
            element,
            bgColor: element.style.backgroundColor,
            boxShadow: element.style.boxShadow
        });
        element.style.boxShadow = "0 0 0 1px #00a8ff";
    }
}
```

本例价格轮 `snapshotLength=2`，k=0 标 F，k=1 标 I。源码修改背景色的语句已经注释，实际只设置阴影。

### 19. 提取全部元素自身：relativeXPath 为空时怎样标记

第 14 篇“提取全部元素”发送的字段路径可以为空，流程图中同样使用这个语义。输入对象是：

```js
const node = {
    option: 3,
    parameters: {
        params: [{
            name: "价格",
            relative: true,
            relativeXPath: "",
            iframe: false
        }]
    }
};
const parentNode = {
    option: 8,
    parameters: {
        loopType: 1,
        xpath: "/html/body/section[1]/article/p",
        iframe: false
    }
};
const evt = makeTrialEvent(node, parentNode);
```

手工推：父路径 + 空字符串，仍是 `/html/body/section[1]/article/p`；snapshot 匹配 F、I，因此两个价格都画蓝框。

与第 16 节“带子元素”的差别是：这里父循环项本身就是价格，字段路径为空；那里父循环项是商品块，价格字段要再走 `/p[1]`。两种标记都进入 option 3，本函数没有再检查第 14 篇操作消息里的 `isDescendents`。

### 20. 固定列表：每条父路径都拼字段路径

继续使用第 16 节的三个字段，但把父节点换成：

```js
const parentNode = {
    option: 8,
    parameters: {
        loopType: 2,
        pathList: '//*[@id="p2"]\n//*[@id="p1"]',
        iframe: false
    }
};
const evt = makeTrialEvent(node, parentNode);
// 这里 node 使用第 16 节的三字段提取节点。
```

只展开价格这一列：

```js
parentXPaths = ['//*[@id="p2"]', '//*[@id="p1"]'];
xpaths = ['//*[@id="p2"]/p[1]', '//*[@id="p1"]/p[1]'];
```

第一条 XPath 的 snapshot 只有 I，第二条只有 F，两个价格都标记，记录顺序是 I → F。三个字段全部处理后，记录顺序是 G、D、G、D、I、F。

这里 `pathList` 是流程图循环参数中的**换行分隔字符串**。第 14 篇扩展发送操作时用的是数组，流程图创建循环节点时已经用 `join("\n")` 转换，所以本文件调用 split。

本分支分割后没有对每条路径 trim，也没有过滤空行；不要把其他分支的 `.trim()` 自动补进它的源码。

### 21. 绝对路径与出错路径：每个字段分别处理

如果只想标记第二块的促销，直接使用绝对定位：

```js
const node = {
    option: 3,
    parameters: {
        params: [{
            name: "促销",
            relative: false,
            relativeXPath: '//*[@id="p2"]/strong[1]',
            iframe: false
        }]
    }
};
const parentNode = {option: 0, parameters: {}};
const evt = makeTrialEvent(node, parentNode);
```

`relative=false`，直接把字段路径放进 `xpaths`，不拼父循环，结果只标 J。

再设某个提取节点有三个字段路径，依次是 `//*[`, `//*[@id="missing"]`、`//*[@id="p2"]/strong[1]`，且都为 `relative=false`：

| 路径 | evaluate 结果 | 本分支怎么处理 |
|---|---|---|
| `//*[` | 无效 XPath，抛异常 | catch，打印“跳过错误的xpath”，继续处理 |
| `//*[@id="missing"]` | 有效，但 snapshotLength 为 0 | 本轮不添加标记 |
| `//*[@id="p2"]/strong[1]` | 匹配 J | 正常画蓝框 |

try/catch 位于每条最终 XPath 的 evaluate/枚举外面，所以一条无效路径不阻止后面的路径。它没有包住函数最前面的 JSON.parse，也没有包住本文件所有 option 的 evaluate。

## 第六部分：标记单字段和标记循环，为什么走另一条路

### 22. option 11：先按 index 取一列，再把匹配交给 addEl

流程图的 `modifyParam(i)` 会复制当前提取节点，把副本的 option 改成 11，并设置 `parameters.index=i`。这是单字段调试入口，不是把保存的提取节点永久改成一种新的任务操作。

用第 16 节的三个字段，标记价格需要 `index=2`，不是第 2 列所用的下标 1：

```js
const node = {
    option: 11,
    parameters: {
        index: 2,
        params: [
            {name: "链接文本", relative: true, relativeXPath: "/a[1]", iframe: false},
            {name: "链接地址", relative: true, relativeXPath: "/a[1]", iframe: false},
            {name: "价格", relative: true, relativeXPath: "/p[1]", iframe: false}
        ]
    }
};
const parentNode = {
    option: 8,
    parameters: {
        loopType: 1,
        xpath: "/html/body/section[1]/article",
        iframe: false
    }
};
const evt = makeTrialEvent(node, parentNode);
```

手工推：取 `params[2]`，拼成 `/html/body/section[1]/article/p[1]`，snapshot 得到 F、I。清旧选择后，循环调用 `addEl(null,F)`、`addEl(null,I)`。

对应的关键源码为：

```js
let i = parameters.index;
let param = params[i];
let xpath = param.relativeXPath;
if (param.relative) {
    let parentXPath = parentNode.parameters.xpath;
    if (parentNode.parameters.loopType == 2) {
        parentXPath = parentNode.parameters.pathList.split("\n")[0].trim();
    }
    xpath = parentXPath + xpath;
}
let elementList = document.evaluate(
    xpath, document, null,
    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
);
clearEl(true);
for (let j = 0; j < elementList.snapshotLength; j++) {
    let element = elementList.snapshotItem(j);
    if (element != null) {
        addEl(null, element);
    }
}
```

换成固定列表 `p2\np1` 时，只取首条 `//*[@id="p2"]`，最终只将 I 交给 `addEl()`。与 option 3 的差别为：

| 标记请求 | 共同商品路径 loopType 1 | 固定列表 loopType 2 | 结果保存方式 |
|---|---|---|---|
| option 3，整个提取节点 | 每列匹配全部商品 | 每列遍历全部父路径 | markElements 与蓝色细阴影 |
| option 11，单个价格字段 | 当前字段匹配 F、I | 当前字段只用第一条父路径 | addEl，进入选择逻辑 |

这里“交给 addEl 的元素”与最终选择数组要分开理解：`addEl()` 还会检查候选、去重并触发匹配，不能把它当成只做一次 push 的函数。

### 23. option 8：标记的是循环范围本身

先分别给出三个循环节点的完整定位输入，每次都用非循环上下文包装为独立事件：

```js
const singleLoop = {
    option: 8,
    parameters: {loopType: 0, xpath: '//*[@id="more"]', iframe: false}
};
const patternLoop = {
    option: 8,
    parameters: {
        loopType: 1,
        xpath: "/html/body/section[1]/article",
        iframe: false
    }
};
const fixedLoop = {
    option: 8,
    parameters: {
        loopType: 2,
        pathList: '//*[@id="p2"]\n//*[@id="p1"]',
        iframe: false
    }
};
const parentNode = {option: 0, parameters: {}};
makeTrialEvent(singleLoop, parentNode);
makeTrialEvent(patternLoop, parentNode);
makeTrialEvent(fixedLoop, parentNode);
```

每个请求的执行顺序为：

| loopType | 查询与遍历 | 实际交给 addEl 的目标 |
|---:|---|---|
| 0 | 用 xpath 查询第一个元素；找到后 clear/add | “加载更多”按钮 |
| 1 | snapshot 查询共同 xpath；clear 后逐个 add | B、C 两个商品块 |
| 2 | clear；按换行拆路径，每条 trim，再查询首个元素并 add | C，然后 B |

loopType 1 代码中曾经“只取第一个，再选择全部”的实现已经注释；当前有效实现直接遍历 snapshot。

loopType 2 每条路径都用 `FIRST_ORDERED_NODE_TYPE`。如果列表某一条是一个匹配很多元素的宽泛 XPath，这一条也只取第一个，不会像 loopType 1 一样枚举它的全部匹配。

文本列表 loopType 3、网址列表等其他方式，没有进入这段 `loopType<=2` 的 DOM 标记处理。点循环节点进行标记，也不表示执行了循环内部操作。

## 第七部分：条件分支怎样判断，怎样显示结果

### 24. option 10 是具体分支，class 决定判断内容

流程图里的 option 9 是判断容器，option 10 才是某一个具体条件分支。本文件进入的是 `option==10`，然后读取 `parameters.class`：

| class | 条件含义 | trial 中的处理 |
|---:|---|---|
| 0 | 无条件 | result=1 |
| 1 | 当前页面包含文本 | 检查 body.innerText 是否包含 value |
| 2 | 当前页面包含元素 | 用 value 作为 XPath，检查第一个匹配是否存在 |
| 3 | 当前循环项包含文本 | 定位首个循环项，检查 innerText |
| 4 | 当前循环项包含元素 | 查询 `(父路径)[1]` + value |
| 5 | 页面 JavaScript 条件 | 读取 Electron 写回的 result |
| 7 | 当前循环项 JavaScript 条件 | 先尝试标记首个循环项，再读取 Electron 的 result |
| 其他，包括 6 | 本文件未实现对应动态判断 | result=2，显示不支持动态调试 |

本节所有条件事件仍用 `makeTrialEvent(node,parentNode)`，最内层 `type=0`。这个请求在扩展中会进行条件检查，但不会执行条件分支里面的提取、点击等后续操作。

### 25. 页面包含“促销”：本地判断结果为 true

先看完整条件配置：

```js
const node = {
    option: 10,
    title: "页面有促销",
    parameters: {class: 1, value: "促销"}
};
const parentNode = {option: 0, parameters: {}};
const evt = makeTrialEvent(node, parentNode);
```

按商品页面推：body.innerText 包含第二块里的“促销”，因此 `indexOf("促销")>=0`，result 从 0 改为 1。源码随后调用：

```js
createNotification("当前页面下，条件分支“页面有促销”的条件已满足", "success");
```

如果 value 改成“已售罄”，本例页面没有这段文字，result 保持 0，产生 warning 通知。

class 2 改为判断元素是否存在。完整输入为：

```js
const node = {
    option: 10,
    title: "页面有促销元素",
    parameters: {class: 2, value: '//*[@id="p2"]/strong[1]'}
};
const parentNode = {option: 0, parameters: {}};
const evt = makeTrialEvent(node, parentNode);
```

这里 value 是 XPath，不是要搜索的普通文字。evaluate 找到 J，result=1；如果改成 `//*[@id="p1"]/strong[1]`，没有匹配，result=0。

class 1、2 不会为了页面级判断调用 addEl 标记 J；class 2 只是检查查询结果是否为 null。

### 26. 当前循环项包含“促销”：为什么共同路径下结果为 false

这次条件与父节点为：

```js
const node = {
    option: 10,
    title: "当前商品有促销",
    parameters: {class: 3, value: "促销"}
};
const parentNode = {
    option: 8,
    parameters: {
        loopType: 1,
        xpath: "/html/body/section[1]/article",
        iframe: false
    }
};
const evt = makeTrialEvent(node, parentNode);
```

逐步推演：

1. class 属于 3/4/7，先用父循环路径查询第一个元素，找到 B；找到后 clear/add，尝试把 B 标为当前上下文。
2. class 3 的判断部分再次用父路径查询第一个元素，仍是 B。
3. B.innerText 有“Java 入门”和“￥99”，没有“促销”。
4. result 保持 0，追加“注意只会检索第一个匹配到的循环项”的说明。
5. 显示 warning：“当前页面下，条件分支‘当前商品有促销’的条件未满足……”；实际文字里的分支名用中文双引号。

第二块 C 明明有促销，为什么没有判断成功？因为本次只是用第一个匹配的循环项做动态检查，不是从 B 到 C 执行一遍循环。

如果父循环换成固定列表 `//*[@id="p2"]\n//*[@id="p1"]`，本分支取首条并 trim，查询 C，C.innerText 包含促销，result=1。这次成功来自“列表首条换成 C”，不是自动改为检查所有循环项。

### 27. 当前循环项包含元素：括号和 [1] 不能漏

class 4 条件的完整节点为：

```js
const node = {
    option: 10,
    title: "当前商品有促销元素",
    parameters: {class: 4, value: "/strong[1]"}
};
const parentNode = {
    option: 8,
    parameters: {
        loopType: 1,
        xpath: "/html/body/section[1]/article",
        iframe: false
    }
};
const evt = makeTrialEvent(node, parentNode);
```

源码构造的不是普通 `parentXPath+value`，而是：

```js
let xpath = "(" + parentXPath + ")" + "[" + "1" + "]" + value;
// (/html/body/section[1]/article)[1]/strong[1]
```

括号把父查询的结果集合包起来，`[1]` 先固定第一个商品块 B，然后查询它的 strong。B 没有 strong，所以 result=0。

如果直接拼成 `/html/body/section[1]/article/strong[1]`，会找到第二块的 J，得到完全不同的范围。本分支加 `(父路径)[1]`，正是为了限制在首个循环项里判断。

换成 C 在前的固定列表，组合结果为 `(//*[@id="p2"])[1]/strong[1]`，找到 J，result=1。

### 28. JavaScript 条件：代码在 Electron 执行，结果放在哪里

class 5、7 不在 `trial.js` 里执行 code。Electron 的标记处理分支调用 `execute_js()`，把 outcome 转成 0、1 或 -1，写入原请求的 `msg.message.result`，然后再包装成外层 trial 消息。

例如页面级 JavaScript 条件的节点输入为：

```js
const node = {
    option: 10,
    title: "JS检查促销",
    parameters: {
        class: 5,
        code: 'return document.body.innerText.includes("促销");',
        waitTime: 0
    }
};
const parentNode = {option: 0, parameters: {}};
const evt = makeTrialEvent(node, parentNode, 0, 1);
```

这里最后的 1 表示假设 Electron 已经执行代码并得到成立结果；不是扩展 helper 自己判断了代码。写回的事件中，该键的位置是：

```js
evt.message.message.result === 1;
```

扩展读取 result=1，显示 success 通知。

当前循环项 JavaScript 条件可以写成：

```js
const node = {
    option: 10,
    title: "JS检查当前商品",
    parameters: {
        class: 7,
        code: 'return arguments[0].innerText.includes("促销");',
        waitTime: 0
    }
};
const parentNode = {
    option: 8,
    parameters: {
        loopType: 1,
        xpath: "/html/body/section[1]/article",
        iframe: false
    }
};
const evt = makeTrialEvent(node, parentNode, 0, 0);
```

本例首个商品是 B，假设 Electron 得到 0。扩展先尝试选择 B，再取 result=0，显示未满足并提示只检索第一个循环项。`arguments[0]` 由 Electron 执行页面 JS 时提供，`trial()` 没有执行这段 code。

最后通知分发是三个明确判断：

| result | 页面通知 |
|---:|---|
| 0 | warning，条件未满足 |
| 1 | success，条件已满足 |
| 2 | info，不支持此类型的动态调试 |
| -1 | 本文件没有对应的通知分支 |

因此 JS 执行异常写回 -1 时，不能由本地代码推出“会显示红色错误通知”。class 6 等未实现的判断则进入 result=2，意思是没有本地动态判断实现，不能当作条件为 false。

## 第八部分：通知怎样出现、停留与删除

### 29. notify 消息也会调用 createNotification

除了条件分支直接调用，Electron 的试运行结果还会通过 `notify` 消息进入 `messageInteraction.js`。假设价格试运行读到 ￥99，扩展收到的消息为：

```json
{
  "type": "notify",
  "level": "success",
  "msg_zh": "获取的内容：￥99",
  "msg_en": "Content obtained: ￥99"
}
```

接收分支调用 `createNotification(LANG(evt.msg_zh,evt.msg_en),evt.level)`；中文界面得到 `createNotification("获取的内容：￥99","success")`。

同一通知函数服务两条路径：条件判断结果直接调用，跨进程试运行结果经 notify 调用。它不会把通知文字写入 `outputParameters`，也不会保存 CSV。

#### 29.1 通知里的字段值从哪里来：Electron 单字段试运行

当内层 type 为 1，Electron 进入实际试运行分支。以 option 11、价格字段为例：

1. 读 params[index]，根据 relative 和父循环组合 XPath。
2. `findElementAcrossAllWindows()` 寻找元素，考虑窗口、iframe 和定位。
3. 先执行字段 beforeJS 和等待配置。
4. 根据 contentType 读取：0 用 getText 并按 nodeType 处理链接/输入/图片；1 用页面 JS 读取直接文本；2/3 读取 innerHTML/outerHTML；4 读取 CSS 背景图；5/6 读取网址/标题；9 执行字段 JS；10/11 读取选项值/文字；14 读取属性；15 读取常量。
5. 用 notify_browser 发读取结果，再执行 afterJS。
6. 扩展 messageInteraction 收到 notify，调用 createNotification，在页面上显示值。

读取价格得 ￥99，是本次设计阶段的试运行反馈。它没有启动 Python 批量执行，也没有把全部循环项的数据写到最终 CSV。

参数生成时内联背景图的读法与这里 Selenium getCssValue 的读法不同；contentType 1 的样例分支也有不同空白处理。要比较设计预览、试运行和正式执行，分别追各自实现。


### 30. 创建通知：先写文字与时间，再设置样式

用一个短通知追代码：

```js
createNotification("采集完成", "success");
```

源码先创建 div，保存 timestamp，再写 innerText：

```js
let notification = document.createElement('div');
notification.className = 'notification_of_easyspider';
notification.setAttribute("data-timestamp", new Date().getTime());
notification.innerText = text;
```

`innerText` 把内容当文字显示。例如传入 `<b>完成</b>`，显示的是这些字符，不会在此处当 HTML 标签解析。

基础样式是 fixed 定位、距底部 20px、初始 right=-320px、最小宽度 300px、白字、圆角；`transition: right 0.5s ease-in-out` 决定左右滑动的时间。随后按通知 type 改颜色：

| type | 背景色 | 距底部 |
|---|---|---|
| success | `rgb(103,194,58)`，绿色 | 20px |
| info，默认值 | `#00a8ff`，蓝色 | 20px |
| warning | `rgb(230,162,60)`，橙色 | 20px |
| error | `#ff6b6b`，红色 | 70px |

`createNotification(text)` 不传 type 时取默认 info；传一个不在这四种中的字符串，源码没有相应的背景色分支，也不会自动回退为 info。不同通知没有统一排队或逐条累加高度，普通通知位置相同，多条同时出现时可能重叠。

### 31. 四个字的通知：手工算一次时间线

“采集完成”的 `text.length=4`，因此：

```js
let timeoutInterval = 1500 * text.length / 5;
// 1500 * 4 / 5 = 1200ms
```

以通知追加到 body 的时刻为 0，忽略定时器调度误差，时间线为：

```text
0ms       创建通知，right=-320px，追加到 body
100ms     第一个定时器：right=20px，开始滑入
约600ms   0.5秒滑入动画结束
1700ms    第二个定时器：1200+500，right=-320px，开始滑出
约2200ms  滑出 transitionend，删除通知
```

退出代码为：

```js
setTimeout(function () {
    notification.style.right = '-320px';
    notification.addEventListener('transitionend', function () {
        if (notification.parentNode === document.body) {
            document.body.removeChild(notification);
        }
    });
}, timeoutInterval + 500);
```

right 从 20px 变成负数，视觉上向右退到屏幕外；源码中“向左退出”的注释与这个效果不一致。移除前检查父节点仍为 body，避免通知已被其他清理删除后再删一次。

`text.length` 是 JavaScript 字符串长度，不是阅读字数或实际阅读时间。这个公式没有设置统一的最短、最长停留时间。

### 32. 另一处 3 秒轮询为什么还要清通知

第 14 篇的 `messageInteraction.js` 每 3000ms 遍历 `notification_of_easyspider`，根据 data-timestamp 删除年龄超过 10000ms、且仍是 body 子元素的通知。

因此删除可以来自两处：正常滑出后的 transitionend，或者消息模块的补充清理。通知文字很长时，按本函数公式计算的退出时间可能超过 10 秒，轮询也可能先把它删除。

例如 `text.length=40`，计划在 `1500*40/5+500=12500ms` 开始退出；如果某轮检查时它已经超过 10 秒，就可能在这个计划时刻之前消失。具体哪一轮取决于定时器启动相位。

坐标圆点使用的是 `highlight_of_easyspider`，通知使用的是 `notification_of_easyspider`，公共标记清理与通知清理按不同 class 查找，不能混为同一种对象。

## 第九部分：把输入、查询、状态与真实执行对齐

### 33. 三种 XPathResult 在本文件中分别做什么

| 查询方式 | 本文件出现的位置 | 返回值怎么读 | 例子 |
|---|---|---|---|
| FIRST_ORDERED_NODE_TYPE | 普通操作、单元素循环、固定列表每条、条件判断 | `.singleNodeValue`，取第一个或 null | 商品共同路径先取 B |
| ORDERED_NODE_SNAPSHOT_TYPE | 整个提取节点、单字段、共同路径循环 | `.snapshotLength`、`.snapshotItem(i)` | 价格路径拿到 F、I |
| ANY_TYPE | 第 14 篇 detectAllSelected，不在本文件 | `.iterateNext()` 逐个枚举 | 统计共同路径匹配数 |

同一条 XPath，选择第一个还是枚举全部，由查询方式与后续循环共同决定。父路径是“能匹配多个元素”的字符串，不代表所有分支都会遍历多个元素。

### 34. 当前实现的几个具体边界

| 看到的现象 | 对应源码事实 |
|---|---|
| 标记后字段预览可能被清掉或重新生成 | clearEl 清字段；addEl 路线还会进入 handleElement |
| 标记链接文本与链接地址，记录数多于元素数 | option 3 逐字段追加 markElements，没有去重 |
| 修改字段时，只标固定列表的第一项 | option 11 使用 split 后的第 0 条 |
| 某些无效 XPath 直接中断处理 | 只有 option 3 的逐路径 evaluate/枚举有局部 try/catch |
| 字段 index 超出数组范围 | option 11 没有检查 params[index] 是否存在 |
| 字段备选路径没有被尝试 | trial 不读取 allXPaths，只使用本次选定路径 |
| iframe 标志没有让这里自动切文档 | evaluate 的上下文始终是当前内容脚本的 document |
| justSend 没有阻止反向标记 | 函数开头的跳过逻辑已经注释 |

还有一个跨文件细节：`trial()` 多次调用 `addEl(null,element)`，但当前 `global.js` 的 `addEl()` 末尾仍直接使用全局 `event.stopImmediatePropagation()` 等方法。直接在控制台调用时，如果没有可用的 event，可能出现异常。阅读本文的消息与路径推演，不应把这些片段当成脱离扩展初始化即可运行的独立程序。

本文件也没有根据当前保存任务的 beforeJS、afterJS、字段 JS 配置执行采集。要看真实动作，继续追 Electron 的 type 4 实际试运行分支和正式执行器。

### 35. 同一个价格字段，标记与试运行分别走哪条链

```text
流程图：价格字段 relative=true，relativeXPath=/p[1]
父循环：loopType=1，xpath=/html/body/section[1]/article
                     │
          ┌──────────┴───────────┐
          │                      │
      请求 type=0             请求 type=1
        标记                    试运行
          │                      │
          ▼                      ▼
Electron 定位/滚动         Electron 定位、读取字段内容
          │                      │
     发 trial                 发 notify
          │                      │
          ▼                      ▼
messageInteraction         messageInteraction
  调用 trial(evt)           调用 createNotification
          │                      │
          ▼                      ▼
option 3：批量画字段位置     页面通知读到的价格
option 11：选择某一列位置    单字段试运行通常先读首个匹配
```

第 8 篇从 DOM 生成字段，第 10 篇生成预览，第 12 篇确认，第 14 篇发送操作；本篇接上反方向的定位和反馈。标记不会自动替代真实采集，也不会启动 Python 执行整份任务。

### 36. 对照源码的练习

1. 外层 `"trial"`、中层 `4`、最内层 `0` 分别决定什么？node 为什么还要再 JSON.parse？
2. 父路径 `/html/body/section[1]/article`，价格字段 `/p[1]`，option 3 的 xpaths 数量、snapshotLength 分别是多少？
3. 两个链接字段与一个价格字段，为什么有 6 条 markElements，却只有 4 个不同元素？
4. 把父循环改成固定列表 p2 在前、p1 在后，比较 option 3、11、8 的范围与顺序。
5. 字段 relativeXPath 为空时，怎样判断它表示价格自身还是商品块自身？
6. 页面有“促销”，class 1 为什么成立，class 3 在共同商品路径下为什么不成立？
7. class 4 中 `(父路径)[1]` 的括号和索引，怎样避免检查到第二个商品的促销？
8. class 7 的 result=-1 时，扩展会走哪条通知分支？请找出实际判断条件。
9. `point(120,240)` 会修改 nodeList 吗？圆点通过什么记录被清理？
10. 长度为 10 的通知，计划什么时候开始滑出？长度为 40 时，另一处清理可能怎样影响它？

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[24.ElectronJS：把网页变成桌面软件](/easyspider/chapter-24) ｜ 下一篇：[26.Node.js 与 Express：任务存取与本地文件服务](/easyspider/chapter-26)
