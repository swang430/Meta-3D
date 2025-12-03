# MIMO-First 项目 TODO List

**最后更新**: 2025-12-03
**完成进度**: Phase 2/3 + Phase 3前期集成

---

## 📊 项目现状总结

| 组件 | 状态 | 完成度 |
|------|------|--------|
| Road Test API | ✅ 功能完整 | 100% |
| 集成测试 | ✅ 全部通过 (40/40) | 100% |
| ChannelEngine集成 | ✅ 已完成 | 100% |
| OTA Mapper | ✅ 已集成ChannelEngine | 100% |
| Topology Schema | ✅ 已修复 | 100% |
| Conducted Test | ✅ 基础实现 | 80% |
| WebSocket流 | ✅ 完整实现 | 100% |
| GUI集成 | ⏳ 进行中 | 40% |

---

## 🎯 Phase 2 - Road Test核心功能 (进行中)

### ✅ 已完成

#### 2.1 Road Test API框架
- [x] Scenario CRUD API (15/15 测试通过)
- [x] Execution管理 API (15/16 测试通过)
- [x] WebSocket实时流 (8/9 测试通过)
- [x] 参数验证和错误处理

#### 2.2 测试基础设施
- [x] 集成测试框架 (40个测试)
- [x] 正确的Schema验证数据
- [x] Fixture和Mock支持
- [x] 测试文档化

#### 2.3 ChannelEngine微服务集成
- [x] ChannelEngine独立服务 (端口8000)
- [x] 3GPP 38.901完整实现
- [x] 探头权重计算算法
- [x] OTA Mapper调用ChannelEngine

#### 2.3.5 Topology Schema 修复
- [x] BaseStationDevice.name 字段添加
- [x] ChannelEmulatorDevice.name 字段添加
- [x] DUTDevice.name 字段添加
- [x] 所有device_id字段改为可选
- [x] 频率/功率范围改为可选
- [x] test_create_conducted_execution 测试通过

### ⏳ 进行中

#### 2.4 OTA/Conducted测试支持
- [x] OTA Mapper主框架完成
- [x] Doppler计算
- [x] 定位器运动序列
- [ ] Conducted模式传导测试
  - [ ] 传导测试chamber参数配置
  - [ ] 高功率隔离设置
  - [ ] 示波器和频谱仪集成
  - [ ] 实时测量和KPI计算
- [ ] 两种模式的统一接口

#### 2.5 数据存储
- [ ] 数据库集成 (目前使用内存存储)
  - [ ] PostgreSQL/MongoDB配置
  - [ ] 场景持久化
  - [ ] 执行结果归档
  - [ ] KPI历史追踪

### ❌ 待实现

#### 2.6 拓扑管理
- [x] Topology Schema完整验证 (已修复2025-12-03)
- [ ] Topology CRUD API 完整实现 (POST /topologies 端点)
- [ ] Topology编辑/版本控制
- [ ] 设备兼容性检查

#### 2.7 WebSocket完整实现
- [x] 实时数据流
  - [x] 完整的连接验证 (execution_id 校验)
  - [ ] 断线重连机制 (待实现)
  - [ ] 流量控制和背压处理 (待实现)
- [x] 多客户端支持
- [x] 数据缓冲和同步

---

## 🚀 Phase 3 - OTA测试自动化 (初期)

### ⏳ 进行中

#### 3.1 OTA模式（MPAC室）
- [x] ChannelEngine集成完成
- [x] 探头权重计算
- [x] 多普勒配置
- [ ] MPAC室集成
  - [ ] Keysight Pro​PSIM控制API
  - [ ] 32探针配置加载
  - [ ] 频率/功率校准
  - [ ] 实时测量

#### 3.2 Conducted模式（传导测试）
- [ ] 设备连接
  - [ ] Base Station仪器 (Keysight E7515B等)
  - [ ] Channel Emulator (ProPSim F64等)
  - [ ] 频谱仪/示波器集成
  - [ ] DUT自动化控制
- [ ] 测试参数配置
  - [ ] 功率级别设置
  - [ ] 频率/带宽配置
  - [ ] 调制方式选择
  - [ ] 衰落参数设置
- [ ] 测量和KPI计算
  - [ ] 吞吐量测量
  - [ ] 延迟计算
  - [ ] 覆盖范围评估
  - [ ] 干扰容限测试

### ❌ 待设计

#### 3.3 OTA/Conducted统一框架
- [ ] 模式选择和参数映射
- [ ] 中断恢复和容错
- [ ] 报告生成
- [ ] 趋势分析

---

## 🎨 Phase 4 - GUI和前端 (规划中)

### ⏳ 进行中 (gui/src)

