#!/usr/bin/env python3
"""
Simple HTTP server for serving the Boulder Web App v2 frontend
"""
import http.server
import socketserver
import os
from pathlib import Path

# Get port from environment variable (Railway sets this)
PORT = int(os.getenv("PORT", 3000))

# Change to the directory containing the frontend files
frontend_dir = Path(__file__).parent
os.chdir(frontend_dir)

class CustomHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add CORS headers for API calls
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

if __name__ == "__main__":
    print(f"🚀 Starting Boulder Web App v2 Frontend Server on port {PORT}")
    print(f"📁 Serving files from: {frontend_dir}")
    print(f"🌐 Frontend will be available at: http://localhost:{PORT}")
    
    with socketserver.TCPServer(("", PORT), CustomHTTPRequestHandler) as httpd:
        print(f"✅ Server running on port {PORT}")
        httpd.serve_forever()
