---
title: "11 · Vue 3 基础"
description: "easyspider · 界面与通信 · 课程讲义"
project: "easyspider"
sourcePath: "EasySpider/Docs/讲义/11.Vue3详解.md"
originalUrl: "/originals/easyspider/chapter-11.md"
outline: [2, 3]
downloadLabel: "下载原始 Markdown"
---

# 11.Vue3详解：读懂 toolkit.vue 前的模板、状态与构建背景

第 08 篇讲完参数生成，第 10 篇又讲完子元素采集与预览数组的转换。先停下来补界面背景：模板怎样读取状态，方法怎样响应按钮，Vue 怎样更新 DOM，以及 `.vue` 文件怎样构建成扩展脚本。下一篇再按业务流程拆 `toolkit.vue` 的关键函数。

> 本篇保留语法、最小例子与构建过程，作为操作台详解的前置背景。
>
> 我们把 `Extension/manifest_v3/src/content-scripts/toolkit.vue`（934 行）当成教材，
>   
> 把一个 Vue 组件里**出现过的每一种语法、每一个钩子、每一个函数**都拎出来，
>   
> 先给一个能抄走的"最小例子"，再回到 toolkit.vue 里看它真实怎么用。
>
> 风格和 03（Chrome 扩展）、04（XPath）一致：概念 → 最小例子 → 真实代码 → 拆解。

---

### 0. 先认清一个事实：toolkit.vue 其实是 Vue 2.7 写的

打开 `Extension/manifest_v3/package.json`，白纸黑字：

```json
"vue": "^2.7.14",
"vue-template-compiler": "^2.7.14",
"rollup-plugin-vue2": "^0.8.1"
```

`rollup.config.js` 里也是：

```js
import vue from 'rollup-plugin-vue2';
// ...
vue(),
```

也就是说，扩展里的 `.vue` 是用 **Vue 2.7** 编译的。

🔬 那为什么这一篇叫"Vue3"？

> 因为 toolkit.vue 用的是 **Options API（选项式 API）**，
>   
> 而 **Options API 在 Vue 3 里被完整保留**——
>   
> `data / methods / mounted / computed / watch` 这些写法，Vue 2 和 Vue 3 几乎一模一样。
>
> 模板和选项式 API 的许多概念可以用于理解 Vue 3；具体挂载、生命周期和响应式边界仍要按版本区分。
>
> 唯一要小心的：toolkit.vue 里有 4 个**纯 Vue 2 的用法**，
>   
> Vue 3 里要么改名、要么删掉了。我们会在每一处标清楚。

#### Vue-2-only 速查表（看到它们别在 Vue 3 文档里找）

| toolkit.vue 里的写法                              | 性质                      | Vue 3 怎么办                                  |
| --------------------------------------------- | ----------------------- | ------------------------------------------ |
| `filters: { toEng(){} }` + `{{ x \| toEng }}` | ❌ Vue 3 已**删除** filters | 改用 `computed` 或 `methods`                  |
| `beforeDestroy(){}`                           | 改名                      | 改成 `beforeUnmount()`                       |
| `data: { ... }`（对象）                           | 根实例特例                   | Vue 3 必须 `data() { return {...} }`（函数）     |
| `el: '#realcontent'`                          | 移除                      | 改成 `createApp(Comp).mount('#realcontent')` |

> 后面每一节，凡是踩到这些，我会用 🔴 标出来。

---

### 1. 没有框架的世界

传统写法是这样的：

数据变了，你要**手动**去改 DOM，而且容易漏。

```js
let count = 0;
function add() {
    count++;
    document.getElementById("num").innerText = count;  // 手动同步
}
```

页面一复杂，这种"数据 ↔ 界面"的手动同步就会失控——
  
改 10 个地方，漏 1 个，界面就不一致了。

---

### 2. Vue 的核心思想：响应式 + 声明式

一句话记住它：

> **你只管改数据，界面自动跟着变。**

```js
const count = ref(0);
// 模板里写 {{ count }}
// 只要 count.value++ 界面自动更新，不用碰 DOM
```

这就是**声明式**：

你声明"界面应该长什么样（取决于哪些数据）"，框架负责"怎么把界面改成那样"。

对比一下两条路：

```text
命令式（jQuery / 原生）：  数据变 → 我手动找元素 → 改它的 text / class / style
声明式（Vue）：            数据变 → Vue 比对前后差异 → 只改真正变的那一小块 DOM
```

---

### 3. 三种写法：CDN / 单文件组件 / \<script setup>

EasySpider 里三种都沾边，先认个脸。

#### 3.1 CDN 写法（Electron 端用，零构建）

```html
<script src="js/vue.global.js"></script>
<div id="app">{{ msg }}</div>
<script>
  const { createApp } = Vue;
  createApp({
    data() { return { msg: "你好" } }
  }).mount("#app");
</script>
```

`vue.global.js` 是 Vue 的"全家桶"版，丢进 `<script>` 就能用，不用打包。

🔬 EasySpider 用这种方式是为了**避免复杂构建**：改完 HTML 直接生效。

#### 3.2 单文件组件写法（扩展用，需打包）

一个 `.vue` 文件 = 模板 + 逻辑 + 样式，三合一。

```html
<template>
  <div>{{ list.nl.length }} 个元素已选中</div>
  <a v-on:mousedown="selectAll">选中全部</a>
</template>

<script>
export default {
  data() {
    return { list: { nl: [] }, valTable: [] }
  },
  methods: {
    selectAll() { readyToList(this.step, false); }
  }
}
</script>

<style>
  .tooldrag { cursor: move; }
</style>
```

浏览器不认识 `.vue`，所以扩展端用 **Rollup + rollup-plugin-vue2** 把它编译成纯 JS 再加载。

#### 3.3 Composition API 写法（Vue 3 官方推荐）

```html
<template>
  <div>{{ count }}</div>
  <button @click="count++">+1</button>
</template>

<script setup>
import { ref } from 'vue';
const count = ref(0);
</script>
```

`<script setup>` 是 Vue 3 的新写法。第 6 节我们会把 toolkit.vue 用这套重写一版。

---

## 4. 模板语法：toolkit.vue 里出现的每一个都讲

下面 7 个，是 toolkit.vue 模板里**全部**出现的 Vue 语法。
  
逐个来：先给最小例子，再贴真实代码，最后拆解。

---

### 4.1 `{{ }}` 插值（Mustache）

**作用**：把数据"显示"到页面上。里面可以放变量、表达式，甚至方法调用。

#### 最小例子

```html
<template>
  <p>当前计数：{{ count }}</p>
  <p>两倍：{{ count * 2 }}</p>
  <p>问候：{{ sayHi() }}</p>
</template>

<script>
export default {
  data() { return { count: 3 } },
  methods: {
    sayHi() { return "你好，Vue"; }
  }
}
</script>
```

#### toolkit.vue 里的真实用法

```html

<div v-if="list.nl.length==1">
  ● 已选中{{ numOfList() }}个{{ tname() }}，
  <span v-if="numOfReady()>0&&tname()!='下一页元素'">同时发现{{
    numOfReady()
  }}个同类元素，</span>
</div>


{{ initial() }}


<td v-for="j in list.opp.length">{{ valTable[j - 1][i - 1] }}</td>
```

#### 拆解

- `{{ }}` 里**只能是表达式**，不能是语句（`if`、`for` 不行）。
- 可以写方法调用 `{{ numOfList() }}`——每次重新渲染都会执行一次。
- 🔴 **坑**：`{{ initial() }}` 这行，方法 `initial()` 内部在改 `this.selectStatus` 等状态（有副作用）。
    
  插值里调有副作用的方法，是**不推荐**的写法（渲染本应纯函数），但 Vue 允许，
    
  效果就是"渲染这行时顺手初始化了状态"。能跑，但不优雅。

---

### 4.2 `v-if` / `v-else-if`：条件渲染

**作用**：条件为真才把这段 DOM 渲染出来（假的就**不创建**，不是隐藏）。

#### 最小例子

```html
<template>
  <div v-if="score >= 90">优秀</div>
  <div v-else-if="score >= 60">及格</div>
  <div v-else>不及格</div>
</template>
```

#### toolkit.vue 里的真实用法

toolkit.vue 用 `v-if` / `v-else-if` 做了**两套语言 + 四个页面**的切换：

```html

<div v-if="lang == 'zh'"> ...中文操作台... </div>
<div v-else-if="lang=='en'"> ...英文操作台... </div>


<div v-if="page==0"> ● 主操作台 </div>
<div v-else-if="page==1"> ● 输入文字面板 </div>
<div v-else-if="page==2"> ● 切换下拉选项面板 </div>
<div v-else-if="page==3"> ● 设置翻页操作面板 </div>
```

#### 拆解

- `v-if` / `v-else-if` / `v-else` 必须**紧挨着**写，中间不能插入别的兄弟。
- 它是"真·销毁/重建"，和 `v-show`（只是 `display:none`）不同：
    
  频繁切换用 `v-show`，一次性条件用 `v-if`。
- toolkit.vue 用 `page` 这个数据当"当前显示哪个面板"的开关——
    
  点按钮时 `this.page = 1`，界面就自动切到输入面板。这就是"改数据→界面变"。

---

### 4.3 `v-for`：列表渲染

**作用**：把一个数组 / 数字范围，渲染成多份重复的 DOM。

#### 最小例子

```html
<template>
  
  <li v-for="item in fruits">{{ item }}</li>

  
  <li v-for="(item, index) in fruits">{{ index }} - {{ item }}</li>

  
  <span v-for="n in 5">{{ n }}</span>
</template>

<script>
export default {
  data() { return { fruits: ["苹果", "香蕉", "橘子"] } }
}
</script>
```

#### toolkit.vue 里的真实用法

```html

<th v-for="(i, index) in list.opp">
  <div>{{ i["name"] }}</div>
  <span v-bind:index="index" v-on:mousedown="removeField" title="删除此字段">×</span>
</th>


<tr v-for="i in valTable[0].length">
  <td v-for="j in list.opp.length">{{ valTable[j - 1][i - 1] }}</td>
  <td v-bind:index="i-1" v-on:mousedown="deleteSingleLine">×</td>
</tr>
```

