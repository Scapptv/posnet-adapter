import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Hub merchant admin paneli — real impl AI-2.7
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
