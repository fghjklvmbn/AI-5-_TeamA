import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, extname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const profiles = {
  main: { directory: 'dist-main', prefix: '/api_memoripal/manage' },
  project3: { directory: 'dist-project3', prefix: '/api_memoripal/project3/manage' },
};
const profileName = process.env.MEMORYPAL_BUILD_PROFILE || 'main';
const profile = profiles[profileName];
if (!profile) throw new Error(`Unsupported MEMORYPAL_BUILD_PROFILE: ${profileName}`);
const moduleRoot = dirname(fileURLToPath(import.meta.url));
const root = resolve(moduleRoot, process.env.MEMORYPAL_ADMIN_DIST || profile.directory);
const port = Number(process.env.MEMORYPAL_ADMIN_PORT || process.env.PORT || 8082);
const prefix = (process.env.MEMORYPAL_ADMIN_BASE_URL || profile.prefix).replace(/\/$/, '');
const mime = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

if (!existsSync(join(root, 'index.html'))) {
  console.error(`Admin ${profileName} build is missing: ${join(root, 'index.html')}`);
  process.exit(1);
}
const manifestPath = join(root, 'deployment-profile.json');
if (!existsSync(manifestPath)) {
  throw new Error(`Admin deployment manifest is missing: ${manifestPath}`);
}
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
if (manifest.profile !== profileName) {
  throw new Error(`Refusing mixed admin build: expected ${profileName}, got ${manifest.profile}`);
}
if (manifest.baseUrl !== `${prefix}/`) {
  throw new Error(`Refusing admin build with base URL ${manifest.baseUrl}; expected ${prefix}/`);
}
if (typeof manifest.apiUrl !== 'string' || !manifest.apiUrl.trim()) {
  throw new Error('Refusing admin build without a public API URL');
}
const connectSources = [
  "'self'",
  'http://127.0.0.1:8010',
  'http://localhost:8010',
];
try {
  const apiOrigin = new URL(String(manifest.apiUrl)).origin;
  if (apiOrigin.startsWith('http://') || apiOrigin.startsWith('https://')) {
    connectSources.push(apiOrigin);
  }
} catch {
  // Relative API URLs are covered by 'self'.
}

function safeFile(pathname) {
  let clean = decodeURIComponent(pathname.split('?')[0]);
  if (clean === prefix) clean = '/';
  else if (clean.startsWith(`${prefix}/`)) clean = clean.slice(prefix.length);
  const candidate = normalize(join(root, clean.replace(/^[/\\]+/, '')));
  if (candidate !== root && !candidate.startsWith(`${root}${sep}`)) return null;
  if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  return join(root, 'index.html');
}

createServer((request, response) => {
  try {
    const file = safeFile(request.url || '/');
    if (!file) {
      response.writeHead(403).end('Forbidden');
      return;
    }
    response.setHeader('Content-Type', mime[extname(file)] || 'application/octet-stream');
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('X-Frame-Options', 'DENY');
    response.setHeader('Referrer-Policy', 'same-origin');
    response.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
    response.setHeader(
      'Content-Security-Policy',
      "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
      "img-src 'self' data:; font-src 'self' data:; connect-src " +
      `${[...new Set(connectSources)].join(' ')}; ` +
      "object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    );
    response.setHeader('Cache-Control', file.endsWith('index.html') ? 'no-store' : 'public, max-age=31536000, immutable');
    createReadStream(file).pipe(response);
  } catch {
    response.writeHead(400).end('Bad request');
  }
}).listen(port, '0.0.0.0', () => {
  console.log(`MemoryPal admin: http://127.0.0.1:${port}${prefix}/`);
});
