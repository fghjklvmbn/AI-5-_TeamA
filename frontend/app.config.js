const path = require('path');
const fs = require('fs');

// Expo config evaluation must never import server-only values from the root
// .env. Read only the explicitly public build inputs needed for local web dev.
const rootEnv = path.resolve(__dirname, '..', '.env');
if (fs.existsSync(rootEnv)) {
  const publicNames = new Set([
    'EXPO_PUBLIC_API_URL',
    'MEMORYPAL_MAIN_PUBLIC_API_URL',
    'MEMORYPAL_PROJECT3_PUBLIC_API_URL',
  ]);
  for (const rawLine of fs.readFileSync(rootEnv, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const separator = line.indexOf('=');
    const name = line.slice(0, separator).trim();
    if (!publicNames.has(name) || process.env[name] !== undefined) continue;
    process.env[name] = line.slice(separator + 1).trim().replace(/^(['"])(.*)\1$/, '$2');
  }
}

const config = require('./app.json');

const profiles = {
  main: '/api_memoripal/main',
  project3: '/api_memoripal/project3/main',
};
const profile = process.env.MEMORYPAL_BUILD_PROFILE || 'main';
if (!Object.prototype.hasOwnProperty.call(profiles, profile)) {
  throw new Error(`Unsupported MEMORYPAL_BUILD_PROFILE: ${profile}`);
}

module.exports = {
  ...config,
  expo: {
    ...config.expo,
    experiments: {
      ...config.expo.experiments,
      baseUrl: process.env.MEMORYPAL_FRONTEND_BASE_URL || profiles[profile],
    },
    extra: {
      ...config.expo.extra,
      deploymentProfile: profile,
    },
  },
};
