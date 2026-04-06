"""
TikTok Sandbox Integration for Golden Home Project.

Implements TikTok Login Kit (OAuth 2.0 + PKCE) and Content Posting API
(video.upload + video.publish) for sandbox app review demonstration.

Flow:
  1. GET  /                -> Landing page with "Login with TikTok" button
  2. GET  /login           -> Redirects user to TikTok authorize endpoint
  3. GET  /callback        -> Receives OAuth code, exchanges for access token,
                              fetches user info, stores token in session
  4. GET  /dashboard       -> Shows authenticated user info + upload form
  5. POST /upload          -> Uploads a local video via Content Posting API
                              (init -> PUT binary -> poll status)

Run:
  export TIKTOK_CLIENT_KEY=sbawxbvzpiy0a4uprg
  export TIKTOK_CLIENT_SECRET=B1PRuB9aeq31RQvl5ATZg0h4mLoUDjkN
  python app.py
  # then visit http://localhost:5173/
"""
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, render_template_string, request, session, url_for

CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "sbawxbvzpiy0a4uprg")
CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "B1PRuB9aeq31RQvl5ATZg0h4mLoUDjkN")
REDIRECT_URI = os.environ.get("TIKTOK_REDIRECT_URI", "http://localhost:5173/callback")
SCOPES = "user.info.basic,video.publish,video.upload"

AUTH_BASE = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
VIDEO_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
VIDEO_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)


# ---------- Templates ----------

LANDING = """
<!doctype html>
<html><head><title>GHP TikTok Sandbox</title>
<style>
  body{font-family:Inter,system-ui,sans-serif;max-width:640px;margin:80px auto;padding:24px;background:#0a0a0a;color:#eee}
  h1{color:#f5a623}
  .btn{display:inline-block;background:#fe2c55;color:#fff;padding:14px 28px;border-radius:8px;
       text-decoration:none;font-weight:600;margin-top:24px}
  .card{background:#1a1a1a;border:1px solid #333;border-radius:12px;padding:32px;margin-top:24px}
  code{background:#222;padding:2px 6px;border-radius:4px;font-size:.9em}
</style></head><body>
  <h1>Golden Home Project — TikTok Sandbox</h1>
  <div class="card">
    <p>This app demonstrates the Content Posting API integration for
       <b>Golden Home Project LLC</b>, an affiliate marketing platform that
       shares home product recommendations. The app publishes short-form
       product videos from our own account.</p>
    <p>Sign in with the authorized sandbox TikTok account to continue.</p>
    <a class="btn" href="/login">Login with TikTok</a>
  </div>
  <div class="card">
    <p><b>Configured credentials</b></p>
    <p>Client key: <code>{{ client_key }}</code><br>
       Redirect URI: <code>{{ redirect_uri }}</code><br>
       Scopes: <code>{{ scopes }}</code></p>
  </div>
</body></html>
"""

DASHBOARD = """
<!doctype html>
<html><head><title>GHP TikTok — Dashboard</title>
<style>
  body{font-family:Inter,system-ui,sans-serif;max-width:720px;margin:60px auto;padding:24px;background:#0a0a0a;color:#eee}
  h1,h2{color:#f5a623}
  .card{background:#1a1a1a;border:1px solid #333;border-radius:12px;padding:24px;margin-top:24px}
  .avatar{width:64px;height:64px;border-radius:50%;vertical-align:middle;margin-right:12px}
  .btn{background:#fe2c55;color:#fff;padding:12px 24px;border:0;border-radius:8px;font-weight:600;cursor:pointer}
  input,textarea{width:100%;padding:10px;background:#222;color:#eee;border:1px solid #444;border-radius:6px;margin-top:6px}
  label{display:block;margin-top:14px;font-weight:500}
  pre{background:#111;padding:12px;border-radius:6px;overflow:auto;font-size:.85em}
</style></head><body>
  <h1>Dashboard</h1>
  <div class="card">
    <img class="avatar" src="{{ user.avatar_url }}" alt="">
    <b>{{ user.display_name }}</b> (open_id: <code>{{ user.open_id[:12] }}…</code>)
  </div>

  <div class="card">
    <h2>Publish a video</h2>
    <form method="post" action="/upload" enctype="multipart/form-data">
      <label>Title / caption
        <input name="title" maxlength="150"
               value="Golden Home Project — sandbox test upload"></label>
      <label>Video file (MP4, &le; 50MB for sandbox)
        <input type="file" name="video" accept="video/mp4" required></label>
      <label>Privacy level
        <select name="privacy_level">
          <option value="SELF_ONLY">Only me (sandbox default)</option>
          <option value="MUTUAL_FOLLOW_FRIENDS">Friends</option>
          <option value="PUBLIC_TO_EVERYONE">Public</option>
        </select></label>
      <p style="margin-top:20px"><button class="btn" type="submit">Upload & Publish</button></p>
    </form>
  </div>
  {% if last_result %}
  <div class="card">
    <h2>Last API response</h2>
    <pre>{{ last_result }}</pre>
  </div>
  {% endif %}
</body></html>
"""


