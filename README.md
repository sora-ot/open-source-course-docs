# 开源软件分析与实践 · 课程文档站

在线阅读：[课程文档网站](https://sora-ot.github.io/open-source-course-docs/)。

本网站整理教师现有讲义，统一提供五个项目入口：EasySpider、OpenClaw、LLaMAFactory、LangChain、MiniMind。MiniMind 阅读稿位于上一级的 `MiniMind整理版/`；按知识主题组织讲义，提供连续分篇、清理后的完整 Markdown、源码对照和配套资料。教师原稿单独保留。

## 从 GitHub 克隆后使用

仓库包含网站源码、整理后的讲义、图片和下载附件，可独立构建。环境需要 Node.js 20.19+ 或 22+。仅使用 Python 静态预览时需要 Python 3.10+。

```powershell
git clone https://github.com/sora-ot/open-source-course-docs.git
cd open-source-course-docs
npm ci
npm run build
npm run check
python scripts/serve.py --open
```

构建后也可以双击 `启动文档网站.cmd`。`node_modules/`、构建目录、临时缓存和本地测试结果不提交到仓库。

## 打开网站

构建完成的网站位于 `docs/.vitepress/dist/`。双击 **启动文档网站.cmd**，浏览器会打开 <http://127.0.0.1:4173/>。此方式需要本机安装 Python。首次从仓库克隆时先执行上面的安装和构建命令；之后打开网站不需要重新安装 npm 依赖。关闭服务窗口即可停止。

也可以在本目录运行：

```powershell
python scripts/serve.py --open
```

不要直接双击 `dist/index.html`：搜索、模块脚本和源码阅读页需要通过 HTTP 访问。

Windows 启动脚本使用 ASCII 编码和 CRLF 换行，避免 CMD 将中文或 LF 换行错误解析为命令。维护时请保留该格式；`.gitattributes` 已为 `.cmd` 文件指定 CRLF。

## 更新讲义与开发

环境：Node.js 20.19+ 或 22+。使用 Python 静态预览时还需 Python 3.10+。

```powershell
npm ci
npm run dev
```

`npm run sync` 是原始课程资料维护命令，读取上一级的讲义并重新生成网站阅读副本。它需要完整的教师资料目录，而 GitHub 仓库中的 `docs/` 已包含生成后的副本，日常构建无需运行同步。若直接维护仓库，可编辑 `docs/` 中的 Markdown；使用教师原稿重新同步时，这些页面会被覆盖。

生成可交付的静态网站：

```powershell
npm run build
npm run preview -- --port 4173
```

在保留了上一级完整教师资料的工作区中，更新原稿后运行 `npm run build:sync`，可先同步再构建。

初次在本机安装时发现全局 npm 代理指向不可用的 `127.0.0.1:7897`。本次安装仅通过命令参数临时停用代理，没有改动全局配置。若复现相同连接错误，可使用：

```powershell
npm install --registry=https://registry.npmjs.org --proxy=null --https-proxy=null
```

## 内容与目录

| 目录／文件 | 用途 |
| --- | --- |
| `scripts/sync_content.py` | 同步讲义、图片、正文配套示例及实际引用的源码快照，排除已删除栏目的独立资源。 |
| `docs/.vitepress/theme/` | 首页、文档主题、源码阅读页。 |
| `docs/.vitepress/config.mts` | 顶部导航、搜索、公式与流程图渲染、网站设置。 |
| `docs/easyspider/` | 28 篇编号讲义、原始目录及项目导读。 |
| `docs/openclaw/` | 18 篇主讲义、3 篇源码补充及项目导读。 |
| `docs/llamafactory/` | 十分钟讲义、源码提纲及项目导读。 |
| `docs/langchain/` | 十分钟讲义及项目导读。 |
| `docs/minimind/` | 40 份讲义分为 6 个正文主题和 MoE、LoRA 两组附录，共 71 个章节，只保留一个项目导读入口。 |
| `docs/public/` | 原稿下载、讲义配图、正文配套示例和所引用的本地源码。 |
| `内容同步报告.json` | 同步数量，以及原资料缺少的文件引用。 |
| `test-results/` | 构建与浏览器检查结果、页面截图。 |

共同步 **93 份 Markdown 讲义**（原有 53 份，MiniMind 40 份），另提供项目导读和源码页。顶层备课安排 TXT／DOCX、课程介绍 PPT、仓库中与讲义无关的文件、旧版 OpenClaw 资料以及隐藏工作目录未作为学生正文发布。

网站已移除“学习路线”“交互与演示”独立栏目。MiniMind 中完整未讲授的 MoE（4 章）和 LoRA（5 章）分别列为“附录 A · MoE”和“附录 B · LoRA”；只调整目录归属，保留全部章节文字、编号、下载和原链接。Transformer 架构以及其他主题中零散的相关内容仍保留在原位。

原栏目使用的 4 个演示视频已从网站资源中移除，后续同步也会排除。删除前已核对 SHA-256，原件保留在项目外的 `../videos/`。交互图解、元素匹配、Selenium、流程图等正文仍在使用的示例和配图继续保留。

`docs/public/` 中的资源会原样复制到构建网站，具体用途如下：

| 路径 | 用途 |
| --- | --- |
| `originals/` | EasySpider、OpenClaw、LLaMAFactory、LangChain 的 Markdown 下载。 |
| `resources/minimind/讲义/` | MiniMind 的 40 份完整整理稿下载，多个分篇共用对应完整稿。 |
| `resources/minimind/配套资料/` | 正文配图和配套 Python 文件。 |
| `resources/easyspider/` | 配图、交互图解，以及 HTML、JS、CSS 等示例依赖。 |
| `resources/openclaw/` | 配图和 SVG 资源。 |
| `resources/sources/`、`source-files.json` | 源码阅读页的文件快照和索引，按讲义引用生成。 |
| `catalog.json`、`favicon.svg` | 讲义索引和网站图标。 |

未被页面或下载讲义引用的 7 份 MiniMind PDF／PPTX 保留在网站外的 `../MiniMind/` 和 `../MiniMind整理版/配套资料/`，不再随网站发布；网站清单中的 `offlineAttachments` 记录这些文件及校验值。71 份没有下载入口的 MiniMind 分篇 Markdown 副本也已移除，完整稿下载继续保留；相同分篇保存在 `../MiniMind整理版/正文/`。清理前均核对了备份的 SHA-256。

同步脚本排除这些冗余副本，并清理未进入最新源码索引的旧快照。若正文开始引用离线附件，同步会提示先将该文件从 `MINI_OFFLINE_ATTACHMENTS` 中移除再发布。不能仅凭正文中搜不到文件名就删除资源：源码文件由索引动态加载，交互示例也会通过相对路径加载依赖。

转换时统一网页标题层级，支持 `\[...\]`／`\(...\)` 公式，改写本地章节、配图和源码链接；代码块内容不因转换而重写。课程资料里的原理说明、教学简化和实际框架差别由原稿解释，网站不把教学伪代码当作新的可执行框架。

原文件没有随资料提供的引用，会转到“资料引用说明”；缺失配图显示文字说明，不展示损坏的图片。LLaMAFactory 的十分钟稿开头以 LoRA 引入、正文重点展开 Full SFT，站内加了阅读提示，未擅自改动教师原稿。

## 设计参考与技术选择

老师所说的“readdoc”很可能指 **Read the Docs**。它是文档构建与托管平台，并不是某种唯一的文件格式。Python 文档通常用 Sphinx 构建，Vue 文档采用 VitePress。本项目选用 VitePress，便于直接复用现有 Markdown、代码与 Vue 主题，后续不必将讲义改写成 reStructuredText。

本次访问并参考的文档网站：

- [Python 文档](https://docs.python.org/3/)：首页提供不同学习入口，正文强调清晰的章节组织和导航。
- [Vue 中文文档](https://cn.vuejs.org/guide/introduction.html)：顶部全局入口、左侧章节、右侧页内目录，配合代码阅读。
- [VitePress 文档](https://vitepress.dev/guide/what-is-vitepress)：Markdown 驱动的文档结构、项目首页与正文统一主题。
- [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)：搜索、侧栏和配色切换，强调长篇文档阅读体验。
- [Read the Docs 文档](https://docs.readthedocs.com/platform/stable/)：任务导向入口、分组目录与文档维护流程。

访问日期：2026-11-01。首页采用暖白底色、项目卡片和可切换的核心流程图；正文以阅读空间、目录和源码对照为重点。字体使用系统字体，搜索在本站本地完成，公式与流程图的依赖随构建打包。

## 已完成的检查

MiniMind 按知识主题组织，清理 AI 对话回应、面向教师的讲授建议和课堂临时议题。Tokenizer、PPL、Decoder-only、Rollout、PPO 与 LoRA 的相关材料并入各自主题；历史稿、压缩包差异稿和课堂录像路线不作为讲义入口。

完整性检查覆盖 40 份整理稿、71 个主题章节和 19,947 个代码／公式块。剥离重新编排的标题后，各章节可拼回清理后的完整正文；清理前后所有代码与公式块逐字节比对，教师原稿通过 SHA-256 核对。清理记录和对应关系存放在 `../MiniMind整理版/整理校对/`，不作为学生网页发布。

25 份篇幅适中的讲义保持单页，15 份长文按知识边界组织为 46 个章节；每个页面的小节从 1 开始编号，侧栏按知识主题平铺章节，与其他项目保持一致。数学标题在正文中显示公式，在页内目录中显示可读的数学符号。

生产构建采用 2.5 GB 的 Node 堆内存上限，并限制索引与页面渲染并发。公式图形按内容去重，保存为站内 SVG 文件，正文保留无障碍 MathML；代码与公式排版作为完整 HTML 片段交给 Vue，减少编译内存。搜索索引使用文本形式的公式与代码。Mermaid 使用依赖自带的浏览器模块，随网站本地发布，无需外部 CDN。网页面向当前主流浏览器，讲义原文与下载文件保持原样。

本地链接、章节锚点、讲义下载和源码快照由 `npm run check` 检查；浏览器检查覆盖五个项目入口、主题目录、清理后的 Markdown 下载、搜索、公式、源码行号、移动侧栏和深色模式。检查结果见 `test-results/links.json`、`browser.json` 及截图；具体页面数量见 `内容同步报告.json`。

原资料中未提供的本地引用统一转到站内说明页，清单见 `内容同步报告.json`。

## 部署

网站已发布在 <https://sora-ot.github.io/open-source-course-docs/>。仓库的 `.github/workflows/deploy-pages.yml` 在每次向 `main` 推送时自动构建、检查并发布；也可以在 GitHub Actions 页面手动运行工作流。日常只需编辑 `docs/` 中的讲义，在本地运行 `npm run dev` 预览，再提交并推送：

```powershell
git add docs
git commit -m "更新课程讲义"
git push origin main
```

如需在发布前核对 GitHub Pages 子路径效果，可运行 `npm run pages:build`、`npm run pages:check` 和 `npm run pages:preview -- --open`，也可双击 `预览GitHubPages.cmd`。正常部署由 Actions 自动完成。

## MiniMind 内容维护

```powershell
python ../MiniMind整理版/整理工具/organize.py
python ../MiniMind整理版/整理工具/verify.py
npm run build
npm run check
node scripts/browser-check.mjs
```

更新原稿后先运行整理和校验，再构建网站。正文由整理工具生成；清理规则在 `editorial.py`，知识主题与资料收录规则在 `organize.py`，长文的拆分边界与概括性标题在 `reading.py`。不要直接修改生成的网页或分篇。
