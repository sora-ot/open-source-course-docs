---
title: "19 · 流程图渲染"
description: "easyspider · 流程图与执行 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/19.流程图渲染机制.md"
originalUrl: "/originals/easyspider/chapter-19.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 19.流程图怎样画出来：逐步执行 refresh、生成 DOM 与 CSS 外观

> 第 15 篇建立层次结构，第 18 篇区分存储下标和界面编号。
>
> 本篇按“准备画布 → 清空重建 → BFS 编号 → 生成 HTML → 放入父容器 → 绑定事件”的过程逐步看代码，再对照 CSS 和实际截图。
>
> 先用五节点小图走通完整过程，再看两层循环、判断分支与十三节点房源图。消息接收放到第 21 讲。

## 开始渲染之前：先认清 id、data、position、pId

先把 HTML 属性读懂，后面才能看清“选中了哪个元素、把孩子放进哪里、在什么位置插入”。这里使用后文加入循环后的五节点图预先说明属性，不另换业务：

~~~text
节点                存储下标 index    界面编号 id
root                     0                0
├─ 打开网页              1                1
├─ 循环                  4                2
│  └─ 点击按钮           2                4
└─ 提取结果              3                3

root.sequence = [1,4,3]
循环.sequence = [2]
actionSequence = [0,1,4,3,2]
~~~

**先区分两种数字：index 定位内存对象，id 定位本次界面。** 循环存于 nodeList[4]，但生成的循环容器用 id="2"；点击存于 nodeList[2]，但方块用 id="4"。从界面编号找对象，要先经过 actionSequence。

**四个属性分别回答什么问题？**

| 属性 | 表示什么 | 本例“点击按钮”上的值 | 用在哪里 |
| --- | --- | --- | --- |
| id | 当前 DOM 元素的唯一标识；业务节点的容器使用其界面编号 | id="4" | 用 `$("#4")` 或 getElementById("4") 选中元素 |
| data | 该元素关联的业务节点界面编号，是源码自定义的属性 | data="4" | 事件里 getAttribute("data")，再查 actionSequence[4]=2 |
| pId | 父节点的界面编号，对应接收孩子的父容器 id | pId="2" | 用 `$("#2")` 找父循环的容器；找父对象则查 nodeList[actionSequence[2]] |
| position | 该节点在父 sequence 中的位置，从 0 开始 | position="0" | 循环的 sequence=[2]，点击正是其中第 0 项 |

pId 保存的是一个编号，不是父元素对象，也不是父节点的稳定 index。position 是父容器内的局部位置，不是 nodeList 下标、整图执行序号或 CSS 的 position 属性。

**把这些值放回 HTML 看。** 下面按最终 DOM 的父子关系展示，保留定位属性，省去行内样式、拖动属性与文字内部包装：

~~~html
<div id="0" class="clk" data="0">
  <p id="firstArrow" class="arrow" pId="0" position="-1">↓</p>

  <div class="sequence">
    <div class="node clk" id="1" data="1" dataType="0" pId="0" position="0">打开网页</div>
    <p class="arrow" data="1" pId="0" position="0">↓</p>
  </div>

  <div class="loop clk" id="2" data="2" dataType="1" pId="0" position="1">
    <p>循环</p>
    <p class="arrow" data="2" pId="2" position="-1">↓</p>
    <div class="sequence">
      <div class="node clk" id="4" data="4" dataType="0" pId="2" position="0">点击按钮</div>
      <p class="arrow" data="4" pId="2" position="0">↓</p>
    </div>
  </div>
  <p class="arrow" data="2" pId="0" position="1">↓</p>

  <div class="sequence">
    <div class="node clk" id="3" data="3" dataType="0" pId="0" position="2">提取结果</div>
    <p class="arrow" data="3" pId="0" position="2">↓</p>
  </div>
</div>
~~~

这份概念示意省去了开始圆形；后面逐步执行部分会展示包含开始标记和全部生成属性的实际快照。

**为什么 id 和 data 相同，还要都写？** 普通方块的两者都来自 node.id，但方块下方的后置箭头也要携带同一节点编号，所以方块与箭头都可以有 data="4"。id 应在整页中唯一，因此不会再给箭头写相同的 id="4"。id 供 DOM 定位，data 供事件读取关联节点的编号。

不是每个元素都同时带这两个属性。首箭头有自己的 id="firstArrow"，没有 data；判断、条件分支模板则把 data 放在外层可选择区域，把数值 id 放在内部接收孩子的容器上。看到 `$("#" + parentId)` 时，要找的是能接收孩子的容器。

**箭头上的 pId、position 怎么读？** 对节点，它们描述“我属于谁、排第几”；对插入箭头，它们描述“新节点应该插进谁的 sequence、插在哪一项之后”：

| 箭头 | pId | position | 对应插入位置 |
| --- | --- | --- | --- |
| root 的首箭头 | 0 | -1 | root.sequence 的开头，插入位置为 0 |
| 循环框内的首箭头 | 2 | -1 | actionSequence[2]=4，插入 nodeList[4].sequence 的开头 |
| 点击按钮后面的箭头 | 2 | 0 | 在父循环第 0 个孩子之后插入，插入位置为 1 |
| 循环框外面的箭头 | 0 | 1 | 在 root 的第 1 个孩子（循环）之后插入，插入位置为 2 |

同样是循环附近的箭头，pId=2 表示放进循环内部，pId=0 表示放进 root，层级完全不同。position=-1 不是数组里真的存在一个“第 -1 项”，而是“第一个孩子之前”的约定，实际插入用 position+1：

~~~js
const parentUiId = Number(arrow.getAttribute("pId"));
const position = Number(arrow.getAttribute("position"));
const parent = nodeList[actionSequence[parentUiId]];
const insertAt = position + 1;
// 后续向 parent.sequence 的 insertAt 位置插入新节点下标。
~~~

DOM 的 getAttribute 返回字符串，所以做 position+1 这样的算术前先转成数字。pId 指的是流程结构上的父容器；由于有 .sequence 包装层，它不一定等于该元素直接 parentElement 的 id。

**顺便认识模板中的其他属性。**

| 属性或字段 | 用途 |
| --- | --- |
| dataType | HTML 上保存 node.type；0=普通动作、1=循环、2=判断、3=条件分支，不是操作 option |
| class | .node、.loop、.arrow 等用于样式和选择元素；.clk 用于统一绑定节点选择事件 |
| draggable="true" | 允许元素参与 HTML 拖动；实际拖动行为还要绑定事件处理函数 |
| node.parentId → HTML 的 pId | 对象字段与 HTML 属性名称不同，但传递的是同一个父界面编号 |

下面遇到 `$("#" + node.parentId).append(newNode(node))`，就可以直接读成：**先按父界面编号选中父容器，再把当前节点生成的 HTML 插入这个父元素内部的末尾。** 接下来才开始逐步看它怎样生成。

---

截图来自[渲染机制教学页](/resources/easyspider/%E7%A4%BA%E4%BE%8B-Flowchart/%E6%B8%B2%E6%9F%93%E6%9C%BA%E5%88%B6-%E6%BC%94%E7%A4%BA.html)：直接使用仓库的 jQuery、Bootstrap、FlowChart.css，并提取原始 `refresh()`、`newNode()` 执行。教学页收起了工具箱与参数面板，另加数据说明；方块与循环框的模板、样式来自源码。点击日志是教学实现，真实事件绑定代码在本篇第四部分逐项讲解。

下面每个渲染步骤都按“执行代码 → 执行后的 HTML → 解释或截图”阅读。HTML 快照取自浏览器实际生成的 DOM，完整展示 **#0 元素及其内部内容**，保留属性和行内样式，只去掉用于排版的空白并整理缩进；#0 外面的工具箱、结束圆形不重复列出。浏览器会把 pId、dataType 属性名规范为小写 pid、datatype，含义不变。

数据赋值和 BFS 编号阶段也会说明 HTML 的状态；只有实际操作 DOM 的语句才会增加、移除或修改标签。后面的复习片段各自回到指定起点，不是在最终画布上再次 append，以免把同一个方块重复添加。

---

## 第一部分：先准备画布，再从空图开始

### 1. HTML 先提供容器，JavaScript 才能往里面放东西

入口页面见 [FlowChart_CN.html](/source/?file=9bc3327fb264a3fe95.html)。样式和脚本按下面的顺序引入；这些相对路径以原页面所在目录为准：

~~~html
<script src="jquery-3.4.1.min.js"></script>
<script src="bootstrap/js/bootstrap.js"></script>
<script src="vue.js"></script>
<link rel="stylesheet" href="bootstrap/css/bootstrap.css">
<link rel="stylesheet" href="FlowChart.css">
~~~

jQuery 提供 `$()`、`empty()`、`append()`；Bootstrap 提供基础样式；FlowChart.css 再定义蓝色动作块、循环边框和箭头。原页面末尾还会加载 FlowChart.js、global.js、logic.js，分别涉及界面、公共能力与操作逻辑。

