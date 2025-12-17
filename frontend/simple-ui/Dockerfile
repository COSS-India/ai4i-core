# Multi-stage Dockerfile for Next.js application (monorepo-safe)

# ---------------- Stage 1: Dependencies ----------------
FROM node:18-alpine AS deps
WORKDIR /app

# Alpine compatibility
RUN apk update && apk add --no-cache libc6-compat

# ✅ FIX: copy package files relative to build context
COPY package.json package-lock.json ./

# Install dependencies
RUN npm ci

# ---------------- Stage 2: Builder ----------------
FROM node:18-alpine AS builder
WORKDIR /app

# Copy node_modules from deps stage
COPY --from=deps /app/node_modules ./node_modules

# ✅ FIX: copy source code relative to build context
COPY . .

# Build-time environment variables
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

# Build Next.js app
RUN npm run build

# ---------------- Stage 3: Runner ----------------
FROM node:18-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000

# Create non-root user
RUN addgroup --system --gid 1001 nodejs \
  && adduser --system --uid 1001 nextjs

# Copy runtime artifacts
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/api/health', r => process.exit(r.statusCode === 200 ? 0 : 1))"

CMD ["node", "server.js"]
