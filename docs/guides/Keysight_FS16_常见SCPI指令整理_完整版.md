# Keysight PROPSIM FS16 常见 SCPI 指令整理（含 emulation 回放控制）

> 适用对象：Keysight PROPSIM FS16 / F8820A 信道模拟器。
> 重点用途：`.smu` emulation 文件加载、运行/暂停/停止/关闭、系统状态查询、输入输出电平设置、信道模型信息查询、参考时钟与连接器查询、自动化测试脚本编写。
> 注意：不同固件版本、选件授权、连接方式、GUI/ATE 同时操作状态可能导致部分命令不可用或返回不同结果。实际执行前建议结合设备自带的 Programming Guide / User Reference 核对。

---

## 1. 使用前说明

### 1.1 SCPI 命令大小写

SCPI 命令通常不区分大小写。手册中大写字母表示该命令字段的最短写法。

例如：

```scpi
SYSTem:ERRor?
```

可以写成：

```scpi
SYST:ERR?
```

也可以写成：

```scpi
system:error?
```

工程脚本中建议统一使用短写或长写，不要混用太多风格。

---

### 1.2 推荐的基本控制流程

PROPSIM 的 ATE / SCPI 控制一般按下面流程使用：

```text
1. 打开 emulation 文件
2. 修改或查询 emulation 参数
3. 运行 emulation，执行测试或测量
4. 停止并关闭 emulation
```

典型 SCPI 流程：

```scpi
*CLS
SYST:ERR?
CALC:FILT:FILE D:\User Emulations\test_2x2.smu
*OPC?
SYST:ERR?
DIAG:SIMU:STATE?
DIAG:SIMU:GO
DIAG:SIMU:STATE?
```

---

## 2. 常用指令总表

