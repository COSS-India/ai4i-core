import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Next.js middleware to set security headers on every response.
 *
 * The headers() config in next.config.js is NOT applied by the
 * standalone server.js (used in production Docker builds).
 * Middleware IS included in standalone builds, so we set headers here.
 */
export function middleware(request: NextRequest) {
  const response = NextResponse.next();

  const connectOrigins = getConnectOrigins();

  const csp = [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "img-src 'self' data: blob: https: http:",
    "media-src 'self' blob:",
    "font-src 'self' data: https://fonts.gstatic.com",
    `connect-src ${connectOrigins}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ');

  response.headers.set('Content-Security-Policy', csp);
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('X-XSS-Protection', '1; mode=block');
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  response.headers.set('Permissions-Policy', 'camera=(), microphone=(self), geolocation=(), interest-cohort=()');
  response.headers.set('X-DNS-Prefetch-Control', 'off');

  return response;
}

function getConnectOrigins(): string {
  const origins = new Set(["'self'"]);
  const urls = [
    process.env.NEXT_PUBLIC_API_URL,
    process.env.NEXT_PUBLIC_TELEMETRY_SERVICE_URL,
    process.env.NEXT_PUBLIC_JAEGER_URL,
    process.env.NEXT_PUBLIC_ASR_STREAM_URL,
    process.env.NEXT_PUBLIC_TTS_STREAM_URL,
  ];
  for (const url of urls) {
    if (url) {
      try {
        origins.add(new URL(url).origin);
      } catch {
        // ignore invalid URLs
      }
    }
  }
  if (origins.size <= 1) {
    origins.add('http://localhost:9000');
    origins.add('http://localhost:8084');
    origins.add('http://localhost:16686');
    origins.add('ws://localhost:8087');
    origins.add('ws://localhost:8088');
  }
  return [...origins].join(' ');
}

// Apply to all routes except static assets
export const config = {
  matcher: '/((?!_next/static|_next/image|favicon.ico).*)',
};
