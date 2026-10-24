/**
 * Node port enumeration for the connection drawer pin Selects.
 *
 * Why this exists: source_pin / target_pin used to be free-text, which let
 * 这里描述画布端点，不是厂商能力清单，也不构成真实仪器端口或自动控制资格。
 *
 * Where to extend: when a new node type is added, list its ports here. If
 * `params.ports` is set on the node (some imports do), it overrides the
 * defaults — that's the supported way for an installer to declare a
 * non-standard port set without code change.
 */
import type { TopologyNode } from '../../api/switchTopologyService'

const DEFAULT_PORTS_BY_TYPE: Record<string, string[]> = {
  ce_port: ['out'],
  bse_port: ['out'],
  sa_port: ['in'],
  switch_slot: ['P1', 'P2', 'P3', 'P4'],
  probe: ['in'],
  channel_emulator: ['in1', 'in2', 'in3', 'in4', 'out'],
  communication_tester: [],
  emcenter: ['switch_in', 'pa_out', 'sw_out', 'pa_in'],
  reference_antenna: ['rf'],
  signal_analyzer: ['rf_in'],
  vna: ['Port1', 'Port2'],
  amplifier: ['in', 'out'],
  combiner: ['in1', 'in2', 'in3', 'in4', 'out'],
  pad: ['in', 'out'],
  antenna: ['P1'],
  termination: ['in'],
}

export function getNodePorts(node: TopologyNode | undefined): string[] {
  if (!node) return ['out', 'in']
  const declared = node.params?.ports
  if (Array.isArray(declared) && declared.every((p) => typeof p === 'string')) {
    return declared as string[]
  }
  return DEFAULT_PORTS_BY_TYPE[node.type] || ['out', 'in']
}

/** Convenience: map node port list to Mantine Select options. */
export function nodePortsToSelectOptions(node: TopologyNode | undefined) {
  return getNodePorts(node).map((p) => ({ value: p, label: p }))
}
