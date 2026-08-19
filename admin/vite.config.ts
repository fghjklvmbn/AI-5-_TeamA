import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const profiles = {
  main: {
    base: '/api_memoripal/manage/',
    outDir: 'dist-main',
  },
  project3: {
    base: '/api_memoripal/project3/manage/',
    outDir: 'dist-project3',
  },
} as const;

export default defineConfig(() => {
  const profileName = process.env.MEMORYPAL_BUILD_PROFILE || 'main';
  const profile = profiles[profileName as keyof typeof profiles];
  if (!profile) throw new Error(`Unsupported MEMORYPAL_BUILD_PROFILE: ${profileName}`);
  return {
    plugins: [react()],
    base: process.env.MEMORYPAL_ADMIN_BASE_URL || profile.base,
    build: {
      outDir: process.env.MEMORYPAL_ADMIN_OUT_DIR || profile.outDir,
      emptyOutDir: true,
    },
  };
});
