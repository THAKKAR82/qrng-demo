/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The address phones open for the audience view; shown as a QR code on slide 1. */
  readonly VITE_AUDIENCE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
