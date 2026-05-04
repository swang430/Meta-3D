import { useState } from 'react';
import {
  Modal,
  TextInput,
  Textarea,
  Button,
  Group,
  Select,
  Stack,
  TagsInput,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { createTestCase, type CreateTestCaseRequest } from '../../../../api/testPlanService';
import type { TestStep } from '../../types';

interface SaveAsTestCaseModalProps {
  opened: boolean;
  onClose: () => void;
  step: TestStep;
}

export function SaveAsTestCaseModal({ opened, onClose, step }: SaveAsTestCaseModalProps) {
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState(`${step.title} (自定义)`);
  const [description, setDescription] = useState(step.description || '');
  const [category, setCategory] = useState<string>('自定义');
  const [tags, setTags] = useState<string[]>(step.tags || []);

  const handleSave = async () => {
    if (!name.trim()) {
      notifications.show({ title: '错误', message: '请输入测试用例名称', color: 'red' });
      return;
    }

    setLoading(true);
    try {
      // Map step properties to TestCase properties
      const request: CreateTestCaseRequest = {
        name: name.trim(),
        description: description.trim(),
        test_type: (step as any).test_type || 'Custom', // Fallback
        configuration: step.parameters || {},
        is_template: true,
        template_category: category,
        created_by: '当前用户',
        tags,
      };

      await createTestCase(request);

      notifications.show({
        title: '保存成功',
        message: `测试用例模板 "${name}" 已保存至库中`,
        color: 'green',
      });
      onClose();
    } catch (error) {
      console.error(error);
      notifications.show({
        title: '保存失败',
        message: '无法将当前步骤保存为测试用例',
        color: 'red',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal opened={opened} onClose={onClose} title="另存为测试用例模板" size="md">
      <Stack gap="md">
        <TextInput
          label="模板名称"
          placeholder="例如：MIMO吞吐量 - ID.4专属"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        
        <Select
          label="模板分类"
          data={['TRP 全向辐射功率', 'TIS 全向灵敏度', 'MIMO OTA 吞吐量', '信道模型验证', '波束管理', '虚拟路测', '切换测试', '自定义']}
          value={category}
          onChange={(val) => setCategory(val || '自定义')}
          required
        />

        <Textarea
          label="描述"
          placeholder="该模板的用途及特殊配置说明"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          minRows={3}
        />

        <TagsInput
          label="标签"
          placeholder="添加标签（回车确认）"
          value={tags}
          onChange={setTags}
        />

        <Group justify="right" mt="md">
          <Button variant="default" onClick={onClose} disabled={loading}>
            取消
          </Button>
          <Button onClick={handleSave} loading={loading}>
            保存为模板
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
