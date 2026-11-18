# 26.Node.js 与 Express：任务存取与本地文件服务

> EasySpider 没有数据库。你在界面上建的每一个任务，最终都变成一个 `tasks/<id>.json` 文件。

> 界面（浏览器窗口）不能直接读写硬盘，而真正能读写的 Electron 主进程又看不到界面上的输入。中间那座桥，就是 `ElectronJS/server.js` 里那个监听在 `127.0.0.1:8074` 的本地 HTTP 服务。

> 这一篇讲这座桥是怎么搭起来的：路由怎么分派、任务 JSON 怎么落盘、上传的 Excel 怎么回传、执行进程又是怎么被拉起来的。

**本篇结构**（和第 06 篇一样）：

```text
第一部分：先写一个「迷你任务管理服务」，跟 EasySpider 完全无关，你自己就能跑
第二部分：再看 EasySpider 的 server.js 是怎么做的，逐行拆真实代码
```

---

---

# 第一部分：先自己写一个「迷你任务管理服务」（与 EasySpider 无关）

## 1. 先看清问题

### 1.1 场景

假设你在做一个"可视化爬虫配置器"，界面是这样一摞网页：

```text
taskList.html    任务列表页（列出所有任务）
taskInfo.html    任务信息页（改名字、改网址）
FlowChart.html   流程图编辑页（拖拽出一串操作）
executeTask.html 执行页（填参数、点"开始执行"）
```

这些页面需要**持久化**：你关掉软件，明天再打开，昨天配的任务还得在。

同时它们还需要**互通**：流程图页做完的任务，执行页要能拿到。

### 1.2 输入和输出

把需求翻译成接口，就是四个动作：

| 动作 | 输入 | 输出 |
|---|---|---|
| 列出任务 | 无 | `[{id, name, url}, ...]` |
| 读取任务 | `id` | 整个任务对象（含流程图 `graph`） |
| 保存任务 | 整个任务对象 | `id`（新建时由服务端分配） |
| 删除任务 | `id` | 成功/失败 |

### 1.3 为什么不能"直接写文件"

你可能会问：页面里用 `localStorage` 不就完了？

问题在于：

- `localStorage` 只有 5MB，一个带几十个节点的流程图 JSON 轻松超；
- 执行任务的是**另一个进程**（Python 打包的可执行文件），它读不到浏览器的 `localStorage`；
- 用户想备份、想手动改任务，文件比浏览器存储友好得多。

所以必须**真的写到硬盘**，而且是**所有进程都能找到的同一个位置**。

> 💡 EasySpider 的解法：起一个本地 HTTP 服务，让"写文件"这件事变成"发一个请求"。
> 谁都能发请求（浏览器页面、Python 进程、命令行），于是谁都能存取任务。

---

## 2. 补最小背景知识

要写这个服务，只需要四样东西。

### 2.1 Node.js：让 JavaScript 能碰硬盘

JavaScript 本来只能在浏览器里跑，浏览器给它的能力是"操作 DOM、发请求"，**没有文件系统**。

Node.js 把 Chrome 的 JS 引擎（V8）单独拎出来，配上一套"操作系统能力"的模块：

```text
浏览器里的 JS：   DOM、fetch、localStorage
Node.js 里的 JS： fs（读文件）、http（开服务）、child_process（起进程）、path（拼路径）
```

验证一下——在浏览器 Console 里敲 `require` 会报 `require is not defined`；在 Node.js 里：

```js
const fs = require("fs");            // 引入内置模块
fs.writeFileSync("hello.txt", "你好");  // 直接写硬盘
console.log(fs.readFileSync("hello.txt", "utf8"));  // 再读出来
```

> 这就是 EasySpider 为什么能在 Electron 里用 JS 管理任务文件——Electron 的主进程就是 Node.js。

### 2.2 一个 HTTP 请求到底在传什么

不用背，记住三块就够：

```text
请求行   GET /task?id=33 HTTP/1.1
请求头   Origin: http://localhost:8074
         Content-Type: application/json
请求体   {"name":"我的任务","graph":[...]}     ← GET 请求没有请求体
```

对应到 Node.js 里：

| HTTP 概念 | 代码里怎么拿 |
|---|---|
| 方法（GET/POST） | `req.method` |
| 路径（`/task`） | `url.parse(req.url).pathname` |
| 查询串（`?id=33`） | `req.query.id`（Express）/ `url.parse(req.url, true).query.id`（原生） |
| 请求头 | `req.headers["origin"]` |
| 请求体 | 原生：自己拼 `req.on("data")`；Express：装了 `express.json()` 后直接 `req.body` |

响应也三块：状态码、响应头、响应体。

```js
res.writeHead(200, { "Content-Type": "application/json" });  // 状态 + 头
res.write(JSON.stringify({ id: 33 }));                        // 体
res.end();                                                    // 结束（必须调，否则浏览器一直转圈）
```

### 2.3 Express 到底省了什么

原生 `http` 模块能开服务，但所有脏活得自己干：

```js
// 原生写法：判断方法、判断路径、拼请求体、解析 JSON……全手写
const server = http.createServer((req, res) => {
  let body = "";
  req.on("data", chunk => body += chunk);       // ① 自己拼请求体
  req.on("end", () => {
    if (req.method === "GET" && req.url === "/tasks") {
      // ...
    } else if (req.method === "POST" && req.url.startsWith("/task")) {
      const data = JSON.parse(body);            // ② 自己解析
      // ...
    } else {
      res.writeHead(404); res.end();            // ③ 自己兜底
    }
  });
});
```

Express 把上面每一样都换成一行：

| 脏活 | 原生 http | Express |
|---|---|---|
| 路由匹配 | 手写 `if/else` 比字符串 | `app.get("/tasks", fn)` |
| 解析请求体 | `req.on("data")` + `JSON.parse` | `app.use(express.json())` |
| 解析查询串 | `url.parse(req.url, true).query` | `req.query` |
| 返回 JSON | `writeHead` + `JSON.stringify` + `end` | `res.json(obj)` |
| 静态文件 | 自己读、自己查 MIME | `app.use(express.static("public"))` |
| 中间件（日志/鉴权/CORS） | 自己塞进每个分支 | `app.use(fn)` |

> ⚠️ **一个重要的预告**：EasySpider 的 8074 端口**并没有用 Express**，用的就是上面那种"原生 http + 一长串 else-if"的写法（见 §7）。
> Express 在本项目里只承担了一个 `/excelUpload` 接口，监听在 **8075**。这是一个很多人会猜错的点。

### 2.4 用 `fs` 读写 JSON：就三个函数

```js
fs.readFileSync(path, "utf8")           // 读成字符串；文件不存在会抛异常
fs.writeFileSync(path, str, "utf8")     // 写字符串；目录不存在会抛异常
fs.readdirSync(dir)                     // 列出目录里的文件名数组
```

配 `JSON.parse` / `JSON.stringify` 就能存对象了：

```js
const task = JSON.parse(fs.readFileSync("33.json", "utf8"));  // 字符串 → 对象
fs.writeFileSync("33.json", JSON.stringify(task), "utf8");    // 对象 → 字符串
```

配套的目录操作：

```js
fs.existsSync(dir)      // 目录在不在
fs.mkdirSync(dir)       // 建目录
fs.statSync(path).mtime // 最后修改时间（任务列表要按它排序）
```

### 2.5 `express.static`：把整个目录变成网站

```js
app.use(express.static(path.join(__dirname, "public")));
```

一行之后，`public/index.html` 就能通过 `http://localhost:8074/index.html` 访问，
`public/style.css` 通过 `http://localhost:8074/style.css` 访问。

它内部做的事：拿到请求路径 → 拼到目录后面 → 读文件 → 按扩展名查 MIME → 返回。

> 🔬 **安全提醒**："把用户给的路径拼到目录后面"这件事天然有 **路径穿越** 风险——
> 请求 `/../../Windows/win.ini` 就能读出目录外的文件。所以任何手写版都必须做校验（见 §4 与 §11）。

### 2.6 CORS：本机服务也要防

浏览器有一条规则：A 网站的页面用 JS 请求 B 网站，B 必须在响应头里写
`Access-Control-Allow-Origin` 允许它，否则浏览器把结果丢掉。

对 `localhost:8074` 这种本地服务，**危险在于：任何网站都能请求它**。

你一边开着 EasySpider，一边逛到一个恶意网页，那个网页就能发：

```js
fetch("http://localhost:8074/deleteTask?id=33");  // 删你的任务
```

浏览器会照发（这叫 **CSRF**），而服务端如果不校验来源，就照做。

唯一的防线是看 `Origin` 头：不是本机来的，一律拒绝。

