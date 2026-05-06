"""
ARIA 90s Bot — GitHub Actions edition
Polls Spotify recently-played every 20 min.
Creates the next playlist when the current one is finished.
"""

import os
import json
import random
import sys
import time
import requests
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────
SPOTIFY_CLIENT_ID     = os.environ["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET = os.environ["SPOTIFY_CLIENT_SECRET"]
SPOTIFY_REFRESH_TOKEN = os.environ["SPOTIFY_REFRESH_TOKEN"]
ANTHROPIC_API_KEY     = os.environ["ANTHROPIC_API_KEY"]

STATE_FILE            = Path("state.json")
SIMILARITY_THRESHOLD  = 0.75   # skip if >75% overlap with recent playlists
FINISH_TRACK_COUNT    = 7      # consider finished if 7+ of 10 tracks appear in recently-played
MAX_ATTEMPTS          = 20     # how many random weeks to try before giving up


# ── Spotify auth ────────────────────────────────────────────────────────────

def get_spotify_token() -> str:
    r = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type":    "refresh_token",
            "refresh_token": SPOTIFY_REFRESH_TOKEN,
            "client_id":     SPOTIFY_CLIENT_ID,
            "client_secret": SPOTIFY_CLIENT_SECRET,
        },
    )
    print(f"API status: {r.status_code} body: {r.text[:300]}")
    r.raise_for_status()
    return r.json()["access_token"]


def spotify(method: str, path: str, token: str, **kwargs):
    url = f"https://api.spotify.com/v1{path}"
    r = requests.request(
        method, url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        **kwargs
    )
    r.raise_for_status()
    return r.json() if r.content else {}


def get_user_id(token: str) -> str:
    return spotify("GET", "/me", token)["id"]


# ── State ───────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"used_weeks": [], "current_playlist": None, "history": []}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ── Playlist-finished detection ─────────────────────────────────────────────

def is_playlist_finished(token: str, playlist: dict) -> bool:
    """
    Returns True if the user has listened through enough of the current playlist
    since it was created.  Two checks (either triggers 'done'):

    1. The final track appears in recently-played after playlist creation time.
    2. At least FINISH_TRACK_COUNT playlist tracks appear in recently-played
       after creation (handles skipping the last track).
    """
    if not playlist:
        return True

    last_uri   = playlist.get("last_track_uri")
    created_at = playlist.get("created_at", "")
    track_uris = set(playlist.get("track_uris", []))

    if not created_at or not track_uris:
        return True

    try:
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return True

    try:
        data  = spotify("GET", "/me/player/recently-played?limit=50", token)
        items = data.get("items", [])
    except Exception as e:
        print(f"  [recently-played] {e}")
        return False

    matched = set()
    for item in items:
        played_at  = item.get("played_at", "")
        track_uri  = item.get("track", {}).get("uri", "")

        try:
            played_dt = datetime.fromisoformat(played_at.replace("Z", "+00:00"))
        except ValueError:
            continue

        if played_dt <= created_dt:
            continue  # listened before this playlist was created

        # Check 1 – last track played
        if last_uri and track_uri == last_uri:
            print("  ✓ Last track detected in recently-played — playlist finished.")
            return True

        # Accumulate for check 2
        if track_uri in track_uris:
            matched.add(track_uri)

    # Check 2 – enough tracks played
    if len(matched) >= FINISH_TRACK_COUNT:
        print(f"  ✓ {len(matched)}/{len(track_uris)} tracks played — playlist finished.")
        return True

    print(f"  Playlist in progress. ({len(matched)}/{len(track_uris)} tracks heard so far)")
    return False


# ── ARIA chart data ─────────────────────────────────────────────────────────

