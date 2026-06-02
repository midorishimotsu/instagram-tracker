import os
import sys
import requests
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    # Manual .env loader fallback
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

import db

IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")
PAGE_TOKEN = os.getenv("PAGE_TOKEN")
APP_ID = os.getenv("APP_ID")
APP_SECRET = os.getenv("APP_SECRET")
BASE = "https://graph.facebook.com/v21.0"

# Keyed by media_product_type (FEED, REELS, STORY, etc.)
METRICS_BY_PRODUCT_TYPE = {
    "FEED":  "reach,saved,shares,likes,comments,follows,profile_visits,total_interactions",
    "REELS": "reach,saved,shares,likes,comments,total_interactions,ig_reels_avg_watch_time",
    "STORY": "reach,saved,shares,total_interactions",
}
FALLBACK_METRICS = "reach,saved,shares,likes,comments,total_interactions"


def api_get(url, params=None):
    p = {"access_token": PAGE_TOKEN}
    if params:
        p.update(params)
    r = requests.get(url, params=p, timeout=30)
    r.raise_for_status()
    return r.json()


def refresh_token():
    """Refresh the long-lived token and update .env if it changes."""
    try:
        r = requests.get(
            f"{BASE}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": APP_ID,
                "client_secret": APP_SECRET,
                "fb_exchange_token": PAGE_TOKEN,
            },
            timeout=30,
        )
        if r.status_code == 200:
            print("Token refreshed successfully.")
    except Exception as e:
        print(f"Token refresh skipped: {e}")


def get_follower_count():
    data = api_get(f"{BASE}/{IG_ACCOUNT_ID}", {"fields": "followers_count"})
    return data["followers_count"]


def get_all_posts():
    url = f"{BASE}/{IG_ACCOUNT_ID}/media"
    params = {
        "fields": "id,caption,media_type,media_product_type,timestamp,permalink,like_count,comments_count",
        "limit": 50,
    }
    posts = []
    while True:
        data = api_get(url, params)
        posts.extend(data.get("data", []))
        next_url = data.get("paging", {}).get("next")
        if not next_url:
            break
        url = next_url
        params = {}
    return posts


def parse_insights(data):
    result = {}
    for item in data.get("data", []):
        name = item["name"]
        if "values" in item and item["values"]:
            result[name] = item["values"][0].get("value", 0)
        else:
            result[name] = item.get("value", 0)
    return result


def get_post_insights(post_id, media_product_type):
    metrics = METRICS_BY_PRODUCT_TYPE.get(media_product_type, FALLBACK_METRICS)
    try:
        data = api_get(f"{BASE}/{post_id}/insights", {"metric": metrics})
        return parse_insights(data)
    except requests.HTTPError:
        pass
    try:
        data = api_get(f"{BASE}/{post_id}/insights", {"metric": FALLBACK_METRICS})
        return parse_insights(data)
    except requests.HTTPError:
        return {}


def collect():
    db.init_db()
    today = date.today().isoformat()

    follower_count = get_follower_count()
    with db.get_conn() as conn:
        prev = conn.execute(
            "SELECT follower_count FROM daily_metrics ORDER BY date DESC LIMIT 1"
        ).fetchone()
        delta = follower_count - (prev["follower_count"] if prev else follower_count)
        conn.execute(
            "INSERT OR REPLACE INTO daily_metrics (date, follower_count, follower_delta) VALUES (?,?,?)",
            (today, follower_count, delta),
        )
    print(f"[{today}] Followers: {follower_count:,} ({delta:+d})")

    posts = get_all_posts()
    print(f"Fetching insights for {len(posts)} posts...")
    with db.get_conn() as conn:
        for i, post in enumerate(posts, 1):
            pid = post["id"]
            media_product_type = post.get("media_product_type") or post.get("media_type", "FEED")
            conn.execute(
                "INSERT OR IGNORE INTO posts (post_id, caption, media_type, posted_at, permalink) VALUES (?,?,?,?,?)",
                (
                    pid,
                    post.get("caption", "")[:500],
                    media_product_type,
                    post.get("timestamp", ""),
                    post.get("permalink", ""),
                ),
            )
            ins = get_post_insights(pid, media_product_type)
            conn.execute(
                """INSERT OR REPLACE INTO post_metrics
                   (post_id, date, reach, saved, shares, likes, comments,
                    follows, profile_visits, total_interactions)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid, today,
                    ins.get("reach", 0),
                    ins.get("saved", 0),
                    ins.get("shares", 0),
                    ins.get("likes", post.get("like_count", 0)),
                    ins.get("comments", post.get("comments_count", 0)),
                    ins.get("follows", 0),
                    ins.get("profile_visits", 0),
                    ins.get("total_interactions", 0),
                ),
            )
            if i % 10 == 0:
                print(f"  {i}/{len(posts)} posts processed...")

    print(f"Done. Data stored for {len(posts)} posts.")
    refresh_token()


if __name__ == "__main__":
    collect()