```js
const LOCAL_ORIGIN_RE = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i;
//                       ↑ http 或 https  ↑ 三种本机写法          ↑ 可选端口   ↑ 忽略大小写
```

---

## 3. 从零写一个完整可运行的最小例子

### 3.1 目录结构

```text
mini-task-server/
├── package.json     ← 依赖清单
├── server.js        ← 全部逻辑，约 90 行
├── public/
│   └── index.html   ← 一个极简前端，验证接口能通
└── tasks/           ← 运行时自动创建，存 0.json / 1.json / ...
```

### 3.2 package.json

```json
{
  "name": "mini-task-server",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "express": "^4.21.2"
  }
}
```

### 3.3 server.js（完整，带中文注释）

```js
/* =============================================================
 * mini-task-server/server.js
 * 一个「迷你任务管理服务」：Express + fs，四个路由 + 一个静态目录
 * 跑起来： npm install && node server.js
 * 打开：   http://localhost:8074/
 * ============================================================= */

// ① 引入模块。Node.js 内置模块直接写名字，第三方模块去 node_modules 找
const express = require("express");   // Web 框架
const fs = require("fs");             // 文件系统（内置）
const path = require("path");         // 路径拼接（内置）

const app = express();                              // ② 创建一个应用对象
const TASKS_DIR = path.join(__dirname, "tasks");    // ③ 任务文件的存放目录

// ④ 中间件：把请求体里的 JSON 文本解析成 req.body 对象
//    没有这一行，req.body 恒为 undefined
app.use(express.json({ limit: "10mb" }));           // 任务 JSON 可能很大，放宽上限

// ⑤ 中间件：CORS 白名单——只放行本机来源（对应 §2.6 的 CSRF 风险）
const LOCAL_ORIGIN_RE = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i;
app.use((req, res, next) => {
  const origin = req.headers.origin;                // 浏览器跨域请求才会带这个头
  if (!origin || LOCAL_ORIGIN_RE.test(origin)) {    // 没有 = 同源或 curl，放行
    res.setHeader("Access-Control-Allow-Origin", origin || "*");
    res.setHeader("Vary", "Origin");                // 告诉缓存：不同 Origin 结果不同
    return next();                                  // 交给后面的路由处理
  }
  res.status(403).send("Origin not allowed");        // 非本机来源，直接 403
});

// ⑥ 启动时保证目录存在，否则第一次写文件会崩
if (!fs.existsSync(TASKS_DIR)) {
  fs.mkdirSync(TASKS_DIR);
}

/* ---------- 工具函数 ---------- */

// ⑦ 把一条任务写到 <id>.json。
//    注意 id 和 task.id 可以不同：逻辑删除时要用原文件名写，但内容里 id 已改成 -2
function writeTask(id, task) {
  const file = path.join(TASKS_DIR, id + ".json");
  fs.writeFileSync(file, JSON.stringify(task), "utf8");
}

// ⑧ 读出 <id>.json。文件不存在 / 内容不是 JSON 都会抛异常，由调用方 try-catch
function loadTask(id) {
  const file = path.join(TASKS_DIR, id + ".json");
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

// ⑨ 算下一个可用 id：现有最大 id + 1；一个都没有就从 0 开始
function nextId() {
  const names = fs.readdirSync(TASKS_DIR)
    .filter(n => n.endsWith(".json"))      // 只留 .json
    .map(n => parseInt(n));                // "33.json" → 33
  return names.length === 0 ? 0 : Math.max(...names) + 1;
}

/* ---------- 路由 1：列出所有任务（精简版，不要完整 graph） ---------- */
app.get("/tasks", (req, res) => {
  const list = fs.readdirSync(TASKS_DIR)
    .filter(n => n.endsWith(".json"))
    .map(n => {
      const t = loadTask(parseInt(n));
      return {
        id: t.id,
        name: t.name,
        url: (t.links || "").split("\n")[0],   // 网址是多行的，列表页只要第一行
      };
    })
    .filter(t => t.id !== -2);                 // -2 = 已逻辑删除，不显示
  res.json(list);                              // res.json 会自动设 Content-Type 并序列化
});

/* ---------- 路由 2：读取单个任务的完整内容 ---------- */
app.get("/task", (req, res) => {
  const id = parseInt(req.query.id);           // ?id=33 → req.query.id 是字符串 "33"
  try {
    res.json(loadTask(id));                    // 原样把整个 JSON 吐回去
  } catch (e) {
    res.status(404).json({ error: "Cannot find task " + id, status: false });
  }
});

/* ---------- 路由 3：保存（新建 or 更新，看 id） ---------- */
app.post("/task", (req, res) => {
  const task = req.body;                       // 有 express.json()，这里已经是对象
  if (task.id === undefined || task.id === -1) {
    task.id = nextId();                        // -1 是"新任务"的约定，由服务端分配 id
  }
  writeTask(task.id, task);
  res.send(String(task.id));                   // ★ 返回纯文本 id，不是 JSON（EasySpider 也这么干）
});

/* ---------- 路由 4：删除（逻辑删除，不删文件） ---------- */
app.delete("/task", (req, res) => {
  const id = parseInt(req.query.id);
  try {
    const task = loadTask(id);
    task.id = -2;                              // ★ 只改标记，文件还在（可恢复）
    writeTask(id, task);                       // ★ 注意：仍然写到原来的文件名
    res.json({ success: "deleted", status: true });
  } catch (e) {
    res.status(404).json({ error: "Cannot find task " + id, status: false });
  }
});

/* ---------- 路由 5：静态目录 ---------- */
// 放在最后：前面没匹配上的请求才来这里找静态文件
app.use(express.static(path.join(__dirname, "public")));

/* ---------- 启动 ---------- */
app.listen(8074, "127.0.0.1", () => {         // ★ 只监听 127.0.0.1，外网访问不到
  console.log("迷你任务服务已启动： http://localhost:8074");
});
```

### 3.4 public/index.html（验证接口能通）

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>迷你任务管理</title>
</head>
<body>
  <h2>任务列表</h2>
  <ul id="list"></ul>
  <button onclick="addTask()">新建任务</button>
  <pre id="log"></pre>

<script>
// 页面本身就是在 8074 上取的，和接口同源，直接用 location.origin
const API = location.origin;

function log(s) { document.getElementById("log").textContent += s + "\n"; }

// ① 列出任务
async function refresh() {
  const res  = await fetch(API + "/tasks");           // GET
  const list = await res.json();
  document.getElementById("list").innerHTML =
    list.map(t => "<li>#" + t.id + " " + t.name + " — " + t.url + "</li>").join("");
}

// ② 新建任务
async function addTask() {
  const task = {
    id: -1,                                            // -1 = 请服务端分配
    name: "任务" + Math.floor(Math.random() * 100),
    links: "https://www.jd.com\nhttps://www.taobao.com",
    graph: [ { option: 1, title: "打开网页" } ],        // 流程图，这里简化成一行
  };
  const res = await fetch(API + "/task", {             // POST
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(task),
  });
  const id = await res.text();                         // ★ 服务端返回的是纯文本 id
  log("新建成功，id = " + id);
  refresh();
}

refresh();
</script>
</body>
</html>
```

### 3.5 怎么跑

```bash
cd mini-task-server
npm install          # 只装 express
node server.js       # 看到 "迷你任务服务已启动"
```

然后浏览器打开 `http://localhost:8074/`，点几次"新建任务"。

也可以用 curl 验证（curl 不带 `Origin` 头，会被白名单放行）：

```bash
curl http://localhost:8074/tasks
curl -X POST http://localhost:8074/task \
     -H "Content-Type: application/json" \
     -d '{"id":-1,"name":"来自curl","links":"https://www.jd.com","graph":[]}'
curl "http://localhost:8074/task?id=0"
curl -X DELETE "http://localhost:8074/task?id=0"
```

### 3.6 跑起来的样子

```text
$ node server.js
迷你任务服务已启动： http://localhost:8074

# 第一次点「新建任务」
POST /task   body = {"id":-1,"name":"任务42","links":"...","graph":[...]}
        ↓ nextId() 计算：tasks/ 里还没有文件 → id = 0
        ↓ writeTask(0, task)
   tasks/0.json  ← {"id":0,"name":"任务42","links":"...","graph":[...]}
        ↑ 响应体："0"（纯文本）

# 再点一次
POST /task   body = {"id":-1,"name":"任务17",...}
        ↓ nextId()：现有 [0] → id = 1
   tasks/1.json
        ↑ 响应体："1"

# 刷新页面
GET /tasks
        ↓ 读 0.json、1.json，各取 id / name / links 第一行
        ↑ [{"id":0,"name":"任务42","url":"https://www.jd.com"},
           {"id":1,"name":"任务17","url":"https://www.jd.com"}]

# 删掉 0 号
DELETE /task?id=0
        ↓ 读 0.json → 把 id 改成 -2 → 仍然写回 0.json
   tasks/0.json  ← {"id":-2,"name":"任务42",...}
        ↑ GET /tasks 时因为 id === -2 被过滤，列表里看不到了，但文件还在
```