| 类别 | 功能 | SCPI 指令 | 常用短写 | 备注 |
|---|---|---|---|---|
| 通用 | 清除状态/错误队列 | `*CLS` | `*CLS` | 自动化开始前常用 |
| 通用 | 查询设备身份 | `*IDN?` | `*IDN?` | 返回厂家、设备、序列号、版本 |
| 通用 | 等待操作完成 | `*OPC?` | `*OPC?` | 返回 `1` 表示前序操作完成 |
| 通用 | 等待后续执行 | `*WAI` | `*WAI` | 阻塞直到无 pending operation |
| 通用 | 复位设备 | `*RST` | `*RST` | 会关闭 emulation，谨慎使用 |
| 通用 | 查询自检结果 | `*TST?` | `*TST?` | 返回自检状态 |
| 通用 | 查询状态字节 | `*STB?` | `*STB?` | 自动化监控用 |
| 系统 | 查询错误队列 | `SYSTem:ERRor?` | `SYST:ERR?` | 关键步骤后建议查询 |
| 系统 | 查询 SCPI 版本 | `SYSTem:VERSion?` | `SYST:VERS?` | 手册示例返回 `1999.0` |
| 系统 | 系统复位 | `SYSTem:RESet` | `SYST:RES` | 会关闭 emulation |
| 系统 | 查询系统信息/授权 | `SYSTem:INFO?` | `SYST:INFO?` | 返回设备、通道数、接口、频段、license 等 |
| 系统 | 查询系统告警 | `SYSTem:STATus?` | `SYST:STAT?` | 查询输入截断、数字削波、参考异常等 |
| 系统 | 关闭所有发射源 | `SYSTem:TRANSmitter:OFF` | `SYST:TRANS:OFF` | 关闭 PROPSIM RF transmitting sources |
| 文件 | 打开 emulation | `CALCulate:FILTer:FILE <filename>` | `CALC:FILT:FILE <filename>` | 直接加载 `.smu` |
| 文件 | 以编辑模式打开 | `CALCulate:FILTer:EDIT <filename>` | `CALC:FILT:EDIT <filename>` | 用于先改参数再加载 |
| 文件 | 将编辑态加载到硬件 | `CALCulate:FILTer:CONNECT` | `CALC:FILT:CONN` | 与 `EDIT` 配合 |
| 回放 | 开始运行 | `DIAGnostic:SIMUlation:GO` | `DIAG:SIMU:GO` | Run / Play emulation |
| 回放 | 暂停 | `DIAGnostic:SIMUlation:STOP` | `DIAG:SIMU:STOP` | 暂停，不回到起点 |
| 回放 | 继续 | `DIAGnostic:SIMUlation:CONTinue` | `DIAG:SIMU:CONT` | 从暂停位置继续 |
| 回放 | 停止并回到起点 | `DIAGnostic:SIMUlation:GOStart` | `DIAG:SIMU:GOS` | Stop + rewind |
| 回放 | 单步到下一个 CIR | `DIAGnostic:SIMUlation:STEP` | `DIAG:SIMU:STEP` | emulation 非运行状态下使用 |
| 回放 | 跳转到指定 CIR/时间 | `DIAGnostic:SIMUlation:GOTO ...` | `DIAG:SIMU:GOTO ...` | 需先暂停或停止 |
| 回放 | 查询运行状态 | `DIAGnostic:SIMUlation:STATE?` | `DIAG:SIMU:STATE?` | 返回 CLOSED/RUNNING 等 |
| 回放 | 查询当前 CIR/时间 | `DIAGnostic:SIMUlation:MODel:STATE?` | `DIAG:SIMU:MOD:STATE?` | 返回各通道位置 |
| 回放 | 查询模型输入/通道/输出数 | `DIAGnostic:SIMUlation:MODel:INFO?` | `DIAG:SIMU:MOD:INFO?` | 返回 inputs,channels,outputs |
| 回放 | 查询插入时延 | `DIAGnostic:SIMUlation:MODel:DELAY?` | `DIAG:SIMU:MOD:DEL?` | 单位 μs |
| 回放 | 查询是否连续模型 | `DIAGnostic:SIMUlation:MODel:CONTinuous?` | `DIAG:SIMU:MOD:CONT?` | 返回 0/1 |
| 回放 | 关闭 emulation | `DIAGnostic:SIMUlation:CLOSE` | `DIAG:SIMU:CLOSE` | 关闭当前 emulation |
| 输入 | 使能/关闭输入 | `INPut:ENable <input>,<0/1>` | `INP:EN <input>,<0/1>` | 0 关闭，1 使能 |
| 输入 | 查询输入状态 | `INPut:ENable? <input>` | `INP:EN? <input>` | 返回 0/1 |
| 输入 | 设置平均输入电平 | `INPut:LEVel:AMPlitude:CH <input>,<dBm>` | `INP:LEV:AMP:CH <input>,<dBm>` | 单位 dBm |
| 输入 | 查询平均输入电平 | `INPut:LEVel:AMPlitude:CH? <input>` | `INP:LEV:AMP:CH? <input>` | 单位 dBm |
| 输入 | 查询输入电平限制 | `INPut:LEVel:AMPlitude:LIMits? <input>` | `INP:LEV:AMP:LIM? <input>` | 返回 lower,upper |
| 输入 | 测量输入电平/峰均比 | `INPut:LEVel:MEASure? <input>,<time>` | `INP:LEV:MEAS? <input>,<time>` | time 可为 0.5/1/3/5/10 s |
| 输入 | 自动设置输入电平/峰均比 | `INPut:LEVel:AUTOSET <input>,<time>` | `INP:LEV:AUTOSET <input>,<time>` | input=0 表示所有输入 |
| 输入 | 取消自动测量 | `INPut:LEVel:AUTOSETCANCEL` | `INP:LEV:AUTOSETCANCEL` | 取消正在进行的 autoset |
| 输入 | 设置 crest factor | `INPut:CREst:SET <input>,<dB>` | `INP:CRE:SET <input>,<dB>` | 单位 dB |
| 输入 | 查询 crest factor | `INPut:CREst:GET? <input>` | `INP:CRE:GET? <input>` | 单位 dB |
| 输入 | 查询输入接口类型 | `INPut:IF:TYPE? <input>` | `INP:IF:TYPE? <input>` | 例如 RF |
| 输入 | 设置输入测量模式 | `INPut:MEASure:MODE:SET <input>,<mode>` | `INP:MEAS:MODE:SET <input>,<mode>` | 0/1/2/3 |
| 输入 | 查询输入测量模式 | `INPut:MEASure:MODE:GET? <input>` | `INP:MEAS:MODE:GET? <input>` | 0/1/2/3 |
| 输入 | AILC 使能/关闭 | `INPut:LEVel:AUTO:ENAble <input>,<0/1>` | `INP:LEV:AUTO:ENA <input>,<0/1>` | Automatic Input Level Control |
| 输入 | 查询 AILC 状态 | `INPut:LEVel:AUTO:ENAble? <input>` | `INP:LEV:AUTO:ENA? <input>` | 返回 0/1 |
| 输出 | 使能/关闭输出 | `OUTPut:ENable <output>,<0/1>` | `OUTP:EN <output>,<0/1>` | 0 关闭，1 使能 |
| 输出 | 查询输出状态 | `OUTPut:ENable? <output>` | `OUTP:EN? <output>` | 返回 0/1 |
| 输出 | 设置平均输出电平 | `OUTPut:LEVel:AMPlitude:CH <output>,<dBm>` | `OUTP:LEV:AMP:CH <output>,<dBm>` | 单位 dBm |
| 输出 | 查询平均输出电平 | `OUTPut:LEVel:AMPlitude:CH? <output>` | `OUTP:LEV:AMP:CH? <output>` | 单位 dBm |
| 输出 | 查询输出电平限制 | `OUTPut:LEVel:AMPlitude:LIMits? <output>` | `OUTP:LEV:AMP:LIM? <output>` | 返回 lower,upper |
| 输出 | 设置输出增益 | `OUTPut:GAIN:CH <output>,<dB>` | `OUTP:GAIN:CH <output>,<dB>` | 单位 dB |
| 输出 | 查询输出增益 | `OUTPut:GAIN:CH? <output>` | `OUTP:GAIN:CH? <output>` | 单位 dB |
| 输出 | 查询输出增益限制 | `OUTPut:GAIN:LIMits? <output>` | `OUTP:GAIN:LIM? <output>` | 返回 lower,upper |
| 输出 | 设置输出相位 | `OUTPut:PHAse:DEGrees:CH <output>,<deg>` | `OUTP:PHA:DEG:CH <output>,<deg>` | 单位 degree |
| 输出 | 查询输出相位 | `OUTPut:PHAse:DEGrees:CH? <output>` | `OUTP:PHA:DEG:CH? <output>` | 单位 degree |
| 信道 | 查询模型增益 | `CHannel:MODel:GAIN:MODel? <ch>` | `CH:MOD:GAIN:MOD? <ch>` | 单位 dB |
| 信道 | 查询总增益 | `CHannel:MODel:GAIN:TOTal? <ch>` | `CH:MOD:GAIN:TOT? <ch>` | 含模型、输入、输出设置 |
| 信道 | 设置通道使能 | `CHannel:MODel:ENABLE <ch>,<0/1>` | `CH:MOD:ENABLE <ch>,<0/1>` | 0 关闭，1 使能 |
| 信道 | 查询通道使能 | `CHannel:MODel:ENABLE? <ch>` | `CH:MOD:ENABLE? <ch>` | 返回 0/1 |
| 信道 | 查询 `.sim` 控制文件 | `CHannel:MODel:FILE:CIR? <ch>` | `CH:MOD:FILE:CIR? <ch>` | 返回模型控制文件 |
| 信道 | 查询源模型文件 | `CHannel:MODel:FILE:SOURCE? <ch>` | `CH:MOD:FILE:SOUR? <ch>` | 返回源文件 |
| 信道 | 查询 CIR 数量 | `CHannel:MODel:CIR? <ch>` | `CH:MOD:CIR? <ch>` | 返回 impulse response 数 |
| 信道 | 查询 sample density | `CHannel:MODel:SD? <ch>` | `CH:MOD:SD? <ch>` | 返回采样密度 |
| 信道 | 查询模型时长 | `CHannel:MODel:TIME? <ch>` | `CH:MOD:TIME? <ch>` | 单位 s |
| 信道 | 查询是否相关模型 | `CHannel:MODel:CORRelating? <ch>` | `CH:MOD:CORR? <ch>` | 返回 0/1 |
| 路由 | 设置参考时钟 | `ROUTe:PATH:REFerence <EXT/INT>` | `ROUT:PATH:REF <EXT/INT>` | 外参考/内参考 |
| 路由 | 查询参考时钟 | `ROUTe:PATH:REFerence?` | `ROUT:PATH:REF?` | 返回 EXT/INT |
| 路由 | 查询通道物理连接器 | `ROUTe:PATH:CONNector? <ch>` | `ROUT:PATH:CONN? <ch>` | 返回 RF 输入/输出等信息 |
| 校准 | 设置校准 | `SYSTem:CALIBration:SET <name>` | `SYST:CALIB:SET <name>` | 例如 `No calibration` |
| 校准 | 查询当前校准 | `SYSTem:CALIBration:GET?` | `SYST:CALIB:GET?` | 返回当前校准名 |
| 校准 | 查询校准列表 | `SYSTem:CALIBration:LIST?` | `SYST:CALIB:LIST?` | 返回可用校准 |
| Lab setup | 设置 lab setup | `SYSTem:LABsetup:SET <name>` | `SYST:LAB:SET <name>` | 例如 `No lab setup` |
| Lab setup | 查询当前 lab setup | `SYSTem:LABsetup:GET?` | `SYST:LAB:GET?` | 返回当前设置 |
| Lab setup | 查询 lab setup 列表 | `SYSTem:LABsetup:LIST?` | `SYST:LAB:LIST?` | 返回可用列表 |
| 监测 | 设置 UDP 测量目标 | `SYSTem:MEASurements:TARget:SET ...` | `SYST:MEAS:TAR:SET ...` | 用于 emulation data sending |
| 监测 | 查询 UDP 测量目标 | `SYSTem:MEASurements:TARget:GET?` | `SYST:MEAS:TAR:GET?` | 返回启用状态、端口、IP |
| 监测 | 设置数据元素上报 | `SYSTem:MEASurements:ELEment:SET ...` | `SYST:MEAS:ELE:SET ...` | 输入功率、输出功率、多普勒等 |
| 监测 | 查询数据元素上报 | `SYSTem:MEASurements:ELEment:GET? <type>` | `SYST:MEAS:ELE:GET? <type>` | 返回 enabled,interval |
| 可选 | 设置高增益模式 | `DIAGnostic:SIMUlation:HIGHGAIN:SET <0/1>` | `DIAG:SIMU:HIGHGAIN:SET <0/1>` | 需根据测试配置确认 |
| 可选 | 查询高增益模式 | `DIAGnostic:SIMUlation:HIGHGAIN:GET?` | `DIAG:SIMU:HIGHGAIN:GET?` | 返回 0/1 |
| 可选 | 设置插值模式 | `DIAGnostic:SIMUlation:INTERPolation:SET <0/1>` | `DIAG:SIMU:INTERP:SET <0/1>` | 0 无插值，1 系数插值 |
| 可选 | 查询插值模式 | `DIAGnostic:SIMUlation:INTERPolation:GET?` | `DIAG:SIMU:INTERP:GET?` | 返回 0/1 |

