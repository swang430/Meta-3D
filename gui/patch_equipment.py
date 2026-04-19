import re

with open('src/App.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

# We need to inject useState into EquipmentManager
equipment_manager_start = content.find('function EquipmentManager() {')
if equipment_manager_start == -1:
    print("Cannot find EquipmentManager")
    exit(1)

# Add editingCategoryKey state
state_injection = """  const [drafts, setDrafts] = useState<Record<string, EquipmentDraft>>({})
  const [editingCategoryKey, setEditingCategoryKey] = useState<string | null>(null)"""
content = re.sub(r'const \[drafts, setDrafts\] = useState<Record<string, EquipmentDraft>>\({}\)', state_injection, content, 1)

# Now rewrite the return block of EquipmentManager
# It starts at: return (\n    <Stack gap="xl">\n      {/* HAL 模式切换器 */}
# It ends right before `function ProbeManager`

return_start = content.find('  return (\n    <Stack gap="xl">\n      {/* HAL 模式切换器 */}')
probe_manager_start = content.find('type ProbeManagerProps = {')

if return_start == -1 or probe_manager_start == -1:
    print("Cannot find boundaries")
    exit(1)

old_return = content[return_start:probe_manager_start]

new_return = """  return (
    <Stack gap="xl">
      <Drawer
        opened={!!editingCategoryKey}
        onClose={() => setEditingCategoryKey(null)}
        title={<Title order={4}>参数配置</Title>}
        position="right"
        size="lg"
        padding="xl"
      >
        {(() => {
          const category = categories.find((c) => c.key === editingCategoryKey)
          if (!category) return null
          const draft = drafts[category.key]
          if (!draft) return null
          const drawerSelectedModel = category.models.find((model) => model.id === draft.modelId) ?? null

          return (
            <Stack gap="xl">
              <Group gap="sm" align="center">
                <Title order={3}>{category.label}</Title>
              </Group>

              <Stack gap="md">
                <Select
                  label="选择型号"
                  placeholder="请选择仪器型号"
                  data={modelSelectData[category.key] ?? []}
                  value={draft.modelId}
                  onChange={(value) => handleModelChange(category.key, value ?? '')}
                  disabled={instrumentMutation.isPending}
                />
                <Card withBorder padding="md" radius="md" shadow="xs" bg="gray.0">
                  {drawerSelectedModel ? (
                    <Stack gap="sm">
                      <Group justify="space-between" align="flex-start">
                        <Stack gap={2}>
                          <Text fw={600}>
                            {drawerSelectedModel.vendor} {drawerSelectedModel.model}
                          </Text>
                          <Text size="sm" c="gray.6">
                            {drawerSelectedModel.summary}
                          </Text>
                        </Stack>
                        <Badge color={instrumentStatusColor[drawerSelectedModel.status]} variant="light">
                          {drawerSelectedModel.status.toUpperCase()}
                        </Badge>
                      </Group>
                      <Group gap="sm" c="gray.6" wrap="wrap">
                        {drawerSelectedModel.channels ? <Text size="xs">通道: {drawerSelectedModel.channels}</Text> : null}
                        {drawerSelectedModel.bandwidth ? <Text size="xs">带宽: {drawerSelectedModel.bandwidth}</Text> : null}
                        <Text size="xs">接口: {drawerSelectedModel.interfaces.join(' / ')}</Text>
                      </Group>
                      <Group gap="xs" wrap="wrap">
                        {drawerSelectedModel.capabilities.map((capability) => (
                          <Badge key={capability} variant="outline" color="brand">
                            {capability}
                          </Badge>
                        ))}
                      </Group>
                    </Stack>
                  ) : (
                    <Stack align="center" py="xl" c="gray.6">
                      <Text size="sm">请选择型号以查看能力说明</Text>
                    </Stack>
                  )}
                </Card>
              </Stack>

              <Stack gap="md">
                <TextInput
                  label="控制端点"
                  placeholder="例: 192.168.100.21:5025"
                  value={draft.endpoint}
                  onChange={handleFieldChange(category.key, 'endpoint')}
                />
                <TextInput
                  label="控制方式"
                  placeholder="LAN/SCPI"
                  value={draft.controller}
                  onChange={handleFieldChange(category.key, 'controller')}
                />
                <Textarea
                  label="备注"
                  placeholder="记录登录凭证、联机说明或版本信息"
                  minRows={3}
                  value={draft.notes}
                  onChange={handleFieldChange(category.key, 'notes')}
                />
                <Group justify="flex-end" mt="md">
                  <Button
                    variant="outline"
                    color="teal"
                    onClick={async () => {
                      showFeedback(category.key, 'success', '正在测试连接...')
                      try {
                        const resp = await client.post(`/instruments/${category.key}/test-connection`)
                        const result = resp.data as { success: boolean; message: string; idn?: string; latency_ms?: number }
                        if (result.success) {
                          const extra = result.idn ? ` | IDN: ${result.idn}` : ''
                          const latency = result.latency_ms ? ` (${result.latency_ms}ms)` : ''
                          showFeedback(category.key, 'success', `✅ ${result.message}${latency}${extra}`)
                        } else {
                          showFeedback(category.key, 'error', `❌ ${result.message}`)
                        }
                      } catch (err: any) {
                        showFeedback(category.key, 'error', `测试失败: ${err.message}`)
                      }
                    }}
                  >
                    测试连接
                  </Button>
                  <Button
                    color="brand"
                    onClick={() => {
                       handleSaveConnection(category.key);
                       setEditingCategoryKey(null);
                    }}
                    loading={instrumentMutation.isPending}
                  >
                    保存配置
                  </Button>
                </Group>
                {feedback[category.key] ? (
                  <Alert
                    color={feedback[category.key].type === 'error' ? 'red' : 'green'}
                    variant="light"
                    radius="md"
                  >
                    {feedback[category.key].message}
                  </Alert>
                ) : null}
              </Stack>
            </Stack>
          )
        })()}
      </Drawer>

      {/* HAL 模式切换器 */}
      <Card withBorder radius="md" padding="lg">
        <Group justify="space-between" align="center">
          <Stack gap={4}>
            <Group gap="sm" align="center">
              <Title order={4}>驱动模式</Title>
              <Badge
                color={halStatus?.mode === 'real' ? 'teal' : 'blue'}
                variant="light"
                size="lg"
              >
                {halStatus?.mode === 'real' ? '🔌 硬件连接' : '🧪 仿真模拟'}
              </Badge>
            </Group>
            <Text size="xs" c="dimmed">
              Mock 模式使用软件仿真驱动（开发调试）；Real 模式从数据库读取配置连接真实硬件。
              已激活 {halStatus?.driver_count ?? 0} 个驱动
              {halStatus?.active_drivers?.length ? `（${halStatus.active_drivers.join(', ')}）` : ''}
            </Text>
          </Stack>
          <Group gap="md" align="center">
            <SegmentedControl
              value={halStatus?.mode ?? 'mock'}
              onChange={handleHALSwitch}
              disabled={halSwitching}
              data={[
                { label: 'Mock 仿真', value: 'mock' },
                { label: 'Real 硬件', value: 'real' },
              ]}
            />
          </Group>
        </Group>
        {feedback['__hal__'] ? (
          <Alert
            color={feedback['__hal__'].type === 'error' ? 'red' : 'green'}
            variant="light"
            radius="md"
            mt="sm"
          >
            {feedback['__hal__'].message}
          </Alert>
        ) : null}
      </Card>

      {isLoading && categories.length === 0 ? (
        <Card withBorder radius="md" padding="xl">
          <Text size="sm" c="gray.6">
            正在加载仪器配置...
          </Text>
        </Card>
      ) : null}
      {!isLoading && categories.length === 0 ? (
        <Card withBorder radius="md" padding="xl">
          <Text size="sm" c="gray.6">
            暂无仪器信息，请在后端添加型号。
          </Text>
        </Card>
      ) : null}
      {categories.map((category) => {
        const selectedModelInfo = category.models.find((model) => model.id === category.selectedModelId) ?? null

        return (
          <Card key={category.key} withBorder radius="md" padding="lg" style={{
            opacity: category.isActive === false ? 0.5 : 1,
            transition: 'opacity 0.3s ease',
            borderLeft: `4px solid ${category.isActive === false ? '#dee2e6' : '#2c77f5'}`
          }}>
            <Stack gap="md">
              <Group justify="space-between" align="center">
                <Group gap="sm" align="center">
                  <Title order={4}>{category.label}</Title>
                  {(category as any).usagePhase?.map((phase: string) => (
                    <Badge
                      key={phase}
                      size="sm"
                      variant="dot"
                      color={phase === 'calibration' ? 'orange' : 'teal'}
                    >
                      {phase === 'calibration' ? '校准' : '测试'}
                    </Badge>
                  ))}
                  <Badge variant="light" color={selectedModelInfo ? "green" : "red"}>
                    {selectedModelInfo ? "已实装" : "未实装"}
                  </Badge>
                </Group>
                
                <Group gap="md">
                  <Switch
                    checked={category.isActive !== false}
                    color="teal"
                    onChange={async (e) => {
                      const newActive = e.currentTarget.checked
                      try {
                        await client.patch(`/instruments/${category.key}/active`, { isActive: newActive })
                        queryClient.invalidateQueries({ queryKey: ['instruments', 'catalog'] })
                        showFeedback(category.key, 'success', `✅ 已${newActive ? '启用' : '停用'} ${category.label}`)
                      } catch (err: any) {
                        showFeedback(category.key, 'error', `操作失败: ${err.message}`)
                      }
                    }}
                  />
                  <Button variant="light" size="sm" onClick={() => setEditingCategoryKey(category.key)}>
                    替换 / 配置实装
                  </Button>
                </Group>
              </Group>

              {/* View Display Area */}
              <Card withBorder radius="sm" padding="sm" bg="gray.0">
                {selectedModelInfo ? (
                  <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
                    <Stack gap={4}>
                      <Group justify="space-between">
                         <Text size="sm" c="dimmed">型号</Text>
                         <Badge color={instrumentStatusColor[selectedModelInfo.status]} variant="dot" size="xs">
                            {selectedModelInfo.status.toUpperCase()}
                         </Badge>
                      </Group>
                      <Text fw={600}>{selectedModelInfo.vendor} {selectedModelInfo.model}</Text>
                      <Text size="xs" c="gray.6">{selectedModelInfo.summary}</Text>
                    </Stack>
                    
                    <Stack gap={4}>
                      <Text size="sm" c="dimmed">互联</Text>
                      <Group gap="xs">
                        <Badge size="xs" variant="outline">{category.connection?.controller || 'Unknown'}</Badge>
                        <Text fw={500} size="sm">{category.connection?.endpoint || '未配置IP'}</Text>
                      </Group>
                      <Text size="xs" c="gray.6" truncate>{category.connection?.notes || '无备注'}</Text>
                    </Stack>
                  </SimpleGrid>
                ) : (
                  <Group justify="center" py="md">
                    <Text size="sm" c="dimmed">该槽位当前为空。请点击“配置实装”进行连接。</Text>
                  </Group>
                )}
              </Card>
            </Stack>
          </Card>
        )
      })}
    </Stack>
  )
}
"""

content = content[:return_start] + new_return + "\n" + content[probe_manager_start:]

with open('src/App.tsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("App.tsx patched successfully!")
