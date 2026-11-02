---
title: "12 · toolkit.vue"
description: "easyspider · 界面与通信 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/12.toolkit.vue详解.md"
originalUrl: "/originals/easyspider/chapter-12.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 12.toolkit.vue：怎样画出操作台、显示表格并修改选择

前一篇补了 Vue 的模板语法、状态与方法。这一篇沿用第 10 篇的商品卡片案例，重点看 `toolkit.vue` 怎样把状态画成界面：`page` 为不同值时显示什么，字段表怎样逐行逐列显示，以及扩大选区、撤销选择、删除行、删除列之后，网页上的选择和操作台里的表格分别怎样变化。

阅读顺序是：**先看界面示意，再代入数据，最后逐句读源码。** 第 10 篇负责解释字段和预览数组如何生成；本篇接着解释 Vue 怎样使用这些结果绘制操作台。输入、点击和发送消息等方法放在后面补充。

源码：[toolkit.vue](/source/?file=7da96f658c0d8f985c.vue)，入口：[main.js](/source/?file=54d4e6ba64e62921ba.js)。扩展实际使用 Vue 2.7；这里按真实的 `data` 对象、`new Vue(ToolKit)`、`beforeDestroy` 和过滤器解释，不把它改写成 Vue3 后再当作源码。

## 第一部分：先看界面状态，再看方法

### 1. 操作台与网页处于同一页，职责不同

继续使用[第 10 篇](/easyspider/chapter-10)的 Java、Python 两张商品卡片。为便于说明“向父节点扩大”，给其中几个节点加上字母：

```text
 A(section)
 ├── B(article)：Java 商品块
 │   ├── D(a href="/java")：Java 入门
 │   │   └── K(span) → em：入门
 │   ├── E(img src="java.jpg")
 │   ├── F(p)：￥99
 │   └── input value="1"
 └── C(article)：Python 商品块
     ├── G(a href="/python")：Python 入门
     │   └── L(span) → em：入门
     ├── H(img src="python.jpg")
     ├── I(p)：￥88
     ├── input value="2"
     └── strong：限时促销
```

对应的核心 HTML 如下，路径仍按第 10 篇的模型推演：

```html
<section>
  <article id="java">
    <a href="/java"><span>Java <em>入门</em></span></a>
    <img src="java.jpg">
    <p>￥99</p>
    <input value="1">
  </article>
  <article id="python">
    <a href="/python"><span>Python <em>入门</em></span></a>
    <img src="python.jpg">
    <p>￥88</p>
    <input value="2">
    <strong>限时促销</strong>
  </article>
</section>
```

后文把字段简称为“链接文本、链接地址、图片地址、价格、数量、促销”。实际表头读取字段对象的 `name`，可能是“参数1_链接文本”“参数4_文本”等；Vue 不会自行把段落识别成价格，也不会替我们给列起业务名称。参数编号取决于本地存储，不保证每次从 1 开始。

右键 D 是“选中网页节点”；在操作台点“采集文字”是“选择读取规则”；在操作台点“采集数据”是“确认把规则送给流程图”。三个动作不能合成一句“点一下就采集”。

`main.js` 为操作台绑定 `mousedown` 并阻止冒泡，所以点击操作台按钮不会继续冒泡到文档的 `addEl`，把按钮本身也选进商品列表。

### 2. 如何从 main.js 挂到页面

```js
let toolkit = document.createElement("div");
toolkit.classList = "tooltips";
toolkit.setAttribute("id", "wrapperToolkit");
document.body.append(toolkit);

// generateToolkit() 内的关键两步
$(".tooltips").html(`<div id="realcontent"></div>`);
global.app = new Vue(ToolKit);
```

`ToolKit` 的配置里有 `el:'#realcontent'`。按执行顺序：

1. 创建外层容器 `wrapperToolkit`，追加到当前网页。
2. 在容器里准备挂载点 `realcontent`。
3. `new Vue(ToolKit)` 读取组件选项中的 `el`，挂载模板。
4. 将实例保存到 `global.app`，供 `global.js` 写入界面状态。
5. 所以 `global.app._data.valTable = ...` 能改变预览，`global.app._data.option = ...` 能改变分支界面。

拖动、尺寸控制、关闭按钮和容器丢失后的重建，主要由 `main.js` 管理；它们不都是 `toolkit.vue` 的 methods。

### 3. page 决定当前子界面

#### 3.1 先看外框：换的是内容区，不是浏览器页面

中文模板的结构可以缩写成：

```html
<!-- 教学缩写：省略各分支内部的按钮和样式 -->
<div v-if="lang == 'zh'">
  <div class="tooldrag">✍操作台（点此拖动，左上角调整大小）</div>
  <div class="realcontent">
    <div v-if="page==0">选择、采集和预览表</div>
    <div v-else-if="page==1">输入文字</div>
    <div v-else-if="page==2">切换下拉选项</div>
    <div v-else-if="page==3">设置翻页操作</div>
  </div>
</div>
```

`v-if / v-else-if` 是一组互斥分支：`page=1` 时输入界面出现在操作台内，`page=0` 的按钮和表格退出当前 DOM；改回 `0`，Vue 再按状态创建默认界面。源码使用的是 `v-if`，并非把四套界面一直画好后只调整显示样式。

操作台标题、拖动区域和关闭按钮在这些 `page` 分支外面，所以切换内容时外框仍在。被采集的 Java、Python 卡片也仍在原网页上；`page=1` 不会让浏览器打开另一张网页。英文部分有相应分支，本篇按中文界面讲解。

| `page` | 内容区画什么 | 怎样进入 | 怎样返回 |
|---:|---|---|---|
| 0 | 选择提示、采集操作、字段预览与底部按钮 | 初始值，或清选择后回到这里 | 按具体操作进入 1、2、3 |
| 1 | 文字输入框、确定、取消、回车标记说明 | `setInput(false)` 或 `setInput(true)` | 取消只改 `page=0`；确定发送后 `clearEl()` 回到 0 |
| 2 | 切换模式下拉框、条件显示的值输入框、确定、取消 | `changeSelect()` | 取消调用 `cancelInput()`；确定切换后清选择 |
| 3 | 选择下一页元素的提示、确认或错误提示、取消 | `setNextPage()` | 确认后清选择；取消后回到 0 并保留翻页入口 |

以下方框都是**根据模板画出的教学示意**，省略部分提示、笑脸和通用按钮，帮助判断当前界面应出现什么。

#### 3.2 page=0，尚未选择任何节点

代入：`list.nl.length=0`、`nextPage=0`、`valTable=[]`。

```text
┌─ ✍操作台 ───────────────────────────┐
│ 采集当前页面的标题                   │
│ 采集当前页面的网址                   │
│ 提示：右键或 F2 选中页面元素          │
└─────────────────────────────────────┘
```

模板进入 `list.nl.length==0` 的区域。此时没有已选节点，因此不画“取消选择”“扩大选区”和路径提示；`valTable.length==0`，也不画字段表。

确认一次采集后，方法先清选择，再设 `nextPage=1`。这时仍然是 `page=0`，但空选择界面会额外出现“检测到您添加了采集数据操作”的提示和“设置翻页操作”入口。**`nextPage=1` 增加入口，`page=3` 才真正切换到翻页设置界面。**

#### 3.3 page=0，只选中 Java 商品块，还没选采集内容

代入：`nodeList=[B]`、候选 `readyList=[C]`、`selectStatus=false`、`selectedDescendents=false`。

```text
┌─ ✍操作台 ───────────────────────────┐
│ 已选中1个元素，同时发现1个同类元素   │
│   选中全部                           │
│   选中子元素                         │
│   采集该元素的文本                   │
│   点击该元素 / 采集 Inner、Outer HTML │
│   ……                                 │
│ [取消选择] [扩大选区]                │
│ Path: html/body/section/article       │
└─────────────────────────────────────┘
```

逐个判断条件：

| 模板条件 | 本例结果 | 画出的内容 |
|---|---|---|
| `list.nl.length==1` | true | 单元素操作区域 |
| `numOfReady()>0 && !selectStatus` | true | “选中全部” |
| `existDescendents() && !selectStatus`，且类型为元素或链接 | true，B 有孩子 | “选中子元素” |
| `!selectedDescendents && !selectStatus` | true | 针对当前节点的采集、点击等操作 |
| `list.nl.length>0` | true | 底部取消按钮和最后一个节点的路径 |
| `!selectStatus` | true | 底部扩大选区按钮 |

