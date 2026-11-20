# 增量独立内审：功能结论 CLEAN

全套首次内审后的定点增量复审。未修改源码、测试或样本；未调用网络、应用或硬件。

## 两条原发现处理

- F1已关闭：实际逐径文件每帧的time_seconds和frame_index现在与wrapper逐项比较；来源模型TIMESTAMP必须等于已核验原始秒的半入毫秒结果。旧复现中仅修改wrapper时间并重绑身份文件，现在在进入单帧换算之前抛出“原始时间或帧索引与实际逐径来源不一致”。_convert_trajectory仍做时间赋值，但赋的是已经一致性核验的同一派生值，不再覆盖矛盾来源。
- F2已关闭：_rounded_time在局部Decimal上下文按输入位数确定精度。旧长精度输入现在实算1000ms，与70位独立参考一致；原1ms错误不再出现。

实跑定点证据：/tmp/gcm-trajectory-review-r2-probe.log。该脚本预期以原F1场景抛ValueError结束，因此退出1是旧错误场景被拒绝的证据，不是声称整套测试通过。

## 验证与同根枚举

已读取并复用主代理最新/tmp/gcm-trajectory-green.log：16项、OK。未重复跑相同输入全量。已读取/tmp/gcm-trajectory-mutations.log：实际文件字节校验、生灭拒绝、毫秒碰撞三项变异均产生相应测试失败，源文件未改。原本固定槽位保护的独立临时变异结果仍有效。

本轮遍历time_seconds/frame_index/TIMESTAMP/raw_paths/_rounded_time/original_time_seconds所有读写点：实际文件核验 → 同源取整 → CSV行 → 清单原始值与取整值未见同根遗漏。完整帧哈希仍覆盖时序字段，模型/导出公共时间也在来源内容比较范围内。0.3m、25波长与单一方向门未因本次换源被绕过。

脚本SHA256：5054ccb000403a2024098b854ca68624c32869d94c020fa9e077222eb2b82dd7。
测试SHA256：e76e0ee4296d19155ff2428e5e081758c411791bccb33236f3d80b42aa27a47a。

## 交付前待完成项（已知依赖，不重复报缺陷）

- 单帧依赖仍须先合并，再在合入正式依赖版本上运行相关测试和端到端；本轮使用只读PYTHONPATH依赖，不证明合并后交付已完成。
- 主代理已说明会更新README的raw_paths时间字段。审阅时scripts/gcm_trajectory.md第22行仍只列paths，需补time_seconds/frame_index及TIMESTAMP派生约束。这是主代理已承诺正在进行的说明同步；本轮功能修复已清，不新增机制或额外测试要求。
- 后端全量、GUI构建按原分档不适用；本报告不代表GitHub外审或厂商导入/设备验收。

无新功能发现；无需对已关闭问题继续扩建测试。
