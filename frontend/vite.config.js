import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Khi dev: `npm run dev` (cổng 5173) và API chạy ở cổng 8000.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
  build: { outDir: 'dist', chunkSizeWarningLimit: 1500 },
})