#### 拆解

- `v-for="(i, index) in list.opp"`：`i` 是每一项，`index` 是下标（**从 0 开始**）。
- `v-for="i in valTable[0].length"`：当右边是数字 `n`，Vue 会渲染 `1..n` 份，
    
  `i` 依次取 `1, 2, ..., n`。所以代码里用 `i-1` 当索引去取数组（因为 `i` 从 1 开始）。
- 🔴 **坑（真实代码就踩了）**：toolkit.vue 的 `v-for` **没有写 `:key`**。
    
  Vue 官方要求列表加 `:key` 来标识"哪份 DOM 对应哪条数据"，否则增删项时可能复用错节点。
    
  正确写法应为 `<th v-for="(i, index) in list.opp" :key="index">`。

---

### 4.4 `v-on` / `@`：事件绑定

**作用**：把"用户操作"（点击、按下、变化……）绑定到一个方法。

- `v-on:click="fn"` 的简写是 `@click="fn"`。
- toolkit.vue 大量用 `v-on:mousedown` 而不是 `click`——这是刻意的：
    
  `mousedown` 比 `click` 先触发，爬虫工具要在浏览器做默认点击**之前**就拦截下来。

#### 最小例子

```html
<template>
  
  <button @click="sayHello">打招呼</button>

  
  <button @click="add(5)">加 5</button>

  
  <button @click="remove($event, id)">删除</button>
</template>

<script>
export default {
  methods: {
    sayHello() { console.log("hi"); },
    add(n) { console.log("加", n); },
    remove(e, id) { console.log("点的是", e.target, "删", id); }
  }
}
</script>
```

#### toolkit.vue 里的真实用法

```html

<a v-on:mousedown="selectAll">选中全部</a>


<a v-on:mousedown="selectDescendents(1,1)">选中子元素（相对首选块共同元素）</a>


<select v-model="optionMode" @change="handleSelectChange">


<span v-bind:index="index" v-on:mousedown="removeField" title="删除此字段">×</span>
```

对应的方法（注意 `event` 怎么用）：

```js
removeField: function (event) {
  let index = event.target.getAttribute("index");   // 从 DOM 上把 index 读回来
  let tParameter = global.outputParameters.splice(index, 1)[0];
  // ...
}
```

#### 拆解

- 模板里写 `v-on:mousedown="removeField"`（**不加括号**）→ Vue 自动传原生 `event`。
- 模板里写 `v-on:mousedown="selectDescendents(1,1)"`（**加括号**）→ 传的是你写的参数，
    
  **不再自动传 event**（想要 event 得自己加 `$event`）。
- toolkit.vue 用的"把 `index` 写到 `v-bind:index` 上、再在方法里 `event.target.getAttribute` 读回来"
    
  是一种**曲线救国**的传参法。Vue 3 更推荐的写法是直接把参数传进方法：
    
  `<span @mousedown="removeField(index)">`，省得绕 DOM 一圈。

---

### 4.5 `v-bind` / `:`：属性绑定

**作用**：把标签的**属性**（不是文字内容）绑定成动态值。
  
静态属性 `class="x"` 写死；动态属性 `:class="x"` 取值。

#### 最小例子

```html
<template>
  
  <img :src="imgUrl" :alt="desc">

  
  <div :style="{ color: textColor, fontSize: textSize + 'px' }">红色字</div>

  
  <div :class="{ active: isOn }">高亮?</div>
</template>

<script>
export default {
  data() { return { imgUrl: "/a.png", desc: "图", isOn: true, textColor: "red", textSize: 14 } }
}
</script>
```

#### toolkit.vue 里的真实用法

```html

<div v-if="list.nl.length==0" :style="{overflow: 'auto', maxHeight: winHeight * 0.4 + 'px'}">


<span v-bind:index="index" v-on:mousedown="removeField">×</span>


<td style="..." v-bind:index="i-1" v-on:mousedown="deleteSingleLine">×</td>
```

#### 拆解

- `v-bind:index` 的简写就是 `:index`。toolkit.vue 里两种写法混着用（风格不统一，但都对）。
- `:style` 用**对象**写法时，CSS 属性名要写成 **camelCase**（`maxHeight`）或带引号的 kebab（`"max-height"`）。
- `winHeight * 0.4 + 'px'`：绑定值里可以是任意表达式，运行时算。
    
  `winHeight` 来自 `data`，窗口缩放时 `this.winHeight = window.outerHeight`（见 5.5），
    
  界面高度就自动跟着变——又是一次"改数据→界面变"。

---

### 4.6 `v-model`：双向绑定

**作用**：表单输入和数据的**双向同步**——
  
输框里打字 → 数据变；数据被代码改 → 输框里显示变。

#### 最小例子

```html
<template>
  <input v-model="keyword" placeholder="搜索">
  <p>你输入的是：{{ keyword }}</p>

  <select v-model="city">
    <option value="hz">杭州</option>
    <option value="nb">宁波</option>
  </select>
</template>

<script>
export default {
  data() { return { keyword: "", city: "hz" } }
}
</script>
```

#### toolkit.vue 里的真实用法

```html

<input id="WTextBox" v-model="text" autoFocus="autofocus" type="text"></input>
<button v-on:click="getInput">确定</button>


<select v-model="optionMode" @change="handleSelectChange">
  <option value=0>切换到下一个选项</option>
  <option value=1>按索引值切换选项</option>
  <option value=2>按选项值切换选项</option>
  <option value=3>按选项文本切换选项</option>
</select>


<input id="selectValue" v-if="optionMode != 0" v-model="optionValue" type="text"></input>
```


#### 拆解

- `v-model="text"` 等价于：`value` 绑定 `text` + 监听 `input` 事件把新值写回 `text`。
- 点"确定"时方法里读 `this.text` 即可拿到用户输入：

```js
getInput: function () {
  input(this.text, this.batch);   // 用 v-model 绑定的 text
  this.text = "";                 // 清空 → 输入框也自动变空
}
```

- 下拉框 `v-model="optionMode"`：选不同 `<option>` 时 `optionMode` 自动变成对应 `value`（注意是**字符串** `"0"`/`"1"`，
    
  toolkit.vue 后面比较时用的是 `==` 而非 `===`，所以类型宽松匹配没问题；若用 `===` 要小心类型）。

---

### 4.7 `filters` 与 `|` 管道  🔴 Vue 2 only

**作用**：在模板里对显示值做"格式化"，写法像 Linux 管道 `value | 过滤器`。

#### 最小例子（仅 Vue 2 可用）

```html
<template>
  <p>{{ price | yuan }}</p>     
</template>

<script>
export default {
  data() { return { price: 12 } },
  filters: {
    yuan(v) { return "￥" + v.toFixed(2); }
  }
}
</script>
```

#### toolkit.vue 里的真实用法

toolkit.vue 用 `toEng` 过滤器把中文元素名翻译成英文（同一套界面中英文切换）：

```html

<div v-if="numOfReady()>0 && !selectStatus"><a v-on:mousedown="selectAll">Select All</a></div>
● Already selected {{ numOfList() }} {{ tname() | toEng }}, ...
```

```js
filters: {
  toEng: function (value) {
    if (value == "下一页元素") return "elements in next page";
    else if (value == "链接") return "link";
    else if (value == "图片") return "image";
    else if (value == "按钮") return "button";
    else if (value == "文本框") return "text box";
    else if (value == "选择框") return "selection box";
    else return "element";
  }
}
```

#### 🔴 拆解：Vue 3 里 filters 被删了！

Vue 3 **正式移除了 `filters`**。官方建议改用：

- **`computed`**（值依赖别的响应式数据、会缓存）→ 适合"由某个 data 派生"的显示；
- **`methods`**（每次渲染都重算）→ 适合 toolkit.vue 这种"传参格式化"。

toolkit.vue 的 `toEng` 在 Vue 3 里应改写成方法调用（和 4.1 一样直接在插值里调）：

```html

{{ toEng(tname()) }}
```

```js
methods: {
  toEng(value) {
    const map = {
      "下一页元素": "elements in next page",
      "链接": "link", "图片": "image", "按钮": "button",
      "文本框": "text box", "选择框": "selection box"
    };
    return map[value] || "element";
  }
}
```

> 💡 顺手把 `if/else` 链换成 `map` 查表，更清爽——这也是读老代码时常做的重构。

---

## 5. 脚本部分（Options API）：toolkit.vue 用到的钩子与选项

模板是"长相"，`<script>` 是"大脑"。toolkit.vue 的 `<script>` 用 Options API，
  
下面把出现的每个选项/钩子逐个讲。

---

### 5.1 `export default { }`：组件定义对象

**作用**：一个 `.vue` 文件导出一个"组件选项对象"，Vue 据此创建组件实例。

#### 最小例子

```js
import { ref } from 'vue';   // 也可以 import 自己的工具函数
export default {
  data() { return { msg: "hi" } },
  methods: { greet() { console.log(this.msg); } }
}
```

#### toolkit.vue 里的真实用法

```js
import { global, isInIframe, getOS, readXPath /* ... */ } from "./global.js";
import { input, sendSingleClick /* ... */ } from "./messageInteraction.js";
import $ from "jquery";

export default {
  el: '#realcontent',
  data: { /* ... 见 5.3 ... */ },
  mounted() { /* ... */ },
  beforeDestroy() { /* ... */ },
  watch: { /* ... 见 5.6 ... */ },
  filters: { /* ... 见 4.7 ... */ },
  methods: { /* ... 见 5.4 ... */ }
}
```

#### 拆解

- `import` 是 **ES 模块**语法（不是 Vue 专属），但它是 `.vue` 能被 Rollup 打包的前提：
    
  `toolkit.vue` 依赖 `global.js` 的算法、`messageInteraction.js` 的通信、`jquery`。
    
  打包时这些 `import` 会被合并进最终 JS。
