# 05.元素待选与选中：先看鼠标做了什么，再看代码怎么记住它

> 这一篇，我们假装自己在写一个“网页元素选择器”。
>
> 页面上有三个商品标题 A、B、C。用户想告诉软件：“我准备采集这些标题。”
>
> 我们先用这个小场景讲清楚过程，再把它对应到 EasySpider 的源码。
>
> 学完后，你应该能解释：**鼠标指着谁、软件记住了谁、软件还推荐了谁，这三件事有什么区别。**

---

## 0. 先认识入口：`main.js` 负责把工具接到网页上

这一篇后面会不断看到 `main.js` 和 `global.js`。先把两者的分工说清楚：

```text
main.js    装配工具、监听鼠标和键盘、把动作转交出去
global.js  保存状态、添加/清空元素、计算 XPath 和同类候选
toolkit.vue 操作台的界面，提供“选中全部”“撤销”等按钮
```

`manifest.json` 的 content script 配置会在网页加载到 `document_end` 后运行 `main.js`。所以它是本次交互的入口，不是“所有算法都写在这里”。

### 0.1 `main.js` 启动时做了什么

```text
① import Vue、jQuery、global.js 和 toolkit.vue
② 创建 wrapperDiv、wrapperTdiv、wrapperToolkit 三个工具元素
③ 把工具元素插进网页 body
④ 监听 mousemove：找出鼠标下的元素并显示悬停提示
⑤ 监听 mousedown：调用 global.js 的 addEl() 完成选择
⑥ 监听键盘：F2 选择、F8 清空、F9 操作当前元素
⑦ 挂载 Vue 操作台，并在网页改写 body 时尝试把它恢复
```

把三条输入线分开：

```text
mousemove  = 观察鼠标在哪里
mousedown  = 把当前目标确认下来
keydown    = 鼠标操作不方便时的快捷入口
```

`main.js` 还负责拖拽和缩放操作台、屏蔽工具界面的误选，以及定时检查工具界面是否被网页删除。这些是“让工具活在网页里”的配套工作；本篇主线只追踪鼠标如何进入 `global.js`。

---

## 1. 先看一次操作，不急着看函数

假设网页上有这样一个列表：

```html
<ul id="goods">
  <li><a href="/p1">商品 A</a></li>
  <li><a href="/p2">商品 B</a></li>
  <li><a href="/p3">商品 C</a></li>
</ul>
```

我们想采集三个商品标题，先观察下面几步。

| 用户的动作 | 界面提示 | 软件需要记住什么 |
| --- | --- | --- |
| 鼠标移到 A 上 | A 出现悬停提示色 | 鼠标现在指着 A |
| 鼠标移到 B 上 | A 的悬停提示撤掉，B 出现提示色 | 鼠标现在指着 B，刚才指着 A |
| 回到 A，选中 A | A 变成选中色 | A 已加入选择名单 |
| 鼠标再移到 B | A 保持选中色，B 出现悬停提示 | 已选 A；当前指着 B |
| 软件找到同类标题 | B、C 出现候选提示 | B、C 可以一起选，但还没正式加入 |
| 点“选中全部” | A、B、C 都成为已选元素 | 名单包含 A、B、C |

这里描述的是主要交互效果。项目中第一次鼠标命中的高亮有一个初始化细节，后面 §10 会说明。

先暂停，问学生一句：

> **鼠标移到 B 时，A 为什么不能也被取消选中？**

因为“指着一个元素”和“已经选中了一个元素”是两件事。

鼠标位置一直在变，已经做出的选择应该保留，直到用户主动撤销或清空。

这就是我们接下来要用变量和数组表达的事情。

---

## 2. 三种提示：当前指着、同类候选、已经选中

原稿里“待选”容易有两种理解，这里先把它们分开。

| 本篇用语 | 意思 | EasySpider 中主要的视觉提示 | 记录在哪里 |
| --- | --- | --- | --- |
| **当前指着**（悬停） | 鼠标此刻落在这个元素上 | 浅蓝紫背景 | 当前元素变量 |
| **同类候选**（预备选择） | 软件建议你还可以选这些元素 | 蓝色阴影 | `readyList` |
| **已经选中** | 用户已确认加入名单 | 青色背景 | `nodeList` |

源码中的颜色：

```js
// global.js 中 global 对象的字段，节选
selectedColor: "rgba(151,255,255, 0.6)",
defaultbgColor: 'rgba(221,221,255,0.8)',
boxShadowColor: "blue 0px 0px 5px",
```