原页面中的画布结构如下，属性和内部内容保留源码写法，只整理缩进：

~~~html
<div style="margin-top:20px;border: solid;height:850px;overflow: auto;width:58%;float:right"
     id="flowchart_graph">
  <div id="0" class="clk" data="0"></div>
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid black;margin: 5px auto;background-color:lightcyan">
    <p style="font-size: 22px!important;text-align: center;margin-left: 1px;">■</p>
  </div>
</div>
~~~

这里有两层不同职责的容器：

| 元素 | 职责 |
| --- | --- |
| #flowchart_graph | 外层可滚动画布，原页面限定 850px 高度 |
| #0 | root 对应的内容容器，refresh 每次清空后重建这里 |
| #0 后面的结束圆形 | 固定 HTML，位于 #0 外面，不随 #0.empty() 删除 |

`$("#0")` 表示选中 id 为 0 的元素；`$("#0").append(html)` 表示把一段 HTML 作为它的内部内容追加到末尾。理解“追加到哪个父元素里面”，就能理解后面的嵌套。

### 2. 第一步：清空 #0，再生成开始标记和第一根箭头

后面的输入例子用一个教学辅助函数缩短数据。它只负责补齐本篇渲染需要的字段，不是源码新增节点的入口：

~~~js
function makeNode(index, title, option, type, sequence = []) {
  return {
    index, title, option, type, sequence,
    id: 0,
    parentId: 0,
    isInLoop: false,
    parameters: {}
  };
}

nodeList = [makeNode(0, "root", 0, -1)];
~~~

`refresh()` 的开头是下面两句。这里把原本省略的 HTML 全部展开：

~~~js
$("#0").empty();
~~~

执行完 empty 后，#0 的完整 HTML 变成：

~~~html
<div id="0" class="clk" data="0"></div>
~~~

再执行添加开始标记与首箭头的语句：

~~~js
$("#0").append(`<div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
  <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
</div>
<p id="firstArrow" class="arrow" position=-1 pId=0>↓</p>`);
~~~

执行完这次 append 后，#0 的完整 HTML 为：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
</div>
~~~

先删掉 #0 内部的旧节点，再添加绿色开始圆形与首箭头。首箭头 `pId=0` 指向 root，`position=-1` 表示位于 root 的第一个孩子之前；后续新增时使用 `position+1=0` 作为插入位置。

空图的 BFS 只取出 root，没有孩子可编号，所以 actionSequence=[0]。后续绘制从 actionSequence 的第 1 项开始，空图没有这一项，结果如下：

![只有 root 时的实际渲染：开始、首箭头与固定结束标记](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%B8%B2%E6%9F%93-01-%E7%A9%BA%E7%94%BB%E5%B8%83.png)

图中出现开始与结束圆形，但 nodeList 仍只有 root。圆形和箭头都是页面元素，不是另外追加的业务节点。若不先 empty，每次刷新都 append 一遍，同一张图就会重复堆在画布中。

### 3. 第二步的简单输入：三个顺序动作先画成一列

在教学页环境里准备四个节点，再调用真实的 refresh：

~~~js
nodeList = [
  makeNode(0, "root",     0, -1, [1,2,3]),
  makeNode(1, "打开网页", 1,  0),
  makeNode(2, "点击按钮", 2,  0),
  makeNode(3, "提取结果", 3,  0)
];
refresh();
~~~

这次三个孩子都属于 root，编号后 actionSequence=[0,1,2,3]。下面是绘制循环在这一特定输入下的展开结果，三句等价于循环的三次迭代：

执行第 1 次追加：

~~~js
$("#0").append(newNode(nodeList[1])); // 打开网页及它后面的箭头
~~~

执行后，#0 的完整 HTML（已包含前 1 个动作）：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
</div>
~~~

执行第 2 次追加：

~~~js
$("#0").append(newNode(nodeList[2])); // 点击按钮及它后面的箭头
~~~

执行后，#0 的完整 HTML（已包含前 2 个动作）：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="sequence">
    <div class="node clk" draggable="true" data="2" datatype="0" id="2" position="1" pid="0">
      <div>
        <p style="margin-top: 2px">点击按钮</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="1" data="2" pid="0">↓</p>
  </div>
</div>
~~~

执行第 3 次追加：

~~~js
$("#0").append(newNode(nodeList[3])); // 提取结果及它后面的箭头
~~~

执行后，#0 的完整 HTML（已包含前 3 个动作）：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="sequence">
    <div class="node clk" draggable="true" data="2" datatype="0" id="2" position="1" pid="0">
      <div>
        <p style="margin-top: 2px">点击按钮</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="1" data="2" pid="0">↓</p>
  </div>
  <div class="sequence">
    <div class="node clk" draggable="true" data="3" datatype="0" id="3" position="2" pid="0">
      <div>
        <p style="margin-top: 2px">提取结果</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="2" data="3" pid="0">↓</p>
  </div>
</div>
~~~


三个片段都是 #0 的孩子，按照 append 的先后向下排列。此时界面 id 与存储下标恰好相同：

![三个顺序动作追加在同一个 root 容器中](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%B8%B2%E6%9F%93-02-%E4%B8%89%E4%B8%AA%E9%A1%BA%E5%BA%8F%E5%8A%A8%E4%BD%9C.png)

下一步加入循环，就会出现不同的父容器，不能继续把所有动作都 append 到 #0。

---

## 第二部分：逐步执行 BFS，再逐步追加 HTML

