# F64R-10 设计稿 — connect 失败泄漏 VISA 句柄(四个驱动)

> **状态**:⛔ **已撤销**(2026-07-26 晚, 用户拍板)。**本设计的前提错了** —— 实施两版
> 都被审查证明比原 bug 更坏, 判决与问题重定义见文末 §8。§1–§7 保留原文作历史记录,
> **不要照着做**。
> **对应 backlog**:[`guides/onsite-20260721-todo.md`](../guides/onsite-20260721-todo.md) F64R-10 / F64R-11
> **来源**:2026-07-26 用户请 Codex 单独 review `propsim_f64.py`,报了"初始化中途失败可能
> 泄漏 VISA socket"。我没照单收下,把它抽象成规则再全仓枚举 —— **结论比单文件结论大**。

---

## 1. 事实(AST 全仓核实,不是印象)

规则:**打开资源之后,任何失败路径都必须把它关掉。**

| 驱动 | connect 打开句柄 | open 之后还有几处 SCPI 往返 | 失败路径关句柄 |
|---|---|---|---|
| `propsim_f64` | ✅ `_visa_resource` | 2(`*IDN?` / `SYST:INFO?`,另有选件探测与 alignment 初始化) | ❌ |
| `propsim_fs16` | ✅ `_visa_resource` | 3 | ❌ |
| `uxm_base_station` | ✅ `_visa_session` | 6(含切 Test App + `*OPC?`) | ❌ |
| `rs_fsva` | ✅ `_visa_session` | 6(整套初始化下发) | ❌ |

四个 `connect()` 的收尾都是同一形状:

```python
except Exception as e:
    logger.error(...)
    self._status = InstrumentStatus.ERROR
    self._last_error = str(e)
    return False        # ← 句柄还开着
```

**Codex 只审了 `propsim_f64.py`,所以只能报一处。** 这条规则的适用点是四处。

## 2. 为什么这条是 P1 而不是洁癖

**F64 的 3334 端口只容一条远程 socket**(ATE AN §1.1.2.3)。泄漏一次 → 下一次 connect
被**自己上次的僵尸连接**挡在门外,现场表现是"连不上,重启 PropSim 才好"。

2026-07-21 现场最大的时间杀手正是"每次都要人工重连 / 最后只能重启 PropSim"。
**机理完全吻合,但我不声称这就是当时的根因** —— 当时没留下能证实的记录。
能确定的是:这个洞在,而且它产生的症状跟现场看到的一模一样。

其余三台是普通 TCP/HiSLIP,泄漏的后果轻一些(句柄耗尽 / 仪器侧会话数上限),
但**同一条规则**。

## 3. ⚠ 这个洞我已经修过一次 —— 在另一半

`disconnect()` 里早就有正确写法(最外层 `finally`,先捕获再同步关):

```python
_leaked = self._visa_resource
self._visa_resource = None
...
if _leaked is not None:
    try: _leaked.close()
    except Exception: pass
```

**我修了断开路,没修连接路。** 这是本周第 N 次"改一个方向、不改它的镜像"
(见 memory `feedback_fix_quality_domain_enumeration_first` 的 2026-07-26 复发记录)。
所以本项**不是发明新写法,是把已有的正确写法铺到它的镜像面上**。

## 4. 设计

### D1 【换源】抽一个共享的关闭助手,四个驱动共用

放 `app/hal/_visa_reconnect.py`(四个驱动已经共用它的 conn-lost 分类器,
且那里已有「ResourceManager 所有权」的权威说明段):

```python
def close_visa_quietly(handle) -> None:
    """关掉一条 VISA 句柄, 吞掉一切异常。

    ⚠ 只关**这条 resource**, 绝不碰 ResourceManager —— F64R-8 (#227) 的结论:
    `rm.close()` 会连带关掉别的驱动的会话。
    ⚠ 关一条半死的句柄本身可能抛 (会话已失效 / 底层 socket 已断), 所以吞异常:
    这里的目的只有一个 —— 别把句柄漏在外面。
    """
```

