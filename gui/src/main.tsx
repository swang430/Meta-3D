import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MantineProvider, createTheme, ColorSchemeScript, localStorageColorSchemeManager } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import './index.css'
import App from './App.tsx'
import { setupMockServer } from './api/mockServer.ts'

setupMockServer()

const queryClient = new QueryClient()
const theme = createTheme({
  fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
  defaultRadius: 'md',
  colors: {
    brand: ['#edf7ff', '#d7ecff', '#b2d5ff', '#80b5ff', '#4d93ff', '#2c77f5', '#1d62d8', '#164fb3', '#134595', '#103a7b'],
  },
  primaryColor: 'brand',
})
const colorSchemeManager = localStorageColorSchemeManager({
  key: 'mimo-ota-color-scheme',
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ColorSchemeScript defaultColorScheme="light" />
      <MantineProvider theme={theme} defaultColorScheme="light" colorSchemeManager={colorSchemeManager}>
        <Notifications position="top-right" limit={3} />
        <App />
      </MantineProvider>
    </QueryClientProvider>
  </StrictMode>,
)
