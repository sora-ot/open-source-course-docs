---
title: "23 · 流程图保存与加载"
description: "easyspider · 流程图与执行 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/23.流程图的保存与加载.md"
originalUrl: "/originals/easyspider/chapter-23.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 23.流程图的保存与加载：JSON 怎样保住结构和执行含义

> 保存的不是截图，也不是某一次运行的访问记录。
>
> 保存的是节点数组、孩子下标和操作参数。
>
> 本篇先保存五节点小图，再用房源任务逐个追踪：设计器内存 → JSON 文件 → 加载后重画 → 执行器递归解释。

---

<a id="vue-parameters-round-trip"></a>

## 接上 Vue 参数栏：刚才修改的值，怎样进入任务文件

如果要找“点节点后参数栏为什么改变、输入框为什么能修改节点”，先看第 20 讲的[Vue 参数栏完整链路](/easyspider/chapter-20#vue-parameter-panel)。本讲承接它的保存阶段：**参数栏通过 v-model 或监听器把值写回 nodeList，saveService 再用 graph: nodeList 保存这些值。**

仍用五节点图中的 nodeList[2]（点击按钮），假设刚把页面加载最长等待时间设为 10：

| 阶段 | 参数在哪里 | 谁负责 |
| --- | --- | --- |
| 在右侧输入 10 | nodeList[2].parameters.maxWaitTime=10 | v-model.number；nowNode 引用原节点 |
| 切换节点再回来 | 仍在原 nodeList[2] 中 | handleElement 重新选择编辑对象 |
| 点击保存 | serviceInfo.graph[2].parameters.maxWaitTime=10 | saveService 组装 graph: nodeList |
| 发出请求并写盘 | JSON 的 graph[2].parameters.maxWaitTime 为 10 | JSON.stringify、/manageTask、文件写入 |
| 重新打开任务 | result.graph[2].parameters.maxWaitTime 为 10 | /queryTask 返回任务 JSON |
| 再次点中点击按钮 | 恢复后的 nowNode.parameters.maxWaitTime 为 10，输入框显示 10 | 重新绑定数组、handleElement、v-model |

**切换节点后还在，是因为参数已写入内存；关闭再打开后还在，是因为任务已经成功写入文件并重新加载。** Vue 的响应式更新负责界面与内存数据的关联，磁盘持久化由本讲的保存与加载代码完成。

## 先把五节点小图保存，再加载回来

先回到第 15 篇构建、第 19 讲渲染的五节点基准图，不累加第 20 讲练习和第 21 讲消息例子的修改：

~~~text
nodeList 下标：0 root、1 打开网页、2 点击按钮、3 提取结果、4 循环
0.sequence = [1,4,3]
4.sequence = [2]
actionSequence = [0,1,4,3,2]
~~~

保存函数组装任务对象时，核心一项是 `graph: nodeList`。所以文件中的对象排列仍然是 root、打开、点击、提取、循环：

~~~json
{
  "graph": [
    {"index":0, "title":"root",     "option":0, "sequence":[1,4,3]},
    {"index":1, "title":"打开网页", "option":1, "sequence":[]},
    {"index":2, "title":"点击按钮", "option":2, "sequence":[]},
    {"index":3, "title":"提取结果", "option":3, "sequence":[]},
    {"index":4, "title":"循环",     "option":8, "sequence":[2]}
  ]
}
~~~

这是只保留结构的教学片段，真实任务还包含节点的 type、parameters、界面辅助字段，以及任务元数据和输入输出摘要。

加载成功后，logic.js 先把 graph 赋给 nodeList，完成相应兼容处理，再调用 refresh：

~~~js
nodeList = result["graph"];
// 中间还有真实加载逻辑中的字段兼容修补
refresh();
~~~

因为 root 的孩子仍是 [1,4,3]、循环的孩子仍是 [2]，所以可以重新算出 [0,1,4,3,2] 这份界面映射，并把点击放进循环框内。**恢复层次依靠 sequence 中保存的稳定下标；不需要把对象数组按界面 id 排序，也不需要把 DOM 写入文件。**

删除节点后留下的槽位也随整个 graph 保留；加载时只绘制 root 可达的部分。保存与加载不会为了去掉这些槽位而重新编号对象数组。

下面切换到完整房源模型，继续追踪实际保存接口、磁盘文件、输入输出摘要和加载代码。两份例子使用同一套存储规则，编号分别独立。

---

## 再把完整房源图保存、关闭、重新打开

你已经设计好“海淀、朝阳，只采单间”的流程图，接下来做四件很普通的事：给任务取名，点保存，关掉设计窗口，再从任务列表打开。重新打开后，地区循环、页面循环、单间分支和各个动作都还在。

**它能恢复，是因为保存了节点及其有序孩子关系，而不是保存了一张流程图图片。** 按本讲例子，核心结构仍然是：

~~~text
2（地区循环）：[3（输入地区）,4（搜索）,5（页面循环）]
5（页面循环）：[6（房源循环）,12（下一页）]
7（判断）：[8（单间分支）,9（兜底分支）]
8（单间分支）：[10（点击房源）,11（提取标题）]
~~~

本讲沿用[房源教学模型](/source/?file=ce174a47484f884969.json)的结构。它是教学骨架；下面模拟设计器已补齐节点默认参数并填写任务信息后的保存过程，不把教学 JSON 本身当成可以直接提交的完整 serviceInfo。主线只提取模型已有的“标题”一列，增加租金会作为字段扩展说明。

| 用户动作 | 实际传递的内容 | 下一阶段接到什么 |
| --- | --- | --- |
| 点保存 | saveService 从界面与 nodeList 组装对象 | serviceInfo，里面 graph=nodeList |
| 前端发送 | params 字段装 JSON.stringify(serviceInfo) | 后端先解表单，再解 JSON 字符串 |
| 后端写任务 | 写入 tasks/任务ID.json | 文件里有 graph、参数和元数据 |
| 重新打开 | GET /queryTask?id=任务ID | 文件内容作为任务对象返回 |
| 画回流程图 | nodeList=result.graph，再 refresh | 重建界面编号、DOM 和事件 |
| 正式执行 | 从任务生成执行实例，Python 读取 graph | 仍按节点下标、option、sequence 解释 |

为了把文件编号说具体，后面假设 tasks 目录已有 0.json、2.json、42.json，新任务会分配任务 ID=43。这个任务 ID 标识整份文件；graph[2] 的 2 则标识文件里的地区循环，两种编号相互独立。

---

## 第一部分：先区分三个容易混淆的“保存”

### 1. 任务、执行实例和采集结果各是什么

先对照三种用户需求：想下次继续改条件，需要任务定义；这次只采西城、不改变原来海淀朝阳的默认配置，需要执行实例；想把采集到的房源标题交给别人，需要采集结果。

在本讲假设中，可能分别对应 tasks/43.json、execution_instances/7.json 和 Data 下生成的数据文件。文件编号 43、7 只用于说明这次过程，不代表仓库已经存在这些示例文件。

| 你在文件中寻找什么 | 应该找哪一类 |
| --- | --- |
| “单间”条件、输入框 XPath、哪些节点属于循环 | 任务定义的 graph |
| 本次覆盖后的地区和页面次数 | 执行实例中的任务配置 |
| 已经读取到的 A、C、E 标题 | 采集输出文件 |

把这三类对象分开，才知道“保存成功”到底在保存什么。下面的表格把三个入口放在一起。

| 内容 | 房源例子里保存什么 | 主要用途 |
| --- | --- | --- |
| 任务定义 | 两个地区、循环结构、判断规则、字段 XPath | 下次继续设计或重新执行 |
| 执行实例 | 从任务生成的执行配置与输入覆盖 | 启动某次具体执行 |
| 采集结果 | A、C、E 的标题 | 用户最终使用的数据 |

本篇主要讲第一行。

采集完成时的 `saveData()` 写数据，不等于设计器的 `saveService()` 写任务。看名字都带 save，但所保存的对象不同。

### 2. saveService 从节点数组生成完整 serviceInfo

用户填写任务名“单间房源采集”，选择 CSV 输出，画好图并点保存。此时数据有两个来源：界面输入框提供任务名、输出格式等；nodeList 提供节点、条件和定位参数。

saveService 先扫描所有未删除节点，形成可调整输入和输出列摘要；再把这些摘要与完整 graph 放在同一个对象中。这个对象不是只有 graph，也不是只有表单字段。

| serviceInfo 字段 | 本例值或内容 | 为什么需要 |
| --- | --- | --- |
| id | 首次保存时为 -1，后端分配为 43 | 区分新增文件和覆盖原文件 |
| name | 单间房源采集 | 任务列表中显示 |
| version | 本仓库保存函数写入 0.6.5 | 加载时做版本提示 |
| outputFormat | csv | 执行器选择输出方式 |
| inputParameters | 地区、网址、循环次数摘要 | 运行前可修改的输入入口 |
| outputParameters | 标题字段摘要 | 描述输出列 |
| graph | 整个节点数组 | 保存完整结构与操作细节 |

下面对象只摘组装核心；其他界面项在真实函数里也会写入。

前端源码：[logic.js](/source/?file=786aaf2ec8ee7dbd78.js)，搜索 `function saveService`。

它读任务名、服务 ID、URL、输出格式等界面项，再遍历节点生成输入参数和输出参数。

最后：

~~~js
serviceInfo = {
  id: parseInt(serviceId),
  name: serviceName,
  // 其他元数据与执行设置省略
  containJudge: containJudge,
  inputParameters: inputParameters,
  outputParameters: outputParameters,
  graph: nodeList
};
~~~

**graph 直接使用整个 nodeList。** 没有只截取 BFS 顺序，也没有把全部操作展开成运行次数那么多项。

---

## 第二部分：同一棵房源树，保存了哪几份信息

### 3. graph 保留结构与每个节点的细节

先问“重新打开后要恢复什么”。不仅要画出一个叫页面循环的框，还要知道它的孩子是房源循环和下一页；不仅要有单间分支，还要知道它检查当前房源是否包含“单间”。

例如这三类数据分别负责：

| 必须保留的信息 | 保存位置 | 丢失后会怎样 |
| --- | --- | --- |
| 先采本页再翻页 | graph[5].sequence=[6,12] | 不知道正确循环体顺序 |
| 单间判断条件 | graph[8].parameters.class=3、value=单间 | 只剩“单间分支”标题，无法据此判断 |
| 从详情页读标题 | graph[11].parameters.params 中的字段定位 | 有输出列名，但读不到网页字段 |

下面结构快照给每个对象加上 title，数字引用可以直接对照操作名称。它仍只是 graph 的骨架，真实节点还有 parameters 等字段。

~~~json
{
  "name": "单间房源采集",
  "graph": [
    {
      "index": 0,
      "title": "root",
      "option": 0,
      "sequence": [
        1,
        2
      ]
    },
    {
      "index": 1,
      "title": "打开网页",
      "option": 1,
      "sequence": []
    },
    {
      "index": 2,
      "title": "地区循环",
      "option": 8,
      "sequence": [
        3,
        4,
        5
      ]
    },
    {
      "index": 3,
      "title": "输入地区",
      "option": 4,
      "sequence": []
    },
    {
      "index": 4,
      "title": "点击搜索",
      "option": 2,
      "sequence": []
    },
    {
      "index": 5,
      "title": "页面循环",
      "option": 8,
      "sequence": [
        6,
        12
      ]
    },
    {
      "index": 6,
      "title": "房源循环",
      "option": 8,
      "sequence": [
        7
      ]
    },
    {
      "index": 7,
      "title": "判断",
      "option": 9,
      "sequence": [
        8,
        9
      ]
    },
    {
      "index": 8,
      "title": "单间分支",
      "option": 10,
      "sequence": [
        10,
        11
      ]
    },
    {
      "index": 9,
      "title": "兜底分支",
      "option": 10,
      "sequence": []
    },
    {
      "index": 10,
      "title": "点击房源",
      "option": 2,
      "sequence": []
    },
    {
      "index": 11,
      "title": "提取信息",
      "option": 3,
      "sequence": []
    },
    {
      "index": 12,
      "title": "点击下一页",
      "option": 2,
      "sequence": []
    }
  ]
}
~~~

上面只展示结构，实际节点还包含标题、类型、参数和刷新后的辅助字段；实际 serviceInfo 还包含版本、输出设置等。

保存的不是：

~~~text
输入海淀、点击搜索、采 A、跳 B、采 C……
输入朝阳、点击搜索、跳 D、采 E……
~~~

这些是运行某份数据之后产生的访问轨迹。执行前可能根本不知道未来会出现哪些房源。

### 4. inputParameters 提供可调整的输入入口

**inputParameters 和 outputParameters 都是在点击保存时，由 logic.js 的 saveService 扫描 nodeList 重新计算的。** 它们不是从右侧输入框逐个抓取出来的，也不是将节点 parameters 原样改名。下面的第 4.1 节给出输入摘要的全部有效代码，第 6.1 节给出输出摘要的全部有效代码。

假设任务默认地区为海淀、朝阳，但运行时想改成西城、东城。输入摘要让调用端知道“哪个输入名称对应哪一个节点”，不必自己遍历整棵树猜地区文本存在哪里。

本例按 nodeList 下标从小到大扫描：

| 扫描到的节点 | 判断结果 | 生成的摘要名称 | 摘要 nodeId |
| --- | --- | --- | --- |
| 1（打开网页） | option=1、useLoop=false | urlList_0 | 1 |
| 2（地区循环） | option=8、loopType=3 | loopText_1 | 2 |
| 3（输入地区） | option=4、useLoop=true | 不另生成输入 | — |
| 5（页面循环） | option=8、loopType=0 | loopTimes_2 | 5 |
| 6（房源循环） | loopType=1，定位元素列表 | 此分支不生成文本输入 | — |

名称后缀跟着 inputIndex 自增；nodeId 则始终是数组下标。它不是“第几个输入”的编号，也不是界面 id。下面的地区摘要里 name=loopText_1、nodeId=2 两个数字含义不同。

源码扫描：

~~~js
for (let i = 1; i < nodeList.length; i++) {
  if (nodeList[i]["id"] != -1) {
    // 按 option 生成输入与输出摘要
  }
}
~~~

房源例子的主要输入：

| 来源节点 | 为什么成为输入 | 关键值 |
| --- | --- | --- |
| 1 打开网页 | option=1 且不使用循环值 | 网站地址列表 |
| 2 地区循环 | loopType 为 3 或 4 | 海淀、朝阳的 textList |
| 5 页面循环 | loopType=0 | exitCount=2 |
| 3 输入地区 | useLoop=true | 不另外生成固定文本输入 |

地区输入摘要近似：

~~~json
{
  "name": "loopText_1",
  "nodeId": 2,
  "nodeName": "地区循环",
  "type": "text",
  "value": "海淀\n朝阳",
  "exampleValue": "海淀\n朝阳"
}
~~~

如果前面已经扫描到打开网页输入，`inputIndex` 为 1，所以这里叫 `loopText_1`。编号会受实际任务里的其他输入影响，不能把这个名称写死当规则。

`nodeId=2` 来自扫描下标 i，是**graph 的数组位置**。后续覆盖输入可以找到对应循环的 `parameters.textList`。

#### 4.1 生成 inputParameters 的具体代码

以下摘自 [logic.js](/source/?file=786aaf2ec8ee7dbd78.js) 的 saveService，只保留输入统计分支；初始化和执行语句保持源码写法，省去任务表单读取、输出统计和其他保存逻辑：

~~~js
let inputParameters = [];
let inputIndex = 0;
let links = "about:blank";

for (let i = 1; i < nodeList.length; i++) {
    if (nodeList[i]["id"] != -1) { //已经被删除的节点不进行统计
        if (nodeList[i]["option"] == 1) //打开网页操作，统计输入框输入操作
        {
            if (!nodeList[i]["parameters"]["useLoop"]) //如果不是使用循环里的文本
            {
                inputParameters.push({
                    id: inputIndex,
                    name: "urlList_" + inputIndex++,
                    nodeId: i, //记录操作位于的节点位置，重要！！！
                    nodeName: nodeList[i]["title"],
                    value: nodeList[i]["parameters"]["links"],
                    desc: LANG("要采集的网址列表，多行以\\n分开", "List of URLs to be collected, separated by \\n for multiple lines",),
                    type: "text",
                    exampleValue: nodeList[i]["parameters"]["links"]
                });
                links = nodeList[i]["parameters"]["links"];
            }
        } else if (nodeList[i]["option"] == 4) //输入文字操作
        {
            if (!nodeList[i]["parameters"]["useLoop"]) //如果不是使用循环里的文本
            {
                inputParameters.push({
                    id: inputIndex,
                    name: "inputText_" + inputIndex++,
                    nodeName: nodeList[i]["title"],
                    nodeId: i,
                    desc: LANG("要输入的文本，如京东搜索框输入：电脑", "The text to be entered, such as 'computer' at eBay search box"),
                    type: "text",
                    exampleValue: nodeList[i]["parameters"]["value"],
                    value: nodeList[i]["parameters"]["value"],
                });
            }
        } else if (nodeList[i]["option"] == 8) //循环操作
        {
            if (parseInt(nodeList[i]["parameters"]["loopType"]) > 2 && parseInt(nodeList[i]["parameters"]["loopType"]) < 5) { //循环中的循环输入文本或循环输入网址
                inputParameters.push({
                    id: inputIndex,
                    name: "loopText_" + inputIndex++,
                    nodeId: i,
                    nodeName: nodeList[i]["title"],
                    desc: LANG("要输入的文本/网址,多行以\\n分开", "Text/URL to be entered, multiple lines should be separated by \\n"),
                    type: "text",
                    exampleValue: nodeList[i]["parameters"]["textList"],
                    value: nodeList[i]["parameters"]["textList"],
                });
            } else if (parseInt(nodeList[i]["parameters"]["loopType"]) == 0) {
                inputParameters.push({
                    id: inputIndex,
                    name: "loopTimes_" + inputIndex++,
                    nodeId: i,
                    nodeName: nodeList[i]["title"],
                    desc: LANG("循环" + nodeList[i]["title"] + "执行的次数（0代表无限循环）", "Number of loop executions for loop " + nodeList[i]["title"] + ", 0 means unlimited loops (until element not found)"),
                    type: "int",
                    exampleValue: nodeList[i]["parameters"]["exitCount"],
                    value: nodeList[i]["parameters"]["exitCount"],
                });
            }
        }
    }
}
~~~

**外层循环的含义：** 从 i=1 开始跳过 root，按 nodeList 存储位置扫描，id=-1 的节点不统计。这里不遍历 sequence，也不使用 actionSequence；它依赖前面的删除逻辑正确标记节点，而不是在保存时重新检查 root 的可达性。

每条输入摘要中，id 是本次摘要的连续编号；name 的后缀来自同一个 inputIndex；nodeId 是来源节点的数组下标 i；nodeName 是节点标题；value、exampleValue 都复制节点当前的参数值。

比如 inputIndex=2 时，代码先计算 `id: inputIndex`，得到 id=2；随后计算 `name: "loopText_" + inputIndex++`，得到 loopText_2，并将 inputIndex 加到 3。跳过的节点不会消耗输入编号；不同种类的输入共用这一个计数器。

#### 4.2 各种节点什么时候生成输入，读哪个字段

| 来源节点条件（均要求 id!=-1） | 是否生成 | name 前缀 | value 与 exampleValue 的来源 | 摘要 type |
| --- | --- | --- | --- | --- |
| option=1，useLoop=false | 是 | urlList_ | parameters.links | text |
| option=1，useLoop=true | 否 | — | 由所在循环提供链接 | — |
| option=4，useLoop=false | 是 | inputText_ | parameters.value | text |
| option=4，useLoop=true | 否 | — | 由所在循环提供输入值 | — |
| option=8，loopType=3 | 是 | loopText_ | parameters.textList，固定文本列表 | text |
| option=8，loopType=4 | 是 | loopText_ | parameters.textList，固定网址列表 | text |
| option=8，loopType=0 | 是 | loopTimes_ | parameters.exitCount | int |
| option=8，loopType=1、2 或脚本类循环 | 否 | — | 该统计分支不提供相应输入入口 | — |
| 点击、提取、悬停、下拉、判断等其他操作 | 否 | — | 仍保留在 graph 中 | — |

loopType 先经过 parseInt，因此合法的数字字符串 "3"、"4"、"0" 也能进入对应分支。`type: "int"` 是摘要的类型说明，统计代码只是复制 exitCount，没有在这里转换它的数据类型。

#### 4.3 把房源图的三个输入完整算出来

沿用本讲房源图，设网址为 https://example.com/rent，地区为两行“海淀、朝阳”，页面循环次数为 2。按存储下标扫描，先遇到节点 1，再遇到节点 2，最后在节点 5 生成第三条输入。省略 desc 后，数组为：

~~~json
[
  {
    "id": 0, "name": "urlList_0", "nodeId": 1, "nodeName": "打开网页",
    "type": "text", "value": "https://example.com/rent",
    "exampleValue": "https://example.com/rent"
  },
  {
    "id": 1, "name": "loopText_1", "nodeId": 2, "nodeName": "地区循环",
    "type": "text", "value": "海淀\n朝阳", "exampleValue": "海淀\n朝阳"
  },
  {
    "id": 2, "name": "loopTimes_2", "nodeId": 5, "nodeName": "页面循环",
    "type": "int", "value": 2, "exampleValue": 2
  }
]
~~~

输入地区 3 的 useLoop=true，所以它没有第四条输入；房源循环 6 是 loopType=1，也不生成输入。名称 loopText_1 的 1 是输入摘要编号，nodeId=2 才表示地区循环位于 graph[2]。

#### 4.4 再用一个独立案例覆盖其余输入分支

下面是另一份图的节点统计字段，省去 sequence 和其他无关参数，不与房源图累加。可以把它作为第 4.1 节代码的 nodeList，直接核对结果：

~~~js
const nodeList = [
  {id:0, option:0, title:"root"},
  {id:1, option:1, title:"打开列表", parameters:{useLoop:false, links:"https://example.com/list"}},
  {id:2, option:4, title:"输入关键词", parameters:{useLoop:false, value:"单间"}},
  {id:3, option:4, title:"输入循环地区", parameters:{useLoop:true, value:"备用值"}},
  {id:4, option:8, title:"地区列表", parameters:{loopType:3, textList:"海淀\n朝阳"}},
  {id:5, option:8, title:"网址列表", parameters:{loopType:4, textList:"https://example.com/a\nhttps://example.com/b"}},
  {id:6, option:8, title:"翻页次数", parameters:{loopType:0, exitCount:2}},
  {id:7, option:8, title:"同类元素", parameters:{loopType:1}},
  {id:8, option:8, title:"固定元素", parameters:{loopType:2}},
  {id:-1, option:4, title:"已删输入", parameters:{useLoop:false, value:"不参与"}},
  {id:9, option:1, title:"打开详情", parameters:{useLoop:false, links:"https://example.com/detail"}},
  {id:10, option:1, title:"打开循环网址", parameters:{useLoop:true, links:"备用网址"}}
];
~~~

| 扫描位置 i | 发生什么 | 生成的 id / name | nodeId | value |
| --- | --- | --- | --- | --- |
| 1 | 固定打开网址 | 0 / urlList_0 | 1 | https://example.com/list |
| 2 | 固定输入文字 | 1 / inputText_1 | 2 | 单间 |
| 3 | useLoop=true，跳过 | — | — | — |
| 4 | 文本列表循环 | 2 / loopText_2 | 4 | 海淀、朝阳，两行 |
| 5 | 网址列表循环 | 3 / loopText_3 | 5 | a、b 两个网址，两行 |
| 6 | 单元素循环次数 | 4 / loopTimes_4 | 6 | 2 |
| 7、8 | 元素列表循环，跳过 | — | — | — |
| 9 | id=-1，跳过 | — | — | — |
| 10 | 第二个固定打开网址 | 5 / urlList_5 | 10 | https://example.com/detail |
| 11 | 使用循环网址，跳过 | — | — | — |

最终 inputParameters.length=6、inputIndex=6。节点 10 的界面 id=9，摘要 nodeId 仍写 10，进一步说明 nodeId 取的是扫描位置 i。

另外，源码每遇到一个符合条件的打开网页节点，就执行 `links = nodeList[i].parameters.links`。因此本例的任务顶层 serviceInfo.links 最后等于 detail 网址，**不是把所有打开网页节点的网址拼接起来**；两条 urlList 输入摘要则都会保留。

### 5. 把页面次数设为 2，保存的到底是什么

用户在页面循环里输入 2，保存后有两个相关位置：完整节点参数中的 exitCount=2；输入摘要中对应循环次数入口的 value=2。前者是执行时实际读取的位置，后者是可调整输入的描述。

如果这次运行把 loopTimes_2 改成 3，生成执行实例时会通过摘要的 nodeId=5 找到页面循环，并把实例内 graph[5].parameters.exitCount 改成 3。它不会创建第三份页面循环节点，也不会把房源循环复制三份。

这里“每轮页面”仍指房源循环加下一页点击组成的整个循环体。正常计数路径完成两轮后退出，第二轮末尾也会调用下一页；元素缺失和异常路径见第 16、17 讲。下面同时观察摘要值与源节点值。

摘要保存：

~~~text
nodeId=5
value=2
~~~

源节点保存：

~~~text
graph[5].parameters.exitCount=2
graph[5].sequence=[6,12]
~~~

这只是正常计数路径中“两轮循环体”的参数定义，不会生成两套房源循环节点。解释器运行时才根据参数重复。

页面最后一轮仍会执行下一页点击，真实异常和退出行为见第 16 篇。

### 6. outputParameters 是字段摘要，不替代采集节点

以“标题”一列为例：用户运行前想知道结果列名，顶层摘要告诉它 name=标题；执行时想知道从哪里读标题，必须继续进入 graph[11].parameters.params，找到 relativeXPath=//h1、nodeType、contentType 等配置。

| 对同一字段的描述 | 本例包含什么 | 谁主要使用 |
| --- | --- | --- |
| 顶层 outputParameters | 名称、类型、描述、示例、是否记录 | 输出结构、界面说明和执行器初始化 |
| 采集节点 parameters.params | 上述字段配置加 XPath、相对定位、内容类型 | getData 真正读取网页 |

如果后续把租金加为第二列，两处都会体现它，但没有必要把整个字段定位对象再复制到顶层摘要。多个提取节点都叫“标题”时，这个采集字段摘要按名字去重，首次遇到的字段说明会先占用该列名；它没有替用户合并不同 XPath 的业务含义。

自定义操作的输出摘要走另一个分支，不能把提取字段的名称去重规则无条件套到所有输出。下面先看普通采集字段的保存位置和摘要例子。

源字段仍在：

~~~text
graph[11].parameters.params
~~~

`saveService` 从提取节点里读取每个字段的名称、描述、字段类型、是否记录和示例值，并按名称去重生成任务顶层输出摘要。

比如：

~~~json
{
  "name": "标题",
  "desc": "房源标题",
  "type": "text",
  "recordASField": 1,
  "exampleValue": "海淀 单间 2500元"
}
~~~

实际字段还需要 `relativeXPath`、`nodeType`、`contentType` 等定位与取值设置；这些仍保存在采集节点内。

因此：

~~~text
顶层 outputParameters：这个任务会输出哪些列
节点 parameters.params：怎样定位并读取这些列
~~~

看到顶层没有 XPath，不意味着 XPath 丢失。

#### 6.1 生成 outputParameters 的具体代码

下面仍摘自同一个 saveService，只保留输出统计分支，并移除已被注释的旧代码；有效语句保持源码写法。这是原统计循环的另一个视角，不是让保存函数再执行一遍重复统计：

~~~js
let outputParameters = [];
let outputNames = [];
let outputIndex = 0;

for (let i = 1; i < nodeList.length; i++) {
  if (nodeList[i]["id"] != -1) {
    if (nodeList[i]["option"] == 3) //提取数据操作
    {
        for (let j = 0; j < nodeList[i]["parameters"]["params"].length; j++) {
            if (outputNames.indexOf(nodeList[i]["parameters"]["params"][j]["name"]) < 0) { //参数名称还未被添加
                outputNames.push(nodeList[i]["parameters"]["params"][j]["name"]);
                outputParameters.push({
                    id: outputIndex++,
                    name: nodeList[i]["parameters"]["params"][j]["name"],
                    desc: nodeList[i]["parameters"]["params"][j]["desc"],
                    type: nodeList[i]["parameters"]["params"][j]["paraType"],
                    recordASField: nodeList[i]["parameters"]["params"][j]["recordASField"],
                    exampleValue: nodeList[i]["parameters"]["params"][j]["exampleValues"][0]["value"],
                });
            }
        }
    } else if (nodeList[i]["option"] == 5) //自定义操作
    {
        let id = outputIndex++;
        let title = nodeList[i]["title"];
        outputNames.push(title);
        outputParameters.push({
            id: id,
            name: title,
            desc: LANG("自定义操作返回的数据", "Output of custom action"),
            type: nodeList[i]["parameters"]["paraType"],
            recordASField: nodeList[i]["parameters"]["recordASField"],
            exampleValue: "",
        });
    }
  }
}
~~~

这里 outputIndex 和 inputIndex 各自从 0 开始。两条输入和一条输出可以分别拥有 id=0，它们属于不同数组，不是节点编号。

#### 6.2 提取字段与自定义操作，逐项读什么

对于 option=3 的提取节点，先按 params 的顺序检查每个字段：

1. 用字段 name 查 outputNames；已经出现就跳过整条摘要，不增加 outputIndex。
2. 没出现则将名字记入 outputNames，并追加输出摘要。
3. 摘要 name、desc、recordASField 分别复制字段同名属性，type 来自字段的 paraType。
4. exampleValue 只取 exampleValues[0].value，不把所有示例值都放进摘要。

对于 option=5 的自定义操作，则直接追加：name 使用节点 title，type 使用节点 parameters.paraType，recordASField 使用节点参数，desc 为“自定义操作返回的数据”，exampleValue 固定为空字符串。

**两个边界要按代码理解：提取字段会查重，自定义操作不会查重；recordASField=0 的配置仍会进入摘要。** 是否记录作为摘要属性保存下来，生成摘要时没有以它作为过滤条件。自定义操作也会把自己的标题放进 outputNames，所以后面遇到同名提取字段时，提取字段会被跳过。

输出摘要本身没有 nodeId、XPath 或提取节点的 option；相应定位信息仍保存在 graph。这里也不会现场执行网页采集或自定义脚本，exampleValue 来自已有示例配置。提取分支直接访问 exampleValues[0].value，没有为缺失示例数组设置回退值。

#### 6.3 用一个独立案例看清去重顺序

本讲房源图原来只有标题字段时，只生成 id=0 的标题摘要；若在同一个提取节点的 params 后面增加租金，就再生成 id=1 的租金摘要。下面另用一份统计快照展示重名和自定义输出，不改变前面的房源图：

~~~js
const nodeList = [
  {id:0, option:0, title:"root"},
  {id:1, option:3, title:"提取列表", parameters:{params:[
    {name:"标题", desc:"列表标题", paraType:"text", recordASField:1,
     exampleValues:[{value:"A单间"},{value:"B单间"}]},
    {name:"内部变量", desc:"仅供后续引用", paraType:"int", recordASField:0,
     exampleValues:[{value:"1"}]}
  ]}},
  {id:2, option:3, title:"提取详情", parameters:{params:[
    {name:"标题", desc:"详情标题", paraType:"text", recordASField:1,
     exampleValues:[{value:"详情A"}]},
    {name:"租金", desc:"月租金", paraType:"double", recordASField:1,
     exampleValues:[{value:"2500"}]}
  ]}},
  {id:3, option:5, title:"标题", parameters:{paraType:"text", recordASField:0}},
  {id:4, option:5, title:"脚本计数", parameters:{paraType:"int", recordASField:1}},
  {id:5, option:3, title:"再次提取", parameters:{params:[
    {name:"脚本计数", desc:"网页上的计数", paraType:"int", recordASField:1,
     exampleValues:[{value:"99"}]},
    {name:"地址", desc:"房源地址", paraType:"text", recordASField:1,
     exampleValues:[{value:"海淀"}]}
  ]}},
  {id:-1, option:5, title:"已删脚本", parameters:{paraType:"text", recordASField:1}}
];
~~~

按 nodeList 下标 i，再按提取节点里的字段下标 j 扫描：

| 扫描到什么 | 查重及过滤结果 | 追加的输出 id | 原因 |
| --- | --- | --- | --- |
| i=1 的标题 | 追加 | 0 | 第一次遇到标题 |
| i=1 的内部变量 | 追加 | 1 | recordASField=0 仍收集配置 |
| i=2 的标题 | 跳过 | — | 标题已在 outputNames 中，保留第一次的说明与示例 |
| i=2 的租金 | 追加 | 2 | 新字段名 |
| i=3 的自定义操作“标题” | 追加 | 3 | 自定义分支不检查重名 |
| i=4 的自定义操作“脚本计数” | 追加 | 4 | 直接追加，并将标题放进 outputNames |
| i=5 的提取字段“脚本计数” | 跳过 | — | 名称已被前面的自定义操作占用 |
| i=5 的地址 | 追加 | 5 | 新字段名 |
| i=6 的已删脚本 | 跳过 | — | id=-1，外层条件不通过 |

最终 outputParameters 为：

~~~json
[
  {"id":0, "name":"标题", "desc":"列表标题", "type":"text",
   "recordASField":1, "exampleValue":"A单间"},
  {"id":1, "name":"内部变量", "desc":"仅供后续引用", "type":"int",
   "recordASField":0, "exampleValue":"1"},
  {"id":2, "name":"租金", "desc":"月租金", "type":"double",
   "recordASField":1, "exampleValue":"2500"},
  {"id":3, "name":"标题", "desc":"自定义操作返回的数据", "type":"text",
   "recordASField":0, "exampleValue":""},
  {"id":4, "name":"脚本计数", "desc":"自定义操作返回的数据", "type":"int",
   "recordASField":1, "exampleValue":""},
  {"id":5, "name":"地址", "desc":"房源地址", "type":"text",
   "recordASField":1, "exampleValue":"海淀"}
]
~~~

这时 outputIndex=6，outputNames 为 `["标题","内部变量","租金","标题","脚本计数","地址"]`，它本身也可能重复。可见不能把整个生成逻辑概括成“所有输出统一按名称去重”，也不能把摘要条数直接视为最终写出的列数；后续使用还会读取 recordASField 等配置。

### 7. containJudge 与图结构不是同一份控制流

如果把 containJudge 从 true 改成 false，却保留 graph[7] 的判断节点和分支参数，图中这组条件并没有被删除。这个布尔值是“任务包含判断”的摘要，真正选分支仍由执行器读取节点 option 和条件参数。

反过来，一个只有 containJudge=true、没有任何条件节点的对象，也无法凭这个布尔值自动生成单间判断。

本例扫描到未删除的 7（判断）时设为 true；如果已经删除房源处理子树并给其中所有节点标记 id=-1，这个扫描不会把已删除判断算进去。下面列出的 graph 条件才是执行语义的来源。

只要扫描到未删除的 `option=9`，就将 `containJudge=true`。

它是任务级标记，不能取代：

~~~text
graph[7].sequence=[8,9]
graph[8].parameters.class=3
graph[8].parameters.value="单间"
~~~

真正选择哪个分支，仍由判断节点和各分支参数决定。

---

## 第三部分：数据怎样送到磁盘

### 8. 请求体里先把 serviceInfo 转为字符串

用“海淀、朝阳”这个字段看清三层对象，特别是换行怎样保留下来：

| 阶段 | 当前是什么 | 地区文本怎样表示 |
| --- | --- | --- |
| 浏览器内存 | JavaScript 对象 serviceInfo | textList 是包含真实换行的字符串 |
| JSON.stringify 之后 | 一段 JSON 文本 | JSON 文本里用转义的反斜杠 n 表示换行 |
| $.post 表单序列化 | 请求体中的 params 字段 | JSON 文本再经过表单编码 |
| 后端解码之后 | 先得到 body.params 字符串，再得到 data 对象 | JSON.parse 恢复真实换行 |

因此前端发送的 params 不是节点里的 parameters，也不是采集字段数组 params，只是 HTTP 接口约定的一个表单字段名。普通保存带原任务 id；另存为在发送前改为 -1，要求服务器分配新任务编号。下面按这两层解码读代码。

前端：

~~~js
$.post(backEndAddressServiceWrapper + "/manageTask", {
  params: JSON.stringify(serviceInfo)
}, function (result) {
  $("#serviceId").val(parseInt(result));
});
~~~

这里 `params` 字段装的是 JSON 字符串。它与整个 HTTP 请求体不一定都是 JSON 格式，是两层概念。

`saveService(1)` 的“另存为”先把服务 ID 设成 `-1`；普通保存保留原服务 ID。

### 9. server.js 不是 Express 路由示例

先算一次文件编号：假设 tasks 目录里已有 0.json、2.json、42.json。新任务带 id=-1，服务器取已有编号最大值 42 再加 1，得到 43，不会因为“只有三个文件”就分配 3。

| 请求中的 id | 服务端选择 | 文件变化 |
| --- | --- | --- |
| -1，首次保存 | 扫描已有编号，分配 43 | 尝试写 tasks/43.json |
| 43，普通保存 | 使用原 id | 尝试覆盖 tasks/43.json |
| -1，另存为 | 再次扫描，假设最大值已为 43 | 尝试写 tasks/44.json，原任务 43 保留 |

后端还会把分配出的编号写回 data.id，所以文件内容的任务 id 与文件名一致。完成路径计算后，把整个 data 转回 JSON 文本并交给 fs.writeFile，再返回编号。

这里没有假设源码使用 Express。请求由 Node HTTP 服务按 pathName 分支处理，表单用 querystring.parse，任务文本再用 JSON.parse。下面各行正是这条请求的实际解析与写入核心。

后端源码：[server.js](/source/?file=a4700292967cb97c43.js)，搜索 `"/manageTask"`：

~~~js
body = querystring.parse(body);
data = JSON.parse(body.params);
let id = data["id"];
~~~

这段使用 Node 的 HTTP 服务与路径分支，不能写成仓库实际存在 `app.post("/manageTask")` 的 Express 路由。

如果 `id==-1`，扫描 `tasks` 中的 JSON 文件编号，选择新的编号；否则用原编号。

然后（路径表达式换成字符串拼接，以免混淆模板字符串）：

~~~js
data = JSON.stringify(data);
fs.writeFile(
  path.join(getDir(), "tasks/" + id + ".json"),
  data,
  (err) => {}
);
res.write(id.toString(), "utf8");
res.end();
~~~

`getDir()` 根据运行方式选择数据目录；开发时常见的是 ElectronJS 下的 tasks，打包后不能假定仍是源码目录。

### 10. 当前保存反馈有一个实现边界

用户看到的两个反馈发生在不同地方：前端发出 $.post 后就隐藏弹窗、显示“保存成功”；收到后端返回的编号后才把 serviceId 改成 43。后端本身又在异步 writeFile 回调完成前发送编号。

按时间顺序写出来，更容易读懂：

| 顺序 | 执行位置 | 实际做了什么 |
| --- | --- | --- |
| 1 | 前端 | 发起 POST，并继续执行本地显示成功的代码 |
| 2 | 后端 | 解析、分配 ID，发起异步文件写入 |
| 3 | 后端 | 返回任务 ID 文本 |
| 4 | 前端回调 | 更新 serviceId；另存为时跳转到新任务地址 |
| 写入回调 | 后端 | 当前回调为空，没有把写入结果回传给上述提示 |

所以“拿到了编号”和“已确认磁盘写完”不是同一个完成条件。这是本仓库当前实现的具体行为，例子中没有把 UI 提示当作一次严格完成的持久化确认。

`fs.writeFile` 是异步调用，回调里没有报告错误；服务在等待它完成之前就可以返回 ID。

前端调用 `$.post` 后也立即显示“保存成功”，并不是所有反馈都等待可靠的磁盘写入完成。

所以讲义可以说“这条路径尝试把任务写入文件”，不能把 UI 成功提示当成持久化成功的严格保证。

阅读存储逻辑时，既要看数据怎么转换，也要看完成信号由谁发出。

---

## 第四部分：重新加载为什么还能画回原样

### 11. queryTask 读出同一个 JSON 文件

保存后的设计窗口地址携带任务 ID=43。重新打开时请求 /queryTask?id=43；后端把 tasks/43.json 的文本返回，并声明 Content-Type 为 application/json，前端回调得到解析后的任务对象 result。

接着有两个赋值：nodeList=result.graph，让结构编辑使用恢复的数组；app.$data.list.nl=nodeList，让界面数据也指向这份数组。然后才补兼容字段、恢复任务表单并 refresh。

| 重新打开前后 | graph 的存储下标 | actionSequence |
| --- | --- | --- |
| 文件中 | 保留保存时的对象位置和 sequence | 没有单独保存 |
| 收到响应后 | 放回 nodeList | 还需要重建 |
| refresh 完成后 | 位置保持，辅助 id 可被覆盖 | 根据当前可达图重新计算 |

后端读取失败会走 404 错误路径，并不会凭文件编号自动生成一份正确的空任务。下面先看前端拿回图，再看后端读文件。

前端：

~~~js
$.get(backEndAddressServiceWrapper + "/queryTask?id=" + sId,
      function (result) {
  nodeList = result["graph"];
  app.$data.list.nl = nodeList;
  // 兼容处理、恢复界面字段
  refresh();
});
~~~

后端的关键读取与返回（路径仍以等价拼接写法展示）：

~~~js
const data = fs.readFileSync(
  path.join(getDir(), "tasks/" + tid + ".json"), "utf8");
res.writeHead(200, {"Content-Type":"application/json"});
res.write(data);
res.end();
~~~

前端拿到任务对象后，图的核心结构又回到 `nodeList`。

### 12. 兼容修补针对具体字段，不是重新推导整个任务

用一个老提取节点具体说明：它的参数里写的是 paras=[标题字段]，没有 params。当前 getData 和界面逻辑读取 params，因此加载时把旧数组赋给新字段名。

~~~js
// 旧节点关键字段示意
const oldParameters = {paras: [{name: "标题", relativeXPath: "//h1"}]};
// 与当前加载补丁一致的赋值效果：
oldParameters.params = oldParameters.paras;
// 字段内容不重新推断，只是让新读取入口能拿到原数组
~~~

打开网页节点如果缺少 cookies，就补空字符串。这个补丁不会自动修正失效的房源 XPath，也不会替用户判断“整租条件是否应该改成单间”。版本不同还会显示提示，所以兼容范围要以代码中明确处理的字段为准。

加载代码中：

~~~text
旧打开网页节点缺 cookies：
    补成空串

旧提取节点有 paras、没有 params：
    parameters.params = parameters.paras
~~~

还会恢复名称、ID、URL、描述和其他可匹配的界面项，比较任务版本并显示兼容提示。

因此不要讲成“任何旧任务都能自动升级成功”；源码只对特定格式做了补充处理。

### 13. 为什么不需要保存 actionSequence

假设文件里下一页节点的 id 已经不是当前应有的编号，但它仍位于 graph[12]，页面循环仍保存 sequence=[6,12]。重新加载后，refresh 从 root 找到它，再给它当前界面 id；下标 12 和它与页面循环的关系才是恢复图的关键。

这也解释了删除后的节点：文件仍可能带着 nodeList[4] 的旧对象，但地区循环已经没有引用 4。加载后 refresh 不访问它，所以不会“因为数组里还有这个对象”就重新画一个搜索方块。

旧辅助字段是对象的一部分，可能随 graph 一起写入；“无需单独保存映射”不等于“JSON 中所有 id 字段都被删除”。恢复时以结构重新建立界面数据即可。

加载后的 `refresh` 再次从 root 沿 `sequence` 做 BFS：

~~~text
graph 给出稳定 index 与孩子关系
    ↓
重算 id、parentId、position、isInLoop
    ↓
重建 actionSequence
    ↓
按父容器 append HTML
~~~

文件里原有的辅助编号可以被刷新覆盖。关键是数组位置和 `sequence` 保持一致。

删除过的节点仍留在 `graph`，但已经不在 root 的可达结构里，刷新不会把它重新画出来。

### 14. 正式执行也不需要界面编号映射

这次把设计器窗口完全关掉，只启动执行任务。Python 仍能跑，因为它需要的是 graph，而不是设计器里的方块 DOM。

比如执行页面循环读到孩子 12，直接取 self.procedure[12]，根据 option=2 调用点击；不需要先知道这个对象原来在界面上叫 id=7，也不需要加载 actionSequence。

同样，判断分支引用 8，直接取 graph[8] 并读 class=3、value=单间。图结构中的数字与执行器的数组读取方式一致，这就是稳定下标的价值。下面两段是真实执行器使用 graph 的入口，完整调用链见第 16、17 讲。

Python：

~~~python
self.procedure = service["graph"]
self.executeNode(0)
~~~

后续读取：

~~~python
node = self.procedure[nodeId]
~~~

它解释 `option` 和 `sequence`，不需要 HTML，也不需要界面的 `actionSequence`。

执行器还会预处理参数、处理运行输入等。完整启动和浏览器控制见第 16、17 讲；这里重点对照图结构与执行器之间的契约。

---

#### 14.1 一次具体执行怎样覆盖地区和次数

现在任务 43 的默认地区仍是“海淀、朝阳”，次数仍是 2；本次想执行“西城、东城，每个地区一轮”。调用生成执行实例的接口时，可提供下面的覆盖值（字段名来自第 4 节的输入摘要）：

~~~json
{
  "loopText_1": "西城\n东城",
  "loopTimes_2": "1"
}
~~~

后端 /invokeTask 先读取原任务，再拿覆盖名称匹配 inputParameters。loopText_1 对应 nodeId=2，改地区循环的 textList；loopTimes_2 对应 nodeId=5，改页面循环的 exitCount。实际分支核心如下，摘自 [server.js](/source/?file=a4700292967cb97c43.js)：

~~~js
for (const [key, value] of Object.entries(data)) {
  for (let i = 0; i < task["inputParameters"].length; i++) {
    if (key === task["inputParameters"][i]["name"]) {
      // 能调用
      const nodeId = parseInt(task["inputParameters"][i]["nodeId"]);
      const node = task["graph"][nodeId];
      if (node["option"] === 1) {
        node["parameters"]["links"] = value;
      } else if (node["option"] === 4) {
        node["parameters"]["value"] = value;
      } else if (
        node["option"] === 8 &&
        node["parameters"]["loopType"] === 0
      ) {
        node["parameters"]["exitCount"] = parseInt(value);
      } else if (node["option"] === 8) {
        node["parameters"]["textList"] = value;
      }
      break;
    }
  }
}
~~~

这里 name 用于查输入入口，nodeId 用于查图中对象，option 与 loopType 决定覆盖哪个参数。对次数还要 parseInt，把输入字符串“1”转成数字 1。本例 loopType 由设计器保存为数值 0，满足源码中的严格比较。

覆盖后，后端把这份配置另写到 execution_instances/执行实例ID.json。假定本次得到实例 ID=7，文件中的任务 id 会改成 7，但 graph[2] 仍是地区循环，graph[5] 仍是页面循环；整份实例编号变化不会改变内部节点下标。原 tasks/43.json 的默认地区和次数保留，本次实例携带覆盖后的值。

## 第五部分：用一次往返验证你的理解

### 15. 从内存到文件再回来，哪些必须保持

先在浏览器控制台中做一次不碰磁盘的序列化练习。假定 serviceInfo 已由本讲保存函数组装，下列代码只是验证 JSON 往返后的关键数据，不是替代后端保存接口：

~~~js
const text = JSON.stringify(serviceInfo);
const restored = JSON.parse(text);
console.log(restored.graph[5].sequence);               // [6,12]：房源循环、下一页
console.log(restored.graph[8].parameters.value);       // 单间
console.log(restored.graph[11].parameters.params[0].relativeXPath); // //h1：标题路径
~~~

如果这三项恢复，说明“孩子顺序、条件文本、字段定位”没有在 JSON 转换时丢失。还要对照整个数组长度和每个节点的 index，确保没有在发送前过滤删除项或按界面 id 排序。

接到磁盘后也是同一个契约：先服务端写 JSON，再读回相同数据，最后 refresh 重新显示。下面把设计器、文件、加载和正式执行四个阶段排在一起。

以房源图为例：

~~~text
设计器：
    5.sequence=[6,12]
    7.sequence=[8,9]
    8.sequence=[10,11]

JSON：
    graph 原样保留这些下标与对应对象

重新打开：
    refresh 可能重建界面编号
    仍然是先房源循环再下一页
    仍然先检查单间再走兜底

执行：
    每页的房源判断结束后才翻页
    单间点击与提取
    非单间空分支返回
~~~

检查四点：

1. 没有把 graph 按界面 id 重排；
2. 没有直接过滤已删除对象导致数组位置改变；
3. 条件仍在分支参数里；
4. 操作参数与所属循环仍然匹配。

如果要压缩数组或改变存储格式，就得同步重写所有孩子引用、节点 index 和输入摘要 nodeId；当前实现没有走这条路线。

### 16. 回答这一组讲义最开始的问题

把第 15 讲的构建过程与第 18～23 讲的界面流程串起来：先从一个 root 开始，追加普通对象、用父 sequence 存顺序；在中间加入循环时，对象仍追加末尾，再调整父子引用；refresh 从 root 编号并建立层次 DOM；手动增删改查落到节点对象和孩子列表；消息到来后复用这些新增、修改与移动入口；最后把整个 nodeList 作为 graph 保存，加载后重新画图。正式执行仍从 graph[0] 开始解释。

最后再区分一次同名参数：运行前输入摘要 inputParameters 指“哪些值可被覆盖”；节点 parameters 指“这个动作的设置”；提取节点 parameters.params 指“这个动作要读哪些字段”；HTTP 表单 params 指“服务端接口里装任务 JSON 的字段”。它们属于不同对象，不能因为都含 parameter 就认为保存的是同一层数据。

下面的总链路可以配合前四讲逐条回查源码：每一步都应能指出当前处理的数据对象和下一个接收它的函数。

~~~text
只有顺序操作：
    列表即可表达先后

加入循环与判断：
    需要保存有序孩子关系、循环输入、分支条件与操作参数

怎样执行：
    root / 分支顺序执行孩子
    循环重复执行孩子
    判断只选择首个满足的分支
    普通节点调用浏览器操作
    调用栈负责解释器返回，历史处理负责网页返回

怎样在界面上编辑：
    改 nodeList 对象与父 sequence
    BFS 重算界面辅助字段
    重新建立层次 DOM

怎样长期保留：
    nodeList 作为 graph 写入任务 JSON
    加载后重建界面
    正式执行直接解释 graph
~~~

第 24 讲继续解释 Electron 怎样承接窗口与通信；第 25 讲再从 trial.js 的相反方向看：选中一个流程图节点，怎样把定位与反馈送回网页。有了这里的节点、字段和父容器模型，就能理解调试消息为什么需要携带当前节点和循环上下文。

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[22.循环采集子元素与 Vue 参数栏](/easyspider/chapter-22) ｜ 下一篇：[24.ElectronJS：把网页变成桌面软件](/easyspider/chapter-24)