- `export default` 导出的对象，就是 Vue 组件的"全部配置"。

---

### 5.2 `el`：挂载到哪个 DOM  🔴 Vue 3 改成 `mount()`

**作用**：告诉 Vue"把这个组件挂到页面上哪个已存在的元素里"。

#### toolkit.vue 里的真实用法

```js
export default {
  el: '#realcontent',   // 挂到 id="realcontent" 的 div 上
  // ...
}
```

对应的模板根节点：

```html
<template>
  <div id="realcontent">
    
  </div>
</template>
```

#### 🔴 拆解：Vue 3 改了挂载方式

Vue 2 可以在选项里写 `el`；**Vue 3 删掉了 `el` 选项**，改为：

```js
import { createApp } from 'vue';
import ToolKit from './toolkit.vue';
createApp(ToolKit).mount('#realcontent');
```

EasySpider 实际使用的是 Vue 2.7：`main.js` 先创建 `<div id="realcontent"></div>`，再执行 `global.app = new Vue(ToolKit)`。虽然构造调用没有单独写 `el`，但传入的 `ToolKit` 选项对象里已经有 `el:'#realcontent'`，因此挂载目标由这个选项提供。上面的 `createApp().mount()` 是 Vue3 对照写法，不是当前仓库的实际入口。

---

### 5.3 `data`：响应式数据源

**作用**：组件"状态"的存放处。模板里 `{{ }}`、方法里 `this.xxx` 读的都是它。

#### 最小例子（Vue 3 必须写成函数）

```js
export default {
  data() {
    return {
      count: 0,
      name: "Vue"
    };
  }
}
```

#### toolkit.vue 里的真实用法（注意：这里是**对象**，不是函数）

```js
data: {
  lang: global.lang,
  batch: false,            // 是否为批量输入模式
  option: 0,
  list: { nl: global.nodeList, opp: global.outputParameters },
  valTable: [],            // 用来存储转换后的参数列表
  // ...
  winHeight: window.outerHeight,
  optionMode: 0,
  optionValue: "",
  nextPage: 0,             // 是否设置翻页操作
  global: global,          // 把外部对象也塞进 data
}
```

#### 拆解

- 🔴 **Vue 2 vs Vue 3 差异**：toolkit.vue 写 `data: { ... }`（对象）。
    
  这是 **Vue 2 根实例**才允许的写法；**Vue 3 要求 `data()` 必须是返回对象的函数**
    
  （避免多个组件实例共享同一份数据）。Vue 3 正确写法：`data() { return { ... } }`。
- 🔬 **一个关键细节**：`list: { nl: global.nodeList, ... }` 把外部对象 `global` 的数组
    
  **直接引用**进了 `data`。
  - 好处：模板里 `list.nl.length` 能反映"已选元素个数"。
  - 代价：`global` 是 `global.js` 里的全局可变对象，**组件外**直接 `global.nodeList.push()`
      
    不一定能稳定触发 Vue 重渲染（Vue 只在自己建立的响应式代理上追踪变化）。
      
    所以代码在关键变更后**手动调用 `handleElement()` 等刷新逻辑**来兜底——
      
    这是"响应式边界"的典型现象，见 5.9。
- `winHeight: window.outerHeight`：初值取窗口高度，缩放时再更新（见 5.5 / 4.5）。

---

### 5.4 `methods`：方法

**作用**：组件的行为逻辑。模板里 `@click="xxx"` 调的就是这里的方法；方法内部用 `this.xxx` 读写数据。

#### 最小例子

```js
export default {
  data() { return { n: 1 } },
  methods: {
    add() { this.n++; },                  // this 指向组件实例
    addBy(k) { this.n += k; },            // 可带参数
    async wait() {                        // 可以是 async
      await new Promise(r => setTimeout(r, 500));
      this.n++;
    }
  }
}
```

#### toolkit.vue 里的真实用法（节选）

```js
methods: {
  // ① 普通方法，内部用 this 改数据
  confirmCollectSingle: function () {
    collectSingle();
    clearEl();
    this.nextPage = 1;          // 改数据 → 界面"设置翻页"提示出现
    this.lastAction = "collectData";
  },

  // ② 带默认参数
  loopClickSingleElement: async function (type = "") {
    let name = this.tname();
    if (type == "nextPageFromIndexPage") name = "nextPageFromIndexPage";
    sendLoopClickSingle(name);
    global.nodeList[0]["node"].focus();
    await new Promise(resolve => setTimeout(resolve, 500));  // 等 500ms 再清空
    clearEl();
    this.nextPage = 0;
  },

  // ③ 模板传参进来 (e, mode)
  selectDescendents: function (e, mode = 0) {
    handleDescendents(mode);
    this.mode = mode;
  },

  // ④ 读 data 里的状态做判断
  existDescendents: function () {
    return global.nodeList.length > 0
        && global.nodeList[0]["node"].children.length > 0
        && !this.selectedDescendents;
  }
}
```

#### 拆解

- `methods` 里 **`this` 指向组件实例**，所以 `this.nextPage`、`this.tname()` 都能用。
- `async function` 可以直接写——`loopClickSingleElement` 用 `await` 等 500ms，
    
  等 Node 端把元素加回列表后再 `clearEl()`，避免竞态（注释里写得很清楚）。
- 💡 **`this` 陷阱**（和 jQuery 回调里常见）：
    
  如果方法是**箭头函数**，`this` 会绑定到外层而非组件实例。
    
  toolkit.vue 全部用 `function () {}`，所以 `this` 正确；但若你写 `onClick: () => {...}`，
    
  里面的 `this` 就丢了。这是 Vue 的经典坑（本篇 9 节再强调）。

---

### 5.5 `mounted` / `beforeDestroy`：生命周期钩子

**作用**：组件"活到某个阶段"时自动调用的函数。

```text
创建组件 → 挂到 DOM → 【mounted 触发】→ 用户操作 → 组件要被销毁 → 【beforeDestroy/beforeUnmount 触发】
```

#### 最小例子

```js
export default {
  mounted() {
    console.log("组件已挂上 DOM");
    window.addEventListener('resize', this.onResize);
  },
  beforeUnmount() {                       // Vue 3 叫法
    window.removeEventListener('resize', this.onResize);
  }
}
```

#### toolkit.vue 里的真实用法

```js
mounted() {
  this.$nextTick(() => {                  // 见 5.7
    window.addEventListener('resize', this.onResize);
  });
  if (isInIframe()) { global.iframe = true; }
  // ... 遍历 iframe，把过小的 iframe 撑大到 600px ...
},
beforeDestroy() {                         // 🔴 Vue 3 里改名 beforeUnmount
  window.removeEventListener('resize', this.onResize);
}
```

#### 拆解

- `mounted` 在组件**第一次渲染完、真实 DOM 已存在**后触发。
    
  toolkit.vue 在这里干两件事：① 监听窗口 `resize`；② 处理 iframe 高度。
- `onResize` 方法里 `this.winHeight = window.outerHeight`——
    
  窗口一缩放，`winHeight` 变 → 模板里 `:style` 的最大高度自动重算（呼应 4.5）。
- 🔴 `beforeDestroy` 在 **Vue 3 改名 `beforeUnmount`**。
    
  它的职责是"打扫卫生"：移除 `resize` 监听，避免组件销毁后监听器还挂着导致内存泄漏。
    
  （Vue 2.7 里 `beforeDestroy` 仍可用；写 Vue 3 请改用 `beforeUnmount`。）

---

### 5.6 `watch`：监听数据变化做副作用

**作用**：盯着某个数据，它一变就执行一段逻辑（"副作用"）。
  
类似 React 的 `useEffect`、Android 的 `LiveData` 监听。

#### 最小例子

```js
export default {
  data() { return { name: "" } },
  watch: {
    name: {
      handler(newVal, oldVal) {
        console.log("名字从", oldVal, "变成", newVal);
      },
      immediate: true   // 创建时立刻执行一次
    }
  }
}
```

#### toolkit.vue 里的真实用法

```js
watch: {
  nowPath: {                       // 监听 data 里的 nowPath
    handler: function (newVal, oldVal) {
      console.log("xpath:", newVal);   // 路径一变就打印
    }
  }
}
```

#### 拆解

- `handler(newVal, oldVal)`：第一个参数是**新值**，第二个是**旧值**。
- toolkit.vue 这里只打了日志；真实项目里 `watch` 常用来"数据变了 → 发请求 / 清缓存 / 校验"。
- 可选配置：`immediate: true`（立刻跑一次）、`deep: true`（监听对象内部深层变化）。
    
  （注意：toolkit.vue 这里没加 `deep`，所以只监听 `nowPath` 这个字符串本身被替换。）
- 💡 对比 `computed`：`computed` 是"由一个数据算出另一个数据"（有返回值、会缓存）；
    
  `watch` 是"数据变了去做点事"（无返回值、适合副作用）。两者别混。

---

### 5.7 `this.$nextTick`：等 DOM 更新完再动手

**作用**：Vue 改数据后，DOM 不会**立刻**变，而是"异步批量"更新。
  
`$nextTick(cb)` 让你的回调**等 DOM 真正更新完**再执行。

#### 最小例子

```js
methods: {
  change() {
    this.msg = "新内容";
    this.$nextTick(() => {
      // 到这里，页面上已经显示"新内容"了
      console.log(document.getElementById("box").innerText);
    });
  }
}
```

#### toolkit.vue 里的真实用法

```js
mounted() {
  this.$nextTick(() => {
    window.addEventListener('resize', this.onResize);
  });
},
setInput: function (batch = false) {
  this.batch = batch;
  this.page = 1;                       // 切到输入面板（DOM 还没立刻出现）
  this.$nextTick(function () {        // 等面板渲染完，再让输入框获得焦点
    document.getElementById("WTextBox").focus();
  });
}
```

#### 拆解

- `setInput` 把 `page` 设为 1（输入面板出现），但**下一行 DOM 还没画出来**，
    
  直接 `getElementById("WTextBox")` 会拿不到。
    
  包进 `$nextTick`，等 Vue 把面板渲染进 DOM 后再 `focus()`，才稳。