---

## 3. 通用 SCPI / 状态控制指令

### 3.1 查询设备身份

```scpi
*IDN?
```

可能返回：

```text
Company Name,Device Name,Serial Number,Firmware Version Number
```

用途：确认是否连到了正确的 FS16 / PROPSIM 设备。

---

### 3.2 清除状态和错误队列

```scpi
*CLS
```

用途：

- 清空 Error/Event Queue；
- 清空部分状态寄存器；
- 建议每个自动化脚本开始时执行。

---

### 3.3 等待前序操作完成

```scpi
*OPC?
```

返回：

```text
1
```

用途：加载 `.smu`、connect、校准等耗时操作之后等待完成。

注意：`*OPC?` 只表示操作完成，不表示没有错误。建议后面再执行：

```scpi
SYST:ERR?
```

---

### 3.4 查询错误队列

```scpi
SYST:ERR?
```

正常返回：

```text
0,"No error"
```

建议在这些步骤后查询：

```scpi
CALC:FILT:FILE ...
*OPC?
SYST:ERR?

DIAG:SIMU:GO
SYST:ERR?

DIAG:SIMU:CLOSE
SYST:ERR?
```

---

### 3.5 查询系统状态

```scpi
SYST:STAT?
```

可能返回：

```text
1
```

表示当前没有支持项里的 warning/caution 激活。

