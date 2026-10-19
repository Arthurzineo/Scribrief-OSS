import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

// Em desenvolvimento, /api é repassado para o back-end (ajuste o alvo em .env: VITE_API_PROXY).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const target = env.VITE_API_PROXY || 'http://127.0.0.1:8000';
  return {
    plugins: [react()],
    server: { proxy: { '/api': { target, changeOrigin: true } } },
    build: {
      // Django templates reference stable entry names; lazy chunks remain fingerprinted.
      cssCodeSplit: false,
      rollupOptions: { output: {
        entryFileNames: 'assets/app.js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name][extname]',
      } },
    },
  };
});
