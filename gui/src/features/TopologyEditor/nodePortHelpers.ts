/**
 * Node port enumeration for the connection drawer pin Selects.
 *
 * Why this exists: source_pin / target_pin used to be free-text, which let
 * operators type "P5" for a node that only exposes ports P1..P4 — that breaks
 * downstream SCPI orchestration silently. Restricting to a known set per node
 * type catches typos at edit time.
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
  switch_slot: ['in', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8'],
  probe: ['V', 'H'],
  amplifier: ['in', 'out'],
  combiner: ['in1', 'in2', 'in3', 'in4', 'out'],
  pad: ['in', 'out'],
  antenna: ['P1'],
  termination: ['in'],
}

export function getNodePorts(node: TopologyNode | undefined): string[] {
  if (!node) return ['out', 'in']
  const declared = node.params?.ports
  if (Array.isArray(declared) && declared.every((p) => typeof p === 'string') && declared.length > 0) {
    return declared as string[]
  }
  // switch_slot port count can vary; let params.num_ports drive it when present.
  if (node.type === 'switch_slot' && typeof node.params?.num_ports === 'number') {
    const n = Math.max(1, Math.min(64, Math.floor(node.params.num_ports)))
    return ['in', ...Array.from({ length: n }, (_, i) => `P${i + 1}`)]
  }
  return DEFAULT_PORTS_BY_TYPE[node.type] || ['out', 'in']
}

/** Convenience: map node port list to Mantine Select options. */
export function nodePortsToSelectOptions(node: TopologyNode | undefined) {
  return getNodePorts(node).map((p) => ({ value: p, label: p }))
}