也可能返回类似：

```text
0,Warning: External Reference missing
```

常见告警源包括：

- Input cut-off；
- Digital Clipping；
- Reference status；
- Unstable level settings。

---

### 3.6 查询系统信息和授权

```scpi
SYST:INFO?
```

返回内容一般包括：

```text
<Device Name>,<Number of channels>,<Interface>,<Device HW version>,<Number of Internal RFLOs>,<Band#1>,...,<License#1>,...
```

用途：

- 查看设备型号；
- 查看可用通道数；
- 查看频段；
- 查看 license / option；
- 排查某些命令不可用是否与授权有关。

---

### 3.7 关闭所有发射源

```scpi
SYST:TRANS:OFF
```

用途：关闭所有 PROPSIM RF transmitting sources，包括 PROPSIM 控制的外部 RF 源。

建议在异常退出或测试结束后谨慎使用。

---

## 4. Emulation 文件打开、编辑与加载

### 4.1 直接打开 `.smu` emulation 文件

```scpi
CALC:FILT:FILE D:\User Emulations\test_2x2.smu
```

完整写法：

```scpi
CALCulate:FILTer:FILE D:\User Emulations\test_2x2.smu
```

如果通信工具要求路径分隔符转义，可能需要写成：

```scpi
CALC:FILT:FILE D:\\User Emulations\\test_2x2.smu
```

推荐流程：

```scpi
*CLS
CALC:FILT:FILE D:\User Emulations\test_2x2.smu
*OPC?
SYST:ERR?
DIAG:SIMU:STATE?
```

---

### 4.2 以编辑模式打开 emulation

```scpi
CALC:FILT:EDIT D:\User Emulations\test_2x2.smu
```

用途：打开后先修改参数，再加载到硬件。

典型场景：先改中心频率、输入输出设置，再 connect。

---

### 4.3 将编辑态 emulation 加载到硬件

```scpi
CALC:FILT:CONN
```

典型流程：

```scpi
CALC:FILT:EDIT D:\User Emulations\test_2x2.smu
# 修改需要的参数
CALC:FILT:CONN
*OPC?
SYST:ERR?
```

---

## 5. Emulation 回放控制指令

### 5.1 开始回放

```scpi
DIAG:SIMU:GO
```

完整写法：

```scpi
DIAGnostic:SIMUlation:GO
```

用途：开始运行当前已加载的 emulation，对应 GUI 中的 Run / Play。

---

### 5.2 暂停回放

```scpi
DIAG:SIMU:STOP
```

注意：`STOP` 是暂停，不会回到起点。

---

### 5.3 继续回放

```scpi
DIAG:SIMU:CONT
```

从暂停位置继续运行。

---

### 5.4 停止并回到起点

```scpi
DIAG:SIMU:GOS
```

完整写法：

```scpi
DIAGnostic:SIMUlation:GOStart
```

含义：

```text
Stop + rewind to start
```

即停止 emulation，并回到起始位置。

---

### 5.5 单步到下一个 CIR

```scpi
DIAG:SIMU:STEP
```

用途：emulation 没有运行时，单步推进到下一次 channel impulse response 变化。

---

### 5.6 跳转到指定 CIR

```scpi
DIAG:SIMU:GOTO 1,99
```

含义：跳转到 channel 1 的第 99 个 CIR。

注意：

```text
执行 GOTO 前，emulation 必须处于 STOPPED / paused 状态。
```

推荐：

```scpi
DIAG:SIMU:STOP
DIAG:SIMU:GOTO 1,99
DIAG:SIMU:MOD:STATE?
```

---

### 5.7 跳转到指定时间

