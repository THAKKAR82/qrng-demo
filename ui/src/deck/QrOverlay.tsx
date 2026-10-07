import { audienceUrl } from '../lib/audienceUrl'
import { QrCode } from '../panels/QrCode'

const url = audienceUrl()

/**
 * A large QR code over the current slide, for latecomers (SPEC.md, Section 9.1). Q shows
 * and hides it; Escape hides it.
 */
export function QrOverlay() {
  return (
    <aside className="qr-overlay" aria-label="QR code for phones">
      {url === null ? (
        <p className="qr-overlay__missing">
          No audience address was set when this deck was built (VITE_AUDIENCE_URL), so there is no QR code.
        </p>
      ) : (
        <div className="qr-overlay__content">
          <div className="qr-overlay__code">
            <QrCode value={url.href} label={`QR code for ${url.short}`} />
          </div>
          <div className="qr-overlay__text">
            <p className="qr-overlay__heading">Play along on your phone</p>
            <p className="qr-overlay__url num">{url.short}</p>
          </div>
        </div>
      )}
    </aside>
  )
}
