/**
 * Top-level React ErrorBoundary.
 *
 * Catches render-time exceptions from any descendant, ships them to the
 * frontend log channel, and shows a recoverable fallback UI instead of a
 * blank page. Errors that propagate past this boundary previously vanished
 * silently — only the browser console saw them.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button, Code, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { IconAlertTriangle, IconRefresh } from '@tabler/icons-react'
import { logFrontendEvent } from './frontendLogger'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    logFrontendEvent({
      level: 'ERROR',
      action: 'react_error_boundary',
      component: 'AppErrorBoundary',
      message: error.message,
      error: `${error.stack || error.message}\n--- componentStack ---\n${info.componentStack ?? '(none)'}`,
    })
  }

  private handleReset = (): void => {
    this.setState({ error: null })
  }

  private handleReload = (): void => {
    if (typeof window !== 'undefined') {
      window.location.reload()
    }
  }

  render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children

    return (
      <Paper p="xl" m="xl" withBorder>
        <Stack gap="md">
          <Group gap="sm">
            <IconAlertTriangle size={28} color="var(--mantine-color-red-6)" />
            <Title order={3}>页面渲染出错</Title>
          </Group>
          <Text c="dimmed">
            该错误已发送至服务端 frontend.log。可以"重置"重试当前页面，或"刷新"重载整个应用。
          </Text>
          <Code block style={{ whiteSpace: 'pre-wrap', maxHeight: 320, overflow: 'auto' }}>
            {error.stack || error.message}
          </Code>
          <Group>
            <Button leftSection={<IconRefresh size={16} />} onClick={this.handleReset}>
              重置当前页面
            </Button>
            <Button variant="light" onClick={this.handleReload}>
              刷新整个应用
            </Button>
          </Group>
        </Stack>
      </Paper>
    )
  }
}