```scpi
DIAG:SIMU:GOTO 2 s
```

含义：跳转到第 2 秒。

注意：时间单位写 `s`。

---

### 5.8 查询回放状态

```scpi
DIAG:SIMU:STATE?
```

可能返回：

| 返回值 | 含义 |
|---|---|
| `CLOSED` | 未加载 emulation |
| `OPENING` | 正在打开 emulation |
| `STOPPING` | 正在停止 |
| `STOPPED` | 已停止/暂停，未运行 |
| `RUNNING` | 正在运行 |
| `EDITING` | 正在编辑 |
| `CLOSING` | 正在关闭 |

---

### 5.9 查询当前回放位置

```scpi
DIAG:SIMU:MOD:STATE?
```

返回格式通常类似：

```text
<channel>,<cir number>,<current emulation time>,...
```

示例：

```text
1,345,2.3,2,345,2.3,3,99,2.3
```

表示各通道当前 CIR 号和当前 emulation time。

---

### 5.10 查询模型拓扑信息

```scpi
DIAG:SIMU:MOD:INFO?
```

返回格式：

```text
<number of inputs>,<number of channels>,<number of outputs>
```

示例：

```text
2,4,2
```

表示 2 个输入、4 个信道、2 个输出。

---

### 5.11 查询模型插入时延

```scpi
DIAG:SIMU:MOD:DEL?
```

返回单位通常为微秒：

```text
3.5
```

---

### 5.12 查询 emulation 是否连续

```scpi
DIAG:SIMU:MOD:CONT?
```

返回：

| 返回值 | 含义 |
|---|---|
| `0` | 非连续模型 |
| `1` | 连续模型 |

说明：即使模型本身不是 continuous，PROPSIM 通常也会按循环方式运行，即结束后从起点继续。

---

### 5.13 关闭当前 emulation

```scpi
DIAG:SIMU:CLOSE
```

推荐流程：

```scpi
DIAG:SIMU:STOP
DIAG:SIMU:CLOSE
*OPC?
SYST:ERR?
DIAG:SIMU:STATE?
```

关闭后：

```text
DIAG:SIMU:STATE?
```

通常应返回：

```text
CLOSED
```

---

## 6. 输入端口 INPut 常见指令

### 6.1 使能/关闭输入

```scpi
INP:EN 1,1
INP:EN 1,0
```

查询：

```scpi
INP:EN? 1
```

返回：

```text
1
```

表示 input 1 已使能。

---

### 6.2 设置平均输入电平

```scpi
INP:LEV:AMP:CH 1,-18.2
```

单位：dBm。

查询：

```scpi
INP:LEV:AMP:CH? 1
```

---

### 6.3 查询输入电平范围

```scpi
INP:LEV:AMP:LIM? 1
```

返回类似：

```text
-23,0
```

表示该输入口可设置的平均输入电平范围。

---

### 6.4 测量平均输入电平和 crest factor

```scpi
INP:LEV:MEAS? 1,3
```

含义：对 input 1 测量 3 秒。

返回类似：

```text
-21.4,4
```

分别表示：

```text
平均输入电平 = -21.4 dBm
crest factor = 4 dB
```

可用测量时长通常为：

```text
0.5, 1, 3, 5, 10 s
```

---

### 6.5 自动设置输入电平和 crest factor

```scpi
INP:LEV:AUTOSET 1,3
```

含义：测量 input 1 的平均输入电平和 crest factor，并自动写入输入参数。

如果要对所有输入同时执行 autoset：

```scpi
INP:LEV:AUTOSET 0,3
```

取消正在进行的 autoset：

```scpi
INP:LEV:AUTOSETCANCEL
```

---

### 6.6 设置/查询 crest factor

设置：

```scpi
INP:CRE:SET 1,4
```

查询：

```scpi
INP:CRE:GET? 1
```

查询范围：

```scpi
INP:CRE:LIM? 1
```

---

### 6.7 查询输入接口类型

```scpi
INP:IF:TYPE? 1
```

可能返回：

```text
RF
```

---

### 6.8 输入测量模式

设置：

```scpi
INP:MEAS:MODE:SET 1,2
```

查询：

```scpi
INP:MEAS:MODE:GET? 1
```

模式含义：

| 数值 | 含义 |
|---|---|
| `0` | DISABLED |
| `1` | BASIC |
| `2` | CONTINUOUS |
| `3` | BURST |

---

### 6.9 冻结/恢复输入测量结果

冻结：

```scpi
INP:MEAS:FREEZE 1,1
```

恢复测量：

```scpi
INP:MEAS:FREEZE 1,0
```

查询：

```scpi
INP:MEAS:FREEZE? 1
```

返回：

| 数值 | 含义 |
|---|---|
| `0` | MEASURE |
| `1` | FREEZE |

---

### 6.10 AILC 自动输入电平控制

AILC = Automatic Input Level Control。

使能：

```scpi
INP:LEV:AUTO:ENA 1,1
```

关闭：

```scpi
INP:LEV:AUTO:ENA 1,0
```

查询：

```scpi
INP:LEV:AUTO:ENA? 1
```

设置模式：