- 💡 一句话记忆：**"改了数据马上要操作 DOM，就包一层 `$nextTick`。"**

---

### 5.8 `import` 与 ES 模块（`.vue` 为什么能拆分文件）

`toolkit.vue` 顶部那一串 `import` 不是 Vue 语法，但它是组件能"拆文件、复用算法"的基础：


```js
import { global, isInIframe, getOS, readXPath /* ... */ } from "./global.js";
import { input, sendSingleClick /* ... */ } from "./messageInteraction.js";
import $ from "jquery";
```

- `global.js`：核心算法（XPath、元素匹配、列表维护）——第 04 篇讲过 `readXPath`。
- `messageInteraction.js`：通过 WebSocket 和 Electron 流程图通信——第 13 篇补通信背景，第 14 篇逐条分析消息。
- `jquery`：拖拽等 DOM 细节操作（第 8 节会对比 jQuery vs Vue）。

> 这些 `import` 在 **Rollup 构建**时被解析，依赖代码被组织成扩展可加载的 JS 文件；具体可能包含多个入口和共享模块，见第 11 节。
>   
> 浏览器本身原生也支持 ES Module（`type="module"`），但扩展里走打包更稳（MV3 不允许远程代码，见 03 篇 7.2）。

---

### 5.9 一个重要的"响应式边界"：global 时机

把 5.3 的细节展开讲，因为这是读 toolkit.vue 最容易迷糊的地方。

```text
toolkit.vue 的 data 里：
  list: { nl: global.nodeList, opp: global.outputParameters }
  global: global

global.js 里：
  global.nodeList = []      ← 一个普通数组
```

问题：`global.js` 在组件**外面**直接 `global.nodeList.push(node)`，
  
toolkit.vue 模板里 `list.nl.length` 会更新吗？

- **Vue 2**：组件创建时 Vue 会把 `data` 里的对象**递归**变成响应式，
    
  `list.nl` 和 `global.nodeList` 指向同一个被"观测"的数组，
    
  所以 `push` 通常能触发更新——但前提是该数组已被 Vue 观测到。
- **Vue 3**：`reactive` 用 `Proxy` 代理，外部直接持有原始引用时，
    
  只有**通过代理对象**做的修改才被追踪。

> 正因为这套跨文件共享对象的响应式行为**不可靠**，
>   
> toolkit.vue 在每次关键变更（增删选中元素）后，
>   
> 都**显式调用 `handleElement()` 重新计算并刷新**，而不是单纯依赖"数据变了界面自动变"。
>
> 💡 教学经验：**Vue 的响应式只对"它自己管理的 data"可靠**。
>   
> 把外部全局对象整个塞进 data，是一种"能用但有隐患"的历史写法。
>   
> 现代 Vue 3 更推荐用 `ref`/`reactive` 明确声明状态，或用 Pinia 管全局状态。

---

## 6. Composition API 对照：把 toolkit.vue 用 Vue 3 重写一版

前面全是 Options API（Vue 2.7 真写的）。
  
但课程叫"Vue3"，所以这一节给出 **Vue 3 官方推荐的 `<script setup>` 写法**，
  
把 toolkit.vue 的核心逻辑对照重写，你一眼能看出区别。

#### Options API（toolkit.vue 现在这样）

```js
export default {
  data() { return { page: 0, text: "", optionMode: 0 } },
  mounted() { window.addEventListener('resize', this.onResize); },
  methods: {
    setInput(batch = false) {
      this.batch = batch; this.page = 1;
      this.$nextTick(() => document.getElementById("WTextBox").focus());
    },
    toEng(v) { /* ... */ }
  }
}
```

#### Composition API（Vue 3 推荐）

```html
<template>
  <div v-if="page === 0">主操作台</div>
  <input v-model="text" />
  <button @click="setInput(false)">输入</button>
  <p>{{ toEng(tname) }}</p>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue';

// ① 用 ref 声明响应式变量（模板里直接用，不用 this）
const page = ref(0);
const text = ref("");
const optionMode = ref(0);

// ② 方法就是普通函数，直接操作 ref.value
function setInput(batch = false) {
  page.value = 1;                       // 注意要写 .value
  nextTick(() => document.getElementById("WTextBox").focus());
}

// ③ 生命周期用 onMounted / onUnmounted（对应 mounted / beforeUnmount）
function onResize() { /* ... */ }
onMounted(() => window.addEventListener('resize', onResize));
onUnmounted(() => window.removeEventListener('resize', onResize));

// ④ 过滤器没了，直接写方法（模板里 {{ toEng(x) }} 调用）
function toEng(v) { /* ... */ }
</script>
```

对照表：

| Options API（toolkit.vue）        | Composition API（Vue 3）                      |
| ------------------------------- | ------------------------------------------- |
| `data() { return { x } }`       | `const x = ref(初始值)`                        |
| `this.x` 读 / `this.x = ` 写      | `x.value` 读 / 写                             |
| `methods: { fn(){} }`           | 直接 `function fn(){}`                        |
| `mounted()`                     | `onMounted(() => {})`                       |
| `beforeDestroy()`               | `onUnmounted(() => {})`                     |
| `this.$nextTick(cb)`            | `nextTick(cb)`                              |
| `filters: { toEng(){} }`        | 普通 `function toEng(){}`，模板 `{{ toEng(x) }}` |
| `watch: { x: { handler(){} } }` | `watch(x, (n, o) => {})`                    |
| `el: '#realcontent'`            | `createApp(App).mount('#realcontent')`      |

> 💡 记住 `ref` 在 **JS 里要 `.value`、在模板里不用 `.value`**（Vue 自动拆包）。
>   
> 这是 Composition API 最常被绊的一下。

---

## 7. 一个完整小例子：待选提示组件（串起来）

把前面几篇的知识串一下，看这么一个组件（基于 toolkit.vue 真实片段）：

```html
<template>
  <div v-if="nodeList.length == 1">
    ● 已选中 {{ numOfList() }} 个{{ tname() }}，
    <span v-if="numOfReady() > 0">
      同时发现 {{ numOfReady() }} 个同类元素
    </span>
    <a v-on:mousedown="selectAll">选中全部</a>
  </div>
</template>

<script>
export default {
  data() { return { nodeList: global.nodeList } },
  methods: {
    numOfList() { return global.nodeList.length; },
    numOfReady() { return global.readyList.length; },
    tname() { /* 根据 tag 返回"链接/图片/按钮…" */ },
    selectAll() { readyToList(this.step, false); }
  }
}
</script>
```

几个关键点：

- `nodeList` 来自 `global.js` 的 `global.nodeList`（已选中的）；
- `numOfReady()` 读 `global.readyList.length`（待选的）；
- 点"选中全部" → 调 `readyToList()` → `global.readyList` 变空、`nodeList` 变多
    
  → 界面因为 `v-if` / 插值依赖这些数据，**自动更新**。

**这就是 MVVM：View(模板) ↔ ViewModel(Vue实例) ↔ Model(global 数据)。**

---

## 8. 为什么用 Vue 而不是 jQuery

项目里**两者都有**（`jquery-3.4.1.min.js` 也在 `Extension/` 里）。

|       | jQuery       | Vue3      |
| ----- | ------------ | --------- |
| 思路    | 命令式（手动改 DOM） | 声明式（改数据）  |
| 复杂 UI | 难维护（选择器满天飞）  | 轻松（模板即界面） |
| 适合    | 简单操作、拖拽细节    | 有状态的复杂界面  |

🔬 EasySpider 里 jQuery 主要用在**拖拽**这种 DOM 细节操作上：

```js
// main.js
$('.tooldrag').mousedown(function (e) { /* 拖动操作台 */ });
```

而状态驱动的界面（操作台、流程图、任务页）交给 Vue。

**混用是历史演进的结果**——早期用 jQuery，后来复杂界面多了才引入 Vue。

---

## 9. 常见坑（含 Vue 2→3 迁移）

💡 **坑 1：filters 没了（Vue 3）**
  
`{{ x | f }}` 在 Vue 3 报错。改用方法 `{{ f(x) }}` 或 `computed`。

💡 **坑 2：`beforeDestroy` 改名**
  
Vue 3 用 `beforeUnmount`，写 `beforeDestroy` 不生效。

💡 **坑 3：`data` 必须是函数（Vue 3）**
  
`data: { }` 在 Vue 3 报错，改成 `data() { return { } }`。
  
（toolkit.vue 的 `data: { }` 是 Vue 2 根实例特例。）

💡 **坑 4：`this` 指向**
  
`methods` 里用 `function () {}`，`this` 是组件实例；
  
若写成箭头函数 `() => {}`，`this` 会变成外层，读不到 `this.xxx`。
  
（toolkit.vue 全部用 `function`，没问题。）

💡 **坑 5：v-for 要加 `:key`**
  
toolkit.vue 没加 `:key`，列表增删可能复用错节点。
  
正确：`<li v-for="(item, i) in list" :key="i">`。

💡 **坑 6：改数组/对象要用能触发响应式的方式**
  
`arr.push()`、`arr.splice()`、`obj.x = y`（Vue 3 的 `reactive`）可以触发更新；
  
直接用索引 `arr[0] = x` 在 Vue 2 里**不会**触发（Vue 3 的 `reactive`/`ref` 用 Proxy 已修复此问题）。
  
这也是为什么 toolkit.vue 用 `splice` 而不是下标赋值。

💡 **坑 7：Composition API 的 `.value`**
  
`ref` 在 JS 里读写都要 `.value`，模板里不用。忘了 `.value` 是头号 bug 来源。

---

## 10. 本篇小结

