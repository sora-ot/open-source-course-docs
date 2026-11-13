import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

export const root = fileURLToPath(new URL('../', import.meta.url))
export const pagesDir = resolve(root, 'docs/.vitepress/dist-pages')

export function normalizeBase(value = '/') {
  const path = value.trim()
  if (!path || path === '/') return '/'
  if (!path.startsWith('/') || /[\\?#\s]/.test(path) || path.includes('//') || path.split('/').some(p => p === '.' || p === '..')) {
    throw new Error('Base must be an absolute URL path, for example /open-source-course-docs/.')
  }
  return path.replace(/\/+$/, '') + '/'
}
