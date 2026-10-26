import { test } from 'node:test';
import assert from 'node:assert/strict';
import * as transport from '../src/api/switchTopologyService.ts';
import type { SwitchTopology } from '../src/api/switchTopologyService.ts';
import { renderToStaticMarkup } from 'react-dom/server';
import React from 'react';
import { MantineProvider } from '@mantine/core';
import { SignalEdge } from '../src/features/TopologyEditor/CustomEdges.tsx';
import { ReactFlowProvider } from '@xyflow/react';

// tsx的测试转换不使用Vite的自动JSX运行时。
(globalThis as any).React=React;

const draft = (): SwitchTopology => ({name:'图', switch_category_id:'s', is_active:true, is_default:false,
  nodes:[{id:'a',type:'pad',label:'衰减器',position: {x:12,y:34},params:{}}],
  connections:[{id:'ap',source:'a',target:'p',pa_gain_db:'旧格式'}],operating_modes:[]});

test('清洁保存不补连接或视图默认位置；显式声明仅携带仍存活边',()=>{
  const graph=draft();
  const before=structuredClone(graph);
  const payload=transport.topologyUpdatePayload(graph,{});
  assert.deepEqual(payload,{nodes:graph.nodes,connections:graph.connections,operating_modes:[]});
  assert.deepEqual(graph,before);
  assert.deepEqual(transport.topologyUpdatePayload(graph,{
    ap:['cable_loss_db'],removed:['cable_length_m'],
  }).connection_numeric_declarations,{ap:['cable_loss_db']});
});

test('显式数值意图合并去重，不变更原map；删边后不会串到新图',()=>{
  const initial={ap:['cable_loss_db'] as transport.ConnectionNumericField[]};
  const next=transport.mergeConnectionDeclarations(initial,'ap',['cable_loss_db','cable_length_m']);
  assert.deepEqual(next,{ap:['cable_loss_db','cable_length_m']});
  assert.deepEqual(initial,{ap:['cable_loss_db']});
  const graph=draft(); graph.connections=[];
  assert.equal(transport.topologyUpdatePayload(graph,next).connection_numeric_declarations,undefined);
});

test('PA传输原始JSON必须运行时收窄，零/负值仍按PA着色',()=>{
  const render=(value: unknown)=>renderToStaticMarkup(React.createElement(MantineProvider,null,React.createElement(ReactFlowProvider,null,
    React.createElement(SignalEdge,{id:'ap',source:'a',target:'p',sourceX:0,sourceY:0,targetX:100,targetY:100,
      data:{pa_gain_db:value,cable_loss_db:0},selected:false,selectable:true,deletable:true,
      zIndex:0, sourcePosition:'right',targetPosition:'left'} as any))));
  for(const value of ['12',true,{},null,undefined]) assert.doesNotMatch(render(value),/stroke:#F59E0B/);
  for(const value of [0,-2,12]) assert.match(render(value),/stroke:#F59E0B/);
});
