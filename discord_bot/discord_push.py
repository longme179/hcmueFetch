#!/usr/bin/env python3
"""Standalone script to fetch newest posts and push to Discord.
Supports both scheduled (12h) and manual (!fetch command) triggers."""

import os
import sys
import time
from itertools import groupby
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import DEFAULT_CONFIG, DEFAULT_SEEN, load_config, run_digest

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "")
COUNT = int(os.getenv("FETCH_COUNT", "5"))
PUSH_INTERVAL_SEC = 12 * 60 * 60  # 12 hours

DATA_DIR = Path(__file__).parent
LAST_PUSH_FILE = DATA_DIR / "last_push.txt"
LAST_CMD_FILE = DATA_DIR / "last_cmd_id.txt"


def discord_api(method, endpoint, payload=None):
    import requests

    headers = {"Authorization": f"Bot {BOT_TOKEN}"}
    url = f"https://discord.com/api/v10{endpoint}"
    r = requests.request(method, url, headers=headers, json=payload, timeout=10)
    if r.status_code == 429:  # Rate limit
        time.sleep(r.json().get("retry_after", 2))
        return discord_api(method, endpoint, payload)
    return r.json() if r.status_code != 204 else {}


def send_discord(items, forced=False):
    if not items:
        discord_api(
            "POST",
            f"/channels/{CHANNEL_ID}/messages",
            {"content": "Không có bài viết mới nào."},
        )
        return

    content = (
        "⚡ **Manual Fetch (Top 3 mỗi nguồn):**\n"
        if forced
        else "📢 **Bài viết mới nhất:**\n"
    )

    # Sort by source name to group them nicely
    items_sorted = sorted(items, key=lambda x: x.source_name)

    for source_name, group in groupby(items_sorted, key=lambda x: x.source_name):
        content += f"\n**[{source_name}]**\n"
        for it in group:
            # it.date_str() returns "dd/mm/yyyy hh:mm" or "(không rõ ngày)"
            line = f"- `{it.date_str()}` [{it.title}](<{it.link}>)\n"
            if len(content) + len(line) > 1900:
                discord_api(
                    "POST", f"/channels/{CHANNEL_ID}/messages", {"content": content}
                )
                content = "...\n"
            content += line

    discord_api("POST", f"/channels/{CHANNEL_ID}/messages", {"content": content})


def check_manual_trigger():
    if not BOT_TOKEN or not CHANNEL_ID:
        return False

    last_id = LAST_CMD_FILE.read_text().strip() if LAST_CMD_FILE.exists() else "0"
    endpoint = f"/channels/{CHANNEL_ID}/messages?limit=10"
    if last_id != "0":
        endpoint += f"&after={last_id}"

    msgs = discord_api("GET", endpoint)
    if not isinstance(msgs, list):
        return False

    triggered = False
    for msg in reversed(msgs):  # chronological order
        if msg.get("content", "").strip().lower() == "!fetch":
            triggered = True
        last_id = msg["id"]

    LAST_CMD_FILE.write_text(last_id)
    return triggered


def check_scheduled_trigger():
    last_push = (
        float(LAST_PUSH_FILE.read_text().strip()) if LAST_PUSH_FILE.exists() else 0
    )
    if time.time() - last_push >= PUSH_INTERVAL_SEC:
        LAST_PUSH_FILE.write_text(str(time.time()))
        return True
    return False


def main():
    if not BOT_TOKEN or not CHANNEL_ID:
        print("Error: Set DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID env vars.")
        return 1

    forced = check_manual_trigger()
    scheduled = check_scheduled_trigger()

    if not forced and not scheduled:
        return 0  # Nothing to do, exit silently

    sources = load_config(DEFAULT_CONFIG)
    if not sources:
        if forced:
            send_discord([], True)
        return 1

    if forced:
        # Manual command: fetch top 3 per source
        count = 3
        mode = "per-source"
    else:
        # Scheduled run: fetch top 5 combined, filter is_new
        count = COUNT
        mode = "combined"

    items, _ = run_digest(
        sources=sources,
        count=count,
        mode=mode,
        no_excerpt=True,
        reset_seen=False,
        seen_path=DEFAULT_SEEN,
        log_func=lambda msg: print(msg),
    )

    # On manual trigger, push all fetched items. On scheduled, only push new ones.
    items_to_push = items if forced else [it for it in items if it.is_new]

    if not items_to_push and not forced:
        print("Không có bài mới, bỏ qua gửi tin nhắn.")
        return 0

    send_discord(items_to_push, forced)


if __name__ == "__main__":
    sys.exit(main() or 0)