---

## 4. 这个最小例子还缺什么

它能跑通核心流程，但离"能给用户用"差得远：

| 缺的东西 | 说明 |
|---|---|
| **没有递归遍历** | 真实的任务目录可能有子目录（`travel()` 递归），这里只扫了一层 |
| **没有排序** | 列表应该按修改时间倒序（最新的在最上面） |
| **没有异常兜底** | 某个 JSON 坏了（手改坏了），`loadTask` 一抛异常整个列表就 500 |
| **没有统一响应格式** | 有的返回 JSON、有的返回纯文本；真实项目会封装 `writeSuccess` / `writeError` |
| **没有"执行实例"概念** | 任务（模板）和执行实例（一次运行）应该是两套文件，这里只有一套 |
| **没有进程管理** | 真实服务要能把 Python 执行器拉起来，还得能停掉它 |
| **没有配置读写** | 数据目录、语言、端口都得能改并持久化 |
| **静态目录没做路径穿越防护** | 手写版必须校验拼完的路径仍在基目录内 |
| **没有超时/并发保护** | 两个请求同时写同一个 id 会互相覆盖 |
| **端口写死** | 真实项目要从配置文件读，冲突时好改 |

下面第二部分，看 EasySpider 怎么补上这些。

---

---

# 第二部分：EasySpider 是怎么做的

## 5. server.js 的全貌

文件：`ElectronJS/server.js`（941 行）。

它不是一个"Express 应用"，而是**两个服务 + 一堆工具函数**：

```text
server.js
├── ① 工具函数
│     travel(dir, cb)      递归遍历目录              （第 16-25 行）
│     compare(p)           生成"按某字段降序"的比较器 （第 26-33 行）
│     getDir()             算出数据目录（打包/开发两套逻辑）（第 35-44 行）
│     generateUuid()       生成随机 key（给远程控制用） （第 175-186 行）
│     safeHandler(fn, res) 包一层 try-catch，防单个请求搞崩整个服务（第 190-206 行）
│
├── ② Express 服务（端口 8075）
│     只挂一个路由：POST /excelUpload（multer 收上传的 xlsx）
│
└── ③ 原生 http 服务（端口 8074，exports.start）
      ├── CORS 白名单（手写响应头）
      ├── 静态文件（src/ 目录）
      └── 一长串 else-if 路由：
            /queryTasks  /queryTask  /queryExecutionInstances  /queryExecutionInstance
            /queryOSVersion  /getConfig  /setUserDataFolder
            /manageTask  /deleteTask  /invokeTask
            /executeTask  /stopTask  /getTaskLog  /getTaskStatus
```

### 5.1 启动时的自举

`server.js` 第 54-77 行，模块一被 `require` 就会执行（不在任何函数里）：

```js
// ① 三个目录/文件不存在就建出来
if (!fs.existsSync(path.join(getDir(), "tasks"))) {
  fs.mkdirSync(path.join(getDir(), "tasks"));                  // 任务目录
}
if (!fs.existsSync(path.join(getDir(), "execution_instances"))) {
  fs.mkdirSync(path.join(getDir(), "execution_instances"));    // 执行实例目录
}
if (!fs.existsSync(path.join(getDir(), "config.json"))) {
  // ② 首次运行，生成一份默认配置
  fs.writeFileSync(
    path.join(getDir(), "config.json"),
    JSON.stringify({
      webserver_address: "http://localhost",
      webserver_port: 8074,                    // ★ 默认端口写在这里
      user_data_folder: "./user_data",
      debug: false,
      lang: "-",                               // "-" = 跟随系统语言
      copyright: 0,
      sys_arch: require("os").arch(),
      mysql_config_path: "./mysql_config.json",
      absolute_user_data_folder: "D:\\Document\\Projects\\EasySpider\\ElectronJS\\user_data",
    })
  );
}
```

### 5.2 `getDir()`：数据目录到底在哪

`server.js` 第 35-44 行：

```js
function getDir() {
  // 打包后的 macOS：绝不能用 __dirname（Gatekeeper 的 App Translocation 会把
  // 应用放到一个临时只读目录，写进去的数据下次启动就没了），必须用 userData
  if (app.isPackaged && process.platform === "darwin") return app.getPath("userData");

  // 打包后的 Windows / Linux：resource 目录的上两级 = 软件根目录（便携版行为）
  if (app.isPackaged) return path.resolve(process.resourcesPath, "../..");

  return __dirname;   // 开发模式：就是 ElectronJS/ 自己
}
```

> 💡 这就是为什么你把整个 EasySpider 文件夹拷到 U 盘，任务也跟着走——
> 数据目录是**软件目录本身**，不是 `C:\Users\...\AppData`。

---

## 6. 启动链路：谁在什么时候把 8074 开起来

### 6.1 主进程启动

`ElectronJS/main.js` 第 27 行引入，第 111-113 行启动：

```js
const task_server = require(path.join(__dirname, "server.js"));   // 第 27 行
// ...
let config = fs.readFileSync(
    path.join(task_server.getDir(), `config.json`), "utf8");      // 第 30-33 行
config = JSON.parse(config);
// ...
if (config.webserver_address.includes("localhost") ||
    config.webserver_address.includes("127.0.0.1")) {             // 第 111 行
    task_server.start(config.webserver_port);                     // 第 112 行 ★ 开服务
}
let server_address = `${config.webserver_address}:${config.webserver_port}`;  // 第 114 行 → "http://localhost:8074"
const websocket_port = 8084;   // 第 115 行 ★ 扩展通信端口，写死（扩展里也写死了）
```

> 🔬 **一个有意思的判断**：只有配置里的地址是 `localhost` / `127.0.0.1` 时才启动服务。
> 如果你把 `webserver_address` 改成局域网 IP，这个本地服务就不开了——
> 因为它的安全模型建立在"只监听回环地址"这个前提上。

### 6.2 还有一条独立启动路径

`ElectronJS/start_server.js`（全文 3 行）：

```js
const path = require("path");
const task_server = require(path.join(__dirname, "server.js"));
task_server.start(8074); //start local server
```

这是给"只想跑服务、不想开界面"的场景用的（远程调用、调试）。

### 6.3 前端怎么知道地址

主进程在打开界面时，把地址塞进 URL 参数（`main.js` 第 426-428 行）：

```js
server_address +
`/taskGrid/FlowChart_CN.html?id=${msg.message.id}&wsport=${websocket_port}&backEndAddressServiceWrapper=` +
    server_address;
```

前端再取出来（`src/taskGrid/logic.js` 第 487 行）：

```js
let backEndAddressServiceWrapper = getUrlParam("backEndAddressServiceWrapper");
// → "http://localhost:8074"
```

之后所有请求都拼它：

```js
$.get(backEndAddressServiceWrapper + "/queryTask?id=" + sId, ...);   // logic.js 第 675 行
$.post(backEndAddressServiceWrapper + "/manageTask", {...}, ...);    // logic.js 第 657 行
```

```text
main.js 启动服务 (8074)
      │
      ├── 拼 URL：...&backEndAddressServiceWrapper=http://localhost:8074
      │
      ▼
浏览器窗口打开 taskGrid/*.html
      │
      ├── 从 URL 参数里取出 backEndAddressServiceWrapper
      │
      ▼
$.get / $.post → http://localhost:8074/queryTask?id=33
```

> 💡 用 URL 参数传地址，而不是写死 `localhost:8074` 常量——
> 这样端口改了、地址改了，前端一行都不用动。

---

## 7. 两个服务：8074（原生 http）和 8075（Express）

这是理解 `server.js` 最关键的一点。

### 7.1 Express 服务（8075）：只为上传 Excel

`server.js` 第 94-95 行、第 108-135 行：

