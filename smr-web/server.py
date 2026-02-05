#!/usr/bin/env python3
"""
Simple HTTP server to serve the SMR web interface
This avoids CORS issues when opening HTML files directly
"""
import http.server
import socketserver
import webbrowser
import os
from pathlib import Path

PORT = 8001
DIRECTORY = Path(__file__).parent

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)
    
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

if __name__ == "__main__":
    os.chdir(DIRECTORY)
    
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}/index.html"
        print(f"🚀 SMR Web Interface Server")
        print(f"📡 Serving on: {url}")
        print(f"📁 Directory: {DIRECTORY}")
        print(f"\n✨ Opening browser...")
        print(f"⚠️  Press Ctrl+C to stop the server\n")
        
        try:
            webbrowser.open(url)
        except:
            print(f"⚠️  Could not open browser automatically")
            print(f"   Please open: {url}\n")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n\n🛑 Server stopped")