**为什么是一个函数而不是每个驱动各写一遍**:四份同样的 try/except 就是
"同一条规则存两份、改的时候只改一份"的标准配方 —— 本周已经踩过。

### D2 【收窄】connect 的失败路径捕获**局部**句柄,不读 `self.`

```python
opened = None
try:
    opened = await asyncio.to_thread(self._rm.open_resource, ...)
    self._visa_resource = opened
    ... 后续 SCPI 往返 ...
    return True
except Exception as e:
    ...
    if opened is not None:
        self._visa_resource = None       # 先摘字段
        close_visa_quietly(opened)       # 再关那条局部句柄
    return False
```

**为什么捕获局部而不是清理时读 `self._visa_resource`**:F64 有
`_silent_reconnect_visa`(open-new-then-close-old),字段可能在别处被换掉。
清理时读字段有关错对象的风险;捕获局部值只关"我这次开的那条",语义确定。
这跟 `disconnect()` 里 `_leaked = self._visa_resource` 是同一个道理
(那里是在锁内一次性捕获)。

### D3 【钉规则】结构性断言,不是逐驱动写四条用例

`tests/test_visa_connect_no_leak.py`:

1. **结构层**:AST 扫全部 HAL 驱动 —— 凡 `connect()` 里出现 `open_resource`,
   其异常处理路径**必须**出现 `close_visa_quietly`。新加驱动忘了 → 直接红。
   ⚠ 扫之前**剥注释与 docstring**:判据含命令/函数名字面量时会被文档本身污染
   (本周已被自己写的注释骗绿一次、骗红一次)。
2. **行为层**:参数化四个驱动,fake 让 `open_resource` 成功、**下一步 SCPI 抛异常**,
   断言 ① `connect()` 返回 False ② 那条句柄的 `close()` 被调用过 ③ 字段被摘成 None。
3. **反向**:connect 成功时**不许**关句柄(别把闸修成"连上了也关掉")。

### D4 【顺带】F64R-11(身份校验)必须跟本项**同一个 PR**,且排在其后

看起来是两件事,实际有**硬耦合**:

- F64R-11 = "`*IDN?` 回来的不是 PROPSIM 就拒绝连接" → 这**新增一条 connect 失败路径**。
- 如果先做 F64R-11、后做 F64R-10,那条新失败路径**天生带泄漏**,而且是最容易触发的
  一条(IP 填错时每次都走)。

所以顺序钉死:**先 D1–D3(堵漏),再加身份校验**。

身份校验本身**不用新造** —— `propsim_f64_health` 探针里已经有:
```python
_IDN_MODEL_TAGS = ("PROPSIM", "F8800")
```
把它下沉到驱动即可。枚举现状:**F64 / UXM / rs_fsva 三个只 `logger.info`,
只有 FS16 有校验** —— 又是"判据存在于一处、另三处没有"。

## 5. 范围

**做**:四个驱动 connect 的失败路径堵漏(D1–D3)+ 身份校验下沉(D4)。

**不做**(明确划走):
- Codex 同一份 review 里的另两条 —— **写完不查错误队列**(AST 枚举出 10 处,约 7 处真缺口)
  和 **FTP 边界**(无超时 / 无 `finally` / 部分上传当成功)。它们是独立母题,
  分别归 F64R-4 和一条新的 FTP 项,**不塞进本 PR**。
- 拆 5076 行单文件。Codex 的可维护性判断我认,但现在拆是纯风险无收益;
  等这批真缺陷修完、缝在哪清楚了再谈。

## 6. 验收

**本地**(全部可做,不需要现场):
- 四个驱动各一条行为用例:open 成功 + 下一步抛 → 句柄被关、字段摘空、返回 False。
- **变异自验**:把 `close_visa_quietly(opened)` 那行删掉,四条用例必须全红。
- 结构断言:临时给某个驱动的 connect 加一条不带清理的 `except` → 断言必须红。
- 反向:连接成功的路径不许调 `close`。
- 全量 + `scripts/dev-fixtures/mutation_sweep.py` 扫改动模块,空转必须为 0。

