import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Lumas | Neural Intelligence',
  description: 'A living neural network visualization powered by advanced AI',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  )
}
