# Keysight PROPSIM FS16 回放控制 SCPI 指令整理

> 适用对象：Keysight PROPSIM FS16 / F8820A 信道模拟器的 emulation / `.smu` 文件加载与回放控制。  
> 说明：不同固件版本、连接方式和软件选件可能导致少量命令差异，实际使用时应以对应设备的 Programming Guide / User Reference 为准。

---

## 1. 基本概念

在 FS16 中，通常先通过软件生成或加载一个 emulation 文件，例如 `.smu` 文件，然后通过 SCPI 指令完成：

1. 加载 emulation 文件；
2. 启动回放；
3. 暂停回放；
4. 继续回放；
5. 停止并回到起点；
6. 查询当前运行状态；
7. 查询当前回放位置；
8. 跳转到指定时间点或 CIR；
9. 关闭当前 emulation。

---

## 2. 常用指令速查表

| 功能 | SCPI 完整指令 | 常用短写 | 说明 |
|---|---|---|---|
| 清除状态/错误队列 | `*CLS` | `*CLS` | 建议每次自动化流程开始前执行 |
| 等待操作完成 | `*OPC?` | `*OPC?` | 返回 `1` 表示前序操作完成 |
| 查询错误队列 | `SYSTem:ERRor?` | `SYST:ERR?` | 用于确认是否有 SCPI 执行错误 |
| 加载 emulation 文件 | `CALCulate:FILTer:FILE <filename>` | `CALC:FILT:FILE <filename>` | 打开指定 `.smu` 文件 |
| 开始回放 | `DIAGnostic:SIMUlation:GO` | `DIAG:SIMU:GO` | 对应界面中的 Run / Play emulation |
| 暂停回放 | `DIAGnostic:SIMUlation:STOP` | `DIAG:SIMU:STOP` | 暂停在当前位置，不回到起点 |
| 继续回放 | `DIAGnostic:SIMUlation:CONTinue` | `DIAG:SIMU:CONT` | 从暂停位置继续运行 |
| 停止并回到起点 | `DIAGnostic:SIMUlation:GOStart` | `DIAG:SIMU:GOS` | Stop + rewind to start |
| 查询回放状态 | `DIAGnostic:SIMUlation:STATE?` | `DIAG:SIMU:STATE?` | 查询当前 emulation 状态 |
| 查询当前回放位置 | `DIAGnostic:SIMUlation:MODel:STATE?` | `DIAG:SIMU:MOD:STATE?` | 查询当前 CIR 编号和 emulation time |
| 跳转到指定时间 | `DIAGnostic:SIMUlation:GOTO <time> s` | `DIAG:SIMU:GOTO <time> s` | 例如跳到 2 秒 |
| 跳转到指定 CIR | `DIAGnostic:SIMUlation:GOTO <channel>,<cir>` | `DIAG:SIMU:GOTO <channel>,<cir>` | 例如跳到 channel 1 的第 99 个 CIR |
| 查询模型时长 | `CHannel:MODel:TIME? <channel>` | `CHAN:MOD:TIME? <channel>` | 返回指定通道的模型总时长，单位通常为秒 |
| 关闭 emulation | `DIAGnostic:SIMUlation:CLOSE` | `DIAG:SIMU:CLOSE` | 关闭当前打开的 emulation |

---

## 3. 加载 `.smu` 文件

### 3.1 指令格式

```scpi
CALCulate:FILTer:FILE <filename>
```

短写：

```scpi
CALC:FILT:FILE <filename>
```

### 3.2 示例

```scpi
CALC:FILT:FILE D:\User Emulations\test_2x2.smu
```

如果通信工具对反斜杠转义有要求，可以写成：

```scpi
CALC:FILT:FILE D:\\User Emulations\\test_2x2.smu
```

建议加载后执行：

```scpi
*OPC?
SYST:ERR?
```

---

## 4. 启动回放

### 4.1 指令格式

```scpi
DIAGnostic:SIMUlation:GO
```

短写：

