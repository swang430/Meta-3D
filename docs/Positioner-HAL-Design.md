# Positioner HAL Design
## 文档信息
- **版本**: 1.0.0, **日期**: 2025-11-16, **优先级**: P1

## 1. 概述
转台HAL控制DUT旋转，支持方位角和俯仰角控制，用于3D扫描测试。

## 2. 支持设备
- Orbit FR Turntable
- ETS-Lindgren 2090 Positioner

## 3. 接口
```typescript
interface IPositioner {
  rotate(azimuth_deg: number, elevation_deg: number): Promise<void>
  getPosition(): Promise<{azimuth: number, elevation: number}>
  home(): Promise<void>  // 回到原点
}
```

## 4. 运动控制
- 速度控制: 1-10 °/s
- 精度: ±0.1°
- 加速度控制防止DUT抖动
