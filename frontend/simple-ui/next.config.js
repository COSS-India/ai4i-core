/** @type {import('next').NextConfig} */

/**
 * Allowed API/backend origins for CSP connect-src. Restricts fetch/XHR/WebSocket to these domains.
 * Uses NEXT_PUBLIC_* env vars when set (e.g. at build time); falls back to localhost for dev.
 */
function getAllowedConnectOrigins() {
  const origins = new Set(["'self'"]);
  const urls = [
    process.env.NEXT_PUBLIC_API_URL,
    process.env.NEXT_PUBLIC_TELEMETRY_SERVICE_URL,
    process.env.NEXT_PUBLIC_JAEGER_URL,
    process.env.NEXT_PUBLIC_ASR_STREAM_URL,
    process.env.NEXT_PUBLIC_TTS_STREAM_URL,
  ];
  urls.forEach((url) => {
    if (url) {
      try {
        origins.add(new URL(url).origin);
      } catch (_) {
        // ignore invalid URLs
      }
    }
  });
  // Dev fallbacks when env vars are not set (e.g. next dev without .env)
  if (origins.size <= 1) {
    [
      "http://localhost:9000",
      "http://localhost:8084",
      "http://localhost:16686",
      "ws://localhost:8087",
      "ws://localhost:8088",
    ].forEach((o) => origins.add(o));
  }
  return [...origins].join(" ");
}

/**
 * Security headers applied to all responses.
 * See: https://nextjs.org/docs/app/building-your-application/configuring/security-headers
 */
function getSecurityHeaders() {
  const connectSrc = getAllowedConnectOrigins();
  return [
    // Prevent clickjacking: disallow embedding in iframes (use SAMEORIGIN if you need same-origin frames)
    { key: 'X-Frame-Options', value: 'DENY' },
    // Prevent MIME-type sniffing; force browser to respect declared Content-Type
    { key: 'X-Content-Type-Options', value: 'nosniff' },
    // Legacy XSS filter (still useful for older browsers)
    { key: 'X-XSS-Protection', value: '1; mode=block' },
    // Control referrer information sent on navigation (strict-origin-when-cross-origin is a good default)
    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
    // Restrict browser features (camera, mic, geolocation, etc.) to reduce attack surface
    {
      key: 'Permissions-Policy',
      value: 'camera=(), microphone=(), geolocation=(), interest-cohort=()',
    },
    // Disable DNS prefetch by default to reduce information leakage (enable only for trusted origins if needed)
    { key: 'X-DNS-Prefetch-Control', value: 'off' },
    // Content Security Policy: restrict sources for scripts, styles, images, and API connections
    {
      key: 'Content-Security-Policy',
      value: [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "img-src 'self' data: blob: https: http:",
        "font-src 'self' data: https://fonts.gstatic.com",
        `connect-src ${connectSrc}`,
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
      ].join('; '),
    },
  ];
}

const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  transpilePackages: ['crypto-js'],
  images: {
    domains: ['localhost', 'api-gateway-service'],
  },
  // Note: NEXT_PUBLIC_* variables from .env files are automatically exposed by Next.js
  // No need to manually set them in the env object - that can cause conflicts
  // If NEXT_PUBLIC_API_URL is not set in .env, the code will use the fallback in api.ts
  output: 'standalone',
  compress: true,

  // --- Security ---
  // Do not expose X-Powered-By: Next.js to reduce fingerprinting
  poweredByHeader: false,

  async headers() {
    const headers = [...getSecurityHeaders()];

    // HSTS: enforce HTTPS in production only (skip in dev to avoid localhost issues)
    if (process.env.NODE_ENV === 'production') {
      headers.push({
        key: 'Strict-Transport-Security',
        value: 'max-age=31536000; includeSubDomains; preload',
      });
    }

    return [
      {
        source: '/:path*',
        headers,
      },
    ];
  },
};

module.exports = nextConfig;