```scpi
INP:LEV:AUTO:MODE 1,2
```

查询模式：

```scpi
INP:LEV:AUTO:MODE? 1
```

模式含义：

| 数值 | 含义 |
|---|---|
| `1` | Prevent cut-off |
| `2` | AGC |
| `3` | AGC keep path loss |

查询 AILC 状态：

```scpi
INP:LEV:AUTO:STAT? 1
```

---

## 7. 输出端口 OUTPut 常见指令

### 7.1 使能/关闭输出

```scpi
OUTP:EN 1,1
OUTP:EN 1,0
```

查询：

```scpi
OUTP:EN? 1
```

---

### 7.2 设置平均输出电平

```scpi
OUTP:LEV:AMP:CH 1,-40
```

单位：dBm。

查询：

```scpi
OUTP:LEV:AMP:CH? 1
```

查询范围：

```scpi
OUTP:LEV:AMP:LIM? 1
```

---

### 7.3 设置输出增益

```scpi
OUTP:GAIN:CH 1,-5
```

单位：dB。

查询：

```scpi
OUTP:GAIN:CH? 1
```

查询范围：

```scpi
OUTP:GAIN:LIM? 1
```

---

### 7.4 设置输出相位

按角度设置：

```scpi
OUTP:PHA:DEG:CH 1,20
```

查询：

```scpi
OUTP:PHA:DEG:CH? 1
```

按 delta 修改：

```scpi
OUTP:PHA:DEG:DELTA:CH 1,10
```

表示在当前相位基础上增加 10°。

查询范围：

```scpi
OUTP:PHA:DEG:LIM? 1
```

---

## 8. 信道模型 CHannel:MODel 常见指令

### 8.1 查询信道模型增益

```scpi
CH:MOD:GAIN:MOD? 1
```

返回单位：dB。

---

### 8.2 查询信道总增益

```scpi
CH:MOD:GAIN:TOT? 1
```

说明：总增益通常包括信道模型增益，以及输入/输出增益或电平设置的综合影响。

---

### 8.3 设置/查询信道使能

关闭 channel 1：

```scpi
CH:MOD:ENABLE 1,0
```

使能 channel 1：

```scpi
CH:MOD:ENABLE 1,1
```

查询：

```scpi
CH:MOD:ENABLE? 1
```

---

### 8.4 查询信道模型文件

查询 `.sim` 控制文件：

```scpi
CH:MOD:FILE:CIR? 1
```

查询源模型文件：

```scpi
CH:MOD:FILE:SOUR? 1
```

---

### 8.5 查询 CIR 数量

```scpi
CH:MOD:CIR? 1
```

返回该通道模型中的 impulse response 数量。

---

### 8.6 查询 sample density

```scpi
CH:MOD:SD? 1
```

---

### 8.7 查询模型时长

```scpi
CH:MOD:TIME? 1
```

返回单位：秒。

---

### 8.8 查询模型是否为相关模型

```scpi
CH:MOD:CORR? 1
```

返回：

| 数值 | 含义 |
|---|---|
| `0` | Channel model is not correlating |
| `1` | Channel model is correlating |

---

### 8.9 设置/查询增益不平衡补偿

设置：

```scpi
CH:MOD:GAIN:ADJ:SET 1,-15
```

查询：

```scpi
CH:MOD:GAIN:ADJ:GET? 1
```

查询范围：

```scpi
CH:MOD:GAIN:ADJ:LIM? 1
```

---

### 8.10 设置/查询相位不平衡补偿

设置：

```scpi
CH:MOD:PHASE:ADJ:SET 1,25
```

查询：

```scpi
CH:MOD:PHASE:ADJ:GET? 1
```

查询范围：

```scpi
CH:MOD:PHASE:ADJ:LIM? 1
```

---

## 9. 参考时钟与物理连接器 ROUTe 指令

### 9.1 设置参考时钟源

使用外部参考：

```scpi
ROUT:PATH:REF EXT
```

使用内部参考：

```scpi
ROUT:PATH:REF INT
```

查询当前参考：

```scpi
ROUT:PATH:REF?
```

返回：

```text
EXT
```

或：

```text
INT
```

---

### 9.2 查询通道对应的物理连接器

```scpi
ROUT:PATH:CONN? 1
```

返回格式通常类似：

```text
sim,in,out,inlo,outlo
```

示例：

```text
1,RF-1,RF-1,1,1
```

用于确认：

- 该 logical channel 属于哪个 emulator；
- 使用哪个 RF input；
- 使用哪个 RF output；
- 使用哪个 RF LO connector。

---

## 10. 校准与 Lab setup 指令

### 10.1 查询可用校准

```scpi
SYST:CALIB:LIST?
```

---

### 10.2 设置当前校准

```scpi
SYST:CALIB:SET LTETestSetup
```

取消校准：

```scpi
SYST:CALIB:SET No calibration
```

---

### 10.3 查询当前校准

```scpi
SYST:CALIB:GET?
```

---

### 10.4 查询校准是否有效

```scpi
SYST:CALIB:VALID?
```

可能返回：

```text
1,1
```

含义：