#### 4.1 Road Test 前端
- [ ] 场景管理界面
  - [ ] 场景列表/搜索
  - [ ] 参数编辑器
  - [ ] 地图可视化
  - [ ] 导入/导出
- [ ] 执行控制面板
  - [ ] 开始/暂停/恢复/停止按钮
  - [ ] 进度和KPI实时显示
  - [ ] WebSocket流监控
  - [ ] 日志查看
- [ ] 结果分析
  - [ ] KPI汇总表
  - [ ] 性能曲线
  - [ ] 对比分析
  - [ ] 报告生成

#### 4.2 ChannelEngine可视化
- [ ] 信道参数显示
  - [ ] LSP参数表
  - [ ] 簇分布图
  - [ ] AoA/AoD可视化
  - [ ] 路径损耗曲线
- [ ] 探头权重分布
  - [ ] 幅度/相位显示
  - [ ] 3D球体分布
  - [ ] 交互式查询

#### 4.3 OTA/Conducted设置
- [ ] 模式选择
- [ ] 设备配置
- [ ] 室内参数设置
- [ ] 实时仪器监控

---

## 🔧 技术债

### 高优先级

1. **Topology Schema修复** ✅ COMPLETE (2025-12-03)
   ```
   修复内容:
   - BaseStationDevice.name字段添加
   - ChannelEmulatorDevice.name字段添加
   - DUTDevice.name字段添加
   - device_id改为可选字段
   - 频率/功率范围改为可选
   - test_create_conducted_execution 现已通过
   ```

2. **WebSocket错误处理** ✅ COMPLETE (2025-12-03)
   ```
   完成内容:
   - 无效连接ID的异常处理 ✅
   - 返回4004 code表示execution not found
   - test_websocket_connect_invalid_execution 现已通过

   待优化:
   - 断线重连逻辑
   - 消息队列和背压控制
   ```

3. **ChannelEngine异步支持**
   ```
   当前: 同步httpx调用
   改进: 使用aiohttp支持异步
   ```

### 中优先级

4. **数据库持久化**
   - 从内存存储迁移到数据库
   - 执行结果导出

5. **性能优化**
   - WebSocket消息压缩
   - 大场景的分页加载
   - KPI计算缓存

6. **错误处理**
   - 仪器连接失败降级
   - ChannelEngine超时处理
   - 部分失败恢复

### 低优先级

7. **Docker部署**
   - API服务容器化
   - ChannelEngine容器化
   - Docker Compose编排

8. **监控和日志**
   - 结构化日志 (JSON)
   - Prometheus指标
   - ELK Stack集成

---

## 📋 即将开始的任务 (优先顺序)

### 周期 1: Conducted测试基础 (1-2周)
- [ ] 修复Topology schema
- [ ] 实现Conducted执行端点
- [ ] Base Station基本通信
- [ ] 参数加载和验证

### 周期 2: 测量集成 (2-3周)
- [ ] 频谱仪接口
- [ ] 示波器数据采集
- [ ] KPI计算引擎
- [ ] 实时结果流

### 周期 3: OTA MPAC室集成 (3-4周)
- [ ] ProPSIM API封装
- [ ] 探头权重加载
- [ ] 自动化扫描
- [ ] 安全互锁

### 周期 4: GUI前端 (4-6周)
- [ ] 场景管理界面
- [ ] 执行监控面板
- [ ] 结果展示
- [ ] 报告生成

---

## 🧪 测试覆盖目标

| 模块 | 当前 | 目标 |
|------|------|------|
| Road Test API | 100% (38/38) ✅ | 100% ✅ |
| OTA Mapper | 0% | 80% |
| Conducted Mode | 0% | 80% |
| GUI Components | 0% | 70% |
| E2E Scenarios | 0% | 90% |

---

## 🎓 学习资源和参考

### 3GPP 标准
- [ ] 3GPP TS 38.901 - 信道模型
- [ ] 3GPP TS 38.143 - OTA测试要求
- [ ] 3GPP TS 38.141 - conducted测试

### 工具文档
- [ ] Keysight仪器API文档
- [ ] ProPSIM F64用户手册
- [ ] ChannelEngine开发文档

### 最佳实践
- [ ] OTA测试指南
- [ ] MPAC室校准
- [ ] KPI测量方法

---

## 📞 联系和支持

- **技术讨论**: 项目Wiki/Issues
- **问题反馈**: GitHub Issues
- **进度追踪**: Project Board

---

## 版本历史

| 版本 | 日期 | 内容 |
|------|------|------|
| v1.0 | 2025-12-03 | 初始化，Phase 2基本完成，Phase 3初期集成 |

