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
    // We intentionally avoid a localhost default here so that
    // production bundles don't hard-code http://localhost:8080.
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "",
  },
  output: "standalone",
  compress: true,
};

module.exports = nextConfig;
