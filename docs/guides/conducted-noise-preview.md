# 按系统仿真预览传导干扰和噪声

在虚拟路测的传导准备窗口展开“按系统仿真预览干扰和噪声”，选择 JSON。统计窗口列表的每一项包含以下字段。

| 字段 | 填写内容 |
|---|---|
| scope | frame 源帧号、receiver 接收口、plane 参考面、bandwidth_hz 带宽、start_s 起点、duration_s 统计时长。receiver_connector 指接收插口；receiver_combined 指接收机内部合并后的量。 |
| signal、existing | 各自包含同一 scope、绝对功率 dbm、不重复的 sources 来源清单。kind 分别填 signal 和 interference_and_noise。已有干扰和接收机等效噪声应只计入一次。 |
| target_sinr_db | 同一统计窗口的信号与干扰加噪声功率比。 |
| additional_source、correlation_real、injection_plane | 新增源名称、与现有扰动的归一化互相关实部、注入参考面。已确定互不相关时填写 0。 |
| method | equivalent_noise 选用等效加性噪声；waveform_covariance 需要另有波形及多端口相关矩阵依据。 |

例如，插口信号 −70 dBm，目标 10 dB，允许的干扰和噪声总量是 −80 dBm。已存在 −83 dBm 且新增源与它不相关，则应再加入约 −83.02 dBm。各端口总量和相关性分开给定。单一功率比无法拆出干扰与噪声成分。

生成样本时，上传包含 windows、sample_rate_hz、sample_count、seed、correlation_real、correlation_imag、interference_i 和 interference_q 的对象。窗口按实际接收口排序；相关矩阵为噪声的归一化复协方差。干扰波形单位为毫瓦平方根，需与生成的噪声互不相关。下载文件给出复基带实部和虚部、各口要求和本次有限长度样本的实际功率。离线生成不会启用射频。真机的注入点、实际可用带宽、功率范围、跨口相关性与插口实测仍须现场验收。