```scpi
DIAG:SIMU:GO
```

### 4.2 示例

```scpi
DIAG:SIMU:GO
```

该指令相当于在 FS16 软件界面中点击 **Run / Play emulation**。

---

## 5. 暂停回放

### 5.1 指令格式

```scpi
DIAGnostic:SIMUlation:STOP
```

短写：

```scpi
DIAG:SIMU:STOP
```

### 5.2 说明

`STOP` 是暂停，不是停止并回到起点。执行后 emulation 会停在当前回放位置。

---

## 6. 继续回放

### 6.1 指令格式

```scpi
DIAGnostic:SIMUlation:CONTinue
```

短写：

```scpi
DIAG:SIMU:CONT
```

### 6.2 示例

```scpi
DIAG:SIMU:CONT
```

用于从暂停位置继续回放。

---

## 7. 停止并回到起点

### 7.1 指令格式

```scpi
DIAGnostic:SIMUlation:GOStart
```

短写：

```scpi
DIAG:SIMU:GOS
```

### 7.2 说明

该指令可以理解为：

```text
Stop + Rewind to Start
```

也就是停止回放，并把回放位置复位到 emulation 起点。

---

## 8. 查询当前运行状态

### 8.1 指令格式

```scpi
DIAGnostic:SIMUlation:STATE?
```

短写：

```scpi
DIAG:SIMU:STATE?
```

### 8.2 可能返回值

| 返回值 | 含义 |
|---|---|
| `CLOSED` | 当前没有打开 emulation |
| `OPENING` | 正在打开 emulation |
| `STOPPED` | emulation 已停止或暂停 |
| `RUNNING` | emulation 正在运行 |
| `EDITING` | emulation 处于编辑状态 |
| `CLOSING` | 正在关闭 emulation |

---

## 9. 查询当前回放位置

### 9.1 指令格式

```scpi
DIAGnostic:SIMUlation:MODel:STATE?
```

短写：

```scpi
DIAG:SIMU:MOD:STATE?
```

### 9.2 说明

该指令用于查询当前 emulation model 的运行位置，一般会返回各通道当前 CIR 编号以及当前 emulation time。

---

## 10. 跳转到指定位置

### 10.1 跳转到指定时间点

例如跳转到第 2 秒：

```scpi
DIAG:SIMU:GOTO 2 s
```

### 10.2 跳转到指定通道的指定 CIR

例如跳转到 channel 1 的第 99 个 CIR：

```scpi
DIAG:SIMU:GOTO 1,99
```

### 10.3 注意事项

执行 `GOTO` 前，建议先暂停或停止 emulation：

```scpi
DIAG:SIMU:STOP
DIAG:SIMU:GOTO 2 s
```

---

## 11. 查询模型总时长

### 11.1 指令格式

```scpi
CHannel:MODel:TIME? <channel>
```

短写：

```scpi
CHAN:MOD:TIME? <channel>
```

### 11.2 示例

查询 channel 1 的模型时长：

```scpi
CHAN:MOD:TIME? 1
```

返回值单位通常为秒。

---

## 12. 关闭当前 emulation

### 12.1 指令格式

```scpi
DIAGnostic:SIMUlation:CLOSE
```

短写：

```scpi
DIAG:SIMU:CLOSE
```

### 12.2 示例

```scpi
DIAG:SIMU:CLOSE
```

---

## 13. 推荐的完整自动化流程

下面是一套典型的 `.smu` 文件加载与回放流程。

```scpi
*CLS
CALC:FILT:FILE D:\User Emulations\test_2x2.smu
*OPC?
SYST:ERR?
DIAG:SIMU:STATE?
DIAG:SIMU:GO
*OPC?
SYST:ERR?
DIAG:SIMU:STATE?
DIAG:SIMU:MOD:STATE?
```

如果需要暂停：

```scpi
DIAG:SIMU:STOP
DIAG:SIMU:STATE?
DIAG:SIMU:MOD:STATE?
```

如果需要继续：

