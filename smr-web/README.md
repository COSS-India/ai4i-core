# SMR Web Interface

A simple web interface for testing the Smart Router TTS Service.

## Usage

1. Open `index.html` in a web browser
2. Fill in the form:
   - Select Routing Policy (Free, Paid, or Enterprise)
   - Select Source Language (English, Tamil, Hindi, Telugu, or Malayalam)
   - Select Gender (Female or Male)
   - Enter Sampling Rate (default: 22050)
   - Select Audio Format (WAV or MP3)
   - Enter text to convert to speech
3. Click "Execute" button
4. The audio will be generated and displayed in an audio player

## Requirements

- API Gateway running on http://localhost:8080
- All services (smart-router, policy-engine, tts-service) must be running
- Modern web browser with JavaScript enabled

## File Location

- HTML file: `~/SMR/ai4i-core/smr-web/index.html`
- Full path: `/home/gokulduraisamy/SMR/ai4i-core/smr-web/index.html`

## Opening the Page

You can open it using:
- Double-click the `index.html` file in your file manager
- Or use: `xdg-open ~/SMR/ai4i-core/smr-web/index.html`
- Or navigate to the file in your browser: `file:///home/gokulduraisamy/SMR/ai4i-core/smr-web/index.html`

## Running with HTTP Server (Recommended)

To avoid CORS issues, use the included Python HTTP server:

```bash
cd ~/SMR/ai4i-core/smr-web
python3 server.py
```

This will:
- Start a server on http://localhost:8001
- Automatically open the page in your browser
- Serve the HTML file with proper CORS headers

## Troubleshooting CORS Errors

If you see "Failed to fetch" errors:
1. Use the HTTP server (see above) instead of opening the HTML file directly
2. Or ensure Policy Engine is running: `docker compose ps policy-engine`
3. Check Policy Engine logs: `docker logs ai4v-policy-engine`
