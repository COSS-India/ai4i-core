# ---------------- Stage 1: Dependencies ----------------
FROM node:18-alpine AS deps
WORKDIR /app

RUN apk update && apk add --no-cache libc6-compat

# ✅ Correct: files are directly in the build context
COPY package.json package-lock.json ./

RUN npm ci

# ---------------- Stage 2: Builder ----------------
FROM node:18-alpine AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules

# ✅ Correct: copy everything from context
COPY . .

ARG NEXT_PUBLIC_API_URL=""
ARG NEXT_PUBLIC_API_KEY=""
ARG NEXT_PUBLIC_ASR_API_KEY=""
ARG NEXT_PUBLIC_TTS_API_KEY=""
ARG NEXT_PUBLIC_NMT_API_KEY=""
ARG NEXT_PUBLIC_PIPELINE_API_KEY=""
ARG NEXT_PUBLIC_MODEL_MANAGEMENT_API_KEY=""
ARG NEXT_PUBLIC_TELEMETRY_SERVICE_URL=""

ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_API_KEY=${NEXT_PUBLIC_API_KEY}
ENV NEXT_PUBLIC_ASR_API_KEY=${NEXT_PUBLIC_ASR_API_KEY}
ENV NEXT_PUBLIC_TTS_API_KEY=${NEXT_PUBLIC_TTS_API_KEY}
ENV NEXT_PUBLIC_NMT_API_KEY=${NEXT_PUBLIC_NMT_API_KEY}
ENV NEXT_PUBLIC_PIPELINE_API_KEY=${NEXT_PUBLIC_PIPELINE_API_KEY}
ENV NEXT_PUBLIC_MODEL_MANAGEMENT_API_KEY=${NEXT_PUBLIC_MODEL_MANAGEMENT_API_KEY}
ENV NEXT_PUBLIC_TELEMETRY_SERVICE_URL=${NEXT_PUBLIC_TELEMETRY_SERVICE_URL}
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN npm run build

# ---------------- Stage 3: Runner ----------------
FROM node:18-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
# Allow connections from all network interfaces (required for Docker)
ENV HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Fix the standalone server.js to use HOSTNAME env var instead of hardcoded 'localhost'
# This is needed because Next.js 13.1.x standalone builds hardcode hostname: 'localhost'
RUN sed -i "s/hostname: 'localhost'/hostname: process.env.HOSTNAME || '0.0.0.0'/g" server.js

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
