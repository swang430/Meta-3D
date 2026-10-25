import { Alert, Stack } from '@mantine/core';
import { BaselineCalibrationCard } from './BaselineCalibrationCard';

export function CalibrationDashboard() {
  return (
    <Stack gap="md" data-testid="system-calibration-overview">
      <Alert color="gray" title="系统校准状态未知">
        当前首页未接入可验证的系统证书、TRP/TIS 或重复性证据，不展示精度、合格率或趋势。
      </Alert>
      <Alert color="gray" title="方法边界">
        基线状态不代表系统证书或 TRP/TIS 验证
      </Alert>
      <BaselineCalibrationCard />
    </Stack>
  );
}

