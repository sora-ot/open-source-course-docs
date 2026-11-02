---
title: "22 · 循环采集与参数栏"
description: "easyspider · 流程图与执行 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/22.循环采集子元素与Vue参数栏.md"
originalUrl: "/originals/easyspider/chapter-22.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 22.循环采集子元素：网页、parameters、流程图与 Vue 参数栏

> 第 21 讲已经说明消息怎样生成节点；本篇继续用一个具体案例，看这些节点怎样驱动 Vue 参数栏。
>
> 网页里有两张房源卡片，每张卡片都有标题和租金。采集每张卡片内部的字段时，图怎样画、参数怎样存、右侧怎样显示、修改的值又流向哪里？

先打开[可操作的 Vue 演示页](/resources/easyspider/%E7%A4%BA%E4%BE%8B-Flowchart/%E5%BE%AA%E7%8E%AF%E5%AD%90%E5%85%83%E7%B4%A0-Vue%E6%BC%94%E7%A4%BA.html)，再对照本篇。页面左边是被采集网页，中间是流程图，右边是真正由仓库 Vue 驱动的参数模板，下方实时显示变量和参数对象。

**本篇只使用四个流程节点：root 0、打开网页 1、循环 2、提取 3。标题和租金是提取节点内的两个字段，不是两个流程节点。** 本例不累加前后讲义的练习，也不采用第 18 讲未来优化方案中的替代编号规则。

## 1. 先看网页：循环对象与采集字段处在不同层次

假设目标网页的关键 HTML 如下：

~~~html
<div class="house">
  <h2>海淀单间</h2>
  <div class="meta">
    <span class="rent">2500元</span><span> / 月</span>
  </div>
</div>
<div class="house">
  <h2>朝阳单间</h2>
  <div class="meta">
    <span class="rent">2800元</span><span> / 月</span>
  </div>
</div>
~~~

在扩展中选中两张同类卡片，选择采集子元素，最后保留并重命名为“标题、租金”两列；“ / 月”那列在预览中删除。自动生成的初始字段名可能是“参数N_文本”，本例已经由用户改名，不能把业务名称当成自动命名规则。

| 层次 | 选中什么 | 保存的定位 | 本例含义 |
| --- | --- | --- | --- |
| 循环对象 | 每张 div.house 卡片 | `//div[@class='house']` | 这一轮处理哪一张卡片 |
| 标题字段 | 当前卡片的 h2 | `/h2[1]` | 在这一张卡片中取标题 |
| 租金字段 | 当前卡片的第一个 div 内第一个 span | `/div[1]/span[1]` | 在这一张卡片中取租金 |

扩展预览中应能看到两行：

| 标题 | 租金 |
| --- | --- |
| 海淀单间 | 2500元 |
| 朝阳单间 | 2800元 |

**“卡片有子元素”说的是网页 DOM；“循环有提取孩子”说的是流程树。** 每轮由循环提供当前卡片，提取操作在这张卡片里读取多个字段，因此流程树只需一个提取孩子。

## 2. 扩展侧 Vue：先生成字段与预览，再确认发送

这里先经过的是网页内的扩展操作台 toolkit.vue；后面右侧流程图参数栏则是 FlowChart 页面的另一个 Vue 实例。两者的数据不在同一个内存对象中。

扩展选择结果的关键状态可以读成：

~~~text
global.nodeList[0].node → 第一张网页卡片 DOM
global.nodeList[1].node → 第二张网页卡片 DOM
global.app._data.selectedDescendents = true
global.app._data.nowPath = "//div[@class='house']"
global.outputParameters = [标题字段, 租金字段]
~~~

本例使用“选中全部块的共有子元素”的方式。global.js 的 handleDescendents(2) 比较各块的相对路径，收集共有字段；保留两列并改名后，每列的 exampleValues 在发送前可含两个样例：

~~~js
// 预览阶段的关键字段；省去其他属性
global.outputParameters = [
  {name:"标题", relative:true, relativeXPath:"/h2[1]", nodeType:0, contentType:1,
   exampleValues:[{num:0,value:"海淀单间"},{num:1,value:"朝阳单间"}]},
  {name:"租金", relative:true, relativeXPath:"/div[1]/span[1]", nodeType:0, contentType:1,
   exampleValues:[{num:0,value:"2500元"},{num:1,value:"2800元"}]}
];
~~~

这里普通文本字段的 contentType=1 来自子元素遍历分支，表示“文本，不包括子元素”；不是前文普通文本示例中常用的 contentType=0。字段的 nodeType=0 表示普通网页节点，也不是流程节点的 option。

toolkit.vue 确认有规律多元素采集时，调用：

~~~js
confirmCollectMultiAndDescendents: function () {
  collectMultiWithPattern();
  clearEl();
  this.nextPage = 1;
  this.lastAction = "collectDataWithLoop";
}
~~~

messageInteraction.js 的 collectMultiWithPattern 建立消息，并把各字段的示例数组缩成第一个样例：

~~~js
let message = {
  "type": "multiCollectWithPattern",
  "history": history.length,
  "tabIndex": -1,
  "loopType": 1,
  "iframe": global.iframe,
  "xpath": "",
  "allXPaths": "",
  "isDescendents": global.app._data.selectedDescendents,
  "parameters": global.outputParameters,
};
for (let i = 0; i < global.outputParameters.length; i++) {
  global.outputParameters[i]["exampleValues"] = [global.outputParameters[i]["exampleValues"][0]];
}
~~~

本例已选中全部匹配卡片，detectAllSelected() 返回 true，发送函数继续使用 loopType=1，并把 nowPath、nowAllPaths 写入消息。若只保留部分卡片，发送端会改用 loopType=2 和 pathList，见第 21 讲其他消息案例。

所以**扩展预览可以显示两行，流程图字段表却只显示每列的第一个示例值**。这不是丢失第二张卡片的采集规则；真正的规则是循环路径与字段相对路径，执行时才重新读取每张卡片。

## 3. 消息长什么样，为什么只新增“循环 + 提取”

本例接收端得到的内层消息如下，省略与主线无关的候选路径元数据。完整配套对象见[消息案例 JSON](/source/?file=0fcc0ac20e258f83bd.json)：

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
    {"name":"标题", "nodeType":0, "contentType":1, "relative":true,
     "relativeXPath":"/h2[1]", "iframe":false, "desc":"",
     "exampleValues":[{"num":0,"value":"海淀单间"}]},
    {"name":"租金", "nodeType":0, "contentType":1, "relative":true,
     "relativeXPath":"/div[1]/span[1]", "iframe":false, "desc":"",
     "exampleValues":[{"num":0,"value":"2500元"}]}
  ]
}
~~~