单元素的类型还会改变菜单。改选 D 链接，会显示采集链接地址；改选数量 INPUT，会显示“输入文字”和“批量输入文字”；选中 SELECT 才显示“切换下拉选项”。这里 `tname()` 的名称直接参与条件判断。

如果对 B 点击“采集该元素的文本”，`getText()` 把 `selectStatus` 设为 true；等参数回调完成后，界面显示整块文本的预览和“确认采集”。原来的单元素操作菜单及“扩大选区”因为条件不成立而消失。

如果对 B 点击“选中子元素”，算法回调把 `selectedDescendents` 设为 true，建立五个字段。此时菜单换成“采集数据”，表格显示 Java 的一行内部信息；`nodeList` 仍只有 B，不会变成五个已选元素。

#### 3.4 page=0，已选中 Java、Python 两个商品块

代入：`nodeList=[B,C]`、`option=50`。先不选子元素，`handleElement()` 会按同类节点生成整块内容的字段。点击“选中子元素（应选尽选）”后，才换成第 10 篇的六列、两行预览：

```text
┌─ ✍操作台 ─────────────────────────────────────────────────────┐
│ 已选择了2个同类元素，您可以：                               │
│   采集数据                                                 │
│   撤销本次选择                                             │
│ ┌链接文本×┬链接地址×┬图片地址×┬价格×┬数量×┬促销×───┬删除┐    │
│ │Java 入门│/java    │java.jpg │￥99 │1    │空白     │ ×  │    │
│ │Python…  │/python  │python…  │￥88 │2    │限时促销 │ ×  │    │
│ └─────────┴─────────┴─────────┴─────┴─────┴─────────┴────┘    │
│ [取消选择] [扩大选区]                                      │
└─────────────────────────────────────────────────────────────┘
```

选子元素前，若 `existDescendents()` 为 true，菜单提供应选尽选、相对首选块共同元素、所有块共同元素三个入口；选完后 `selectedDescendents=true`，这些入口和循环点击、循环移动入口不再显示。“采集数据”和“撤销本次选择”仍显示。本例 `selectStatus=false`，所以扩大选区仍可见。

如果多个节点的路径结构不一致，`option=100`，改画“已选择了以下元素”以及无规律多元素采集菜单，并由 `generateMultiParameters()` 生成一行预览。例如 Java 链接与 Python 图片会作为不同字段放到同一行。这说明**预览行数不总等于已选节点数量**，第 5 节会继续代入数组分析。

#### 3.5 page=1，把默认内容区换成输入文字界面

先选 Java 块中的 `<input value="1">`，点击“输入文字”：

```text
┌─ ✍操作台 ───────────────────────────┐
│ ● 请输入文字：                      │
│ [3<enter>                     ]     │
│ [确定] [取消]                       │
│ 输入 <enter> 或 <ENTER> 可模拟回车。 │
└─────────────────────────────────────┘
```

对应模板的核心语句是：

```html
<input id="WTextBox" v-model="text" type="text">
<button v-on:click="getInput">确定</button>
<button v-on:click="cancelInput">取消</button>
```

用户输入 `3<enter>`，先改变 Vue 的 `text`。此刻网页 INPUT 仍是原来的目标节点，键入操作台并不直接修改它；点确定后才调用 `input(this.text,this.batch)`。普通输入和批量输入都使用 `page=1`，区别由 `batch` 保存。取消只回到 `page=0`，保留已选 INPUT，`text` 也没有在 `cancelInput()` 中清空。

#### 3.6 page=2，根据切换模式再决定要不要画输入框

第 10 篇的商品 HTML 没有 SELECT。这里另外补一个教学用控件：

```html
<select>
  <option value="java">Java</option>
  <option value="py">Python</option>
</select>
```

选中它，当前选项是 Java，点击“切换下拉选项”，方法设 `page=2`、`optionMode=0`，并把下一个选项的文字 Python 保存到 `optionValue`。

```text
模式0：                         模式2：
┌─ ✍操作台 ───────────────┐      ┌─ ✍操作台 ───────────────┐
│ ● 切换模式              │      │ ● 切换模式              │
│ [切换到下一个选项 ▼]    │      │ [按选项值切换选项 ▼]    │
│ [确定] [取消]           │      │ ● 选项值                │
└─────────────────────────┘      │ [py                 ]   │
                                │ [确定] [取消]           │
                                └─────────────────────────┘
```

| `optionMode` | 模式 | 要画的额外标签 | 是否画 `selectValue` 输入框 |
|---:|---|---|---|
| 0 | 下一项 | 无 | 否，`optionMode != 0` 为 false |
| 1 | 按索引 | 索引值 | 是，例如 Python 索引为 1 |
| 2 | 按值 | 选项值 | 是，例如 `py` |
| 3 | 按文本 | 选项文本 | 是，例如 `Python` |

模式选择框用 `v-model="optionMode"`，值输入框用 `v-model="optionValue"`。改变模式还会触发 `@change="handleSelectChange"`，重填建议值；用户再编辑为自己想切换的值。模式 0 虽然不画输入框，数据中的 `optionValue` 仍存在。

#### 3.7 page=3，按选中数量画翻页设置提示

确认采集后，从空选择界面的“设置翻页操作”进入：

```text
刚进入，0个节点：               右键选中“下一页”，1个节点：
┌─ ✍操作台 ───────────────┐      ┌─ ✍操作台 ───────────────┐
│ 请右键选择下一页按钮。  │      │ 请右键选择下一页按钮。  │
│ 取消设置翻页操作        │      │ 已选中一个元素：下一页  │
└─────────────────────────┘      │ 确认设置翻页操作        │
                                │ 取消设置翻页操作        │
                                └─────────────────────────┘
```

`list.nl.length==1` 时才画选中元素的短文本及确认入口；超过一个则画红色提示“翻页操作只能设置一个元素”，并隐藏确认入口。取消入口一直存在。这里不会显示 `page=0` 的字段表和底部扩大选区按钮，即使数组中还有数据。

至此可以把绘制顺序写成：**语言 → page → 分支内部的状态条件 → 插值和循环绘制具体内容。** 不同状态条件可以同时满足，例如 `page=0` 的多元素菜单、表格和底部按钮就可以同时出现。

### 4. 最重要的状态分别记录什么

```js
list: {nl: global.nodeList, opp: global.outputParameters},
valTable: [],
selectedDescendents: false,
selectStatus: false,
nowPath: "",
nowAllPaths: [],
nextPage: 0,
lastAction: "collectData"
```

| 状态 | 用途 | 不应怎样理解 |
|---|---|---|
| `list.nl` | 已选网页节点记录，共享 `global.nodeList` | 不是字段列表 |
| `list.opp` | 字段列表，共享 `global.outputParameters` | 一个链接可以占两项 |
| `valTable` | 以列为外层的预览数组 | 每个内层数组是一列，不是实际抓取完成的数据文件 |
| `option` | `relatedTest()` 得到的关系分类，50 有规律、100 无规律 | 不是流程图节点的 option 枚举 |
| `selectStatus` | 单元素已经选择了采集内容，模板可显示确认采集 | 不是 WebSocket 已发送状态 |
| `selectedDescendents` | 当前参数来自子元素选择 | 不增加已选商品块数量 |
| `nowPath` / `nowAllPaths` | 共同匹配范围及备选定位 | 不等于单个字段的块内路径 |
| `mode` | 子元素模式，0 应选尽选、1 按首块、2 共同元素 | 删除行后重算时使用 |
| `nextPage` | 是否提示接着设置翻页 | `1` 不表示已经选好了翻页按钮 |
| `lastAction` | 最近添加的操作类别 | 后面影响翻页节点如何包装 |

后面的四种操作会反复用到这些状态，先记住：`nodeList` 决定选中了哪些网页节点，`outputParameters` 决定采哪些字段，`valTable` 决定预览格子里显示什么。三者有关联，但不是同一份数据。

### 5. table 怎样把第 10 篇的结果画出来

#### 5.1 先确定输入：两块、六个字段、六个列数组

正式选中 B、C，执行 `handleDescendents(0)`，等异步回调完成后，第 10 篇得到的几份数据可以缩写为：

