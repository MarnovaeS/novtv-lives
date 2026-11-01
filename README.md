# novtv-lives

Keeps the current live video id of each YouTube channel that the Nov TV app embeds.

- `channels.json`: the channels (official broadcaster channels only).
- `update_lives.py`: refreshes `lives.json` through the YouTube Data API v3 (standard library only).
- `.github/workflows/update.yml`: runs it every 30 minutes and commits `lives.json` when it changes.
- `lives.json`: what the app reads, at `https://raw.githubusercontent.com/MarnovaeS/novtv-lives/main/lives.json`.

## Setup

1. Create an API key for **YouTube Data API v3** in Google Cloud Console.
2. In this repository: Settings → Secrets and variables → Actions → new secret `YOUTUBE_API_KEY`.
3. Actions → "Update live ids" → Run workflow, to fill `lives.json` the first time.

## Quota

The daily free quota is 10,000 units. One run costs about 2 units to check known and new videos, plus at most `SEARCH_BUDGET` (default 1) search at 100 units. Searches only happen for channels that are not live and have not been searched in the last 6 hours. At 48 runs a day, the worst case is about 5,000 units.

## Adding a channel

Add it to `channels.json` (name, `channelId`, optional current `videoId`) and to `PublicChannels.kt` in the app.