```text
当前有校准在用，且对所有连接器和频率有效
```

---

### 10.5 查询 lab setup 列表

```scpi
SYST:LAB:LIST?
```

---

### 10.6 设置 lab setup

```scpi
SYST:LAB:SET LTETestSetup
```

取消 lab setup：

```scpi
SYST:LAB:SET No lab setup
```

---

### 10.7 查询当前 lab setup

```scpi
SYST:LAB:GET?
```

---

## 11. Emulation 数据上报 / 测量数据 UDP 指令

### 11.1 设置 UDP 目标

启用 emulation data sending，并设置端口和目标 IP：

```scpi
SYST:MEAS:TAR:SET 1,3800,192.168.1.10
```

关闭数据发送：

```scpi
SYST:MEAS:TAR:SET 0
```

查询：

```scpi
SYST:MEAS:TAR:GET?
```

---

### 11.2 设置数据元素上报

```scpi
SYST:MEAS:ELE:SET 101,1,100
```

含义：

```text
element 101 = input power
1 = enabled
100 = report interval 100 ms
```

查询：

```scpi
SYST:MEAS:ELE:GET? 101
```

常见 element type：

| Element type | 含义 |
|---|---|
| `1` | Emulation event |
| `3` | Emulation time |
| `101` | Input power |
| `201` | Output power calculated from input power |
| `401` | Link Doppler |
| `402` | Link output RSRP |
| `403` | Link AoA angle |
| `404` | Link AoD angle |

---

## 12. 可选：高增益模式、插值模式、bypass

### 12.1 高增益模式

设置：

```scpi
DIAG:SIMU:HIGHGAIN:SET 1
```

关闭：

```scpi
DIAG:SIMU:HIGHGAIN:SET 0
```

查询：

```scpi
DIAG:SIMU:HIGHGAIN:GET?
```

注意：高增益模式会影响链路电平预算，开启前应确认当前测试配置、校准和输入输出电平范围。

---

### 12.2 插值模式

设置系数插值：

```scpi
DIAG:SIMU:INTERP:SET 1
```

关闭插值：

```scpi
DIAG:SIMU:INTERP:SET 0
```

查询：

```scpi
DIAG:SIMU:INTERP:GET?
```

返回：

| 数值 | 含义 |
|---|---|
| `0` | No interpolation |
| `1` | Coeff interpolation |

---

### 12.3 按 link / group 设置 bypass

按 group：

```scpi
GRO:BYPass:STate:CH 5,1
```

查询：

```scpi
GRO:BYPass:STate:CH? 5
```

按 link：

```scpi
LINK:BYPass:STate:CH 5,1
```

查询：

```scpi
LINK:BYPass:STate:CH? 5
```

返回：

| 数值 | 含义 |
|---|---|
| `0` | bypass off，使用信道模型 |
| `1` | Butler bypass enabled |
| `-1` | group 内状态不一致，仅部分查询命令可能返回 |

---

## 13. 常见自动化流程模板

### 13.1 只加载 `.smu` 并开始回放

```scpi
*CLS
CALC:FILT:FILE D:\User Emulations\test_2x2.smu
*OPC?
SYST:ERR?
DIAG:SIMU:STATE?
DIAG:SIMU:GO
DIAG:SIMU:STATE?
```

---

### 13.2 安全停止并关闭 emulation

```scpi
DIAG:SIMU:STOP
DIAG:SIMU:CLOSE
*OPC?
SYST:ERR?
DIAG:SIMU:STATE?
```

期望状态：

```text
CLOSED
```

---

### 13.3 加载后检查拓扑、时长、当前状态

```scpi
*CLS
CALC:FILT:FILE D:\User Emulations\test_2x2.smu
*OPC?
SYST:ERR?

DIAG:SIMU:MOD:INFO?
DIAG:SIMU:MOD:CONT?
CH:MOD:TIME? 1
CH:MOD:CIR? 1
DIAG:SIMU:STATE?
```

---

### 13.4 输入电平 autoset 后启动回放

```scpi
*CLS
CALC:FILT:FILE D:\User Emulations\test_2x2.smu
*OPC?
SYST:ERR?

INP:LEV:AUTOSET 0,3
*OPC?
SYST:ERR?

DIAG:SIMU:GO
DIAG:SIMU:STATE?
```

---

### 13.5 暂停后跳转到 2 秒再继续

```scpi
DIAG:SIMU:STOP
DIAG:SIMU:GOTO 2 s
DIAG:SIMU:MOD:STATE?
DIAG:SIMU:GO
```

---

### 13.6 查询外参考是否正常

```scpi
ROUT:PATH:REF?
SYST:STAT?
SYST:ERR?
```

如果 `SYST:STAT?` 返回 external reference missing 之类告警，需要检查：

- 10 MHz 外参考是否接入；
- 参考源是 `EXT` 还是 `INT`；
- 仪器前面板或后面板参考输入是否正确；
- 外部参考信号幅度是否满足仪器要求。

---

## 14. Python + PyVISA 示例

下面示例假设 FS16 通过 LAN / SOCKET 连接，IP 为 `192.168.1.100`，端口为 `3334`。实际端口和 VISA resource string 需要按你的设备配置修改。