```js
// 教学数据：字段名改用业务简称，省略 XPath、类型等属性。
// 实际 nodeList 保存对象，以下 B、C 表示两条块记录。
nodeList = [B, C];
outputParameters = [
  { name: "链接文本" },
  { name: "链接地址" },
  { name: "图片地址" },
  { name: "价格" },
  { name: "数量" },
  { name: "促销" }
];
valTable = [
  ["Java 入门", "Python 入门"], // 第0列
  ["/java", "/python"],         // 第1列
  ["java.jpg", "python.jpg"],   // 第2列
  ["￥99", "￥88"],             // 第3列
  ["1", "2"],                  // 第4列
  [" ", "限时促销"]            // 第5列，第一块没有促销
];
```

`list.nl` 指向 `global.nodeList`，`list.opp` 指向 `global.outputParameters`；`valTable` 则是 `generateValTable()` 写入 Vue 实例的数据。

这里有三个不同的长度：

| 表达式 | 本例的值 | 绘制时的用途 |
|---|---:|---|
| `list.nl.length` | 2 | 判断进入哪个选择菜单，显示已选块数量 |
| `list.opp.length` | 6 | 绘制六个字段表头和每行六个数据格 |
| `valTable.length` | 6 | 说明有六列，且大于 0，可以显示表格区域 |
| `valTable[0].length` | 2 | 绘制两行数据 |

`valTable.length` 是列数；如果把它当作行数，就会误以为这张表要画六行。

#### 5.2 什么情况下显示 table

真实模板在 `page==0` 内写了：

```html
<div v-if="valTable.length>0">
  <div class="toolkitcontain">
    <!-- 表头 table 和数据 table -->
  </div>
</div>
```

本例 `valTable.length=6`，显示预览区域。生成参数前或调用 `clearParameters()` 后，`valTable=[]`，条件为 false，整块预览退出 DOM。这个判断也避免空数组时继续读取 `valTable[0].length`。

但是“有预览”不等于“数据已经发送给流程图”。它只说明当前字段有可以展示的示例值；后面还要点击确认采集。

#### 5.3 为什么源码画了两个 table

实际结构是上面一张只放字段名的表，下面一张放数据的表：

```html
<div class="toolkitcontain">
  <table cellSpacing="0" class="toolkittb2">
    <tbody>
      <th v-for="(i, index) in list.opp">
        <div>{{ i["name"] }}</div>
        <span v-bind:index="index"
              v-on:mousedown="removeField" title="删除此字段">×</span>
      </th>
      <th style="width:40px">删除</th>
    </tbody>
  </table>
  <table cellSpacing="0" class="toolkittb4">
    <tbody>
      <tr v-for="i in valTable[0].length">
        <td v-for="j in list.opp.length">{{ valTable[j - 1][i - 1] }}</td>
        <td style="font-size: 22px!important;width:40px;cursor:pointer"
            v-bind:index="i-1" v-on:mousedown="deleteSingleLine">×</td>
      </tr>
    </tbody>
  </table>
</div>
```

配合 [toolkit.css](/source/?file=d099273d8c29eb0147.css) 理解布局：

```css
/* 摘录与布局直接相关的属性，其余省略。 */
.toolkitcontain {
  height: 150px;
  overflow: auto;
  position: relative;
}
.toolkitcontain table {
  table-layout: fixed;
  width: 100%;
}
.toolkitcontain .toolkittb2 {
  position: sticky;
  top: 0px;
  background-color: aliceblue;
  z-index: 1000;
}
.toolkitcontain .toolkittb4 {
  position: absolute;
}
```

外层是高度 150px、允许滚动的区域；表头使用 `position:sticky`，滚动时留在容器顶部，并用背景色遮住后面的数据。下面的数据表随滚动查看。两张表都按相同字段顺序布置，并在末尾多留一列“删除”，从而对应表头和行内的列位置。

这段源码直接把 `th` 写在 `tbody` 下，上面的代码保留原结构供对照；标准表头结构通常会写成 `thead > tr > th`。这里先读懂现有模板及样式，不把结构改写后当成原实现。

#### 5.4 表头循环：对象负责名字，下标负责删列

```html
<th v-for="(i, index) in list.opp">
  <div>{{ i["name"] }}</div>
  <span v-bind:index="index" v-on:mousedown="removeField">×</span>
</th>
```

这里 `i` 是字段对象，`index` 是从 0 开始的数组下标。循环前几次得到：

| 循环下标 `index` | `i` 对应字段 | 插值显示 | × 上的属性 |
|---:|---|---|---|
| 0 | 链接文本 | 链接文本 | `index="0"` |
| 1 | 链接地址 | 链接地址 | `index="1"` |
| 2 | 图片地址 | 图片地址 | `index="2"` |
| 3 | 价格 | 价格 | `index="3"` |
| 4 | 数量 | 数量 | `index="4"` |
| 5 | 促销 | 促销 | `index="5"` |

`v-bind:index` 把本次下标写成 DOM 属性，`v-on:mousedown` 绑定按下鼠标时的处理函数。按“价格”旁边的 ×，事件目标就是带 `index="3"` 的 span；`removeField(event)` 再用 `event.target.getAttribute("index")` 读出它。这个 `index` 是项目自己定义的属性，并非浏览器内置的删列功能。

第一个表头循环结束后，还画一个固定的“删除”表头。它没有字段删除 ×，也不占 `outputParameters` 的一项。

#### 5.5 数据循环：先选第几行，再从每一列取该行的值

```html
<tr v-for="i in valTable[0].length">
  <td v-for="j in list.opp.length">{{ valTable[j - 1][i - 1] }}</td>
  <td v-bind:index="i-1" v-on:mousedown="deleteSingleLine">×</td>
</tr>
```

这两个 `v-for` 都是数字范围循环。Vue 遍历数字 2 时给出 `1、2`，遍历数字 6 时给出 `1、2、3、4、5、6`；而 JavaScript 数组下标从 0 开始，因此这里要减 1。

**第一次外层循环：`i=1`，画 Java 的一行。**

| 内层 `j` | 实际访问位置 | 放到格子里的值 |
|---:|---|---|
| 1 | `valTable[0][0]` | Java 入门 |
| 2 | `valTable[1][0]` | `/java` |
| 3 | `valTable[2][0]` | `java.jpg` |
| 4 | `valTable[3][0]` | ￥99 |
| 5 | `valTable[4][0]` | 1 |
| 6 | `valTable[5][0]` | 一个空格，视觉上是空白 |

六个数据格画完，还要追加行尾 ×，它的属性是 `index="0"`。这一行一共有七个格子，最后一个是操作格，不是第七个采集字段。

**第二次外层循环：`i=2`，画 Python 的一行。**

内层依次读取 `valTable[0][1]` 到 `valTable[5][1]`，得到 Python 入门、`/python`、`python.jpg`、￥88、2、限时促销。行尾 × 的属性变为 `index="1"`。

所以最终看到：

| 链接文本 × | 链接地址 × | 图片地址 × | 价格 × | 数量 × | 促销 × | 删除 |
|---|---|---|---|---|---|---|
| Java 入门 | `/java` | `java.jpg` | ￥99 | 1 | 空白 | ×（index=0） |
| Python 入门 | `/python` | `python.jpg` | ￥88 | 2 | 限时促销 | ×（index=1） |

为避免混淆，这个表格里的“空白”和“index=…”是教学注记，实际页面只显示空格和 ×。

#### 5.6 第一块缺少促销，为什么后一行没有错位

第 10 篇已经讲过 `exampleValues` 到 `valTable` 的转换：促销字段只有 `{num:1,value:"限时促销"}`，`generateValTable()` 按块编号填值，在 `num=0` 的位置先补 `" "`，形成：

```js
valTable[5] = [" ", "限时促销"];
```

Vue 只负责把 `[5][0]` 和 `[5][1]` 显示出来，不会自行查 DOM 或补缺值。所有列在生成时按相同行数补齐，才使 `valTable[0].length` 能用于画整张表。

如果点击的是“所有块共同元素”，字段生成阶段会排除 Python 独有的促销，最终得到五列、两行。模板不用改：`list.opp.length` 和 `valTable` 变了，下一次渲染就少画一列。

#### 5.7 同一套模板也能画单块和无规律多节点预览

