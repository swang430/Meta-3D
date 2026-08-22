# P3-22 测试契约收敛设计

## 目标

把重复的测试源码收敛为显式产品契约矩阵，同时保留每个安全边界的独立用例身份、断言强度和变异保护。本片不以减少测试数量为目标，也不修改产品代码。

## 当前实证

- `git ls-files 'api-service/tests/**' 'gui/test/**'` 枚举出 216 个 tracked 文件、82,803 行；全后端基线为 4,228 passed / 5 skipped。
- AST 归一化只找到三类“外形重复”候选；逐条核对后，只有 HAL 模式决策表满足同一 fixture、同一路径、同一断言语义。
- `test_p1_49_static_route_order.py` 的两组测试分别保护静态路由不被 UUID 路由遮挡、UUID 详情路由仍可达，失败场景不同，保留。
- `test_bootstrap_lifespan.py` 与 `test_instrument_catalog_model_capabilities.py` 的数据库 fixture 分别服务应用 lifespan 与 catalog 模型能力，依赖覆盖和生命周期不同，保留。

## 契约矩阵

| 产品契约 / 故障 | 当前保护 | 裁决 |
|---|---|---|
| `MOCK_FORCE` 不得因仪器级 `real` 连接真实硬件 | 4 个同类测试方法 | 收敛到参数矩阵，保留 4 个具名 cell |
| legacy `MOCK` 仍尊重仪器级 `real` | 3 个同类测试方法 | 收敛到同一参数矩阵，保留 3 个具名 cell |
| `REAL` 默认真实，但仪器级 `mock` 必须覆盖 | 3 个同类测试方法 | 收敛到同一参数矩阵，保留 3 个具名 cell |
| 三个 wire value 与 `mock_force` 字符串稳定 | 2 个枚举测试 | 唯一保护，保留 |
| 静态路由与 UUID 详情路由同时可达 | 两组参数测试 | 两个不同故障，保留 |
| lifespan 与 catalog 的独立数据库上下文 | 两个局部 fixture | 生命周期不同，保留 |

## 实现

将 `_decide_use_real()` 的 10 个方法改为一张带稳定 case id 的 `pytest.mark.parametrize` 表。每个原输入组合仍单独执行、单独报告；枚举 wire contract 不变。不得抽象产品断言、合并不同预期或删除任何矩阵 cell。

## 验收

1. HAL 文件仍收集 12 个测试结果：10 个决策 cell + 2 个枚举契约。
2. 10 个 cell 的 `mode / instrument_mode / expected` 与改前逐项一致。
3. 反向变异能分别让真实/模拟边界用例变红。
4. 完整规则门与全后端回归通过，产品代码 diff 为空。
5. 报告被收敛的重复源码，以及经核实保留的非重复保护。

## 非目标

- 不按相似名称、相似断言或共享 fixture 形状批量删测试。
- 不降低规则门、硬件安全门或外审要求。
- 不执行 P2-40 的任何备份、隔离、移动、删除或 prune。
