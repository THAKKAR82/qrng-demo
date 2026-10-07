import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'
import { viteSingleFile } from 'vite-plugin-singlefile'

// Ways to build and run the UI (see README):
//   npm run dev        dev server
//   npm run preview    production build in ui/dist/, served locally: the primary way to present
//   npm run build:demo `--mode demo`: ONE self-contained index.html (JS, CSS, fonts and data
//                      inlined) written to the repo-level demo/, which opens under file://
//                      with the network off.
//   npm run build:web  `--mode web`: the phone version only, from web/index.html, as a static
//                      site in ui/dist-web/ with index.html at its root. No presenter code is
//                      imported from that entry, so none is bundled. `npm run preview:web`
//                      serves it.
//
// __QRNG_LIVE__ is true only in the presenter builds that python -m pipeline.tasks live-server
// can serve (dev and `npm run build` into ui/dist/). In the demo and web builds it is false, so
// the live-run code is removed from those bundles entirely (SPEC.md, Section 6.4).
// https://vite.dev/config/

const envDir = fileURLToPath(new URL('.', import.meta.url))

/**
 * Records the build's VITE_AUDIENCE_URL in a meta tag, so live-server can say at startup
 * which address the QR codes in the build it serves point to. The app itself reads the
 * setting from import.meta.env as before.
 */
function audienceUrlMeta(mode: string): Plugin {
  const value = loadEnv(mode, envDir, 'VITE_').VITE_AUDIENCE_URL ?? ''
  const escaped = value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return {
    name: 'qrng-audience-url-meta',
    transformIndexHtml: (html) =>
      html.replace('</head>', `  <meta name="qrng-audience-url" content="${escaped}" />\n  </head>`),
  }
}

export default defineConfig(({ mode }) => {
  if (mode === 'web') {
    return {
      root: fileURLToPath(new URL('./web', import.meta.url)),
      // Read VITE_* settings from ui/, like the other modes.
      envDir,
      base: './',
      define: { __QRNG_LIVE__: 'false' },
      plugins: [react()],
      build: {
        outDir: fileURLToPath(new URL('./dist-web', import.meta.url)),
        emptyOutDir: true,
      },
    }
  }
  const demo = mode === 'demo'
  return {
    // Relative asset URLs, so builds work from any folder and under file://.
    base: './',
    define: { __QRNG_LIVE__: demo ? 'false' : 'true' },
    plugins: demo
      ? [react(), viteSingleFile({ removeViteModuleLoader: true })]
      : [react(), audienceUrlMeta(mode)],
    build: demo
      ? {
          outDir: fileURLToPath(new URL('../demo', import.meta.url)),
          // demo/ holds a committed .gitkeep; keep it.
          emptyOutDir: false,
        }
      : {},
  }
})
