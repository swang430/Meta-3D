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

/**
 * P1-34: 日志行时间戳 → **本地时区**的 `HH:mm:ss.SSS`。
 *
 * 后端给的是带偏移的完整时刻（容器跑 UTC，形如
 * `"2026-08-05T02:58:00.352+00:00"`）。此前两个日志面板各自用**切字符串**
 * 的写法取时分秒（`ts.split('T')[1].slice(0,8)` / 正则 `/T(\d{2}:..)/`），
 * 把偏移量整个丢掉 —— 于是宿主机 10:58 的操作在界面上显示成 02:58，
 * 操作员对不上自己的手表，也就没法定位"我刚点的那一下"。
 *
 * ⚠ 两个面板必须共用本函数，别各写一份：复制出去的第二份迟早漂。
 *
 * 解析不出来时**如实回显原值**，不编一个时间出来。
 */
export function formatLogTime(
  ts: string,
  opts: { millis?: boolean; locale?: string } = {},
): string {
  if (!ts) return '—';
  const { millis = true, locale = 'zh-CN' } = opts;
  const d = parseServerDateTime(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleTimeString(locale, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    ...(millis ? { fractionalSecondDigits: 3 as const } : {}),
  });
}

/** P1-34: 日志行时间戳 → 本地时区的日期。语义同 {@link formatLogTime}。 */
export function formatLogDate(ts: string, locale = 'zh-CN'): string {
  if (!ts) return '';
  const d = parseServerDateTime(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleDateString(locale);
}

/**
 * P1-39: 一次执行的**人可读短标签** `YYYYMMDD-HHMMSS`（本地时区）。
 *
 * ⚠ **这不是索引，只是给人认的。** 真正用于过滤/跳转的永远是完整
 * `execution_id`（UUID）——用户原话是「测试例 ID 太长」，解法是给一个认得出的
 * 标签，**不是**再造一个短主键。别拿它当 key、别用它做等值查询。
 *
 * ⚠ **取本地时区，不取 UTC。** 后端建执行快照时用的是
 * `datetime.utcnow()`（`test_case_runner.py:134`，名字形如
 * `xxx [执行 20260805-151251]`），而日志面板 P1-34 已统一显示**本地时间**。
 * 本标签的用途是让人拿它跟**日志时间线和墙上的钟**对上，所以跟着日志走；
 * 与快照名相差一个时区偏移是**预期行为**，那是名字不是索引。
 */
export function formatExecutionTag(ts: string | null | undefined): string {
  if (!ts) return '—';
  const d = parseServerDateTime(ts);
  if (Number.isNaN(d.getTime())) return '—';
  const p = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}` +
    `-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`
  );
}
