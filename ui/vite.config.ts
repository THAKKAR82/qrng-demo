import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
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
// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  if (mode === 'web') {
    return {
      root: fileURLToPath(new URL('./web', import.meta.url)),
      // Read VITE_* settings from ui/, like the other modes.
      envDir: fileURLToPath(new URL('.', import.meta.url)),
      base: './',
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
    plugins: demo ? [react(), viteSingleFile({ removeViteModuleLoader: true })] : [react()],
    build: demo
      ? {
          outDir: fileURLToPath(new URL('../demo', import.meta.url)),
          // demo/ holds a committed .gitkeep; keep it.
          emptyOutDir: false,
        }
      : {},
  }
})
