import { readdirSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { root } from './site-paths.mjs'

// Mermaid already ships a browser ESM build. Publish it unchanged rather than
// asking Rollup to parse and re-bundle every diagram engine and its dependencies.
export function mermaidAssetsPlugin(base) {
  const dist = resolve(root, 'node_modules/mermaid/dist')
  const names = ['mermaid.esm.min.mjs', ...readdirSync(resolve(dist, 'chunks/mermaid.esm.min')).filter(n => n.endsWith('.mjs')).map(n => `chunks/mermaid.esm.min/${n}`)]
  const files = new Map(names.map(name => [name, readFileSync(resolve(dist, name))]))
  files.set('LICENSE', readFileSync(resolve(dist, '../LICENSE')))
  return {
    name: 'course-mermaid-assets',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url || '/', 'http://course.local').pathname
        const prefix = `${base}assets/vendor/mermaid/`
        if (!pathname.startsWith(prefix)) return next()
        const name = pathname.slice(prefix.length)
        const source = files.get(name)
        if (!source) return next()
        response.setHeader('Content-Type', name.endsWith('.mjs') ? 'text/javascript' : 'text/plain')
        response.end(source)
      })
    },
    generateBundle() {
      for (const [name, source] of files) this.emitFile({ type: 'asset', fileName: `assets/vendor/mermaid/${name}`, source })
    },
  }
}
