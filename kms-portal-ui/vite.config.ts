/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

// HTTPS: enabled when cert files exist, disable with VITE_DISABLE_HTTPS=true
const certPath = path.resolve(__dirname, 'kms.local.dev.pem')
const keyPath = path.resolve(__dirname, 'kms.local.dev-key.pem')
const disableHttps = process.env.VITE_DISABLE_HTTPS === 'true'
const certsExist = fs.existsSync(certPath) && fs.existsSync(keyPath)
const httpsConfig = (!disableHttps && certsExist)
  ? { key: fs.readFileSync(keyPath), cert: fs.readFileSync(certPath) }
  : false

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    https: httpsConfig,
    host: '0.0.0.0',
    port: 3000,
    open: true,
    proxy: {
      '/api': {
        target: 'http://localhost:9000',
        changeOrigin: true,
        secure: false,
      },
      '/uploads': {
        target: 'http://localhost:9000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: true,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
