# P2-91 报告字体与层级

用户批准上一轮嵌入中文字体/标题正文分层方案并要求三项连续闭环。范围：报告 PDF 的字体渲染；P2-92/93 在后续独立 PR 实现。证书继续既有 CID 字体，不改数据/trust/SCPI。

## 四行契约与全集

- 输入：既有报告内容与模板；输出：相同数据、嵌入字体的报告 PDF。
- 真值：字体文件随 `app/` 分发，以模块路径定位；无系统字体/网络运行依赖。
- 失败：缺字体文件显式失败，不静默回退难以核验的系统替代字体。
- 排除：不改历史 PDF、不改变正式资格或 schema、不接触仪器。

字体消费全集：PDFGenerator 全部 stylesheet、表格 FONTNAME、Paragraph bold family；PDFCertificateGenerator 仍用旧 CJK_FONT。Docker COPY app/ 已覆盖字体资源。字体出处为 Noto CJK 官方 Sans/LICENSE（SIL OFL 1.1），保留许可与上游来源/固定 revision/构建方式。

## 实施顺序

1. baseline 既有报告/证书 25 passed。
2. RED：真实 PDF 中正文及标题 TrueType 字体嵌入、文本提取保留中文；标题粗体不是同一个文件；从不同 cwd 仍能加载。
3. GREEN：只替换报告字体，保留证书；随应用打包 regular/bold 字体并记录来源。
4. 相关报告/证书/rule gates，完整后端（首次功能）；真实 PDF 渲染检查。
5. 独立只读内审 → Ready PR → R1/R2 最新 HEAD → merge/main 同步/清理 → P2-92。

验证执行者为主代理，不为审查身份重复全量。字体为生成资产，使用上游资源及机械转换，不手写二进制。