如果已经忘了“为什么要做 BFS、actionSequence 有什么用”，可以先复习[第 18 讲双层循环的生成过程与目的](/easyspider/chapter-18#nested-bfs-action-sequence)，再回来逐句跟踪下面的代码和 HTML。

### 4. 准备五节点输入，初始化编号和队列

接下来各步骤固定使用这份输入。下标 2 的点击创建得早，但属于后来创建的循环 4：

~~~js
nodeList = [
  makeNode(0, "root",     0, -1, [1,4,3]),
  makeNode(1, "打开网页", 1,  0),
  makeNode(2, "点击按钮", 2,  0),
  makeNode(3, "提取结果", 3,  0),
  makeNode(4, "循环",     8,  1, [2])
];
~~~

清空画布、添加开始标记之后，refresh 用下面的代码开始编号：

~~~js
actionSequence.splice(0);
queue.splice(0);
let idd = 1;
queue.push(0);
actionSequence.push(0);
~~~

准备五节点数据、清空画布并初始化两个数组后，还没有追加业务节点，HTML 为：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
</div>
~~~

`splice(0)` 清空已有数组；queue=[0] 表示 root 等待展开；actionSequence=[0] 表示界面 id=0 对应 nodeList[0]；idd=1 表示下一个被发现的孩子将拿到界面 id=1。

### 5. 取出一个父节点，依次给它的孩子写入定位字段

先看完整的遍历代码，来自 [FlowChart.js](/source/?file=48b61e5e4ebaa6ccf2.js) 的 refresh：

~~~js
while (queue.length != 0) {
  let nd = queue.shift();
  for (let i = 0; i < nodeList[nd].sequence.length; i++) {
    nodeList[nodeList[nd].sequence[i]].parentId = nodeList[nd].id;
    nodeList[nodeList[nd].sequence[i]]["position"] = i;
    nodeList[nodeList[nd].sequence[i]].id = idd++;
    if (nodeList[nd].option == 8 || nodeList[nd].isInLoop) {
      nodeList[nodeList[nd].sequence[i]].isInLoop = true;
    } else {
      nodeList[nodeList[nd].sequence[i]].isInLoop = false;
    }
    queue.push(nodeList[nd].sequence[i]);
    actionSequence.push(nodeList[nd].sequence[i]);
  }
}
~~~

`shift()` 取出队首并移除，`push()` 把新发现的孩子加入队尾。这样先展开浅层，再展开深层，就是 BFS。把一轮中连续的数组下标拆成变量，便于看清每一行：

~~~js
const parent = nodeList[nd];           // 本轮父对象
const childIndex = parent.sequence[i]; // 第 i 个孩子的稳定存储下标
const child = nodeList[childIndex];    // 孩子对象

child.parentId = parent.id;           // 父的界面 id，用于找到父 DOM 容器
child.position = i;                   // 在父 sequence 中的位置
child.id = idd++;                      // 本次界面编号，写完后计数器加一
child.isInLoop = parent.option == 8 || parent.isInLoop;

queue.push(childIndex);               // 孩子以后也要展开
actionSequence.push(childIndex);      // 保存 界面 id → 存储下标 的映射
~~~

例如第一次取出 root，nd=0；处理它的第二个孩子时 i=1：

~~~js
const parent = nodeList[0];       // root，id=0
const childIndex = parent.sequence[1]; // 4
const child = nodeList[4];        // 循环

child.parentId = 0;
child.position = 1;
child.id = 2;                     // 此时 idd=2，原代码 idd++ 后变为 3
child.isInLoop = false;           // 父亲 root 不是循环，也不在循环内
queue.push(4);
actionSequence.push(4);           // 写入的是存储下标 4
~~~

循环自身不在循环内，所以 isInLoop=false。以后取出循环 4，发现它的点击孩子 2，点击就会得到 isInLoop=true。

| 本轮 nd | 发现的孩子（存储下标） | 孩子获得的界面 id | 本轮结束的 queue | actionSequence |
| --- | --- | --- | --- | --- |
| 0 root | 1、4、3 | 1→1，4→2，3→3 | [1,4,3] | [0,1,4,3] |
| 1 打开 | 无 | 无 | [4,3] | [0,1,4,3] |
| 4 循环 | 2 | 2→4 | [3,2] | [0,1,4,3,2] |
| 3 提取 | 无 | 无 | [2] | [0,1,4,3,2] |
| 2 点击 | 无 | 无 | [] | [0,1,4,3,2] |

最终要带入 HTML 模板的字段如下：

| index | 节点 | id | parentId | position | isInLoop |
| --- | --- | --- | --- | --- | --- |
| 1 | 打开网页 | 1 | 0 | 0 | false |
| 4 | 循环 | 2 | 0 | 1 | false |
| 3 | 提取结果 | 3 | 0 | 2 | false |
| 2 | 点击按钮 | 4 | 2 | 0 | true |

到这里完成的是编号。每次 shift、字段赋值和 push 都只操作 JavaScript 数据，没有操作 DOM。上表五轮 BFS 各自结束后，HTML 都与下面这份快照完全相同：

BFS 每轮结束后，以及整个 BFS 结束后的 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
</div>
~~~



### 6. 绘制循环先取对象，再找到父容器

编号结束后，真实代码是：

~~~js
for (let i = 1; i < actionSequence.length; i++) {
  let parentId = nodeList[actionSequence[i]]["parentId"];
  $("#" + parentId).append(newNode(nodeList[actionSequence[i]]));
}
bindEvents();
~~~

这里 i 是界面 id；actionSequence[i] 才是存储下标。拆开一轮看：

~~~js
const index = actionSequence[i]; // 查本轮对象在 nodeList 的位置
const node = nodeList[index];
const parentId = node.parentId;
const html = newNode(node);      // 根据 type 返回 HTML 字符串
$("#" + parentId).append(html);  // 放进父元素的内部末尾
~~~

`"#" + 2` 得到选择器 `"#2"`，选中循环框；不是取 nodeList[2]。第 0 项 root 的容器已经在静态 HTML 中，所以从 i=1 开始。

### 7. 第 1、2 次 append：先放打开网页，再建立空循环框

先执行第一轮：

~~~js
// i=1，actionSequence[1]=1，打开网页的 parentId=0
$("#0").append(newNode(nodeList[1]));
~~~

第一轮执行后，只有打开网页及它的后置箭头进入 #0：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
</div>
~~~

再执行第二轮：

~~~js
// i=2，actionSequence[2]=4，循环的 parentId=0
$("#0").append(newNode(nodeList[4]));
~~~

第二轮执行后，#0 增加了循环框 #2 和框外后置箭头；#2 内还没有点击动作：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="loop clk" data="2" draggable="true" datatype="1" id="2" position="1" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">循环</p>
    <p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
  </div>
  <p class="arrow" draggable="true" data="2" position="1" pid="0">↓</p>
</div>
~~~


第二句创建出 id="2" 的循环框，框内暂时只有标题和首箭头。虽然数据里已经写着循环 sequence=[2]，模板函数不会自己递归画孩子；后面的绘制迭代还要把点击放进去。

![前两次 append：父循环框已经创建，内部点击尚未追加](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%B8%B2%E6%9F%93-03-%E5%85%88%E5%BB%BA%E7%AB%8B%E7%A9%BA%E5%BE%AA%E7%8E%AF%E6%A1%86.png)

这是教学页截取的中间状态。真实 refresh 连续完成全部迭代，通常不会让用户看到这个暂停画面。

### 8. 第 3 次 append：提取先画出来，但仍在循环框外

第三轮 i=3，actionSequence[3]=3，提取的 parentId=0：

~~~js
$("#0").append(newNode(nodeList[3]));
~~~

第三轮执行后，#0 的完整 HTML 如下；注意提取包装层出现在循环闭合标签之后：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="loop clk" data="2" draggable="true" datatype="1" id="2" position="1" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">循环</p>
    <p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
  </div>
  <p class="arrow" draggable="true" data="2" position="1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="3" datatype="0" id="3" position="2" pid="0">
      <div>
        <p style="margin-top: 2px">提取结果</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="2" data="3" pid="0">↓</p>
  </div>
</div>
~~~

追加目标是 #0，所以提取成为循环框后面的同级元素：

![第三次 append：提取已在循环框外，循环内部仍为空](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%B8%B2%E6%9F%93-04-%E5%85%88%E6%8A%8A%E6%8F%90%E5%8F%96%E6%94%BE%E5%9C%A8%E6%A1%86%E5%A4%96.png)

这时点击虽然尚未生成，提取也不会因此成为循环的孩子；HTML 的父元素已经决定了归属。

### 9. 第 4 次 append：找到 #2，把点击放进循环

最后一轮 i=4，actionSequence[4]=2，点击的 parentId=2：

~~~js
const node = nodeList[actionSequence[4]]; // nodeList[2]，点击按钮
const parentId = node.parentId;          // 2：父循环的界面 id
$("#" + parentId).append(newNode(node));  // 追加到循环框 #2 内部
~~~

第四轮执行后，完整 HTML 变成下面这样；点击动作新出现在 #2 的内部，提取仍在外面：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="loop clk" data="2" draggable="true" datatype="1" id="2" position="1" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">循环</p>
    <p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
    <div class="sequence">
      <div class="node clk" draggable="true" data="4" datatype="0" id="4" position="0" pid="2">
        <div>
          <p style="margin-top: 2px">点击按钮</p>
        </div>
      </div>
      <p class="arrow" draggable="true" position="0" data="4" pid="2">↓</p>
    </div>
  </div>
  <p class="arrow" draggable="true" data="2" position="1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="3" datatype="0" id="3" position="2" pid="0">
      <div>
        <p style="margin-top: 2px">提取结果</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="2" data="3" pid="0">↓</p>
  </div>
</div>
~~~

父框在第二轮已经创建，因此这里能够选中 #2。点击的方块与后置箭头都进入循环框，循环框按内容自然变高：

![第四次 append：点击进入父循环，形成最终嵌套](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%B8%B2%E6%9F%93-05-%E5%86%8D%E6%8A%8A%E7%82%B9%E5%87%BB%E6%94%BE%E8%BF%9B%E6%A1%86%E5%86%85.png)

整理后的 DOM 层次如下，文字行代表已生成的元素：

~~~text
#0
├─ 开始圆形与首箭头
├─ .sequence：打开网页 id=1，以及后置箭头
├─ .loop：循环 id=2
│  ├─ 循环标题
│  ├─ 循环内首箭头
│  └─ .sequence：点击按钮 id=4，以及后置箭头
├─ 循环外的后置箭头
└─ .sequence：提取结果 id=3，以及后置箭头
~~~

BFS 保证父容器先创建，再追加孩子。若按存储下标 1、2、3、4 直接绘制，点击 2 会先于父循环 4，届时 #2 还不存在。绘制顺序为打开、循环、提取、点击；执行时却要先完成整个循环，再提取。这两种顺序的用途在第 18 讲已经区分。

**换成深度优先的“先序遍历”也可以：先处理父节点，再递归处理孩子。** 仍用这里的五节点图，下面数字都是稳定的存储下标，包含 root：

~~~text
广度优先：0 → 1 → 4 → 3 → 2
          root → 打开 → 循环 → 提取 → 点击

深度先序：0 → 1 → 4 → 2 → 3
          root → 打开 → 循环 → 点击 → 提取
~~~

两种次序都先创建循环 4 的容器，再把点击 2 放进去，因此可以得到相同的 HTML 层次。**渲染的关键是父容器先建立，BFS 是当前源码采用的选择。**

如果改用 DFS，actionSequence、界面 id 和 parentId 要按新次序一致地生成；nodeList 的稳定下标、各节点的 sequence 和业务执行含义不需要改变。这里说的是深度优先的先序遍历，不能把先处理孩子、后处理父亲的后序遍历直接套到当前 append 写法中。

---

## 第三部分：newNode 每种类型究竟生成什么 HTML

### 10. 先完整看模板函数，再分别代入节点

newNode 只根据 type 选择模板、把字段放入字符串并返回；它本身不调用 append，也不递归访问 sequence。下面完整摘录原函数，包括中英文判断模板：

~~~js
function newNode(node) {
    id = node["id"];
    title = node["title"];
    type = node["type"];
    if (type == 0) //顺序
    {
        return `<div class="sequence"><div class="node clk" draggable="true" data="${id}" dataType=${type} id = "${id}" position=${node["position"]} pId=${node["parentId"]}>
                <div >
                    <p style="margin-top: 2px">${title}</p>
                </div>
            </div>
            <p class="arrow" draggable="true" position=${node["position"]} data = "${id}" pId=${node["parentId"]}>↓</p></div>`;
    } else if (type == 1) //循环
    {
        return `<div class="loop clk" data="${id}" draggable="true" dataType=${type} id = "${id}" position=${node["position"]} pId=${node["parentId"]}>
             <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                <p class="arrow" draggable="true" position=-1 data = "${id}" pId=${id}>↓</p>
            </div>
            <p class="arrow" draggable="true" data = "${id}" position=${node["position"]} pId=${node["parentId"]}>↓</p></div>`;
    } else if (type == 2) //判断
    {
        return LANG(`<div class="loop clk" draggable="true" dataType=${type} data="${id}" position=${node["position"]} pId=${node["parentId"]}>
                    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                    <p class="branchAdd" data="${id}">点击此处在最右边增加条件分支</p>
                    <div class="judge" id = "${id}">
                    </div></div>
                    <p class="arrow" draggable="true" data = "${id}" position=${node["position"]} pId=${node["parentId"]}>↓</p></div>`,
            `<div class="loop clk" draggable="true" dataType=${type} data="${id}" position=${node["position"]} pId=${node["parentId"]}>
                    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                    <p class="branchAdd" data="${id}">Click here to add a new condition to the right most</p>
                    <div class="judge" id = "${id}">
                    </div></div>
                    <p class="arrow" draggable="true" data = "${id}" position=${node["position"]} pId=${node["parentId"]}>↓</p></div>`);
    } else //判断分支
    {
        return `<div class="branch clk" dataType=${type} data="${id}" position=${node["position"]} pId=${node["parentId"]}>
                    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                    <p data = "${id}" class="arrow" draggable="true" position=-1 pId=${id}>↓</p>
                    <div id = "${id}">
                    </div></div>`;
    }
}
~~~

`id`、`title`、`type` 在原函数中是赋值写法；本节讲模板生成，不把它们改写成另一个实现。LANG 负责选择中英文文本。普通动作 type=0，循环 type=1，判断 type=2，其余路径用于条件分支 type=3。

下面的 HTML 按浏览器解析后的有效层次整理缩进。原循环和判断模板字符串尾部有多余的闭合 div；不要据此想象出新的父容器，实际层次可在教学页开发者工具的 Elements 中查看。

### 11. 普通动作：一个包装层、一个方块、一根后置箭头

这里回到第二部分第三次 append 之后的状态，复习第四次追加；不要在已经画好的最终图上重复执行：

~~~js
const html = newNode(nodeList[2]); // index=2，id=4，parentId=2，position=0
$("#2").append(html);
~~~

执行这两句后，整张 #0 的 HTML 就是第二部分第四轮后的完整快照。其中本次追加的普通节点片段为：

~~~html
<div class="sequence">
  <div class="node clk" draggable="true" data="4" dataType="0"
       id="4" position="0" pId="2">
    <div><p style="margin-top: 2px">点击按钮</p></div>
  </div>
  <p class="arrow" draggable="true" position="0" data="4" pId="2">↓</p>
</div>
~~~

`.sequence` 把方块与它后面的箭头作为一组；`.node` 控制方块外观；`.clk` 让 bindEvents 找到可选择的元素。id/data 用界面编号，pId 用父界面编号，position 用父 sequence 内的位置。

后面的箭头 `pId=2, position=0` 表示在循环容器的第 0 个孩子后面插入。它指向父循环的孩子列表，不会把新动作塞进点击自己那个空 sequence。

### 12. 循环：先返回能装孩子的框，孩子稍后追加

对循环对象生成模板：

~~~js
const loop = nodeList[4];           // id=2，parentId=0，position=1
$("#0").append(newNode(loop));      // 建立循环容器 #2
// 之后处理点击孩子时，目标才会是 #2：
$("#2").append(newNode(nodeList[2]));
~~~

循环模板在孩子追加之前的有效结构是：

~~~html
<div class="loop clk" data="2" draggable="true" dataType="1"
     id="2" position="1" pId="0">
  <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">循环</p>
  <p class="arrow" draggable="true" position="-1" data="2" pId="2">↓</p>
</div>
<p class="arrow" draggable="true" data="2" position="1" pId="0">↓</p>
~~~

| 箭头 | pId | position | 对应插入地址 |
| --- | --- | --- | --- |
| 循环框内首箭头 | 2 | -1 | actionSequence[2]=4，在 nodeList[4].sequence 的开头插入 |
| 循环框外后置箭头 | 0 | 1 | 在 root.sequence 的第 1 项之后插入 |

这两句是第二部分第二轮和第四轮的路径复习：建立循环框后 HTML 对应第二轮快照，添加点击后对应第四轮快照；中间的提取追加仍按第三轮完成。

两根箭头长得相同，但父容器相差一层。图中的灰标题来自模板里的行内 style；蓝色外框来自 CSS 的 .loop。

### 13. 两层循环：无需新增渲染算法，再套一层父容器即可

这是从五节点基准图独立添加内层循环的例子，与第 15 讲的七节点快照一致：

~~~js
nodeList[4].title = "外层循环";
nodeList[4].sequence = [2,5];
nodeList.push(makeNode(5, "内层循环", 8, 1, [6]));
nodeList.push(makeNode(6, "点击内层按钮", 2, 0));
refresh();
~~~

刷新得到 actionSequence=[0,1,4,3,2,5,6]。外层循环 id=2，内层循环 id=5，内层动作 id=6。编号生成的逐轮过程与用途见[第 18 讲双层循环图解](/easyspider/chapter-18#nested-bfs-action-sequence)。

把这次 refresh 的六次 append 全部展开。起点仍是只包含开始标记和首箭头的 #0：

**嵌套示例，第 1 次追加：打开网页。**

~~~js
$("#0").append(newNode(nodeList[1]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
</div>
~~~

**嵌套示例，第 2 次追加：外层循环，建立 #2。**

~~~js
$("#0").append(newNode(nodeList[4]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="loop clk" data="2" draggable="true" datatype="1" id="2" position="1" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">外层循环</p>
    <p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
  </div>
  <p class="arrow" draggable="true" data="2" position="1" pid="0">↓</p>
</div>
~~~

**嵌套示例，第 3 次追加：提取结果。**

~~~js
$("#0").append(newNode(nodeList[3]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="loop clk" data="2" draggable="true" datatype="1" id="2" position="1" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">外层循环</p>
    <p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
  </div>
  <p class="arrow" draggable="true" data="2" position="1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="3" datatype="0" id="3" position="2" pid="0">
      <div>
        <p style="margin-top: 2px">提取结果</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="2" data="3" pid="0">↓</p>
  </div>
</div>
~~~

**嵌套示例，第 4 次追加：外层点击。**

~~~js
$("#2").append(newNode(nodeList[2]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="loop clk" data="2" draggable="true" datatype="1" id="2" position="1" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">外层循环</p>
    <p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
    <div class="sequence">
      <div class="node clk" draggable="true" data="4" datatype="0" id="4" position="0" pid="2">
        <div>
          <p style="margin-top: 2px">点击按钮</p>
        </div>
      </div>
      <p class="arrow" draggable="true" position="0" data="4" pid="2">↓</p>
    </div>
  </div>
  <p class="arrow" draggable="true" data="2" position="1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="3" datatype="0" id="3" position="2" pid="0">
      <div>
        <p style="margin-top: 2px">提取结果</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="2" data="3" pid="0">↓</p>
  </div>
</div>
~~~

**嵌套示例，第 5 次追加：内层循环，建立 #5。**

~~~js
$("#2").append(newNode(nodeList[5]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="loop clk" data="2" draggable="true" datatype="1" id="2" position="1" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">外层循环</p>
    <p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
    <div class="sequence">
      <div class="node clk" draggable="true" data="4" datatype="0" id="4" position="0" pid="2">
        <div>
          <p style="margin-top: 2px">点击按钮</p>
        </div>
      </div>
      <p class="arrow" draggable="true" position="0" data="4" pid="2">↓</p>
    </div>
    <div class="loop clk" data="5" draggable="true" datatype="1" id="5" position="1" pid="2">
      <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">内层循环</p>
      <p class="arrow" draggable="true" position="-1" data="5" pid="5">↓</p>
    </div>
    <p class="arrow" draggable="true" data="5" position="1" pid="2">↓</p>
  </div>
  <p class="arrow" draggable="true" data="2" position="1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="3" datatype="0" id="3" position="2" pid="0">
      <div>
        <p style="margin-top: 2px">提取结果</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="2" data="3" pid="0">↓</p>
  </div>
</div>
~~~

**嵌套示例，第 6 次追加：内层点击。**

~~~js
$("#5").append(newNode(nodeList[6]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="loop clk" data="2" draggable="true" datatype="1" id="2" position="1" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">外层循环</p>
    <p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
    <div class="sequence">
      <div class="node clk" draggable="true" data="4" datatype="0" id="4" position="0" pid="2">
        <div>
          <p style="margin-top: 2px">点击按钮</p>
        </div>
      </div>
      <p class="arrow" draggable="true" position="0" data="4" pid="2">↓</p>
    </div>
    <div class="loop clk" data="5" draggable="true" datatype="1" id="5" position="1" pid="2">
      <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">内层循环</p>
      <p class="arrow" draggable="true" position="-1" data="5" pid="5">↓</p>
      <div class="sequence">
        <div class="node clk" draggable="true" data="6" datatype="0" id="6" position="0" pid="5">
          <div>
            <p style="margin-top: 2px">点击内层按钮</p>
          </div>
        </div>
        <p class="arrow" draggable="true" position="0" data="6" pid="5">↓</p>
      </div>
    </div>
    <p class="arrow" draggable="true" data="5" position="1" pid="2">↓</p>
  </div>
  <p class="arrow" draggable="true" data="2" position="1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="3" datatype="0" id="3" position="2" pid="0">
      <div>
        <p style="margin-top: 2px">提取结果</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="2" data="3" pid="0">↓</p>
  </div>
</div>
~~~

截图里两层框都使用 .loop，内部内容使外层框自然撑高：

![两个循环容器按父子关系嵌套，内层动作追加进内层容器](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%B8%B2%E6%9F%93-06-%E4%B8%A4%E5%B1%82%E5%BE%AA%E7%8E%AF.png)

### 14. 判断与分支：分支追加到 judge，动作追加到分支内部

为看清横向布局，这里换成一份独立的六节点输入，编号从 0 重新开始，不与五节点图或十三节点房源图混用：

~~~js
nodeList = [
  makeNode(0, "root",       0, -1, [1]),
  makeNode(1, "是否单间",   9,  2, [2,3]),
  makeNode(2, "单间分支",  10,  3, [4,5]),
  makeNode(3, "空兜底分支",10,  3),
  makeNode(4, "点击房源",   2,  0),
  makeNode(5, "提取信息",   3,  0)
];
refresh();
~~~

这份输入的 actionSequence=[0,1,2,3,4,5]，界面 id 与存储下标恰好相同。判断模板的外框没有把 id 放在最外层，而是放在内部的 .judge 容器；分支模板也把 id 放在内部动作容器：

~~~html
<!-- 判断片段：分支要追加到 #1 -->
<div class="loop clk" draggable="true" dataType="2" data="1" position="0" pId="0">
  <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">是否单间</p>
  <p class="branchAdd" data="1">点击此处在最右边增加条件分支</p>
  <div class="judge" id="1"></div>
</div>
<p class="arrow" draggable="true" data="1" position="0" pId="0">↓</p>

<!-- 单间分支片段：动作要追加到 #2 -->
<div class="branch clk" dataType="3" data="2" position="0" pId="1">
  <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">单间分支</p>
  <p data="2" class="arrow" draggable="true" position="-1" pId="2">↓</p>
  <div id="2"></div>
</div>
~~~

下面重新从只有开始标记和首箭头的 #0 出发，逐次追加，不预先生成分支内部动作：

**判断示例，第 1 次追加：判断外框，建立 judge #1。**

~~~js
$("#0").append(newNode(nodeList[1]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="loop clk" draggable="true" datatype="2" data="1" position="0" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">是否单间</p>
    <p class="branchAdd" data="1">点击此处在最右边增加条件分支</p>
    <div class="judge" id="1"></div>
  </div>
  <p class="arrow" draggable="true" data="1" position="0" pid="0">↓</p>
</div>
~~~

**判断示例，第 2 次追加：单间分支，建立动作容器 #2。**

~~~js
$("#1").append(newNode(nodeList[2]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="loop clk" draggable="true" datatype="2" data="1" position="0" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">是否单间</p>
    <p class="branchAdd" data="1">点击此处在最右边增加条件分支</p>
    <div class="judge" id="1">
      <div class="branch clk" datatype="3" data="2" position="0" pid="1">
        <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">单间分支</p>
        <p data="2" class="arrow" draggable="true" position="-1" pid="2">↓</p>
        <div id="2"></div>
      </div>
    </div>
  </div>
  <p class="arrow" draggable="true" data="1" position="0" pid="0">↓</p>
</div>
~~~

**判断示例，第 3 次追加：空兜底分支，建立 #3。**

~~~js
$("#1").append(newNode(nodeList[3]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="loop clk" draggable="true" datatype="2" data="1" position="0" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">是否单间</p>
    <p class="branchAdd" data="1">点击此处在最右边增加条件分支</p>
    <div class="judge" id="1">
      <div class="branch clk" datatype="3" data="2" position="0" pid="1">
        <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">单间分支</p>
        <p data="2" class="arrow" draggable="true" position="-1" pid="2">↓</p>
        <div id="2"></div>
      </div>
      <div class="branch clk" datatype="3" data="3" position="1" pid="1">
        <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">空兜底分支</p>
        <p data="3" class="arrow" draggable="true" position="-1" pid="3">↓</p>
        <div id="3"></div>
      </div>
    </div>
  </div>
  <p class="arrow" draggable="true" data="1" position="0" pid="0">↓</p>
</div>
~~~

**判断示例，第 4 次追加：点击进入单间分支。**

~~~js
$("#2").append(newNode(nodeList[4]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="loop clk" draggable="true" datatype="2" data="1" position="0" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">是否单间</p>
    <p class="branchAdd" data="1">点击此处在最右边增加条件分支</p>
    <div class="judge" id="1">
      <div class="branch clk" datatype="3" data="2" position="0" pid="1">
        <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">单间分支</p>
        <p data="2" class="arrow" draggable="true" position="-1" pid="2">↓</p>
        <div id="2">
          <div class="sequence">
            <div class="node clk" draggable="true" data="4" datatype="0" id="4" position="0" pid="2">
              <div>
                <p style="margin-top: 2px">点击房源</p>
              </div>
            </div>
            <p class="arrow" draggable="true" position="0" data="4" pid="2">↓</p>
          </div>
        </div>
      </div>
      <div class="branch clk" datatype="3" data="3" position="1" pid="1">
        <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">空兜底分支</p>
        <p data="3" class="arrow" draggable="true" position="-1" pid="3">↓</p>
        <div id="3"></div>
      </div>
    </div>
  </div>
  <p class="arrow" draggable="true" data="1" position="0" pid="0">↓</p>
</div>
~~~

**判断示例，第 5 次追加：提取进入单间分支。**

~~~js
$("#2").append(newNode(nodeList[5]));
~~~

执行后，#0 的完整 HTML：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="loop clk" draggable="true" datatype="2" data="1" position="0" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">是否单间</p>
    <p class="branchAdd" data="1">点击此处在最右边增加条件分支</p>
    <div class="judge" id="1">
      <div class="branch clk" datatype="3" data="2" position="0" pid="1">
        <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">单间分支</p>
        <p data="2" class="arrow" draggable="true" position="-1" pid="2">↓</p>
        <div id="2">
          <div class="sequence">
            <div class="node clk" draggable="true" data="4" datatype="0" id="4" position="0" pid="2">
              <div>
                <p style="margin-top: 2px">点击房源</p>
              </div>
            </div>
            <p class="arrow" draggable="true" position="0" data="4" pid="2">↓</p>
          </div>
          <div class="sequence">
            <div class="node clk" draggable="true" data="5" datatype="0" id="5" position="1" pid="2">
              <div>
                <p style="margin-top: 2px">提取信息</p>
              </div>
            </div>
            <p class="arrow" draggable="true" position="1" data="5" pid="2">↓</p>
          </div>
        </div>
      </div>
      <div class="branch clk" datatype="3" data="3" position="1" pid="1">
        <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">空兜底分支</p>
        <p data="3" class="arrow" draggable="true" position="-1" pid="3">↓</p>
        <div id="3"></div>
      </div>
    </div>
  </div>
  <p class="arrow" draggable="true" data="1" position="0" pid="0">↓</p>
</div>
~~~


两条分支同属 #1，因此按分支模板横向排列；单间分支里的两个动作同属 #2，继续竖向排列：

![判断内的两个横向分支与单间分支中的竖向动作](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%B8%B2%E6%9F%93-07-%E5%88%A4%E6%96%AD%E4%B8%8E%E6%A8%AA%E5%90%91%E5%88%86%E6%94%AF.png)

截图中空分支较短，靠下排列，这是原 .branch 使用 inline-block 默认基线对齐的结果；后面的 CSS 小节会具体解释。

---

## 第四部分：画出来之后，把交互接回去

### 15. 默认锚点怎样设置，为什么有 refresh(false)

编号结束、追加节点之前，原函数执行：

~~~js
if (nowArrowReset) {
  app._data.nowArrow = {
    position: nodeList[0].sequence.length - 1,
    pId: 0,
    num: 0
  };
}
~~~

**默认箭头放在全局流程的最后面，即 root 最后一个孩子之后。** 五节点图 root.sequence=[1,4,3]，所以 position=2、pId=0，地址是 root 最后一个孩子“提取结果”之后；空图 length=0，才得到 position=-1。源码旁边“最开头处”的注释与表达式不一致，这里按实际计算结果理解。

调用形式如下：

~~~js
refresh();      // 默认参数 true，重置到 root 末尾
refresh(false); // 保留调用方已设置的 nowArrow
~~~

这条 nowArrow 赋值本身只改变状态，不新增标签。本教学页没有 Vue 监听器，所以此步骤的 #0 仍是编号结束时的 HTML。原程序另有 nowArrow 的 Vue watch，会把匹配箭头的背景设为 lavender；在五节点图完整绘制后，目标是 root 末尾箭头，相关元素会变为：

~~~html
<p class="arrow" draggable="true" position="2" data="3" pid="0" style="background-color: lavender;">↓</p>
~~~

这里改变的是该箭头的 style；方块与容器的父子结构保持不变。

新增逻辑还可能在 refresh 返回后，把锚点改到新循环内部或新节点后面。锚点是界面插入地址，不是执行器即将运行的节点。

### 16. 为什么重新绑定事件，具体绑了哪些函数

empty 已删除旧方块与箭头，新 HTML 是新的元素。**原先绑定在旧元素上的事件不会自动移到新元素上，所以 refresh 最后调用 bindEvents**。下面是完整原函数：

~~~js
function bindEvents() {
    // 清空原来的listener然后再添加新的listener
    //以下绑定了左右键的行为
    let rect = document.getElementsByClassName('clk');
    for (let i = 0, rule; rule = rect[i++];) {
        rule.removeEventListener('mousedown', elementMousedown);
        rule.addEventListener('mousedown', elementMousedown);
        rule.removeEventListener('click', elementClick);
        rule.addEventListener('click', elementClick);
        rule.removeEventListener('dblclick', elementDblClick);
        rule.addEventListener('dblclick', elementDblClick);
        rule.removeEventListener('dragend', elementDragEnd);
        rule.addEventListener('dragend', elementDragEnd);
    }
    let arr = document.getElementsByClassName('arrow');
    for (let i = 0, rule; rule = arr[i++];) {
        rule.removeEventListener('click', arrowClick);
        rule.addEventListener('click', arrowClick);
        rule.removeEventListener('mousedown', arrowMouseDown);
        rule.addEventListener('mousedown', arrowMouseDown);
        rule.removeEventListener('dblclick', arrowDblClick);
        rule.addEventListener('dblclick', arrowDblClick);
        rule.removeEventListener('dragover', arrowDragOver);
        rule.addEventListener('dragover', arrowDragOver);
        rule.removeEventListener('dragend', arrowDragEnd);
        rule.addEventListener('dragend', arrowDragEnd);
    }
    let branch = document.getElementsByClassName('branchAdd');
    for (let i = 0, rule; rule = branch[i++];) {
        rule.removeEventListener('click', branchClick);
        rule.addEventListener('click', branchClick);
    }
    let options = document.getElementsByClassName("options");
    for (let i = 0, rule; rule = options[i++];) {
        rule.removeEventListener('dragend', optionDragEnd);
        rule.addEventListener('dragend', optionDragEnd);
    }
}
~~~

| 选择器 | 对应元素 | 主要事件 |
| --- | --- | --- |
| .clk | root、动作、循环和分支等可选择区域 | mousedown、click、dblclick、dragend |
| .arrow | 插入箭头 | click、mousedown、dblclick、dragover、dragend |
| .branchAdd | 判断框中“增加条件分支”的文字 | click |
| .options | 工具箱选项 | dragend |

在教学页里，五节点图追加完毕，再执行 bindEvents 后，HTML 仍是下面这样。监听器保存在 DOM 的事件机制中，不会序列化成 onclick 属性：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="loop clk" data="2" draggable="true" datatype="1" id="2" position="1" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">循环</p>
    <p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
    <div class="sequence">
      <div class="node clk" draggable="true" data="4" datatype="0" id="4" position="0" pid="2">
        <div>
          <p style="margin-top: 2px">点击按钮</p>
        </div>
      </div>
      <p class="arrow" draggable="true" position="0" data="4" pid="2">↓</p>
    </div>
  </div>
  <p class="arrow" draggable="true" data="2" position="1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="3" datatype="0" id="3" position="2" pid="0">
      <div>
        <p style="margin-top: 2px">提取结果</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="2" data="3" pid="0">↓</p>
  </div>
</div>
~~~

`rule.removeEventListener('click', elementClick)` 只移除对应函数的监听器，再 add 同一个函数，避免重复累积。这里没有直接使用 `onclick="..."`，而是生成 DOM 后统一绑定。

### 17. 点中方块：从 DOM 的 data 回到节点对象

普通方块的 click 入口来自源码：

~~~js
function elementClick(e) {
  operationChange(e, this);
  e.stopPropagation();
}
~~~

这里 this 是被点击的 DOM 元素。operationChange 中与本例直接有关的几句，按原顺序摘出为：

~~~js
nowNode = theNode;
vueData.nowNodeIndex = actionSequence[theNode.getAttribute("data")];
theNode.style.borderColor = "blue";
handleElement();
~~~

点中循环里的点击方块时，data="4"，actionSequence[4]=2，因此参数面板最终读 nodeList[2]。把边框改为蓝色能标出当前选择；stopPropagation 避免点击孩子时继续冒泡，把父循环也当成此次选择。

点中内部点击方块后，#0 的完整 HTML 如下；变化位于 id="4" 方块新增的 style="border-color: blue;"：

~~~html
<div id="0" class="clk" data="0">
  <div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
    <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
  </div>
  <p id="firstArrow" class="arrow" position="-1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="1" datatype="0" id="1" position="0" pid="0">
      <div>
        <p style="margin-top: 2px">打开网页</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="0" data="1" pid="0">↓</p>
  </div>
  <div class="loop clk" data="2" draggable="true" datatype="1" id="2" position="1" pid="0">
    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">循环</p>
    <p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
    <div class="sequence">
      <div class="node clk" draggable="true" data="4" datatype="0" id="4" position="0" pid="2" style="border-color: blue;">
        <div>
          <p style="margin-top: 2px">点击按钮</p>
        </div>
      </div>
      <p class="arrow" draggable="true" position="0" data="4" pid="2">↓</p>
    </div>
  </div>
  <p class="arrow" draggable="true" data="2" position="1" pid="0">↓</p>
  <div class="sequence">
    <div class="node clk" draggable="true" data="3" datatype="0" id="3" position="2" pid="0">
      <div>
        <p style="margin-top: 2px">提取结果</p>
      </div>
    </div>
    <p class="arrow" draggable="true" position="2" data="3" pid="0">↓</p>
  </div>
</div>
~~~

下面截图由教学页触发同一方块的教学点击处理器，显示蓝色选择边框和编号转换日志：

![点中内部动作后，用 data 与 actionSequence 找到存储对象](/resources/easyspider/%E5%9B%BE%E7%89%87/Flowchart/%E6%B8%B2%E6%9F%93-08-%E7%82%B9%E5%87%BB%E6%96%B9%E5%9D%97%E4%B8%8E%E4%BA%8B%E4%BB%B6.png)

**点击操作后参数栏变成什么、为什么能修改参数、修改后为什么能保存，集中见第 20 讲的[Vue 参数栏完整链路](/easyspider/chapter-20#vue-parameter-panel)。** 本讲讲到 DOM 如何定位节点；下一讲继续追踪 handleElement、v-if、v-model、watch，再接上保存与恢复。截图教学页只显示地址日志，不执行采集或试运行。

### 18. 点中箭头：先记插入地址，再交给工具箱逻辑

箭头点击函数完整代码如下：

~~~js
function arrowClick(e) {
  if (option != 0) {
    app._data.nowArrow = {
      position: this.getAttribute('position'),
      pId: this.getAttribute('pId'),
      num: 0
    };
  }
  toolBoxKernel(e);
}
~~~

读取箭头属性、写入 nowArrow 本身不追加 HTML。以循环内首箭头为例，它原有的结构仍然是：

~~~html
<p class="arrow" draggable="true" position="-1" data="2" pid="2">↓</p>
~~~

在原程序 Vue 的锚点高亮监听执行后，这个目标箭头会带上背景色，其他父子结构保持不变：

~~~html
<p class="arrow" draggable="true" position="-1" data="2" pid="2" style="background-color: lavender;">↓</p>
~~~

至于 toolBoxKernel 是否继续新增、移动或删除节点，由当时选择的 option 决定，不能把所有箭头点击都说成 HTML 不变。

只有已经选择工具箱操作、option!=0 时，这条路径才把箭头的 position/pId 记作锚点。以循环内首箭头为例，pId=2、position=-1；随后可通过 actionSequence[2]=4 找到循环对象，向它的 sequence 开头插入。新增与移动具体怎样 splice，见第 20 讲。

---

## 第五部分：稍微读一点 CSS，解释截图为什么长这样

下面修改样式表中的 CSS 规则，只改变浏览器对现有标签的排版和绘制，不会给 #0 添加新标签。每段 CSS 对应的 HTML 仍是前面已列出的动作、循环或判断快照；只有通过 JavaScript 设置 element.style 时，序列化 HTML 中才会出现对应的行内 style 变化。

### 19. 普通动作为什么是蓝色方块，箭头为什么单独占一行

以下规则节选自 [FlowChart.css](/source/?file=4f024983a7438a6f3a.css)，省去注释、已被后面覆盖的颜色声明及与本节无关的规则，保留本节相关的有效样式：

~~~css
div.node {
  height: 45px;
  width: 180px;
  border-radius: 7px;
  border: #007bff solid;
  border-color: transparent;
  background: rgb(10, 120, 200);
  color: white;
  text-align: center;
  padding: 5px;
  margin: 10px auto;
}
.sequence { display: block; }
.arrow {
  margin: 10px auto;
  text-align: center;
  font-size: 23px !important;
  color: black;
}
div.node:hover {
  cursor: pointer;
  background: navy;
}
.arrow:hover {
  background-color: deepskyblue !important;
  cursor: pointer;
  color: white;
}
~~~

180px/45px 给动作固定尺寸，蓝色 background 与白字产生截图中的动作块；border-radius 让四角变圆。`margin:10px auto` 在块级排版中提供上下间距、左右自动居中。透明边框预先占据空间，选中时只换边框颜色，方块尺寸不会因此改变。

包装层 .sequence 为 block；箭头本身是 p 元素，也按块级元素排版，所以方块和后置箭头自然上下排列。箭头是实际字符“↓”，不是 canvas 绘制的线段，也没有为每条连线计算起点和终点坐标。

### 20. 循环框为什么能包住孩子，并随嵌套自动变高

~~~css
.loop {
  border: rgb(10, 120, 200) solid;
  border-color: deepskyblue;
  text-align: center;
  padding: 5px;
  width: 90%;
  min-width: 150px;
  overflow: auto;
  margin: 10px auto;
  border-radius: 7px;
}
~~~

width:90% 让循环框相对父容器缩进，边框标出包含范围；padding 是框内留白，margin 是框外间距。.loop 没写固定 height，点击动作追加到它内部后，浏览器根据内容重新排版，循环框随之变高。两层循环继续相对各自父容器取宽度，所以截图里内层更窄。

DOM 的嵌套先决定“属于哪个框”，CSS 再决定“框多宽、边框什么颜色”。只给点击添加蓝色边框，不能让它自动成为循环的孩子；必须先 append 到正确父容器。

### 21. 判断分支为什么横排，空分支为什么靠下

~~~css
.judge {
  text-align: center;
  padding: 5px;
  width: 100%;
  min-width: 150px;
  margin: 10px auto;
  justify-content: center;
  border-radius: 7px;
}
.branch {
  display: inline-block;
  border: deepskyblue solid;
  text-align: center;
  padding: 5px;
  width: 300px;
  min-width: 150px;
  margin: 10px;
  border-radius: 7px;
}
~~~

真正让两个 branch 能放在同一行的是 `display:inline-block`；每个分支内部依然包含块级动作包装层，所以分支内部是竖排。容器够宽时两条分支同排，宽度不足时会换行。

原 .judge 的 display:flex 被注释掉了，所以这里不能把横排归因于 Flex 布局；`justify-content:center` 也没有在当前普通块布局中提供 Flex 居中效果。当前水平居中主要由父容器 text-align:center 与分支 inline-block 配合完成。

inline-block 默认按基线对齐，原 .branch 没设 vertical-align。因此截图里短的空兜底分支比长分支更靠下。可以在开发者工具临时做下面的样式实验：

~~~css
/* 教学实验：原样式文件没有这一条。 */
.branch { vertical-align: top; }
~~~

两条分支会顶部对齐，但它们的父子结构、sequence 和 actionSequence 都不改变。截图保留原始样式，未应用这条实验规则。

### 22. Bootstrap 和行内样式也会影响结果

FlowChart.css 开头还有：

~~~css
* {
  margin: 0;
  padding: 0;
  font-size: 17px !important;
}
~~~

普通文字默认 17px，而 .arrow 的字号用更具体的选择器和 !important 设置成 23px。循环标题的灰底与左对齐写在 newNode 的行内 style 中；开始/结束圆形的尺寸、边框也写在 HTML 的 style 中。

原页面先加载 Bootstrap，再加载 FlowChart.css。Bootstrap 的 `box-sizing:border-box` 使方块声明的宽高包含内边距与边框。复现截图时应保留两份样式的加载顺序，只复制 .node 一段可能出现尺寸和间距差异。

---

## 第六部分：把各步骤接回完整 refresh，再亲手切换示例

### 23. 完整 refresh：对应前面每一步代码

下面保留原函数，前文已经依次解释其中各段。注意锚点那行的原注释写“最开头处”，其实际表达式指向 root 末尾：

~~~js
function refresh(nowArrowReset = true) {
    $("#0").empty();
    $("#0").append(`<div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
                        <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
                        </div>
                        <p id="firstArrow" class="arrow" position=-1 pId=0>↓</p>`);
    actionSequence.splice(0);
    queue.splice(0);
    let idd = 1;
    queue.push(0);
    actionSequence.push(0);
    while (queue.length != 0) {
        let nd = queue.shift(); //取出父元素并建立对子元素的链接
        for (let i = 0; i < nodeList[nd].sequence.length; i++) {
            nodeList[nodeList[nd].sequence[i]].parentId = nodeList[nd].id;
            nodeList[nodeList[nd].sequence[i]]["position"] = i;
            nodeList[nodeList[nd].sequence[i]].id = idd++;
            //检测元素是否位于循环内
            if (nodeList[nd].option == 8 || nodeList[nd].isInLoop) {
                nodeList[nodeList[nd].sequence[i]].isInLoop = true;
            } else {
                nodeList[nodeList[nd].sequence[i]].isInLoop = false;
            }
            queue.push(nodeList[nd].sequence[i]);
            actionSequence.push(nodeList[nd].sequence[i]);
        }
    }
    if (nowArrowReset) //如果要重置锚点位置
    {
        app._data.nowArrow = {"position": nodeList[0].sequence.length - 1, "pId": 0, "num": 0}; //设置默认要添加的位置是元素流程最开头处
    }
    //第一个元素不渲染
    for (let i = 1; i < actionSequence.length; i++) {
        let parentId = nodeList[actionSequence[i]]["parentId"];
        $("#" + parentId).append(newNode(nodeList[actionSequence[i]]));
    }
    bindEvents();
}
~~~

| 执行段 | 读取什么 | 改变什么 |
| --- | --- | --- |
| empty 与开始标记 append | 静态画布 #0 | 重建开始标记与首箭头 |
| BFS | 各节点的 sequence 与父节点状态 | 可达节点的 id、parentId、position、isInLoop，以及两个辅助数组 |
| 默认锚点 | root 的孩子数量 | nowArrow，除非传入 false |
| newNode 与 append | actionSequence、type、title、定位字段 | 业务节点和箭头的 DOM |
| bindEvents | 新生成元素的 class | 事件监听器 |

refresh 不重排 nodeList，不改写 sequence，也不调用 Selenium 执行业务动作。Vue 管理配置状态，当前画布的节点 HTML 由 jQuery 重建。循环执行十轮，设计器仍只画一个循环框。

### 24. 打开教学页，对照代码、DOM 和截图

直接用浏览器打开[渲染机制-演示.html](/resources/easyspider/%E7%A4%BA%E4%BE%8B-Flowchart/%E6%B8%B2%E6%9F%93%E6%9C%BA%E5%88%B6-%E6%BC%94%E7%A4%BA.html)，页面下方会实时显示本步骤 #0 的完整 HTML。选择第 0～6 次追加，或点击方块后，HTML 会同步更新。可切换空图、顺序、循环、两层循环、判断，并查看前几次 append 的中间结果。中间状态只截取 HTML 追加过程，BFS 编号已经完成；原 refresh 正常运行时不会暂停。

建议依次操作：

1. 切到五节点循环图，只显示前两次 append，确认空循环框已经存在。
2. 显示前三次 append，确认提取在循环外。
3. 显示全部，确认点击追加到 #2 内部。
4. 点中点击方块，核对 data=4 → actionSequence[4]=2 → nodeList[2]。
5. 打开开发者工具，在 Elements 中展开 #0、#2，确认 DOM 的实际父子关系。
6. 在 Styles 中临时修改 .loop 的 width、.branch 的 vertical-align，观察外观与层次的分工。

教学页使用的两个原函数放在[渲染机制-源码片段.js](/source/?file=eded6a6f72b5510ba6.js)。若源码发生变化，可在仓库根目录重新提取；截图脚本仅使用 Python 标准库，自动查找本机 Chrome/Edge：

~~~powershell
python "Docs/讲义/示例-Flowchart/生成渲染演示.py"
python "Docs/讲义/示例-Flowchart/生成渲染演示.py" --screenshots
python "Docs/讲义/示例-Flowchart/生成渲染演示.py" --html-snapshots
~~~

[生成脚本](/source/?file=d427c25bd7823c603e.py) 用独立临时浏览器配置生成八张截图，或导出[各步骤的 HTML 快照数据](/source/?file=bb2965f45151b6d56e.json)，不依赖采集服务、目标网站或已打开的浏览器会话。

---

## 进阶：再手算完整房源图

已经走完前面的渲染示例后，再用第 15 篇的十三节点房源教学模型训练 BFS。以下编号独立于前面的五节点、七节点与六节点示例。


### 先准备输入

回到第 15 篇的完整房源树。先以页面循环这行输入为例：5→[6,12] 表示节点 5（页面循环）的直接孩子依次为 6（房源循环）和 12（点击下一页），不是一条“5 跳到 6 或 12”的任选边。

初始 queue=[0] 表示还没展开 root 的孩子；actionSequence=[0] 表示已经把根的界面 id=0 对应到数组位置 0；idd=1 表示下一个孩子将获得 id=1。

原对象可能带着上一次保存的 id。可达节点的编号会在发现时被覆盖，因此不必先按旧 id 排序，更不能先根据旧 id 去重。下面准备的数据只依赖稳定数组位置和 sequence。

~~~text
0 → [1,2]
2 → [3,4,5]
5 → [6,12]
6 → [7]
7 → [8,9]
8 → [10,11]
其他项 → []
~~~

初始：

~~~text
queue=[0]
actionSequence=[0]
idd=1
~~~

所有表格中的队列数字都是 **index**；“发出的编号”才是 **id**。

### 十三轮完整记录

现在一次 while 迭代只看一个父节点。特别注意：从队列取出父节点时，它一般已经在更早的“被发现”阶段得到 id；本轮主要给它的孩子编号。

例如 nd=5 时，页面循环自己早已拿到 id=5。它的第一个孩子 6（房源循环）获得 id=6，第二个孩子 12（下一页）获得 id=7。下一轮展开房源循环 6，才给判断 7 发 id=8。

因此后面表格里的“发出的 id”写成“存储下标→界面编号”。它不是执行跳转，也不是把对象搬到新数组位置。为了看懂每轮，应同时看本轮取出谁、又把谁留在队列里。

| 本轮取出 nd（存储下标与操作） | 本轮发现的孩子 | 孩子获得的界面 id | 本轮结束后的 queue |
| --- | --- | --- | --- |
| 0（root） | 1（打开网页）、2（地区循环） | 1（打开网页）→id=1；2（地区循环）→id=2 | [1（打开网页）, 2（地区循环）] |
| 1（打开网页） | 无 | 无 | [2（地区循环）] |
| 2（地区循环） | 3（输入地区）、4（点击搜索）、5（页面循环） | 3（输入地区）→id=3；4（点击搜索）→id=4；5（页面循环）→id=5 | [3（输入地区）, 4（点击搜索）, 5（页面循环）] |
| 3（输入地区） | 无 | 无 | [4（点击搜索）, 5（页面循环）] |
| 4（点击搜索） | 无 | 无 | [5（页面循环）] |
| 5（页面循环） | 6（房源循环）、12（点击下一页） | 6（房源循环）→id=6；12（点击下一页）→id=7 | [6（房源循环）, 12（点击下一页）] |
| 6（房源循环） | 7（判断） | 7（判断）→id=8 | [12（点击下一页）, 7（判断）] |
| 12（点击下一页） | 无 | 无 | [7（判断）] |
| 7（判断） | 8（单间分支）、9（兜底分支） | 8（单间分支）→id=9；9（兜底分支）→id=10 | [8（单间分支）, 9（兜底分支）] |
| 8（单间分支） | 10（点击房源）、11（提取信息） | 10（点击房源）→id=11；11（提取信息）→id=12 | [9（兜底分支）, 10（点击房源）, 11（提取信息）] |
| 9（兜底分支） | 无 | 无 | [10（点击房源）, 11（提取信息）] |
| 10（点击房源） | 无 | 无 | [11（提取信息）] |
| 11（提取信息） | 无 | 无 | [] |

“12→7”的意思是 `nodeList[12].id=7`。

关键两轮放慢看。

扩展页面循环 5：

~~~text
先发现孩子 6：
    parentId=5，position=0，id=6，isInLoop=true
再发现孩子 12：
    parentId=5，position=1，id=7，isInLoop=true

queue=[6,12]
~~~

扩展房源循环 6：

~~~text
发现孩子 7：
    parentId=6，position=0，id=8，isInLoop=true

原队尾还有 12
所以 queue=[12,7]
~~~

因此 12 的编号比判断 7 小。它们的实际执行先后仍由第 16 篇的容器递归决定。

### isInLoop 为什么能一层层传下去

先沿一条祖先链手算：地区循环 2 本身位于 root 下，所以它的 isInLoop=false；它的孩子页面循环 5 有循环父亲，变成 true；判断 7、分支 8 虽然不是循环，但处于更深的循环体中，也应为 true。

| 当前父节点 | 父 option 是不是 8 | 父 isInLoop | 孩子的结果 |
| --- | --- | --- | --- |
| root 0 | 否 | false | 地区循环 2 为 false |
| 地区循环 2 | 是 | false | 输入 3、搜索 4、页面循环 5 为 true |
| 房源循环 6 | 是 | true | 判断 7 为 true |
| 判断 7 | 否 | true | 单间分支 8、兜底 9 为 true |
| 单间分支 8 | 否 | true | 点击 10、提取 11 为 true |

这就是代码用“父本身是循环，或者父已经在循环内”两个条件的原因。若只检查父 option=8，判断里的点击和提取就会漏掉循环标记。这个布尔标记便于界面显示“使用循环项”等选项；当前究竟是哪个网页元素，仍要靠运行时 loopValue、loopPath、index 传递。

源码检查父节点：

~~~js
parent.option == 8 || parent.isInLoop
~~~

两种情况：

~~~text
父本身是循环：
    孩子就在循环内
父不是循环，但父已经在循环内：
    孩子也在循环内
~~~

于是判断、条件分支、点击与提取都能继承“在某个循环内”。

它只记录布尔值，不记录“最近的循环具体是节点几”。真正执行上下文仍由递归参数传入。

### 同级顺序从哪里来

换一个可以观察结果的参数实验：只把页面循环的孩子从 [6,12] 改成 [12,6]，即把“点击下一页”调到“房源循环”前面。

刷新时，两者仍属于页面循环，但发现顺序互换：下一页 12 先拿 id=6，房源循环 6 后拿 id=7。正式执行时也会每轮先点击下一页，再处理翻页后的房源，当前第一页可能被跳过。

这说明同级顺序保存在 sequence；BFS 是按这个顺序读取它，并把不同层的节点统一编号。读上面的十三轮 BFS 表时，不要把跨层发现顺序当作完整业务执行顺序。

`for` 从 `sequence[0]` 开始遍历，所以：

~~~text
root 的 1 在 2 前；
页面循环的 6 在 12 前；
判断里的 8 在 9 前。
~~~

BFS 保留每个容器内部的孩子顺序，只把不同深度的节点按层排入编号映射。

---


练习：回到五节点基准图，把循环 4 的孩子 2 移回 root，成为 root 的最后一个孩子。结果为 0.sequence=[1,4,3,2]、4.sequence=[]；刷新后 actionSequence 仍为 [0,1,4,3,2]，但点击的 parentId 从 2 变为 0，position 从 0 变为 3，isInLoop 从 true 变为 false，HTML 改为 append 到 #0。同一张编号表也可能对应不同层次，关系仍必须读取 sequence。

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[18.流程图核心数据结构：稳定下标与界面编号](/easyspider/chapter-18) ｜ 下一篇：[20.流程图的增删改查：从读取节点到修改孩子列表](/easyspider/chapter-20)
