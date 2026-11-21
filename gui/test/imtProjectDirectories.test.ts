import assert from 'node:assert/strict'
import test from 'node:test'
import { imtProjectDirectories } from '../src/features/ChannelWorkbench/imtProjectDirectories.ts'

function file(path: string) {
  return { webkitRelativePath: path, name: path.split('/').at(-1) } as File
}

test('总目录按子工程隔离同名文件，不从另一目录补齐缺失文件', () => {
  const groups = imtProjectDirectories([
    file('工程/dynamic/manifest.json'),
    file('工程/baseline/manifest.json'),
    file('工程/baseline/TX0.asc'),
    file('工程/TX0.asc'),
  ])
  assert.deepEqual(
    groups.map(([path, files]) => [path, files.map((f) => f.name)]),
    [
      ['baseline', ['manifest.json', 'TX0.asc']],
      ['dynamic', ['manifest.json']],
    ],
  )
})

test('直接选择单个工程时仅读取清单所在目录', () => {
  const groups = imtProjectDirectories([
    file('dynamic/manifest.json'),
    file('dynamic/备份/TX0.asc'),
  ])
  assert.deepEqual(
    groups[0][1].map((f) => f.name),
    ['manifest.json'],
  )
})

test('多个来源或混杂清单均拒绝读取', () => {
  for (const paths of [
    ['一/manifest.json', '二/TX0.asc'],
    ['工程/manifest.json', '工程/dynamic/manifest.json'],
    ['工程/其他/manifest.json'],
  ])
    assert.throws(() => imtProjectDirectories(paths.map(file)), /工程目录/)
})

for (const [side, other] of [
  ['baseline', 'dynamic'],
  ['dynamic', 'baseline'],
]) {
  test('总目录缺少 ' + side + ' 子目录时指出缺失的一侧', () => {
    assert.throws(
      () => imtProjectDirectories([file('工程/' + other + '/manifest.json')]),
      new RegExp(side + ' 子目录缺失或为空'),
    )
  })

  test(side + ' 子目录有文件但缺少清单时指出清单路径', () => {
    assert.throws(
      () =>
        imtProjectDirectories([
          file('工程/' + side + '/数据/TX0.asc'),
          file('工程/' + other + '/manifest.json'),
        ]),
      new RegExp('缺少 ' + side + '/manifest\\.json'),
    )
  })
}
