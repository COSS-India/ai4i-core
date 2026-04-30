/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  images: {
    domains: ["localhost", "api-gateway-service"],
  },
  // Note: NEXT_PUBLIC_* variables from .env files are automatically exposed by Next.js
  // No need to manually set them in the env object - that can cause conflicts
  // If NEXT_PUBLIC_API_URL is not set in .env, the code will use the fallback in api.ts
  output: "standalone",
  compress: true,
};

module.exports = nextConfig;