# ---------- PKCE helpers ----------

def _pkce_pair():
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = hashlib.sha256(verifier.encode()).digest()
    import base64
    challenge_b64 = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
    return verifier, challenge_b64


# ---------- Routes ----------

@app.route("/")
def index():
    return render_template_string(
        LANDING, client_key=CLIENT_KEY, redirect_uri=REDIRECT_URI, scopes=SCOPES
    )


@app.route("/login")
def login():
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    session["oauth_state"] = state
    session["pkce_verifier"] = verifier
    params = {
        "client_key": CLIENT_KEY,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return redirect(f"{AUTH_BASE}?{urlencode(params)}")


@app.route("/callback")
def callback():
    if request.args.get("state") != session.get("oauth_state"):
        return "State mismatch", 400
    code = request.args.get("code")
    if not code:
        return f"OAuth error: {request.args.get('error_description', 'no code')}", 400

    # Exchange code for access token
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": session.get("pkce_verifier", ""),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    token_data = resp.json()
    if "access_token" not in token_data:
        return f"Token exchange failed: {token_data}", 400

    session["access_token"] = token_data["access_token"]
    session["open_id"] = token_data.get("open_id")
    session["refresh_token"] = token_data.get("refresh_token")

    # Fetch user info
    info = requests.get(
        USER_INFO_URL,
        params={"fields": "open_id,union_id,avatar_url,display_name"},
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
        timeout=30,
    ).json()
    session["user"] = info.get("data", {}).get("user", {})
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if "access_token" not in session:
        return redirect(url_for("index"))
    return render_template_string(
        DASHBOARD, user=session.get("user", {}), last_result=session.pop("last_result", None)
    )


@app.route("/upload", methods=["POST"])
def upload():
    if "access_token" not in session:
        return redirect(url_for("index"))

    title = request.form.get("title", "GHP test upload")
    privacy = request.form.get("privacy_level", "SELF_ONLY")
    file = request.files["video"]
    video_bytes = file.read()
    total_size = len(video_bytes)

    token = session["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Step 1: init upload
    init_body = {
        "post_info": {
            "title": title,
            "privacy_level": privacy,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": total_size,
            "chunk_size": total_size,
            "total_chunk_count": 1,
        },
    }
    init_resp = requests.post(VIDEO_INIT_URL, headers=headers, json=init_body, timeout=30).json()
    if init_resp.get("error", {}).get("code") not in ("ok", None):
        session["last_result"] = json.dumps(init_resp, indent=2)
        return redirect(url_for("dashboard"))

    upload_url = init_resp["data"]["upload_url"]
    publish_id = init_resp["data"]["publish_id"]

    # Step 2: PUT binary
    put_resp = requests.put(
        upload_url,
        data=video_bytes,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{total_size - 1}/{total_size}",
        },
        timeout=120,
    )

    # Step 3: poll status
    status = None
    for _ in range(20):
        time.sleep(2)
        s = requests.post(
            VIDEO_STATUS_URL, headers=headers, json={"publish_id": publish_id}, timeout=30
        ).json()
        status = s
        state = s.get("data", {}).get("status")
        if state in ("PUBLISH_COMPLETE", "FAILED", "SEND_TO_USER_INBOX"):
            break

    session["last_result"] = json.dumps(
        {"init": init_resp, "put_status": put_resp.status_code, "final": status}, indent=2
    )
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    print(f"Starting GHP TikTok sandbox on {REDIRECT_URI.rsplit('/', 1)[0]}")
    print(f"Client key: {CLIENT_KEY}")
    app.run(host="0.0.0.0", port=5173, debug=False)