**现场**(不阻塞合并,属于"验它真解决了什么"):
- 故意把某台仪器的 IP 配错 → 连续点 5 次"重载 HAL" → 改回正确 IP → **一次就能连上**。
  修之前的预期是:F64 那台会被前几次的僵尸 socket 挡住。
  这条落在 `instrument_idn_sweep` 或新加一条诊断序列里,别用临时脚本。

## 7. 待决 / 风险

**待决①**:身份校验对不上时,`connect()` 应该 **返回 False** 还是 **连上但打 WARNING**?
- 返回 False = 彻底防"朝别的仪器发 F64 专用命令",但**如果某台机器的 `*IDN?`
  措辞跟我们的白名单不符**(本项目实证过"手册里有、这台回 -100"这类偏差),
  就会把一台好仪器锁在门外,而且是在现场。
- **我的建议:F64 返回 False,其余三台先打 WARNING。** 理由:F64 是唯一
  "发错命令会把业务层搞卡死"的(2026-07-21 实证反复 GO 卡死 PropSim);
  其余三台发错命令顶多报 -113。等现场确认过各家 `*IDN?` 的实际措辞再统一收紧。
- ⚠ 白名单要**可配**(`connection_params` 里能覆盖),否则现场撞上措辞偏差没有逃生门。

**风险①**:`close()` 一条半死的句柄可能**阻塞**(不是抛异常)。pyvisa 的 `close()`
一般不带超时。若真发生,connect 失败路径会卡住 HAL init。
→ 现有 `disconnect()` 里同样的写法已在生产跑了一段时间没见此症状,
所以先按同样写法做;**若现场出现"HAL 重载卡死",本条是第一嫌疑人**,已写进注释。

**已知未知**:F64 那条"泄漏导致下次连不上"的因果链,**我只验证了机理,没有现场证据**。
修完之后现场若仍需人工重连,说明还有别的原因,不要因为修了这条就停止排查。

---

## 8. 判决(2026-07-26 晚):撤销,问题重定义

三轮审查(设计 → 初版实施 → 重写版)的最终结论:**§1 的前提就错了,改动全部撤销**。
补丁存档于会话 scratchpad(`f64r10-drivers.patch` + 测试文件),没有丢。

### 三个把问题重新定性的事实(审查 agent 实跑证据,不是推演)

**① 泄漏的那条句柄是活的,字段指着它,安全停止命令靠它下发。**
§1 把"connect 中途失败句柄留着"当纯坏事 —— 错。失败后 `self._visa_x` 指着一条
**能用**的句柄,后续 `stop_signaling()` / `stop_emulation()` / `disconnect()` 正是
靠它把 `CELL:STATe OFF` / `GOS` / `CLOSE` 发出去。在失败点关它(重写版)或摘字段
(初版 D2)都会把"最坏 = 漏一条 socket"恶化成"**最坏 = 停止命令一条发不出去,
仪器带功率没人管**"。四条实跑对照:CMW500 小区 ON 再 connect 失败 / MXG 连接被取消 /
F64 失败后 `/hal/reload` / F64 冷却窗口内 stop —— 改后全部 `sent=[]`,改前全部落地。

**② 13 个驱动里 9 个没有懒重连。** "已关句柄抛 InvalidSession → 懒重连重开 →
命令落地"这条自愈链只在 F64 / FS16 / ENA / UXM 存在;F64 自己在 disconnect 路
(`_tearing_down` 挡懒重连)和 30s 冷却期内也拿不到。我在 UXM 上验证了这条链,
然后把结论**原样抄进 9 个没有这个机制的驱动**(grep 证实:那 9 个文件里
`_silent_reconnect` 只出现在抄进去的注释里)。

