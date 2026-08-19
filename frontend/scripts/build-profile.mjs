import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const profiles = {
  main: {
    baseUrl: '/api_memoripal/main',
    defaultApiUrl: 'http://127.0.0.1:8010/v1',
    apiVariable: 'MEMORYPAL_MAIN_PUBLIC_API_URL',
    outputDir: 'dist-main',
  },
  project3: {
    baseUrl: '/api_memoripal/project3/main',
    defaultApiUrl: 'http://127.0.0.1:8010/v1',
    apiVariable: 'MEMORYPAL_PROJECT3_PUBLIC_API_URL',
    outputDir: 'dist-project3',
  },
};

const profileName = process.argv[2] || 'main';
const profile = profiles[profileName];
if (!profile) {
  console.error(`Unknown frontend build profile: ${profileName}`);
  process.exit(2);
}

function normalizePublicApiUrl(rawValue) {
  const value = String(rawValue).trim().replace(/\/+$/, '');
  if (value.startsWith('/')) return value || '/';
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`Frontend public API URL is invalid: ${value}`);
  }
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) {
    throw new Error('Frontend public API URL must be HTTP(S) and must not contain credentials');
  }
  if (parsed.search || parsed.hash) {
    throw new Error('Frontend public API URL must not contain a query string or fragment');
  }
  return value;
}

const executable = process.platform === 'win32' ? 'npx.cmd' : 'npx';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repositoryEnv = resolve(root, '..', '.env');
const publicFileValues = {};
if (existsSync(repositoryEnv)) {
  for (const rawLine of readFileSync(repositoryEnv, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const separator = line.indexOf('=');
    const name = line.slice(0, separator).trim();
    if (![profile.apiVariable, 'EXPO_PUBLIC_API_URL'].includes(name)) continue;
    publicFileValues[name] = line.slice(separator + 1).trim().replace(/^(['"])(.*)\1$/, '$2');
  }
}
const apiUrl = normalizePublicApiUrl(process.env[profile.apiVariable]
  || publicFileValues[profile.apiVariable]
  || (profileName === 'main'
    ? process.env.EXPO_PUBLIC_API_URL || publicFileValues.EXPO_PUBLIC_API_URL
    : undefined)
  || profile.defaultApiUrl);
const environment = {
  ...process.env,
  MEMORYPAL_BUILD_PROFILE: profileName,
  MEMORYPAL_FRONTEND_BASE_URL: profile.baseUrl,
  EXPO_PUBLIC_API_URL: apiUrl,
};
const allowedMemoryPalVariables = new Set([
  profile.apiVariable,
  'MEMORYPAL_BUILD_PROFILE',
  'MEMORYPAL_FRONTEND_BASE_URL',
].map((name) => name.toUpperCase()));
for (const name of Object.keys(environment)) {
  if (/^MEMORYPAL_/i.test(name) && !allowedMemoryPalVariables.has(name.toUpperCase())) {
    delete environment[name];
  }
}
const result = spawnSync(
  executable,
  ['expo', 'export', '--clear', '--platform', 'web', '--output-dir', profile.outputDir],
  {
    cwd: root,
    env: environment,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  },
);
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);

const output = resolve(root, profile.outputDir);
if (!existsSync(resolve(output, 'index.html'))) {
  throw new Error(`Frontend build did not create ${profile.outputDir}/index.html`);
}
writeFileSync(
  resolve(output, 'deployment-profile.json'),
  `${JSON.stringify({ profile: profileName, baseUrl: profile.baseUrl, apiUrl }, null, 2)}\n`,
  'utf8',
);