```js
const fileServer = express();                                    // 第 94 行
const upload = multer({ dest: path.join(getDir(), "Data/") });   // 第 95 行 上传暂存目录

fileServer.post("/excelUpload", upload.single("file"), (req, res) => {   // 第 108 行
  let workbook = XLSX.readFile(req.file.path);                   // ① 用 xlsx 库读上传的文件
  let sheet_name_list = workbook.SheetNames;                     // ② 所有工作表名
  let data = XLSX.utils.sheet_to_json(
      workbook.Sheets[sheet_name_list[0]]);                      // ③ 第一个表 → 行对象数组

  // ④ 按列聚合： [{A:1,B:2},{A:3,B:4}] → {A:[1,3], B:[2,4]}
  let result = data.reduce((acc, obj) => {
    Object.keys(obj).forEach((key) => {
      if (!acc[key]) { acc[key] = []; }
      acc[key].push(obj[key]);
    });
    return acc;
  }, {});

  fs.unlink(req.file.path, (err) => {                            // ⑤ 读完就删掉临时文件
    if (err) { console.error(err); return; }
  });
  res.send(JSON.stringify(result));                             // ⑥ 回给前端
});

fileServer.listen(8075, "127.0.0.1", () => {                    // 第 133 行 ★ 8075！
  console.log("Server listening on http://localhost:8075");
});
```

前端调用处写死了这个端口（`src/taskGrid/executeTask.html` 第 439 行）：

```js
$.ajax({
    url: "http://localhost:8075/excelUpload",   // ★ 注意不是 backEndAddressServiceWrapper
    type: 'POST',
    data: form_data,
    processData: false,       // FormData 不要被 jQuery 序列化
    contentType: false,       // 让浏览器自己带 multipart/form-data 边界
    success: function (response) { ... }
});
```

**用途**：任务的"批量输入"。你有一个 1000 行的 Excel，每行一个网址，
上传后每一列变成一个输入参数的值列表，任务就循环 1000 次。

> ⚠️ **为什么上传要单开一个端口？**
> 因为 8074 那个服务是手写的原生 http，解析 `multipart/form-data`（文件上传格式）
> 极其麻烦。而 `multer` 是 Express 生态里专门干这个的。
> 于是作者没有重写 8074，而是**另起一个 Express 服务专管上传**——一个务实的工程选择。

### 7.2 原生 http 服务（8074）：剩下的全部

`server.js` 第 208-210 行：

```js
exports.start = function (port = 8074) {      // ★ 默认端口 8074
  http
    .createServer(function (req, res) {
      let body = "";                          // 手动攒请求体
      // ... CORS、静态文件、一长串 else-if 路由
      req.on("data", function (chunk) {       // 第 321 行 收数据
        body += chunk;
      });
      req.on("end", safeHandler(() => {       // 第 324 行 收完了，进路由
        ...
      }, res));
    })
    .listen(port, "127.0.0.1");               // 第 938 行 ★ 只监听回环地址
  console.log("Server has started on 127.0.0.1:" + port);
};
```

### 7.3 两个服务对照

| | 8074（原生 http） | 8075（Express） |
|---|---|---|
| 技术 | `http.createServer` + 手写 `else-if` | `express()` + `multer` |
| 路由数 | 14 个 | 1 个（`/excelUpload`） |
| 主要职责 | 任务/执行实例的增删查、启动进程、读日志 | 收上传的 xlsx，解析成列数据 |
| 调用方 | 前端页面（`backEndAddressServiceWrapper`）、Python 执行器 | 前端页面（端口写死） |
| 请求体 | `querystring.parse(body)`（表单格式） | `multipart/form-data`（multer） |

---

## 8. 安全：CORS 只允许本机来源

两个服务都做了同一件事，但写法不同。

### 8.1 Express 那边：用 cors 中间件

`server.js` 第 97-107 行：

```js
// SECURITY: Restrict CORS to local origins only to prevent CSRF from malicious
// websites driving this locally-bound API (CWE-352).
const LOCAL_ORIGIN_RE = /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/i;
fileServer.use(cors({
  origin: function (origin, callback) {
    // 允许同源 / 非浏览器请求（没有 Origin 头）
    if (!origin) return callback(null, true);
    if (LOCAL_ORIGIN_RE.test(origin)) return callback(null, true);
    return callback(new Error("Origin not allowed"));     // 其他一律拒绝
  },
}));
```

### 8.2 原生那边：手写响应头

`server.js` 第 219-246 行：

```js
const reqOrigin = req.headers.origin;                       // ① 取 Origin 头
const isLocalOrigin = !reqOrigin || LOCAL_ORIGIN_RE.test(reqOrigin);

if (reqOrigin && isLocalOrigin) {                           // ② 本机来源才回送
  res.setHeader("Access-Control-Allow-Origin", reqOrigin);  //    注意：回送的是原值，不是 "*"
  res.setHeader("Vary", "Origin");
  res.setHeader("Access-Control-Allow-Credentials", "true");
}

if (req.method && req.method.toUpperCase() === "OPTIONS") { // ③ 预检请求
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers",
    req.headers["access-control-request-headers"] || "Content-Type");
  res.writeHead(isLocalOrigin ? 204 : 403);                 // ★ 非本机来源，预检就 403
  res.end();
  return;
}

if (!isLocalOrigin) {                                       // ④ 真正的请求也拦一道
  res.writeHead(403, { "Content-Type": "application/json" });
  res.end(JSON.stringify({
    error: "Cross-origin requests are not allowed.",
    status: false,
  }));
  return;
}
```

### 8.3 为什么必须这样

源码注释写得很直白（第 212-218 行）：

```text
这个本地 HTTP API 能：
  - spawn 子进程（/executeTask）   ← 能在你机器上跑任意程序
  - 改写磁盘上的任务/配置文件       ← 能删你的任务
它没有鉴权，所以一旦放开 CORS：
  任何你访问过的网站都能跨域驱动它
```

> 🔬 这类攻击有个专门的名字：**DNS rebinding**（把域名解析到 127.0.0.1 绕过同源）和 **CSRF**。
> 唯一的防线就是"看 Origin，只认回环地址"，而且**绝不能回 `Access-Control-Allow-Origin: *`**。

---

## 9. 请求分发：一长串 else-if

### 9.1 先算路径，再定"安全基目录"

`server.js` 第 248-254 行：

```js
const pathName = url.parse(req.url).pathname;   // "/taskGrid/FlowChart.html" 或 "/queryTask"
const safeBase = path.join(__dirname, "src");   // ★ 静态文件只允许从 src/ 取

// 把用户给的路径"规范化"后拼到基目录后面
const safeJoin = (base, target) => {
  const targetPath = "." + path.posix.normalize("/" + target);  // 把 ".." 解析掉
  return path.join(base, targetPath);
};
```

### 9.2 有扩展名 → 当静态文件；没有 → 当接口

`server.js` 第 288 行这个判断很关键：

```js
else if (pathName.indexOf(".") >= 0) {
  // 路径里有 "." → 认为是前端在请求资源文件（.html / .js / .css / .png ...）
  const filePath = safeJoin(safeBase, pathName);

  if (!filePath.startsWith(safeBase)) {         // ★ 路径穿越防护
    res.writeHead(400, { "Content-Type": 'text/html;charset="utf-8"' });
    res.end("Invalid path");
    return;
  }

  fs.readFile(filePath, async (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": 'text/html;charset="utf-8"' });
      res.end(err.message);
      return;
    }
    // 按扩展名查 MIME，从 mime.json 读（第 90-92 行加载）
    let extname = path.extname(pathName);
    let mime = FileMimes[extname];
    res.writeHead(200, { "Content-Type": mime + ';charset="utf-8"' });
    res.end(data);
  });
}
```

> 💡 这就是 §2.5 的 `express.static` 手写版。`mime.json` 是一个 15KB 的扩展名→MIME 映射表。

### 9.3 分发总表

```text
收到请求
  │
  ├─ OPTIONS 预检 ───────────────→ 204（本机）/ 403（非本机）
  ├─ 非本机 Origin ──────────────→ 403
  │
  ├─ pathName 含 "." ────────────→ 静态文件（src/ 目录 + 路径穿越校验）
  │
  └─ 否则（在 req.on("end") 里按 pathName 逐个 else-if 匹配）
       ├─ /queryTasks              列出所有任务
       ├─ /queryTask               读单个任务
       ├─ /queryExecutionInstances 列出所有执行实例
       ├─ /queryExecutionInstance  读单个执行实例
       ├─ /queryOSVersion          操作系统与 CPU 架构
       ├─ /getConfig               读 config.json
       ├─ /setUserDataFolder       改用户数据目录
       ├─ /manageTask              保存任务（新建/更新）
       ├─ /deleteTask              逻辑删除任务
       ├─ /invokeTask              由任务生成执行实例
       ├─ /executeTask             ★ 拉起 Python 执行器进程
       ├─ /stopTask                停止正在跑的执行器
       ├─ /getTaskLog              取执行日志
       ├─ /getTaskStatus          查询是否还在跑
       └─ /                        返回 "Hello World!"（探活）
```

---

## 10. 路由逐行拆解

### 10.1 三个响应工具函数

