import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('./dist', import.meta.url)));
const port = Number(process.env.MEMORYPAL_ADMIN_PORT || process.env.PORT || 8082);
const prefix = '/api_memoripal/project3/manage';
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
  console.error('관리자 빌드가 없습니다. 먼저 npm run build를 실행하세요.');
  process.exit(1);
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
      "img-src 'self' data:; font-src 'self' data:; connect-src 'self' " +
      'http://127.0.0.1:8000 http://localhost:8000 https://developark.duckdns.org; ' +
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
