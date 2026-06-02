import os
import sys
import json
import requests
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

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def get_follower_data(days):
    start = (date.today() - timedelta(days=days)).isoformat()
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT date, follower_count, follower_delta FROM daily_metrics WHERE date >= ? ORDER BY date",
            (start,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_top_posts(days, limit=10):
    start = (date.today() - timedelta(days=days)).isoformat()
    with db.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.post_id, p.caption, p.media_type, p.posted_at, p.permalink,
                   MAX(pm.follows)            AS follows,
                   MAX(pm.reach)              AS reach,
                   MAX(pm.saved)              AS saved,
                   MAX(pm.shares)             AS shares,
                   MAX(pm.likes)              AS like_count,
                   MAX(pm.comments)           AS comment_count,
                   MAX(pm.profile_visits)     AS profile_visits,
                   MAX(pm.total_interactions) AS total_interactions
            FROM post_metrics pm
            JOIN posts p ON p.post_id = pm.post_id
            WHERE pm.date >= ?
            GROUP BY pm.post_id
            ORDER BY follows DESC
            LIMIT ?
            """,
            (start, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def shorten(text, n=80):
    if not text:
        return "(no caption)"
    text = text.replace("\n", " ")
    return text[:n] + "..." if len(text) > n else text


def generate_html(label, follower_data, top_posts):
    if follower_data:
        start_count = follower_data[0]["follower_count"]
        end_count = follower_data[-1]["follower_count"]
        total_growth = end_count - start_count
        growth_pct = (total_growth / start_count * 100) if start_count else 0
    else:
        start_count = end_count = total_growth = 0
        growth_pct = 0

    dates_js = json.dumps([r["date"] for r in follower_data])
    counts_js = json.dumps([r["follower_count"] for r in follower_data])
    top5 = top_posts[:5]
    bar_labels = json.dumps([shorten(p["caption"], 25) for p in top5])
    bar_values = json.dumps([p["follows"] or 0 for p in top5])

    rows_html = ""
    for i, p in enumerate(top_posts, 1):
        posted = p["posted_at"][:10] if p["posted_at"] else "-"
        rows_html += f"""
        <tr>
          <td>{i}</td>
          <td><a href="{p['permalink']}" target="_blank">{shorten(p['caption'])}</a></td>
          <td>{p['media_type']}</td>
          <td>{posted}</td>
          <td><strong>{p['follows'] or 0:,}</strong></td>
          <td>{p['total_interactions'] or 0:,}</td>
          <td>{p['reach'] or 0:,}</td>
          <td>{p['like_count'] or 0:,}</td>
          <td>{p['saved'] or 0:,}</td>
        </tr>"""

    sign = "+" if total_growth >= 0 else ""
    growth_color = "#2ecc71" if total_growth >= 0 else "#e74c3c"
    today_str = date.today().strftime("%B %d, %Y")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>@nellsleep_usa — {label} Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f4f5f7;color:#222}}
.header{{background:linear-gradient(135deg,#405DE6,#833AB4,#E1306C,#FD1D1D);color:#fff;padding:32px 40px}}
.header h1{{font-size:22px;font-weight:700}}
.header p{{opacity:.8;margin-top:4px;font-size:14px}}
.container{{max-width:1100px;margin:0 auto;padding:28px 20px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:28px}}
.kpi{{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.kpi .label{{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#888;margin-bottom:6px}}
.kpi .val{{font-size:26px;font-weight:700}}
.charts{{display:grid;grid-template-columns:2fr 1fr;gap:14px;margin-bottom:28px}}
.card{{background:#fff;border-radius:12px;padding:22px;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
.card h2{{font-size:14px;font-weight:600;margin-bottom:16px;color:#555}}
.section-title{{font-size:16px;font-weight:600;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
th{{background:#f8f9fa;text-align:left;padding:10px 14px;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#666;border-bottom:1px solid #eee}}
td{{padding:11px 14px;border-bottom:1px solid #f0f0f0;font-size:13px;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#fafafa}}
a{{color:#405DE6;text-decoration:none}}
a:hover{{text-decoration:underline}}
.footer{{text-align:center;color:#bbb;font-size:12px;margin-top:36px;padding-bottom:24px}}
</style>
</head>
<body>
<div class="header">
  <h1>@nellsleep_usa &mdash; {label} Instagram Report</h1>
  <p>Generated {today_str}</p>
</div>
<div class="container">
  <div class="kpis">
    <div class="kpi"><div class="label">Total Followers</div><div class="val">{end_count:,}</div></div>
    <div class="kpi"><div class="label">{label} Growth</div><div class="val" style="color:{growth_color}">{sign}{total_growth:,}</div></div>
    <div class="kpi"><div class="label">Growth Rate</div><div class="val" style="color:{growth_color}">{sign}{growth_pct:.1f}%</div></div>
    <div class="kpi"><div class="label">Posts Tracked</div><div class="val">{len(top_posts)}</div></div>
  </div>

  <div class="charts">
    <div class="card"><h2>Follower Trend</h2><canvas id="lineChart"></canvas></div>
    <div class="card"><h2>Top Posts by Follows</h2><canvas id="barChart"></canvas></div>
  </div>

  <div class="section-title">Top Posts by Follower Growth</div>
  <table>
    <thead><tr><th>#</th><th>Post</th><th>Type</th><th>Date</th><th>Follows</th><th>Interactions</th><th>Reach</th><th>Likes</th><th>Saves</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <div class="footer">Instagram Tracker &bull; @nellsleep_usa</div>
</div>
<script>
new Chart(document.getElementById('lineChart'),{{
  type:'line',
  data:{{labels:{dates_js},datasets:[{{label:'Followers',data:{counts_js},
    borderColor:'#405DE6',backgroundColor:'rgba(64,93,230,.08)',
    borderWidth:2,pointRadius:3,fill:true,tension:.3}}]}},
  options:{{responsive:true,plugins:{{legend:{{display:false}}}},
    scales:{{y:{{beginAtZero:false,ticks:{{callback:v=>v.toLocaleString()}}}}}}}}
}});
new Chart(document.getElementById('barChart'),{{
  type:'bar',
  data:{{labels:{bar_labels},datasets:[{{label:'Follows',data:{bar_values},
    backgroundColor:'rgba(131,58,180,.7)',borderRadius:6}}]}},
  options:{{indexAxis:'y',responsive:true,plugins:{{legend:{{display:false}}}},
    scales:{{x:{{beginAtZero:true}}}}}}
}});
</script>
</body>
</html>"""


def send_slack(label, follower_data, top_posts):
    if not SLACK_WEBHOOK:
        print("SLACK_WEBHOOK not set — skipping.")
        return

    if follower_data:
        end_count = follower_data[-1]["follower_count"]
        growth = end_count - follower_data[0]["follower_count"]
        pct = (growth / follower_data[0]["follower_count"] * 100) if follower_data[0]["follower_count"] else 0
    else:
        end_count = growth = 0
        pct = 0

    arrow = "📈" if growth >= 0 else "📉"
    sign = "+" if growth >= 0 else ""

    top3_lines = ""
    for i, p in enumerate(top_posts[:3], 1):
        caption = shorten(p["caption"], 55)
        top3_lines += f"{i}. <{p['permalink']}|{caption}>\n   ➕ *{p['follows'] or 0} follows*\n"

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"Instagram {label} Report — @nellsleep_usa"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Total Followers*\n{end_count:,}"},
                    {"type": "mrkdwn", "text": f"*{label} Growth*\n{arrow} {sign}{growth:,}  ({sign}{pct:.1f}%)"},
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🏆 Top Posts by Follower Growth*\n{top3_lines or '_No post data yet._'}",
                },
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Full HTML report saved to `Instagram tracking/reports/`"}
                ],
            },
        ]
    }

    r = requests.post(SLACK_WEBHOOK, json=payload, timeout=10)
    if r.status_code == 200:
        print("Slack message sent.")
    else:
        print(f"Slack error {r.status_code}: {r.text}")


def run_report(period="weekly"):
    days = 7 if period == "weekly" else 30
    label = "Weekly" if period == "weekly" else "Monthly"

    db.init_db()
    follower_data = get_follower_data(days)
    top_posts = get_top_posts(days)

    html = generate_html(label, follower_data, top_posts)
    filename = f"report_{period}_{date.today().isoformat()}.html"
    out = REPORTS_DIR / filename
    out.write_text(html, encoding="utf-8")
    print(f"HTML report: {out}")

    send_slack(label, follower_data, top_posts)


if __name__ == "__main__":
    period = sys.argv[1] if len(sys.argv) > 1 else "weekly"
    if period not in ("weekly", "monthly"):
        print("Usage: python report.py [weekly|monthly]")
        sys.exit(1)
    run_report(period)
