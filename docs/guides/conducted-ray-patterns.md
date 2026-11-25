# 在传导工程中使用天线方向图

未指定替换时，生成器直接使用 MPDB 的 H。若数据包含标准导出的两端 Jones 分量和 H 极化组合声明，清单注明源系数已包含双端。天线版本仍需要独立资料核对。

按端口替换时，在 ZIP 根目录加入 ray-antenna-patterns.json。登记 schema 为 ray-antenna-patterns/1、下行文件 source_sha256、carrier_hz，以及 basis 为 global_theta_phi_rx_effective_length_transpose。tx 和 rx 对象以实际端口号为键；只提供需要替换的端口。每个方向图包含如下字段：

- version 为本端口实测或仿真方向图的版本标识。carrier_hz 必须与源载频相等。
- local_to_global 为安装姿态的三维右手旋转矩阵。azimuth_deg 和 zenith_deg 是局部坐标中的递增角度数组，单位为度。azimuth_coverage 为 periodic 或 sector，分别表示完整周期或有限扇区。超出扇区或天顶角范围会指出缺项。
- gain_convention 为 absolute_field。field 的下标依次为天顶角、方位角、两项复电场分量、实部与虚部。发射使用发射场，接收使用已转换为接收有效长度约定的复响应。增益含在场幅中，只计一次。仅有标量增益时，无法恢复极化和相位，不能把它直接当作复场方向图。
- 导入以源 H 核对传播矩阵、两端极化和路径幅相；替换时从传播数据重算，不把新增益叠在原 H 上。缺少相应分量时保留源 H 并标明未核验。替换后若出现旧成员表没有的射线，默认停止；允许在文件中明确指定 regroup_uncovered_rays 为 delay_bins，对这些变化按本帧统一时延区间重新分组。外传的成员表优先，须先移除才可重分组。
- 核对两端方向图的坐标、版本与幅相约定后再用于现场。文件摘要和发生替换的端口随工程保存，模型输出不能进入正式测量判定。
