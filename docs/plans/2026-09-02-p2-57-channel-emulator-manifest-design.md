# P2-57 — Channel Emulator Capability Manifest（设计稿，待 review）

**日期**：2026-09-02　**状态**：✅ 已 review（用户 2026-09-02 拍板三条，见 §7）　**对应条目**：P2-57

---

## 1. 可观察故障（比 roadmap 条目写的更具体，且更严重）

roadmap 条目说「共同 `ChannelEmulatorDriver` 目前默认宣称所有信道仿真器支持
`EXTERNAL_WAVEFORM`」。取证后发现**根因是结构性的**，条目只看到了它的一个症状。

### 1.1 基类的抽象接口**根本不在基类上**

`app/hal/channel_emulator.py` 的 AST 顶层结构：

```
 95-210   ClassDef    ChannelEmulatorDriver          ← 类体只到 :210
213-489   FunctionDef normalize_channel_model_entries ← 一个模块级函数吞掉了 276 行
492-839   ClassDef    MockChannelEmulator
```

**14 个方法被嵌在 `normalize_channel_model_entries` 内部**（`:313`–`:487`）：

`set_mimo_config` / `set_path_loss` / `set_doppler` / `start_emulation` /
`stop_emulation` / `get_channel_state` / `upload_asc_files` /
`set_external_attenuators` / `set_baseband_power` /
`get_calibration_tone_capabilities` / `set_calibration_tone` /
`stop_calibration_tone` / `set_passthrough_mode` / `clear_passthrough_mode`

它们是死代码 —— 每次那个函数运行时被定义成局部函数，**永远不可能作为驱动方法被调用**。
实证：`hasattr(ChannelEmulatorDriver, "upload_asc_files")` → `False`。
该结构自 **2026-05-13** 存在（`git blame` :213）。

### 1.2 为什么至今没人发现

| 驱动 | 自己实现了几个 | 后果 |
|---|---|---|
| **F64** | 14 / 14 | 完全正常 |
| **Mock** | 14 / 14 | **测试永远绿** |
| **FS16** | **1 / 14** | 其余 13 个是 `AttributeError` |

F64 与 Mock 各自实现了全集，把结构缺陷完全掩盖。

### 1.3 具体的错误形态

FS16 的文件头（`:52-53`）写着这些方法「fall through to the abstract base's
`NotImplementedError`」——**这句是假的**。实证：

```
宣称支持的模式: ['external_waveform']          ← get_supported_load_modes()
→ AttributeError: 'RealPropsimFs16Driver' object has no attribute 'upload_asc_files'
```

即：能力门**放行**，然后崩在一个**不受控**的 `AttributeError` 上，
而不是被一条可操作的理由挡在门外。

### 1.4 同一件事的两个渠道互相矛盾，且诚实的那个没人读

| 渠道 | FS16 说什么 | 消费方 |
|---|---|---|
| `get_supported_load_modes()` | `[EXTERNAL_WAVEFORM]` —— **宣称支持** | **4 处真实消费**（`load_channel` 自己的门、`measure.py:1777`、gcm/b2 两个 strategy） |
| `InstrumentCapability("channel_loading")` | `supported=False`，描述写明未实现 | **零消费方** |

**决定的那个渠道说「支持」，诚实的那个渠道没人读** —— `feedback_effective_end_not_nominal` 的教科书形态。

---

## 2. ⚠️ 显而易见的修法**不安全**（本稿最重要的一条）

「把 14 个方法重新缩进回类里」看起来是一行修复，**但它会把 8 处静默跳过翻成运行时崩溃**：

| 站点 | 现在（FS16） | 天真修复后 |
|---|---|---|
| `services/mimo_ota/cleanup.py:157` `hasattr(emulator,"stop_emulation")` | False → **跳过清理** | True → 调用 → `NotImplementedError` |
| `executors/measure.py:2232` `not hasattr(...,"set_passthrough_mode")` | 走「不支持」分支 | 走另一支 |
| `executors/measure.py:2240` `hasattr(...,"stop_emulation")` | 跳过 | 调用 |
| `executors/measure.py:3769` `not hasattr(...,"set_baseband_power")` | 走降级分支 | 走另一支 |
| `api/instrument.py:4416 / :4418 / :4517` `getattr(driver, ..., None)` | None → 跳过 | 非 None → 调用 |
| `diagnostics/sequences/propsim_f64_p08_gate.py:307` `hasattr(ce, m)`（迭代 `_REQUIRED_METHODS`） | 缺就 reject | 恒有 → 门失效 |

⚠️ **初稿写「7 处」，实际是 8** —— 最后那处的第二实参是**变量**不是字面量
（`[m for m in _REQUIRED_METHODS if not hasattr(ce, m)]`），按字面量枚举时漏掉了。
内审 R1 找出。这正是 §2 想说的那件事的又一次实例：枚举的形态空间比想象的宽。

**这 8 处正是 P2-57 要替换掉的东西** —— 用 `hasattr` 当能力探测，
是「没有 manifest」时的将就做法。所以结构修复与 manifest **必须同片**，
先修结构会制造一次真实回归。

---

## 3. 双实证前置

### 3.1 memory

- `feedback_effective_end_not_nominal` —— §1.4 就是它的实例：判断要打在**被消费的那个渠道**上。
- `feedback_enumerate_before_changing` —— §2 的 8 处 `hasattr` 是「改之前先列全集」直接换来的；
  只看「我想改的那个文件」会把它们全漏掉。
- `feedback_gate_itself_can_be_fake` —— Mock 实现了全集 → 测试永远绿。
  **新门必须能在 Mock 之外发现问题**（见 §5 的不变量门）。

