# Proxyman Setup for Dabble API

Use this guide to capture the exact headers and tokens the Dabble iOS app sends, then wire them into the scraper.

## 1. Install and configure Proxyman

1. Install [Proxyman](https://proxyman.io/) on your Mac.
2. Open **Certificate** → install the Proxyman root CA on your Mac (required for HTTPS decryption).
3. On your iPhone: **Settings → Wi-Fi → (your network) → Configure Proxy → Manual**
   - Server: your Mac’s local IP (shown in Proxyman)
   - Port: `9090` (default)
4. On iPhone: visit `proxy.man/ssl` in Safari and install the Proxyman certificate.
5. **Settings → General → About → Certificate Trust Settings** → enable full trust for Proxyman.

## 2. Capture Dabble traffic

1. Open Proxyman and confirm traffic appears when you browse on the phone.
2. Open the **Dabble** app and log in normally.
3. In Proxyman, filter by domain: `dabble.com` or `api.dabble.com`.
4. Find these requests (names may vary slightly):
   - **Sign-in:** `POST https://api.dabble.com/sign-in`
   - **Schedule / board:** `GET .../search/dfs/competitions/.../props`
   - **Game detail:** `GET .../frontend-api/sport-fixtures/details/{id}`

## 3. Export sign-in details (fix 401 if needed)

1. Click the **sign-in** request → **Request** tab.
2. Note the **JSON body** field names and format (e.g. `username` vs phone format).
3. Copy **all request headers** (not just User-Agent). Common ones:
   - `User-Agent`
   - `Content-Type`
   - `Accept`
   - `Accept-Language`
   - `Accept-Encoding`
4. Update `backend/config/api_headers.py` → `DABBLE_BASE_HEADERS` with any headers the app sends that we are missing.
5. Update `backend/.env` or `backend/config/.env`:
   ```env
   DABBLE_USERNAME=+1XXXXXXXXXX
   DABBLE_PASSWORD=your_password
   ```
   Use the **exact** phone format shown in Proxyman (often E.164 with `+1`).

## 4. Capture Bearer token (dev fallback)

When sign-in from the script still fails, use a token from the app:

1. In Proxyman, open any **authenticated** Dabble API request (schedule or fixture detail).
2. Copy the full `Authorization` header value: `Bearer eyJ...`
3. Paste **only the token part** (without `Bearer `) into `.env`:
   ```env
   DABBLE_BEARER_TOKEN=eyJraWQiOi...
   ```
4. Run the engine — it will skip sign-in and use this token until it expires.

To refresh: log out/in on the app or wait for expiry, then capture a new token.

## 5. Verify schedule and fixture URLs

1. Open a successful **schedule** request in Proxyman.
2. Confirm the URL matches `DABBLE_SCHEDULE_URL` in `backend/config/api_headers.py`.
3. Open a **fixture detail** request and confirm the path pattern matches `DABBLE_FIXTURE_DETAIL_URL`.

If competition IDs or query params changed, update `api_headers.py` from the captured URL.

## 6. Run the engine

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
python -m scrapers.dfs.dabble_engine
```

Expected log flow:

- `Authenticating with Dabble...` **or** `Using DABBLE_BEARER_TOKEN from environment`
- `Found N total active NBA games`
- `pipeline complete: saved N props to data/archive/dabble/dabble_master_board.json`

## 7. Security reminders

- Never commit `.env` or paste tokens into source code.
- Rotate passwords/tokens if they were ever committed or shared.
- `DABBLE_BEARER_TOKEN` is for local dev only; production should use programmatic sign-in once credentials work.
