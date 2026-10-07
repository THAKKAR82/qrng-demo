import qrcode from 'qrcode-generator'
import { useMemo } from 'react'
import './QrCode.css'

interface QrCodeProps {
  value: string
  /** Accessible name, such as "QR code for example.org/qrng". */
  label: string
}

/**
 * A QR code drawn as SVG in the app itself, from the bundled qrcode-generator library:
 * no online service, no network. Dark modules in ink on the surface, with the standard
 * four-module quiet zone.
 */
export function QrCode({ value, label }: QrCodeProps) {
  const { size, path } = useMemo(() => {
    const qr = qrcode(0, 'M')
    qr.addData(value)
    qr.make()
    const n = qr.getModuleCount()
    let d = ''
    for (let r = 0; r < n; r += 1) {
      for (let c = 0; c < n; c += 1) {
        if (qr.isDark(r, c)) {
          d += `M${c + 4},${r + 4}h1v1h-1z`
        }
      }
    }
    return { size: n + 8, path: d }
  }, [value])
  return (
    <svg className="qr-code" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <rect width={size} height={size} className="qr-code__ground" />
      <path d={path} className="qr-code__modules" />
    </svg>
  )
}