这三个概念可以重叠：鼠标也可以指着一个已经选中的元素。

这时它应该继续保持青色，而不是被悬停色盖掉。

💡 **颜色是显示结果，数组中的记录才是程序判断是否选中的依据。**

程序不会通过“这个元素看起来是青色”来判断是否选中，因为网页自己也可能用了青色背景。

---

## 3. 软件要有两种记忆：当前位置和选择名单

暂时不用源码里的缩写，先用容易读的名字。

```js
let current = null;        // 现在指着谁
let previous = null;       // 刚才指着谁
const selected = [];      // 已经选中了哪些元素
```

### 3.1 为什么需要 `previous`

鼠标移动事件告诉你这次的位置。

但你还要撤掉**上一次**的悬停色，所以需要自己记住上一次的元素。

```text
鼠标从 A 移到 B：
  current  = B
  previous = A

这次处理：
  撤掉 A 的临时提示
  给 B 加上临时提示

处理结束：
  previous = B
  留给下一次鼠标移动使用
```

`previous` 不是“最早指过的元素”，而是**上一轮处理后保留下来的元素**。

### 3.2 为什么 `selected` 要用数组

当前鼠标通常只指着一个元素，但用户可以选中很多个。

```text
current  = C
selected = [A, B]
```

这表示：

> 鼠标现在指着 C；A、B 已经选过。

两个状态互不冲突。

### 3.3 对照 EasySpider 的真实变量

| 教学名字 | 源码名字 | 阅读时这样理解 |
| --- | --- | --- |
| `current` | `global.oe` | 这次鼠标命中的元素 |
| `previous` | `global.xnode` | 上一次保留的元素，用来撤掉旧提示 |
| 当前操作目标 | `global.NowNode` | 接下来 `addEl()` 等操作默认使用的元素 |
| `selected` | `global.nodeList` | 已选记录数组 |
| 同类候选 | `global.readyList` | 同类候选记录数组 |

🔴 **`NowNode` 的名字不能按“已经选中”理解。**

在 `main.js` 的鼠标移动处理中，有：

```js
global.NowNode = global.oe;
```

所以鼠标移到 B，`NowNode` 就可能是 B，即使 B 根本没加入已选名单。

判断“已经选中”，要查 `nodeList`。

---

## 4. 第一步：鼠标坐标怎么变成网页元素

用户给我们的输入是鼠标位置；程序要得到的是一个 DOM 元素。

### 4.1 先认识浏览器提供的查询方法

```js
const element = document.elementFromPoint(300, 200);
```

意思是：

> 请告诉我，当前网页可视区域中，坐标 `(300, 200)` 这个点命中了哪个元素。

坐标从浏览器页面可视区域的左上角算，不是从整个电脑屏幕左上角算，也不是页面滚动前的文档顶端。

最小示意：

```js
document.addEventListener('mousemove', function (e) {
  const current = document.elementFromPoint(e.clientX, e.clientY);
  console.log(current);
});
```

`mousemove` 每次发生时，都用这次坐标问浏览器“下面是谁”。

### 4.2 回到真实代码

`main.js` 使用的是：

```js
global.oe = document.elementFromPoint(event.x, event.y);
global.NowNode = global.oe;
```

这里鼠标事件的 `x/y` 对应可视区域坐标，读代码时可以和前面的 `clientX/clientY` 对照。

### 4.3 为什么有时命中标题，有时命中外层盒子

假设结构是：

```text
li（整行商品）
  └─ a（标题链接）
       └─ span（标题文字）
```

鼠标落在文字上时可能命中 `span`；落在标题旁的空白处，可能命中 `li`。

如果上面盖着一个可接收鼠标的浮层，也可能命中浮层。

因此正确理解是：

> `elementFromPoint` **返回该点最上层、能参与命中测试的元素，不保证是面积最小的元素，也不会自动找“商品标题”**。

