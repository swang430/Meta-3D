/**
 * 系统校准方法说明；执行只回到同一当前实验室的原射频拓扑。
 */
import { Alert, Button, Modal, Stack, Text } from '@mantine/core';

interface CalibrationWizardProps {
  opened: boolean;
  onClose: () => void;
  onOpenPathCalibration: () => void;
  pathUnavailableReason: string | null;
}

export function CalibrationWizard({
  opened, onClose, onOpenPathCalibration, pathUnavailableReason,
}: CalibrationWizardProps) {
  return (
    <Modal opened={opened} onClose={onClose} title="系统校准方法说明" size="lg">
      <Stack gap="md">
        <Text>路径损耗/增益、上下行链、多频点：在当前实验室拓扑核对接线并选择已有通路；只开放该工作台已支持的范围</Text>
        <Text>TRP/TIS：本入口没有可验证真实测量链</Text>
        <Text>重复性：旧测量入口未开放；执行指标对齐不等于 TRP/TIS 重复性验证</Text>
        <Text>静区/相位/互耦：需要独立方法和已验证现场条件，路径损耗不能替代</Text>
        <Text>相对基线：仅保留原记录查询，不执行旧模拟 quick/drift</Text>
        <Text>参考件：参考天线/接收线缆来源在原拓扑填写；证书有效性、适用频率和不确定度仍需独立核验</Text>
        {pathUnavailableReason && <Alert color="yellow">{pathUnavailableReason}</Alert>}
        <Button disabled={pathUnavailableReason !== null} onClick={onOpenPathCalibration}>
          进入当前实验室射频拓扑
        </Button>
      </Stack>
    </Modal>
  );
}
