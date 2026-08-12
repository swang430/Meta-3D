export interface LogFileInfo {
  filename: string
  size_bytes: number
  size_human: string
  last_modified: string
  is_current: boolean
}

export interface LogFileOption {
  value: string
  label: string
}

export interface LogFileCatalog {
  current: LogFileOption[]
  historyCategory: LogFileOption[]
  historyExecution: LogFileOption[]
}

const CATEGORY_LABELS: Record<string, string> = {
  app: '应用日志',
  audit: '审计日志',
  db: '数据库日志',
  frontend: '前端日志',
  scpi: 'SCPI 通信日志',
  channel_engine: '信道引擎日志',
  measurement: '测量日志',
  calibration: '校准日志',
  alert: '告警日志',
}

const EXECUTION_LOG_RE = /^exec-(.+)\.log$/
const ARCHIVE_DATE_RE = /(?:^|\.)(\d{4}-\d{2}-\d{2})(?:\.|$)/

function categoryLabel(filename: string): string {
  const match = filename.match(/^(.+?)\.log(?:\.|$)/)
  if (!match) return filename
  return CATEGORY_LABELS[match[1]] ?? filename
}

function archiveDate(file: LogFileInfo): string {
  return file.filename.match(ARCHIVE_DATE_RE)?.[1]
    ?? file.last_modified.replace('T', ' ').slice(0, 10)
}

function modifiedMinute(file: LogFileInfo): string {
  return file.last_modified.replace('T', ' ').slice(0, 16)
}

export function buildLogFileCatalog(files: LogFileInfo[]): LogFileCatalog {
  const catalog: LogFileCatalog = {
    current: [],
    historyCategory: [],
    historyExecution: [],
  }

  for (const file of files) {
    if (file.is_current) {
      catalog.current.push({
        value: file.filename,
        label: `${categoryLabel(file.filename)} · ${file.filename} · ${file.size_human}`,
      })
      continue
    }

    const execution = file.filename.match(EXECUTION_LOG_RE)
    if (execution) {
      catalog.historyExecution.push({
        value: file.filename,
        label: `${modifiedMinute(file)} · 执行 ${execution[1]} · ${file.filename} · ${file.size_human}`,
      })
      continue
    }

    catalog.historyCategory.push({
      value: file.filename,
      label: `${archiveDate(file)} · ${categoryLabel(file.filename)} · ${file.filename} · ${file.size_human}`,
    })
  }

  catalog.historyCategory.sort((a, b) => b.label.localeCompare(a.label))
  catalog.historyExecution.sort((a, b) => b.label.localeCompare(a.label))
  return catalog
}