浏览器只回答“坐标下面是谁”，业务含义还需要软件或用户判断。方法的坐标、遮挡和 iframe 行为见 [MDN 说明](https://developer.mozilla.org/en-US/docs/Web/API/Document/elementFromPoint)。

💡 源码用这个方法查询元素，但调用它的 `mousemove` 监听器仍要收到事件；不能据此声称整个拾取过程完全不受网页事件传播影响。

---

## 5. 第二步：悬停色怎样跟着鼠标走

这一部分先只考虑 A、B 都没选中的情况。

### 5.1 用三句话讲算法

```text
① 找到鼠标现在指着谁。
② 如果换了元素，撤掉上一个的提示，给当前的加上提示。
③ 记住当前元素，等下一次移动时使用。
```

鼠标在 A 内部移动时，命中的还是 A，就不需要反复“清色、上色”。

判断是否换了元素，只需比较两个 DOM 引用：

```js
if (previous === current) return;
```

### 5.2 教学版代码：先把过程写清楚

下面是**教学版**，不是 EasySpider 源码的逐字复制。我们额外保存每个元素的原背景色，让还原过程容易看懂。

```js
let previous = null;
let previousBackground = '';

function showHover(current) {
  if (!current || current === previous) return;

  // ① 撤掉旧提示
  if (previous) {
    previous.style.backgroundColor = previousBackground;
  }

  // ② 先保存当前元素的旧颜色，再加新提示
  previousBackground = current.style.backgroundColor;
  current.style.backgroundColor = 'rgba(221,221,255,0.8)';

  // ③ 交接：当前元素成为下一轮的“上一个”
  previous = current;
}
```

注意顺序：

> **先保存旧值，再覆盖新值。** 否则保存到的就是提示色，之后无法还原。

### 5.3 走一遍 A → B → C

| 这次鼠标位置 | 处理前的 `previous` | 撤掉谁的提示 | 给谁加提示 | 处理后的 `previous` |
| --- | --- | --- | --- | --- |
| A | `null` | 无 | A | A |
| B | A | A | B | B |
| C | B | B | C | C |

把这一张表看懂，再读真实代码中的 `xnode = oe` 就不会绕。

---

## 6. 加上选择名单：为什么选中 A 后，移走鼠标它还保持青色

现在 A 已经加入 `nodeList`，鼠标准备从 A 移到 B。

如果仍执行上一节的“撤掉 A 的提示”，就会把选中色也擦掉。

所以要多问两句话：

```text
动上一个元素之前：它已经选中了吗？
动当前元素之前：它已经选中了吗？
```

### 6.1 先理解“查名单”

EasySpider 的名单不是 `[A, B]`，而是：

```js
[
  { node: A, /* 其他信息 */ },
  { node: B, /* 其他信息 */ }
]
```

`node` 字段指向实际 DOM 元素。

判断 A 在不在名单里，就是逐条看记录：

```js
// 教学版写法
function isSelected(element) {
  return global.nodeList.some(record => record.node === element);
}
```

`some()` 的意思是：“只要有一条满足条件，就返回 true。”

真实源码用 `for` 循环做同样的检查：

```js
let exist = 0;
for (let o of global.nodeList) {
    if (o["node"] == global.oe) {
        exist = 1;
        break;
    }
}
```

翻译成中文：

> 当前鼠标命中的这个对象，是否就是名单里某条记录指向的那个对象？找到就标记为 1，并停止查找。

不是比较文字。两个元素即使都显示“商品 A”，也不一定是同一个 DOM 对象。

### 6.2 两个标记各管一边

源码用了两个名字很像的变量：

| 标记 | 检查谁 | 为 1 时的处理 |
| --- | --- | --- |
| `exist` | 当前的 `oe` | 不覆盖当前元素的选中色 |
| `exist2` | 上一个的 `xnode` | 不擦掉上一个元素的选中色 |

只查当前元素不够，因为移开时也可能擦掉已经选中的元素。

### 6.3 真实颜色分支（节选）

前面已经查好两个标记，接下来：

```js
if (global.xnode != global.oe) {
    if (exist2 == 0) {
        try {
            global.xnode.style.backgroundColor = global.style;
        } catch {
            global.xnode.style.backgroundColor = "";
        }
    }

    if (exist == 1) {
        // 当前元素已选中，保持它的颜色
    } else {
        try {
            global.oe.style.backgroundColor = global.defaultbgColor;
        } catch {
        }
    }
    global.xnode = global.oe;
    global.div.style.display = "none";
}
```

先只抓主线：

```text
换元素了吗？
  → 上一个没选中：撤掉它的临时色
  → 当前没选中：加上临时色
  → 更新 xnode，供下一轮使用
```

`try/catch` 是错误处理，不改变这条主线。背景还原值的限制放在 §10 说明。

### 6.4 用四种情况检查理解

| 上一个元素 | 当前元素 | 上一个怎么处理 | 当前怎么处理 |
| --- | --- | --- | --- |
| 没选中 | 没选中 | 撤掉临时色 | 加临时色 |
| 已选中 | 没选中 | 保持选中色 | 加临时色 |
| 没选中 | 已选中 | 撤掉临时色 | 保持选中色 |
| 已选中 | 已选中 | 保持选中色 | 保持选中色 |

课堂可以只问第二行：**A 已选中，鼠标移到未选中的 B，会发生什么？**

能回答“A 保持青色，B 出现悬停色”，就理解了两个标记的作用。

---

## 7. 第三步：一次“选中”到底做了什么

### 7.1 用户动作先变成函数调用

`main.js` 中有：

```js
document.oncontextmenu = () => false;
document.addEventListener("mousedown", addEl);
```

第一行屏蔽右键菜单；第二行在鼠标按下时调用 `addEl`。

教程通常让用户右键选择，但这里的 `mousedown` 没有按鼠标按钮过滤，所以左键也会进入这条逻辑。

另一条入口是 F2：键盘处理代码会调用 `addEl()`，使用当前操作目标。

> 先区分两个动作：“加入选择名单”由 `addEl` 处理；“让网页真的执行点击”是另一件事。

F9 的代码会对 `NowNode` 调用 `focus()` 和 `click()`，意图是操作网页元素。它和 F2 的用途不同。

### 7.2 先讲普通分支：这次只加一个元素

暂时假设当前元素既没选过，也不在同类候选中。

```text
确认目标
  → 检查有没有选过
  → 建立一条选择记录
  → 加进 nodeList
  → 上选中色
  → 更新相关提示和候选
```

真实函数的参数：

```js
export function addEl(e, node = global.NowNode, handle = true) {
    // 函数体见下面各段
}
```

| 参数 | 用途 |
| --- | --- |
| `e` | 传入的事件 |
| `node` | 要选择的元素；不传就用 `NowNode` |
| `handle` | 选择后是否调用 `handleElement()` 更新相关状态 |

### 7.3 名单里存的是一张“元素记录卡”

普通添加分支会 `push` 一条记录，下面保留关键字段，简化阴影表达式：

```js
global.nodeList.push({
    node: global.NowNode,
    step: global.step,
    bgColor: style,
    // boxShadow 字段的源码表达式见 §10
    xpath: readXPath(global.NowNode, 1),
    allXPaths: getElementXPaths(global.NowNode)
});
global.NowNode.style.backgroundColor = global.selectedColor;
```

可以把记录卡读成：

```text
node        现在这个页面里的元素对象
bgColor     取消时准备写回的背景值
boxShadow   取消时准备写回的阴影值
xpath       以后重新定位这个元素的路径
allXPaths   其他候选定位路径
step        这条记录属于哪一次选择操作
```

`node` 和 XPath 各自解决不同的问题：

> **当前页面修改颜色，用 DOM 引用；以后重新定位，用 XPath 等路径信息。**

刷新页面后，旧 DOM 引用不能代表新页面里的元素。XPath 可以作为定位信息存入任务相关数据，但仍可能受网页结构变化影响，见第 4 篇。

### 7.4 为什么不会每按一次就重复加一条

添加之前，源码会遍历 `nodeList` 检查当前 `oe` 是否已经在里面；已经存在时跳过添加分支。

常规鼠标选择中，`oe` 和本次目标通常一致，因此可以防止重复加入同一个元素。

🔬 函数也允许显式传 `node`，但检查仍使用 `oe`。这是源码实现上的细节，不能把这个去重判断泛化成“任何调用方式都按传入目标正确去重”。

### 7.5 `step` 是选择批次，不是流程图节点编号

进入新的添加分支时，源码执行：

```js
global.step++;
```

例如：

```text
单独选 A：             A 的 step = 1
下一次把候选 B、C 全选： B、C 的 step = 2
```

一次操作可以加多个元素，它们可以有相同的 `step`。

它的重要用途是**撤销最近一批选择**。不要把它理解成“采集流程图的第几个节点”。在网页上选中了元素，也不代表已经向流程图添加了对应动作。

---

## 8. 第四步：软件推荐的同类元素，为什么还要放另一个数组

选中 A 后，软件可能发现 B、C 看起来和 A 属于同一类。

但这是软件的建议，用户尚未确认。

所以我们希望这样记：

```text
nodeList  = [A 的记录]           用户已确认
readyList = [B 的记录, C 的记录] 软件推荐，等待确认
```

### 8.1 选中之后，谁负责更新候选

`addEl` 中有：

```js
if (handle) {
    handleElement();
}
```

`handleElement()` 的真实主干是：

```js
export function handleElement() {
    clearReady();
    if (global.nodeList.length > 1) {
        global.app._data.option = relatedTest();
        if (global.app._data.option == 100) {
            generateMultiParameters();
        } else {
            generateParameters(0);
        }
    } else if (global.nodeList.length == 1) {
        findRelated();
    }
}
```

按中文读：

```text
先撤掉旧候选
  → 只选了一个：尝试自动找同类
  → 已选多个：检查这些元素的关联并更新参数
```

本篇只需要知道 `findRelated()` 会尝试找候选；它怎样修改 XPath 来找同类，放到第 6 篇。

🔴 找同类不一定成功，也不保证猜中的就是用户需要的字段。所以候选和已选要分开。

### 8.2 蓝色阴影不等于正式选中

`pushToReadyList()` 查询匹配结果，把尚未选中的元素加入候选数组，再给匹配元素加阴影。

注意：这个阴影还可能出现在匹配到的已选 A 上，因此“有阴影”也不是候选数组成员的严格判断。

程序判断候选身份，仍然查 `readyList`。

### 8.3 点“选中全部”，候选怎样转成已选

操作台里有这条调用：

```js
selectAll: function () {
  selectAllElements(this);
}
```

函数主线：

```text
selectAllElements()
  → step 加 1
  → readyToList() 把候选记录加到 nodeList
  → 给这些元素上选中色
  → 清掉候选数组和候选阴影
  → handleElement() 更新后续状态
```

例如：

| 时间 | `nodeList` 中的元素 | `readyList` 中的元素 |
| --- | --- | --- |
| 选中 A 之前 | 空 | 空 |
| 选中 A、找到同类后 | A | B、C |
| 候选转入已选时 | A、B、C | 清空 |

表格描述转入这一步；后续 `handleElement()` 会继续根据当前选择重算相关状态。

### 8.4 为什么点 B，有时会把 B、C 都选上

`addEl()` 还有一个分支：

```js
if (exist) { // 此处 exist 表示当前 oe 在 readyList 中
    readyToList(global.step, false);
    // 处理子元素的代码省略
} else {
    clearReady();
    // 普通添加一个元素的分支
}
```

也就是说，选择一个已在候选中的元素，会触发**当前候选整批转入**。

这和操作台上的“选中全部”是两条入口，都会调用 `readyToList()`。

所以课堂不能笼统地说：“鼠标每按一次只会选一个元素。”

---

## 9. 撤销和清空：为什么 `step` 和原样式都要保存

### 9.1 撤销最近一次选择

前面的例子是：

```text
A：step = 1
B：step = 2
C：step = 2
```

点“撤销本次选择”，应该撤掉 B、C，保留 A。

操作台的 `revoke()` 意图是：从数组末尾向前删除当前批次的记录，用记录中保存的样式值还原元素，再更新相关状态。

```text
撤销前：[A(step 1), B(step 2), C(step 2)]
撤销后：[A(step 1)]
```

这就是“一个批次可以有多条记录”的实际用途。

当前源码的撤销循环没有完整保护空数组访问；这里讲的是批次撤销的设计意图，不能把它当成没有边界问题的实现。

### 9.2 清空全部选择

F8 调用 `clearEl()`。核心代码（节选）：

```js
for (let node of global.nodeList) {
    node["node"].style.backgroundColor = node["bgColor"];
    node["node"].style.boxShadow = node["boxShadow"];
}
global.step = 0;
clearReady();
clearParameters();
global.nodeList.splice(0, global.nodeList.length);
```

中文顺序：

```text
先按记录恢复样式
  → 清候选和参数
  → 清已选名单
  → 批次计数归零
```

如果先把数组清掉，就找不到要还原的元素和保存的值了。

`splice(0, length)` 是删除数组的全部项，保留原来的数组对象。这和把变量指向一个新空数组是不同操作。

---

## 10. 对照源码时要知道的几个差异

前面先建立清楚的工作模型；现在再告诉学生：现有代码并没有把每一个细节都实现得很完善。

### 10.1 第一次命中的元素，可能没有马上出现悬停色

`main.js` 中：

```js
if (global.xnode == null) {
    global.xnode = global.oe;
}
if (global.xnode != global.oe) {
    // 换元素时的上色逻辑
}
```

第一次把 `xnode` 设成当前 `oe` 后，两者相等，所以不进入换色分支。切换到另一个元素后才进入。

这也是为什么教学版明确处理“上一个为空”，而不是照抄这段初始化。

### 10.2 记录里有 `bgColor`，不等于原背景一定保存对了

普通选择分支先计算：

```js
let style = node == global.NowNode
    ? global.style
    : node.style.backgroundColor;
```

设计意图是使用上色前的值。但实际悬停代码中，原本想保存颜色的几行已被注释，`global.style` 不会随每次悬停正确更新。

结果可能是：

```text
元素背景来自样式表：
  写回空串 → 撤掉内联覆盖，通常能重新显示样式表的背景

元素原来写了 style="background-color:red"：
  如果没有提前保存 red，写回空串就不能恢复这条内联值
```

`revoke()` 在某些情况下会赋值给 `global.style`，所以也不能说它永远为空。

> 这里要学到的规则是“修改之前保存原值”。源码中的 `bgColor` 是用于还原的记录值，其准确性取决于保存过程。

### 10.3 保存阴影的表达式也有问题

源码里有：

```js
boxShadow: global.NowNode.style.boxShadow == "" || global.boxShadowColor
    ? "none"
    : global.NowNode.style.boxShadow
```

`global.boxShadowColor` 是非空字符串，在条件中为真，所以这个表达式通常得到 `"none"`，没有正确保存原有阴影。

不要把这段当成推荐写法。课堂实验里我们直接保存 `element.style.boxShadow` 或用独立 CSS 类管理提示，更容易保证还原逻辑正确。

### 10.4 三个事件函数到底分别阻止什么（重点）

`addEl()` 末尾写了：

```js
event.stopImmediatePropagation();
event.stopPropagation();
event.preventDefault ? event.preventDefault() : event.returnValue = false;
```

先画出一次事件的路线。假设用户按下一个链接：

```text
按下鼠标
  → 目标元素上的监听器
  → 父元素上的监听器
  → document 上的监听器
  → 浏览器随后执行链接、按钮等默认行为
```

这三个函数分别切断不同的部分。

#### `stopPropagation()`：不让事件继续向父级传播

它阻止事件从当前元素继续冒泡到父元素、`body` 或 `document`，但不取消浏览器默认行为，也不阻止同一个元素上其他已经登记的监听器。

```js
link.addEventListener('mousedown', event => {
  event.stopPropagation();
});
```

在 EasySpider 中，操作台容器使用这类逻辑：点操作台按钮时，事件不要冒泡到 `document.addEventListener("mousedown", addEl)`，否则点“选中全部”可能同时被当成选择网页元素。

#### `stopImmediatePropagation()`：同一目标上的后续监听器也停止

它除了阻止事件继续冒泡，还会停止当前目标上尚未执行的其他监听器：

```js
element.addEventListener('mousedown', firstHandler);
element.addEventListener('mousedown', secondHandler);

function firstHandler(event) {
  event.stopImmediatePropagation();
}
```

执行 `firstHandler` 后，`secondHandler` 不会在这次事件中执行。可以这样记：

```text
stopPropagation          不往外走
stopImmediatePropagation  不往外走，同一个目标后面的也不走
```

#### `preventDefault()`：取消浏览器原本要做的动作

它不管事件传播，而是尝试取消这次事件对应的可取消默认行为，例如链接跳转或表单控件的默认动作：

```js
anchor.addEventListener('mousedown', event => {
  event.preventDefault();
});
```

所以三者的分工是：

```text
stopImmediatePropagation  阻止其他 JavaScript 监听器继续处理
stopPropagation           阻止事件向父级 / document 传播
preventDefault            阻止浏览器默认动作
```

### 10.5 这三行放在 `addEl()` 末尾的完整含义

`main.js` 把 `mousedown` 交给 `addEl`，`addEl` 先记录元素、上选中色、更新候选，然后执行：

```js
event.stopImmediatePropagation();
event.stopPropagation();
event.preventDefault ? event.preventDefault() : event.returnValue = false;
```

一次按下的意图就是：

```text
① 先把当前元素写入 nodeList，或把候选转为已选
② 不让同一目标上的其他 mousedown 监听器继续抢处理
③ 不让事件再冒泡到网页父级和 document 的其他路径
④ 尝试取消链接、按钮等浏览器默认动作
```

但三个函数只处理当前这一次事件。`mousedown`、`mouseup`、`click` 是不同事件；阻止 `mousedown` 不会自动撤销已经运行的监听器，也不能保证所有后续 `click` 都被取消。`preventDefault()` 也只对确实存在且可取消的默认行为生效。

`mousedown`、`mouseup`、`click` 是不同事件，已经运行过的监听器也不会被倒回去。因此不能说这几行一定阻止了所有网页点击和跳转。参见 [事件传播说明](https://developer.mozilla.org/en-US/docs/Web/API/Event/stopImmediatePropagation) 和 [默认行为说明](https://developer.mozilla.org/en-US/docs/Web/API/Event/preventDefault)。

还有一个实现细节：函数形参叫 `e`，末尾却用 `event`，依赖了非标准全局事件的行为。更稳妥的写法是统一使用传入参数：

```js
export function addEl(event, node = global.NowNode, handle = true) {
  // …
  event.stopImmediatePropagation();
  event.stopPropagation();
  event.preventDefault();
}
```

以上是源码当前的意图和边界。本次讲义整理不修改这些程序实现。

以上是源码阅读提示。本次讲义整理不修改这些程序实现。

---

## 11. 最后再看三个 div：工具怎样避免选中自己

到这里再讲辅助界面，就容易理解了。

| 元素 ID | 主要用途 | 与选择过程的关系 |
| --- | --- | --- |
| `wrapperToolkit` | 操作台浮窗 | 用户点工具按钮时，不应误选工具界面 |
| `wrapperDiv` | 虚线框 | 显示当前操作目标的位置和大小 |
| `wrapperTdiv` | 预留的透明层 | 当前默认设为不接收鼠标，特殊选择切换代码已注释 |

### 11.1 为什么点“选中全部”不会把这个按钮选进去

`main.js` 一方面在鼠标移动时判断操作台区域并提前返回，另一方面阻止操作台的 `mousedown` 冒泡：

```js
toolkit.addEventListener("mousedown", function(e) {
    e.stopPropagation();
});
```

可以画成：

```text
点操作台按钮
  → 执行按钮自己的处理，例如 selectAll()
  → 事件到达操作台容器时被停止
  → 不再冒泡到 document 的 addEl 监听器
```

这是“操作工具按钮”和“选择网页元素”两个操作通道。

通知条也有区域排除代码，不过当前实现主要按它的纵向范围判断，不能理解为对所有通知元素都做了精确矩形过滤。

### 11.2 虚线框怎样对准元素

`addEl()` 中：

```js
let pos = global.NowNode.getBoundingClientRect();
global.div.style.display = "block";
global.div.style.height = global.NowNode.offsetHeight + "px";
global.div.style.width = global.NowNode.offsetWidth + "px";
global.div.style.left = pos.left + "px";
global.div.style.top = pos.top + "px";
global.div.style.zIndex = 2147483645;
global.div.style.pointerEvents = "none";
```

`getBoundingClientRect()` 提供元素相对可视区域的位置；辅助框使用 `position: fixed`，因此可以按 `left/top` 移过去，再设置宽高。

`pointerEvents = "none"` 表示命中测试跳过这个框，让鼠标继续指向下面的网页元素。

💡 这个框只有一个，不是给每个已选元素分别造一个。切换悬停元素时，代码会隐藏它；已选名单及选中色仍然保留。

不要用“框还在不在”判断元素是否已经选中。

---

## 12. 动手实验：自己写一个缩小版选择器

这次不用启动完整 EasySpider。新建 `selection-demo.html`，复制下面的代码，用浏览器打开。

建议使用没有 EasySpider 拾取脚本干扰的页面环境，观察这个教学例子自己的行为。

它只演示三件事：**悬停提示、确认选择、清空**。使用 CSS 类管理提示，省去保存和恢复背景值的干扰；同类候选留到下一篇。

```html
<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>元素选择实验</title>
<style>
  .item { padding: 16px; margin: 8px; border: 1px solid #ccc; }
  .hovered { background-color: rgba(221,221,255,0.8); }
  .selected { background-color: rgba(151,255,255,0.6); }
</style>

<p>鼠标移动看提示；右键加入名单；点按钮清空。</p>
<div class="item">商品 A</div>
<div class="item">商品 B</div>
<div class="item">商品 C</div>
<button id="clear">清空选择</button>
<p id="status">已选：0 个</p>

<script>
  let previous = null;
  const selected = [];
  const status = document.querySelector('#status');

  document.addEventListener('mousemove', e => {
    const hit = document.elementFromPoint(e.clientX, e.clientY);
    const current = hit && hit.classList.contains('item') ? hit : null;
    if (current === previous) return;

    if (previous) previous.classList.remove('hovered');
    if (current && !selected.includes(current)) {
      current.classList.add('hovered');
    }
    previous = current;
  });

  // 教学版明确只处理商品区域的右键，与项目 mousedown 入口不同。
  document.addEventListener('contextmenu', e => {
    const current = e.target.closest('.item');
    if (!current) return;
    e.preventDefault();
    if (selected.includes(current)) return;

    selected.push(current);
    current.classList.remove('hovered');
    current.classList.add('selected');
    status.textContent = '已选：' + selected.length + ' 个';
  });

  document.querySelector('#clear').addEventListener('click', () => {
    for (const element of selected) element.classList.remove('selected');
    if (previous) previous.classList.remove('hovered');
    selected.splice(0, selected.length);
    previous = null;
    status.textContent = '已选：0 个';
  });
</script>
</html>
```

### 12.1 按这五步观察

| 操作 | 预期现象 | 对应概念 |
| --- | --- | --- |
| 鼠标放到 A，再移到 B | 提示从 A 移到 B | `previous` 负责撤掉旧提示 |
| 回到 A，右键 | A 青色，已选数量为 1 | 元素加入数组 |
| 从 A 移到 B | A 保持青色，B 出现悬停色 | 选中状态不随鼠标移动消失 |
| 再次右键 A | 数量仍是 1 | 按 DOM 引用去重 |
| 点清空 | 选中色消失，数量归零 | 清视觉状态，也清数组 |

### 12.2 改一行，看问题出现在哪里

先把右键处理里的这句注释掉：

```js
if (selected.includes(current)) return;
```

再次右键 A，多点几次。

**颜色没有变，但计数不断增加。** 这说明视觉状态不能代替数据状态，也说明为什么要去重。

恢复这句，再把清空处理里的这句注释掉：

```js
selected.splice(0, selected.length);
```

清空之后，界面虽然暂时不青了，数组却还记着旧元素。再次选择时会被判定为“已经选过”。

> 清空不仅是擦掉颜色，还必须同步更新程序记忆。

---

## 13. 现在打开源码：按操作路线读，不按文件行数背

建议第一次阅读只沿下面这条路走：

```text
鼠标移动：
main.js 的 mousemove 监听器
  → elementFromPoint
  → oe / NowNode
  → nodeList 成员检查
  → 旧提示、新提示、xnode 交接

确认选择：
main.js 的 mousedown 监听器
  → global.js 的 addEl
  → 普通添加或候选整批转入
  → handleElement

确认同类：
toolkit.vue 的 selectAll
  → selectAllElements
  → readyToList

取消操作：
toolkit.vue 的 revoke      撤销最近批次
main.js 的 F8 → clearEl   清空全部选择
```

几个文件的分工：

| 文件 | 本篇先读什么 |
| --- | --- |
| `src/content-scripts/main.js` | 鼠标和键盘怎样触发函数；辅助界面怎样接入网页 |
| `src/content-scripts/global.js` | 状态数组、添加、清空、候选转入 |
| `src/content-scripts/toolkit.vue` | “选中全部”“撤销本次选择”按钮调用谁 |

以上路径均相对 `Extension/manifest_v3/`。

`main.js` 中的 Vue 挂载、拖拽、缩放和定时恢复操作台，可以在掌握主线之后再读。它们是工具界面的维护工作，不必在理解元素选择前一次学完。

---

## 14. 课堂收尾：用自己的话回答这五个问题

1. **鼠标指着 B，为什么 A 还能保持选中？** 当前位置和已选名单分别保存，悬停逻辑会跳过已选元素的颜色修改。
2. **为什么需要 `xnode`？** 要撤掉上一轮的悬停提示，就必须记住上一轮的元素。
3. **`readyList` 和 `nodeList` 有什么区别？** 一个保存软件推荐的候选，一个保存用户已经确认的记录。
4. **同一次操作加入 B、C，撤销时怎么一起删掉？** 用相同的 `step` 标记这批记录。
5. **选中元素之后，采集任务就保存好了吗？** 还没有；这里记录的是当前页面上的选择状态，后续还要通过操作台形成采集动作和任务数据。

把本篇主线压成一句话：

> **鼠标移动更新“当前目标”；确认选择更新“已选名单”；软件推荐更新“候选名单”；界面再根据这些记录显示提示。**

下一篇沿着 `findRelated()` 继续：软件怎么从 A 的 XPath 推测出 B、C。

---

返回目录：[README.md](README.md) ｜ 上一篇：[04.XPath：元素定位的通用语言](04.XPath详解.md) ｜ 下一篇：[06.同类元素自动匹配：点一个，猜出一整列](06.同类元素自动匹配.md)
