import { defineConfig } from 'vitepress'
import sidebar from './sidebar.json'
import { installMathRenderer, renderMath } from '../../scripts/math-renderer.mjs'
// PPTX is a downloadable course attachment, not a VitePress page route.
process.env.VITE_EXTRA_EXTENSIONS = [process.env.VITE_EXTRA_EXTENSIONS, 'pptx'].filter(Boolean).join(',')

export default defineConfig({
  lang: 'zh-CN',
  title: '开源软件分析与实践',
  titleTemplate: ':title · 开源软件分析与实践',
  description: '从源码出发，理解软件如何运转。EasySpider、OpenClaw、MiniMind、LLaMAFactory 与 LangChain 课程讲义。',
  base: process.env.DOCS_BASE_PATH || '/',
  cleanUrls: true,
  head: [['link', { rel: 'icon', type: 'image/svg+xml', href: `${process.env.DOCS_BASE_PATH || '/'}favicon.svg` }]],
  appearance: true,
  srcExclude: ['README.md', 'public/**'],
  // One rendering pass for diagrams; the large library is loaded only on pages that need it.
  vite: { ssr: { noExternal: ['mermaid'] }, build: { chunkSizeWarningLimit: 2200 } },
  markdown: {
    math: true,
    lineNumbers: true,
    theme: { light: 'github-light', dark: 'github-dark' },
    config(md) {
      installMathRenderer(md)
      // Teacher notes contain HTML-looking examples; don't execute them as Vue templates.
      md.set({ html: false })
      md.block.ruler.before('paragraph', 'lecture_anchor', (state, start, _end, silent) => {
        const line = state.src.slice(state.bMarks[start] + state.tShift[start], state.eMarks[start])
        const match = line.match(/^<a\s+(?:id|name)=["']([\p{L}\p{N}_-]+)["']\s*><\/a>\s*$/u)
        if (!match) return false
        if (silent) return true
        const token = state.push('lecture_anchor', '', 0)
        token.meta = { id: match[1] }
        state.line = start + 1
        return true
      })
      md.renderer.rules.lecture_anchor = (tokens, idx) => `<span id="${tokens[idx].meta.id}" class="lecture-anchor"></span>\n`
      const renderText = md.renderer.rules.text!
      md.renderer.rules.text = (...args) => renderText(...args).replace(/\{\{/g, '&#123;&#123;')
      const renderInline = md.renderer.rules.code_inline!
      md.renderer.rules.code_inline = (...args) => renderInline(...args).replace(/\{\{/g, '&#123;&#123;')
      const fence = md.renderer.rules.fence!
      md.renderer.rules.fence = (tokens, idx, options, env, self) => {
        if (/^math(?:\s|$)/.test(tokens[idx].info.trim())) {
          const id = tokens[idx].info.match(/\bid="([\w-]+)"/)?.[1]
          return (id ? `<span id="${id}"></span>` : '') + renderMath(tokens[idx].content, true)
        }
        if (tokens[idx].info.trim() === 'mermaid') {
          const encoded = Buffer.from(tokens[idx].content).toString('base64')
          return `<MermaidDiagram encoded="${encoded}" />`
        }
        return fence(tokens, idx, options, env, self)
      }
    },
  },
  themeConfig: {
    logo: '/favicon.svg',
    siteTitle: '开源软件分析与实践',
    nav: [
      { text: '课程首页', link: '/' },
      { text: '项目讲义', items: [
        { text: 'EasySpider · 可视化采集', link: '/easyspider/' },
        { text: 'OpenClaw · 智能体系统', link: '/openclaw/' },
        { text: 'LLaMAFactory · 训练框架', link: '/llamafactory/' },
        { text: 'LangChain · 组件编排', link: '/langchain/' },
        { text: 'MiniMind · 大模型训练', link: '/minimind/' },
      ] },
    ],
    sidebar,
    outline: { level: [2, 3], label: '本页目录' },
    docFooter: { prev: '上一篇', next: '下一篇' },
    darkModeSwitchLabel: '切换颜色主题',
    lightModeSwitchTitle: '切换至浅色',
    darkModeSwitchTitle: '切换至深色',
    sidebarMenuLabel: '章节目录',
    returnToTopLabel: '回到顶部',
    search: {
      provider: 'local',
      options: {
        miniSearch: {
          options: {
            tokenize: (text) => {
              const segmenter = new Intl.Segmenter('zh-CN', { granularity: 'word' })
              return [...segmenter.segment(text)].filter(s => s.isWordLike).map(s => s.segment.toLowerCase())
            },
          },
        },
        translations: {
          button: { buttonText: '搜索讲义', buttonAriaLabel: '搜索课程讲义' },
          modal: { displayDetails: '显示摘要', resetButtonTitle: '清空', backButtonTitle: '返回', noResultsText: '没有找到相关内容', footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' } },
        },
      },
    },
    footer: { message: '以真实项目为线索，让原理与代码相遇。', copyright: '开源软件分析与实践 · 课程文档' },
  },
})
