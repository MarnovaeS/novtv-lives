"""Refresh the live video id of every YouTube channel Nov TV embeds.

Reads channels.json, writes lives.json:
    {"updated": "...", "lives": {"<channelId>": "<videoId>" | null}, "searched": {"<channelId>": "<iso time>"}}
null means the channel was checked and is not live right now (the app then shows the channel's page).

Quota-friendly, cheapest check first:
  1. the id we already have, still live?   videos.list, 1 unit per 50 ids
  2. a live among the channel's latest uploads?   public RSS feed (free) + videos.list
  3. YouTube search for the channel's live   search.list, 100 units, capped by SEARCH_BUDGET (default 1) per run
     and only for channels not searched in the last SEARCH_EVERY_HOURS.

Needs YOUTUBE_API_KEY (YouTube Data API v3). Standard library only.
"""

import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

API = "https://www.googleapis.com/youtube/v3"
SEARCH_BUDGET = int(os.environ.get("SEARCH_BUDGET", "1"))
SEARCH_EVERY_HOURS = float(os.environ.get("SEARCH_EVERY_HOURS", "6"))


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "novtv-lives/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def api(key: str, path: str, **params) -> dict:
    params["key"] = key
    return json.loads(fetch(f"{API}/{path}?{urllib.parse.urlencode(params)}"))


def live_now(key: str, video_ids: list[str]) -> dict[str, str]:
    """videoId -> channelId, for the given videos that are live right now."""
    live = {}
    for start in range(0, len(video_ids), 50):
        batch = video_ids[start:start + 50]
        for item in api(key, "videos", part="snippet", id=",".join(batch), maxResults=50).get("items", []):
            snippet = item["snippet"]
            if snippet.get("liveBroadcastContent") == "live":
                live[item["id"]] = snippet["channelId"]
    return live


def latest_uploads(channel_id: str) -> list[str]:
    try:
        feed = fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}").decode("utf-8")
    except Exception as error:  # a broken feed must not stop the other channels
        print(f"  rss {channel_id}: {error}", file=sys.stderr)
        return []
    return re.findall(r"<yt:videoId>([A-Za-z0-9_-]{11})</yt:videoId>", feed)


def search_live(key: str, channel_id: str) -> str | None:
    items = api(key, "search", part="id", channelId=channel_id, eventType="live", type="video", maxResults=1).get("items", [])
    return items[0]["id"]["videoId"] if items else None


def main() -> int:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        # Not configured yet: skip quietly so the schedule doesn't send a failure email every 30 minutes.
        print("::warning::YOUTUBE_API_KEY secret is not set; lives.json left as is")
        return 0

    channels = json.load(open("channels.json", encoding="utf-8"))
    try:
        previous = json.load(open("lives.json", encoding="utf-8"))
    except FileNotFoundError:
        previous = {}
    old_lives = previous.get("lives", {})
    searched = previous.get("searched", {})
    now = dt.datetime.now(dt.timezone.utc)

    lives: dict[str, str | None] = {}

    # 1. Known ids (from the last run, or the id bundled in the app).
    known = {c["channelId"]: old_lives.get(c["channelId"]) or c.get("videoId") for c in channels}
    still_live = live_now(key, [v for v in known.values() if v])
    for video_id, channel_id in still_live.items():
        lives[channel_id] = video_id

    # 2. Latest uploads of the channels that are not covered yet.
    missing = [c["channelId"] for c in channels if c["channelId"] not in lives]
    candidates = {video_id: channel_id for channel_id in missing for video_id in latest_uploads(channel_id)}
    for video_id, channel_id in live_now(key, list(candidates)).items():
        if candidates.get(video_id) == channel_id:
            lives.setdefault(channel_id, video_id)

    # 3. Search, for the channels searched least recently, within the budget.
    def last_search(channel_id: str) -> dt.datetime:
        stamp = searched.get(channel_id)
        return dt.datetime.fromisoformat(stamp) if stamp else dt.datetime.min.replace(tzinfo=dt.timezone.utc)

    missing = sorted((c["channelId"] for c in channels if c["channelId"] not in lives), key=last_search)
    budget = SEARCH_BUDGET
    for channel_id in missing:
        if budget == 0 or now - last_search(channel_id) < dt.timedelta(hours=SEARCH_EVERY_HOURS):
            # Not checked this run: keep whatever we knew, so a quiet run doesn't wipe a good id.
            lives.setdefault(channel_id, old_lives.get(channel_id))
            continue
        budget -= 1
        searched[channel_id] = now.isoformat(timespec="seconds")
        lives[channel_id] = search_live(key, channel_id)

    result = {
        "updated": now.isoformat(timespec="seconds"),
        "lives": {c["channelId"]: lives.get(c["channelId"]) for c in channels},
        "searched": searched,
    }
    with open("lives.json", "w", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")

    live_count = sum(1 for v in result["lives"].values() if v)
    print(f"{live_count}/{len(channels)} channels live; searches used: {SEARCH_BUDGET - budget}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
