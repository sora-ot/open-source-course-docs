// Reuse a MathJax document. Creating and globally registering one per equation
// exhausts Node memory when rendering the complete MiniMind lecture collection.
import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
const require = createRequire(import.meta.url)
const { mathjax } = require('mathjax-full/js/mathjax.js')
const { TeX } = require('mathjax-full/js/input/tex.js')
const { SVG } = require('mathjax-full/js/output/svg.js')
const { liteAdaptor } = require('mathjax-full/js/adaptors/liteAdaptor.js')
const { RegisterHTMLHandler } = require('mathjax-full/js/handlers/html.js')
const { AllPackages } = require('mathjax-full/js/input/tex/AllPackages.js')
const { AssistiveMmlHandler } = require('mathjax-full/js/a11y/assistive-mml.js')

const adaptor = liteAdaptor()
AssistiveMmlHandler(RegisterHTMLHandler(adaptor))
const document = mathjax.document('', { InputJax: new TeX({ packages: AllPackages }), OutputJax: new SVG({ fontCache: 'none' }) })
const cache = new Map()
const labels = new Map()
const svgAssets = new Map()
let assetBase = '/'

// Keep formula glyphs outside page JavaScript. MathML stays in the document for
// accessibility, while each reusable SVG is an ordinary same-origin image.
export function mathAssetsPlugin(base) {
  assetBase = base
  return {
    name: 'course-math-assets',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url || '/', 'http://course.local').pathname
        const prefix = `${base}assets/math/`
        if (!pathname.startsWith(prefix)) return next()
        const svg = svgAssets.get(pathname.slice(prefix.length))
        if (!svg) return next()
        response.setHeader('Content-Type', 'image/svg+xml')
        response.end(svg)
      })
    },
    generateBundle() {
      for (const [name, source] of svgAssets) this.emitFile({ type: 'asset', fileName: `assets/math/${name}`, source })
    },
  }
}

export function renderMath(content, display = false) {
  const key = (display ? 'block:' : 'inline:') + content
  if (!cache.has(key)) {
    const rendered = document.convert(content, { display })
    const html = adaptor.outerHTML(rendered)
    // Tall matrix brackets contain nested SVGs; serialize the complete root
    // node so an inner </svg> cannot truncate the equation asset.
    const svgNode = adaptor.tags(rendered, 'svg')[0]
    if (!svgNode) throw new Error('MathJax did not produce an SVG formula.')
    const svg = adaptor.outerHTML(svgNode)
    const name = createHash('sha256').update(svg).digest('hex').slice(0, 24) + '.svg'
    svgAssets.set(name, svg)
    const width = svg.match(/\bwidth="([^"]+)"/)?.[1] || 'auto'
    const height = svg.match(/\bheight="([^"]+)"/)?.[1] || 'auto'
    const style = svg.match(/\bstyle="([^"]+)"/)?.[1] || ''
    cache.set(key, html.replace(svg, `<img class="math-svg" src="${assetBase}assets/math/${name}" alt="" aria-hidden="true" style="width:${width};height:${height};${style}">`))
  }
  return cache.get(key)
}

// Compile each trusted, already-rendered fragment as one HTML value rather than
// retaining a Vue AST node for every code token, SVG path and MathML element.
export function htmlFragment(html, tag = 'span') {
  const expression = JSON.stringify(html).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return `<${tag} class="rendered-fragment" v-html="${expression}"></${tag}>`
}

function mathLabel(content) {
  if (labels.has(content)) return labels.get(content)
  const parsed = adaptor.parse(renderMath(content), 'text/html')
  const mml = adaptor.tags(adaptor.body(parsed), 'mjx-assistive-mml')[0]
  function read(node) {
    const kind = adaptor.kind(node)
    if (kind === '#text') return adaptor.value(node)
    if (kind === 'annotation' || kind === 'annotation-xml') return ''
    const children = adaptor.childNodes(node).map(read)
    if (kind === 'mfrac') return `(${children[0]})/(${children[1]})`
    if (kind === 'msqrt') return `√(${children.join('')})`
    if (kind === 'mroot') return `root(${children[0]}, ${children[1]})`
    if (kind === 'msub') return `${children[0]}_${children[1]}`
    if (kind === 'msup') return `${children[0]}^${children[1]}`
    if (kind === 'msubsup') return `${children[0]}_${children[1]}^${children[2]}`
    return children.join('')
  }
  const label = mml ? read(mml) : content
  labels.set(content, label)
  return label
}

export function installMathRenderer(md) {
  md.core.ruler.after('inline', 'lecture_heading_math', state => {
    for (let i = 0; i < state.tokens.length; i++) {
      if (state.tokens[i].type !== 'heading_open') continue
      for (const child of state.tokens[i + 1]?.children || []) {
        if (child.type === 'math_inline') child.meta = { ...child.meta, inHeading: true }
      }
    }
  })
  md.renderer.rules.math_inline = (tokens, index, _options, env) => {
    const token = tokens[index]
    if (env?.courseSearch && !token.meta?.inHeading) return md.utils.escapeHtml(token.content)
    const rendered = htmlFragment(renderMath(token.content))
    if (!token.meta?.inHeading) return rendered
    // VitePress extracts the outline from direct heading children. Keep a plain
    // mathematical label there, while the actual heading displays the SVG.
    const label = md.utils.escapeHtml(mathLabel(token.content))
    return `<span class="heading-equation ignore-header" aria-hidden="true" title="${label}">${rendered}</span><span class="heading-math-label">${label}</span>`
  }
  md.renderer.rules.math_block = (tokens, index, _options, env) => env?.courseSearch
    ? `<p>${md.utils.escapeHtml(tokens[index].content)}</p>`
    : htmlFragment(renderMath(tokens[index].content, true), 'div')
}
