"""
Generates CSV exports from the local SQLite database for Google Sheets upload.
Includes spike detection and post correlation analysis.
"""
import os
import csv
import io
import json
from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

import db

EXPORT_DIR = Path(__file__).parent / "exports"
EXPORT_DIR.mkdir(exist_ok=True)

INFLUENCER_HANDLES = [
    "lesleywolman", "healthywithspence", "melissameyers", "romyraves", "ally.warren",
    "gizweezy", "ariannapapalexopoulos", "amandumb1", "our.chaotic.little.life",
    "longboy_louis", "rxchelleyu", "foxtoller", "kayli_renee_jones", "iamcelys",
    "courtneyquist_", "la3to", "hhthr", "laurenboggi", "zabrinapeters2.0", "chloegaynor",
    "_koreygregg_", "desttirado", "arinunezz", "kate_romanoff",
]


def flag_influencer(caption):
    if not caption:
        return ""
    cap = caption.lower()
    for h in INFLUENCER_HANDLES:
        if "@" + h in cap or h in cap:
            return "⭐ " + h
    return ""


def compute_spike_analysis():
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT date, follower_count, follower_delta FROM daily_metrics ORDER BY date"
        ).fetchall()
    return [dict(r) for r in rows]


def get_posts_by_date_range(start_date, end_date):
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT p.post_id, p.posted_at, p.media_type, p.caption, p.permalink,
                      pm.follows, pm.reach, pm.total_interactions
               FROM posts p
               LEFT JOIN post_metrics pm ON pm.post_id = p.post_id
               WHERE date(p.posted_at) BETWEEN ? AND ?
               ORDER BY p.posted_at DESC""",
            (start_date, end_date),
        ).fetchall()
    return [dict(r) for r in rows]


def build_daily_tracker_csv():
    daily_data = compute_spike_analysis()

    # Calculate 7-day rolling average delta
    enriched = []
    for i, row in enumerate(daily_data):
        window = daily_data[max(0, i - 7):i]
        if window:
            avg = sum(w["follower_delta"] for w in window) / len(window)
        else:
            avg = None

        delta = row["follower_delta"]
        is_spike = avg is not None and avg > 0 and delta >= 2 * avg

        # Find posts from 1-5 days prior to this date
        day = date.fromisoformat(row["date"])
        lookback_end = (day - timedelta(days=1)).isoformat()
        lookback_start = (day - timedelta(days=5)).isoformat()
        prior_posts = get_posts_by_date_range(lookback_start, lookback_end)

        if prior_posts:
            driver_parts = []
            for p in prior_posts[:3]:
                inf = flag_influencer(p["caption"] or "")
                caption_short = (p["caption"] or "")[:50].replace("\n", " ")
                posted = p["posted_at"][:10] if p["posted_at"] else ""
                label = f"{inf} {p['media_type']} ({posted}): {caption_short}...".strip()
                driver_parts.append(label)
            drivers = " | ".join(driver_parts)
        else:
            drivers = "—"

        enriched.append({
            "date": row["date"],
            "follower_count": row["follower_count"],
            "follower_delta": f"{delta:+d}" if delta != 0 else "0",
            "avg_7d": f"{avg:.1f}" if avg is not None else "—",
            "spike": "🔴 YES" if is_spike else "No",
            "drivers": drivers,
        })

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "HOW TO READ: Spike = day where growth is 2× the 7-day average. "
        "Likely Post Drivers = posts published 1–5 days before. "
        "⭐ = influencer collab. Reels follows unavailable from Instagram API.",
        "", "", "", "", "",
    ])
    w.writerow([
        "Date", "Followers", "Daily Change", "7-Day Avg Change",
        "Spike?", "Likely Post Drivers (1–5 days prior)",
    ])
    for r in enriched:
        w.writerow([
            r["date"], r["follower_count"], r["follower_delta"],
            r["avg_7d"], r["spike"], r["drivers"],
        ])

    return out.getvalue()


def build_post_performance_csv():
    with db.get_conn() as conn:
        posts = conn.execute(
            """SELECT p.posted_at, p.media_type, p.caption, p.permalink,
                      pm.follows, pm.reach, pm.likes, pm.saved, pm.shares,
                      pm.total_interactions, pm.profile_visits
               FROM post_metrics pm
               JOIN posts p ON p.post_id = pm.post_id
               ORDER BY p.posted_at DESC"""
        ).fetchall()
    posts = [dict(r) for r in posts]

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "NOTE: Follows only available for FEED/CAROUSEL — Instagram does not "
        "provide this metric for Reels. For Reels use Reach + Total Interactions. "
        "⭐ = matched against influencer list.",
        "", "", "", "", "", "", "", "", "", "", "",
    ])
    w.writerow([
        "Post Date", "Type", "Influencer Collab", "Caption (preview)", "Link",
        "Follows (Feed only)", "Reach", "Likes", "Saves", "Shares",
        "Total Interactions", "Profile Visits",
    ])
    for p in posts:
        caption = (p["caption"] or "").replace("\n", " ")
        preview = caption[:100] + ("..." if len(caption) > 100 else "")
        posted = p["posted_at"][:10] if p["posted_at"] else ""
        w.writerow([
            posted, p["media_type"], flag_influencer(caption), preview, p["permalink"],
            p["follows"] or 0, p["reach"] or 0, p["likes"] or 0,
            p["saved"] or 0, p["shares"] or 0,
            p["total_interactions"] or 0, p["profile_visits"] or 0,
        ])

    return out.getvalue()


def main():
    db.init_db()
    today = date.today().isoformat()

    daily_csv = build_daily_tracker_csv()
    posts_csv = build_post_performance_csv()

    daily_path = EXPORT_DIR / "daily_tracker.csv"
    posts_path = EXPORT_DIR / "post_performance.csv"
    meta_path = EXPORT_DIR / "meta.json"

    daily_path.write_text(daily_csv, encoding="utf-8")
    posts_path.write_text(posts_csv, encoding="utf-8")
    meta_path.write_text(json.dumps({
        "updated": today,
        "drive_folder_id": "1zlzbLD4Sh1ifjdB2geMwPPUb-tkjGvKP",
    }), encoding="utf-8")

    print(f"Exports written to {EXPORT_DIR}")
    print(f"  {daily_path.name}: {len(daily_csv.splitlines())} rows")
    print(f"  {posts_path.name}: {len(posts_csv.splitlines())} rows")


if __name__ == "__main__":
    main()
