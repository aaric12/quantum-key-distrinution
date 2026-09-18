import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Dev-only workaround: vite's fs allow-list mis-resolves when the project
    // path contains a ':' (e.g. "project 26:9"). Safe to remove if the project
    // lives in a colon-free path.
    fs: { strict: false },
  },
})
