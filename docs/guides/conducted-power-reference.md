# 传导工程的发射参考

物理传播路径、两端天线和仪器之间的接入线分别登记。生成器把簇的复系数原样写入 ASC，比例为 1。工程中的 carrier-power.json 按源帧、发射口、接收口保存载频处的系数相干和的模平方。只有系数确为两参考面间的复电压传递比（相同匹配阻抗，或等价功率波归一化）时，这一数值才有绝对功率增益的意义。

如需单发射口在载频连续波激励下的接收功率预测，将 conducted-power-reference.json 与 R0B0S0D.mpdb 放在同一 ZIP 根目录。示意结构如下，摘要、功率、频点及参考面必须换成本批资料。tx_power_dbm 按已知发射端口登记连续波功率；只有带内平坦功率谱时可登记 tx_psd_dbm_per_hz 与 bandwidth_hz，保留谱密度供宽带计算。links 按“发射口/接收口”声明依据，缺少依据的链路保留未知。

```json
{"schema":"conducted-power-reference/1","source_sha256":"下行 MPDB 的 SHA-256","carrier_hz":3500000000,"bandwidth_hz":20000000,"tx_power_dbm":{"0":0},"links":{"0/0":{"coefficient_unit":"power_wave_ratio","relative_ray_phase":"preserved","carrier_phase_convention":"included_in_coefficient","tx_plane":"基站天线馈口","rx_plane":"车载天线馈口","phase_origin":"载频复系数已含传播相位","delay_origin":"相对发射时刻","included_losses":"传播与声明的天线响应","antenna_response":"both"}}}
```

若使用 voltage_transfer_ratio，须分别给出 tx_impedance_ohm 与 rx_impedance_ohm，按两个匹配实阻抗之比换算功率。

天线字段接受 both、tx、rx、neither、unknown。缺少参考文件时仍可生成相对工程。已给参考的预测按发射 dBm 加上模平方的 10 倍常用对数计算；完全相消时模平方为零，dBm 留空。宽带平均和同时发射的端口合成需要频谱与互相关依据。此表是模型预测，排除在正式实测判定之外。
