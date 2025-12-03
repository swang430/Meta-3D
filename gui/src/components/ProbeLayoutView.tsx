import { useMemo, useState } from 'react'
import { Tabs } from '@mantine/core'
import type { Probe } from '../types/api'
import ProbeLayoutView3D from './ProbeLayoutView3D'
import './ProbeLayoutView.css'

type Props = {
  probes: Probe[]
  selectedId: string
  onSelect: (id: string) => void
}

const RINGS = [1, 2, 3] as const // Ring 1 = upper, Ring 2 = middle, Ring 3 = lower

function normalizeRing(ring: number): number {
  if (RINGS.includes(ring as (typeof RINGS)[number])) {
    return ring
  }
  return 2 // Default to middle ring
}

function parsePosition(position: { azimuth: number; elevation: number; radius: number }): { x: number; y: number; z: number } {
  // Convert spherical coordinates to Cartesian
  const azimuthRad = (position.azimuth * Math.PI) / 180
  const elevationRad = (position.elevation * Math.PI) / 180
  const r = position.radius

  return {
    x: r * Math.cos(elevationRad) * Math.sin(azimuthRad),
    y: r * Math.cos(elevationRad) * Math.cos(azimuthRad),
    z: r * Math.sin(elevationRad),
  }
}

function getRingColor(ring: number): string {
  switch (normalizeRing(ring)) {
    case 1: // Upper ring
      return '#22d3ee'
    case 3: // Lower ring
      return '#f97316'
    case 2: // Middle ring
    default:
      return '#8b5cf6'
  }
}

function scalePoint(value: number, maxAbs: number, size: number): number {
  if (maxAbs === 0) return size / 2
  return (value / (maxAbs * 1.05)) * (size / 2) + size / 2
}

export default function ProbeLayoutView({ probes, selectedId, onSelect }: Props) {
  const [activeTab, setActiveTab] = useState<string | null>('3d')

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
    <Tabs value={activeTab} onChange={setActiveTab}>
      <Tabs.List>
        <Tabs.Tab value="3d">3D 可视化</Tabs.Tab>
        <Tabs.Tab value="2d">2D 视图</Tabs.Tab>
      </Tabs.List>

      <Tabs.Panel value="3d" pt="md">
        <ProbeLayoutView3D probes={probes} selectedId={selectedId} onSelect={onSelect} />
      </Tabs.Panel>

      <Tabs.Panel value="2d" pt="md">
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
                const label = probe.probe_number.toString()
                return (
                  <g
                    key={probe.id}
                    className={isSelected ? 'probe-layout__point probe-layout__point--selected' : 'probe-layout__point'}
                    transform={`translate(${cx}, ${cy})`}
                    onClick={() => onSelect(probe.id)}
                  >
                    <circle r={10} fill={color} />
                    <text
                      y={-14}
                      className="probe-layout__label"
                      style={{
                        fontSize: '10px',
                        fontWeight: 'bold',
                        fill: color,
                        textAnchor: 'middle'
                      }}
                    >
                      {label}
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
                const label = probe.probe_number.toString()
                return (
                  <g
                    key={probe.id}
                    className={isSelected ? 'probe-layout__point probe-layout__point--selected' : 'probe-layout__point'}
                    transform={`translate(${cx}, ${cy})`}
                    onClick={() => onSelect(probe.id)}
                  >
                    <rect width={20} height={20} x={-10} y={-10} rx={4} fill={color} />
                    <text
                      y={-14}
                      className="probe-layout__label"
                      style={{
                        fontSize: '10px',
                        fontWeight: 'bold',
                        fill: color,
                        textAnchor: 'middle'
                      }}
                    >
                      {label}
                    </text>
                  </g>
                )
              })}
            </svg>
          </div>
        </div>
      </Tabs.Panel>
    </Tabs>
  )
}