手写服务最烦的就是每次都三件套（`writeHead` + `write` + `end`）。作者封了三个：

`server.js` 第 145-173 行：

```js
// ① 最底层：写头、写体、结束
function writeAndEnd(res, data, statusCode = 200, contentType = 'application/json') {
  res.writeHead(statusCode, { 'Content-Type': contentType });
  res.write(data);
  res.end();
}

// ② 成功：统一带 status:true，其余字段展开进去
function writeSuccess(res, data, successMessage = "") {
  writeAndEnd(res,
    JSON.stringify({ success: successMessage, status: true, ...data }),
    200, 'application/json');
}

// ③ 失败：统一带 status:false
function writeError(res, errorCode, errorMessage = "Internal Server Error") {
  writeAndEnd(res,
    JSON.stringify({ error: errorMessage, status: false }),
    errorCode, 'application/json');
}
```

调用效果：

```text
writeSuccess(res, {}, "Task has been deleted successfully.")
  → {"success":"Task has been deleted successfully.","status":true}

writeError(res, 404, "Cannot find task based on specified task ID.")
  → {"error":"Cannot find task based on specified task ID.","status":false}   (404)
```

### 10.2 `safeHandler`：别让一个请求搞崩服务

`server.js` 第 190-206 行：

```js
// 当 handler 里出错时，会被捕获并记录；如果响应头还没发出去，就回一个 500。
// 这能防止因为某个请求里未捕获的异常导致整个服务器崩溃。
function safeHandler(handler, res) {
  return (...args) => {
    try {
      handler(...args);
    } catch (err) {
      console.error("Error handling request:", err);
      if (!res.headersSent) {                        // ★ 已经发过头了就别再发
        res.writeHead(500, { 'Content-Type': 'text/plain' });
        if (process.env.NODE_ENV === 'development') {
          res.end(`Internal Server Error: \n${err.stack}`);   // 开发模式给堆栈
        } else {
          res.end("Internal Server Error");                   // 生产模式不给（防信息泄露）
        }
      }
    }
  };
}
```

用在第 324 行：`req.on("end", safeHandler(() => { ...一大段路由... }, res));`

> 💡 这是个很值得抄的模式：**给每个入口回调套一层 try-catch**。
> 否则一个坏掉的 `tasks/99.json` 就能让整个 EasySpider 的文件服务挂掉。

### 10.3 `/queryTasks`：递归遍历 + 按修改时间排序

`server.js` 第 326-353 行：

```js
if (pathName == "/queryTasks") {
  output = [];
  // ① 递归遍历 tasks/ 目录（travel：是目录就继续递归，是文件就回调）
  travel(path.join(getDir(), "tasks"), function (pathname) {
    const data = fs.readFileSync(pathname, "utf8");
    let stat = fs.statSync(pathname, "utf8");
    if (pathname.indexOf(".json") >= 0) {              // 只处理 .json
      const task = JSON.parse(data);
      let item = {
        id: task.id,
        name: task.name,
        url: task.links.split("\n")[0],                // 网址可能多行，列表只显示第一行
        mtime: stat.mtime,                             // 最后修改时间
        links: task.links,
        desc: task.desc,
      };
      if (item.id != -2) {                             // ★ 过滤掉逻辑删除的
        output.push(item);
      }
    }
  });
  output.sort(compare("mtime"));                       // ② 按修改时间降序
  res.writeHead(200, { "Content-Type": "application/json" });
  res.write(JSON.stringify(output));
  res.end();
}
```

两个工具函数（第 16-33 行）：

```js
// 递归遍历目录：是目录 → 继续往下钻；是文件 → 回调
function travel(dir, callback) {
  fs.readdirSync(dir).forEach((file) => {
    const pathname = path.join(dir, file);
    if (fs.statSync(pathname).isDirectory()) { travel(pathname, callback); }
    else { callback(pathname); }
  });
}
// 返回一个"按字段 p 降序"的比较器
function compare(p) { return function (m, n) { return n[p] - m[p]; }; }
```

⚠️ **一处小瑕疵**：`travel()` 遇到坏 JSON 会抛异常，整个 `/queryTasks` 就 500 了。
`safeHandler` 能兜住不崩，但用户看到的是"任务列表打不开"。

### 10.4 `/queryTask`：读单个任务

`server.js` 第 382-396 行：

```js
else if (pathName == "/queryTask") {
  let params = url.parse(req.url, true).query;   // ① 第二个参数 true → 自动解析查询串
  try {
    let tid = parseInt(params.id);               // ② 一定要 parseInt！否则拼路径有注入风险
    const data = fs.readFileSync(
      path.join(getDir(), `tasks/${tid}.json`), "utf8");   // ③ 直接读文件
    res.writeHead(200, { "Content-Type": "application/json" });
    res.write(data);                             // ④ 原样吐回，不做任何加工
    res.end();
  } catch (error) {
    writeError(res, 404, "Cannot find task based on specified task ID.");
  }
}
```

> 💡 `parseInt` 那一步是**安全关键**：如果直接用 `params.id` 拼路径，
> 请求 `/queryTask?id=../../config` 就能读到别的文件。

前端（`src/taskGrid/logic.js` 第 675 行）：

```js
$.get(backEndAddressServiceWrapper + "/queryTask?id=" + sId, function (result) {
    nodeList = result["graph"];            // ① 取出流程图
    app.$data.list.nl = nodeList;
    for (let node of nodeList) {           // ② 兼容旧版本任务的字段缺失
        if (node["option"] == 1 && !("cookies" in node["parameters"])) {
            node["parameters"]["cookies"] = "";
        } else if (node["option"] == 3 &&
                   node["parameters"]["paras"] != undefined &&
                   node["parameters"]["params"] == undefined) {
            node["parameters"]["params"] = node["parameters"]["paras"];
        }
    }
    for (let key of Object.keys(result)) { // ③ 把字段填回表单（用 id 当选择器）
        try { $("#" + key).val(result[key]); } catch (e) {}
    }
    refresh();
});
```

> 💡 第 ③ 步是个巧思：表单控件的 `id` 直接取任务 JSON 的字段名，
> 于是"填表单"变成一个循环——加新字段时前端不用改。

### 10.5 `/manageTask`：保存任务（核心）

`server.js` 第 441-499 行：

```js
body = querystring.parse(body);          // ① 表单格式的请求体 → 对象
data = JSON.parse(body.params);          // ② params 字段里才是真正的任务 JSON
let id = data["id"];

if (data["id"] == -1) {                  // ③ -1 = 新任务，分配 id
  file_names = [];
  fs.readdirSync(path.join(getDir(), "tasks")).forEach((file) => {
    try {
      if (file.split(".")[1] == "json") {
        file_names.push(parseInt(file.split(".")[0]));    // "33.json" → 33
      }
    } catch (error) {}                   // ★ 忽略解析不了的文件名
  });
  // 一个任务都没有 → 从 0 开始；否则 最大 id + 1
  id = file_names.length == 0 ? 0 : Math.max(...file_names) + 1;
  data["id"] = id;
}

// ④ 输出格式是 mysql 时，确保 mysql_config.json 存在（没有就生成一份模板）
if (data["outputFormat"] == "mysql") { /* fs.access(F_OK) 检查 + 写模板，省略 */ }

fs.writeFile(path.join(getDir(), `tasks/${id}.json`),
             JSON.stringify(data), (err) => {});          // ⑤ 落盘

res.writeHead(200, { "Content-Type": "text/plain" });
res.write(id.toString(), "utf8");        // ⑥ ★ 返回纯文本 id
res.end();
```

前端（`src/taskGrid/logic.js` 第 657 行）：

```js
$.post(backEndAddressServiceWrapper + "/manageTask",
    { params: JSON.stringify(serviceInfo) },       // ★ 整个任务塞进 params 字段
    function (result) {
        $("#serviceId").val(parseInt(result))      // ★ result 是纯文本 "33"
        if (type == 1) {                           // 另存为：跳到新 id 的页面
            let newUrl = currentUrl.replace("id=" + id, "id=" + result + "&saveAs=1");
            window.location.href = newUrl;
        }
    });
```

> 🔬 **为什么响应体是纯文本 id 而不是 JSON？**
> 历史原因（早期版本就这么写的），前端用 `parseInt(result)` 直接转。
> 源码第 350 行有句注释："只修改外层为 `{}` 的响应增加 status 字段，其他响应不变，否则就和之前不兼容了"——**向后兼容的代价**。

### 10.6 `/deleteTask`：逻辑删除

`server.js` 第 416-440 行：

