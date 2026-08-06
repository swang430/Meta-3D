/**
 * P1-39: 「短显示 + 点击复制全长」的**唯一**实现。
 *
 * 背景（用户 2026-08-06）：「测试例的编号能在哪里查到？除了 log 以外」——
 * 实测三个界面（用例库 / 执行历史 / 报告详情）**没有一处**能拿到完整 ID：
 * 前两处只把 id 当 React `key`，报告页那个卡片 `slice(0,12)` 截断且不可复制，
 * 而日志过滤要**全长** —— 正好卡在「看得见但用不了」。
 *
 * ⚠ **别在调用点各写一份。** 本片有三个消费方，三份手写实现必然漂
 * （截断位数不一致 / 有的能复制有的不能 / tooltip 文案各异），
 * 与 `SystemLogViewer` 里 `buildLogQuery` 那条禁令是同一个母题。
 *
 * ⚠ **截断只影响显示，复制永远给全长。** 这是本组件存在的全部理由 ——
 * 用户要的是能粘进日志过滤框的那个值，不是好看的省略号。
 */
import { ActionIcon, CopyButton, Text, Tooltip, Group } from '@mantine/core'
import { IconCheck, IconCopy } from '@tabler/icons-react'

interface CopyableIdProps {
  /** 完整值（UUID 等）。空/`null` 时渲染成占位符，不渲染复制按钮。 */
  value: string | null | undefined
  /** 显示前几位；`0` 或不传 = 显示全长。复制**永远**是全长，与本参数无关。 */
  head?: number
  /** 覆盖显示文本（例如短标签）；仍然复制 `value` 全长。 */
  display?: string
  /** tooltip 里给的说明前缀，默认「点击复制」。 */
  label?: string
  size?: 'xs' | 'sm'
}

export function CopyableId({
  value,
  head = 8,
  display,
  label = '点击复制完整 ID',
  size = 'xs',
}: CopyableIdProps) {
  if (!value) {
    return (
      <Text size={size} c="dimmed" ff="monospace">
        —
      </Text>
    )
  }

  const shown = display ?? (head > 0 ? value.slice(0, head) : value)

  return (
    <Group gap={4} wrap="nowrap">
      <Text size={size} ff="monospace" c="dimmed" title={value}>
        {shown}
      </Text>
      {/* CopyButton 的 copy() 拿到的是 value —— 全长，跟 shown 无关 */}
      <CopyButton value={value} timeout={1500}>
        {({ copied, copy }) => (
          <Tooltip label={copied ? '已复制' : `${label}：${value}`} withArrow>
            <ActionIcon
              size={size === 'xs' ? 'xs' : 'sm'}
              variant="subtle"
              color={copied ? 'teal' : 'gray'}
              onClick={(e) => {
                e.stopPropagation() // 行本身可能是可点的，别把点击冒泡出去
                copy()
              }}
              aria-label={copied ? '已复制' : label}
            >
              {copied ? <IconCheck size={12} /> : <IconCopy size={12} />}
            </ActionIcon>
          </Tooltip>
        )}
      </CopyButton>
    </Group>
  )
}
