/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  images: {
    domains: ["localhost", "api-gateway-service"],
  },
  env: {
    // For production builds, set NEXT_PUBLIC_API_URL at build time
    // (for example, to "https://dev.ai4inclusion.org").
    // For local development, defaults to http://localhost:8080
    // Note: NEXT_PUBLIC_* variables are automatically exposed by Next.js,
    // but we explicitly set it here to ensure it's available.
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || (process.env.NODE_ENV === 'development' ? 'http://localhost:8080' : ''),
  },
  output: "standalone",
  compress: true,
};

module.exports = nextConfig;
