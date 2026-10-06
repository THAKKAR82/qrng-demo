import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { viteSingleFile } from 'vite-plugin-singlefile'

// https://vite.dev/config/
// viteSingleFile inlines all JS/CSS into dist/index.html so the build can be
// copied to demo/ and opened offline. Copying to demo/ is a separate task step.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
})
