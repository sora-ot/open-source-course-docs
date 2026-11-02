import { readFile, readdir, access, mkdir, writeFile } from 'node:fs/promises'
import { resolve, join, relative, dirname } from 'node:path'
import { createHash } from 'node:crypto'

const root = resolve(import.meta.dirname, '..')
const dist = join(root, 'docs/.vitepress/dist')
const results = join(root, 'test-results')
await mkdir(results, { recursive: true })
const catalog = JSON.parse(await readFile(join(dist, 'catalog.json'), 'utf8'))
const sourceFiles = JSON.parse(await readFile(join(dist, 'source-files.json'), 'utf8'))
const mini = JSON.parse(await readFile(join(root, 'docs/.vitepress/minimind-manifest.json'), 'utf8'))
const missing = []
const anchors = []
const exists = async p => { try { await access(p); return true } catch { return false } }
const pages = []
async function walk(folder) {
  for (const entry of await readdir(folder, { withFileTypes: true })) {
    if (entry.name === 'resources' || entry.name === 'assets') continue
    const path = join(folder, entry.name)
    if (entry.isDirectory()) await walk(path)
    else if (entry.name.endsWith('.html')) pages.push(path)
  }
}
await walk(dist)
const htmlCache = new Map()
async function locate(url) {
  const decoded = decodeURIComponent(url.pathname)
  const path = join(dist, decoded)
  for (const candidate of [path, path + '.html', join(path, 'index.html')]) {
    if (await exists(candidate)) {
      const extension = candidate.split('.').pop()
      if (extension === 'html') return candidate
      // A directory itself isn't a valid file target; try its index instead.
      const { stat } = await import('node:fs/promises')
      if ((await stat(candidate)).isFile()) return candidate
    }
  }
  return null
}
for (const file of pages) {
  const html = await readFile(file, 'utf8')
  const route = '/' + relative(dist, file).replaceAll('\\', '/')
  htmlCache.set(file, html)
  for (const match of html.matchAll(/\b(href|src)="([^"<>]+)"/g)) {
    const raw = match[2].replaceAll('&amp;', '&')
    if (!raw || /^(https?:|mailto:|tel:|data:|javascript:|blob:)/.test(raw)) continue
    let url
    try { url = new URL(raw, 'http://course.local' + route) } catch { continue }
    const target = await locate(url)
    if (!target) { missing.push({ page: route, target: raw }); continue }
    if (url.hash && target.endsWith('.html') && !url.search && !url.pathname.startsWith('/resources/')) {
      const targetHTML = htmlCache.get(target) || await readFile(target, 'utf8')
      const anchor = decodeURIComponent(url.hash.slice(1))
      if (!targetHTML.includes(`id="${anchor}"`)) anchors.push({ page: route, target: raw })
    }
  }
}
for (const key of Object.keys(sourceFiles)) {
  if (!await exists(join(dist, 'resources/sources', key))) missing.push({ source: key })
}
const miniParts = mini.documents.flatMap(d => d.parts)
if (catalog.length !== 53 + mini.guidePages + miniParts.length) throw new Error(`Unexpected lecture count: ${catalog.length}`)
const miniPages = catalog.filter(p => p.project === 'minimind')
if (miniPages.some(p => /历史稿|压缩包差异稿|专题补充|拓展 ·|第[一二三]课|课堂路线/.test(p.group + p.title))) throw new Error('Obsolete MiniMind grouping')
if (pages.some(p => /[\\/]minimind[\\/](h[0-9a-f]{8}|classroom-route|source-map|reading-guide|contents|versions)/.test(p))) throw new Error('Removed MiniMind pages still published')
if (miniPages.some(p => /[\\$]/.test(p.title))) throw new Error('Raw math in MiniMind navigation titles')
const sidebar = JSON.parse(await readFile(join(root, 'docs/.vitepress/sidebar.json'), 'utf8'))['/minimind/']
if (sidebar[0].items.length !== 1 || sidebar[0].items[0].text !== '项目导读') throw new Error('Unexpected MiniMind guide entries')
if (sidebar.slice(1).some(g => g.items.some(i => i.items))) throw new Error('MiniMind navigation still nests small fragments')
if (await exists(join(dist, 'resources/minimind/原稿快照'))) throw new Error('Unedited MiniMind snapshots still published')
for (const part of miniParts) {
  if (!catalog.some(p => p.route === '/minimind/' + part.slug)) throw new Error(`Missing MiniMind part ${part.slug}`)
  const html = await readFile(join(dist, 'minimind', part.slug + '.html'), 'utf8')
  if (html.includes('language-math') || html.includes('data-mml-node="merror"')) throw new Error(`Unrendered or invalid equation in ${part.slug}`)
  if (/可以。给学生讲|下面这一版可以直接拿去上课|序言：开源赚钱的方式|OS社区/.test(html)) throw new Error(`Editorial residue in ${part.slug}`)
  const headingHTML = [...html.matchAll(/<h[1-6]\b[^>]*>([\s\S]*?)<\/h[1-6]>/g)].map(m => m[1]).join(' ')
  const headingText = headingHTML.replace(/<[^>]*>/g, '')
  if (/\\(?:sqrt|frac|omega|gamma|lambda|theta|partial|pi|\(|\))|\$[^$]+\$/.test(headingText)) throw new Error(`Unrendered heading math in ${part.slug}`)
  if (part.headings.some(h => /\\\(|\$/.test(h.title)) && !headingHTML.includes('heading-equation')) throw new Error(`Missing heading equation in ${part.slug}`)
}
for (const item of mini.attachments) {
  const actual = await readFile(join(dist, 'resources/minimind', item.snapshot))
  if (createHash('sha256').update(actual).digest('hex') !== item.sha256) throw new Error(`Changed MiniMind download ${item.source}`)
}
for (const item of mini.codeFiles) {
  const [key] = Object.entries(sourceFiles).find(([, value]) => value.path === 'MiniMind整理版/' + item.snapshot) || []
  if (!key) throw new Error(`Missing source variant ${item.source}`)
  const actual = await readFile(join(dist, 'resources/sources', key))
  if (createHash('sha256').update(actual).digest('hex') !== item.sha256) throw new Error(`Changed source variant ${item.source}`)
}
for (const project of ['easyspider', 'openclaw', 'llamafactory', 'langchain', 'minimind']) {
  if (!catalog.some(p => p.project === project)) throw new Error(`Missing project ${project}`)
}
const report = { pages: pages.length, lectures: catalog.length, sourceFiles: Object.keys(sourceFiles).length, miniMind: { originalMarkdown: mini.documents.length, parts: miniParts.length, verifiedAttachments: mini.attachments.length, verifiedSourceVariants: mini.codeFiles.length }, missing, anchors }
await writeFile(join(results, 'links.json'), JSON.stringify(report, null, 2))
console.log(JSON.stringify({ pages: pages.length, lectures: catalog.length, sourceFiles: Object.keys(sourceFiles).length, missing: missing.length, unmatchedAnchors: anchors.length }))
if (missing.length || anchors.length) process.exitCode = 1
