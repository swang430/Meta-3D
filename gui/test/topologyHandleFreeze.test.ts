import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MantineProvider } from '@mantine/core';
import { ReactFlow } from '@xyflow/react';
import { customNodeTypes } from '../src/features/TopologyEditor/CustomNodes.tsx';
(globalThis as any).React=React;

// 真实ReactFlow将节点connectable转换为NodeProps.isConnectable；不mock节点或Handle。
// SSR不运行全局StoreUpdater effect，因此显式给节点连接状态；全局冻结另由真实浏览器验证。
function handles(declared: boolean, enabled: boolean): string[] {
  const markup = renderToStaticMarkup(React.createElement(MantineProvider, {},
    React.createElement(ReactFlow, {
      width: 800, height: 600, nodesConnectable: enabled, nodeTypes: customNodeTypes,
      nodes: [{id:'probe',type:'probe',width:180,height:80,connectable:enabled,position:{x:100,y:100},
        data:{label:'冻结探头',params:declared?{ports:['A','B']}:{}}}],
    })));
  return [...markup.matchAll(/class="([^"]*\breact-flow__handle\b[^"]*)"/g)].map(match=>match[1]);
}

for (const declared of [false, true]) {
  test(`${declared?'显式':'旧式'}端口在全局禁止连接时没有连接指示或起止手势，恢复后仍可连接`,()=>{
    const disabled=handles(declared,false), enabled=handles(declared,true);
    assert.equal(disabled.length,declared?4:1);
    assert.equal(enabled.length,declared?4:1);
    for(const classes of disabled) assert.doesNotMatch(classes,/\b(connectable|connectablestart|connectableend|connectionindicator)\b/);
    for(const classes of enabled) {
      assert.match(classes,/\bconnectable\b/);
      assert.match(classes,/\bconnectablestart\b/);
      assert.match(classes,/\bconnectableend\b/);
    }
  });
}