| 选择和生成方式 | `nodeList.length` | `valTable` 的结构 | 最终预览 |
|---|---:|---|---|
| 只选 B，再选子元素 | 1 | 五个列数组，每列一个值 | 五列、一行 |
| 选 B、C，应选尽选 | 2 | 六个列数组，每列两个值 | 六列、两行 |
| 选 B、C，所有块共同元素 | 2 | 五个列数组，每列两个值 | 五列、两行 |
| 无规律选择 D 链接和 H 图片 | 2 | 三个列数组，每列一个值 | 三列、一行 |

最后一种由 `generateMultiParameters()` 生成链接文本、链接地址、图片地址三列，再调用 `generateValTable(false)`，可以写成：

```js
valTable = [["Java 入门"], ["/java"], ["python.jpg"]];
```

页面画的是：

| Java 链接文本 × | Java 链接地址 × | Python 图片地址 × | 删除 |
|---|---|---|---|
| Java 入门 | `/java` | `python.jpg` | ×（index=0） |

这一行包含两个已选节点贡献的不同字段。因此行尾 × 的 `index=0` 并不代表“删除两个来源节点”，具体行为必须继续看 `deleteSingleLine()`。

#### 5.8 修改数组后，表格为什么能自动重画

组件初始化时建立共享引用：

```js
list: {nl: global.nodeList, opp: global.outputParameters},
valTable: []
```

例如 `global.outputParameters.splice(3,1)` 删除价格字段，`list.opp` 也立即少一项；再对 `this.valTable.splice(3,1)` 删除价格列，表头循环和数据循环便得到新的长度。Vue 2 会追踪这些数组变更，并在后续 DOM 更新中重画表格，不需要手工找出第三列的 `<td>` 再逐个删除。

这些数组用 `splice()` 原地修改也保留了共享关系。如果改为让 `global.outputParameters` 指向另一份全新数组，原来的 `list.opp` 引用不会自行转向新数组；现有代码避免了这个问题。

## 第二部分：先预览，后确认发送

### 6. getText() 只生成参数，不发送采集消息

```js
getText: function () {
  generateParameters(0, true, false);
  this.selectStatus = true;
  clearReady();
}
```

只选 D 时逐句推：

1. 调用参数函数：`type=0`，链接文本开启，链接地址关闭，所以请求生成一列链接文本。
2. 参数函数内部注册存储回调后返回；此刻不能假定字段已经生成。
3. 设置 `selectStatus=true`，让模板转入已选择采集规则的状态。
4. `clearReady()` 清候选及候选样式，D 仍保留在已选列表。
5. 编号回调到达，生成 D 的字段，再更新 `valTable`，预览才显示出来。

这说明按钮状态与字段生成存在异步先后；函数没有 `await generateParameters()`，也没有返回“生成完成”的 Promise。多链接只保留一列的源码问题见参数篇，不在这里重复当作正常流程。

### 7. 采集内容按钮对照

这些方法都采用“调用生成函数 → `selectStatus=true` → `clearReady()`”的结构：

| 方法 | 核心调用 | 示例 |
|---|---|---|
| `getText()` | `generateParameters(0,true,false)` | D 的链接文本 |
| `getLink()` | `generateParameters(0,false,true)` | D 的 `/java` |
| `getInnerHtml()` | `generateParameters(2,true,false)` | D 的内部 span HTML |
| `getOuterHtml()` | `generateParameters(3,true,false)` | D 的完整 a HTML |
| `getBackgroundPic()` | `generateParameters(4,true,false)` | 内联背景图地址 |
| `getSelectedValue()` | `generateParameters(10,true,false)` | SELECT 的选项 value |
| `getSelectedText()` | `generateParameters(11,true,false)` | SELECT 的选项显示文字 |
| `getCurrentURL()` | 先 `addEl()`，再 `generateParameters(5,true,false)` | 页面网址 |
| `getCurrentTitle()` | 先 `addEl()`，再 `generateParameters(6,true,false)` | 页面标题 |

最后两个仍需要一个选中节点占位，来源是当时的 `global.NowNode`，不是自动创建一个“页面标题 DOM”。

### 8. 三个确认采集方法，为什么 send 在 clear 之前

```js
confirmCollectSingle: function () {
  collectSingle();
  clearEl();
  this.nextPage = 1;
  this.lastAction = "collectData";
},
confirmCollectMulti: function () {
  collectMultiNoPattern();
  clearEl();
  this.nextPage = 1;
  this.lastAction = "collectData";
},
confirmCollectMultiAndDescendents: function () {
  collectMultiWithPattern();
  clearEl();
  this.nextPage = 1;
  this.lastAction = "collectDataWithLoop";
}
```

以 B、C 两个商品块采集为例：

1. 参数已经由 `handleDescendents()` 生成，确认按钮调用第三个方法。
2. `collectMultiWithPattern()` 读取现有字段、共同路径和子元素标记，立即序列化并发送。
3. 发送函数返回后，`clearEl()` 恢复选中样式、清已选节点、字段、预览等本地状态。
4. 设置 `nextPage=1`，空选择界面显示继续设置翻页的提示。
5. 记录 `lastAction="collectDataWithLoop"`，供下一次翻页操作使用。

必须先发送：如果先 `clearEl()`，发送函数读到的参数就被清掉了。但 `ws.send()` 返回不等于流程图已经处理成功；这些方法没有等待处理回执。

## 第三部分：改变选择时，参数为什么需要重算

### 9. selectDescendents()：把按钮模式交给算法

```js
selectDescendents: function (e, mode = 0) {
  handleDescendents(mode);
  this.mode = mode;
}
```

模板“应选尽选”直接绑定这个方法，事件作为 `e`，`mode` 取默认 `0`。另外两个按钮调用 `selectDescendents(1,1)`、`selectDescendents(1,2)`，第一个数字只是占据 `e` 的位置，第二个才是模式。

先把模式传给参数算法，再保存到 `this.mode`。`selectedDescendents=true` 是算法回调设置的，不是这里立即设置。

### 10. selectAll()：把候选转为正式选择

```js
selectAll: function () {
  selectAllElements(this);
}
```

1. 组件把自己传给 `global.js`，便于算法读取当前子元素状态。
2. 算法增加选择步骤，把 `readyList` 节点搬进 `nodeList`，清候选。
3. 调用 `handleElement()`，重新计算多元素关系和参数。
4. 如果已启用子元素模式，还会请求重新遍历商品块。

`readyList` 是候选，参数函数不会因为有候选就把它们全部当作已选记录；这一步才完成身份转换。

### 11. enlarge()：把最后一个已选节点换成它的父节点

#### 11.1 先看操作结果：从标题内部走到整张商品卡片

假设先右键选中了 Java 标题的 K（span），候选节点不算正式选择。连续按两次“扩大选区”：

```text
第0次：nodeList = [K(span)]     选中标题包装元素
                    │ 父节点
第1次：nodeList = [D(a)]        选中整个链接
                    │ 父节点
第2次：nodeList = [B(article)]  选中整个 Java 商品块
                    │ 父节点
第3次：nodeList = [A(section)]  选中两张卡片外面的共同容器
```

每次都是替换已有记录里的 `node`，列表长度始终为 1。选中 A 也不等于把 B、C 分别选进列表：`[A]` 是一个容器，`[B,C]` 是两个块，生成预览时对应的行数和字段定位方式不同。

如果当前 `nodeList=[D,G]`，最后一项是 Python 链接 G，那么按一次只得到 `[D,C]`；Java 链接 D 不动。两条路径的结构从“两个链接”变成“链接和商品块”，`handleElement()` 可能把关系分类改成 `option=100`，进而换成无规律多元素菜单和一行预览。

因此“扩大”指向 DOM 父节点移动一级，既不是把操作台窗口拉宽，也不是把所有已选节点同时扩大。

#### 11.2 把源码按执行顺序拆开

为减少反复出现的长下标，下面对原方法做等价拆写，`last` 指向原数组最后一个记录对象：

