# Multi-stage Dockerfile for Next.js application optimized for production

# Stage 1: Dependencies
FROM node:18-alpine AS deps
WORKDIR /app

# Install libc6-compat for Alpine compatibility
RUN apk update && apk add --no-cache libc6-compat

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci --only=production

# Stage 2: Builder
FROM node:18-alpine AS builder
WORKDIR /app

# Copy node_modules from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy source code
COPY . .

# Set environment variables for build
# - NEXT_PUBLIC_API_URL is provided as a build-arg so we can point the UI
#   either at Kong (preferred) or directly at the API gateway.
# - Service-specific API keys are provided as build-args from .env file
ARG NEXT_PUBLIC_API_URL=""
ARG NEXT_PUBLIC_API_KEY=""
ARG NEXT_PUBLIC_ASR_API_KEY=""
ARG NEXT_PUBLIC_TTS_API_KEY=""
ARG NEXT_PUBLIC_NMT_API_KEY=""
ARG NEXT_PUBLIC_PIPELINE_API_KEY=""
ARG NEXT_PUBLIC_MODEL_MANAGEMENT_API_KEY=""
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_API_KEY=${NEXT_PUBLIC_API_KEY}
ENV NEXT_PUBLIC_ASR_API_KEY=${NEXT_PUBLIC_ASR_API_KEY}
ENV NEXT_PUBLIC_TTS_API_KEY=${NEXT_PUBLIC_TTS_API_KEY}
ENV NEXT_PUBLIC_NMT_API_KEY=${NEXT_PUBLIC_NMT_API_KEY}
ENV NEXT_PUBLIC_PIPELINE_API_KEY=${NEXT_PUBLIC_PIPELINE_API_KEY}
ENV NEXT_PUBLIC_MODEL_MANAGEMENT_API_KEY=${NEXT_PUBLIC_MODEL_MANAGEMENT_API_KEY}
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# Build the application
RUN npm run build

# Stage 3: Runner
FROM node:18-alpine AS runner
WORKDIR /app

# Set environment variables
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Create non-root user
RUN addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

# Copy public assets
COPY --from=builder /app/public ./public

# Copy standalone build
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Switch to non-root user
USER nextjs

# Expose port
EXPOSE 3000

# Set port environment variable
ENV PORT=3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/api/health', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})"

# Start the application
CMD ["node", "server.js"]

