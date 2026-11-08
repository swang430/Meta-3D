"""UXM诊断的有界前置排队；不授予方言支持资格。

厂商 UXM5G_SCPI_03_LTE，LTE System > App Info > System error queue
(Section PD 1.9.1): 空队列返回 +0,"No error"；只列 NSA/SA，未确认IRAT。
保留既有profile命令用于诊断，不新增/推断命令。重复-113停止是应用层保守策略，
不是手册定义的队列终态；达到软件上限也不能认为干净。
"""
from app.diagnostics.sequences.uxm_scpi_compatibility import _parse_err


async def drain_diagnostic_errors(query, command, limit=100):
    reads = []
    if not command:
        return reads, "方言缺错误查询，未发送命令"
    previous = None
    for _ in range(limit):
        try:
            raw = await query(command)
        except Exception as exc:
            return reads, f"错误队列读取异常: {type(exc).__name__}: {exc}"
        reads.append(raw)
        code, text = _parse_err(raw or "")
        if code == 0:
            return reads, None
        if code is None:
            return reads, "错误队列回复读不出错误码，状态未知，诊断结论不可信"
        undefined = code == -113 and "UNDEFINED HEADER" in text.upper()
        if undefined and raw == previous:
            return reads, "连续两次相同-113，查询疑似不受支持，停止诊断"
        previous = raw if undefined else None
    return reads, f"已达{limit}条读取上限，尚未确认队列清空"
