'use client'

import { useRef, useMemo, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

interface BrainNodeData {
  position: THREE.Vector3
  strength: number
  baseStrength: number
  phase: number
}

// Generate brain-like low-poly mesh vertices
function generateBrainGeometry() {
  const vertices: number[] = []
  const indices: number[] = []
  const nodePositions: THREE.Vector3[] = []

  // Brain shape parameters
  const leftHemisphere = generateHemisphere(-0.3, 1)
  const rightHemisphere = generateHemisphere(0.3, 1)
  
  // Combine hemispheres
  const allPoints = [...leftHemisphere, ...rightHemisphere]
  
  // Generate brain stem
  const stemPoints = generateBrainStem()
  allPoints.push(...stemPoints)
  
  // Add some randomness to create organic feel
  allPoints.forEach(p => {
    p.x += (Math.random() - 0.5) * 0.05
    p.y += (Math.random() - 0.5) * 0.05
    p.z += (Math.random() - 0.5) * 0.05
  })

  // Store node positions
  allPoints.forEach(p => nodePositions.push(p.clone()))

  // Create vertices array
  allPoints.forEach(p => {
    vertices.push(p.x, p.y, p.z)
  })

  // Generate faces using Delaunay-like triangulation (simplified)
  const tempIndices = triangulatePoints(allPoints)
  indices.push(...tempIndices)

  return { vertices, indices, nodePositions }
}

function generateHemisphere(xOffset: number, scale: number): THREE.Vector3[] {
  const points: THREE.Vector3[] = []
  
  // Create brain hemisphere shape
  const layers = 8
  const pointsPerLayer = 10
  
  for (let layer = 0; layer < layers; layer++) {
    const t = layer / (layers - 1)
    const y = (t - 0.5) * 1.6 // Height
    
    // Brain shape profile (wider at top, narrower at bottom)
    const profileRadius = Math.sin(t * Math.PI) * 0.6 + 0.2
    const brainWidthMod = 1 - Math.pow(Math.abs(t - 0.4), 2) * 0.5
    
    for (let i = 0; i < pointsPerLayer; i++) {
      const angle = (i / pointsPerLayer) * Math.PI * 2
      
      // Create asymmetric brain shape
      let r = profileRadius * brainWidthMod
      
      // Add bumps for brain folds
      r += Math.sin(angle * 3 + layer) * 0.08
      r += Math.sin(angle * 5 - layer * 0.5) * 0.05
      
      // Front-back asymmetry (brain is longer front to back)
      const fbMod = 1 + Math.cos(angle) * 0.2
      
      const x = Math.cos(angle) * r * fbMod * scale + xOffset
      const z = Math.sin(angle) * r * scale * 0.9
      
      points.push(new THREE.Vector3(x, y * scale, z))
    }
  }
  
  // Add central points for better mesh
  points.push(new THREE.Vector3(xOffset, 0.8 * scale, 0)) // Top
  points.push(new THREE.Vector3(xOffset, -0.6 * scale, 0)) // Bottom
  
  return points
}

function generateBrainStem(): THREE.Vector3[] {
  const points: THREE.Vector3[] = []
  
  // Brain stem at the bottom
  const stemLayers = 4
  const pointsPerLayer = 6
  
  for (let layer = 0; layer < stemLayers; layer++) {
    const t = layer / (stemLayers - 1)
    const y = -0.6 - t * 0.5
    const r = 0.15 - t * 0.05
    
    for (let i = 0; i < pointsPerLayer; i++) {
      const angle = (i / pointsPerLayer) * Math.PI * 2
      const x = Math.cos(angle) * r
      const z = Math.sin(angle) * r - 0.1
      points.push(new THREE.Vector3(x, y, z))
    }
  }
  
  // Bottom point
  points.push(new THREE.Vector3(0, -1.2, -0.1))
  
  return points
}

function triangulatePoints(points: THREE.Vector3[]): number[] {
  const indices: number[] = []
  const n = points.length
  
  // Create triangles by connecting nearby points
  for (let i = 0; i < n; i++) {
    const distances: { index: number; dist: number }[] = []
    
    for (let j = 0; j < n; j++) {
      if (i !== j) {
        const dist = points[i].distanceTo(points[j])
        distances.push({ index: j, dist })
      }
    }
    
    // Sort by distance and connect to nearest neighbors
    distances.sort((a, b) => a.dist - b.dist)
    
    // Create triangles with nearby points
    for (let k = 0; k < Math.min(6, distances.length - 1); k++) {
      const j = distances[k].index
      const l = distances[k + 1].index
      
      // Check if this triangle would be reasonable
      const d1 = points[i].distanceTo(points[j])
      const d2 = points[j].distanceTo(points[l])
      const d3 = points[l].distanceTo(points[i])
      
      const maxDist = 0.6
      if (d1 < maxDist && d2 < maxDist && d3 < maxDist) {
        // Ensure consistent winding order
        const normal = new THREE.Vector3()
        const v1 = new THREE.Vector3().subVectors(points[j], points[i])
        const v2 = new THREE.Vector3().subVectors(points[l], points[i])
        normal.crossVectors(v1, v2)
        
        const center = new THREE.Vector3().addVectors(points[i], points[j]).add(points[l]).multiplyScalar(1/3)
        
        if (normal.dot(center) > 0) {
          indices.push(i, j, l)
        } else {
          indices.push(i, l, j)
        }
      }
    }
  }
  
  return indices
}

interface LowPolyBrainProps {
  hovered: boolean
}

export default function LowPolyBrain({ hovered }: LowPolyBrainProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const wireframeRef = useRef<THREE.LineSegments>(null)
  const nodesRef = useRef<THREE.Points>(null)
  const glowNodesRef = useRef<THREE.Points>(null)
  
  // Generate geometry once
  const { geometry, wireframeGeometry, nodeData, nodeGeometry, glowNodeGeometry } = useMemo(() => {
    const { vertices, indices, nodePositions } = generateBrainGeometry()
    
    // Create main geometry
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
    geo.setIndex(indices)
    geo.computeVertexNormals()
    
    // Create wireframe geometry
    const wireGeo = new THREE.WireframeGeometry(geo)
    
    // Create node data with random strengths
    const nodes: BrainNodeData[] = nodePositions.map((pos, i) => ({
      position: pos,
      strength: Math.random(),
      baseStrength: 0.3 + Math.random() * 0.7,
      phase: Math.random() * Math.PI * 2
    }))
    
    // Create points geometry for nodes
    const nodePositionsArray = new Float32Array(nodes.length * 3)
    const nodeSizes = new Float32Array(nodes.length)
    const nodeStrengths = new Float32Array(nodes.length)
    
    nodes.forEach((node, i) => {
      nodePositionsArray[i * 3] = node.position.x
      nodePositionsArray[i * 3 + 1] = node.position.y
      nodePositionsArray[i * 3 + 2] = node.position.z
      nodeSizes[i] = 1.5 + node.baseStrength * 2
      nodeStrengths[i] = node.baseStrength
    })
    
    const nodeGeo = new THREE.BufferGeometry()
    nodeGeo.setAttribute('position', new THREE.Float32BufferAttribute(nodePositionsArray, 3))
    nodeGeo.setAttribute('size', new THREE.Float32BufferAttribute(nodeSizes, 1))
    nodeGeo.setAttribute('strength', new THREE.Float32BufferAttribute(nodeStrengths, 1))
    
    // Glow nodes (larger, more transparent)
    const glowGeo = new THREE.BufferGeometry()
    glowGeo.setAttribute('position', new THREE.Float32BufferAttribute(nodePositionsArray, 3))
    glowGeo.setAttribute('size', new THREE.Float32BufferAttribute(nodeSizes.map(s => s * 1.8), 1))
    glowGeo.setAttribute('strength', new THREE.Float32BufferAttribute(nodeStrengths, 1))
    
    return {
      geometry: geo,
      wireframeGeometry: wireGeo,
      nodeData: nodes,
      nodeGeometry: nodeGeo,
      glowNodeGeometry: glowGeo
    }
  }, [])
  
  // Animation
  useFrame((state) => {
    const time = state.clock.getElapsedTime()
    
    if (meshRef.current) {
      // Slow rotation
      const baseSpeed = 0.15
      const speedMod = hovered ? 1.3 : 1
      meshRef.current.rotation.y = time * baseSpeed * speedMod
      
      // Subtle tilt on hover
      meshRef.current.rotation.x = Math.sin(time * 0.3) * 0.05 + (hovered ? 0.1 : 0)
    }
    
    if (wireframeRef.current) {
      wireframeRef.current.rotation.y = meshRef.current?.rotation.y || 0
      wireframeRef.current.rotation.x = meshRef.current?.rotation.x || 0
    }
    
    if (nodesRef.current) {
      nodesRef.current.rotation.y = meshRef.current?.rotation.y || 0
      nodesRef.current.rotation.x = meshRef.current?.rotation.x || 0
      
      // Animate node sizes based on strength and time
      const sizes = nodesRef.current.geometry.attributes.size as THREE.BufferAttribute
      const strengths = nodesRef.current.geometry.attributes.strength as THREE.BufferAttribute
      
      for (let i = 0; i < nodeData.length; i++) {
        const baseSize = 1.5 + nodeData[i].baseStrength * 2
        const pulse = Math.sin(time * 2 + nodeData[i].phase) * 0.5 + 0.5
        const hoverBoost = hovered ? 1.15 : 1
        sizes.array[i] = baseSize * (0.85 + pulse * 0.3) * hoverBoost
      }
      sizes.needsUpdate = true
    }
    
    if (glowNodesRef.current) {
      glowNodesRef.current.rotation.y = meshRef.current?.rotation.y || 0
      glowNodesRef.current.rotation.x = meshRef.current?.rotation.x || 0
    }
  })
  
  // Custom shader for nodes
  const nodeShader = useMemo(() => ({
    uniforms: {
      time: { value: 0 },
      hovered: { value: 0 }
    },
    vertexShader: `
      attribute float size;
      attribute float strength;
      varying float vStrength;
      
      void main() {
        vStrength = strength;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = size * (300.0 / -mvPosition.z);
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying float vStrength;
      
      void main() {
        float dist = length(gl_PointCoord - vec2(0.5));
        if (dist > 0.5) discard;
        
        float intensity = 1.0 - dist * 2.0;
        intensity = pow(intensity, 2.0);
        
        vec3 color = vec3(1.0);
        float alpha = intensity * (0.3 + vStrength * 0.5);
        
        gl_FragColor = vec4(color, alpha);
      }
    `
  }), [])
  
  const glowShader = useMemo(() => ({
    uniforms: {
      time: { value: 0 }
    },
    vertexShader: `
      attribute float size;
      attribute float strength;
      varying float vStrength;
      
      void main() {
        vStrength = strength;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = size * (300.0 / -mvPosition.z);
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: `
      varying float vStrength;
      
      void main() {
        float dist = length(gl_PointCoord - vec2(0.5));
        if (dist > 0.5) discard;
        
        float intensity = 1.0 - dist * 2.0;
        intensity = pow(intensity, 4.0);
        
        vec3 color = vec3(1.0);
        float alpha = intensity * vStrength * 0.08;
        
        gl_FragColor = vec4(color, alpha);
      }
    `
  }), [])
  
  return (
    <group>
      {/* Main mesh - dark translucent faces */}
      <mesh ref={meshRef} geometry={geometry}>
        <meshStandardMaterial
          color="#1a1a2e"
          roughness={0.8}
          metalness={0.2}
          transparent
          opacity={0.6}
          side={THREE.DoubleSide}
        />
      </mesh>
      
      {/* Wireframe edges */}
      <lineSegments ref={wireframeRef} geometry={wireframeGeometry}>
        <lineBasicMaterial color="#404060" transparent opacity={0.4} />
      </lineSegments>
      
      {/* Glow nodes (background) */}
      <points ref={glowNodesRef} geometry={glowNodeGeometry}>
        <shaderMaterial
          {...glowShader}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      
      {/* Main nodes */}
      <points ref={nodesRef} geometry={nodeGeometry}>
        <shaderMaterial
          {...nodeShader}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  )
}
