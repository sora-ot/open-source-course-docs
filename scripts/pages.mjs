import { spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
import { parseArgs } from 'node:util'
import { root, pagesDir, normalizeBase } from './site-paths.mjs'

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: { base: { type: 'string' }, port: { type: 'string' }, open: { type: 'boolean' } },
})
const action = positionals[0] || 'build'
if (positionals.length > 1 || !['build', 'check', 'preview', 'package'].includes(action)) {
  throw new Error('Use build, check, preview or package [--base /repository/] [--port 4174] [--open].')
}

function repositoryBase() {
  let repository = process.env.GITHUB_REPOSITORY
  if (!repository) {
    const remote = spawnSync('git', ['-c', `safe.directory=${root.replaceAll('\\', '/')}`, 'remote', 'get-url', 'origin'], { cwd: root, encoding: 'utf8' })
    repository = remote.stdout?.trim().match(/github\.com[/:]([^/]+\/[^/]+?)(?:\.git)?$/)?.[1]
  }
  repository ||= 'sora-ot/open-source-course-docs'
  const [owner, name] = repository.split('/')
  return name?.toLowerCase() === `${owner.toLowerCase()}.github.io` ? '/' : `/${name}/`
}

function run(command, args, env = process.env) {
  const result = spawnSync(command, args, { cwd: root, env, stdio: 'inherit' })
  if (result.error) throw result.error
  if (result.status !== 0) process.exit(result.status || 1)
}

if (action === 'build' || action === 'package') {
  const base = normalizeBase(values.base ?? process.env.DOCS_BASE_PATH ?? repositoryBase())
  console.log(`Building GitHub Pages: base=${base}, output=docs/.vitepress/dist-pages`)
  run(process.execPath, ['--max-old-space-size=2560', resolve(root, 'node_modules/vitepress/bin/vitepress.js'), 'build', 'docs'], {
    ...process.env, DOCS_BASE_PATH: base, DOCS_OUT_DIR: pagesDir,
    GOMAXPROCS: process.env.GOMAXPROCS || '2',
    GOMEMLIMIT: process.env.GOMEMLIMIT || '512MiB',
  })
}
if (action === 'check' || action === 'package') {
  run(process.execPath, [resolve(root, 'scripts/check-site.mjs'), '--dist', pagesDir])
}
if (action === 'preview') {
  // The server reads the base from the build, so a custom build stays reproducible.
  const args = [resolve(root, 'scripts/serve.py'), '--directory', pagesDir, '--port', values.port || '4174']
  if (values.open) args.push('--open')
  run('python', args)
}
if (action === 'package') run('python', [resolve(root, 'scripts/package_release.py')])
