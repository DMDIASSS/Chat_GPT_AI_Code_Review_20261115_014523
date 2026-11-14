"""Download ranked 2v2 / 3v3 replays from ballchasing.com.

Usage (PowerShell):
    $env:BALLCHASING_KEY = "your-token"
    python ballchasing_download.py --max 200 --out replays
    python ballchasing_download.py --inspect          # print one raw list item to see the real JSON shape

Notes (from https://ballchasing.com/doc/api):
  * min-rank has NO 'supersonic-legend' value. The highest filter is 'grand-champion',
    so we filter server side with that and then check the rank on each player client side.
  * GET /replays   : default tier 2 calls/s, 500/hour.
  * GET /replays/{id}/file : default tier 1 call/s, 200/hour (patron tiers are higher).
  Set --per-hour to your tier's file limit.
"""
import argparse, json, os, pathlib, sys, time
import requests

API = "https://ballchasing.com/api"
PLAYLISTS = {"2v2": "ranked-doubles", "3v3": "ranked-standard"}


def player_rank_id(player: dict) -> str:
    rank = player.get("rank") or {}
    return (rank.get("id") or rank.get("name") or "").lower().replace(" ", "-")


def is_ssl(player: dict) -> bool:
    r = player_rank_id(player)
    return "supersonic" in r


def replay_is_all_ssl(item: dict, require_rank: bool = True) -> bool:
    """True if every player has an SSL rank. If a player has no rank field, treat as unknown:
    rejected when require_rank is True, accepted otherwise."""
    players = (item.get("blue") or {}).get("players", []) + (item.get("orange") or {}).get("players", [])
    if not players:
        return False
    for p in players:
        if not player_rank_id(p):
            if require_rank:
                return False
            continue
        if not is_ssl(p):
            return False
    return True


class Client:
    def __init__(self, key: str, per_hour: int):
        self.s = requests.Session()
        self.s.headers["Authorization"] = key
        self.per_hour = per_hour
        self.sent = []          # timestamps of file downloads in the last hour

    def get(self, url, **kw):
        for attempt in range(8):
            r = self.s.get(url, timeout=60, **kw)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 10 * (attempt + 1)))
                print(f"429 rate limited, sleeping {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        raise RuntimeError("too many 429 responses")

    def throttle_files(self):
        now = time.time()
        self.sent = [t for t in self.sent if now - t < 3600]
        if len(self.sent) >= self.per_hour:
            wait = 3600 - (now - self.sent[0]) + 5
            print(f"hourly file limit reached, sleeping {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
        self.sent.append(time.time())
        time.sleep(1.1)          # 1 call/second for the default tier


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="replays")
    ap.add_argument("--max", type=int, default=100, help="max replays to download per playlist")
    ap.add_argument("--modes", nargs="+", default=["2v2", "3v3"], choices=list(PLAYLISTS))
    ap.add_argument("--per-hour", type=int, default=200, help="file download limit of your patron tier")
    ap.add_argument("--min-rank", default="grand-champion")
    ap.add_argument("--allow-unknown-rank", action="store_true", help="accept players with no rank field")
    ap.add_argument("--inspect", action="store_true")
    a = ap.parse_args()

    key = os.environ.get("BALLCHASING_KEY")
    if not key:
        sys.exit("Set the BALLCHASING_KEY environment variable first.")
    c = Client(key, a.per_hour)
    c.get(f"{API}/")                                 # ping: fails fast on a bad key

    if a.inspect:
        r = c.get(f"{API}/replays", params={"playlist": "ranked-doubles", "min-rank": a.min_rank, "count": 1}).json()
        print(json.dumps(r["list"][0] if r.get("list") else r, indent=2)[:4000])
        return

    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.jsonl"
    seen = set()
    if manifest_path.exists():
        seen = {json.loads(l)["id"] for l in manifest_path.read_text().splitlines() if l.strip()}

    for mode in a.modes:
        playlist = PLAYLISTS[mode]
        got = 0
        url = f"{API}/replays"
        params = {"playlist": playlist, "min-rank": a.min_rank, "count": 200,
                  "sort-by": "replay-date", "sort-dir": "desc"}
        while url and got < a.max:
            time.sleep(0.6)
            page = c.get(url, params=params).json()
            for item in page.get("list", []):
                if got >= a.max:
                    break
                rid = item["id"]
                if rid in seen:
                    continue
                if not replay_is_all_ssl(item, require_rank=not a.allow_unknown_rank):
                    continue
                c.throttle_files()
                data = c.get(f"{API}/replays/{rid}/file").content
                (out / f"{mode}_{rid}.replay").write_bytes(data)
                with manifest_path.open("a") as f:
                    f.write(json.dumps({"id": rid, "mode": mode, "date": item.get("date"),
                                        "duration": item.get("duration"), "season": item.get("season")}) + "\n")
                seen.add(rid); got += 1
                print(f"[{mode}] {got}/{a.max} {rid}")
            url, params = page.get("next"), None      # 'next' already contains the query string
        print(f"{mode}: downloaded {got}")


if __name__ == "__main__":
    main()
