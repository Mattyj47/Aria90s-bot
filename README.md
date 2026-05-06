# ARIA 90s Bot

Automatically creates a new Spotify playlist every time you finish the current one. Each playlist is the real Australian ARIA Top 10 from a randomly selected week somewhere between January 1990 and December 1999. Weeks are never repeated until all 521 have been used. Playlists that are more than 75% similar to a recent one are skipped.

Runs entirely on GitHub Actions — no computer needs to be on.

---

## How it works

Every 20 minutes, GitHub Actions runs the bot. It:

1. Gets a fresh Spotify access token using your stored refresh token
2. Checks your `recently-played` history to see if you've finished the current playlist
3. If finished (or no playlist exists yet): picks a random week from the 90s, asks Claude for the historically accurate ARIA Top 10, searches Spotify for each track, and creates a new private playlist in your account
4. Saves state back to `state.json` in this repo so history persists

---

## One-time setup (takes about 10 minutes)

### Step 1 — Create a Spotify Developer App

1. Go to https://developer.spotify.com/dashboard and log in with your Spotify account
2. Click **Create app**
3. Fill in:
   - App name: `ARIA 90s Bot` (or anything)
   - App description: anything
   - Website: `http://localhost`
   - Redirect URI: `http://127.0.0.1:8888/callback` ← **exact, including trailing nothing**
4. Tick **Web API**, then click **Save**
5. On the app page, click **Settings** and copy your **Client ID** and **Client Secret** — you'll need both shortly

### Step 2 — Get your Spotify Refresh Token (Windows)

This is a one-time step. The refresh token never expires.

1. Make sure Python is installed on your PC. Open a terminal and run `python --version` to check. If you don't have it, download from https://python.org (tick "Add Python to PATH" during install).
2. Download or copy `get_refresh_token.py` from this repo to a folder on your PC
3. Open a terminal in that folder and run:
   ```
   python get_refresh_token.py
   ```
4. Paste your Client ID and Client Secret when prompted
5. Your browser will open — log in to Spotify and click Agree
6. The terminal will print four values. **Keep this window open** — you need these in the next step.

### Step 3 — Fork or create this repo on GitHub

If you're reading this in the repo, you're already there. If starting fresh:

1. Go to https://github.com/new
2. Create a **public** repository (public = unlimited free Actions minutes; private = 2000 min/month free which may be enough but is not guaranteed)
3. Upload all files from this folder into the repo root (drag and drop in the GitHub UI works fine)

### Step 4 — Add GitHub Secrets

1. In your GitHub repo, go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret** and add each of these four secrets:

   | Secret name | Value |
   |---|---|
   | `SPOTIFY_CLIENT_ID` | From Step 2 output |
   | `SPOTIFY_CLIENT_SECRET` | From Step 2 output |
   | `SPOTIFY_REFRESH_TOKEN` | From Step 2 output |
   | `ANTHROPIC_API_KEY` | Your Anthropic API key — find it at https://console.anthropic.com/settings/keys |

### Step 5 — Enable Actions and do a test run

1. In your repo, click the **Actions** tab
2. If prompted, click **I understand my workflows, go ahead and enable them**
3. Click **ARIA 90s Bot** in the left sidebar
4. Click **Run workflow → Run workflow** (green button) to trigger it manually right now
5. Watch the run — it should complete in under a minute and create your first playlist in Spotify

After this, the bot runs automatically every 20 minutes. You don't need to do anything else.

---

## State file

`state.json` is updated by the bot after every playlist is created. It stores:

- `used_weeks` — all weeks already played (never repeats until all 521 are done)
- `current_playlist` — name, Spotify URL, track URIs, creation time
- `history` — last 100 playlists with full song lists

You can read it at any time in the repo to see what playlists have been created.

---

## Adjusting behaviour

Edit `aria_bot.py` to change:

| Variable | Default | What it does |
|---|---|---|
| `SIMILARITY_THRESHOLD` | `0.75` | Skip weeks where 75%+ of songs match a recent playlist |
| `FINISH_TRACK_COUNT` | `7` | Consider playlist done after 7 of 10 tracks played |
| `MAX_ATTEMPTS` | `20` | Max retries when looking for a distinct week |

---

## If a run fails

Go to the **Actions** tab, click the failed run, and expand the **Run ARIA Bot** step to read the error. Common causes:

- **Token expired or revoked** — re-run `get_refresh_token.py` and update the `SPOTIFY_REFRESH_TOKEN` secret
- **Rate limited by Spotify** — the next scheduled run (within 20 min) will succeed automatically
- **Anthropic API key invalid** — check https://console.anthropic.com

---

## Stopping the bot

To pause: go to **Actions → ARIA 90s Bot → ⋯ → Disable workflow**.  
To resume: same menu → **Enable workflow**.