```js
// 教学拆写：不是额外新增的实现。
const last = global.nodeList[global.nodeList.length - 1];
if (last.node.tagName != "BODY") {
  last.node.style.backgroundColor = last.bgColor;
  last.node.style.boxShadow = last.boxShadow;

  const tNode = last.node.parentNode;
  let sty;
  if (tNode != global.NowNode) {
    sty = tNode.style.backgroundColor;
  } else {
    sty = global.style;
  }

  last.node = tNode;
  last.bgColor = sty;
  last.xpath = readXPath(tNode, 1);
  last.allXPaths = getElementXPaths(tNode);

  handleElement();
  global.oe = tNode;
  tNode.style.backgroundColor = "rgba(0,191,255,0.5)";
  this.selectedDescendents = false;
}
```

以 D 扩大到 B 为例：

| 顺序 | 代码做什么 | 对本例的影响 |
|---:|---|---|
| 1 | 判断末尾节点不是 BODY | D 可以向上扩大；到 BODY 后本方法不再继续 |
| 2 | 恢复旧节点的背景色、阴影 | D 退出这条正式选择记录，不再保留该选择的样式 |
| 3 | 取 `parentNode` | 得到 B（article） |
| 4 | 保存父节点原背景 | 以后取消 B 时有背景值可还原 |
| 5 | 改原记录中的 `node`、背景、路径 | 原记录由 D 变为 B，数组没有新增一项 |
| 6 | 调用 `handleElement()` | 清旧候选；单元素时找 B 的同类块，多元素时重测关系、生成字段 |
| 7 | 改 `global.oe`、给父节点着色 | 将当前选区指向并标记 B |
| 8 | `selectedDescendents=false` | 取消“已选择子元素”的界面标志，可以重新选 B 的内部字段 |

`sty` 的分支也是为还原样式服务的：如果 B 恰好是 `global.NowNode`，它当前的背景可能已被鼠标悬停处理改过，因此读 `global.style` 保存的原值；否则直接读 B 的背景。

#### 11.3 路径和界面怎样跟着变化

```text
扩大前：
node  = D
xpath = /html/body/section[1]/article[1]/a[1]

扩大后：
node  = B
xpath = /html/body/section[1]/article[1]
```

`allXPaths` 也重新针对 B 生成，因为下一次定位的目标已从链接换成商品块。底部 `lastElementXPath()` 读取这条新路径来画提示，但它会去掉索引，只显示简化形式；不能把提示文字直接当作完整 XPath。

当只剩 B 一项时，`handleElement()` 调用 `findRelated()`，本例可找到 C 作为候选。默认界面变成“已选中1个元素，同时发现1个同类元素”，提供选中全部和选中子元素等操作。要得到第 10 篇的两行内部字段预览，还需正式选中 B、C，再选择子元素。

#### 11.4 源码中哪些东西没有随扩大一起保存

这段方法没有递增 `global.step`，也没有保存“原来选的是 D”的历史对象。因此扩大两次不形成两条可逐步退回的操作历史；`revoke()` 根据选择步骤删除记录，不会把 B 自动还原成 D。

另外，原方法更新了父节点的 `bgColor`，**没有重新保存父节点原来的 `boxShadow`**，记录里仍可能是旧子节点的阴影值；不能把它讲成所有样式都完整备份了。

扩大也没有直接调用 `clearParameters()`。多节点时 `handleElement()` 会触发参数重建；单节点时只重新查找候选，因此若此前已有子元素预览，不能仅凭末尾 `selectedDescendents=false` 推断旧字段已被全部清除。重新选子元素才会清旧字段并按新块建立预览。这些是当前源码的实际边界。

### 12. revoke()：撤销最近一个选择步骤

#### 12.1 第 10 篇两块案例：撤销“选中全部”会剩下什么

从没有选择开始，按顺序操作：

| 操作 | `global.step` | 正式记录 `nodeList` | 候选 |
|---|---:|---|---|
| 右键选 B | 1 | `[B(step=1)]` | C |
| 点击选中全部 | 2 | `[B(step=1), C(step=2)]` | 无 |
| 点击选中子元素 | 2 | 同上；只改字段与预览 | 无 |

这时表格是 Java、Python 两行。点击菜单里的“撤销本次选择”，目标步骤为 2，方法把 C 删除、恢复它的样式、清参数，再对剩下的 B 重算候选。

```text
撤销前：两块已选 + 六列两行预览
撤销后：B 仍正式选中，C 重新成为候选
        outputParameters = []
        valTable = []
        selectedDescendents = false
        selectStatus = false
```

界面回到单元素菜单，显示“选中全部”“选中子元素”等入口，不会自动留下“Java 的六列一行表”。虽然最后点击的是“选中子元素”，它没有增加选择步骤，撤销仍针对此前的“选中全部”。

#### 12.2 一次选择加入多个节点，会一次撤销多个

在原两张卡片后临时增加第三张 Rust 卡片，结构与商品块一致。右键选 B 后，C 与 Rust 块都进入候选；再点一次“选中全部”：

```text
global.step = 2
nodeList = [
  B       (step=1),
  C       (step=2),
  Rust块  (step=2)
]
```

`selectAllElements()` 只增加一次 `step`，`readyToList()` 把这批候选都登记为这个步骤。撤销时从末尾连续删除：

```text
删 Rust块(step=2) → 删 C(step=2) → 遇到 B(step=1)，停止
```

所以一个撤销按钮可能移除多个选择节点；它不按“最后一行”或“最后一个字段”判断。

#### 12.3 逐句看 revoke() 源码

```js
revoke: function () {
  let tstep = global.step;
  global.step--;
  console.log(global.step, global.nodeList);
  while (tstep == global.nodeList[global.nodeList.length - 1]["step"]) {
    let node = global.nodeList.splice(global.nodeList.length - 1, 1)[0];
    node["node"].style.backgroundColor = node["bgColor"];
    node["node"].style.boxShadow = node["boxShadow"];
    if (global.NowNode == node["node"]) {
      global.style = node["bgColor"];
    }
    clearParameters();
  }
  handleElement();
}
```

| 语句 | 作用 | 三块例子中的值 |
|---|---|---|
| `tstep = global.step` | 保存本次要撤销的步骤编号 | 2 |
| `global.step--` | 退回一步的计数 | 变为 1，但删除条件仍比较 `tstep=2` |
| 比较最后一项的 `step` | 只删除末尾属于这一批的记录 | Rust、C 满足，B 不满足 |
| `splice(length-1,1)[0]` | 删除数组末尾一项，取出被删记录 | 先得到 Rust，再得到 C |
| 恢复背景与阴影 | 取消对应网页节点的选择样式 | 被删块退出正式选择 |
| 更新 `global.style` | 若被删节点也是 `NowNode`，同步它的原背景缓存 | 防止后续还原仍使用选中颜色 |
| `clearParameters()` | 清字段、参数节点记录、预览及采集标志 | 内部字段不能继续沿用旧块列表 |
| `handleElement()` | 根据剩余选择重算候选或多元素参数 | 只剩 B 时找回同类候选 |

方法在循环内清参数；如果删了两项，就会调用两次，第二次面对的已经是清空后的字段数组。

#### 12.4 撤销与取消选择的区别，以及空数组边界

“撤销本次选择”在 `page=0` 的多元素菜单中出现，按最近步骤删末尾一批；底部“取消选择”调用 `cancel()` → `clearEl()`，会清除所有选择并把步骤归零。取消并不保留 B 作为起点。

当前 `while` 条件没有先检查 `nodeList.length>0`。如果一次删除把列表删空，下一轮条件会访问不存在的最后一项，再取 `["step"]`，可能抛异常。上面的正常例子保留了 step=1 的 B，所以能遇到较早步骤并停止；不要据此认为源码已处理所有空数组情况。

删行、扩大选区也没有各自建立完整历史记录，因此 `revoke()` 是按选择步骤撤销的机制，不能当作任意操作的通用“撤销”。

### 13. deleteSingleLine()：按行号删除一条正式选择记录

#### 13.1 两块例子：删 Python 行后，表格会消失

从第 10 篇的六列两行预览开始，按 Python 行末尾的 ×：

```html
<!-- 第二行 i=2，因此实际绑定 index=1 -->
<td v-bind:index="i-1" v-on:mousedown="deleteSingleLine">×</td>
```

事件读出字符串 `"1"`，`splice()` 把它作为数组下标使用：

```text
原 nodeList = [B, C]
splice(1,1) 删除 C
新 nodeList = [B]
```

用户看到的结果按源码应是：Python 块的选择样式恢复，Java 块仍选中，**表头和数据预览一起消失**，回到需要选择采集内容的单元素状态。

