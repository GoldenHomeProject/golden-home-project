# TikTok Sandbox Integration — Golden Home Project

Flask app that demonstrates the **Login Kit** (OAuth 2.0 + PKCE) and
**Content Posting API** (`video.upload` + `video.publish`) flows end to end,
for TikTok app review.

## App

- **App ID:** 7619346780731574293
- **Sandbox ID:** 7625706833369991175 (GHP Sandbox)
- **Client key:** `sbawxbvzpiy0a4uprg`
- **Redirect URI:** `http://localhost:5173/callback`
- **Scopes:** `user.info.basic`, `video.publish`, `video.upload`

## Run

```bash
pip install flask requests
export TIKTOK_CLIENT_KEY=sbawxbvzpiy0a4uprg
export TIKTOK_CLIENT_SECRET=***
python app.py
# open http://localhost:5173/
```

## Flow

1. **/** — Landing page, "Login with TikTok" button.
2. **/login** — Generates PKCE verifier/challenge, redirects to TikTok
   `/v2/auth/authorize/` with `response_type=code`.
3. **/callback** — Validates `state`, exchanges `code` + `code_verifier`
   at `/v2/oauth/token/` for an access token, fetches user info from
   `/v2/user/info/`, stores in session.
4. **/dashboard** — Shows authenticated user, upload form.
5. **/upload** — Implements the 3-step publish flow:
   - `POST /v2/post/publish/video/init/` with `post_info` + `source_info`
   - `PUT` video bytes to the returned `upload_url` with `Content-Range`
   - Poll `POST /v2/post/publish/status/fetch/` until
     `PUBLISH_COMPLETE` / `SEND_TO_USER_INBOX` / `FAILED`

## Sandbox configuration required

- Target user: authorized GHP TikTok account added under
  *Sandbox settings → Target Users*.
- Redirect URI `http://localhost:5173/callback` registered under the
  sandbox Login Kit config.

## Demo recording

The full browser flow (login → consent → callback → dashboard → upload →
publish status) is recorded as `tiktok_sandbox_demo.mp4` for submission.