```js
else if (pathName == "/deleteTask") {
  let params = url.parse(req.url, true).query;
  try {
    let tid = parseInt(params.id);
    let data = fs.readFileSync(path.join(getDir(), `tasks/${tid}.json`), "utf8");
    data = JSON.parse(data);
    data.id = -2;                          // ★ 关键：只把 id 改成 -2，文件不删
    data = JSON.stringify(data);
    fs.writeFile(path.join(getDir(), `tasks/${tid}.json`), data, (err) => {
      if (err) { throw err; }
    });
    writeSuccess(res, {}, "Task has been deleted successfully.");
  } catch (error) {
    writeError(res, 404, "Cannot find task based on specified task ID.")
  }
}
```

前端（`src/taskGrid/taskList.html` 第 194-195 行）——删完立刻重新拉列表：

```js
$.get(app.$data.backEndAddressServiceWrapper + "/deleteTask?id=" + id, function (res) {
    $.get(app.$data.backEndAddressServiceWrapper + "/queryTasks", function (re) {
        // ...刷新表格
    });
});
```

> 💡 逻辑删除的好处：删错了还能从 `tasks/<id>.json` 里把 `-2` 改回来。
> 代价：`/queryTasks` 每次都要把 `-2` 的过滤掉，而且 id 不会回收。

### 10.7 `/invokeTask`：由任务生成"执行实例"

任务（`tasks/<id>.json`）是**模板**，执行实例（`execution_instances/<eid>.json`）是**一次运行**。
为什么要分开？因为同一次运行要能填不同的参数（比如换一批网址）。

`server.js` 第 500-585 行（节选关键部分）：

```js
// ① 取参数（不传就用任务里的默认值）；再按任务 id 读出模板
let data = (body.params === undefined || body.params == "") ? {} : JSON.parse(body.params);
let task = JSON.parse(fs.readFileSync(path.join(getDir(), `tasks/${id}.json`), "utf8"));

// ② 允许覆盖 urlList_0（一行一个网址）
if (data["urlList_0"] !== undefined && data["urlList_0"] != "") {
    task["links"] = data["urlList_0"];
}

// ③ 把传入的参数写回流程图里对应的节点（按 inputParameters 里的 name 匹配）
for (const [key, value] of Object.entries(data)) {
  for (let i = 0; i < task["inputParameters"].length; i++) {
    if (key === task["inputParameters"][i]["name"]) {
      const node = task["graph"][parseInt(task["inputParameters"][i]["nodeId"])];
      if (node["option"] === 1) {                          // 打开网页节点 → 改网址
        node["parameters"]["links"] = value;
      } else if (node["option"] === 4) {                   // 输入文字节点 → 改输入内容
        node["parameters"]["value"] = value;
      } else if (node["option"] === 8 && node["parameters"]["loopType"] === 0) {
        node["parameters"]["exitCount"] = parseInt(value);  // 循环（单个元素）→ 改次数
      } else if (node["option"] === 8) {                    // 循环（文本列表）
        node["parameters"]["textList"] = value;
      }
      break;
    }
  }
}

// ④ 分配执行实例 id（最大 + 1）；若指定了 EID 就覆盖原有的实例
let eid = file_names.length != 0 ? Math.max(...file_names) + 1 : 0;
if (body["EID"] != "" && body["EID"] != undefined) { eid = parseInt(body["EID"]); }

task["id"] = eid;                        // ★ 把任务对象的 id 换成执行实例 id
fs.writeFile(path.join(getDir(), `execution_instances/${eid}.json`),
             JSON.stringify(task), (err) => {});

res.writeHead(200, { "Content-Type": "text/plain" });
res.write(eid.toString(), "utf8");       // ⑤ 返回执行实例 id（纯文本）
res.end();
```

> 🔬 **参数是怎么"注入"流程图的**：`inputParameters` 里每一项都记着 `nodeId`，
> 指向 `graph` 里的某个节点。所以 `/invokeTask` 只要按名字找到参数，
> 顺着 `nodeId` 找到节点，再把值写进 `node["parameters"]` 的对应字段就行。

```text
tasks/33.json（模板，长期保存）
      │
      │  POST /invokeTask  id=33  params={"urlList_0":"https://a.com\nhttps://b.com"}
      ↓  把参数写回节点，分配 eid
execution_instances/0.json（一次运行，可覆盖）
      │
      ↓  返回 "0"
前端拿到 eid = 0，再去调 /executeTask
```

### 10.8 `/executeTask`：拉起 Python 执行器

这是最"重"的一个路由（第 610-830 行，220 行）。拆成六步：

**第 ① 步：按平台找到可执行文件**（第 625-656 行）

```js
let platform_dir = "";
let executable_name = "easyspider_executestage";

if (process.platform === "win32" && process.arch === "x64") {
    platform_dir = "chrome_win64";
    executable_name += ".exe";                        // Windows 要加 .exe
} else if (process.platform === "win32" && process.arch === "ia32") {
    platform_dir = "chrome_win32";
    executable_name += ".exe";
} else if (process.platform === "linux") {
    platform_dir = "chrome_linux64";
} else if (process.platform === "darwin") {
    // ★ macOS 明确不支持"远程控制"方式启动
    writeError(res, 400, "Executing from remote control is not supported on macOS.");
    return;
}
// 开发路径优先，其次打包路径；都找不到就 500
const dev_executable_path = path.join(__dirname, platform_dir, executable_name);
const packaged_executable_path =
    path.join(getEasySpiderLocation(), 'resources', 'app', platform_dir, executable_name);
```

**第 ② 步：校验实例存在 + 没在跑**（第 668-721 行）

`body.id` 可以是单个 id，也可以是数组（一次跑多个）。逐个 `readFileSync` 试读，
读不到 / `id == -2` 的进 `not_found`；然后再查 `child_processes[id] != null`
就说明已经有一个在跑了，直接 400 拒绝。

> `child_processes` 是模块级变量（第 79 行 `let child_processes = {};`），
> 保存"执行实例 id → 进程信息"的映射。

**第 ③④ 步：拼参数并 spawn**（第 745-769 行）

```js
let server_address = `${config.webserver_address}:${config.webserver_port}`;  // http://localhost:8074
let secret_key = generateUuid();        // ★ 每次执行生成一个随机密钥（第 175-186 行）
let parameters = [
    "--ids", "[" + ids_string + "]",            // 执行实例 id 列表，如 "[0]"
    "--server_address", server_address,         // 让 Python 知道回哪儿取数据
    "--user_data", body.use_user_data.toString(),
    "--remote_control", "1",                    // 开启远程控制（IPC）
    "--remote_control_key", secret_key,         // 密钥，防止别人随便停你的任务
];
const child_process = spawn(executable_path, parameters,
  { detached: false,
    env: { ...process.env,
           'PYTHONUNBUFFERED': '1',   // ★ 不缓冲输出，日志才能实时看到
           'PYTHONUTF8': '1' } });    // ★ 强制 UTF-8，中文日志才不乱码
```

**第 ⑤ 步：从 stdout 里"抓" IPC 端口**（第 772-808 行）

这是整个路由最巧的一段——父子进程通信的端口是**子进程随机选的**，父进程怎么知道？
答案是：让子进程把它打印出来，父进程用正则抓。

```js
child_process.stdout.on("data", (data) => {
  const output = data.toString();

  // 累积日志，供 /getTaskLog 使用（多个 id 时每个都存一份）
  child_logs[body.id] = (child_logs[body.id] || "") + output;

  // ★ 抓 "IPC_SERVER_PORT:12345" 这样的输出
  const match = output.match(/IPC_SERVER_PORT:(\d+)/);
  if (match && match[1]) {
    const ipc_port = parseInt(match[1], 10);
    // 存下进程信息：pid / ipc_port / 进程对象 / 密钥（后两个给 /stopTask 用）
    child_processes[body.id] = {
      pid: child_process.pid, ipc_port: ipc_port,
      process: child_process, key: secret_key,
    };
    if (!ipc_port_captured) {        // ★ 只回一次响应（stdout 会触发很多次）
      ipc_port_captured = true;
      writeSuccess(res, { message: `Task execution started successfully for ID(s): ${ids_string}` });
    }
  }
});
```

**第 ⑥ 步：超时兜底**（第 825-830 行）

```js
// 加一个超时，以防 Python 脚本没能成功启动 IPC 服务器
setTimeout(() => {
  if (!ipc_port_captured) {
    writeError(res, 500, "Failed to get IPC port from child process within timeout.");
    child_process.kill('SIGKILL');   // 强制杀掉没响应的进程
  }
}, timeout * 1000);                  // timeout 默认 10 秒（第 616 行）
```

### 10.9 `/stopTask`：用密钥叫停

`server.js` 第 831-869 行：