```text
【认版本】
toolkit.vue 实际由 Vue 2.7 编译（package.json: "vue":"^2.7.14"）
Options API 在 Vue 3 完整保留 → 本篇概念通用
Vue-2-only 4 处：filters / beforeDestroy / data 对象 / el
  → Vue3 分别改：方法/computed、beforeUnmount、data()函数、createApp().mount()

【模板语法（toolkit.vue 全出现）】
{{ }}        插值（可放表达式、可调用方法）
v-if/else-if 条件渲染（toolkit 用 lang + page 切语言/切面板）
v-for        列表渲染（支持 (item,index)、数字范围；记得加 :key）
v-on / @     事件绑定（toolkit 多用 mousedown 抢在 click 前拦截）
v-bind / :   属性绑定（:style 对象写法里能写 JS 表达式）
v-model      双向绑定（input / select）
filters |    格式化显示（🔴Vue3 删除，改方法/computed）

【脚本 Options API】
export default {}   组件对象
el                  挂载点（🔴Vue3 用 mount()）
data                响应式状态（🔴Vue3 要 data() 函数；global 引用有响应式边界）
methods             方法（this 指向实例；可 async / 默认参数）
mounted/beforeUnmount  生命周期（监听/清理 resize）
watch               监听变化做副作用（handler(newVal,oldVal)）
this.$nextTick      等 DOM 更新完再操作
import              ES 模块，Rollup 打包进扩展

【Vue 3 现代写法】
<script setup> + ref()/reactive()/onMounted()/watch()/nextTick()
ref 在 JS 里要 .value，模板里不用

【价值】
Vue = 数据驱动界面（响应式 + 声明式）
把"改界面"从代码里拿掉：改数据，界面自动变
```

---

## 11. 打包扩展：Rollup 怎样把 `.vue` 变成可执行的 `.js`

前面我们读了 `toolkit.vue`，但 Chrome 并不能直接执行这个文件。

本节按下面的顺序讲：

```text
① Rollup 是什么，为什么项目需要它？
② 插件在 Rollup 的构建过程中分别做了什么？
③ .vue 的内容究竟发生了哪些变化，生成的 .js 为什么能执行？
④ 最后再执行命令，检查产物，加载扩展。
```

先把前三个问题讲清楚，再谈 `.crx` 和中英文发布。

🔬 这里讲的是 `Extension/manifest_v3/` 的扩展构建，实际配置使用 Rollup 2 和 Vue 2.7。

---

### 11.1 Rollup 是什么：把分散的模块组织成可以交付的程序

