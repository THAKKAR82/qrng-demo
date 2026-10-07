/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The address phones open for the audience view; shown as a QR code on slide 1. */
  readonly VITE_AUDIENCE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/**
 * True in the presenter builds live-server can serve; false in the single-file demo build
 * and the phone site, so the live-run code is dropped from them (vite.config.ts).
 */
declare const __QRNG_LIVE__: boolean
