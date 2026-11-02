# 字数统计器 —— 讲义 03 配套示例

这是 [03. Chrome 扩展开发 MV3](../03.Chrome扩展开发MV3.md) 第 4 节的完整可运行示例。

## 文件说明

```text
word-counter/                    （本文件夹）
├── manifest.json      身份证 + 权限声明
├── popup.html         面板长什么样（HTML）
├── popup.js           面板的逻辑
├── content.js         注入网页：负责数数
└── background.js      后台：负责记账
```

## 怎么运行

```text
① 地址栏输入 chrome://extensions
② 右上角打开「开发者模式」
③ 点「加载已解压的扩展程序」，选中本文件夹
④ 随便打开一个 http/https 网页（已打开的要刷新一次）
⑤ 点工具栏的扩展图标 → 弹出面板 → 点「统计字数」
```

## 跑起来之后可以试试

- 点「查看上次结果」→ 从 `chrome.storage` 里读历史
- F12 → Application → Local Storage / Extensions → 看 `history` 里存了什么
- 删掉 manifest 里的 `content_scripts` 整段再加载 → 点按钮会提示"请刷新页面后重试"
  （体会：没有 content script，popup 就摸不到网页）
- 把 `matches` 改成 `["https://*.github.com/*"]` → 只有 GitHub 生效

对应讲义章节：

| 文件 | 讲义位置 |
| --- | --- |
| manifest.json | §4.2 |
| popup.html / popup.js | §4.3 / §4.4 |
| content.js | §4.5 |
| background.js | §4.6 |
| 通信全景 | §6 |

---

🏠 返回讲义目录：[../README.md](../README.md)　｜　⬅️ 上一篇：[03. Chrome 扩展开发 MV3](../03.Chrome扩展开发MV3.md)　｜　➡️ 下一篇：[13. WebSocket 详解](../13.WebSocket详解.md)
