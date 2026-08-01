# P1-22 设计稿 — 报告可信化（死键谓词 + CJK 字体 + 模板残留）

> 状态：**待 review**（v1）
> Roadmap：**P1-22**（2026-08-01 拍板从 Discovered 区提升；原临时代号 T1 已废 ——
> triage 出口只有 promoted to P1/P2/P3 or dropped，不另造编号体系）
> 双实证：memory ✅（修法红线已在 roadmap Discovered 条被内审 F1 + Codex #254 两轮
> 打磨写死）/ NotebookLM **不适用**（报告生成，不涉 UXM/F64 SCPI）

---

## 0. 事实（全部当场核过）

### 0.1 死键母题 — `executors/report.py` 全站点枚举（按整体不按局部）

| 站点 | 读什么 | 写方实况 | 后果 |
|---|---|---|---|
| `:164` | `analysis.get("overall_pass", False)` | analysis 写的是 `verdict`，**全仓无人写此键** | 恒 False → 报告恒 failed / 0.0% |
| `:235` | `precheck.get("overall_pass")` | precheck **只在失败分支写 False**，成功不写 | **半死键**：成功（键缺失）也判 FAIL |
| `:261` | 透传 `analysis.get("overall_pass")` | 同 `:164` | 恒 None 进报告 |
| `:262` | `analysis.get("pass_criteria_summary")` | 全仓无人写 | 恒 None |

canonical 真值源（`analysis.py:120-131`）：`verdict ∈ {"PASS","MARGINAL","FAIL"}`；
`TestExecution.validation_pass = (verdict in ("PASS","MARGINAL"))`（列，非 payload）。

### 0.2 禁区（上一片外审划定，本片红线）

- **禁** `status=='completed'` 判通过 —— 相位机械成功 ≠ KPI 通过，谎报通过代价不对称
- **禁** `bool(verdict)` —— "FAIL" 非空恒 True，反向翻车
- **禁动** `report_service.py` 的 `execution_summary` 兜底段 —— VRT 归档路径活代码（#254 R2）
- **禁动** `report_data_collector` 的 `validation_pass` 谓词 —— 现状正确（手动路径）

### 0.3 CJK 字体与模板

- `pdf_generator.py` 全文件零 `registerFont/TTFont/CID` 调用；字体使用面 3 处
  `setFont/fontName`（默认 Helvetica，无 CJK 字形 → 豆腐块）
- `Test Plan` 计划链残留 3 处（`:252` section 标题 / `:323` HTML 模板行 / `:371` 表行）

---

## 1. 目标与不做

**目标**：自动执行报告的 pass/fail 与相位真值一致；中文可读；计划链残留字段清掉。

**不做**：不动 0.2 的四个禁区；不重构报告架构（双路径并存现状保留）；
不做报告对比/分页等 backlog 功能。

## 2. 方案

### 2.1 谓词换源（4 站点一次收口）

- `:164` → 读 `context.test_execution.validation_pass`（首选，canonical 列）；
  上下文拿不到 execution 时兜 `analysis.get("verdict") in ("PASS", "MARGINAL")`
- `:235` → precheck 站点改**存在性安全**形态：成功分支补写 `overall_pass=True`
  （precheck 自己的键，补齐写方而不是改读方 —— 它的 PASS/FAIL 语义本就该自含）
- `:261` → 透传改 `verdict` 本值（报告里显示 PASS/MARGINAL/FAIL 三态，比布尔信息多）
- `:262` → `pass_criteria_summary` 死键**删站点**（无写方无消费真值，去掉 > 加机制）

### 2.2 CJK 字体：reportlab 内置 `STSong-Light`（UnicodeCIDFont）

零新增资产（CID 字体由阅读器端字形渲染），3 处使用面全换。
乙案（捆绑 Noto Sans CJK .ttf）字形更可控但要进 repo ~16MB 字体文件 —— 不取。

### 2.3 模板残留：3 处 `Test Plan` 字段改「来源」（执行来源：用例执行/暗室首测），
取 `executed_by` 语义映射，不再显示恒 N/A 的计划名。

## 3. 待决

- ①（§2.2）字体走内置 STSong-Light（我倾向，零资产）还是捆绑 Noto？
- ②（§2.3）`Test Plan` 字段是**改成「来源」**（我倾向，字段还有用）还是整行删？

## 4. 门（诚实分档）

- **D-1 行为门**：verdict 三形态（PASS/MARGINAL/FAIL）× 自动报告
  `overall_result`/`pass_rate` 断言 + precheck 成功分支补键断言。
  **变异**：谓词改回 `analysis.get("overall_pass")` → PASS 形态断言必须红；实跑。
- **D-2 CJK 存在性门**：生成的 PDF 字节里 `STSong` 字体对象存在 + 标题文本可提取
  非 ■（存在性档，粗筛）；**配套 D-3 人工看 PDF**（行为验证，截图为证）。
- **D-4 申报**：模板视觉布局无自动门，靠 D-3 人工。

## 5. 验收

1. D-1 绿 + 变异红对位实跑
2. S6 那条执行重新出报告：Pass Rate 与 verdict 一致、标题中文可读、无 Test Plan: N/A
3. VRT 归档路径回归（`report_service` 兜底段行为不变）— 现有测试suite 全量绿
4. ⓪⁺ 全流程：内审 → Codex 四通道 → merge → 迟到回查
