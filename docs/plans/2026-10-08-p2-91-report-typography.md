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

## 已验记录

- RED：真实 PDF 新测试旧实现 `1 failed`（0个嵌入字体）；静态字体首次生成未更新内部 name table，字体混为 Thin，测试检出；追加 `--update-name-table` 后常规与粗体独立。
- 内审发现 FAIL 标记 `✗` 缺字；真实 phase/KPI PDF RED 提取含 `\x00`。所有九处同根字面量换 `×`，不改判词/颜色/分支。
- GREEN：`.venv/bin/python -m pytest -q tests/test_p2_91_report_typography.py tests/test_p1_22_report_trustworthy.py tests/test_p2_21_report_flags_cert_cjk.py tests/test_p2_88_report_traceability.py tests/test_rule_gates.py --color=no -o log_cli=false --show-capture=no --tb=short` → `125 passed, 74 warnings in 4.03s`。
- DB `SET TRANSACTION READ ONLY` 读取报告 `3eaa811a` 内存重渲染到 `/tmp/mimo-p2-91-preview.pdf`，未改生产 DB/PDF。`pdffonts` regular/bold 均 TrueType，emb/sub/uni=yes；渲染第4页检查中英文、标题、表格无遮挡。
- compileall、单 Alembic head `c1e3f5a7b9d2`、diff-check 通过。GUI/API schema 无改动，不重复 build/四镜像。
- 独立内审首次P2符号缺字，经同根修正增量复审 CLEAN；核心保护由 RED 证实，不为审查身份重复造变异。
- 全量由主代理唯一执行；两次中间版本在发现输入改变后主动 SIGINT，exit2，不计通过。最终稳定输入 `.venv/bin/python -m pytest -q --color=no -o log_cli=false --show-capture=no --tb=short` → `7031 passed, 17 skipped, 5397 warnings in 263.27s (0:04:23)`，exit0，日志 `/tmp/mimo-p2-91-stable-full.log`；此后仅本记录变化，不掩盖重复运行成本。
