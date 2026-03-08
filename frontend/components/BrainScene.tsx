'use client'

import { Suspense, useState, useCallback } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera } from '@react-three/drei'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import LowPolyBrain from './LowPolyBrain'

function Scene({ hovered }: { hovered: boolean }) {
  return (
    <>
      {/* Camera */}
      <PerspectiveCamera makeDefault position={[0, 0, 4]} fov={50} />
      
      {/* Lighting */}
      <ambientLight intensity={0.2} />
      <directionalLight position={[5, 5, 5]} intensity={0.5} color="#ffffff" />
      <directionalLight position={[-5, 3, -5]} intensity={0.3} color="#6366f1" />
      <pointLight position={[0, 2, 3]} intensity={0.4} color="#ffffff" />
      
      {/* Brain */}
      <Suspense fallback={null}>
        <LowPolyBrain hovered={hovered} />
      </Suspense>
      
      {/* Subtle controls - disabled for automatic rotation focus */}
      <OrbitControls
        enableZoom={false}
        enablePan={false}
        enableRotate={false}
        minPolarAngle={Math.PI / 3}
        maxPolarAngle={Math.PI / 1.5}
      />
      
      {/* Post-processing for glow */}
      <EffectComposer>
        <Bloom
          intensity={0.3}
          luminanceThreshold={0.6}
          luminanceSmoothing={0.4}
          mipmapBlur
        />
      </EffectComposer>
    </>
  )
}

export default function BrainScene() {
  const [hovered, setHovered] = useState(false)
  
  const handlePointerEnter = useCallback(() => setHovered(true), [])
  const handlePointerLeave = useCallback(() => setHovered(false), [])
  
  return (
    <div 
      className="canvas-container"
      onPointerEnter={handlePointerEnter}
      onPointerLeave={handlePointerLeave}
    >
      <Canvas
        gl={{ 
          antialias: true,
          alpha: true,
          powerPreference: 'high-performance'
        }}
        style={{ background: '#000000' }}
      >
        <Scene hovered={hovered} />
      </Canvas>
    </div>
  )
}
