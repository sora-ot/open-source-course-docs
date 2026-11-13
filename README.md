# 开源软件分析与实践 · 课程文档站

该项目整理了“开源软件分析与实践”这门课程的相关讲义，包括EasySpider、OpenClaw、LLaMAFactory、LangChain、MiniMind等5个部分，读者可以在[课程文档网站](https://sora-ot.github.io/open-source-course-docs/)这里进行阅读，也可以将项目下载到本地进行构建及阅读。

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

构建后双击 `启动文档网站.cmd`打开项目网页。

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

## 部署

网站已发布在 <https://sora-ot.github.io/open-source-course-docs/>。仓库每次向 `main` 推送时会自动构建、检查并发布；也可以在 GitHub Actions 页面手动运行工作流。日常只需编辑 `docs/` 中的讲义，在本地运行 `npm run dev` 预览，再提交并推送：

```powershell
git add docs
git commit -m "更新课程讲义"
git push origin main
```

如需在发布前核对 GitHub Pages 子路径效果，可运行 `npm run pages:build`、`npm run pages:check` 和 `npm run pages:preview -- --open`，也可双击 `预览GitHubPages.cmd`。正常部署由 Actions 自动完成。
