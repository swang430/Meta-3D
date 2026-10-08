# P2-90 吞吐判据去理论依赖

已批准队列最后一片，base `0241dcef`（P2-89 PR #515已合并/main同步/清理）。严格WIP=1；不改变测量、仪器能力、provenance或hardware blocker。

## 设计与全集

1. `MIMOOTAPassCriteria.min_throughput_mbps` 变为可空、默认null，仅严格数值/有限数校验，不评价操作员数值合理性。存量显式300保持300，不猜其编辑历史；缺省不得补300。冻结配置是本次阈值真值，不读可变TestCase的第二份pass_criteria。
2. NR不再要求理论峰值；ratio/理论峰值留历史兼容但不参与当前判决、不提供有效编辑控件、不产生新的正式ratio。旧报告不篡改，其历史请求字段明确已弃用。
3. ANALYSIS在原完整真实证据门后，可信吞吐平均值与绝对阈值比较：低于FAIL，达到PASS；缺阈值为UNKNOWN，不自动PASS。Mock/缺测/无效证据原门不变。吞吐比值不得加入跨量纲margin；不新建“合理阈值”检查器。
4. `legacy_migration` 只保留显式绝对阈值，不从target/理论峰值推导；factory/canonical/create-session三入口同一可空语义。bootstrap已有显式模板阈值保留，其他road-test领域不改。
5. 共同报告列冻结阈值与测量/判决；比较服务不再从frozen theoretical peak重算当前正式ratio，缺旧字段不补默认。初始化不再生成重复理论峰值执行真值，但保留历史常量供兼容识别。
6. TestCase表单、commissioning现有入口/sessionBody、live/checked OpenAPI/generatedTS/手写类型一起收口：绝对阈值可留空，不强加300；撤ratio与理论控件。实际Mbps单位沿用原权威测量投影。

NotebookLM不新增查询：本片改变应用层操作员判据，不解释新仪器回读、单位或命令；不存在需要厂商证明的理论峰值。不得将本片阈值称为厂商/CTIA推荐值。

## 实施与验证

- 先RED：NR无峰值可冻结、默认无300、非有限/布尔/非法格式拒绝；合法显式阈值及legacy无判据不推导。
- 生产ANALYSIS反例覆盖无理论但可信96.5Mbps达到50阈值、低于100阈值、无阈值UNKNOWN、Mock/缺证据UNKNOWN；冻结后改源用例不影响本次判据。
- 比较读取/重建、报告/PDF、create-session与GUI契约同步RED→GREEN。
- 相关消费者+规则门；稳定最终全后端一次，GUI契约/build、compileall、Alembic head、diff-check。独立只读功能内审；Ready PR Codex R1→R2，最新HEAD R2无P1才merge/main同步/清理。
