"""
get_refresh_token.py
────────────────────
Run this ONCE on your Windows PC to get your Spotify refresh token.
The refresh token never expires (unless revoked), so you only need to
do this once and then store it as a GitHub Secret.

Usage:
    python get_refresh_token.py
"""

import webbrowser
import urllib.parse
import urllib.request
import http.server
import threading
import base64
import json
import sys

print("=" * 60)
print("  ARIA 90s Bot — Spotify Refresh Token Setup")
print("=" * 60)
print()

CLIENT_ID     = input("Paste your Spotify Client ID:     ").strip()
CLIENT_SECRET = input("Paste your Spotify Client Secret: ").strip()
print()

if not CLIENT_ID or not CLIENT_SECRET:
    print("Both fields are required. Exiting.")
    sys.exit(1)

REDIRECT_URI = "http://127.0.0.1:8888/callback"

# ── Local HTTP server to catch the OAuth callback ───────────────────────────
auth_code = None
server_done = threading.Event()


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        if "code" in params:
            auth_code = params["code"][0]
            body = b"""
            <html><body style="font-family:sans-serif;padding:40px;text-align:center">
            <h2 style="color:#1DB954">&#10003; Authorised!</h2>
            <p>You can close this tab and return to the terminal.</p>
            </body></html>"""
        else:
            body = b"""
            <html><body style="font-family:sans-serif;padding:40px;text-align:center">
            <h2 style="color:red">&#10007; No code received</h2>
            <p>Close this and try again.</p>
            </body></html>"""

        self.wfile.write(body)
        server_done.set()

    def log_message(self, *args):
        pass  # silence default request logging


server = http.server.HTTPServer(("localhost", 8888), OAuthHandler)
server_thread = threading.Thread(target=server.handle_request)
server_thread.daemon = True
server_thread.start()

# ── Open Spotify login in the browser ──────────────────────────────────────
scope = " ".join([
    "playlist-modify-public",
    "playlist-modify-private",
    "user-read-recently-played",
    "user-read-private",
])

auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
    "client_id":     CLIENT_ID,
    "response_type": "code",
    "redirect_uri":  REDIRECT_URI,
    "scope":         scope,
})

print("Opening your browser for Spotify login...")
print("(If it doesn't open, paste this URL into your browser manually)")
print(f"\n  {auth_url}\n")
webbrowser.open(auth_url)

print("Waiting for authorisation (up to 2 minutes)...")
server_done.wait(timeout=120)

if not auth_code:
    print("\nNo authorisation code received within 2 minutes.")
    print("Try running the script again.")
    sys.exit(1)

print("  Authorisation code received. Exchanging for tokens...")

# ── Exchange code for tokens ─────────────────────────────────────────────
creds   = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
payload = urllib.parse.urlencode({
    "grant_type":   "authorization_code",
    "code":         auth_code,
    "redirect_uri": REDIRECT_URI,
}).encode()

req = urllib.request.Request(
    "https://accounts.spotify.com/api/token",
    data=payload,
    headers={
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/x-www-form-urlencoded",
    },
)

try:
    response = urllib.request.urlopen(req)
    tokens   = json.loads(response.read())
except urllib.error.HTTPError as e:
    print(f"\nToken exchange failed: {e.read().decode()}")
    sys.exit(1)

refresh_token = tokens.get("refresh_token")
if not refresh_token:
    print("\nNo refresh token in response. Make sure your app has the correct scopes.")
    sys.exit(1)

print()
print("=" * 60)
print("  SUCCESS — copy the four values below into GitHub Secrets")
print("=" * 60)
print()
print(f"  Secret name : SPOTIFY_CLIENT_ID")
print(f"  Secret value: {CLIENT_ID}")
print()
print(f"  Secret name : SPOTIFY_CLIENT_SECRET")
print(f"  Secret value: {CLIENT_SECRET}")
print()
print(f"  Secret name : SPOTIFY_REFRESH_TOKEN")
print(f"  Secret value: {refresh_token}")
print()
print("=" * 60)
print("  Your ANTHROPIC_API_KEY is the 4th secret (see README).")
print("=" * 60)
print()
input("Press Enter to exit...")