### 3.2 NotebookLM

本片**零新 SCPI**（roadmap 条目明写），只做声明与结构。按规则显式记：
**不涉及新的仪器语义，NotebookLM 此项不适用**。
（若 review 后决定顺带补 FS16 的真实实现，那部分必须先查 PROPSIM notebook。）

---

## 4. 范围建议

### 4.1 本片做

| # | 内容 |
|---|---|
| 1 | **建 Channel Emulator manifest**（结构照 `BaseStationAdapterManifest` 的既有形态：不可变、版本化、逐能力带 `support` 与 `source_reference`） |
| 2 | **把 14 个方法搬回 `ChannelEmulatorDriver`**，各自 `raise NotImplementedError` |
| 3 | **8 处 `hasattr` / `getattr` 探测换源到 manifest 查询** —— 与 2 同片，否则制造回归 |
| 4 | **FS16 的 manifest 如实声明**：`external_waveform` 载入、path loss、doppler、MIMO 全部 `not_implemented`；`get_supported_load_modes()` 随之收窄到**空**（今天返回 `[EXTERNAL_WAVEFORM]` 是假声明） |
| 5 | **registry 门**：manifest 声明 ⊆ 类实际实现（AST 派生，不靠 Mock） |

### 4.2 本片不做

| 不做 | 理由 |
|---|---|
| **FS16 的真实实现**（upload / start / path loss / doppler / MIMO） | 条目明写「FS16 在真实实现前不得宣称」——本片只负责**不宣称**；实现要先查 PROPSIM notebook，是独立一片 |
| **零新 SCPI** | 条目硬约束，本稿遵守 |
| **F64 行为变化** | 条目硬约束：F64 实现了全集，搬回基类对它是 no-op |

---

## 5. 门的设计（关键：**不能靠 Mock**）

Mock 实现了全部 14 个，所以任何「跑一遍 Mock 看通不通」的门对本片的故障**恒绿**。
新门必须从**代码结构**派生：

1. **类体完整性不变量**（AST）：`ChannelEmulatorDriver` 的抽象方法集合 ⊇ 那 14 个名字。
   变异：把任一方法移出类体 → 红。**这道门直接钉住本片的根因。**
2. **manifest ⊆ 实现**（AST）：manifest 声明 `implemented` 的每个能力，
   对应驱动类上必须有**自己的**定义（不算继承自基类的 `NotImplementedError` 桩）。
   变异：给 FS16 的 manifest 谎报一个能力 → 红。
3. **零 `hasattr` 探测**（AST 不变量，两条）：那 14 个名字既不得作为
   **字面量**出现在 `hasattr` / `getattr` 的第二实参，也不得经由**任何迭代形态**
   （普通 `for`、四种推导式、集合拼接）喂进去。后一条被连续绕过 5 次才收敛 ——
   每次都是「判据只认我当时想到的那种写法」。变异：五种写法各加回一处 → 红。
4. **FS16 的 `get_supported_load_modes()` 与 manifest 一致**（集合相等）。

## 6. 爆炸半径

- 原 bug 最坏：FS16 在 8 处服务层调用点崩 `AttributeError`（不受控，堆栈指向基类找不到属性）。
- 修完最坏：FS16 被 manifest **提前挡住**并给出可操作理由；F64 / Mock 行为不变。
- ⚠️ 风险点：§2 那 8 处换源。**每一处都要单独给行为门**，否则 4.1-2 与 4.1-3 之间
  任何一处漏改都会制造 §2 描述的那次回归。

## 7. Review 结论（用户 2026-09-02 拍板）

1. **可接受** —— FS16 的 `get_supported_load_modes()` 收窄到空。
   ⚠️ 拍板后补量的风险实证（本机 `meta3d_ota`）：`instrument_connections` **0 行**提到 FS16；
   `diagnostic_runs` 8 行**全是 `propsim_fs16_health`**（只读普查序列）；无执行记录、无配置引用。
   **没有任何实际跑过的东西依赖那个假声明**，收窄的实际爆炸半径为零。
2. **同片** —— 「搬回类里」与「8 处 `hasattr` 换源」一次做完（拆开的中间态就是 §2 那次回归）。
3. **信道仿真器要有自己的 manifest 结构**，不复用 `BaseStationAdapterManifest`。
   理由：基站 manifest 的脊梁是「MAC profile 逐维度取值域」，而信道仿真器的脊梁是
   **那 14 个操作各自实现没有** —— 硬套会带进一堆恒空的字段。
   本片的 manifest 以 **operation × support** 为主轴，附 load mode 与通道/端口基数。

## 8. 原 review 问题（存档）

1. **§4.1-4：把 FS16 的 `get_supported_load_modes()` 收窄到空**，是否可接受？
   后果是 FS16 从「看起来能跑 ASC」变成「明确不能」——**这是把一个假承诺换成真拒绝**，
   但如果现场有人正靠它跑，会立刻暴露。要不要先查一下有没有 FS16 的历史执行记录？
2. **§4.1-2/3 的搬回 + 换源要不要拆成两片**？拆开更小，但中间态就是 §2 那次回归；
   我倾向**同片**，代价是这一片会比较大（14 方法 + 7 站点 + manifest + 4 道门）。
3. **manifest 的结构照抄 `BaseStationAdapterManifest` 到什么程度**？
   完全照抄能复用 P2-46/54/55/56 那套（含 digest 与 registry 门）的经验，
   但信道仿真器没有「MAC profile 维度」这类概念，硬套会带进不需要的字段。