这个结果容易讲错。如果只对所有列做 `splice(1,1)`，表格会保留 Java 一行；但源码实际删除的是 `nodeList`，并在只剩一个节点时清空所有参数与预览，没有直接逐列删除旧值。

#### 13.2 把完整分支展开

下面摘录原方法的核心逻辑，只省略计时和日志：

```js
deleteSingleLine: function (event) {
  let index = event.target.getAttribute("index");
  let tnode = global.nodeList.splice(index, 1)[0];
  tnode["node"].style.backgroundColor = tnode["bgColor"];
  tnode["node"].style.boxShadow = tnode["boxShadow"];

  if (global.nodeList.length > 1) {
    handleElement();
    if (this.selectedDescendents) {
      handleDescendents(this.mode);
    }
  } else {
    this.valTable = [];
    this.selectStatus = false;
    clearParameters();
  }
}
```

| 顺序 | 做什么 | B、C 删除 C 的例子 |
|---:|---|---|
| 1 | 从被按下的行尾格子读 `index` | `"1"` |
| 2 | 删除对应正式节点记录 | C 被取出，B 保留 |
| 3 | 恢复被删节点原背景、阴影 | Python 商品块不再维持正式选择样式 |
| 4 | 检查剩余数量是否大于 1 | 只剩 1，不进入重算分支 |
| 5 | 清表与采集标志 | `valTable=[]`、`selectStatus=false` |
| 6 | `clearParameters()` | 字段、参数节点记录被清，`selectedDescendents=false` |

两个分支都没有删除网页里的 `<article>`。删掉的是采集选择记录，网页商品卡片仍存在。

#### 13.3 三块删成两块：为什么需要重新生成字段和 num

仍用临时补充的 Rust 块，假设它的链接、图片、价格、数量分别为 Rust 入门、`/rust`、`rust.jpg`、￥77、3，没有促销。先选三个块，再用应选尽选生成：

| 行说明（不属于字段） | 链接文本 | 链接地址 | 图片地址 | 价格 | 数量 | 促销 |
|---|---|---|---|---|---|---|
| B，旧 num=0 | Java 入门 | `/java` | `java.jpg` | ￥99 | 1 | 空白 |
| C，旧 num=1 | Python 入门 | `/python` | `python.jpg` | ￥88 | 2 | 限时促销 |
| Rust，旧 num=2 | Rust 入门 | `/rust` | `rust.jpg` | ￥77 | 3 | 空白 |

删除 Python 行后：

```text
nodeList = [B, Rust块]
新编号：B → num=0，Rust块 → num=1
```

剩余数量为 2，调用 `handleElement()` 重测两块的关系，并触发参数生成。若当前 `selectedDescendents` 仍为 true，还调用 `handleDescendents(this.mode)`，按上次模式重新遍历剩下的块。

在子元素重算回调完成、按应选尽选建立新字段时，两个剩余块都没有 `strong`，促销列也不再生成：

| 链接文本 | 链接地址 | 图片地址 | 价格 | 数量 | 删除 |
|---|---|---|---|---|---|
| Java 入门 | `/java` | `java.jpg` | ￥99 | 1 | ×（index=0） |
| Rust 入门 | `/rust` | `rust.jpg` | ￥77 | 3 | ×（index=1） |

这次不仅少一行，还少了仅由被删块贡献的一列。新 `exampleValues.num` 也会按新的 `nodeList` 下标重新编号，避免 Rust 的值继续放在旧第 2 行而错位。

`this.mode` 是 `selectDescendents()` 上次保存的模式：0 应选尽选，1 相对首选块共同元素，2 所有块共同元素。删行时继续用它，避免用户原先选共同元素，重算却擅自换成应选尽选。

注意这里的参数生成依赖存储回调，方法没有 `await`。`handleElement()` 与 `handleDescendents()` 可能分别发起异步生成，不能把上面的目标结果解释成点击后所有数组立即同步完成；当前代码也没有用 Promise 显式串行等待两次生成。

#### 13.4 只剩一个或零个时，重新选择采集内容

| 删除前正式节点数量 | 删除后数量 | 分支 | 表格结果 |
|---:|---:|---|---|
| 3 | 2 | 重算关系，必要时重算子元素 | 等生成回调后显示新预览 |
| 2 | 1 | 清参数与预览 | 表格消失，剩下节点仍正式选中 |
| 1 | 0 | 清参数与预览 | 表格消失，显示默认空选择界面 |

如果两块删成一块，还想采集 Java 内部的五个字段，就再点击“选中子元素”；源码不会自动替用户完成这一步。这个分支没有调用 `clearEl()`，所以不负责把步骤归零或执行完整的候选清理。

#### 13.5 疑似 bug：无规律多元素预览的行号与选择节点不对应（留作学生修复任务）

> **待确认 / 待修复：** 这里可能是代码的 bug。以下说明记录当前源码行为，不把它当作合理的删除规则。本讲先保留问题，后续由同学复现、确定交互语义并修复。

第 5 节的无规律例子是：

```text
nodeList = [D(Java链接), H(Python图片)]
valTable = [["Java 入门"], ["/java"], ["python.jpg"]]
```

预览只有一行，行尾绑定 `index=0`。按 × 时方法仍然执行 `nodeList.splice(0,1)`，实际只删 D；H 保留，但因为只剩一项，三个字段和预览都被清空。它并不是一次把这一行涉及的链接和图片都删掉。

所以行号与块号一一对应，主要适用于按块生成多行预览的情况；无规律多节点把不同来源合在一行时，当前方法并没有另做来源映射。

**学生修复任务：**

1. 复现：选中 Java 链接 D 和 Python 图片 H，确认进入 `option=100` 的无规律多元素界面；等待三列一行预览生成，点击行尾 ×，观察剩余节点和预览变化。
2. 定位：对照 `generateMultiParameters()` 中的 `generateValTable(false)`、模板的 `index=i-1` 和 `deleteSingleLine()` 中的 `nodeList.splice(index,1)`，说明为什么预览行号不能直接作为来源节点下标。
3. 设计并实现修复：先明确这种合并预览是否应该支持删行。如果支持，明确删除这一行应处理哪些来源节点；如果不支持，可以在该模式下隐藏行删除入口，保留字段删除。说明选择该方案的理由。
4. 验证：无规律多元素模式的行为符合所选方案，同时有规律多块预览仍能删除指定块；检查剩余一个节点、清空选择，以及一个链接贡献文本和地址两列的情况。

#### 13.6 删除行怎样影响后续循环列表

原方法注释说删行后按照固定元素列表采集，但 `deleteSingleLine()` 没有直接赋值 `loopType`。后续采集消息里的 `detectAllSelected()` 会比较共同 XPath 的匹配数量与正式已选数量。

例如共同路径仍能匹配 B、C、Rust 三个块，用户删 C 后只正式保留 B、Rust，检测结果不再是全选，消息函数便可能使用固定列表。这与“从网页 DOM 删除 C”不同：C 仍能被原 XPath 匹配，所以后续必须尊重用户缩小后的正式名单。

### 14. removeField()：删一个采集字段，并清相关参数节点标记

**删除列时，只要还剩其他字段，`nodeList` 是不变的；删掉的是这一列的采集字段信息，后续给流程图发送采集消息时就不再包含这一列。** 例如删除价格列，Java、Python 两个商品块仍然选中，只是不再把价格字段送给流程图。

从需要完成的工作来看，可以分成两步：

1. **第一步：清空这一列对应节点的标记样式。** 根据被删字段的 `unique_index`，找到 `outputParameterNodes` 中对应的节点，清空它们的背景色和阴影，并移除这些参数节点记录。例如价格列对应 Java 的 F 和 Python 的 I，要把两个价格节点的标记都清掉。
2. **第二步：删除这一列的信息。** 从 `outputParameters` 删除字段对象，从 `valTable` 删除对应的整列预览值。这样操作台不再显示价格列，后续确认采集时，消息读取的字段列表也不再包含价格；B、C 两条正式选择记录仍留在 `nodeList` 中。

这里按职责分成两步；实际源码先取出并删除字段，再删除预览列、清理对应节点样式，具体执行顺序见 14.2。点击删列本身不会立即发送采集消息。删除最后一个字段则会调用 `clearEl()`，连 `nodeList` 一起清空，这个例外见 14.5。