**Rollup 是一个 JavaScript 模块打包工具。** 它运行在开发者电脑上的 Node.js 环境中，从入口出发，沿着模块引用找到依赖，再生成输出文件。参见 [Rollup 官方介绍](https://rollupjs.org/introduction/)。

先不涉及 Vue，看一个只有两个 JS 文件的小程序。

#### 开发时：代码分在两个文件里

```js
// helper.js
export function greet(name) {
  return '你好，' + name;
}
```

```js
// main.js
import { greet } from './helper.js';
document.body.textContent = greet('同学');
```

`main.js` 要运行，必须有 `helper.js` 提供的 `greet`。

Rollup 从 `main.js` 开始，读到 `import`，就继续找 `helper.js`。这种“谁需要谁”的关系叫**依赖关系**。

#### 构建时：Rollup 把依赖关系接起来

```text
入口 main.js
  → 发现它需要 helper.js 的 greet
  → 读取 helper.js
  → 确认 greet 在哪里定义、在哪里使用
  → 把所需代码组织成输出文件
```

对于这样的小程序，输出可以理解为下面这个样子：

```js
// bundle.js，教学示意：实际代码外形取决于输出配置。
function greet(name) {
  return '你好，' + name;
}

document.body.textContent = greet('同学');
```

原来跨文件的引用关系，已经由构建工具接好了。

> **开发时可以把代码拆开写；交付时，Rollup 负责把它们组织起来。**

“打包”在这里是分析、组织代码，不是简单把文件压成 ZIP，也不是把整个项目目录照搬过去。

实际项目可以输出一个文件，也可以输出多个入口和共享模块；不必为了理解打包而假定“所有代码最终都挤进一个 JS”。

#### Rollup 与 Vue 分别在什么时候工作

| 工具 | 主要工作时间 | 主要工作 |
| --- | --- | --- |
| Rollup | 执行构建命令时 | 找依赖、组织模块、生成文件 |
| Vue 编译器 | 构建过程中，由插件调用 | 把组件模板转换成 JS 渲染函数 |
| Vue 运行时 | 浏览器加载生成的 JS 以后 | 创建组件实例，更新数据和 DOM |

所以用户在网页上点按钮时，负责更新界面的是 Vue 运行时；这时不需要 Rollup 在用户电脑上再打一次包。

---

### 11.2 为什么 Rollup 还需要插件

上面的例子只有标准 JS 模块，事情比较简单。

但 EasySpider 的入口里会出现：

```js
import Vue from 'vue';
import $ from 'jquery';
import ToolKit from './toolkit.vue';
import config from './config.json';
```

后台还有 `background.ts`，扩展还有 `manifest.json`、HTML、CSS 和图标。

问题来了：

```text
'vue' 只是一个包名，实际文件在哪？
.vue 里混着模板、脚本、样式，怎样变成 JS？
.json 是数据，怎样让 import 得到一个 JS 对象？
.ts 里有类型标注，怎样让浏览器执行？
扩展清单指向多个入口，怎样把这些入口一起构建？
```

**插件就是给 Rollup 增加这些具体处理能力的程序。**

插件安装在开发环境中，写进 `rollup.config.js`，构建时由 Rollup 调用。它们不需要在用户浏览器里作为“构建工具”运行。

#### 插件怎样插入工作过程

可以把一次模块处理粗略理解成：

```text
遇到一个引用
  → 找到对应的模块
  → 读取内容
  → 必要时转换内容
  → 分析转换后的 JS 和其中的新引用
  → 继续处理依赖
  → 组织输出，写入文件
```

Rollup 在这些阶段提供调用插件的机会，称为**钩子（hook）**。

| 阶段 | 常见钩子 | 中文理解 |
| --- | --- | --- |
| 查找模块 | `resolveId` | 这个名字对应什么模块？ |
| 读取模块 | `load` | 这个模块的内容是什么？ |
| 转换代码 | `transform` | 是否要把内容改成可分析的 JS？ |
| 生成输出 | `generateBundle` 等 | 还需要生成或调整哪些产物？ |

不同插件可能用到多个阶段。这个表解释工作机制，不表示每个插件只使用某一个钩子。参见 [Rollup 插件说明](https://rollupjs.org/plugin-development/)。

💡 **`plugins` 数组不是“每个文件必须依次经过的全部工序”。** `.vue`、JSON、TS 等文件由适合它们的插件处理，转换后产生的新依赖也会继续进入构建过程。

---

### 11.3 先看配置：入口、输出、处理工具在哪里指定

EasySpider 的 `rollup.config.js` 可以先缩成三个部分：

```js
// 教学节选：插件的 import 和配置参数暂时省略。
export default {
  input: 'src/manifest.json',
  output: {
    dir: 'dist',
    format: 'esm',
    chunkFileNames: 'chunks/[name]-[hash].js',
  },
  plugins: [
    alias(/* 参数省略 */),
    chromeExtension(/* 参数省略 */),
    simpleReloader(),
    vue(),
    replace(/* 参数省略 */),
    typescript(),
    postcss(),
    json(),
    resolve(),
    commonjs(),
    emptyDir(),
  ],
};
```

先读成三句话：

```text
input    从哪里开始构建？这里从扩展清单开始。
output   生成的文件放哪里、采用什么输出格式？这里放 dist/。
plugins  遇到不同材料时，请哪些工具参与处理？
```

`format: 'esm'` 是 Rollup 的输出格式设置；扩展插件还会处理各入口的加载方式。若产生共享模块，其文件名使用 `chunks/[name]-[hash].js` 这种形式。

现在再看这些插件具体怎样参与。

---

### 11.4 插件在打包过程中分别做了什么

下面按“构建时遇到了什么问题”来讲，而不是只背插件名字。

#### ① `chromeExtension()`：把扩展清单变成构建任务

普通 Rollup 项目可以从一个 `main.js` 开始，但本项目从 `src/manifest.json` 开始。

清单不是可执行代码，它列的是扩展有哪些入口：

```json
{
  "background": { "service_worker": "background.ts" },
  "action": { "default_popup": "popup.html" },
  "content_scripts": [
    {
      "js": ["content-scripts/main.js"],
      "css": ["style/toolkit.css"]
    }
  ]
}
```

这是清单节选。

扩展插件读它以后，知道要处理哪些脚本、页面和资源：

```text
manifest.json
  ├─ 后台入口：background.ts
  ├─ 弹出面板：popup.html → 它引用的 popup.js、CSS
  ├─ 网页脚本：content-scripts/main.js → 它 import 的组件和库
  └─ 样式、图标等资源
```

它还生成与产物路径对应的输出清单，让 Chrome 加载构建后的文件。

**它负责把“整个扩展”组织成构建任务；它不负责翻译 Vue 模板。**

真实配置还通过 `extendManifest` 从环境变量补充清单的 `key`。`dotenv/config` 用于在构建环境读取 `.env`，这属于配置准备工作。

#### ② `resolve()`：包名怎样找到实际代码

```js
import Vue from 'vue';
```

这里没有写 `./vue.js`，而是写了 npm 包名。

`@rollup/plugin-node-resolve` 会根据包的声明和模块解析规则，在安装的依赖中找到对应文件。

```text
源码中的 'vue'
  → resolve 插件查找 node_modules/vue 的包信息
  → 确定本次构建应读取的入口模块
  → Rollup 继续读取它的代码和依赖
```

`npm install` 负责把包安装到本机；`resolve()` 负责构建时找到它。两者工作不同。

#### ③ `commonjs()`：旧式模块怎样参与构建

某些库使用 CommonJS：

```js
// CommonJS 风格示意
const helper = require('./helper');
module.exports = helper;
```

`@rollup/plugin-commonjs` 帮助把这些引用和导出转换成 Rollup 能处理的模块关系。

```text
resolve()   解决“库在哪里”
commonjs()  解决“库采用的模块写法怎样接进来”
```

它们都不负责解释 `<template>` 或 `v-if`。

#### ④ `vue()`：把 `.vue` 转换成 JS 组件模块

项目实际导入：

```js
import vue from 'rollup-plugin-vue2';
```

因此 `vue()` 使用的是 Vue 2 的单文件组件构建插件。

遇到 `toolkit.vue` 时，它协调组件解析、模板编译和组件代码组装，把结果提供给后续模块处理过程。

```text
输入：.vue 的模板、脚本、样式
  → 拆分三个部分
  → 模板编译成 render 等 JS 函数
  → 脚本中的组件选项与渲染函数组合
  → 样式交给相应的样式处理流程
输出：可继续参与打包的 JS 组件模块，以及相关样式内容
```

这是 `.vue` 能进入 JS 打包过程的关键。下一节会把它的输入和输出摊开看。

🔬 依赖表中即使列着其他 Vue 插件，也要看配置实际导入谁。当前项目是 `rollup-plugin-vue2`，配套 Vue 和 `vue-template-compiler` 为 2.7 系列。

#### ⑤ `json()`：JSON 数据怎样变成可导入的值

真实代码中有：

```js
import config from './config.json';
```

而配置文件是：

```json
{"language":"zh"}
```

JSON 插件把数据转换成 JS 模块内容，等效理解为：

```js
// 教学示意，实际输出形式可能不同。
const config = { language: 'zh' };
export default config;
```

之后，源码里的 `config.language` 就能读到这个对象中的值。

它不是运行时再让浏览器去读源码目录的 JSON；这份数据在构建时参与了模块输出。

#### ⑥ `typescript()`：去掉 `.ts` 中浏览器不能直接执行的类型语法

```ts
// 编译前，教学示意
const title: string = 'EasySpider';
```

```js
// 编译后
const title = 'EasySpider';
```

项目用 `rollup-plugin-typescript2`，结合 `tsconfig.json` 处理后台等 TS 源码，再把 JS 交回构建流程。

#### ⑦ `replace()`：把构建环境中的指定值写进代码

配置中有：

```js
"process.env.NODE_ENV": JSON.stringify("production")
```

等效理解为：

```js
// 替换前
if (process.env.NODE_ENV === 'production') { /* ... */ }

// 替换后
if ("production" === 'production') { /* ... */ }
```

生成的代码使用替换后的字面值，不需要用户浏览器读取开发者的 Node 环境变量。

`JSON.stringify()` 在这里产生带引号的字符串字面量，避免把 `production` 写成一个未定义的变量名。

#### ⑧ `postcss()`：处理进入模块构建流程的 CSS

JS 和 CSS 是两种材料。CSS 不能直接当 JS 语句执行，需要样式处理。

`rollup-plugin-postcss` 让模块引用的 CSS 参与构建。样式可能以注入代码或独立资源等方式交付，具体取决于插件配置以及组件插件如何提供样式。

本项目还有清单显式引用的 `style/toolkit.css`，这类扩展资源也会随扩展输出。

**“`.vue` 变成 JS”不表示 CSS 规则都被改写成 JS 语法。** 如果通过 JS 注入，JS 只是创建样式节点、把 CSS 内容放进去，最终仍由浏览器的 CSS 系统处理。

#### ⑨ 三个辅助插件

| 调用 | 构建过程中的作用 |
| --- | --- |
| `alias()` | 将 `@` 这类别名映射到 `src` 路径，帮助解析源码引用 |
| `simpleReloader()` | watch 模式下添加扩展重载支持，方便开发验证 |
| `emptyDir()` | 清理输出目录，避免旧产物混入新结果 |

这些插件帮助组织构建和开发过程，不是把 Vue 模板翻译成 JS 的工具。

#### 用一张图把分工接起来

```text
扩展清单 ── chromeExtension ──→ 找到后台、popup、网页脚本等入口
                                      │
                         Rollup 沿着 import 查找依赖
                                      │
                 ┌────────────────────┼───────────────────┐
                 ↓                    ↓                   ↓
              npm 包                .vue                JSON / TS
       resolve 查找实际模块     Vue 插件处理组件      json / typescript 转换
       commonjs 接入旧格式       模板 → JS 函数               │
                 └────────────────────┼───────────────────┘
                                      ↓
                        Rollup 分析、组织转换后的 JS 模块
                                      ↓
                     输出 JS、清单、页面、样式、资源到 dist/
```

`replace`、样式处理和辅助插件在相应阶段参与。这张图表示职责和数据去向，不是插件钩子的精确执行顺序。

---

### 11.5 `.vue` 究竟变成了什么：把转换前后摆在一起

现在已经知道谁负责组织、谁负责转换，再回答最关键的问题。

> **`.vue` 不是把后缀改成 `.js`；它内部的内容经过了转换。**

用一个小组件代替很长的 `toolkit.vue`。

#### 第一步：原始文件里面有三种内容

```html
<!-- Counter.vue，教学组件，使用 Vue 2 写法 -->
<template>
  <button @click="count++">已点击 {{ count }} 次</button>
</template>

<script>
export default {
  data() { return { count: 0 } }
}
</script>

<style>
button { color: red; }
</style>
```

它方便人阅读，但整体不是合法 JS：

```text
<template> 不是 JS 语句
@click 不是 JS 的事件注册语法
{{ count }} 不是 JS 中显示文字的操作
<style> 中的是 CSS，也不是 JS 语句
```

所以不能直接把整个文件交给 JavaScript 引擎。

#### 第二步：插件拆出脚本中的组件选项

`<script>` 里面本来就是 JS 模块代码，取出其中的组件定义：

```js
const componentOptions = {
  data() { return { count: 0 } }
};
```

这时只是“组件有哪些数据”的说明，还没有告诉 Vue 要画什么界面。

#### 第三步：模板编译器生成渲染函数

下面是**等效教学写法**。真实 Vue 2 编译输出常带有 `_c`、`_v`、`_s` 等辅助调用，也可能有静态渲染函数，外形不一定如此。

```js
function render(h) {
  return h(
    'button',
    {
      on: {
        click: () => { this.count++; }
      }
    },
    ['已点击 ' + this.count + ' 次']
  );
}
```

逐项对应：

| 原模板内容 | 等效 JS 表达 | 解释 |
| --- | --- | --- |
| `<button>` | `h('button', ...)` | 描述一个按钮的虚拟节点 |
| `@click="count++"` | `on: { click: () => { this.count++; } }` | 给按钮提供点击处理函数 |
| `已点击 {{ count }} 次` | `'已点击 ' + this.count + ' 次'` | 读实例数据，组成显示文字 |

`h` 是 Vue 提供的创建虚拟节点函数。虚拟节点先用 JS 对象描述界面，Vue 再根据它创建或更新实际 DOM。参见 [Vue 2 渲染函数说明](https://v2.vuejs.org/v2/guide/render-function.html)。

这里没有在构建时创建网页按钮。构建时只是**生成了一段以后可以创建按钮的程序**。

#### 第四步：组件选项与渲染函数组装成 JS 模块

把上面两部分接起来，等效结果是：

```js
// Counter.vue 转换后的 JS 模块，教学示意。
const componentOptions = {
  data() { return { count: 0 } }
};

componentOptions.render = function (h) {
  return h('button', {
    on: {
      click: () => { this.count++; }
    }
  }, ['已点击 ' + this.count + ' 次']);
};

export default componentOptions;
```

现在看看这一段：变量、对象、函数、字符串、导出，**全是 JS 语法**。

`<template>` 和 `{{ }}` 等源码形式已经被它们的 JS 等效实现替代，所以 JS 引擎不需要学会解析 `.vue`。

样式则由插件安排交付：作为 CSS 资源，或者由生成的 JS 带着 CSS 文本完成注入。它不需要保留一个原始 `<style>` 区块夹在 JS 语句中。

🔬 这个中间组件模块通常可以只存在于构建过程里，不要求磁盘上先出现一个 `Counter.vue.js`。插件把结果交给 Rollup，Rollup 再生成最终文件。

---

### 11.6 Rollup 怎样把这个组件与 Vue 接起来

组件已变成 JS，但它还需要 Vue 提供 `h`、响应式和 DOM 更新能力。

入口可以这样写：

```js
// 教学入口 main.js
import Vue from 'vue';
import Counter from './Counter.vue';

new Vue(Counter).$mount('#app');
```

构建过程中，这两条引用分别走两条处理路线：

```text
import Vue from 'vue'
  → resolve 找到 Vue 的模块
  → Rollup 读取、组织所需的 Vue 运行时代码

import Counter from './Counter.vue'
  → Vue 插件把组件转换为 JS 模块
  → Rollup 将转换后的模块接入入口
```

最终产物可以粗略理解为：

```js
// bundle.js 的组成示意，不是可单独运行的完整 Vue 实现。
// ① Vue 运行时代码在这里，或在相应的共享模块中。

// ② 原 .vue 转换后的组件定义。
const Counter = {
  data() { return { count: 0 } },
  render(h) {
    return h('button', {
      on: { click: () => { this.count++; } }
    }, ['已点击 ' + this.count + ' 次']);
  }
};

// ③ 原入口的启动逻辑。
new Vue(Counter).$mount('#app');
```

这里的 `Vue` 由第①部分提供，不是浏览器自带的变量。实际构建也可能通过输出模块之间的引用来连接它们。

因此，原来的 `import Counter from './Counter.vue'` 在输出里已经有了对应的组件代码；浏览器不会再去源码目录打开 `Counter.vue`。

#### 为什么生成的 `.js` 能执行

要把三个条件一起说完整：

```text
① 内容是 JS：模板已经变成函数，组件选项也是 JS 对象。
② 依赖能找到：Vue 等库已纳入产物，并按输出模块关系连接。
③ 加载方式正确：浏览器按扩展输出清单 / 页面引用加载这些文件。
```

不是“后缀叫 `.js` 就能执行”，而是**源码语法已经转换、依赖已经连接、运行入口已经安排好**。

#### 执行以后，按钮怎样真的出现在页面上

```text
浏览器加载生成的 JS
  → 执行 new Vue(Counter)，创建实例
  → data() 提供 count = 0
  → Vue 调用 render(h)
  → 得到描述按钮和文字的虚拟节点
  → Vue 创建实际 DOM，挂到 #app
  → 用户点击，事件函数使 count 加 1
  → Vue 追踪到数据变化，再渲染、更新按钮文字
```

这里才是运行时。

> **模板编译器把界面写法翻译成程序；Vue 运行时执行这段程序；Rollup 把程序和所需依赖组织成可交付文件。**

---

### 11.7 回到 EasySpider：完整追踪一次 `npm run build`

`package.json` 中有：

```json
"build": "rollup -c"
```

所以执行 `npm run build`，就是让 npm 启动项目安装的 Rollup，`-c` 表示读取配置。

#### 构建阶段：发生在开发者电脑上

```text
npm run build
  → 执行 rollup -c
  → 读取 rollup.config.js：入口、输出、插件
  → chromeExtension 读取 src/manifest.json
  → 找到 content-scripts/main.js 等入口
  → 读到 main.js 的 import ToolKit from './toolkit.vue'
  → Vue 插件解析组件，把模板编译成渲染函数，组装 JS 组件模块
  → 继续处理组件 import 的 global.js、通信模块、JSON、npm 库等依赖
  → resolve / commonjs 等插件帮助接入 Vue、jQuery 等代码
  → 后台 TS、样式、环境值等由各自插件处理
  → Rollup 组织代码，扩展插件处理相应清单和资源引用
  → 将生成结果写进 dist/
```

读出来的依赖会继续进入同一处理过程；不是只处理一层 `import` 就停。

输出目录包含构建后的 JS、扩展清单以及所需页面、样式、图标等，具体文件名以实际产物中的引用为准。

`toolkit.vue` 的逻辑可能进入 content script 产物或相关模块中，**不保证生成一个恰好叫 `toolkit.js` 的文件**。

当前配置也没有显式配置 JS 压缩插件；“构建”不等于一定把所有代码压缩成一个文件。

#### 运行阶段：发生在 Chrome 中

EasySpider 的 `main.js` 有下面的真实代码（节选）：

```js
function generateToolkit() {
    $(".tooltips").html(`
    <div id="realcontent"></div>
`);
    global.app = new Vue(ToolKit);
    // 拖拽等后续代码省略
}
```

结合 `toolkit.vue` 组件选项中的 `el: '#realcontent'`：

```text
Chrome 加载 dist/ 中的扩展
  → 按输出清单在匹配网页运行 content script
  → generateToolkit() 创建 #realcontent 挂载位置
  → new Vue(ToolKit) 创建操作台实例
  → ToolKit 中已经有构建生成的渲染函数
  → Vue 执行渲染函数，把界面挂到 #realcontent
  → 之后由 Vue 根据数据变化更新操作台
```

最后做一次口头检查：

| 问题 | 回答 |
| --- | --- |
| 谁把模板写法转换成 JS 函数？ | Vue 插件调用的模板编译器 |
| 谁把组件、入口和库组织成输出？ | Rollup 与相应插件 |
| 谁在网页里真正渲染操作台？ | Vue 运行时 |
| Chrome 要直接执行 `.vue` 吗？ | 不需要，它加载构建后的 JS 和资源 |
| 这时一定要有 `.crx` 吗？ | 不需要，构建后的扩展目录可直接用于开发加载 |

下面再动手运行命令、检查输出，最后才做 `.crx` 封装和双语言发布。

---
### 11.8 动手走一遍：先构建，再加载目录验证

以下命令在 **EasySpider 项目根目录**打开的 PowerShell 中执行。

#### 第一步：进入扩展项目，检查工具

```powershell
cd Extension/manifest_v3
node --version
npm --version
```

Node.js 用来运行 Rollup、`package.js` 等工具；npm 用来安装依赖、执行脚本。

这两条版本命令都应能输出版本号。如果找不到命令，先安装 Node.js 并重新打开终端。

#### 第二步：安装项目依赖

```powershell
npm install
```

它会读取 `package.json`，结合 `package-lock.json` 安装依赖。

```text
安装前：有源码和构建配置
安装后：多出 node_modules/，里面有 Rollup、Vue、编译插件等
```

依赖已装好且没有变化时，不需要每次构建都重装。

项目带有锁文件；需要严格按锁文件重建依赖环境时可使用 `npm ci`，它会重建 `node_modules/`，且要求依赖声明与锁文件一致。

#### 第三步：构建一次

```powershell
npm run build
```

成功后应出现 `dist/`，至少检查：

```powershell
Test-Path ./dist/manifest.json
Get-Content ./dist/manifest.json
Get-ChildItem ./dist
```

检查的不只是“有目录”，还要看：

```text
① dist/manifest.json 存在
② 清单引用的脚本、HTML、CSS、图标在产物目录中能找到
③ 后台引用已经指向构建后的 JS，而不是要求 Chrome 执行源码 TS
④ 如果引用了 chunks/ 下的文件，这些文件也完整保留
```

这里不写死所有产物文件名：插件可能重写入口和生成文件名，**以实际输出清单及 HTML 中的引用为准**。

#### 第四步：Chrome 加载 `dist/`

```text
① 打开 chrome://extensions
② 打开“开发者模式”
③ 点“加载已解压的扩展程序”
④ 选择 Extension/manifest_v3/dist 目录
⑤ 查看扩展卡片是否出现错误
⑥ 打开一个允许扩展运行的普通 http / https 页面，检查操作台和 popup
```

🔴 选的是 `dist/`，不是源码 `src/`，也不是包含 `package.json` 的项目根目录。

`src/` 中的清单仍指向 `.ts` 和带构建依赖的源码；项目根目录则没有作为扩展入口的根级清单。

加载未打包目录的方式见 [Chrome 官方开发说明](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked)。

🔬 EasySpider 的 popup 和部分操作会连接 `ws://localhost:8084`。要验证完整通信，需要配合桌面端提供的服务；只验证扩展加载时，应把连接失败和构建错误分开排查。

---

### 11.9 开发模式：改完代码以后，哪几处需要更新

开发时可以执行：

```powershell
npm run dev
```

它等价于 `rollup -c -w`：先构建，再持续等待源码变化。终端不会马上退出，结束时按 `Ctrl+C`。

```text
修改 src/content-scripts/toolkit.vue
  → watch 检测到变化
  → 重新生成 dist/
  → simpleReloader 提供扩展重载支持
  → 在浏览器中验证新的界面
```

💡 原来的“热重载”容易让人以为这是 Vue 网页开发中的组件 HMR。这里更准确地理解成**自动重建 + 扩展重载支持**；不要期待组件状态一定保留。

如果没有看到变化，按这条链检查：

```text
源码已保存？
  → 终端是否显示这次构建成功？
  → Chrome 加载的是这份 dist/，还是 ElectronJS 里的旧版本？
  → 必要时在扩展卡片点重新加载
  → 刷新目标网页，让已有页面重新加载 content script
  → 关闭并重新打开 popup
```

重新构建只改了磁盘文件，不代表旧标签页里已经运行的脚本会自行替换。

---

### 11.10 `.crx` 封装：为什么命令后面还要跟目录

本地调试通过后，如果需要 `.crx`，再做这一层。

项目的脚本只有：

```json
"crx": "crx3"
```

它没有写死输入目录。因此手动封装 `dist/` 应执行：

```powershell
npm run crx -- dist
```

拆开看：

```text
npm run crx    找到 scripts.crx，也就是 crx3
--             告诉 npm：后面的参数传给这个脚本
 dist          告诉 crx3：读取 dist 这个扩展目录

最终执行：crx3 dist
```

`.crx` 封装会把扩展文件归档并签名；它不会再替你编译 `.vue`，所以要先完成构建。

按工具的目录命名规则，通常得到 `dist.crx`，并使用或生成对应的签名私钥文件；具体选项见 [crx3 项目文档](https://github.com/ahwayakchih/crx3#usage-cli)。后续为同一签名身份打包时应复用相应私钥，私钥不要放进公开分发的扩展文件中。

#### `.crx`、`.zip`、目录各自用在哪里

| 形式 | 本节中的用途 |
| --- | --- |
| 已构建的扩展目录 | 本地“加载已解压的扩展程序”；当前桌面端也使用目录安装 |
| `.crx` | 带签名的扩展封装；能否直接安装取决于浏览器及分发策略 |
| `.zip` | Chrome Web Store 上传的扩展文件归档 |

🔴 不要把“生成了 `.crx`”等同于“任何 Chrome 都能拖进去安装”。Chrome 对商店外安装有分发限制，课堂调试直接加载目录即可。见 [Chrome 扩展分发说明](https://developer.chrome.com/docs/extensions/how-to/distribute)。

商店发布通常上传 ZIP，ZIP 根层应直接包含 `manifest.json`，不要多包一层 `dist/`。见 [Chrome Web Store 发布说明](https://developer.chrome.com/docs/webstore/publish)。

---

### 11.11 双语言发布：逐段读懂 `package.js`

前面是手动构建一个版本；项目还提供：

```powershell
npm run package
```

这个命令在 `Extension/manifest_v3/` 内执行，运行的是 `node package.js`。

> 它把“改语言 → 构建 → 改目录名 → 封装 → 复制”做两遍，先英文，再中文。

#### 第一段：读配置，把语言设成英文

真实代码（节选）：

```js
let config = fs.readFileSync(
  path.join(__dirname, `src/content-scripts/config.json`), 'utf8'
);
config = JSON.parse(config);

config.language = "en";
let data = JSON.stringify(config);
fs.writeFileSync(
  path.join(__dirname, `src/content-scripts/config.json`), data,
  (err) => { if (err) { throw err; } }
);
```

逐行解释：

```text
readFileSync       把配置文件读成字符串
JSON.parse         字符串 → JS 对象
config.language    把当前对象里的语言设为 en
JSON.stringify     JS 对象 → JSON 字符串
writeFileSync      把修改写回源码配置文件
```

💡 `__dirname` 是脚本所在目录。当前 `package.js` 用 `fileURLToPath(import.meta.url)` 和 `path.dirname()` 算出它，方便定位文件。

为什么要先改配置再构建？

> 因为 `global.js`、`popup.js` 会导入这个 JSON，语言值在构建时参与输出。英文配置构建一次，中文配置再构建一次，就得到两个版本。

它们用的是同一套源码，不需要维护两份 `toolkit.vue`。

#### 第二段：构建，然后给产物目录改名

下面保留关键调用，省略源码中传给 `execSync` 的第二个参数：

```js
execSync(`npm run build`);
fs.renameSync(
  path.join(__dirname, `dist/`),
  path.join(__dirname, `EasySpider_en`)
);
```

```text
构建结束：dist/ 中是英文版
改名之后：EasySpider_en/ 中是英文版，dist/ 被移走
```

下一轮中文构建会重新生成 `dist/`，所以改名可以把英文产物保存下来。

🔬 `execSync` 的关键是 **Sync（同步）**：当前外部命令完成后才继续；命令失败通常会抛异常。

源码把回调函数写在第二个参数位置，这不是 `execSync` 的回调用法，不能据此认为它正确实现了异步日志或错误处理。理解发布顺序时，应抓住实际执行的命令和同步等待行为。

同样，`writeFileSync` 的第三个参数不是错误回调；不要把这些写法当成 Node.js API 范本照抄。

#### 第三段：封装英文目录，复制两种产物

关键调用（同样省略 `execSync` 的第二个参数）：

```js
execSync(`npm run crx EasySpider_en`);
fs.copyFileSync(
  path.join(__dirname, './EasySpider_en.crx'),
  path.join(__dirname, '../../ElectronJS/EasySpider_en.crx')
);
copyFolderSync(
  path.join(__dirname, './EasySpider_en'),
  path.join(__dirname, '../../ElectronJS/EasySpider_en')
);
```

逐行拆：

```text
crx EasySpider_en   把已经构建的英文目录封装为 EasySpider_en.crx
copyFileSync       复制单个 .crx 文件到 ElectronJS/
copyFolderSync     复制整个扩展目录到 ElectronJS/
../../ElectronJS   从 manifest_v3/ 向上两层，再进入 ElectronJS/
```

源码使用 `npm run crx EasySpider_en` 传目录；手动操作时可使用显式分隔形式 `npm run crx -- EasySpider_en`，含义更清楚。

#### 第四段：换成中文，把相同过程再做一遍

```text
config.language = "zh"
  → 写回 config.json
  → npm run build
  → dist/ 改名为 EasySpider_zh/
  → 封装为 EasySpider_zh.crx
  → 复制 .crx 和目录到 ElectronJS/
```

完整调用顺序：

```text
英文：写 en → 构建 → 保存 EasySpider_en → crx → 复制
中文：写 zh → 构建 → 保存 EasySpider_zh → crx → 复制
```

#### 跑完应该看到什么

```text
Extension/manifest_v3/
  EasySpider_en/       英文版构建目录
  EasySpider_zh/       中文版构建目录
  EasySpider_en.crx    英文封装文件
  EasySpider_zh.crx    中文封装文件

ElectronJS/
  EasySpider_en/       复制来的英文扩展
  EasySpider_zh/       复制来的中文扩展
  EasySpider_en.crx
  EasySpider_zh.crx
```

按这个脚本的正常完成路径，最后的 `dist/` 已改名为 `EasySpider_zh/`，所以**跑完 package 没有 dist 并不代表失败**。

还要知道它的实际副作用：

- 构建前会尝试删除原有的 `EasySpider_en/`、`EasySpider_zh/`。
- 复制时会替换 `ElectronJS/` 中同名目录和 `.crx` 文件。
- 最后一次写入是 `language: "zh"`，脚本没有恢复运行前的语言配置。

所以日常改一个按钮，用 `build` 或 `dev` 就够了；需要更新供桌面端使用的中英两版时，再用 `package`。

---

### 11.12 桌面端怎样用到这些产物

当前工作区的 `ElectronJS/main.js` 会根据语言选择**解压后的扩展目录**，关键代码是：

```js
if (lang == "zh") {
    easySpiderPath = path.join(__dirname, "EasySpider_zh");
} else {
    easySpiderPath = path.join(__dirname, "EasySpider_en");
}
const easySpiderId = await webExtension.install(
    ExtensionData.setPath(easySpiderPath)
);
```

把最后一段路接上：

```text
扩展源码
  → Rollup 构建
  → package.js 保存中英文目录并复制到 ElectronJS/
  → 桌面端启动浏览器时，选择对应语言目录安装扩展
  → Chrome 执行扩展
  → Vue 渲染操作台
```

🔬 `package.js` 也复制了 `.crx`，但当前这段桌面端安装代码实际使用目录。讲“集成到桌面端”时，要以实际加载代码为准。

**扩展更新了，不等于桌面安装包已经重新制作好了。** `npm run package` 在这里负责准备扩展产物；桌面程序的发布还要走 Electron 自己的构建流程。

---

### 11.13 MV3 为什么要求代码放在扩展包里（重点）

这里最容易出现一个误解：

> “MV3 必须使用 Rollup，否则不能运行。”

真正的约束是：**扩展执行的代码应随扩展提供，不能从远程服务器下载代码再执行。** Rollup 是本项目用来满足这个要求、处理源码的一种工具。见 [Chrome 关于远程托管代码的说明](https://developer.chrome.com/docs/extensions/develop/migrate/remote-hosted-code)。

```text
远程 CDN 下载 Vue，再执行     → 远程代码问题
把 Vue 放进扩展本地文件       → 代码随扩展提供
把 Vue 通过 Rollup 构建进产物 → 本项目采用的方式
```

第 3.1 节的例子写的是 `<script src="js/vue.global.js">`，其实是**本地脚本引用**。是否远程加载，要看 `src` 的实际地址，不能只凭“用 script 标签”判断。

03 篇里直接写本地 `content.js` 的最小扩展，不用任何构建工具也能运行。

EasySpider 需要构建，是因为用了 `.vue`、`.ts` 和 npm 模块依赖；MV3 的要求则解释了为什么所需代码要随扩展产物一起交付。

---

### 11.14 常见问题：沿着出错的那一步查

| 现象 | 先检查什么 | 原因和处理方向 |
| --- | --- | --- |
| 找不到 `package.json` 或 npm 脚本 | 终端当前目录 | 四个脚本定义在 `Extension/manifest_v3/package.json` |
| 找不到 Rollup 或构建插件 | 安装依赖的结果 | `npm install` 必须成功，且要包含构建所需的开发依赖 |
| 构建报错但 `dist/` 还在 | 终端错误、文件更新时间 | 目录存在可能只是旧产物；先解决构建错误 |
| Chrome 报清单缺失 | 加载的目录 | 目录根层必须直接有 `manifest.json` |
| 修改 `.vue` 后看不到变化 | 构建、扩展重载、网页刷新 | 三步分别更新磁盘文件、扩展和已有网页脚本 |
| `.crx` 命令失败或没有预期输入 | 命令有没有目录参数 | 手动构建后用 `npm run crx -- dist` |
| 桌面端仍是旧界面 | `ElectronJS/EasySpider_zh` 或 `_en` | 只构建 `dist/` 不会自动更新桌面端的副本 |
| package 后找不到 `dist/` | 中英文产物目录 | 正常流程把它分别改名保存了 |
| 语言修改不生效 | 配置是否重新构建、加载哪份产物 | 改源码 JSON 不会改掉浏览器里正在运行的旧代码 |
| 操作台出现但通信失败 | 本地服务、WebSocket 错误 | 检查桌面服务和 8084 端口，区分运行问题与构建问题 |

🔴 如果 Node 或插件版本不兼容，保留具体报错并检查项目锁定的版本和 API。不要看到错误就把 Vue、Rollup 和插件全部升级：这是 Vue 2.7 的构建链，版本需要配套。

---

### 11.15 做一个小实验：验证你理解了流程

选 `toolkit.vue` 中一处固定提示文字，在文字末尾加上“（课堂实验）”。

```text
① 改 src/content-scripts/toolkit.vue 对应内容并保存
② npm run build
③ Chrome 加载 / 重新加载 dist/
④ 刷新目标网页，观察文字变化
⑤ 恢复源码中的提示文字，再构建、重载、刷新
```

再想两个问题：

**为什么只保存源码，旧网页里不会马上变？**

因为网页执行的是已经加载的构建产物，源码文件、磁盘产物和页面中运行的脚本不是同一份状态。

**为什么这里不用生成 `.crx`？**

因为 Chrome 能直接加载构建后的目录，封装不参与这次界面验证。

---

### 11.16 把整条路记住

```text
【本地开发】
进入 Extension/manifest_v3/
  → npm install（准备工具和库）
  → npm run build（一次构建）或 npm run dev（持续监听）
  → Chrome 加载 dist/
  → 验证、修改、重建、重载、刷新

【需要 .crx】
构建后的目录 → npm run crx -- dist → 封装文件

【供桌面端使用的中英两版】
npm run package
  → 写 en → 构建 → EasySpider_en → 封装、复制
  → 写 zh → 构建 → EasySpider_zh → 封装、复制
  → ElectronJS 根据语言安装对应目录

【每一层管什么】
Vue 编译插件    把模板变成 render 函数
Rollup / 插件   处理依赖、脚本、清单、样式、资源，生成扩展目录
Chrome          按输出清单加载扩展
Vue 运行时      创建实例、维护响应式状态、渲染操作台
crx3            给已构建的扩展加上封装和签名
package.js      把两种语言的构建和复制串起来
```

---

返回目录：[README.md](/easyspider/directory) ｜ 上一篇：[10.选中子元素与预览表：先用 DFS 生成字段，再转换成表格](/easyspider/chapter-10) ｜ 下一篇：[12.toolkit.vue：怎样画出操作台、显示表格并修改选择](/easyspider/chapter-12)
