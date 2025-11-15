import { useMemo } from 'react'
import type { Probe } from '../types/api'
import './ProbeLayoutView.css'

type Props = {
  probes: Probe[]
  selectedId: string
  onSelect: (id: string) => void
}

const RINGS = ['上层', '中层', '下层'] as const

function normalizeRing(ring: string): string {
  if (RINGS.includes(ring as (typeof RINGS)[number])) {
    return ring
  }
  return '中层'
}

function parsePosition(position: string): { x: number; y: number; z: number } {
  const match = position.match(/(-?\d+\.?\d*)/g)
  if (!match || match.length < 3) {
    return { x: 0, y: 0, z: 0 }
  }
  return {
    x: parseFloat(match[0]),
    y: parseFloat(match[1]),
    z: parseFloat(match[2]),
  }
}

function getRingColor(ring: string): string {
  switch (normalizeRing(ring)) {
    case '上层':
      return '#22d3ee'
    case '下层':
      return '#f97316'
    case '中层':
    default:
      return '#8b5cf6'
  }
}

function scalePoint(value: number, maxAbs: number, size: number): number {
  if (maxAbs === 0) return size / 2
  return (value / (maxAbs * 1.05)) * (size / 2) + size / 2
}

export default function ProbeLayoutView({ probes, selectedId, onSelect }: Props) {
  const parsed = useMemo(() => {
    return probes.map((probe) => ({
      ...probe,
      ringNormalized: normalizeRing(probe.ring),
      pos: parsePosition(probe.position),
    }))
  }, [probes])

  const maxHorizontal = useMemo(() => {
    const max = parsed.reduce((acc, probe) => {
      const { x, y } = probe.pos
      return Math.max(acc, Math.sqrt(x * x + y * y))
    }, 0)
    return max === 0 ? 1 : Math.ceil(max)
  }, [parsed])

  const maxHeight = useMemo(() => {
    const max = parsed.reduce((acc, probe) => Math.max(acc, Math.abs(probe.pos.z)), 0)
    return max === 0 ? 1 : Math.ceil(max)
  }, [parsed])

  return (
    <div className="probe-layout">
      <div className="probe-layout__canvas">
        <h3>俯视图</h3>
        <svg viewBox="0 0 320 320" className="probe-layout__svg">
          <circle cx="160" cy="160" r="150" className="probe-layout__ring probe-layout__ring--outer" />
          <circle cx="160" cy="160" r="100" className="probe-layout__ring" />
          <circle cx="160" cy="160" r="50" className="probe-layout__ring" />
          <line x1="160" y1="10" x2="160" y2="310" className="probe-layout__axis" />
          <line x1="10" y1="160" x2="310" y2="160" className="probe-layout__axis" />
          {parsed.map((probe) => {
            const { x, y } = probe.pos
            const cx = scalePoint(x, maxHorizontal, 320)
            const cy = scalePoint(y, maxHorizontal, 320)
            const color = getRingColor(probe.ringNormalized)
            const isSelected = probe.id === selectedId
            return (
              <g
                key={probe.id}
                className={isSelected ? 'probe-layout__point probe-layout__point--selected' : 'probe-layout__point'}
                transform={`translate(${cx}, ${cy})`}
                onClick={() => onSelect(probe.id)}
              >
                <circle r={12} fill={color} />
                <text y={4} className="probe-layout__label">
                  {probe.id.replace('P-', '')}
                </text>
              </g>
            )
          })}
        </svg>
      </div>

      <div className="probe-layout__canvas">
        <h3>侧视图</h3>
        <svg viewBox="0 0 320 220" className="probe-layout__svg">
          <line x1="20" y1="110" x2="300" y2="110" className="probe-layout__axis" />
          <line x1="160" y1="10" x2="160" y2="210" className="probe-layout__axis" />
          {parsed.map((probe) => {
            const cx = scalePoint(probe.pos.x, maxHorizontal, 320)
            const cy = scalePoint(-probe.pos.z, maxHeight, 220)
            const color = getRingColor(probe.ringNormalized)
            const isSelected = probe.id === selectedId
            return (
              <g
                key={probe.id}
                className={isSelected ? 'probe-layout__point probe-layout__point--selected' : 'probe-layout__point'}
                transform={`translate(${cx}, ${cy})`}
                onClick={() => onSelect(probe.id)}
              >
                <rect width={22} height={22} x={-11} y={-11} rx={4} fill={color} />
                <text y={4} className="probe-layout__label">
                  {probe.id.replace('P-', '')}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
