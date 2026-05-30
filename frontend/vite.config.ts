import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig(({ mode }) => {
  const rootEnv = loadEnv(mode, path.resolve(__dirname, '..'), '')
  const frontendEnv = loadEnv(mode, __dirname, '')
  const readEnv = (key: string) => process.env[key] ?? frontendEnv[key] ?? rootEnv[key]

  return {
    plugins: [react(), tailwindcss()],
    define: {
      'import.meta.env.VITE_SUPABASE_URL': JSON.stringify(
        readEnv('VITE_SUPABASE_URL') ?? readEnv('SUPABASE_URL') ?? ''
      ),
      'import.meta.env.VITE_SUPABASE_ANON_KEY': JSON.stringify(
        readEnv('VITE_SUPABASE_ANON_KEY') ?? readEnv('SUPABASE_ANON_KEY') ?? ''
      ),
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/scalar': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/openapi.json': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
