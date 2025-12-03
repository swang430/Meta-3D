import { useRef, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Grid, Text, Sphere } from '@react-three/drei'
import * as THREE from 'three'
import type { Probe } from '../types/api'

type Props = {
  probes: Probe[]
  selectedId: string
  onSelect: (id: string) => void
}

const RINGS = [1, 2, 3] as const

function normalizeRing(ring: number): number {
  if (RINGS.includes(ring as (typeof RINGS)[number])) {
    return ring
  }
  return 2
}

function parsePosition(position: { azimuth: number; elevation: number; radius: number }): [number, number, number] {
  // Convert spherical coordinates to Cartesian (Three.js uses Y-up coordinate system)
  const azimuthRad = (position.azimuth * Math.PI) / 180
  const elevationRad = (position.elevation * Math.PI) / 180
  const r = position.radius

  const x = r * Math.cos(elevationRad) * Math.sin(azimuthRad)
  const y = r * Math.sin(elevationRad)  // Y is vertical in Three.js
  const z = r * Math.cos(elevationRad) * Math.cos(azimuthRad)

  return [x, y, z]
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

type ProbeMarkerProps = {
  probe: Probe & { pos: [number, number, number] }
  isSelected: boolean
  onClick: () => void
}

function ProbeMarker({ probe, isSelected, onClick }: ProbeMarkerProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const color = getRingColor(probe.ring)

  // Animate selected probe
  useFrame((state) => {
    if (meshRef.current && isSelected) {
      const scale = 1 + Math.sin(state.clock.elapsedTime * 3) * 0.15
      meshRef.current.scale.setScalar(scale)
    } else if (meshRef.current) {
      meshRef.current.scale.setScalar(1)
    }
  })

  return (
    <group position={probe.pos}>
      <Sphere ref={meshRef} args={[0.15, 32, 32]} onClick={onClick}>
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={isSelected ? 0.5 : 0.2}
          metalness={0.5}
          roughness={0.3}
        />
      </Sphere>

      {/* Probe number label */}
      <Text
        position={[0, 0.3, 0]}
        fontSize={0.2}
        color={color}
        anchorX="center"
        anchorY="middle"
        outlineWidth={0.02}
        outlineColor="#000000"
      >
        {probe.probe_number.toString()}
      </Text>

      {/* Connection line to origin */}
      <line>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            count={2}
            array={new Float32Array([0, 0, 0, ...probe.pos])}
            itemSize={3}
          />
        </bufferGeometry>
        <lineBasicMaterial color={color} opacity={0.2} transparent linewidth={1} />
      </line>
    </group>
  )
}

function Scene({ probes, selectedId, onSelect }: Props) {
  const parsedProbes = useMemo(() => {
    return probes.map((probe) => ({
      ...probe,
      pos: parsePosition(probe.position),
    }))
  }, [probes])

  const maxRadius = useMemo(() => {
    const max = parsedProbes.reduce((acc, probe) => {
      const [x, y, z] = probe.pos
      const radius = Math.sqrt(x * x + y * y + z * z)
      return Math.max(acc, radius)
    }, 0)
    return max === 0 ? 1 : max
  }, [parsedProbes])

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.4} />
      <directionalLight position={[10, 10, 5]} intensity={0.8} castShadow />
      <directionalLight position={[-10, -10, -5]} intensity={0.3} />
      <pointLight position={[0, 0, 0]} intensity={0.5} color="#ffffff" />

      {/* Reference sphere at origin (quiet zone) */}
      <Sphere args={[0.3, 32, 32]} position={[0, 0, 0]}>
        <meshStandardMaterial
          color="#ffffff"
          opacity={0.1}
          transparent
          wireframe
        />
      </Sphere>

      {/* Coordinate axes */}
      <axesHelper args={[maxRadius * 1.2]} />

      {/* Ground grid */}
      <Grid
        args={[maxRadius * 3, maxRadius * 3]}
        cellSize={0.5}
        cellThickness={0.5}
        cellColor="#6b7280"
        sectionSize={2}
        sectionThickness={1}
        sectionColor="#9ca3af"
        fadeDistance={maxRadius * 4}
        fadeStrength={1}
        position={[0, -maxRadius * 1.1, 0]}
        infiniteGrid
      />

      {/* Probes */}
      {parsedProbes.map((probe) => (
        <ProbeMarker
          key={probe.id}
          probe={probe}
          isSelected={probe.id === selectedId}
          onClick={() => onSelect(probe.id)}
        />
      ))}

      {/* Camera controls */}
      <OrbitControls
        makeDefault
        minDistance={maxRadius * 0.5}
        maxDistance={maxRadius * 5}
        enableDamping
        dampingFactor={0.05}
        rotateSpeed={0.5}
        zoomSpeed={0.8}
      />
    </>
  )
}

export default function ProbeLayoutView3D({ probes, selectedId, onSelect }: Props) {
  return (
    <div style={{ width: '100%', height: '600px', background: '#0a0a0a', borderRadius: '8px' }}>
      <Canvas
        camera={{
          position: [5, 5, 5],
          fov: 50,
        }}
        shadows
      >
        <Scene probes={probes} selectedId={selectedId} onSelect={onSelect} />
      </Canvas>
    </div>
  )
}