这里 msg.parameters 是字段数组。外层 type=3、from=0 的信封经过主进程转发与 JSON.parse，才得到这个对象；跨页面传递的是 JSON 内容，不是网页 DOM，也不是共享的 JavaScript 对象引用。

logic.js 的实际接收分支为：

~~~js
} else if (msg["type"] == "multiCollectWithPattern") {
  addElement(8, msg);
  addElement(3, msg);
  changeOutputFormat(msg);
  notifyParameterNum(msg["parameters"].length);
}
~~~

从 root.sequence=[1]、锚点 `{pId:0, position:0}` 开始：

| 时刻 | 执行语句 | nodeList 与 sequence 的变化 | 插入与选中状态 |
| --- | --- | --- | --- |
| 收到消息前 | — | 只有 root 0、打开网页 1 | 插在打开网页之后 |
| 第一次新增 | addElement(8,msg) | 新建循环 2；root.sequence=[1,2] | 循环创建后把锚点设为 `{pId:2,position:-1}` |
| 第二次新增 | addElement(3,msg) | 新建提取 3；2.sequence=[3] | 选中提取 3，锚点位于它之后 |
| 接收收尾 | changeOutputFormat、notifyParameterNum | 本例无需切换输出格式；回传新增 2 个字段的编号变化 | 不再新增流程节点 |

循环的 modifyParameters 分支读取 loopType、xpath；提取的分支为各字段补默认设置，并执行：

~~~js
for (let i = 0; i < param["parameters"].length; i++) {
  changeGetDataParameters(param, i);
}
t["parameters"]["params"] = param["parameters"];
~~~

**同一条消息创建两个操作对象，但字段数组只写入提取节点的 parameters.params。** isDescendents=true 是扩展带来的标记；本例接收分支不会凭这个字段为每个子元素另建流程节点。

## 4. 图长什么样，节点 parameters 又是什么样

最终流程树如下：

~~~text
root 0：sequence=[1,2]
├─ 打开网页 1
└─ 循环采集数据 2：option=8，sequence=[3]
   └─ 提取标题和租金 3：option=3
      └─ parameters.params=[标题字段,租金字段]
~~~

最后一行是提取对象内部的数据说明，不是第四个可见业务方块。界面实际只画“打开网页、循环框、提取”这三个业务元素，截图见后文。

refresh 得到 actionSequence=[0,1,2,3]。本小图的 id 恰好与 index 相同；换成其他插入顺序仍要经过 actionSequence 转换。提取 3 的 parentId=2、position=0、isInLoop=true。

循环 2 的关键参数为：

~~~json
{
  "loopType": 1,
  "xpath": "//div[@class='house']",
  "allXPaths": ["//div[@class='house']"],
  "skipCount": 0,
  "historyWait": 2,
  "breakMode": 0,
  "useLoop": false
}
~~~

这是循环 parameters 的摘录，公共等待、滚动、脚本等默认字段省略。loopType=1 表示按匹配到的元素列表循环，不能把默认的 exitCount=0 理解成必须无限循环；这个模式主要由元素列表长度决定轮数。

提取 3 的 parameters 关键结构如下。公共 history、tabIndex、xpath、wait 等参数省略，**两份字段对象则完整列出本例接收默认值后的内容**：