```python
import pyvisa
import time

FS16_IP = "192.168.1.100"
FS16_PORT = 3334
SMU_FILE = r"D:\User Emulations\test_2x2.smu"

rm = pyvisa.ResourceManager()
inst = rm.open_resource(f"TCPIP0::{FS16_IP}::{FS16_PORT}::SOCKET")

inst.read_termination = "\n"
inst.write_termination = "\n"
inst.timeout = 60000

def write(cmd: str):
    print(">>", cmd)
    inst.write(cmd)

def query(cmd: str):
    print(">>", cmd)
    resp = inst.query(cmd).strip()
    print("<<", resp)
    return resp

def check_error():
    err = query("SYST:ERR?")
    if not err.startswith("0,"):
        raise RuntimeError(f"FS16 SCPI error: {err}")

# 1. 确认连接
query("*IDN?")
query("SYST:INFO?")

# 2. 清状态
write("*CLS")
check_error()

# 3. 加载 emulation
write(f"CALC:FILT:FILE {SMU_FILE}")
query("*OPC?")
check_error()

# 4. 查询模型信息
query("DIAG:SIMU:STATE?")
query("DIAG:SIMU:MOD:INFO?")
query("DIAG:SIMU:MOD:CONT?")
query("CH:MOD:TIME? 1")
query("CH:MOD:CIR? 1")

# 5. 可选：输入 autoset
# write("INP:LEV:AUTOSET 0,3")
# query("*OPC?")
# check_error()

# 6. 开始回放
write("DIAG:SIMU:GO")
check_error()
query("DIAG:SIMU:STATE?")

time.sleep(2)

# 7. 查询当前位置
query("DIAG:SIMU:MOD:STATE?")

# 8. 暂停
write("DIAG:SIMU:STOP")
check_error()
query("DIAG:SIMU:STATE?")

# 9. 跳转到 2 秒
write("DIAG:SIMU:GOTO 2 s")
check_error()
query("DIAG:SIMU:MOD:STATE?")

# 10. 停止并回到起点
write("DIAG:SIMU:GOS")
check_error()
query("DIAG:SIMU:MOD:STATE?")

# 11. 关闭 emulation
write("DIAG:SIMU:CLOSE")
query("*OPC?")
check_error()
query("DIAG:SIMU:STATE?")
```

---

## 15. 使用注意事项

### 15.1 `STOP` 与 `GOS` 的区别

```scpi
DIAG:SIMU:STOP
```

是暂停，停在当前回放位置。

```scpi
DIAG:SIMU:GOS
```

是停止并回到起点。

---

### 15.2 `*OPC?` 与 `SYST:ERR?` 要配合使用

推荐：

```scpi
CALC:FILT:FILE D:\xxx.smu
*OPC?
SYST:ERR?
```

因为：

- `*OPC?` 只表示操作完成；
- `SYST:ERR?` 才能确认是否有错误。

---

### 15.3 `GOTO` 要在暂停/停止状态下使用

推荐：

```scpi
DIAG:SIMU:STOP
DIAG:SIMU:GOTO 2 s
DIAG:SIMU:GO
```

---

### 15.4 不要随便执行 `*RST`

```scpi
*RST
```

会执行设备复位，并关闭 emulation。自动化测试中，除非明确需要初始化设备，否则建议优先使用：

```scpi
DIAG:SIMU:STOP
DIAG:SIMU:CLOSE
*CLS
```

---

### 15.5 路径中的反斜杠可能需要转义

普通 SCPI 工具里可能写：

```scpi
CALC:FILT:FILE D:\User Emulations\test_2x2.smu
```

Python 字符串里建议写：

```python
smu_file = r"D:\User Emulations\test_2x2.smu"
```

或：

```python
smu_file = "D:\\User Emulations\\test_2x2.smu"
```

---

## 16. 最常用指令极简版

如果只记一组，建议记下面这些：

```scpi
*IDN?
*CLS
SYST:ERR?
SYST:INFO?
SYST:STAT?

CALC:FILT:FILE D:\User Emulations\test_2x2.smu
*OPC?

DIAG:SIMU:GO
DIAG:SIMU:STOP
DIAG:SIMU:CONT
DIAG:SIMU:GOS
DIAG:SIMU:STATE?
DIAG:SIMU:MOD:STATE?
DIAG:SIMU:CLOSE

INP:LEV:MEAS? 1,3
INP:LEV:AUTOSET 0,3
OUTP:GAIN:CH? 1
CH:MOD:TIME? 1
CH:MOD:CIR? 1
ROUT:PATH:REF?
ROUT:PATH:CONN? 1
```

---

## 17. 资料依据与限制

本文件主要依据公开可查的 Keysight PROPSIM User Reference 相关内容整理，并结合 FS16 / F8820A 作为 PROPSIM FS16 Channel Emulator 的产品定位进行归纳。

本文档不是 Keysight 官方手册的完整替代品。执行涉及 RF 输出、电平、校准、外部参考、自动校准、外部转台/暗室控制的命令前，应结合现场连接、功率预算和仪器授权确认。
