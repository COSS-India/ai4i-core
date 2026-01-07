# Jaeger UI Customization for Non-Technical Users

## Overview
This document describes how to customize Jaeger UI labels and visibility to make traces more understandable for non-technical users. Since Jaeger UI runs as a standard container, we have two options:

## Option 1: Custom Jaeger UI Build (Recommended for Production)

### Steps:
1. **Fork/Customize Jaeger UI Source Code**
   - Clone Jaeger UI repository: https://github.com/jaegertracing/jaeger-ui
   - Make minimal changes to label text only (no logic changes)

2. **Key Files to Modify:**
   - `packages/jaeger-ui/src/model/trace-viewer.tsx` - Main trace viewer component
   - `packages/jaeger-ui/src/components/TracePage/TraceTimelineViewer/index.tsx` - Timeline labels
   - `packages/jaeger-ui/src/components/TracePage/TracePageHeader/TracePageHeader.tsx` - Header labels
   - `packages/jaeger-ui/src/components/TracePage/TracePageHeader/TraceStatisticsHeader.tsx` - Statistics labels

3. **Label Changes:**
   ```typescript
   // Replace "Trace" with "Request Flow"
   // Replace "Span" with "Step"
   // Replace "Duration" with "Time Taken"
   ```

4. **Hide Advanced Features:**
   - Comment out or conditionally hide "Compare" tab
   - Hide advanced filter UI elements
   - Make Trace ID search optional (behind a toggle)

5. **Add Tooltips:**
   - Add tooltips explaining timeline bars: "Longer bar = more time spent"
   - Add tooltip for "Step": "A step represents a single operation in the request flow"

6. **Build Custom Image:**
   ```dockerfile
   FROM node:18-alpine AS builder
   WORKDIR /app
   COPY . .
   RUN npm install && npm run build

   FROM nginx:alpine
   COPY --from=builder /app/packages/jaeger-ui/build /usr/share/nginx/html
   ```

7. **Update docker-compose.yml:**
   ```yaml
   jaeger:
     image: your-registry/custom-jaeger-ui:latest
     # ... rest of config
   ```

## Option 2: Browser Extension / Proxy (Quick Solution)

### Create a Browser Extension:
1. Intercept Jaeger UI API calls
2. Transform span names on-the-fly
3. Inject CSS to hide advanced features
4. Inject JavaScript to add tooltips

### Or Use a Reverse Proxy:
1. Create a simple proxy service
2. Intercept HTML responses
3. Use regex to replace labels
4. Inject custom CSS/JS

## Option 3: Minimal Changes (Current Implementation)

The current implementation focuses on **instrumentation changes** which make traces more readable even with standard Jaeger UI:

### What We've Done:
1. ✅ **Business-friendly span names:**
   - `ocr.inference` → `OCR Request Processing`
   - `ocr.process_batch` → `OCR Processing`
   - `ocr.triton_batch` → `AI Model Processing`
   - `ocr.build_response` → `Response Construction`
   - `auth.validate` → `Authentication Validation`
   - `request.authorize` → `Request Authorization`

2. ✅ **Collapsed noisy spans:**
   - Removed `ocr.resolve_images` loop span
   - Removed individual `ocr.resolve_image` spans
   - Removed `triton.inference` nested span
   - Removed `auth.decision.*` decision spans
   - Removed `auth.validate_api_key` nested span

3. ✅ **Added business-friendly attributes:**
   - `purpose` - Plain-English description
   - `user_visible` - true/false
   - `impact_if_slow` - What happens if slow
   - `owner` - Team responsible

### Result:
Even with standard Jaeger UI, traces are now much more readable because:
- Span names are in plain English
- Fewer nested spans (less noise)
- Business context is available in attributes

## Testing

1. **Start services:**
   ```bash
   docker-compose up -d
   ```

2. **Make an OCR request:**
   ```bash
   curl -X POST http://localhost:8099/api/v1/ocr/inference \
     -H "Content-Type: application/json" \
     -d '{"image": [{"imageContent": "base64..."}], "config": {"serviceId": "ocr"}}'
   ```

3. **View in Jaeger UI:**
   - Open http://localhost:16686
   - Search for service: `ocr-service`
   - View trace - you should see business-friendly span names

## Future Enhancements

If you want to fully customize Jaeger UI:
1. Follow Option 1 to create custom build
2. Or use Option 2 for quick browser-based solution
3. Consider contributing changes back to Jaeger UI project