#### 14.1 先看删价格列，行数和正式块数都不变

在 B、C 的六列两行表里，按“价格”表头旁边的 ×。列下标是 3：

```text
删除前：
outputParameters = [链接文本, 链接地址, 图片地址, 价格, 数量, 促销]
valTable[3]      = ["￥99", "￥88"]
nodeList        = [B,C]

删除后：
outputParameters = [链接文本, 链接地址, 图片地址, 数量, 促销]
valTable         = [
  ["Java 入门", "Python 入门"],
  ["/java", "/python"],
  ["java.jpg", "python.jpg"],
  ["1", "2"],
  [" ", "限时促销"]
]
nodeList         = [B,C]  // 还有字段时，两块继续正式选中
```

页面重新画成：

| 链接文本 × | 链接地址 × | 图片地址 × | 数量 × | 促销 × | 删除 |
|---|---|---|---|---|---|
| Java 入门 | `/java` | `java.jpg` | 1 | 空白 | × |
| Python 入门 | `/python` | `python.jpg` | 2 | 限时促销 | × |

网页上的两个 `p` 仍显示价格，只是不再作为本次采集字段。新表头循环使数量的按钮下标由 4 变成 3、促销由 5 变成 4；字段自己的 `name` 和 `unique_index` 不会因此重新编号。

#### 14.2 按执行顺序看源码

```js
removeField: function (event) {
  let index = event.target.getAttribute("index");
  let tParameter = global.outputParameters.splice(index, 1)[0];
  if (global.outputParameters.length == 0) {
    this.valTable = [];
    clearEl();
  } else {
    console.log("remove:", tParameter, global);
    this.valTable.splice(index, 1);
    for (let i = global.outputParameterNodes.length - 1; i >= 0; i--) {
      let node = global.outputParameterNodes[i];
      if (node["unique_index"] == tParameter["unique_index"]) {
        node["node"].style.backgroundColor = "";
        node["node"].style.boxShadow = "";
        global.outputParameterNodes.splice(i, 1);
      }
    }
  }
}
```

| 顺序 | 改哪份数据 | 删除价格的效果 |
|---:|---|---|
| 1 | 从表头 × 读列号 | 得到 `"3"` |
| 2 | `outputParameters.splice(3,1)` | 删除价格字段，取出其对象保存为 `tParameter` |
| 3 | 检查是否还剩字段 | 还剩五个，进入 `else` |
| 4 | `valTable.splice(3,1)` | 删除整个价格列数组，两个价格值一同退出预览 |
| 5 | 用 `unique_index` 找参数节点记录 | 找到两块内对应价格的节点 |
| 6 | 清样式并删除匹配记录 | 价格节点不再维持该字段的参数标记 |

为什么要同时删字段和列数组？只删 `outputParameters`，表头变成五个，但 `valTable` 还保留旧价格列。此时数量表头下可能读到 `valTable[3]` 的价格值，字段名和内容便错位。两处按同一个下标 `splice()` 才能保持对应。

这里不需要调用 `generateValTable()` 重建全部值：删除字段后其他字段的示例值没有变，直接删除相应列就够了。

#### 14.3 unique_index 怎样把一列连到两块里的节点

第 10 篇的多块子元素模式按块内路径识别字段。价格位置 `/p[1]` 可以作为字段和参数节点记录共用的标识，缩写为：

```js
// 只列出本节要比较的属性。
tParameter = { name: "价格", unique_index: "/p[1]" };

// 实际数组还包括块根和促销节点等记录，这里只展示部分。
outputParameterNodes = [
  { node: B, unique_index: "" },
  { node: F, unique_index: "/p[1]" },  // Java 价格
  { node: C, unique_index: "" },
  { node: I, unique_index: "/p[1]" }   // Python 价格
];
```

删价格时会匹配 F、I 两条记录。删列需要同时取消两块里对应节点的参数标记，因为“一列”代表一个结构位置，可以对应多个网页节点。

循环从末尾向前：先删 I 的记录，再继续向前找到 F。如果从前向后遍历，`splice()` 会让后面的元素向前移动；相邻两个待删记录时，循环下标再递增，就可能跳过一项。倒序删除不会让尚未检查的前面部分改变下标。

原方法写的是 `style.backgroundColor=""` 和 `style.boxShadow=""`，清除内联值，之后可由样式表决定外观；它没有从记录中恢复完整的原背景和阴影。因此应说“清标记样式”，不能把它等同于删行时的原值还原。

#### 14.4 链接两列共享标识，还要看参数节点记录是否存在

链接文本和链接地址来自同一个 `a`，字段可以共享 `unique_index="/a[1]"`：

```text
字段：链接文本 → /a[1]
字段：链接地址 → /a[1]
```

本篇 HTML 把文字包在 `span` 里，D、G 链接自身没有直接文本节点。应选尽选分支只在 `ndText != "" || nd == tnode` 时登记 `outputParameterNodes`，因此本例虽然有链接字段，**并没有 D、G 对应的链接参数节点记录**。删链接地址会减少一列，但循环不会凭字段路径自动找到网页链接去清样式。

为了观察共享标识的效果，把两个链接改成下面这种带直接文本的变体，其他结构不变：

```html
<a href="/java">Java <span>入门</span></a>
<a href="/python">Python <span>入门</span></a>
```

这时 D、G 自身分别有直接文本 Java、Python，会登记 `unique_index="/a[1]"` 的参数节点记录。链接整体的文字仍是 Java 入门、Python 入门。只删“链接地址”后，“链接文本”字段和文字预览保留，但循环会清除 D、G 上所有匹配 `/a[1]` 的参数节点记录和样式。

当前方法没有检查另一个字段是否仍引用同一标识，所以不能解释为“删除哪列，就只取消哪列独占的节点高亮”。字段是否生成、参数节点是否登记，以及一个节点是否服务多个字段，需要分别判断。

#### 14.5 删掉最后一个字段：整个选择也会清掉

当只剩一个字段时再按它的 ×，执行的是：

```js
this.valTable = [];
clearEl();
```

`clearEl()` 恢复正式选择节点的样式，清候选、参数、正式节点列表，把 `step` 归零、`option` 和 `page` 归零。因此最终既没有字段表，也没有 B、C 的正式选择，回到空选择界面。

| 操作 | 正式节点 | 字段与预览 | 主要界面结果 |
|---|---|---|---|
| 扩大 `[D]` | 换成 `[B]`，数量不变 | 是否重建取决于 `handleElement()` 分支 | 类型、路径、候选与菜单变化 |
| 撤销 `[B(step1),C(step2)]` | 删 C，保留 B | 清参数；单节点分支不自动生成表 | 回单元素菜单 |
| 删除两块表中的 Python 行 | 删 C，保留 B | 剩一块时清全部字段和预览 | 回单元素菜单 |
| 删除价格列，还有其他字段 | B、C 保留 | 删除价格字段及整列值 | 两行不变，少一列 |
| 删除最后一列 | 所有正式节点清空 | 全清 | 回空选择界面 |

这张对照表也说明，虽然行尾 × 与表头 × 都是删除图标，它们操作的数据对象和触发的分支完全不同。

## 第四部分：输入、点击、下拉框与循环操作

### 15. 文字输入分成“打开输入界面”和“确认发送”

```js
setInput: function (batch = false) {
  this.batch = batch;
  this.page = 1;
  this.$nextTick(function () {
    document.getElementById("WTextBox").focus();
  });
},
getInput: function () {
  global.nodeList[0]["node"].focus();
  input(this.text, this.batch);
  this.text = "";
  clearEl();
}
```

1. 选择网页中的 INPUT，调用 `setInput(false)`。
2. 改 `page` 后，Vue 还没有立刻把输入子界面更新到 DOM，所以聚焦操作放进 `$nextTick()`。
3. 用户在操作台输入“电脑”，`v-model` 更新的是 `this.text`，不是网页 INPUT 的内容。
4. 点确定：先给网页节点焦点，调用 `input("电脑",false)` 发消息。
5. 清操作台文字，清选择状态。普通输入消息与批量输入消息的差别由第 14 篇消息交互解释。
6. 点取消输入则只把 `page` 改为 `0`；`cancelInput()` 没有发消息，也没有清选择。

### 16. 点击与移动：操作台发送命令，Electron 做实际动作