```js
const process_info = child_processes[body.id];      // ① 从映射表里找
if (!process_info || !process_info.ipc_port) {      //    没有 = 已经跑完了
    writeError(res, 404, `No running process found for execution instance ID: ${body.id}. ...`);
    return;
}
const options = {
    hostname: '127.0.0.1',
    port: process_info.ipc_port,                      // ② 子进程自己开的 IPC 端口
    path: '/shutdown',
    method: 'GET',
    headers: { 'Authorization': process_info.key },    // ③ ★ 带上启动时生成的密钥
};
const req = http_request.request(options, (api_res) => {
    if (api_res.statusCode === 200) {
      writeSuccess(res, { message: `Shutdown command sent successfully to task ID ${body.id}.` });
    } else {
      writeError(res, 500, `IPC server responded with status: ${api_res.statusCode}`);
    }
});
req.end();
```

> 💡 注意方向反过来了：这里是 **Node 作为客户端**去请求 Python 起的 HTTP 服务。
> 8074 是"Python → Node"，IPC 端口是"Node → Python"。

### 10.10 `/getTaskLog`：运行中读内存，结束后读文件

`server.js` 第 871-920 行：

```js
// ① 进程还在跑 → 直接返回内存里累积的日志（/executeTask 的 stdout 回调一直在往里塞）
const process_info = child_processes[id];
if (process_info && process_info.ipc_port) {
    writeSuccess(res, { log: child_logs[id] || "" });
    return;
}

// ② 进程已结束 → 去 Data/Task_<id>/ 下找最新的 .log 文件
let logFileFolder = path.join(getDir(), `Data/Task_${id}`);
fs.readdir(logFileFolder, (err, files) => {
    if (err) { writeError(res, 400, "Log file does not exist."); return; }
    let logFilePath = "", logFileName = "";
    files.forEach((file) => {
      if (file.endsWith(".log") && file > logFileName) {   // ★ 文件名带时间戳，字符串比大小 = 取最新
        logFilePath = path.join(logFileFolder, file);
        logFileName = file;
      }
    });
    if (logFilePath === "") { writeError(res, 404, "Log file not found."); return; }
    fs.readFile(logFilePath, "utf8", (err, data) => {
      if (err) { writeError(res, 500, "Failed to read log file."); return; }
      writeSuccess(res, { log: data });
    });
});
```

> 💡 同一个接口，两种数据来源：跑着的时候读内存（实时），跑完了读文件（持久）。
> 前端不用关心区别。

### 10.11 其余小路由

| 路由 | 行号 | 干什么 | 响应 |
|---|---|---|---|
| `/` | 412-415 | 探活 | `Hello World!`（纯文本） |
| `/queryOSVersion` | 354-359 | 查平台和架构 | `{"version":"win32","bit":"x64"}` |
| `/queryExecutionInstances` | 360-381 | 列出所有执行实例 | `[{id,name,url},...]` |
| `/queryExecutionInstance` | 397-411 | 读单个执行实例 | 整个 JSON |
| `/getConfig` | 586-598 | 读 `config.json` | 整个配置对象 |
| `/setUserDataFolder` | 599-609 | 改 `user_data_folder` 并写回 | `writeSuccess` |
| `/getTaskStatus` | 921-935 | 任务还在跑吗 | `{"running":true/false}` |

`/getConfig` 的实现（第 586-598 行）：

```js
else if (pathName == "/getConfig") {
  let config_file = fs.readFileSync(path.join(getDir(), `config.json`), "utf8");
  config_file = JSON.parse(config_file);
  let lang = config_file["lang"];
  if (lang == undefined) {
    lang = "-";                       // "-" = 跟随系统
  }
  res.writeHead(200, { "Content-Type": "application/json" });
  res.write(JSON.stringify(config_file));
  res.end();
}
```

---

## 11. Python 执行器也在这个服务上取数据

8074 不只服务前端，还服务 `easyspider_executestage`（Python 打包的可执行文件）。

`ExecuteStage/easyspider_executestage.py` 第 2341 行是它的默认参数：

```python
"server_address": "http://localhost:8074",
```

第 2552-2554 行——启动时去取执行实例：

```python
if c.read_type == "remote":
    print("remote")
    try:
        content = requests.get(
            c.server_address + "/queryExecutionInstance?id=" + str(id))
        service = json.loads(content.text)      # 加载服务信息
    except:
        print("Cannot connect to the server, please make sure that the EasySpider Main Program is running, "
              "or you can change the --read_type parameter to 'local' to read the task information from the "
              "local task file without keeping the EasySpider Main Program running.")
```

```text
Electron 主进程                        Python 执行器
  server.js (8074)   ←── GET /queryExecutionInstance?id=0 ──  easyspider_executestage
        │                                                            ↑
        └── spawn(executable, ["--ids","[0]",
                               "--server_address","http://localhost:8074", ...])
                        ↑ 告诉它回哪儿取
```

> 💡 如果把 `--read_type` 改成 `local`，执行器就直接读
> `execution_instances/<id>.json` 文件，**不需要 EasySpider 主程序开着**。
> 这就是命令行/服务器部署的用法（见第 2558-2568 行的 `local` 分支）。

---

## 12. 任务存储：一个真实的 tasks/33.json

最小的一个真实任务（`ElectronJS/tasks/33.json`，826 字节）格式化后：

```json
{
  "id": 33,
  "name": "新web采集任务",
  "url": "https://www.jd.com",
  "links": "https://www.jd.com",
  "containJudge": false,
  "desc": "https://www.jd.com",
  "inputParameters": [
    { "id": 0, "name": "urlList_0", "nodeId": 1, "nodeName": "打开网页",
      "value": "https://www.jd.com", "desc": "要采集的网址列表,多行以\\n分开",
      "type": "string", "exampleValue": "https://www.jd.com" }
  ],
  "outputParameters": [],
  "graph": [
    { "index": 0, "id": 0, "parentId": 0, "type": -1, "option": 0, "title": "root",
      "sequence": [1], "parameters": {...}, "isInLoop": false },
    { "id": 1, "index": 1, "parentId": 0, "type": 0, "option": 1, "title": "打开网页",
      "sequence": [], "isInLoop": false, "position": 0,
      "parameters": { "useLoop": false, "xpath": "", "wait": 0,
                      "url": "https://www.jd.com", "links": "https://www.jd.com",
                      "scrollType": 0, "scrollCount": 0 } }
  ]
}
```

对照 §10.5 的 `/manageTask`：

| 字段 | 谁产生 | 谁消费 |
|---|---|---|
| `id` | `/manageTask` 分配（`id == -1` 时） | `/queryTask?id=` |
| `name` / `desc` | 任务信息页 | `/queryTasks` 的列表 |
| `links` | 打开网页节点的网址（多行） | Python 执行器 `service["links"].split("\n")` |
| `inputParameters` | 执行页填的表单 | `/invokeTask` 写回节点 |
| `graph` | 流程图编辑器 | Python 执行器（`service["graph"]`） |

> 项目里 `ElectronJS/tasks/` 下有 **304 个** 这样的 json——全是示例任务。

### 12.1 数据落地在哪

执行产出的数据文件（Python 侧写的，不在 `server.js` 里）：

```text
Data/
└── Task_<执行实例id>/
    ├── <saveName>.csv          ← 主数据文件（或 .xlsx / .json / .txt）
    ├── <saveName>.log          ← 执行日志（/getTaskLog 会来找它）
    ├── <saveName>_steps.txt    ← 已执行到第几步（断点续采用）
    └── <saveName>/
        ├── files/              ← 下载的文件
        ├── images/             ← 下载的图片
        └── screenshots/        ← 元素截图
```

> ⚠️ **注意主数据文件的位置**：是 `Data/Task_<id>/<saveName>.csv`，
> **不在** `<saveName>/` 子目录里。`<saveName>/` 下面只有 `files/`、`images/`、`screenshots/` 三个子目录。
> （对应源码 `easyspider_executestage.py` 第 582-597 行、第 138-148 行。）

---

## 13. 真实请求走一遍

场景：用户新建一个任务 → 保存 → 打开 → 填参数执行 → 看日志 → 停掉。

