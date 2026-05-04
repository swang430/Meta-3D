const TIMEZONE_RE = /Z$|[+-]\d{2}:?\d{2}$/;

export function parseServerDateTime(value: string): Date {
  return new Date(TIMEZONE_RE.test(value) ? value : value + 'Z');
}

export function formatServerDateTime(
  value: string,
  locale: string = 'zh-CN',
  options?: Intl.DateTimeFormatOptions,
): string {
  return parseServerDateTime(value).toLocaleString(locale, options);
}
