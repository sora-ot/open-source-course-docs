// Reuse a MathJax document. Creating and globally registering one per equation
// exhausts Node memory when rendering the complete MiniMind lecture collection.
import { createRequire } from 'node:module'
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

export function renderMath(content, display = false) {
  const key = (display ? 'block:' : 'inline:') + content
  if (!cache.has(key)) cache.set(key, adaptor.outerHTML(document.convert(content, { display })))
  return cache.get(key)
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
  md.renderer.rules.math_inline = (tokens, index) => {
    const token = tokens[index]
    const rendered = renderMath(token.content)
    if (!token.meta?.inHeading) return rendered
    // VitePress extracts the outline from direct heading children. Keep a plain
    // mathematical label there, while the actual heading displays the SVG.
    const label = md.utils.escapeHtml(mathLabel(token.content))
    return `<span class="heading-equation ignore-header" aria-hidden="true" title="${label}">${rendered}</span><span class="heading-math-label">${label}</span>`
  }
  md.renderer.rules.math_block = (tokens, index) => renderMath(tokens[index].content, true)
}
