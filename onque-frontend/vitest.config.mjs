import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // 앱 코드가 '@/lib/api' 형태로 import 한다. tsconfig의 paths와 맞춘다.
      '@': fileURLToPath(new URL('./', import.meta.url)),
    },
  },
  test: {
    // 순수 로직만 테스트한다. DOM이 필요해지면 그때 jsdom을 켠다.
    environment: 'node',
    include: ['lib/**/*.test.ts'],
  },
});