**③ 真正有害的泄漏是无人认领的孤儿连接,唯一实证入口在 connect 的覆盖点。**
成功 re-connect 时 `self._visa_resource = open_resource(...)` **直接覆盖旧值不关旧会话**,
上一条活 session 从此无人指着 —— `measure.py` 每个测量步骤 connect 一次,F64 上
一条就够堵死 3334。这才是"连不上,重启 PropSim 才好"的机理,而它恰恰是
"在 connect **失败**点关句柄"修不了的(失败路根本没走到覆盖那一步)。
> ⚠ 本判决初稿曾把"HAL reload 换对象"也列为入口 —— **#230 Codex P2 纠正,复核成立**:
> `reload_hal_service_atomic` 在一把锁里先 `shutdown()` 再建新,shutdown 对每个驱动
> 逐个 `await disconnect()` 且单驱动异常不中断循环(`instrument_hal_service.py`
> shutdown 循环 + `reload_hal_service_atomic`);F64 的 disconnect 外层 finally
> 连被取消都同步关句柄。**reload 主路径不造孤儿,别再朝"对象交接/登记"设计。**

### 判决

- **撤销**:13 驱动 finally 清理 + `close_visa_quietly` + `test_visa_connect_no_leak.py`
  全部恢复 main 行为。
- **§4-D2 本身就写着被禁的动作**:"先摘字段"一行正是 `_silent_reconnect_visa`
  docstring 明令禁止的置 None。设计评审时没人(包括写它的我)对照过那条禁令,
  实施第二轮才被审查抓出;第三轮换成"只关不摘"又撞上事实①。
  **教训:设计文档也要过 ⓪-②(grep 目标文件自己的禁令),不是只有代码要过。**
- **F64R-11 解耦**:§4-D4 的顺序约束作废 —— "身份校验新增的失败路径天生带泄漏"
  这个耦合理由随泄漏语义重定义而消失,F64R-11 可独立做。
  §7 待决①(F64 拒连 / 其余 WARNING + 白名单可配)仍有效。

### 问题重定义(转 backlog,见 todo F64R-10 条目)

要修的不是"connect 失败泄漏句柄",是 **"成功 re-connect 在覆盖点把上一条活
session 丢掉不关"**(唯一实证入口,见事实③;reload 入口已被 #230 Codex P2 排除)。
解法空间收窄到 connect 覆盖点本身,两个候选形状:
- **关旧再开新**:connect 入口若字段已指着句柄,先收尾再开
  (ATE AN §1.1.2.3;`_silent_reconnect_visa` 已是这个形状,不是新机制);
- **活句柄复用**:已连着且句柄活的就不重开(要定义"活"的判据,别拿 `!= None` 充数)。

⚠ 两个形状都必须**正面回答"关旧成功 + 开新失败"窗口** —— 字段既不许置 None
("失败不留死态",F64R-1)也不该假装旧句柄还在;`_silent_reconnect_visa` 对这个
窗口的现有处理(字段留在死句柄上 + 懒重连自愈)只在**有懒重连的 4 个驱动**成立,
9 个没有的怎么办是设计必答题,不是脚注。

任何后续方案的硬约束:
1. 动手前先回答:**那条句柄死的还是活的?谁还指着它?**
2. 行为覆盖铺满 13 个驱动 —— 9 个无懒重连驱动零覆盖,正是本次 P1 藏了两轮的直接原因。

### 实证收获(留给下一个碰这块的人)

- pyvisa 1.16.2:`Resource.close()` 后所有 IO 抛 `InvalidSession`;重复 close 是
  静默 no-op(它自己吞 InvalidSession)。**造 fake 必须复刻这个语义**,否则安全门
  变合格证打印机(fake 里 close 之后 write 还成功 = 物理上不可能的句柄)。
- `await asyncio.to_thread(rm.open_resource, ...)` 在 await 点被取消时,工作线程
  照样把 socket 开出来,返回值无人持有 —— **finally 兜不住这条**。F64 不可达时
  TCP 等待窗口最宽,恰是 `/hal/reload` 被取消的高发点。
- connect 内部的 `*IDN?` 撞 conn-lost 会触发懒重连,懒重连开出的新句柄不在任何
  "本次开的"手记清单里 —— **手记的账跟字段真值会漂**,判据要用字段本身。
