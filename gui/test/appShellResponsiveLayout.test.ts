import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

// 去掉 JSX / 块注释与行注释后再匹配：token 藏进注释不能算数。
const stripComments = (text: string) =>
  text
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')

const appSource = () =>
  stripComments(
    readFileSync(join(import.meta.dirname, '..', 'src', 'App.tsx'), 'utf8'),
  )

test('桌面宽度始终保留左侧导航，仅低于 md 时提供折叠开关', () => {
  const source = appSource()

  assert.match(source, /breakpoint:\s*'md'/)
  assert.match(source, /collapsed:\s*\{\s*mobile:\s*!mobileNavOpened\s*\}/)
  assert.match(source, /<Burger[\s\S]*?hiddenFrom="md"[\s\S]*?aria-label=/)
  // 开关必须真的翻转导航状态，空的 onClick 会让窄屏下导航永远打不开。
  assert.match(
    source,
    /<Burger[\s\S]*?onClick=\{\(\)\s*=>\s*setMobileNavOpened\(\(opened\)\s*=>\s*!opened\)\}/,
  )
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

  // 规则写在 CSS 里不够，必须真的挂在主工作区元素上。
  assert.match(appSource(), /<AppShell\.Main\s+className="app-main"/)

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
  // 操作结果提示必须在吸底容器内（按钮之前）：放在容器外会落到屏幕外、随后自动消失。
  assert.match(
    source,
    // 从容器开标签到 <Alert 之间不得出现 </Stack>：出现就说明提示已在容器之外。
    /className="instrument-config-drawer__actions">(?:(?!<\/Stack>)[\s\S])*?<Alert(?:(?!<\/Stack>)[\s\S])*?<Group justify="flex-end">/,
  )
  // 吸底背景跟随主题，不写死白色。
  assert.match(css, /\.instrument-config-drawer__actions\s*\{[^}]*background:\s*var\(--mantine-color-body\)/s)
})