def get_aria_chart(week: str) -> dict:
    """Call Claude to get the historically accurate ARIA top-10 for a given week."""
    prompt = (
        "Return ONLY valid JSON — no markdown fences, no preamble, no commentary.\n"
        f'Format exactly: {{"songs":[{{"n":1,"t":"Song Title","a":"Artist Name"}},'
        f'{{"n":2,"t":"...","a":"..."}},...up to 10]}}\n\n'
        f"Give me the actual ARIA Australian singles Top 10 for the week closest to {week}. "
        "These must be real songs that charted in Australia. Be historically accurate."
    )

    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model":      "claude-3-5-haiku-20241022",
            "max_tokens": 800,
            "messages":   [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    if not r.ok:
        print(f"    Anthropic error detail: {r.text}")
    r.raise_for_status()

    text = "".join(c.get("text", "") for c in r.json().get("content", []))
    text = text.strip().strip("```json").strip("```").strip()
    return json.loads(text)


# ── Spotify search ──────────────────────────────────────────────────────────

def find_track(token: str, title: str, artist: str) -> str | None:
    queries = [
        f'track:"{title}" artist:"{artist}"',
        f"{title} {artist}",
    ]
    for q in queries:
        try:
            data  = spotify("GET", f"/search?q={urllib.parse.quote(q)}&type=track&limit=1&market=AU", token)
            items = data.get("tracks", {}).get("items", [])
            if items:
                return items[0]["uri"]
        except Exception:
            pass
    return None


# ── Helpers ─────────────────────────────────────────────────────────────────

def all_weeks() -> list[str]:
    weeks, d, end = [], datetime(1990, 1, 7), datetime(1999, 12, 26)
    while d <= end:
        weeks.append(d.strftime("%Y-%m-%d"))
        d += timedelta(weeks=1)
    return weeks


def jaccard(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    norm = lambda x: x.lower().replace(" ", "").replace("'", "")
    sa, sb = set(map(norm, a)), set(map(norm, b))
    i = len(sa & sb)
    return i / (len(sa) + len(sb) - i)


def fmt_date(week_str: str) -> str:
    d = datetime.strptime(week_str, "%Y-%m-%d")
    return d.strftime("%-d %B %Y")   # Linux/macOS — GH Actions is Ubuntu, this is fine


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'─'*55}")
    print(f"  ARIA 90s Bot  |  {ts}")
    print(f"{'─'*55}")

    state   = load_state()
    token   = get_spotify_token()
    user_id = get_user_id(token)
    print(f"  Spotify user: {user_id}")

    current = state.get("current_playlist")

    if current:
        print(f"\n  Current playlist: \"{current.get('name')}\"")
        finished = is_playlist_finished(token, current)
    else:
        print("\n  No current playlist — will create one.")
        finished = True

    if not finished:
        print("\n  Nothing to do. Exiting.\n")
        return

    # ── Pick a week ──────────────────────────────────────────────────────────
    weeks     = all_weeks()
    used      = state.get("used_weeks", [])
    history   = state.get("history", [])
    available = [w for w in weeks if w not in used]

    if not available:
        print("\n  All 521 weeks played! Resetting pool.")
        used      = []
        available = weeks[:]
        state["used_weeks"] = []

    recent_keys = [h.get("keys", []) for h in history[:10]]
    selected    = None
    chart_data  = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        candidate = random.choice(available)
        print(f"\n  Attempt {attempt}: week of {candidate}")

        try:
            data = get_aria_chart(candidate)
        except Exception as e:
            print(f"    Chart fetch failed: {e}")
            continue

        songs = data.get("songs", [])
        if len(songs) < 5:
            print("    Received too few songs, retrying.")
            continue

        keys        = [f"{s['t']} {s['a']}" for s in songs]
        too_similar = False
        for recent in recent_keys:
            sim = jaccard(keys, recent)
            if sim >= SIMILARITY_THRESHOLD:
                print(f"    Skipping — {sim:.0%} match with a recent playlist.")
                too_similar = True
                break

        if not too_similar:
            selected   = candidate
            chart_data = data
            break

    if not selected:
        print(f"\n  Could not find a distinct week in {MAX_ATTEMPTS} attempts. Exiting.")
        sys.exit(1)

    # ── Find tracks on Spotify ───────────────────────────────────────────────
    songs   = chart_data["songs"]
    uris    = []
    missing = []

    print(f"\n  Chart: ARIA Australia Top 10 — week of {fmt_date(selected)}")
    for s in songs:
        uri = find_track(token, s["t"], s["a"])
        if uri:
            uris.append(uri)
            print(f"    {s['n']:>2}. ✓ {s['t']} — {s['a']}")
        else:
            missing.append(f"{s['t']} — {s['a']}")
            print(f"    {s['n']:>2}. ✗ {s['t']} — {s['a']}  (not on Spotify AU)")

    if not uris:
        print("\n  No tracks found at all — aborting.")
        sys.exit(1)

    # ── Create Spotify playlist ──────────────────────────────────────────────
    label       = fmt_date(selected)
    pl_name     = f"🇦🇺 ARIA Top 10 · {label}"
    pl_desc     = (
        f"Australian ARIA Top 10 singles — week of {label}. "
        "Auto-generated by ARIA 90s Bot."
    )

    pl = spotify("POST", f"/users/{user_id}/playlists", token,
                 json={"name": pl_name, "description": pl_desc, "public": False})
    spotify("POST", f"/playlists/{pl['id']}/tracks", token, json={"uris": uris})

    pl_url = pl.get("external_urls", {}).get("spotify", "")

    print(f"\n  ✅  Created: \"{pl_name}\"")
    print(f"      Tracks added : {len(uris)}/{len(songs)}")
    if missing:
        print(f"      Not on Spotify: {', '.join(missing)}")
    print(f"      URL: {pl_url}")

    # ── Persist state ────────────────────────────────────────────────────────
    entry = {
        "id":             pl["id"],
        "name":           pl_name,
        "url":            pl_url,
        "week":           selected,
        "label":          label,
        "keys":           [f"{s['t']} {s['a']}" for s in songs],
        "songs":          songs,
        "track_uris":     uris,
        "last_track_uri": uris[-1],
        "created_at":     datetime.now(timezone.utc).isoformat(),
        "found":          len(uris),
        "total":          len(songs),
        "missing":        missing,
    }

    state["current_playlist"] = entry
    state["used_weeks"]       = used + [selected]
    state["history"]          = [entry] + history[:99]
    save_state(state)

    print(f"\n  State saved. {len(state['used_weeks'])} / {len(weeks)} weeks used.")
    print(f"{'─'*55}\n")


if __name__ == "__main__":
    main()