| 步骤 | 请求 | 服务端动作 | 响应 |
|---|---|---|---|
| ① 打开软件 | `main.js` 读 `config.json` | `task_server.start(8074)` | — |
| ② 列表页加载 | `GET /queryTasks` | 递归读 `tasks/*.json`，过滤 `id==-2`，按 mtime 降序 | `[{id,name,url,mtime,links,desc},...]` |
| ③ 点"新建" | 打开 `FlowChart.html?id=-1&...&backEndAddressServiceWrapper=http://localhost:8074` | — | HTML |
| ④ 点"保存" | `POST /manageTask` `params=<整个任务JSON>` | `id==-1` → 扫目录算 `max+1=33` → 写 `tasks/33.json` | `33`（纯文本） |
| ⑤ 打开 33 号 | `GET /queryTask?id=33` | 读 `tasks/33.json` 原样返回 | 整个任务 JSON |
| ⑥ 点"开始执行" | `POST /invokeTask` `id=33&params={...}&EID=` | 参数写回节点 → 分配 `eid=0` → 写 `execution_instances/0.json` | `0`（纯文本） |
| ⑦ 拉起执行器 | `POST /executeTask` `id=0` | 校验文件存在、没在跑 → `spawn(exe, ["--ids","[0]", ...])` → 抓 `IPC_SERVER_PORT:54321` | `{"success":"Task execution started successfully for ID(s): 0","status":true}` |
| ⑧ 执行器取任务 | `GET /queryExecutionInstance?id=0`（Python 发的） | 读 `execution_instances/0.json` | 整个实例 JSON |
| ⑨ 看日志 | `GET /getTaskLog?id=0` | 进程还在 → 读内存 `child_logs[0]` | `{"log":"...","success":"","status":true}` |
| ⑩ 点"停止" | `POST /stopTask` `id=0` | 用 `child_processes[0].ipc_port` + `key` 请求 `/shutdown` | `{"success":"Shutdown command sent successfully...","status":true}` |
| ⑪ 事后看日志 | `GET /getTaskLog?id=0` | 进程没了 → 读 `Data/Task_0/<saveName>.log` | 日志文件内容 |
| ⑫ 删任务 | `GET /deleteTask?id=33` | 读文件 → `id=-2` → 写回 `tasks/33.json` | `{"success":"Task has been deleted successfully.","status":true}` |

---

## 14. 三个设计权衡

### 14.1 为什么用 HTTP 而不是 Electron 的 IPC？

| 方案 | 优点 | 缺点 |
|---|---|---|
| Electron `ipcMain` / `ipcRenderer` | 快、不需要端口、天然安全 | **只有 Electron 进程能用**，Python 执行器用不了 |
| 本地 HTTP | 任何语言/进程都能调用，浏览器直接访问调试 | 要占端口、要自己防 CSRF |

EasySpider 的执行器是 **Python**，必须跨语言。HTTP 是唯一大家都懂的协议。

> 副作用：你可以在浏览器里直接敲 `http://localhost:8074/queryTasks` 看数据——调试极其方便。

### 14.2 为什么主服务不用 Express？

按理说 Express 更好写。我猜原因是**历史包袱 + 只有一个文件**：

- 这段代码从最早版本就是原生 `http` 写的，跑得好好的；
- 路由虽然多，但每个都很短，写成 `else-if` 反而一眼看全；
- 真需要 Express 生态能力（文件上传）时，**再开一个 8075** 就够了，不用重构。

代价就是：每个路由都要手写 `writeHead` + 手动 `parseInt`、手动 try-catch。
（作者用 `writeSuccess` / `writeError` / `safeHandler` 三个函数补了一部分。）

### 14.3 为什么删除是"逻辑删除"？

| | 物理删除 | 逻辑删除（`id = -2`） |
|---|---|---|
| 实现 | `fs.unlink` | 改一个字段再写回 |
| 误删恢复 | 不可能 | 把 `-2` 改回来即可 |
| id 回收 | 可以复用 | 不复用（新任务 id 一直涨） |
| 列表开销 | 无 | 每次要过滤 |

对用户来说，"能恢复"比"id 好看"重要得多。

---

## 15. 局限与应对

| 局限 | 原因 | 现状 / 应对 |
|---|---|---|
| **没有鉴权，只靠 CORS** | 本地服务，作者假设"能上你机器的都是你自己" | CORS 白名单 + 只监听 `127.0.0.1` + `/stopTask` 用随机 key |
| **端口写死 8074 / 8084 / 8075** | 扩展里也写死了（`main.js` 第 115 行注释明说） | 8074 可以从 `config.json` 改；8084 改不了 |
| **单文件 941 行** | 历史累积 | 路由按 `else-if` 平铺，可读性尚可但难测试 |
| **`/queryTasks` 遇坏 JSON 就整体失败** | `travel()` 里没 try-catch | `safeHandler` 兜住不崩，但用户看到空列表 |
| **响应格式不统一** | 早期返回纯文本 id，后来加了 `{status,...}` | 源码第 350 行注释：为了向后兼容，只能给"外层是 `{}`"的响应加字段 |
| **上传接口地址硬编码 8075** | `executeTask.html` 第 439 行写死 | 如果 8075 被占用，上传功能就废了 |
| **并发写同一任务会覆盖** | 没有锁 | 单人桌面软件，场景基本不存在 |

---

## 16. 本篇小结

```text
Node.js = 让 JS 能读文件、起服务、开子进程
Express = 把"手写 if-else + 手写解析 + 手写 MIME"变成一行

EasySpider 的 server.js（941 行）其实是两个服务：
  8075  Express + multer   → 只干一件事：收上传的 xlsx，解析成列数据
  8074  原生 http + else-if → 14 个路由：任务/执行实例增删查、拉起执行器、读日志

任务存储：
  tasks/<id>.json                 模板，长期保存（删除 = id 改成 -2）
  execution_instances/<eid>.json   一次运行，由 /invokeTask 从模板生成

执行产出：
  Data/Task_<eid>/<saveName>.csv         主数据
  Data/Task_<eid>/<saveName>/{files,images,screenshots}/

关键函数：
  getDir()        算出数据目录（打包的 macOS 用 userData，其余用软件目录）
  travel()        递归遍历目录
  compare("mtime") 生成降序比较器
  writeSuccess / writeError / writeAndEnd   统一响应格式
  safeHandler()   给入口回调套 try-catch，防止单个请求搞崩服务
  generateUuid()  给每次执行生成随机 key（/stopTask 鉴权用）

进程交互：
  父 → 子：命令行参数（--ids / --server_address / --remote_control_key）
  子 → 父：stdout 里打印 "IPC_SERVER_PORT:<port>"，父进程正则抓取
  父 → 子：HTTP 请求 localhost:<ipc_port>/shutdown，带 Authorization: <key>

端口速记：
  8074  文件服务（server.js exports.start）
  8075  Excel 上传（Express）
  8084  WebSocket（扩展 ↔ Electron，写死）

安全要点：
  只监听 127.0.0.1；CORS 只放行 localhost/127.0.0.1/[::1]；绝不回 "*"
```

一句话：**把"写文件"包装成"发请求"，于是浏览器页面和 Python 进程都能存取同一份任务。**

---

## 17. 动手练习

**① 跑通最小例子**

按 §3 建 `mini-task-server/`，`npm install && node server.js`，然后用 curl 走一遍
"新建 → 列表 → 读取 → 删除"，观察 `tasks/` 目录里文件的变化。

**② 用浏览器直接访问真实服务**

启动 EasySpider，然后在浏览器里依次打开：

```text
http://localhost:8074/                        → Hello World!
http://localhost:8074/queryTasks              → 所有任务（JSON）
http://localhost:8074/queryTask?id=33         → 33 号任务
http://localhost:8074/queryOSVersion          → 你的平台和架构
http://localhost:8074/getConfig               → EasySpider 的配置
```

**③ 验证 CORS 防护**

在浏览器 Console 里（注意：要在一个**非 localhost** 的页面上，比如 `https://example.com`）：

```js
fetch("http://localhost:8074/queryTasks").then(r => r.text()).then(console.log).catch(console.error);
// → 会被 CORS 拦住（服务端返回 403）
```

再在 `http://localhost:8074/` 页面上发同样的请求，就能成功——因为它自己是 localhost 来源。

**④ 思考题**

- `/queryTask` 里为什么要 `parseInt(params.id)`？如果去掉会有什么风险？
- `/manageTask` 和 `/invokeTask` 都返回"纯文本 id"而不是 JSON。如果你来重构，会怎么改？向后兼容怎么做？
- 父子进程为什么要用"打印到 stdout 再正则抓"这种方式传端口？有没有更稳的方案？
- `/deleteTask` 用逻辑删除，那 `tasks/` 目录会一直膨胀吗？`nextId()` 会因此出问题吗？

---

返回目录：[README.md](README.md) ｜ 上一篇：[25.调试功能详解](25.调试功能详解.md) ｜ 下一篇：[27.项目开发、调试、打包与发布](27.项目开发、调试、打包与发布.md) ｜ 执行器回读：[16.Flowchart 递归执行、控制流与生命周期](16.Flowchart递归执行原理.md)
