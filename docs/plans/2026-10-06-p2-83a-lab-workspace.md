# P2-83A 实施计划

> 执行方式：主代理使用executing-plans顺序实现；完成后按requesting-code-review进行独立只读内审，不并行开发。

**目标**：操作员从“实验室配置”一个入口访问总览和三个既有编辑器。
**架构**：保留App原SectionKey编辑器映射，新建工作台壳包住它们；总览复用OperationalLabContext及现有GET API，不改变保存或执行配置。
**技术栈**：现有React、Mantine、TanStack Query、TypeScript；不新增产品依赖。
**设计**：[P2-83A书面设计](../design/2026-10-06-p2-83a-lab-workspace.md)。用户2026-10-06回复“继续”确认书面设计进入实施。

## 全局约束

- 仪器资源保存后分类HAL激活保持原逻辑；“同步到LabProfile”仍是显式独立操作，未保存草稿仍不能同步。
- 不新增定时轮询，不调用驱动、SCPI、连接测试、HAL reload或写接口。
- 不修改后端schema、数据库、OpenAPI、执行冻结、认证、校准、KPI或正式provenance白名单。
- 不增加跨子视图草稿持久化；保留原编辑器挂载/卸载语义。
- NotebookLM不适用：没有新增或修改仪器语义。memory参考已用当前代码复核。

## 文件职责与关系全集

- `gui/src/App.tsx`（修）：左栏、sectionDescriptor、renderSection、内部onNavigate。equipment/probeManager/topologyEditor三个旧key继续定位子视图；labWorkspace定位总览。
- `gui/src/features/LabWorkspace/LabWorkspace.tsx`（修，新）：工作台壳，接收view、onNavigate与当前子视图children；不持有编辑器配置或复制Lab选择。
- `gui/src/features/LabWorkspace/LabOverview.tsx`（修，新）：总览，显示同lab的readiness与rf-chains；错误和身份分叉不展示成功。
- `gui/test/labWorkspace.browser.js`（修，新）：真实App交互；仅替换HTTP transport，覆盖导航、lab归属、读取失败、刷新、不写入。
- `gui/test/instrumentCatalogError.browser.js`（顺带）：原浏览器回归改从统一入口进入仪器资源，保留既有目录失败/草稿断言。
- `docs/roadmap-first-call.md`及本设计/计划（修）：顶表、LOCAL-OPEN与本条同步状态。

验收关系：App导航→旧编辑器；顶部Lab选择→显式请求lab→服务器投影→总览；编辑器dirty/in-flight→已有切换阻断。测试只替换HTTP，不替换App或上下文。

## Task 1：统一导航与工作台壳

接口：`LabWorkspace({view,onNavigate,children})`；view为`labWorkspace|equipment|probeManager|topologyEditor`，onNavigate保持原SectionKey setter；总览仅在labWorkspace挂载。

- [ ] 写浏览器RED：真实App左栏只出现一个“实验室配置”，点击进入总览，再切换三个编辑子视图。

```js
await page.getByRole('tab', {name:'实验室配置',exact:true}).click();
await page.getByRole('tab', {name:'仪器资源',exact:true}).click();
await page.getByRole('button', {name:'替换 / 配置实装',exact:true}).waitFor();
```

- [ ] 运行RED：独立Vite端口5198，无生产API重启；`playwright_cli.sh -s=p283a run-code --filename gui/test/labWorkspace.browser.js`。旧版缺统一入口必须失败。
- [ ] 最小实现：左栏三个记录替换为labWorkspace；sectionDescriptor/sidebar active把旧三个key映射到labWorkspace；renderSection四个case统一包壳后按key挂原编辑器。

```tsx
case 'labWorkspace':
case 'equipment':
case 'probeManager':
case 'topologyEditor':
  return <LabWorkspace view={section} onNavigate={payload.setActiveSection}>
    {section === 'equipment' ? <EquipmentManager /> :
     section === 'probeManager' ? <ProbeManager onNavigate={payload.setActiveSection} /> :
     section === 'topologyEditor' ? <TopologyEditor /> : null}
  </LabWorkspace>
```

- [ ] GREEN后执行上下文与同步契约回归，并提交本Task。

## Task 2：同Lab只读总览与完整验证

接口：LabOverview无外部配置props；useOperationalLab获取唯一选择；fetchReadiness与fetchRFChains接收显式lab id。

- [ ] 扩展浏览器RED：lab A/B返回不同绑定；A刷新503时不得继续展示A成功数据；B响应冒用A时显示冲突；无选择不发总览请求；HAL unavailable仍展示DB Lab；Mock标诊断；未评估兼容性不是通过；手动刷新只GET。

```js
await page.getByRole('button',{name:'刷新总览',exact:true}).click();
await page.getByText('读取失败', {exact:false}).waitFor();
if (await page.getByText('adapter-lab-a',{exact:true}).count()) {
  throw new Error('失败后仍把旧快照当成功');
}
```

- [ ] 最小实现：两个query绑定lab（readiness复用cockpit键，rf-chains新局部键），enabled要求已选lab；不设refetchInterval；isError/isFetching先于data分支；同时核对response lab身份与nested binding身份；只展示服务器字段和原status，不生成正式通过总判。
- [ ] 总览含Lab/暗室、基站binding、信道仿真器binding、HAL快照与RF链路，明确“当前快照、不是执行冻结证据”；空值标未解析，不填默认实测值。
- [ ] 实跑浏览器正反例及核心变异（去掉lab归属校验、错误时继续用缓存），恢复后核对diff；1280与窄屏截图检查无内容遮挡。
- [ ] GUI相关Node契约、完整GUI Node测试、`npm run build --prefix gui`；后端只执行rule gates及OpenAPI受影响门，契约四镜像未改以diff核实；不重复全后端。
- [ ] 独立只读内审；功能P1及本片可执行P2最小修复并必要回归。提交、推送、Ready PR；核对最新SHA触发Codex R1→R2，完成结果到达即读取，不再额外等一轮。
- [ ] R2覆盖最新HEAD无P1且合并条件通过时merge commit；fetch、主目录ff-only同步、保留用户资料、清理仅本片worktree/branch。

## 检查记录

设计各项均由Task1/2覆盖；范围仅A片，B/C未实现。不将本地Mock交互称为现场验证。最终PR记录实际命令、输出、测试输入版本、审查HEAD及时间；文档更新不触发重复全量。