| 方法 | 发送函数 | 后续动作 | `lastAction` |
|---|---|---|---|
| `clickElement()` | `sendSingleClick()` | 当前节点 focus，等待 500ms，清选择 | `clickElement` |
| `mouseMove()` | `sendMouseMove()` | 立即清选择 | `mouseMove` |
| `loopMouseMove()` | `sendLoopMouseMove()` | 立即清选择 | `loopMouseMove` |
| `loopClickSingleElement()` | `sendLoopClickSingle(name)` | focus，等待 500ms，清选择 | `clickElementWithLoop` |
| `loopClickEveryElement()` | `sendLoopClickEvery()` | focus，等待 500ms，清选择 | `clickEveryElementWithLoop` |

这些方法最后都设 `nextPage=0`。以 `clickElement()` 为例：先发送记录 → focus 当前网页节点 → 等待 → 清状态。源码里直接 `node.click()` 的语句已注释；500ms 是经验等待，不是 Electron 的成功回执。

循环点击单个元素会先用 `tname()` 判断是不是“下一页元素”。如果从设置翻页界面传入 `"nextPageFromIndexPage"`，会覆盖这个名称；消息函数据此改为 `loopClickNextPage`。

### 17. 下拉框切换的三层方法

| 方法 | 先做什么 | 示例 |
|---|---|---|
| `changeSelect()` | `page=2`，默认模式 0，预填下一个选项文字 | 当前 Java，下个 Python，预填 Python |
| `handleSelectChange()` | 随模式变化重填 `optionValue` | 模式 1 填当前索引；模式 2 填当前 value；模式 3 填当前文本 |
| `sendChangeSelect()` | 先 `sendChangeOption()`，再尝试在当前 DOM 修改选项，最后清选择 | 按 value 切换到 `py` |

`optionMode`：0 下一项；1 按索引；2 按值；3 按文字。按文字时，源码遍历 options，找到 `option.text===optionValue` 后把 SELECT 的 value 改成该 option 的 value。

按步骤看一个例子：选择下拉框 → 打开切换界面 → 改模式为 2 → 输入 `py` → 发出 `{optionMode:2,optionValue:"py"}` → 本地 `.value="py"` → 清选择。源码没有在这段显式派发 change 事件。

还有两个边界：初始化“下一项”时直接访问 `selectedIndex+1`，最后一项可能没有下一项；真正发送后的本地修改放在 try/catch 中，但初始化和模式变化处没有同样的保护。

### 18. 翻页提示怎样接续上一次采集

1. 确认采集后设 `nextPage=1`，默认空选择界面显示设置翻页入口。
2. `setNextPage()` 改 `page=3`，用户按提示选择下一页按钮。
3. `confirmNextPage()` 调用 `loopClickSingleElement("nextPageFromIndexPage")`。
4. 消息函数生成 `loopClickNextPage`，还携带之前的 `lastAction`。
5. 流程图据 `lastAction` 判断前一次采集是否已有循环，再安排翻页循环的位置。
6. `cancelNextPage()` 调用 `cancel()` 清选择，然后恢复 `nextPage=1`，让用户还可以重新指定。

## 第五部分：辅助方法和生命周期也要知道它们的边界

### 19. 显示与状态辅助函数

| 函数 | 基本逻辑与例子 |
|---|---|
| `initial()` | 清子元素、采集状态和共同路径；模板在无选择时调用它以重置状态 |
| `tname()` | 按直接文本是否含“下一页”、标签和 INPUT type，返回下一页元素、链接、图片、按钮、文本框、选择框等 |
| `getSelectedInnerText()` | 取首个已选节点的 innerText，trim 后截到前 10 字，超长加省略号 |
| `existDescendents()` | 已选非空、首个节点有孩子、尚未选子元素时为 true，用于显示按钮 |
| `numOfReady()` | 候选数量；例如 D 已选、G 候选时返回 1 |
| `numOfList()` | 正式已选数量，和候选数量分开显示 |
| `lastElementXPath()` | 读最后一条已选路径，最多保留末尾五段，去掉索引后加 Path 前缀；只用于提示 |
| `setWidth(width)` | jQuery 修改 `.tooltips` 宽度，返回空字符串，模板可调用它产生布局副作用 |
| `cancel()` | 调用 `clearEl()`，统一清选择与参数 |
| `specialSelect()` | 方法体目前只有注释，不会启用一种新的选择算法 |
| `onResize()` | 把 `window.outerHeight` 写入 `winHeight`，模板据此限制内容高度 |

`tname()` 判断文本框的条件写成 `inputType != "checkbox" || inputType != "ratio"`。这个或条件始终成立，而且标准类型是 radio；所以不能据返回名称断言它正确区分了所有复选框、单选框。下一页识别也只是检测直接文本里有没有“下一页”，不是完整的翻页识别算法。

### 20. mounted、watch 与 filters

1. `mounted()` 在 `$nextTick()` 内注册窗口 resize 监听。
2. 如果当前内容脚本在 iframe 内，设置 `global.iframe=true`，以后字段和消息携带这个标志。
3. 遍历当前文档的 iframe，打印路径和尺寸；高度或宽度小于 600 时，尝试调整样式和 iframe 属性。
4. `beforeDestroy()` 移除 resize 监听；源码是 Vue2 生命周期名。
5. `watch.nowPath` 只打印新 XPath，没有自动重新匹配或生成字段。
6. `filters.toEng` 把“链接”等名称翻成英文，服务英文模板；它不翻译字段值，也不参与采集。

## 第六部分：把一次完整操作串起来

### 21. 从两个商品块到采集消息

按这条执行链逐个找函数，不跳过中间状态：

```text
右键选择 B → 找到候选 C → 选择全部
                    │
                    ▼
             selectAll() / selectAllElements()
                    │
                    ▼
点击选中子元素 → selectDescendents(e,0)
                    │
                    ▼
      handleDescendents(0) 的异步回调
                    │
                    ▼
 outputParameters → generateValTable() → valTable
                    │
                    ▼
      模板显示字段名、两行值与删除按钮
                    │
                    ▼
点击采集数据 → confirmCollectMultiAndDescendents()
                    │
                    ▼
          collectMultiWithPattern() → WebSocket
                    │
                    ▼
     clearEl() → nextPage=1 → 提示继续设置翻页
```

操作台主要协调已有算法与通信函数：它决定何时调用生成、何时允许确认、何时清状态。参数如何构造在第 8 篇；接下来先在第 13 篇补 WebSocket 通信背景，再在第 14 篇逐条解释消息里装了什么、哪些消息会回到操作台。

### 22. 手工练习

1. 选中 Java 的数量 INPUT 后，`setInput(false)` 把 `page` 改成几？界面上还会不会显示字段表和扩大选区？输入框中的 `v-model` 修改的是哪份数据？
2. 两块应选尽选得到六列两行。Python 的促销格子对应 `i`、`j` 各是多少，实际读取 `valTable` 的哪两个下标？为什么 Java 促销为空时不会把 Python 促销移到第一行？
3. `nodeList=[D,G]` 时扩大选区，最终是哪两个节点？数组长度、末尾路径和 `step` 分别怎样变化？
4. `[B(step=1),C(step=2),Rust块(step=2)]` 撤销一次，会删除几条记录？如果此前选过子元素，字段表还会保留吗？
5. 在 B、C 的两行表中删除 Python 行，为什么结果不是 Java 的一行表？换成三块删成两块时，哪些字段和 `exampleValues.num` 需要重算？
6. 删除价格列要修改哪两个数组？如果只改字段数组，不改 `valTable`，数量表头下面会显示什么？删除最后一个字段又为什么会连选择一起清掉？
7. 原 HTML 的链接文字全部包在 span 中，删链接地址时为何不一定清链接节点标记？换成有直接文本的链接变体后，共享 `unique_index` 又会产生什么效果？
8. `getText()` 返回后为什么字段可能还没生成？为什么确认采集要先发消息，再 `clearEl()`？
9. `nextPage=1` 与 `page=3` 分别控制什么？翻页界面选中两个节点时，模板会画哪些提示和入口？

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[11.Vue3详解：读懂 toolkit.vue 前的模板、状态与构建背景](/easyspider/chapter-11) ｜ 下一篇：[13.WebSocket：三进程实时通信的桥梁](/easyspider/chapter-13)