```scpi
DIAG:SIMU:CONT
DIAG:SIMU:STATE?
```

如果需要停止并回到起点：

```scpi
DIAG:SIMU:GOS
DIAG:SIMU:MOD:STATE?
```

如果需要关闭：

```scpi
DIAG:SIMU:CLOSE
```

---

## 14. Python + PyVISA 示例

下面示例假设 FS16 通过 LAN / SOCKET 方式连接，IP 地址为 `192.168.1.100`，端口为 `3334`。实际资源字符串需要按你的设备连接方式修改。

```python
import pyvisa

rm = pyvisa.ResourceManager()

inst = rm.open_resource("TCPIP0::192.168.1.100::3334::SOCKET")
inst.read_termination = "\n"
inst.write_termination = "\n"
inst.timeout = 60000

smu_file = r"D:\User Emulations\test_2x2.smu"

# 清除状态
inst.write("*CLS")

# 加载 emulation 文件
inst.write(f"CALC:FILT:FILE {smu_file}")
print("OPC:", inst.query("*OPC?"))
print("ERR:", inst.query("SYST:ERR?"))

# 查询状态
print("STATE before run:", inst.query("DIAG:SIMU:STATE?"))

# 启动回放
inst.write("DIAG:SIMU:GO")
print("OPC:", inst.query("*OPC?"))
print("ERR:", inst.query("SYST:ERR?"))

# 查询状态和回放位置
print("STATE after run:", inst.query("DIAG:SIMU:STATE?"))
print("MODEL STATE:", inst.query("DIAG:SIMU:MOD:STATE?"))

# 暂停
inst.write("DIAG:SIMU:STOP")
print("STATE after stop:", inst.query("DIAG:SIMU:STATE?"))

# 继续
inst.write("DIAG:SIMU:CONT")
print("STATE after continue:", inst.query("DIAG:SIMU:STATE?"))

# 停止并回到起点
inst.write("DIAG:SIMU:GOS")
print("MODEL STATE after rewind:", inst.query("DIAG:SIMU:MOD:STATE?"))

# 关闭 emulation
inst.write("DIAG:SIMU:CLOSE")
```

---

## 15. 使用注意事项

1. **`STOP` 和 `GOS` 不一样**  
   - `DIAG:SIMU:STOP`：暂停在当前位置；
   - `DIAG:SIMU:GOS`：停止并回到起点。

2. **加载文件后建议执行 `*OPC?`**  
   加载 `.smu` 文件可能需要时间，建议用 `*OPC?` 等待操作完成。

3. **每个关键步骤后建议查询 `SYST:ERR?`**  
   `*OPC?` 只表示操作完成，不代表操作没有错误。  
   推荐关键步骤后执行：

   ```scpi
   SYST:ERR?
   ```

4. **路径写法要注意转义**  
   不同控制环境对反斜杠处理不同。  
   例如 Python 原始字符串可以写：

   ```python
   smu_file = r"D:\User Emulations\test_2x2.smu"
   ```

5. **`GOTO` 建议在暂停或停止状态下执行**  
   例如：

   ```scpi
   DIAG:SIMU:STOP
   DIAG:SIMU:GOTO 2 s
   ```

6. **不同固件版本可能存在差异**  
   如果指令返回错误，需要结合：

   ```scpi
   SYST:ERR?
   ```

   查看具体错误原因。

---

## 16. 最小可用指令集

如果只想完成“加载文件并开始回放”，最小流程可以写成：

```scpi
*CLS
CALC:FILT:FILE D:\User Emulations\test_2x2.smu
*OPC?
DIAG:SIMU:GO
DIAG:SIMU:STATE?
```

如果只想控制播放/暂停/复位，记住下面几条即可：

```scpi
DIAG:SIMU:GO       -- 开始回放
DIAG:SIMU:STOP     -- 暂停
DIAG:SIMU:CONT     -- 继续
DIAG:SIMU:GOS      -- 停止并回到起点
DIAG:SIMU:STATE?   -- 查询状态
```