~~~json
{
  "useLoop": false,
  "clear": 0,
  "newLine": 1,
  "params": [
    {
      "nodeType": 0,
      "contentType": 1,
      "relative": true,
      "name": "标题",
      "desc": "",
      "relativeXPath": "/h2[1]",
      "allXPaths": ["/h2[1]"],
      "exampleValues": [{"num":0,"value":"海淀单间"}],
      "iframe": false,
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
      "nodeType": 0,
      "contentType": 1,
      "relative": true,
      "name": "租金",
      "desc": "",
      "relativeXPath": "/div[1]/span[1]",
      "allXPaths": ["/div[1]/span[1]"],
      "exampleValues": [{"num":0,"value":"2500元"}],
      "iframe": false,
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
~~~

这几层同名状态要分开：

| 名称 | 本例是什么 |
| --- | --- |
| 扩展 global.outputParameters | 发送之前的字段配置数组 |
| 接收端 msg.parameters | 消息中的字段配置数组 |
| nodeList[3].parameters | 提取操作的参数对象，包含 clear、newLine、params 等 |
| nodeList[3].parameters.params | 此提取操作内部的字段配置数组 |
| app.params.parameters | Vue 字段表使用的数组引用 |
| 保存任务顶层 outputParameters | 保存时另外生成的输出摘要，第 23 讲计算 |

**本例采集节点 parameters.useLoop=false，字段 relative=true，二者并不矛盾。** 提取字段是否相对循环定位，看各字段的 relative；循环提供哪个父元素，看真实的父子调用与 isInLoop。不要把点击、输入操作的 useLoop 判断照搬成采集字段的开关。

## 5. 点中循环：右侧变成循环参数栏

点击中间的循环框，operationChange 把 DOM 的 data 转换成稳定下标，然后调用 handleElement。这里得到 nowNodeIndex=2：

~~~js
vueData.nowNodeIndex = actionSequence[theNode.getAttribute("data")];
handleElement();
~~~

handleElement 与循环有关的代码为：

~~~js
app._data["nowNode"] = nodeList[vueData.nowNodeIndex];
app._data["nodeType"] = app._data["nowNode"]["option"];
app._data.useLoop = app._data["nowNode"]["parameters"]["useLoop"];
app._data.xpath = app._data["nowNode"]["parameters"]["xpath"];
// 省略其他初始化与分支
if (app._data["nodeType"] == 8) {
  app._data.loopType = app._data["nowNode"]["parameters"]["loopType"];
}
~~~

对应状态是 nowNode=nodeList[2]、nodeType=8、loopType=1。模板的 `v-if="nodeType==8"` 成立，右侧显示“不固定元素列表”、循环 XPath、跳过次数、脚本退出和历史等待等配置。

![选中循环时，右侧显示循环路径和循环配置](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E5%BE%AA%E7%8E%AF%E5%AD%90%E5%85%83%E7%B4%A0-01-%E5%BE%AA%E7%8E%AF%E5%8F%82%E6%95%B0.png)

此时还没有在右侧编辑标题或租金字段；当前正在改的是“怎样枚举卡片”。例如循环 XPath 输入框直接绑定：

~~~html
<textarea v-model='nowNode["parameters"]["xpath"]'></textarea>
~~~

它写回 nodeList[2].parameters.xpath。下面的 useLoop 或 xpath 临时界面状态，与提取字段的 relativeXPath 也不是同一个字段。

## 6. 点中提取：右侧变成字段表，默认编辑标题

这次点击循环框里的“提取标题和租金”。选择入口得到 nowNodeIndex=3，handleElement 的提取分支执行：

~~~js
app._data["nowNode"] = nodeList[vueData.nowNodeIndex];
app._data["nodeType"] = app._data["nowNode"]["option"];
// 省略公共状态加载
if (app._data["nodeType"] == 3) {
  app._data.paraIndex = 0;
  app._data.params.parameters = app._data["nowNode"]["parameters"]["params"];
}
~~~

### 6.1 先把 app.params.parameters 的实际内容展开

FlowChart.js 创建 Vue 实例时，相关 data 初值是：

~~~js
data: {
  // 其他状态省略
  params: {parameters: []},
  paraIndex: 0
}
~~~

app 是这个 Vue 实例，app.params 是里面的一个对象，app.params.parameters 才是字段数组。刚创建页面时数组为空；执行上面的 handleElement 之后，**读取 app.params 会看到下面这样的具体内容**。这里保留本页表格、输入框和下拉框用到的主要字段，脚本等完整默认字段已在第 4 节列出：

~~~json
{
  "parameters": [
    {
      "name": "标题",
      "relative": true,
      "relativeXPath": "/h2[1]",
      "nodeType": 0,
      "contentType": 1,
      "paraType": "text",
      "recordASField": 1,
      "exampleValues": [{"num":0,"value":"海淀单间"}]
    },
    {
      "name": "租金",
      "relative": true,
      "relativeXPath": "/div[1]/span[1]",
      "nodeType": 0,
      "contentType": 1,
      "paraType": "text",
      "recordASField": 1,
      "exampleValues": [{"num":0,"value":"2500元"}]
    }
  ]
}
~~~

因此，**app.params.parameters 就是上面 parameters 后面的整个数组，既不是字符串，也不是一条字段，更不是当前采集到的一行结果。** 把表达式逐个代入，就能看懂页面在读什么：

| 表达式 | 本例具体值 | 右侧哪里使用 |
| --- | --- | --- |
| app.params.parameters.length | 2 | 表格生成两行 |
| app.params.parameters[0].name | "标题" | 第一行字段名 |
| app.params.parameters[1].name | "租金" | 第二行字段名 |
| app.params.parameters[0].exampleValues[0].value | "海淀单间" | 第一行示例值 |
| app.params.parameters[1].exampleValues[0].value | "2500元" | 第二行示例值 |
| app.params.parameters[0].relativeXPath | "/h2[1]" | 编辑标题时的 XPath |
| app.params.parameters[1].relativeXPath | "/div[1]/span[1]" | 编辑租金时的 XPath |

模板里省略 app，写成 params.parameters；Vue 方法内部可以写 this.params.parameters。这三种写法在本例访问的是同一份状态。比如表格第一行绑定 `params.parameters[0].name`，读出的就是“标题”；第二行绑定 `params.parameters[1].name`，读出的就是“租金”。

### 6.2 再看这份数组怎样指向原节点

上面的数组来自 nodeList[3].parameters.params。handleElement 的赋值没有复制数组，完成后存在以下引用关系：

~~~text
app.nowNode ───────────────────────────→ nodeList[3]
app.params.parameters ─────────────────→ nodeList[3].parameters.params
app.params.parameters[0] ──────────────→ 标题字段对象
app.params.parameters[1] ──────────────→ 租金字段对象
app.paraIndex = 0 ─────────────────────→ 下半部分编辑标题
~~~

~~~js
app.params.parameters === nodeList[3].parameters.params; // true
app.params.parameters[0] === nodeList[3].parameters.params[0]; // true
~~~

**nodeType=3 选择“提取表单”，paraIndex=0 选择“这张表单正在编辑哪个字段”。** 这两个变量分别控制整块参数区域和区域内部的字段选择。

当前 paraIndex=0 时，可以直接算出：

~~~js
app.params.parameters[app.paraIndex].name;
// 等价于 app.params.parameters[0].name，值为 "标题"

app.params.parameters[app.paraIndex].relativeXPath;
// 等价于 app.params.parameters[0].relativeXPath，值为 "/h2[1]"

app.nowNode.parameters.params[0].name;
// 同样是 "标题"，因为 app.nowNode 就是 nodeList[3]
~~~

### 6.3 用这些具体值读右侧模板

![选中提取节点时，右侧显示两行字段，下面默认编辑标题](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E5%BE%AA%E7%8E%AF%E5%AD%90%E5%85%83%E7%B4%A0-02-%E6%A0%87%E9%A2%98%E5%8F%82%E6%95%B0.png)

截图中的上半部分有：新增字段、提取前清空其他字段、提取后生成新数据行，以及标题、租金两行字段。下半部分默认显示标题，勾选“使用相对循环内的 XPATH”，XPath 为 /h2[1]。继续向下滚动，可以看到内容类型、节点类型、参数类型、默认值和是否保存字段等设置。

FlowChart_CN.html 的关键模板如下，省略样式和其他控件：

~~~html
<div class="elements" v-if="nodeType==3">
  <table>
    <tr v-for="i in params.parameters.length">
      <td><input v-model='params.parameters[i-1]["name"]'></td>
      <td>{{params.parameters[i-1]["exampleValues"][0]["value"]}}</td>
      <td><a v-on:mousedown="modifyParam(i-1)">修改</a></td>
    </tr>
  </table>

  <div v-if="paraIndex<params.parameters.length">
    <strong>{{params.parameters[paraIndex]["name"]}}</strong>
    <p v-if="nowNode['isInLoop']">
      <input type="checkbox" v-model='params.parameters[paraIndex]["relative"]'>
      使用相对循环内的XPATH
    </p>
    <textarea v-model='params.parameters[paraIndex]["relativeXPath"]'></textarea>
    <textarea readonly>{{getFinalXPath(
      params.parameters[paraIndex]['relativeXPath'],
      params.parameters[paraIndex]['relative'])}}</textarea>
  </div>
</div>
~~~

v-for 遍历数字时，本例 i 依次为 1、2，所以代码用 i-1 转成数组下标 0、1。“示例值”单元格是插值显示，不是编辑本轮采集结果的输入框。

<a id="vue-watch-bridge"></a>

### 6.4 watch 在哪里，直接绑定是否能代替它

**直接绑定能否完成界面联动，首先取决于 parameters 是否已经成为响应式对象。当前源码新增节点时先 push、后普通赋值添加 parameters，确实会遇到 Vue 2 的属性新增检测限制。** 此时直接绑定可能已经改了内存值，依赖它的 v-if 等界面却没有更新；不能仅根据一个预先构造完整参数的例子，就断言可以删掉现有 watch。

当前 useLoop、xpath 先绑定到预先声明的顶层响应式状态，再用 watch 写回节点。下面先读这条写回链，再在[第 6.4.5 节](#vue2-late-parameters)结合实际新增顺序解释为什么需要它。标题、租金字段的数组还经过另一条引用与观察路径，不能将它们与后添加的普通参数属性一概而论。

#### 6.4.1 先找到源码中的位置

这三段在 [FlowChart.js](/source/?file=48b61e5e4ebaa6ccf2.js) 顶部的 `let app = new Vue(...)` 内，属于与 data、methods 并列的 watch 配置。搜索 `watch:`，再找 useLoop、xpath、params：

~~~js
let app = new Vue({
  el: '#app',
  data: {
    // 其他字段省略
    nowNode: null,
    useLoop: false,
    xpath: "",
    params: {parameters: []}
  },
  watch: {
    // 其他监听省略，以下三项保留原语句
    useLoop: {
      handler: function (newVal, oldVal) {
        this.nowNode["parameters"]["useLoop"] = newVal;
      }
    },
    xpath: {
      handler: function (newVal, oldVal) {
        this.nowNode["parameters"]["xpath"] = newVal;
      }
    },
    params: {
      handler: function (newVal, oldVal) {
        this.nowNode["parameters"]["params"] = newVal["parameters"];
      }
    }
  }
  // mounted、methods 等配置省略
});
~~~

这里 this 是 Vue 实例 app。watch 的键 useLoop 监听 app.useLoop，xpath 监听 app.xpath，params 监听 app.params；它们不是在这三行配置中直接监听 nodeList。newVal 是被监听属性的新值，分别可能是 true、一个 XPath 字符串、一个包含 parameters 数组的对象；这三个回调没有使用 oldVal。

#### 6.4.2 useLoop、xpath 为什么需要这两步

以点击操作参数栏为例，FlowChart_CN.html 实际写的是：

~~~html
<input type="checkbox" v-model="useLoop">
<textarea v-model="xpath"></textarea>
~~~

它们的绑定目标是 app.useLoop、app.xpath，而业务参数在 app.nowNode.parameters 里面。假设另选了一个点击节点，其初值如下：

~~~js
// 这个最小快照只演示点击操作，不改变前文四节点采集案例
app.nowNode.parameters.useLoop; // false
app.nowNode.parameters.xpath;   // "//button[@id='search']"
app.useLoop;                    // false
app.xpath;                      // "//button[@id='search']"
~~~

两边此刻值相同，是 handleElement 选中节点时执行了“从节点加载到界面状态”：

~~~js
app._data.useLoop = app._data.nowNode.parameters.useLoop;
app._data.xpath = app._data.nowNode.parameters.xpath;
~~~

**布尔值、字符串的赋值没有建立两个属性之间的自动关联。** 用户在 textarea 中输入新 XPath，只会先改变 v-model 绑定的 app.xpath；当前设计再用 watch 完成反向写回：

~~~text
选中节点：
node.parameters.xpath="//button[@id='search']"
  → handleElement 加载 app.xpath
  → textarea 显示搜索按钮路径

用户编辑：
textarea 输入 "//button[@id='submit']"
  → v-model 写 app.xpath，新值为提交按钮路径
  → xpath 的 watch 收到 newVal
  → this.nowNode.parameters.xpath = newVal
  → nodeList 中当前节点的 XPath 也变成提交按钮路径

用户勾选：
checkbox 勾选
  → app.useLoop=true
  → useLoop 的 watch 写 this.nowNode.parameters.useLoop=true
~~~

若只删除这两个 watch，同时保留原模板，编辑会停留在 app.xpath、app.useLoop，节点参数不会通过这条路径更新。后续保存读取的是 nodeList，所以不能仅看输入框已经改变，就认为节点一定也改了。

**如果先保证 parameters 及相关字段已经被 Vue 观察，可以考虑直接绑定节点。** 以下写法成立的前提是初始化和响应性已经处理好：

~~~html
<div v-if="nowNode && nodeType==2">
  <input type="checkbox" v-model="nowNode.parameters.useLoop">
  <textarea v-model="nowNode.parameters.xpath"></textarea>
</div>
~~~

这段输入会直接写到当前节点，但若参数对象没有响应性，不能保证相关界面同步更新。仓库中的循环 XPath 控件也使用 `v-model='nowNode["parameters"]["xpath"]'`；输入框能改对象里的字符串，并不能单独证明其他依赖该属性的控件会响应变化。

如果以后统一重构，应先修复完整参数对象的初始化与观察顺序，再把原来的 `v-if="!useLoop"`、路径预览的 useLoop 实参等读取位置一起改为 nowNode.parameters.useLoop，最后调整 handleElement 的临时状态加载及写回监听。**按现有新增顺序，不能只替换 v-model 表达式并删掉 watch，就认为行为等价。**

#### 6.4.3 params 是对象，情况与前面两个标量不同

回到本篇标题、租金的采集案例。执行 handleElement 后：

~~~js
app.params.parameters === nodeList[3].parameters.params; // true
~~~

因此输入 `params.parameters[1].name` 或 `params.parameters[1].relativeXPath` 时，本来就在修改原字段对象。即使不经过 params 这个回调，也已经改到了 nodeList[3].parameters.params[1]。

**原 params 监听没有 deep:true，不能把它当作“每次字段变化都执行”的深度监听。** 对本例已经存在的响应式属性，下面几种操作应分别理解：

| 操作 | 是否直接影响原节点 | 原 params 监听是否因此执行 |
| --- | --- | --- |
| `app.params.parameters[1].name = "月租"` | 是，字段对象共享 | 不会因这次已有字段属性修改而执行 |
| `app.params.parameters.push(完整字段对象)` | 是，数组共享 | 不会因这次内部数组 push 而执行 |
| `app.params.parameters = 新数组` | 只替换界面对象内部的数组引用，原节点仍指向旧数组 | 不会因这次已有嵌套属性赋值而执行 |
| `app.params = {parameters: 新数组}` | 整个界面包装对象被替换后，由监听写回 | 会，回调把 newVal.parameters 交给当前节点 |

例如，保留字段结构并创建一个新数组，再替换整个包装对象：

~~~js
const nextFields = DeepClone(app.params.parameters);
nextFields[1].name = "月租";
app.params = {parameters: nextFields};
// params 的回调执行后：
// newVal 是 {parameters: nextFields}
// this.nowNode.parameters.params = nextFields
~~~

这个监听能够处理“替换整个 params 包装对象”的写回。但当前 handleElement 写的是 `app.params.parameters = 节点字段数组`，并没有替换 app.params；这里依靠的是先把界面数组指向已有节点数组。随后普通字段编辑靠共享引用完成写回，不能说这些编辑必须靠 params 的 watch 才能保存。

这次赋值还有一个与响应性有关的作用：app.params.parameters 本来就是 Vue data 中已声明的响应式属性；把字段数组赋给它时，Vue 会观察新数组及其中的字段对象。因此，后续修改字段的 name、relativeXPath 可以被追踪。它与“已经观察过的节点上，通过普通赋值新增 parameters”并不是相同的初始化路径。

以上区分针对普通属性赋值和本例的数组操作；Vue.set、Vue.delete 等改变响应式对象结构的通知机制不在此表讨论范围内。

#### 6.4.4 nowNode 的深度监听又负责另一件事

同一个 watch 配置中还有：

~~~js
nowNode: {
  deep: true,
  handler: function (newVal, oldVal) {
    updateUI();
  }
}
~~~

它负责在当前节点及其**已经可被响应式追踪的嵌套参数**变化后调用 updateUI → refresh(false)，重画由 jQuery 创建的流程图并恢复选择状态。deep:true 不会自动把普通赋值后加的属性补成响应式属性。即便已经解决参数响应性，直接 v-model 也不会替你调用这套 jQuery 绘图函数。

所以本篇改租金字段时的实际路径是：**v-model → 共享字段对象被修改 → nowNode 的深度监听 → 重画流程图**。这里的 params 监听与 nowNode 深度监听职责不同；这些监听也都不是写磁盘的保存函数，真正持久化仍要经过第 23 讲的 saveService。

<a id="vue2-late-parameters"></a>

#### 6.4.5 本项目确实存在“先观察节点，后添加 parameters”的限制

FlowChart_CN.html 加载的本地 vue.js 文件头标明版本为 **Vue 2.6.11**。这版 Vue 对已观察对象的普通属性新增有检测限制，见 [Vue 2 官方响应式说明](https://v2.vuejs.org/v2/guide/reactivity.html#For-Objects)。关键不在路径写得长，关键在属性是什么时候、以什么方式加入对象的。

FlowChart.js 的 toolBoxKernel 新增普通节点时，执行顺序摘录如下：

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
nodeList.push(t); // 此时没有 parameters；Vue 已观察的数组会观察这个新节点
// 省略容器类型设置、父 sequence 插入和锚点处理
refresh();
addParameters(t); // 后面才给节点增加 parameters
~~~

logic.js 的 addParameters 一开始又是普通赋值：

~~~js
t["parameters"] = {
  history: 1,
  tabIndex: 0,
  useLoop: false,
  xpath: "",
  // 其余公共参数省略
};
// 后面继续添加点击、输入、循环等操作专属参数
~~~

于是产生这样的顺序：

~~~text
new Vue 的 data.list.nl 指向 nodeList，数组已被观察
  → push 一个尚无 parameters 的节点 t
  → Vue 观察 t 当时已有的属性
  → 普通赋值 t.parameters = 默认参数对象
  → 这个后加属性及其对象没有经这一步自动完成响应式转换
  → 直接改 t.parameters.useLoop，未必通知依赖它的界面
~~~

本节用仓库 Vue 2.6.11 和原 addParameters 函数做了浏览器对照，勾选后等到 nextTick 再检查结果：

| 初始化与绑定方式 | 节点中的 useLoop | 模板显示的状态 | `v-if="!绑定值"` 的固定输入区 |
| --- | --- | --- | --- |
| 按原顺序先 push、后补参数；直接绑定节点参数 | 已变成 true | 仍显示 false | 仍显示，联动没有生效 |
| 同样先 push、后补参数；绑定顶层 useLoop，再 watch 写回 | true | true | 正常隐藏 |
| 先构造完整 parameters，再 push；直接绑定 | true | true | 正常隐藏 |
| 首次添加完整 parameters 时使用 Vue.set；直接绑定 | true | true | 正常隐藏 |
| 加载包含完整 parameters 的数组，再交给响应式 list.nl；直接绑定 | true | true | 正常隐藏 |

**所以这里的“直接写无效”应具体理解为：对象值可能改了，但相关界面没有被通知。** 不能仅检查 checkbox 自身已勾选，或控制台里的节点值已变成 true，就判断表单联动正常；还要看依赖它的文本、条件区域和预览有没有更新。

顶层 useLoop、xpath 预先声明在 Vue data 中，具备响应式 getter/setter。界面依赖这些状态，变化时能触发更新；watch 再把新值写入当前节点。这个办法并不是给原 parameters 自动补上响应性，而是让界面通过已知的响应式状态完成联动，并让业务对象接收到值。

这也解释了为什么“加载已有任务”和“现场新增节点”可能表现不同：加载回调把包含完整参数的 graph 赋给 app.$data.list.nl，新数组被观察时参数已经存在；现场新增则是 push 时参数还没创建。

若以后改为直接绑定，应先选择一致的初始化方式：在节点进入响应式数组前构造完整参数；或先在局部对象中构造好公共及操作专属参数，再在首次添加 parameters 时用 Vue.set。不能在 parameters 已经普通赋值后，简单对这个已存在的同名属性再调用一次 Vue.set，就当作已经补完观察。

本篇配套演示预置完整四节点状态，再创建 Vue 实例，适合观察字段切换和引用写回；**它没有复现现场新增的“先 push、后补参数”过程，因此不能拿它证明原新增流程可直接删掉 watch。**

<a id="para-index"></a>

## 7. paraIndex 专题：右侧正在编辑第几个字段

### 7.1 它是当前提取节点内部的字段数组下标

**paraIndex 表示“右侧下半部分正在编辑 params.parameters 数组的哪一项”，从 0 开始。** 它是 FlowChart.js 中 Vue data 的一个数值状态，初值为 0：

~~~js
paraIndex: 0, // 当前参数的 index
~~~

继续代入本例的具体数组，省去字段的其他属性：

~~~js
// app.params.parameters 的内容节选
[
  {name:"标题", relative:true, relativeXPath:"/h2[1]"},
  {name:"租金", relative:true, relativeXPath:"/div[1]/span[1]"}
]
~~~

| paraIndex 的值 | 取到的字段对象 | 右侧当前字段名 | XPath 输入框的值 |
| --- | --- | --- | --- |
| 0 | app.params.parameters[0] | 标题 | /h2[1] |
| 1 | app.params.parameters[1] | 租金 | /div[1]/span[1] |

选择对象需要两层定位：**nowNodeIndex=3 先找到提取节点 nodeList[3]，paraIndex=1 再找到它内部的租金字段。** 展开后就是：

~~~js
nodeList[vueData.nowNodeIndex].parameters.params[app.paraIndex]
// 代入 3、1：nodeList[3].parameters.params[1]
// 本例取到租金字段对象
~~~

因此，paraIndex=1 并不是选择 nodeList[1]，也不是选择第二张网页卡片。它只在当前提取节点的字段数组中取第 1 项。

### 7.2 点击某行“修改”，怎样把它设成那一行的下标

点第二行“修改”，模板调用 modifyParam(1)。FlowChart.js 的实际方法为：

~~~js
modifyParam: function (i) {
  this.paraIndex = i;
  let clone_node = DeepClone(this.nowNode);
  clone_node.option = 11;
  clone_node.parameters.index = i;
  trialElement(clone_node, 0);
}
~~~

第一句使 paraIndex 从 0 变成 1；右侧下半部分从标题配置变成租金配置。后面几句深复制当前提取节点，在临时副本上标记 option=11 和 parameters.index=1，用于单字段标记消息。

**原 nodeList[3].option 仍是 3，副本没有 push 进 nodeList，也没有修改任何 sequence。** 这里的 option=11 是试运行消息里的特殊节点含义，不是第 20 讲工具箱中的同号操作。

字段表用 `v-for="i in params.parameters.length"` 生成行，数字遍历从 1 开始，模板才用 i-1 调用修改：

~~~html
<tr v-for="i in params.parameters.length">
  <td>{{params.parameters[i-1]["name"]}}</td>
  <td><a v-on:mousedown="modifyParam(i-1)">修改</a></td>
</tr>
~~~

| 表格行 | 本行 v-for 的 i | 调用的方法 | 方法写入的 paraIndex |
| --- | --- | --- | --- |
| 第一行：标题 | 1 | modifyParam(0) | 0 |
| 第二行：租金 | 2 | modifyParam(1) | 1 |

### 7.3 它怎样让一整组控件同时切换字段

![点击租金的修改后，流程图不变，右侧字段详情切换为租金](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E5%BE%AA%E7%8E%AF%E5%AD%90%E5%85%83%E7%B4%A0-03-%E7%A7%9F%E9%87%91%E5%8F%82%E6%95%B0.png)

| 状态 | 刚选中提取节点 | 点租金的“修改”后 |
| --- | --- | --- |
| nowNodeIndex | 3 | 3 |
| app.nowNode | nodeList[3] | 仍是 nodeList[3] |
| nodeType | 3 | 3 |
| paraIndex | 0 | 1 |
| 当前字段 | params.parameters[0]，标题 | params.parameters[1]，租金 |
| XPath 输入框 | /h2[1] | /div[1]/span[1] |
| root.sequence | [1,2] | [1,2] |
| 循环.sequence | [3] | [3] |

代入这一次点击后的实际值：

~~~js
app.paraIndex; // 1
app.params.parameters.length; // 2，两条字段配置仍然都在
app.params.parameters[0].name; // "标题"
app.params.parameters[1].name; // "租金"
app.params.parameters[app.paraIndex].relativeXPath;
// app.params.parameters[1].relativeXPath，即 "/div[1]/span[1]"
~~~

所以换到租金详情时，app.params.parameters 本身仍是第 6.1 节那份两元素数组。变化的是取数组时使用的 paraIndex：上半部分表格始终展示两行，下半部分这次读取第 1 项。

下半部分的控件共用同一个 paraIndex，因此不仅是标题文字改变，所有字段级控件都会一起改读、改写对应对象：

~~~html
<strong>{{params.parameters[paraIndex]["name"]}}</strong>
<input type="checkbox" v-model='params.parameters[paraIndex]["relative"]'>
<textarea v-model='params.parameters[paraIndex]["relativeXPath"]'></textarea>
<select v-model='params.parameters[paraIndex]["contentType"]'>...</select>
<select v-model='params.parameters[paraIndex]["paraType"]'>...</select>
<input v-model='params.parameters[paraIndex]["default"]'>
~~~

比如 paraIndex=1 时，修改 XPath 输入框，实际写的是 app.params.parameters[1].relativeXPath，也就是原节点内的租金路径；paraIndex=0 时，同一个输入框写的则是标题路径。这里不是把租金配置拷贝进一套独立表单，再按“确定”拷回去。

**paraIndex 已经在 Vue data 中声明，模板又读取了它，所以赋值后 Vue 会更新这组控件，不需要另外写一个 watch: {paraIndex: ...} 才能切换。** 它的变化本身不修改字段内容；字段内容变化后，才涉及前一节介绍的 nowNode 深度监听与流程图重画。

### 7.4 哪些入口会改变 paraIndex，什么时候回到 0

它的初始声明和三个交互赋值位置如下，均可在 [FlowChart.js](/source/?file=48b61e5e4ebaa6ccf2.js) 和 [logic.js](/source/?file=786aaf2ec8ee7dbd78.js) 中搜索 paraIndex 核对：

| 入口 | 实际赋值 | 作用 |
| --- | --- | --- |
| Vue data 初始化 | paraIndex:0 | 初始编辑位置为第 0 项，字段未加载时数组仍可为空 |
| handleElement 选中提取节点 | app._data.paraIndex=0 | 每次进入提取节点，默认编辑第一列 |
| modifyParam(i) | this.paraIndex=i | 切换到用户点“修改”的那一列 |
| addParam() 新增字段 | this.paraIndex=this.nowNode.parameters.params.length-1 | 添加后立即编辑新数组的最后一项 |

上表中的 Vue data 是初始声明，后三行是交互过程中重新赋值的位置。比如本例原来只有标题、租金，点击“新增字段”后，addParam 的关键收尾为：

~~~js
// 前面已向 this.nowNode.parameters.params push 完整的新字段对象
notifyParameterNum(1);
this.paraIndex = this.nowNode["parameters"]["params"].length - 1;
~~~

数组长度从 2 变为 3，paraIndex 就设为 2，新字段的默认名为“自定义参数_N”。用户把它改名为“面积”后，状态可以读成：

~~~text
params.parameters = [标题字段, 租金字段, 面积字段]
paraIndex = 2
params.parameters[paraIndex].name = "面积"
~~~

重新点击提取方块会再次执行 handleElement，把 paraIndex 重置为 0。因此“从租金切去循环，再点击提取”，默认又回到标题。

另外，handleElement 的循环分支不会清空 params.parameters，提取分支也不会重置 loopType。比如从提取切到循环时，字段数组引用可以仍留在 Vue 状态中，但 nodeType=8 使提取区域不可见；不能仅看某个临时状态还在，就认为当前显示的仍是那张表单。

### 7.5 单字段试运行怎样知道测试的是哪一列

字段详情下面的“试运行”按钮使用当前 paraIndex：

~~~html
<a v-on:mousedown="trialParam(paraIndex)">试运行</a>
~~~

FlowChart.js 的方法为：

~~~js
trialParam: function (i) {
  let clone_node = DeepClone(this.nowNode);
  clone_node.option = 11;
  clone_node.parameters.index = i;
  trialElement(clone_node, 1);
}
~~~

本例正在编辑租金时，按钮调用 trialParam(1)，副本的 parameters.index=1，接收端据此选择副本的 params[1]。与 modifyParam 相比：modifyParam 会设置 paraIndex，并发送 type=0 的标记请求；trialParam 接收当前下标，发送 type=1 的试运行请求，本身不再给 paraIndex 赋值。

这里几个数字的作用分别是：

| 名称 | 本例值 | 表示什么 |
| --- | --- | --- |
| vueData.nowNodeIndex | 3 | nodeList 中的提取操作 |
| app.paraIndex | 1 | 参数栏当前编辑租金字段 |
| 临时副本 parameters.index | 1 | 标记或试运行消息要求测试租金字段 |
| 正式循环的 index | 0 或 1 | 当前处理海淀卡片还是朝阳卡片 |

正式执行并不依靠 app.paraIndex 决定只采某一列。它读取提取节点的整个 params 字段数组；本例每张卡片都采标题、租金两列。

### 7.6 删除、排序后，下标会不会继续指向同一个字段

**paraIndex 保存的是数组位置，不是永久绑定某个字段对象的标识。** 原 deleteParam、upParam、downParam 直接 splice 字段数组，没有同步调整 paraIndex。下面每行都独立从 `[标题,租金]`、paraIndex=1 开始：

| 用户动作 | 数组变成什么 | paraIndex | 右侧详情会怎样 |
| --- | --- | --- | --- |
| 将租金上移，upParam(1) | [租金,标题] | 仍为 1 | 第 1 项现在是标题，详情转而读取标题 |
| 删除标题，deleteParam(0) | [租金] | 仍为 1 | 1 已超出数组，详情区域隐藏 |
| 删除租金，deleteParam(1) | [标题] | 仍为 1 | 同样超出数组，详情区域隐藏 |

模板外层有这样的判断：

~~~html
<div v-if="paraIndex<params.parameters.length">
  <!-- 当前字段详情控件 -->
</div>
~~~

例如删除标题后，paraIndex=1、length=1，条件不成立，就不会创建里面读取 params.parameters[1] 的控件。这个条件负责隐藏越界详情，不负责把 paraIndex 自动改为有效值；再点剩余字段的“修改”，执行 modifyParam(0)，才能明确选中剩下那列。若字段全部删完，deleteParam 还会调用 deleteElement 删除提取节点，见源码相应分支。

### 7.7 它只保存当前编辑位置，不进入任务文件

paraIndex 放在 app 的 Vue data 中；saveService 保存 graph:nodeList，没有把整个 app 状态一起序列化。modifyParam、trialParam 增加的 parameters.index 也只放在深复制的试运行副本上，不会因此写进原提取节点。

所以保存的是标题、租金的字段配置，当前停留在哪列的编辑状态不会以 app.paraIndex 单独保存。重新打开任务并选中提取节点时，handleElement 仍将它设为 0，从第一列开始编辑。

## 8. “最终 XPath”为什么能把父卡片路径拼进来

getFinalXPath 还要用到 app.parentNode。logic.js 的 updateParentNode 从当前节点的 parentId，经 actionSequence 找到父对象：

~~~js
let parentNode = nodeList[actionSequence[app._data.nowNode["parentId"]]];
// 本例没有条件分支，省去调整分支层级的代码
app._data.parentNode = parentNode;
~~~

在新增的工具箱逻辑收尾会更新父节点；普通点击的标记路径调用 trialElement 时也会先调用 updateParentNode。本例选中提取后，parentNode 就是 nodeList[2]，不能只靠 handleElement 的前两行解释完整路径的来源。

对 loopType=1 的本例，getFinalXPath 的有效逻辑可以读成：

~~~js
if (this.parentNode == null || this.parentNode.parameters == null ||
    this.parentNode.parameters.xpath == null) {
  return xpath;
} else if (useLoop) {
  let parent_xpath = this.parentNode.parameters.xpath;
  return parent_xpath + xpath; // 此处省去原方法中的 loopType=2 分支
} else {
  return xpath;
}
~~~

采集模板传给这里的第二个实参是字段 relative，所以本例 useLoop 这个形参收到 true。标题显示为 `//div[@class='house']/h2[1]`，租金显示为 `//div[@class='house']/div[1]/span[1]`。

**这个只读框展示的是“父列表路径 + 字段路径”，不是正在切换第几轮的运行时地址。** 正式执行还有当前卡片对象和 index，才能区分海淀这一张与朝阳那一张。界面上看到一个合成 XPath，不表示每轮都读取第一张卡片。

## 9. 修改租金字段，值写回哪里

保持 paraIndex=1，把字段名从“租金”改成“月租”，再把路径改成等价写法 `/div[1]/span[@class='rent']`。两条绑定分别为：

~~~html
<!-- 字段表中第二行的名字：i-1=1 -->
<input v-model='params.parameters[i-1]["name"]'>
<!-- 当前字段详情：paraIndex=1 -->
<textarea v-model='params.parameters[paraIndex]["relativeXPath"]'></textarea>
~~~

写回路径可以逐层展开：

~~~text
用户在租金这一行输入“月租”
  → app.params.parameters[1].name = "月租"
  → nodeList[3].parameters.params[1].name = "月租"

用户修改当前 XPath 输入框
  → app.params.parameters[app.paraIndex].relativeXPath = 新路径
  → nodeList[3].parameters.params[1].relativeXPath = 新路径
~~~

这里是同一个字段对象的属性发生变化，不需要再把整张字段表复制回 nodeList。原 params 监听没有 deep:true，本次字段修改依靠共享引用直接写回；与 nowNode 深度监听的区别见[第 6.4 节](#vue-watch-bridge)。

![将租金改为月租并修改相对路径后，同一个节点对象同步变化](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E5%BE%AA%E7%8E%AF%E5%AD%90%E5%85%83%E7%B4%A0-04-%E7%BC%96%E8%BE%91%E5%90%8E%E5%8F%82%E6%95%B0.png)

编辑后读取 app.params.parameters，关键内容变成下面这样；这里只展示名称、相对定位开关和路径，其他字段保持各自原值：

~~~json
[
  {"name":"标题", "relative":true, "relativeXPath":"/h2[1]"},
  {"name":"月租", "relative":true, "relativeXPath":"/div[1]/span[@class=\"rent\"]"}
]
~~~

此时 paraIndex 仍为 1，所以右侧当前字段名变成“月租”，XPath 输入框变成新路径；第一行“标题”和它的路径仍保留。再从原节点读取，会得到同样的值：

~~~js
app.params.parameters[1] === nodeList[3].parameters.params[1]; // true
nodeList[3].parameters.params[1].name; // "月租"
nodeList[3].parameters.params[1].relativeXPath; // '/div[1]/span[@class="rent"]'
nodeList[3].parameters.params[0].relativeXPath; // 标题仍是 "/h2[1]"
~~~

字段名与详情标题会随 Vue 重新显示，最终 XPath 预览也重新计算。exampleValues 仍是录制时保存的示例，本例租金示例保持“2500元”；修改路径本身不会自动重新采样网页。

原 Vue 对 nowNode 的深度监听还会调用 updateUI → refresh(false)，重画流程图并恢复选择框。**参数变化可以触发重画，但本例的父子结构没有变化。** 标题、月租仍在同一个提取节点内。

## 10. 正式运行时，当前卡片怎样传到字段提取

设计阶段的 paraIndex 只控制正在编辑哪一列；正式运行用的是循环的 index，它控制正在处理哪一张卡片。二者没有共用一个计数器。

对于本例 loopType=1，正式执行器的核心调用来自 loopExecute：

~~~python
# 节选正常路径；省略跳过、异常、退出与历史恢复处理
elements = self.browser.find_elements(By.XPATH, xpath, iframe=node["parameters"]["iframe"])
index = 0
while index < len(elements):
    element = elements[index]
    for i in node["sequence"]:
        self.executeNode(i, element, xpath, index)
    # 原函数在本轮收尾后递增 index
    index += 1
~~~

于是提取 3 分别收到：

| 本轮 | loopValue / 当前元素 | loopPath / parentPath | index | 字段数组 |
| --- | --- | --- | --- | --- |
| 第 1 轮 | 海淀卡片 DOM 对应的 Selenium 元素 | //div[@class='house'] | 0 | 同一份标题、月租配置 |
| 第 2 轮 | 朝阳卡片 DOM 对应的 Selenium 元素 | //div[@class='house'] | 1 | 同一份标题、月租配置 |

executeNode 对 option=3 调用：

~~~python
self.getData(node["parameters"], loopValue, node["isInLoop"],
             parentPath=loopPath, index=index)
~~~

以非优化提取路径解释本例，getData 对 relative=true 且以单斜杠开头的字段，在当前 loopElement 上查找：

~~~python
element = loopElement.find_element(By.XPATH, relativeXPath[1:])
~~~

比如标题 `/h2[1]` 去掉首斜杠，成为对当前卡片查找的 `h2[1]`；月租同理在当前卡片中查找 div 下的 span。相对路径含 `//` 时，源码还有用 parentPath 和 index+1 拼完整路径的分支。解释器也有优化提取路径，具体选择不影响“当前卡片 + 字段配置”的职责分工，细节见第 16、17 讲。

两轮正常结果是：

| 标题 | 月租 |
| --- | --- |
| 海淀单间 | 2500元 |
| 朝阳单间 | 2800元 |

不是第 1 轮只提标题、第 2 轮只提租金；每轮都遍历提取节点内的字段配置。newLine=1 表示此提取操作后生成新行。

## 11. 保存以后，这些配置到哪里去了

保存仍由第 23 讲的 saveService 处理：

~~~js
serviceInfo = {
  // 省略其他任务配置
  inputParameters: inputParameters,
  outputParameters: outputParameters,
  graph: nodeList
};
~~~

本例的 inputParameters 只有打开网页的网址入口；loopType=1 的元素列表循环不会生成 loopText 输入。输出摘要则从 graph[3].parameters.params 读取两列信息，编辑后得到“标题、月租”。

两列的 relative、relativeXPath、contentType 和脚本配置仍在 graph[3].parameters.params 里；顶层 outputParameters 只保存列名、类型、示例和是否记录等摘要。重新加载后，点击提取节点，再由 handleElement 建立同样的 Vue 引用，右侧就能显示保存后的名字和路径。

## 12. 用演示页逐步核对变量

1. 打开[演示页](/resources/easyspider/%E7%A4%BA%E4%BE%8B-Flowchart/%E5%BE%AA%E7%8E%AF%E5%AD%90%E5%85%83%E7%B4%A0-Vue%E6%BC%94%E7%A4%BA.html)，选中循环：看 nowNodeIndex=2、nodeType=8、loopType=1。
2. 点提取方块：看 nowNodeIndex=3、nodeType=3、paraIndex=0，右侧默认编辑标题。
3. 点租金那行“修改”：看 paraIndex=1，nowNodeIndex 仍为 3；字段路径变成 /div[1]/span[1]。
4. 修改字段名或相对路径：看下方 nodeList[3].parameters.params[1] 同步变化。
5. 再点循环、再点提取：看 paraIndex 回到 0；点租金“修改”仍能看到刚改过的配置。

截图与页面使用同一份生成结果。演示复用仓库 Vue 配置、参数模板、默认参数函数和渲染函数，宿主在创建 Vue 前预置完整四节点状态；试运行消息只在本地记录，页面没有连接 Electron 或采集浏览器。四种状态已经用浏览器渲染验证，并对两张卡片的相对 XPath 结果做了核对；这不等于启动了完整 Python/Selenium 任务。现场新增节点的响应性限制另见[第 6.4.5 节](#vue2-late-parameters)。

完整的四种状态和原节点 parameters 可在[状态快照 JSON](/source/?file=b0b010c7f432548405.json)中对照。重新生成演示与截图可运行：

~~~powershell
python Docs/讲义/示例-Flowchart/生成循环子元素演示.py --screenshots
~~~

脚本使用本机 Chrome 或 Edge；可用 --browser 指定浏览器路径。“编辑后”状态通过页面中的真实 input 事件修改字段名和路径，再核对原节点的参数写回。

源码对照：

| 要找的逻辑 | 文件与入口 |
| --- | --- |
| 选择子元素、生成相对字段 | [global.js](/source/?file=f93e2dd77faf5042a2.js) 的 handleDescendents、readXPath |
| 扩展确认采集 | [toolkit.vue](/source/?file=7da96f658c0d8f985c.vue) 的 confirmCollectMultiAndDescendents |
| 发送字段与循环路径 | [messageInteraction.js](/source/?file=1a2b7d0e84fb34fe83.js) 的 collectMultiWithPattern |
| 接收、赋参数、建立当前编辑对象 | [logic.js](/source/?file=786aaf2ec8ee7dbd78.js) 的 handleAddElement、modifyParameters、handleElement |
| Vue 状态、修改字段、路径预览、重画 | [FlowChart.js](/source/?file=48b61e5e4ebaa6ccf2.js) 的 Vue 配置、modifyParam、getFinalXPath、refresh |
| 右侧字段表与参数控件 | [FlowChart_CN.html](/source/?file=9bc3327fb264a3fe95.html) 的 nodeType==3 与 nodeType==8 区域 |
| 本地演示生成 | [生成循环子元素演示.py](/source/?file=c61d9e14d6495b0313.py) 与[宿主模板](/resources/easyspider/%E7%A4%BA%E4%BE%8B-Flowchart/%E5%BE%AA%E7%8E%AF%E5%AD%90%E5%85%83%E7%B4%A0-%E6%BC%94%E7%A4%BA%E6%A8%A1%E6%9D%BF.html) |

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[21.消息到流程图节点](/easyspider/chapter-21) ｜ 下一篇：[23.流程图的保存与加载](/easyspider/chapter-23)
