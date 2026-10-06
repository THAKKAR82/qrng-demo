import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { viteSingleFile } from 'vite-plugin-singlefile'

// Three ways to run the UI (see README):
//   npm run dev        dev server
//   npm run preview    production build in ui/dist/, served locally: the primary way to present
//   npm run build:demo `--mode demo`: ONE self-contained index.html (JS, CSS, fonts and data
//                      inlined) written to the repo-level demo/, which opens under file://
//                      with the network off.
// https://vite.dev/config/
export default defineConfig(({ mode }) => {
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
