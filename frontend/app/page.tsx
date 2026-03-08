'use client'

import dynamic from 'next/dynamic'

// Dynamic import for Three.js components (requires client-side only)
const BrainScene = dynamic(() => import('@/components/BrainScene'), {
  ssr: false,
  loading: () => (
    <div className="canvas-container flex items-center justify-center bg-black">
      <div className="text-white/30 text-sm">Loading neural network...</div>
    </div>
  )
})

export default function Home() {
  return (
    <main className="relative min-h-screen bg-black overflow-hidden">
      {/* 3D Brain Background */}
      <BrainScene />
      
      {/* Hero Content Overlay */}
      <div className="hero-content relative z-10 min-h-screen flex flex-col justify-between p-6 md:p-12">
        {/* Header */}
        <header className="flex items-center justify-between">
          <div className="text-white/90 font-semibold text-xl tracking-tight">
            LUMAS
          </div>
          <nav className="hidden md:flex items-center gap-8 text-sm text-white/60">
            <a href="#" className="hover:text-white transition-colors">Research</a>
            <a href="#" className="hover:text-white transition-colors">Technology</a>
            <a href="#" className="hover:text-white transition-colors">About</a>
          </nav>
        </header>
        
        {/* Main Hero Text */}
        <div className="flex-1 flex items-center justify-start md:justify-start">
          <div className="max-w-xl">
            <h1 className="text-4xl md:text-6xl font-light text-white text-glow leading-tight mb-6">
              Intelligence
              <br />
              <span className="text-white/40">Visualized</span>
            </h1>
            <p className="text-white/50 text-lg md:text-xl font-light leading-relaxed mb-8">
              Each node represents a neural signal. 
              Brightness indicates strength and confidence 
              — a living map of cognitive activity.
            </p>
            
            {/* Node Strength Legend */}
            <div className="flex items-center gap-6 text-sm text-white/40">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-white/30 pulse-indicator"></span>
                <span>Low activity</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-white/60"></span>
                <span>Medium</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-white shadow-[0_0_10px_rgba(255,255,255,0.5)]"></span>
                <span>High strength</span>
              </div>
            </div>
          </div>
        </div>
        
        {/* Footer */}
        <footer className="flex items-end justify-between">
          <div className="text-white/30 text-xs">
            © 2026 Lumas Neural Systems
          </div>
          <div className="text-white/30 text-xs text-right">
            <div>Real-time neural visualization</div>
            <div className="text-white/20">WebGL powered</div>
          </div>
        </footer>
      </div>
    </main>
  )
}
