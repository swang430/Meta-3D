import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

const appSource = () =>
  readFileSync(join(import.meta.dirname, '..', 'src', 'App.tsx'), 'utf8')

test('桌面宽度始终保留左侧导航，仅低于 md 时提供折叠开关', () => {
  const source = appSource()

  assert.match(source, /breakpoint:\s*'md'/)
  assert.match(source, /collapsed:\s*\{\s*mobile:\s*!mobileNavOpened\s*\}/)
  assert.match(source, /<Burger[\s\S]*?hiddenFrom="md"[\s\S]*?aria-label=/)
})

test('窄桌面保留左侧导航时顶部操作区独立换行，不挤压中间与右侧内容', () => {
  const source = appSource()
  const css = readFileSync(join(import.meta.dirname, '..', 'src', 'App.css'), 'utf8')

  assert.match(
    source,
    /header=\{\{\s*height:\s*\{\s*base:\s*172,\s*sm:\s*140,\s*['"]87\.5em['"]:\s*84\s*\}\s*\}\}/,
  )
  assert.match(source, /className="app-header-layout"/)
  assert.match(source, /className="app-header-actions"/)
  assert.match(css, /@media \(max-width:\s*87\.49em\)[\s\S]*?\.app-header-layout/s)
})

test('主工作区固定在视口内并独立提供双向滚动', () => {
  const css = readFileSync(join(import.meta.dirname, '..', 'src', 'App.css'), 'utf8')

  assert.doesNotMatch(css, /\.app-main\s*\{[^}]*overflow:\s*hidden/s)
  assert.match(css, /\.app-main\s*\{[^}]*height:\s*100dvh/s)
  assert.match(css, /\.app-main\s*\{[^}]*overflow:\s*auto/s)
  assert.match(css, /\.app-main\s*\{[^}]*scrollbar-gutter:\s*stable/s)
})

test('仪器配置抽屉显式提供滚动区并固定操作区', () => {
  const source = appSource()
  const css = readFileSync(join(import.meta.dirname, '..', 'src', 'App.css'), 'utf8')

  assert.match(source, /size="min\(900px, 100vw\)"/)
  assert.match(source, /classNames=\{\{[\s\S]*?content:\s*'instrument-config-drawer__content'[\s\S]*?body:\s*'instrument-config-drawer__body'/)
  assert.match(source, /className="instrument-config-drawer__actions"/)
  assert.match(css, /\.instrument-config-drawer__content\s*\{[^}]*scrollbar-gutter:\s*stable/s)
  assert.match(css, /\.instrument-config-drawer__actions\s*\{[^}]*position:\s*sticky[^}]*bottom:\s*0/s)
})
