---
title: "20 · 流程图增删改查"
description: "easyspider · 流程图与执行 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/20.流程图的增删改查.md"
originalUrl: "/originals/easyspider/chapter-20.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 20.流程图的增删改查：Vue 参数栏与孩子列表的修改

> 已经能从 root 搭出数据，也能把数据画成图。
>
> 本篇先在同一份五节点图上讲清查询、Vue 参数区域切换、调整锚点，再完成新增、移动和删除，之后展开判断、复制与完整房源任务。
>
> 这些操作可以从界面工具箱发起；暂时不需要消息。第 21 讲才把消息接到这些入口上。

---

**想找“点一个操作，右侧为什么变、参数为什么能改、改完为什么能保存”，直接看本篇的[Vue 参数栏完整链路](#vue-parameter-panel)。** 这一节从选择节点讲到参数写回，再接上保存和重新加载；第 23 讲继续展开请求与磁盘文件。

## 基础练习：对五节点图连续做一轮增删改查

### 查：点到一个方块，怎样找到对象与父容器

从第 15 篇构建、第 19 讲渲染的五节点基准图开始：

~~~text
0 root、1 打开网页、2 点击按钮、3 提取结果、4 循环
0.sequence = [1,4,3]
4.sequence = [2]
actionSequence = [0,1,4,3,2]
~~~

点击按钮的 DOM 携带 data=4。直接访问 nodeList[4] 会读到循环；正确查法是先把界面 id 翻译成稳定下标：

~~~js
const index = actionSequence[4]; // 2
const node = nodeList[index];    // 点击按钮
const parent = nodeList[actionSequence[node.parentId]]; // 循环 4
const childIndex = parent.sequence[node.position];       // 2
~~~

若本来就持有稳定下标 2，可以直接读 nodeList[2]，无需绕回界面编号。查整个流程的层次，要从 nodeList[0] 的 sequence 展开；仅扫描对象数组不能得到父子关系和动作先后。

真实点击入口在 [FlowChart.js](/source/?file=48b61e5e4ebaa6ccf2.js) 的 operationChange：

~~~js
vueData.nowNodeIndex = actionSequence[theNode.getAttribute("data")];
handleElement();
~~~

[logic.js](/source/?file=786aaf2ec8ee7dbd78.js) 的 handleElement 再让配置面板指向它：

~~~js
app._data["nowNode"] = nodeList[vueData.nowNodeIndex];
app._data["nodeType"] = app._data["nowNode"]["option"];
~~~

所以“查”既包括拿节点参数，也包括查它属于哪个父容器、位于父 sequence 的哪个位置。

<a id="vue-parameter-panel"></a>

### Vue 参数栏完整链路：点击操作 → 切换表单 → 修改参数 → 保存与恢复

前面两句 handleElement 只是入口。现在把“点击方块 → 找到对象 → 切换参数区域 → 修改原对象 → 保存 → 重新加载”完整走一遍，仍用本节尚未修改结构的五节点图，actionSequence=[0,1,4,3,2]。这里点击的是流程图中的已有方块；工具箱里的“新增点击”等按钮走后面的新增入口。

**参数栏显示的是当前节点的数据；编辑会写回 nodeList 中的节点，保存任务再把这份 nodeList 写入文件。** 先记住这条主线，再分别看每一步由谁完成：

| 用户看到的动作 | 实际机制 | 关键源码 |
| --- | --- | --- |
| 点中一个操作，参数栏换了 | 找到节点，设置 nowNode、nodeType，Vue 按 v-if 显示表单 | FlowChart.js 的 operationChange；logic.js 的 handleElement |
| 输入框显示该操作原来的值 | v-model 从绑定的数据读取值 | FlowChart_CN.html 的参数控件 |
| 改数字、XPath、循环类型 | v-model 直接写节点，或经 watch、change 方法写回 | FlowChart.js 的 watch、methods |
| 切到别的节点，再切回来仍是新值 | 改动已经留在原节点对象中 | nodeList[index].parameters |
| 保存、关闭、重新打开后仍是新值 | graph=nodeList 被序列化并写盘，加载后重新绑定 | logic.js 的 saveService、加载回调；server.js 的任务接口 |

**先分清几个名字相近的状态。** FlowChart.js 用 `new Vue({el:'#app', ...})` 管理右侧参数区域。相关 data 配置摘录如下，省去其他配置项：

~~~js
// 外部共享的当前存储下标
let vueData = {nowNodeIndex: 0};

// new Vue 的 data 配置中的相关字段
data: {
  list: {nl: nodeList},
  index: vueData,
  nodeType: 0,
  nowNode: null,
  loopType: -1,
  xpath: "",
  nowArrow: {position: -1, pId: 0, num: 0}
}
~~~

| 状态 | 存什么 | 点中点击按钮时 |
| --- | --- | --- |
| 全局 nowNode | 被选中的 DOM 元素 | 画布上 data="4" 的方块 |
| vueData.nowNodeIndex | 选中对象的稳定存储下标 | 2 |
| app._data.nowNode | 选中的节点数据对象 | nodeList[2] 本身 |
| app._data.nodeType | 当前操作的 option，用来选择参数区域 | 2，表示点击操作 |
| app._data.nowArrow | 下一次插入的父容器与间隙 | 与当前选中的方块分别保存 |

模板中的 list.nl 对应原 nodeList，index 对应外部 vueData。全局 nowNode 是 DOM，而 app._data.nowNode 是节点对象，不能混用。

**第一步：点击方块，把界面编号转换为存储下标。** elementClick 把当前 DOM 元素 this 传给 operationChange：

~~~js
function elementClick(e) {
    operationChange(e, this);
    e.stopPropagation();
}
~~~

operationChange 中与选择有关的语句按源码顺序摘出为：

~~~js
nowNode = theNode;
vueData.nowNodeIndex = actionSequence[theNode.getAttribute("data")];
theNode.style.borderColor = "blue";
handleElement();
~~~

点中点击按钮，data="4" → actionSequence[4]=2 → nowNodeIndex=2。蓝色边框标出当前选择；stopPropagation 避免这次点击继续冒泡，让外面的循环也被当成选中对象。

**第二步：handleElement 把对象和操作类型交给 Vue。** 下面是 logic.js 中的完整函数：

~~~js
function handleElement() {
    app._data["nowNode"] = nodeList[vueData.nowNodeIndex];
    app._data["nodeType"] = app._data["nowNode"]["option"];
    app._data.useLoop = app._data["nowNode"]["parameters"]["useLoop"];
    app._data.xpath = app._data["nowNode"]["parameters"]["xpath"];
    app._data["codeMode"] = -1; //自定义初始化
    if (app._data["nodeType"] == 8) {
        app._data.loopType = app._data["nowNode"]["parameters"]["loopType"];
    } else if (app._data["nodeType"] == 3) {
        app._data.paraIndex = 0; //参数索引初始化
        app._data.params.parameters = app._data["nowNode"]["parameters"]["params"];
    } else if (app._data["nodeType"] == 5) {
        app._data.codeMode = app._data["nowNode"]["parameters"]["codeMode"];
    } else if (app._data["nodeType"] == 10) {
        app._data.TClass = app._data["nowNode"]["parameters"]["class"];
    }
}
~~~

最关键的是前两行：nowNode 指向 nodeList[2]，nodeType 取它的 option=2。后面的 useLoop、xpath 等字段把当前对象的值装入相应界面状态；循环还要加载 loopType，采集加载 params，自定义操作加载 codeMode，分支加载 TClass。

**第三步：Vue 根据 nodeType，创建对应的参数区域。** [FlowChart_CN.html](/source/?file=9bc3327fb264a3fe95.html) 预先写好了各类参数控件，用 v-if 选择当前区域。下面保留点击与循环相关绑定，省去其他控件：

~~~html
<div id="app">
  <label>选项名称：</label>
  <input v-model='list.nl[index.nowNodeIndex]["title"]'>

  <div class="elements" v-if="nodeType==2">
    <label>XPath：</label>
    <textarea v-model="xpath"></textarea>
    <label>点击后页面加载最长等待时间（秒）：</label>
    <input type="number" v-model.number='nowNode["parameters"]["maxWaitTime"]'>
  </div>

  <div class="elements" v-if="nodeType==8">
    <label>循环类型：</label>
    <select v-model="loopType" @change="handleLoopTypeChange">
      <option :value="0">单个元素（多用于循环点击下一页）</option>
      <option :value="1">不固定元素列表</option>
      <option :value="2">固定元素列表</option>
      <option :value="3">文本列表（多用于循环在文本框输入文本）</option>
      <option :value="4">网址列表（多用于循环打开网页）</option>
    </select>
    <div v-if="parseInt(loopType) < 2">
      <label>XPath：</label>
      <textarea v-model='nowNode["parameters"]["xpath"]'></textarea>
    </div>
    <div v-else-if="parseInt(loopType) == 2">
      <label>XPath列表：</label>
      <textarea v-model='nowNode["parameters"]["pathList"]'></textarea>
    </div>
    <div v-else-if="parseInt(loopType) < 5">
      <label>内容列表：</label>
      <textarea v-model='nowNode["parameters"]["textList"]'></textarea>
    </div>
  </div>
</div>
~~~

这是相关控件的教学摘录，原循环下拉框还包含脚本类循环选项。v-if 条件成立时 Vue 创建这组控件，不成立时移除；页面没有跳转到另一个 URL，也不是点击函数手工拼出整块参数表单。

**为什么只是给 nodeType 赋值，右侧就能改变？** `new Vue` 把 `#app` 内的模板与 data 中的数据建立了响应式关联。模板读了 nodeType，Vue 就会在它变化后更新相应区域；模板读了 nowNode 的参数，就会显示当前对象的值。这里 handleElement 负责改数据，Vue 负责根据模板更新参数栏，通常在本轮数据修改后的异步更新中完成。

读这段模板时，几个 Vue 写法分别负责不同的事：

| 写法 | 在本页的作用 |
| --- | --- |
| `el: '#app'` | 指定 Vue 管理的参数栏范围 |
| `v-if="nodeType==2"` | 当前是点击操作时创建点击表单 |
| `v-model="xpath"` | 将控件的显示值和 Vue 的 xpath 状态双向绑定 |
| `v-model.number='nowNode["parameters"]["maxWaitTime"]'` | 将数字输入写入当前节点参数；有效数字输入会转换为数值 |
| `:value="3"` | 将选项值绑定为数值 3 |
| `@change="handleLoopTypeChange"` | 用户切换下拉选项时调用对应方法 |
| `watch` 与 `deep: true` | 监听数据变化；深度监听还会响应被观察对象内部的字段变化 |

这里的 nodeType 名字容易误导：**它保存 node.option，不是节点的外观字段 node.type。** 点击的 type=0、option=2，因此显示 nodeType==2 区域；循环的 type=1、option=8，显示的是 nodeType==8 区域。

| 选择的方块 | DOM data | nowNodeIndex | nowNode 指向 | nodeType | 右侧出现什么 |
| --- | --- | --- | --- | --- | --- |
| 点击按钮 | 4 | 2 | nodeList[2] | 2 | 点击的 XPath、点击方式、等待等参数 |
| 循环 | 2 | 4 | nodeList[4] | 8 | 循环类型及相应列表、XPath、退出条件等参数 |
| 再选点击按钮 | 4 | 2 | 重新指向 nodeList[2] | 2 | 回到原点击对象的配置 |

**第四步：修改控件，值写到原节点对象。** handleElement 没有复制节点，app._data.nowNode 与 nodeList[nowNodeIndex] 是同一个对象。以选中点击按钮为例：

~~~text
v-model.number='nowNode["parameters"]["maxWaitTime"]'
    ↓ 用户输入 10
nodeList[2].parameters.maxWaitTime = 10

v-model='list.nl[index.nowNodeIndex]["title"]'
    ↓ 用户修改名称
nodeList[2].title = 新名称
~~~

以普通文本输入为例，可以把 v-model 理解成“从数据读出当前值，再在输入事件中把新值写回绑定位置”；这是双向绑定的教学解释，原模板仍由 Vue 处理。比如上面的数字输入，绑定目标最终就是 nodeList[2].parameters.maxWaitTime。**不是等点击保存时才读取这个输入框，用户编辑时就已经在改内存里的节点参数。**

另一些控件先绑定到界面状态，再通过 watch 或 change 方法写回。例如点击区域的 XPath 绑定 xpath，watch 中实际执行：

~~~js
xpath: {
  handler: function (newVal, oldVal) {
    this.nowNode["parameters"]["xpath"] = newVal;
  }
}
~~~

直接绑定 nowNode.parameters.xpath 可以写对象里的值，但要保证相关界面联动，还必须保证参数具有响应性。当前新增流程先 push 节点、后普通赋值补 parameters，会受到 Vue 2 属性新增检测限制，不能只换绑定表达式就删掉 watch。三个监听的职责和参数新增时序，集中见第 22 讲的[watch 与直接绑定对照](/easyspider/chapter-22#vue-watch-bridge)及[实际响应性限制](/easyspider/chapter-22#vue2-late-parameters)。

循环类型绑定 loopType；下拉框 change 时调用 handleLoopTypeChange，其第一句写回参数：

~~~js
this.nowNode["parameters"]["loopType"] = this.loopType;
~~~

该方法还根据循环类型修改标题。比如选择 3，就写入 loopType=3，标题改为“循环 - 文本列表”；上面的 v-else-if 随之显示 textList 输入框。这是在同一个循环参数区域内再切换一组控件。

**第五步：参数变化以后，画布怎样更新？** 原 Vue 对 nowNode 设置了深度监听：

~~~js
nowNode: {
  deep: true,
  handler: function (newVal, oldVal) {
    updateUI();
  }
}
~~~

logic.js 的 updateUI 完整代码如下：

~~~js
function updateUI() {
    refresh(false);
    app.$data.nowArrow["num"]++; //改变元素的值,通知画图，重新对锚点画图
    let tnodes = document.getElementsByClassName("clk");
    let position = nodeList[vueData.nowNodeIndex]["position"];
    let pid = nodeList[vueData.nowNodeIndex]["parentId"];
    for (let i = 0; i < tnodes.length; i++) {
        if (position == tnodes[i].getAttribute("position") && pid == tnodes[i].getAttribute("pId")) {
            tnodes[i].style.borderColor = "blue"; // 点击了确定按钮之后需要重新对选中的颜色画框
            nowNode = tnodes[i];
            break;
        }
    }
}
~~~

refresh(false) 用当前数据重画方块，并保留已选插入地址；随后 num++ 触发锚点重着色，再按父编号和 position 找到新 DOM，恢复蓝色选择框。旧 DOM 已被重建，所以全局 nowNode 也要重新指向新元素。

这里有两条各自负责的更新路径：Vue 根据 nodeType、loopType 等状态切换右侧控件；jQuery 的 refresh 重建左侧流程图。**参数写回内存、重画流程图、保存到磁盘是三个不同的动作。** nowNode 的深度监听调用 updateUI，不会调用 saveService；logic.js 中的“确定”按钮也只是绑定 updateUI。

**第六步：为什么参数能保存？因为保存函数拿到的就是已经改过的 nodeList。** 沿用点击按钮的例子，假设把 maxWaitTime 改为 10，并把 XPath 改为 `//button[@id='search']`。等绑定和监听器完成写回，内存中已有：

~~~js
nodeList[2].parameters.maxWaitTime === 10;
nodeList[2].parameters.xpath === "//button[@id='search']";
app._data.nowNode === nodeList[2]; // 当前仍选中点击按钮时为 true
~~~

此时点循环，handleElement 会把 nowNode 改为 nodeList[4]，nodeType 改为 8；再点点击按钮，nowNode 又指回 nodeList[2]，表单自然读出刚才的 10 和新 XPath。**切换面板只改变当前正在编辑谁，已写入其他节点的参数仍留在 nodeList 里。**

接着点顶部“保存任务”，打开任务信息窗口，再点窗口里的“保存”。logic.js 通过下面的事件调用保存函数：

~~~js
$("#saveButton").mousedown(function () {
    saveService(0);
});
~~~

saveService 的关键部分如下，省去任务元数据、输入输出摘要及其他处理：

~~~js
serviceInfo = {
    // 任务名、输出设置等字段省略
    graph: nodeList
};
$.post(backEndAddressServiceWrapper + "/manageTask",
    {params: JSON.stringify(serviceInfo)},
    function (result) {
        $("#serviceId").val(parseInt(result));
    });
~~~

`graph: nodeList` 包含所有节点的 parameters，因此这次发送的 JSON 中，graph[2].parameters.maxWaitTime 就是 10，xpath 就是刚才输入的字符串。server.js 的 /manageTask 接口解析请求后，把任务对象写入 tasks/任务ID.json。**Vue 负责让编辑结果进入节点对象；保存函数和后端负责让节点对象进入文件。** 请求处理和保存反馈的实现边界见第 23 讲。

**第七步：重新打开以后，怎样回到同一个参数栏？** logic.js 的加载回调先执行：

~~~js
nodeList = result["graph"];
app.$data.list.nl = nodeList;
// 兼容处理与恢复任务信息省略
refresh();
~~~

第一行恢复节点数组，第二行让 Vue 的 list.nl 指向恢复后的新数组，refresh 再重建画布和事件。此时还需要点击相应方块，经过 operationChange → handleElement，nowNode 才指向恢复后的 nodeList[2]，参数栏显示文件中保存的 10 和新 XPath。加载恢复的是节点数据；当前选择哪个节点，由点击逻辑重新设置。

可以用下面的顺序检查这条链路：

1. 点击循环内的点击按钮：确认 nowNodeIndex=2、nodeType=2，右侧出现点击参数。
2. 把页面加载最长等待时间改为 10：确认 nodeList[2].parameters.maxWaitTime 已变为 10。
3. 点击循环，再点击按钮：确认输入框仍显示 10。这一步验证内存中的编辑结果。
4. 保存任务，关闭后重新打开，再点击按钮：确认仍显示 10。这一步验证文件中的保存结果。

第 23 讲的[参数保存与恢复入口](/easyspider/chapter-23#vue-parameters-round-trip)接着解释这份数据怎样经过 JSON、请求接口和磁盘文件完成往返。

### 改：先改一个值，结构不变

假设把点击后的等待改成 1 秒，对应数据变化是：

~~~js
nodeList[2].parameters.wait = 1;
~~~

nodeList[2] 仍是原对象，root.sequence 和循环 sequence 都不变。若改标题，也是写原对象的 title；若把动作挪出循环，则要改父 sequence，是另一类修改。

上面是直接用下标解释数据变化。实际面板通过 nowNode 及 Vue 配置项读写参数，updateUI 会调用 refresh(false) 并恢复选中显示。重画一次并不表示一定改了结构。

<a id="adjust-anchor"></a>

### 调整锚点：只选定下一次插入的位置

前面已经知道选中方块会改变右侧参数区域。现在要另外选择“下一次把新节点插在哪里”。**选中的节点与插入锚点是两份状态**：选中点击按钮用于编辑它，锚点可以放在点击之前、循环外或其他容器里。

仍在五节点图上，准备在循环里的点击之前新增动作：

~~~text
当前：root.sequence=[1,4,3]；循环 4 的 sequence=[2]
目标：下一次新增时，放到循环的第一个孩子之前。
应选箭头：pId=2，position=-1
          ↑ 界面 id=2，actionSequence[2]=4，指向循环对象
~~~

对应的循环内首箭头由 newNode 生成：

~~~html
<p class="arrow" draggable="true" data="2" pId="2" position="-1">↓</p>
~~~

**第一步：点击工具箱的“调整锚点”。** 原页面按钮为：

~~~html
<button type="button" data="13" draggable="true" class="btn btn-outline-primary options"
        title="调整下一个要插入的节点的位置">调整锚点</button>
~~~

工具箱的 .options mousedown 处理器中，相关赋值是：

~~~js
option = parseInt(this.getAttribute("data")); // 这里得到 13
title = this.innerHTML;
~~~

option=13 表示当前选择的是“调整锚点”工具，不是新增一个 option=13 的业务节点。此时还没有选定新的目标箭头。

**第二步：单击循环内的首箭头，读取它的 pId 和 position。** 原函数为：

~~~js
function arrowClick(e) {
    if (option != 0) {
        app._data.nowArrow = {"position": this.getAttribute('position'), "pId": this.getAttribute('pId'), "num": 0};
    }
    toolBoxKernel(e);
}
~~~

因为 option=13，不等于 0，这次点击把 nowArrow 改为：

~~~js
app._data.nowArrow = {pId: "2", position: "-1", num: 0};
~~~

DOM 属性读出的是字符串。它记录“父循环的第一个孩子之前”；真正插入时才把 position 转成数字并加 1。

**第三步：进入工具箱逻辑，但不修改任务结构。** toolBoxKernel 对 option==13 的分支实际只有注释：

~~~js
if (option == 13) { //调整锚点
    // let tarrow = DeepClone(app.$data.nowArrow);
    // refresh();
    // app._data.nowArrow =tarrow;
}
~~~

锚点已经在 arrowClick 中设置好了，因此这个分支不必再 push 对象、splice 孩子列表或重新调用 refresh。函数末尾会执行 option=0，结束这次工具箱操作。

调整锚点后，数据保持：

~~~text
nodeList.length = 5
root.sequence = [1,4,3]
循环.sequence = [2]
nowArrow = {pId:"2", position:"-1", num:0}
~~~

**第四步：Vue 监听 nowArrow，让目标箭头显示淡紫色。** FlowChart.js 的 watch 中，这段代码完整地先清除旧高亮，再找到新目标：

~~~js
nowArrow: { //变量发生变化的时候进行一些操作
            deep: true,
            handler: function (newVal, oldVal) {
                let arrlist = document.getElementsByClassName("arrow");
                if (oldVal != null) {
                    for (let i = 0; i < arrlist.length; i++) {
                        if (arrlist[i].getAttribute("position") == oldVal["position"] &&
                            arrlist[i].getAttribute("pid") == oldVal["pId"]) {
                            arrlist[i].style.backgroundColor = ""; // 时刻指示现在应该插入的节点的位置
                            break;
                        }
                    }
                }
                for (let i = 0; i < arrlist.length; i++) {
                    if (arrlist[i].getAttribute("position") == newVal["position"] &&
                        arrlist[i].getAttribute("pid") == newVal["pId"]) {
                        arrlist[i].style.backgroundColor = "lavender"; // 时刻指示现在应该插入的节点的位置
                        break;
                    }
                }
            }
        },
~~~

它同时比较 pId 和 position：同样的 position=-1 在 root、循环、分支里都可能出现，必须加上父编号才是完整地址。找到本例目标后，箭头的 HTML 会带上行内颜色：

~~~html
<p class="arrow" draggable="true" data="2" pid="2" position="-1"
   style="background-color: lavender;">↓</p>
~~~

颜色由监听器设置，HTML 的父子关系没有改变。锚点调整成功不代表已经新增动作，也不代表执行器将从这里开始运行。

**第五步预告：以后真正新增节点时，使用保存的地址。** 在本图末尾追加新对象 5 后，插入的核心才会执行。这里先读懂这段代码，暂不执行；下一小节“增”才完成这次新增：

~~~js
const pId = app._data.nowArrow.pId; // "2"
const position = parseInt(app._data.nowArrow.position); // -1
nodeList[actionSequence[pId]].sequence.splice(position + 1, 0, 5);
// nodeList[4].sequence 从 [2] 变成 [5,2]。
~~~

所以调整锚点只决定将来的插入位置，新增动作才修改 sequence。这段连接代码只在下面“增”的例子中执行一次，当前结构仍是循环内只有点击 2。

**还有一个快捷入口：双击箭头。** 它不必先点击工具箱，直接把 option 设为 13，并记录被双击箭头的地址：

~~~js
function arrowDblClick(e) {
    option = 13; //调整锚点操作
    app._data.nowArrow = {"position": this.getAttribute('position'), "pId": this.getAttribute('pId'), "num": 0};
    toolBoxKernel.call(this, e);
    e.stopPropagation();
}
~~~

**num 有什么用？** 它不参与插入位置计算。重画流程图后，锚点的 pId、position 可能没变，但旧箭头已经被替换；updateUI 执行 `app.$data.nowArrow["num"]++`，借助 deep:true 再触发 nowArrow 监听，给新箭头恢复高亮。真正定位间隙仍然只看 pId、position。

| 用户动作 | 改变的主要状态 | 直接效果 |
| --- | --- | --- |
| 点击方块 | nowNodeIndex、nowNode、nodeType | 方块蓝色边框，右侧显示它的参数 |
| 调整锚点后点击箭头，或直接双击箭头 | nowArrow | 箭头淡紫色，记住下一次插入地址 |
| 再选择新增操作并插入 | nodeList 与目标父 sequence | 新对象进入任务并显示为方块 |

### 增：新动作追加末尾，再把引用插到循环开头

接着在每轮点击之前增加“输入文字”。当前 nodeList.length=5，新输入分配 index=5。

~~~text
① 新对象存到 nodeList[5]，由 addParameters 补默认配置
② 把下标 5 插入循环 4 的 sequence 开头
~~~

要选循环内的首箭头：循环当前界面 id=2，所以锚点为 `{pId:2, position:-1, num:0}`。

~~~js
// 已构造好新输入节点 t，t.index=5；以下摘出连接步骤
nodeList[actionSequence[2]].sequence.splice(-1 + 1, 0, t.index);
~~~

结果：

~~~text
nodeList.length = 6
0.sequence = [1,4,3]
4.sequence = [5,2]
actionSequence = [0,1,4,3,5,2]  // refresh 后
~~~

新对象虽然在数组末尾，却排在循环里的旧点击 2 前面。实际新增代码调用 refresh 后，还会补默认参数、处理选中态和下一次插入锚点；不能把两句数组修改当成完整的界面新增实现。

### 改结构：把原来的提取移入循环

继续希望每轮“输入 → 点击 → 提取”，不再等整个循环结束才提取。把原节点 3 从 root 移到循环的点击后面：

~~~text
移动前：0.sequence=[1,4,3]，4.sequence=[5,2]
移动后：0.sequence=[1,4]，  4.sequence=[5,2,3]
~~~

按当前界面定位：提取的源 pId=0、position=2；循环的界面 id=2，目标在循环第 1 个孩子（点击）之后，因此目标 pId2=2、position2=1。

~~~js
// 摘出移动的核心；真实工具还检查目标不是自己或自己的后代
const moved = nodeList[actionSequence[0]].sequence.splice(2, 1);
nodeList[actionSequence[2]].sequence.splice(1 + 1, 0, moved[0]);
refresh();
~~~

nodeList[3] 没有移动。改变的是两个父孩子列表；提取从循环外一次执行，变为每轮循环执行。刷新后映射为 [0,1,4,5,2,3]，提取的 parentId=2、position=2、isInLoop=true。

### 删：从父列表摘掉入口，保留存储位置

接着删除刚加入的输入 5：

~~~text
删除前：4.sequence=[5,2,3]
删除后：4.sequence=[2,3]
nodeList[5].id = -1
nodeList.length 仍然是 6
~~~

刷新后 actionSequence=[0,1,4,2,3]，下标 5 不再从 root 可达。若再新增一个动作，新 index 取当前长度 6，追加到 nodeList[6]；不会因为有一个已删除槽位，就自动回填位置 5。

真实 deleteElement 先从父 sequence 摘下目标，再用队列给整棵被删子树标记 id=-1。如果只写 -1、父引用还在，下次刷新仍会重新编号并画出它。

### 这一轮到底改了哪些数据

| 操作 | nodeList 对象或长度 | sequence | 刷新后的界面 |
| --- | --- | --- | --- |
| 查询点击 | 读取原对象 | 读取父孩子列表 | 用映射定位，不修改结构 |
| 改等待 | 改原对象 parameters | 保持不变 | 配置变化 |
| 新增输入 5 | 追加新对象，长度加 1 | 循环变成 [5,2] | 输入画在点击前 |
| 移动提取 3 | 旧对象仍在原槽位 | root 摘掉 3，循环加入 3 | 提取画到框内 |
| 删除输入 5 | 原对象标记 -1，长度不减 | 循环摘掉 5 | 输入消失，其余重新编号 |

到这里，已经可以只靠数据解释每次界面操作。下面进入更完整的实现细节。

---

## 进阶起点：在完整房源图里选择插入位置

以下切换到第 15 篇的十三节点房源模型，**不继续累加刚才五节点练习的改动**。这部分各例默认从原始房源图重新开始，新增节点从 13 算起。

假设要在翻页前等待 1 秒。原来页面循环 5 的孩子是 6（房源循环）、12（点击下一页）。你希望先采完本页，再等一下，最后翻页，所以应该把新节点 13 插在这两个孩子之间。

~~~text
操作前：5（页面循环）→ [6（房源循环）, 12（下一页）]
操作后：5（页面循环）→ [6（房源循环）, 13（等待1秒）, 12（下一页）]
~~~

如果把同一个等待节点插进单间分支 8，结果就变成每采一个单间后等待一次；如果放在地区循环中、页面循环之后，则一个地区的所有页面处理完才等一次。**新增节点的参数相同，父容器不同，发生时机与次数就不同。**

本篇所有编辑例子默认从原始十三节点房源图重新开始，彼此独立。每次写“新节点 13”，都表示这次例子中的首次新增，不把前一例修改继续累加。涉及错误结构的移动例子，会先重新算一遍界面 id，再使用它作为 pId。

| 要做的事 | nodeList 的对象怎样变化 | 父 sequence 怎样变化 |
| --- | --- | --- |
| 新增 | 在数组末尾追加一个新对象 | 插入新对象的稳定下标 |
| 移动 | 原对象保持原数组位置 | 从旧父删除下标，再插到新父 |
| 复制 | 深复制出一个新对象，追加末尾 | 插入副本的新下标 |
| 删除 | 保留对象并标记 id=-1 | 从父列表摘掉入口 |
| 改输入值或 XPath | 修改原对象的 parameters | 一般不改变父子连接 |

下面每次都按“用户动作 → 操作前快照 → 修改哪个数组 → 原代码 → 执行效果”来读。

---

## 第一部分：插入位置由锚点决定

### 1. nowArrow 指向的是一个间隙

先在页面循环的两个孩子之间找插入位置。已有 [6（房源循环）,12（下一页）]，如果想把新动作插到它们中间，应选择“第 0 个孩子之后”，所以 position=0。不是填写新节点自己的下标 13，也不是点击下一页的界面 id=7。

pId=5 表示本次要改页面循环的孩子列表；position=0 表示在这个列表的哪一个间隙。二者共同确定结构位置。num 用于锚点界面响应，不参与 splice 的插入下标计算。

下面示意中的竖线是插入间隙，6、12 分别代表房源循环与点击下一页。请先把三个间隙的执行时机说出来，再看后面的调用。

Vue 数据项 nowArrow 的实际初值：

~~~json
{"position": -1, "pId": 0, "num": 0}
~~~

以页面循环为例：

~~~text
页面循环 5 的 sequence=[6,12]

位置 -1：  | 6 | 12
位置  0：    6 | 12
位置  1：    6   12 |
~~~

`pId` 是父节点的界面编号。`position` 表示哪个孩子之后；`-1` 表示第一个孩子之前。

例如：

~~~text
nowArrow={pId:5, position:0}
~~~

在本例里表示“页面循环内，房源循环之后、下一页点击之前”。

### 2. splice 的三个参数要读对

先只看 JavaScript 数组的一次具体变动：

~~~js
const children = [6, 12]; // 6=房源循环，12=下一页
children.splice(1, 0, 13); // 从位置1开始，删除0项，插入13（等待1秒）
// children 变成 [6,13,12]，已有两项都保留
~~~

如果第二个参数误写成 1，下一页 12 会被新节点替换，而不是排到后面。如果把 splice 作用在 nodeList 而不是父 sequence，所有后续对象的存储下标都会变化。

因此读原代码要先确认“改的是哪个数组”，再读三个参数。这里 position=0、position+1=1，恰好是在房源循环后面插入。

插入核心：

~~~js
nodeList[actionSequence[pId]].sequence
  .splice(position + 1, 0, t.index);
~~~

~~~text
position+1：从哪个数组位置开始操作
0：删除零项
t.index：在这个位置插入的新孩子下标
~~~

不是把新节点插入 `nodeList` 中间；新对象仍追加到 `nodeList` 末尾，只在父的孩子列表里插入一个数字。

---

## 第二部分：插入一个普通操作，逐项算一次

### 3. 在翻页前加“等待1秒”

先把动作配置具体化：新增一个普通外观的自定义操作，命名“翻页前等待1秒”，codeMode=0、code 为空、wait=1。空代码不需要执行网页脚本，执行器在这个节点操作后按 wait 等待 1 秒。其余公共字段由 addParameters 补齐。

~~~json
{
  "index": 13,
  "option": 5,
  "type": 0,
  "title": "翻页前等待1秒",
  "sequence": [],
  "parameters": {"codeMode": 0, "code": "", "wait": 1}
}
~~~

这是关键字段示意，不是可单独导入的完整任务。这个动作只实现固定延时，没有检测列表是否真正稳定。

接下来分两次修改：第一，把新对象追加到 nodeList[13]；第二，把数字 13 插进页面循环的 sequence。下面的快照和 splice 展示的就是这两步，nodeList 中的旧下一页对象仍放在第 12 项。

新节点 index=13，为自定义操作“翻页前等待1秒”；下面继续追踪它的结构归属。

操作前：

~~~text
nodeList.length=13
5.sequence=[6,12]
nowArrow={pId:5, position:0}
~~~

构造新对象、追加：

~~~text
nodeList[13]=新操作
nodeList.length=14
~~~

接到页面循环：

~~~js
nodeList[5].sequence.splice(1,0,13);
~~~

结果：

~~~text
5.sequence=[6,13,12]
~~~

执行变化：

~~~text
原来：房源循环 → 下一页点击
现在：房源循环 → 新操作 → 下一页点击
~~~

新操作会在每一轮页面循环执行，不是每个房源执行。

### 4. 如果同样插入单间分支呢

同一个普通操作，这次放到 A 的点击和提取之后。原始图中单间分支的存储下标为 8，当前界面 id=9，所以目标父 pId 必须填 9，而不是 8。

先通过 actionSequence[9]=8 找到父对象，再在父的 [10（点击房源）,11（提取）] 末尾插入新节点 13。position=1 代表第 2 个孩子之后，真正的 splice 插入下标是 2。

| 放在哪个父容器 | 海淀第1页 A、B 的表现 |
| --- | --- |
| 页面循环中，房源循环与下一页之间 | A、B 都处理完后等 1 次 |
| 单间分支中，提取之后 | A 是单间，等 1 次；B 走空兜底，不等待 |
| 兜底分支中 | B 被跳过采集，但可执行等待等兜底动作 |

因此在节点对象里看见 wait=1，还不足以知道任务会等多少次，还要沿父容器看它属于哪层。

原始房源图的单间分支 index=8，界面 id=9：

~~~text
8.sequence=[10,11]
nowArrow={pId:9, position:1}
~~~

同样追加新节点 13，然后：

~~~js
nodeList[actionSequence[9]].sequence.splice(2,0,13);
~~~

结果：

~~~text
8.sequence=[10,11,13]
~~~

新操作只在满足单间条件时执行，且每个单间都执行一次。

两个操作都叫“新增”，业务频率却完全由父容器决定。

---

## 第三部分：新增判断实际要创建三个对象

### 5. 判断与条件分支分别是什么

独立地从原始图末尾新增一个判断：原 nodeList.length=13，因此判断分配 index=13，两个自动创建的分支分别为 14、15。把判断插在 root 末尾时，root.sequence 从 [1（打开网页）,2（地区循环）] 变成 [1,2,13]。

| 对象 | 新数组下标 | option | type | 初始孩子 |
| --- | --- | --- | --- | --- |
| 判断 | 13 | 9 | 2 | [14（分支一）,15（分支二）] |
| 左分支 | 14 | 10 | 3 | [] |
| 右分支 | 15 | 10 | 3 | [] |

判断负责挑选一个分支；分支负责存自己的条件和内部动作。若只创建判断而没有分支对象，就没有候选条件可检查。下面原代码中的 l、l+1、l+2 正好对应这三个存储位置。

查看 [FlowChart.js](/source/?file=48b61e5e4ebaa6ccf2.js) 的 `toolBoxKernel`，新增 `option==9`：

~~~text
判断 t：
    index=l
    option=9
    type=2

第一个分支 nt：
    index=l+1
    option=10
    type=3

第二个分支 nt2：
    index=l+2
    option=10
    type=3
~~~

然后：

~~~js
t.sequence.push(nt.index);
t.sequence.push(nt2.index);
nodeList.push(nt);
nodeList.push(nt2);
addParameters(nt);
addParameters(nt2);
~~~

新判断 t 自己已经先 push 进数组；两个分支补入后，判断才有可容纳操作的孩子。

### 6. “新建判断”不会自动知道什么是单间

新判断下的两条分支默认都为 class=0，也就是无条件。你只把左边标题改成“单间”，但没有改参数，执行时它仍会总是先满足，右边就没有机会。

要让它按 A、B 分类，必须同时完成“条件配置”和“操作放入”：

| 配置 | 左分支 | 右分支 |
| --- | --- | --- |
| 条件参数 | class=3，value="单间" | class=0 |
| 操作内容 | 点击当前房源、提取详情 | 空，或者放记录跳过原因 |
| 处理 A 时 | 条件满足，执行内容 | 不再检查 |
| 处理 B 时 | 条件不满足，跳过内容 | 无条件满足，执行兜底 |

标题帮助人理解，parameters 才供程序判断。默认值、可视名称和真正执行条件应分别核对。

`addParameters` 给新分支：

~~~js
t.parameters.class = 0;
t.parameters.value = "";
t.parameters.code = "";
t.parameters.waitTime = 0;
~~~

两个默认分支都是无条件。第一次执行判断时，第一个就会匹配，第二个不会走到。

为了得到房源例子的含义，需要用户配置：

~~~text
第一个分支：
    class=3，value="单间"
    放入点击和提取

第二个分支：
    class=0
    sequence=[]
~~~

给框改标题叫“单间”并不足以改变判断逻辑；真正判断读的是参数。

### 7. 再增加第三条分支

本例重新从原判断 7 开始，左为 8（单间）、右为 9（无条件兜底）。用户点击“在最右边增加条件分支”，新对象放到 nodeList[13]，并追加到判断的孩子末尾，得到 [8,9,13]。

如果希望第三条是“整租”，此时即使正确设置 class=3、value="整租”，它也永远走不到：单间不满足时先遇到无条件的 9，判断已经选中并停止检查。

因此还要把新分支向左移一次，变为 [8（单间）,13（整租）,9（兜底）]。这样 A 走第一条，B 走第二条，其他类型才走兜底。最后还要给整租分支放入它应该执行的操作，空分支只能表达不做事。

后面的 branchClick 是“新增分支”，右键前移/后移则是在父判断的 sequence 中交换两个下标，两者合起来决定真正的检查优先级。

`branchClick()` 取得判断的界面 id，再新建 `option=10,type=3` 的对象，追加到判断的 `sequence` 末尾：

~~~js
nodeList[actionSequence[judgeId]].sequence.push(t.index);
refresh();
app._data.nowArrow = {position:-1, pId:t.id, num:0};
~~~

假设在原图判断 7 下新增分支 13：

~~~text
7.sequence=[8,9] → [8,9,13]
~~~

但 9 是无条件，13 无论配置什么都不会被检查到。需要把新的有条件分支放到 9 前面，形成：

~~~text
7.sequence=[8,13,9]
~~~

“向左/向右移动分支”本质是交换判断 `sequence` 中的两个下标；它同时改变检查优先级。

---

## 第四部分：移动不是挪动 nodeList 里的对象

### 8. 把下一页从 root 移进页面循环

先看错误行为：下一页被放在 root 的最后，页面循环里只有房源循环。这样页面循环每轮缺少翻页动作，整个地区处理结束后 root 才点击一次下一页。我们要把同一个下一页对象移到页面循环的房源处理之后。

**错误结构已经改变了 BFS 编号，目标 pId 要重新计算。** 对 root.sequence=[1,2,12]、5.sequence=[6] 刷新，映射为 [0,1,2,12,3,4,5,6,7,8,9,10,11]：下一页 12 的界面 id=3，页面循环 5 的界面 id=6。

| 移动所需信息 | 当前值 | 说明 |
| --- | --- | --- |
| 选中的下一页方块 data | 3 | 界面 id=3，映射到 nodeList[12] |
| 源父 pId、源 position | 0、2 | root 的第 3 个孩子 |
| 目标父 pId2 | 6 | 当前页面循环的界面 id；actionSequence[6]=5 |
| 目标 position2 | 0 | 插到房源循环这个第 1 个孩子之后 |

如果沿用原图的 pId=5，就会查到当前界面 id=5 的搜索节点，插错父容器。下面例子先给错误结构，再代入正确的当前编号。

考虑一个搭图过程中出现的错误结构：

~~~text
0.sequence=[1,2,12]
5.sequence=[6]
~~~

选择下一页 12，把锚点放到页面循环内房源循环之后。

源位置：

~~~text
父界面 id=0
position=2
~~~

目标：

~~~text
pId2=6
position2=0
~~~

源码核心：

~~~js
let element =
  nodeList[actionSequence[pId]].sequence.splice(position,1);
nodeList[actionSequence[pId2]].sequence
  .splice(position2+1,0,element[0]);
refresh();
~~~

代入：

~~~text
从 root.sequence 删除下标 12：
    [1,2,12] → [1,2]
插入 5.sequence 的位置 1：
    [6] → [6,12]
~~~

`nodeList[12]` 没有挪位置，仍是下一页。移动的是父孩子列表里的引用。

`parentId`、`position`、`id` 和 `isInLoop` 由刷新重算。

### 9. 为什么同级向后移动要减一次位置

先用一个独立的孩子列表看清问题：父 sequence=[A,B,C,D]，想把 B 移到 C 后面。A、B、C、D 在这里代表四个节点下标的代号；不是房源数据中的 A、B。

操作前，B 的 position=1；目标间隙在 C 后面，所以 position2=2。先从原位置删除 B，会得到 [A,C,D]；此时 C 已从位置 2 前移到位置 1。

| 做法 | 删除 B 后使用的插入位置 | 最终结果 |
| --- | --- | --- |
| 没有修正 | 旧 position2+1=3 | [A,C,D,B]，误放到 D 后面 |
| 同父向后移动时先 position2-- | 新 position2=1，再加 1 得到 2 | [A,C,B,D]，正确放在 C 后面 |

现在读真实的剪切核心：

~~~js
let element = nodeList[actionSequence[pId]]["sequence"].splice(position, 1);
if (pId == pId2 && position < position2) {
    position2--;
}
nodeList[actionSequence[pId2]]["sequence"].splice(position2 + 1, 0, element[0]);
~~~

这里 element 是 splice 返回的数组，本例里面只有被移出的 B；真正插入的是 element[0]。第一句按源孩子位置删除，最后一句按目标间隙插入，中间的修正处理“删除后位置前移”。

为什么只在这两个条件同时成立时减一？同一个父容器意味着删除真的改变了目标列表；向后移动意味着目标位于被删除项后面。如果跨父移动，目标列表未被源删除影响；如果向前移动，前面的目标位置也没有变化。

例如把 D 移到 A 后面：先删末尾 D，不会改变 A 的位置，所以不用减一。先逐项写数组变化，再看条件，就能理解它不是为了修正界面 id。

### 10. 为什么不能把循环移进自己的子孙

尝试把地区循环 2 拖进单间分支 8。原始图中地区循环的界面 id=2，单间分支的界面 id=9。检查从目标父 9 开始向上走：

| 当前祖先的界面 id | 映射到哪个对象 | 下一步父 id |
| --- | --- | --- |
| 9 | 8（单间分支） | 8 |
| 8 | 7（判断） | 6 |
| 6 | 6（房源循环） | 5 |
| 5 | 5（页面循环） | 2 |
| 2 | 2（地区循环），正是待移动对象 | 命中，禁止移动 |

如果允许这次移动，地区循环包含分支，分支又包含地区循环，形成循环引用；refresh 也无法正常耗尽队列。源码在改 sequence 之前就沿目标祖先链检查，因此不会先破坏原结构再尝试补救。

例如把地区循环 2 放进单间分支 8：

~~~text
2 包含 5
5 包含 6
6 包含 7
7 包含 8
~~~

如果 8 再包含 2，就形成环。`refresh` 的 BFS 没有 visited 防护，这样的结构会不断扩展；执行也会递归回自己。

移动前源码沿目标父的 `parentId` 向 root 走：

~~~js
let pidt = pId2;
while (pidt != 0) {
  if (pidt == id) {
    move = false;
    break;
  }
  pidt = nodeList[actionSequence[pidt]].parentId;
}
~~~

这里遍历的是当前界面 id。它检查目标祖先链是否遇到待移动节点。

当前实现禁止条件分支容器本身用这条剪切路径移动；分支顺序由专门的前移、后移处理。判断和循环可移动，但必须通过防环检查。

---

## 第五部分：复制和删除

### 11. 当前实现只复制普通操作

从原图复制 10（点击房源），目标放在原点击和提取之间。复制后应当有两个独立点击对象，而不是同一个节点下标在孩子列表里出现两次。

| 项目 | 原对象 | 副本 |
| --- | --- | --- |
| 数组位置 | nodeList[10] | nodeList[13] |
| 初始 XPath、点击方式等 | 保留 | 深复制得到相同值 |
| 后续把副本 wait 改为 5 | 原 wait 不变 | 副本独立变为 5 |
| 单间分支的孩子 | 原来 [10,11] | 变为 [10,13,11]；10=原点击，13=副本，11=提取 |

复制让 A 可能被连续点击两次，业务上是否合理要由用户判断。本例主要说明对象如何独立，以及为什么复制后仍需要一个新 index。循环、判断、分支的 dataType>0，目前这条入口会直接拒绝复制。

源码：

~~~js
if (nowNode.getAttribute("dataType") > 0) {
  showError(/* 循环、判断、条件分支不可复制 */);
} else {
  t = DeepClone(tt);
  t.index = nodeList.length;
  nodeList.push(t);
  // 把 t.index 插入目标父的 sequence，随后 refresh
}
~~~

`DeepClone` 递归复制对象和数组。尽管旁边注释写“浅复制”，函数实际递归处理字段；讲解应以实现为准。

例如复制房源点击 10：

~~~text
原对象 nodeList[10] 保留
新对象 nodeList[13] 获得新的 index
目标分支 8.sequence=[10,11] → [10,13,11]
~~~

新旧点击的参数内容起初相同，但参数对象是分别复制的。后续修改副本，不应当作仍在引用原对象。

复制并不是“把同一个 index=10 在 sequence 里再写一遍”。

### 12. 删除普通节点只摘一个孩子

用户选中单间分支里的点击 10，执行删除。父分支 8 的第 0 项被移除，提取 11 仍在，所以业务变成满足单间条件后直接提取当前页面，而不是先进入详情。

| 要观察的地方 | 删除前 | 删除后 |
| --- | --- | --- |
| 8.sequence | [10（点击）,11（提取）] | [11（提取）] |
| nodeList[10] | 活跃点击对象 | 原对象保留，id=-1 |
| nodeList[11].index | 11 | 仍为 11 |
| 数组长度 | 13 | 仍为 13 |

删除代码使用 splice(position,1)，与插入用 position+1 不同：源 position 已经指向要删除的孩子本身，不需要再加 1。

原结构：

~~~text
8.sequence=[10,11]
~~~

删除点击 10：

~~~text
8.sequence=[11]
nodeList[10].id=-1
nodeList.length 保持不变
~~~

解释器现在直接提取，不会点击详情。数据结构合法，不代表业务结果合理。

### 13. 删除容器，会标记整棵子树

这次删房源循环 6，不能只标记它一个对象。它下面还有判断 7、两个分支 8/9、点击 10、提取 11，这些都已不属于当前活跃任务。

删除队列逐步变化为：

| 取出并标记谁 | 发现的孩子 | 标记后剩余队列 |
| --- | --- | --- |
| 6（房源循环） | 7（判断） | [7] |
| 7（判断） | 8（单间分支）、9（兜底） | [8,9] |
| 8（单间分支） | 10（点击）、11（提取） | [9,10,11] |
| 9（兜底） | 无 | [10,11] |
| 10（点击） | 无 | [11] |
| 11（提取） | 无 | [] |

先从页面循环的孩子列表摘掉 6，保证子树不可达；再把上述对象都设为 id=-1，保证保存输入输出摘要时也跳过它们。内部的旧 sequence 可以保留，因为存储位置没有压缩，也没有入口再执行这些对象。

`deleteElement()` 的关键部分：

~~~js
let tnode =
  nodeList[actionSequence[pId]].sequence.splice(position,1);

let queue = new Array();
queue.push(tnode[0]);
while (queue.length > 0) {
  let index = queue.shift();
  nodeList[index].id = -1;
  for (let i = 0; i < nodeList[index].sequence.length; i++) {
    queue.push(nodeList[index].sequence[i]);
  }
}
// 实际函数先设置删除后的锚点，再 refresh(false)
refresh(false);
~~~

删除房源循环 6：

~~~text
5.sequence=[6,12] → [12]

依次标记这些 index：
6 → 7 → 8,9 → 10,11
~~~

节点对象及其内部 `sequence` 可以仍留在数组里，但这棵子树已经从 root 断开。刷新不再访问它，保存的参数统计也排除 `id=-1` 的对象。

这个局部 `queue` 专门用于删除子树，与全局刷新队列同名但不是同一个变量。

### 14. 改参数与改结构，要看不同入口

给出四个用户动作，先预测会改哪里：

| 用户要求 | 应改的数据 | 操作后怎样观察 |
| --- | --- | --- |
| 把单间条件改成整租 | 分支 8.parameters.value | 框层次相同，选中条件变化 |
| 把输入海淀改为输入西城 | 地区循环 2.parameters.textList | 节点仍是同一组，运行文本变化 |
| 提取后再点击 | 单间分支 8.sequence 的排列 | 两个方块次序及执行顺序改变 |
| 每页处理后点击下一页 | 把 12 移到页面循环 5 的 sequence | 方块父容器及发生频率改变 |

它们可能都触发界面更新，但底层修改范围不同。不要把“刷新了一次”当成“做了同一种编辑”。下面按入口再归纳一次。

~~~text
改“输入文字”“XPath”“条件文本”：
    修改节点 parameters

调换点击与提取：
    改分支 sequence 的排列

把下一页放进页面循环：
    从旧父 sequence 删除，再插进新父 sequence

删除整个房源处理段：
    从父 sequence 摘掉容器，并标记它的子树
~~~

`updateUI()` 等配置逻辑会刷新显示与选中状态；新增、移动、删除等结构路径要重新计算编号和层次。

### 15. 一次操作后，应该检查什么

先完整分析最后一个容易犯的错误：把提取 11 从单间分支移到房源循环中，放在判断后面。现在房源循环孩子为 [7（判断）,11（提取）]，单间分支只剩 [10（点击）]。

A 满足单间，判断内部点击后返回，父循环接着提取；B 不满足单间，兜底空分支返回，但父循环仍会执行自己的下一项 11。因此“兜底里没有提取”并不能阻止父容器里的提取。

这个错误说明编辑结果不能只看原分支内部是否留有某个节点，还要看父容器下一步会做什么。第 16 讲的递归返回规则在这里直接决定改图后的业务行为。下面的问题按这条思路逐项检查。

用房源例子读源码时，按顺序问：

1. 新对象是否追加到 `nodeList`，index 是否是它的数组位置？
2. root 到它是否有 `sequence` 路径？
3. 它属于正确的循环或分支吗？
4. 同级排列是否就是期望的操作顺序？
5. 判断的兜底分支是否在最后？
6. 刷新后的 id 是否仍被正确翻译成 index？

这几个问题比“方块在屏幕上看起来是不是摆对了”更能判断任务是否正确。

练习：把提取 11 从单间分支 8 移到房源循环 6 的判断后面。结果是 `6.sequence=[7,11]`、`8.sequence=[10]`。所有房源都会执行提取，整租分支为空也无法阻止父容器继续执行 11。


---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[19.流程图怎样画出来：逐步执行 refresh、生成 DOM 与 CSS 外观](/easyspider/chapter-19) ｜ 下一篇：[21.消息到流程图节点](/easyspider/chapter-21)
