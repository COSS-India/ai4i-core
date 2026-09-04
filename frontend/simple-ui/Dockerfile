# syntax=docker/dockerfile:1
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

COPY src/ ./src/
COPY public/ ./public/
COPY package.json next.config.js tsconfig.json ./

# Browser-facing URLs and ENABLED_TASK_TYPES are NO LONGER build-args.
# They are read at runtime from the pod env / ConfigMap (see /api/config and
# src/config/runtimeConfig.ts). Rebuild is not required to change them.
#
# Remaining NEXT_PUBLIC_* below are API keys still inlined at build via
# BuildKit secrets (not ConfigMap).
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

# API keys are injected via BuildKit secret mounts so they are never persisted
# in image layers or visible via `docker inspect` / `docker history`.
# Next.js statically inlines NEXT_PUBLIC_* values into the client JS bundle —
# these are not server-side credentials, but keeping them out of image metadata
# follows least-privilege and satisfies docker:S6472.
# Build with: --secret id=NEXT_PUBLIC_API_KEY,env=NEXT_PUBLIC_API_KEY (etc.)
RUN --mount=type=secret,id=NEXT_PUBLIC_API_KEY \
    --mount=type=secret,id=NEXT_PUBLIC_ASR_API_KEY \
    --mount=type=secret,id=NEXT_PUBLIC_TTS_API_KEY \
    --mount=type=secret,id=NEXT_PUBLIC_NMT_API_KEY \
    --mount=type=secret,id=NEXT_PUBLIC_PIPELINE_API_KEY \
    --mount=type=secret,id=NEXT_PUBLIC_MODEL_MANAGEMENT_API_KEY \
    export NEXT_PUBLIC_API_KEY=$(cat /run/secrets/NEXT_PUBLIC_API_KEY 2>/dev/null || echo "") \
    && export NEXT_PUBLIC_ASR_API_KEY=$(cat /run/secrets/NEXT_PUBLIC_ASR_API_KEY 2>/dev/null || echo "") \
    && export NEXT_PUBLIC_TTS_API_KEY=$(cat /run/secrets/NEXT_PUBLIC_TTS_API_KEY 2>/dev/null || echo "") \
    && export NEXT_PUBLIC_NMT_API_KEY=$(cat /run/secrets/NEXT_PUBLIC_NMT_API_KEY 2>/dev/null || echo "") \
    && export NEXT_PUBLIC_PIPELINE_API_KEY=$(cat /run/secrets/NEXT_PUBLIC_PIPELINE_API_KEY 2>/dev/null || echo "") \
    && export NEXT_PUBLIC_MODEL_MANAGEMENT_API_KEY=$(cat /run/secrets/NEXT_PUBLIC_MODEL_MANAGEMENT_API_KEY 2>/dev/null || echo "") \
    && npm run build

# ---------------- Stage 3: Runner ----------------
FROM node:18-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
# Allow connections from all network interfaces (required for Docker)
ENV HOSTNAME=0.0.0.0
# Runtime ConfigMap keys (override per env). Prefer these names; legacy
# NEXT_PUBLIC_* equivalents are still accepted by runtimeConfig.ts.
# Default llm so Service Management / Usage Dashboard stay LLM-only when the
# ConfigMap omits the key.
ENV ENABLED_TASK_TYPES=llm
ENV PLATFORM_NAME="AI4I Orchestrate"
# ENV API_URL=
# ENV TELEMETRY_SERVICE_URL=

RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

COPY --from=builder --chown=root:root --chmod=755 /app/public ./public
COPY --from=builder --chown=root:root --chmod=755 /app/.next/standalone ./
COPY --from=builder --chown=root:root --chmod=755 /app/.next/static ./.next/static

# Fix the standalone server.js to use HOSTNAME env var instead of hardcoded 'localhost'
# This is needed because Next.js 13.1.x standalone builds hardcode hostname: 'localhost'
RUN sed -i "s/hostname: 'localhost'/hostname: process.env.HOSTNAME || '0.0.0.0'/g" server.js

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
