"""
Daily Morning News Emailer — GNews API (Rate Limit Safe)
1 request per beat + delay | GitHub Actions | 9 AM IST
Bilingual Hindi + English
"""

import os, smtplib, hashlib, logging, time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dataclasses import dataclass, field

import requests

CONFIG = {
    "sender_email":    os.environ["SENDER_EMAIL"],
    "sender_password": os.environ["SENDER_PASSWORD"],
    "receiver_email":  os.environ["RECEIVER_EMAIL"],
    "gnews_key":       os.environ["GNEWS_KEY"],
    "news_per_beat":   10,
}

BEATS = ["National", "International", "Politics", "Sports",
         "Entertainment", "Science & Tech", "City News"]

BEAT_BILINGUAL = {
    "National":       {"hi": "राष्ट्रीय",      "en": "National"},
    "International":  {"hi": "अंतर्राष्ट्रीय",  "en": "International"},
    "Politics":       {"hi": "राजनीति",         "en": "Politics"},
    "Sports":         {"hi": "खेल",             "en": "Sports"},
    "Entertainment":  {"hi": "मनोरंजन",         "en": "Entertainment"},
    "Science & Tech": {"hi": "विज्ञान & टेक",   "en": "Science & Tech"},
    "City News":      {"hi": "शहर",             "en": "City News"},
}

# Sirf 1 request per beat — total 7 requests/day (well within 10/day limit)
BEAT_REQUEST = {
    "National": {
        "url": "https://gnews.io/api/v4/top-headlines",
        "params": {"country": "in", "lang": "en", "max": 10},
    },
    "International": {
        "url": "https://gnews.io/api/v4/top-headlines",
        "params": {"topic": "world", "lang": "en", "max": 10},
    },
    "Politics": {
        "url": "https://gnews.io/api/v4/search",
        "params": {"q": "India politics election BJP Congress Modi", "lang": "en", "max": 10},
    },
    "Sports": {
        "url": "https://gnews.io/api/v4/top-headlines",
        "params": {"topic": "sports", "lang": "en", "max": 10},
    },
    "Entertainment": {
        "url": "https://gnews.io/api/v4/top-headlines",
        "params": {"topic": "entertainment", "lang": "en", "max": 10},
    },
    "Science & Tech": {
        "url": "https://gnews.io/api/v4/top-headlines",
        "params": {"topic": "technology", "lang": "en", "max": 10},
    },
    "City News": {
        "url": "https://gnews.io/api/v4/search",
        "params": {"q": "Delhi Mumbai Bangalore Chennai Hyderabad city news", "lang": "en", "max": 10},
    },
}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    beat: str
    fingerprint: str = field(init=False)

    def __post_init__(self):
        self.fingerprint = hashlib.md5(
            " ".join(self.title.lower().split()).encode()
        ).hexdigest()


def fetch_gnews(beat: str) -> list:
    items = []
    req = BEAT_REQUEST[beat]
    try:
        params = dict(req["params"])
        params["apikey"] = CONFIG["gnews_key"]
        r = requests.get(req["url"], params=params, timeout=15)
        data = r.json()
        if "errors" in data:
            log.warning(f"{beat}: GNews error — {data['errors']}")
            return items
        for art in data.get("articles", []):
            title = (art.get("title") or "").strip()
            url   = (art.get("url") or "").strip()
            src   = (art.get("source", {}).get("name") or "GNews").strip()
            if not title or not url:
                continue
            for sep in [" - ", " | "]:
                if sep in title:
                    title = title.rsplit(sep, 1)[0].strip()
            items.append(NewsItem(title=title, url=url, source=src, beat=beat))
        log.info(f"✅ {beat:15s} → {len(items)} articles")
    except Exception as e:
        log.error(f"❌ {beat}: {e}")
    return items


def collect_news() -> dict:
    categorized = {}
    global_seen = set()

    for i, beat in enumerate(BEATS):
        # 5 second delay between requests to avoid rate limiting
        if i > 0:
            log.info(f"⏳ Waiting 5s before next request...")
            time.sleep(5)

        items = fetch_gnews(beat)
        unique = []
        for item in items:
            if item.fingerprint not in global_seen:
                global_seen.add(item.fingerprint)
                unique.append(item)

        categorized[beat] = unique[:CONFIG["news_per_beat"]]
        log.info(f"📰 {beat:15s} → Final: {len(categorized[beat])} news")

    return categorized


BEAT_META = {
    "National":       {"color": "#1a56db", "icon": "🇮🇳"},
    "International":  {"color": "#0e9f6e", "icon": "🌍"},
    "Politics":       {"color": "#7e3af2", "icon": "🏛️"},
    "Sports":         {"color": "#d97706", "icon": "🏆"},
    "Entertainment":  {"color": "#e02424", "icon": "🎬"},
    "Science & Tech": {"color": "#0891b2", "icon": "🔬"},
    "City News":      {"color": "#059669", "icon": "🏙️"},
}

HINDI_MONTHS = {
    "January": "जनवरी", "February": "फ़रवरी", "March": "मार्च",
    "April": "अप्रैल", "May": "मई", "June": "जून", "July": "जुलाई",
    "August": "अगस्त", "September": "सितंबर", "October": "अक्टूबर",
    "November": "नवंबर", "December": "दिसंबर",
}
HINDI_DAYS = {
    "Monday": "सोमवार", "Tuesday": "मंगलवार", "Wednesday": "बुधवार",
    "Thursday": "गुरुवार", "Friday": "शुक्रवार",
    "Saturday": "शनिवार", "Sunday": "रविवार",
}


def hindi_date() -> str:
    n = datetime.now()
    return (f"{HINDI_DAYS.get(n.strftime('%A'), n.strftime('%A'))}, "
            f"{n.day} "
            f"{HINDI_MONTHS.get(n.strftime('%B'), n.strftime('%B'))} "
            f"{n.year}")


def build_html(news_by_beat: dict) -> str:
    total    = sum(len(v) for v in news_by_beat.values())
    today_hi = hindi_date()
    today_en = datetime.now().strftime("%A, %d %B %Y")
    beats_html = ""

    for beat in BEATS:
        items = news_by_beat.get(beat, [])
        meta, bi = BEAT_META[beat], BEAT_BILINGUAL[beat]
        rows = ""
        if not items:
            rows = """<tr><td style="padding:16px 18px;color:#94a3b8;font-size:13px;">
                        Aaj is category mein news nahi mili.
                      </td></tr>"""
        else:
            for i, item in enumerate(items, 1):
                rows += f"""
                <tr>
                  <td style="padding:12px 18px;border-bottom:1px solid #f1f5f9;vertical-align:top;">
                    <table width="100%" cellpadding="0" cellspacing="0"><tr>
                      <td style="width:28px;vertical-align:top;padding-top:2px;">
                        <b style="color:{meta['color']};font-size:13px;">#{i}</b>
                      </td>
                      <td style="padding-left:8px;">
                        <a href="{item.url}"
                           style="color:#1e293b;text-decoration:none;font-size:14px;
                                  font-weight:500;line-height:1.6;display:block;">
                          {item.title}
                        </a>
                        <span style="font-size:11px;color:#94a3b8;
                                     margin-top:3px;display:inline-block;">
                          📰 {item.source}
                        </span>
                      </td>
                    </tr></table>
                  </td>
                </tr>"""

        beats_html += f"""
        <div style="margin-bottom:22px;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
          <div style="background:{meta['color']};padding:12px 20px;">
            <table width="100%" cellpadding="0" cellspacing="0"><tr>
              <td>
                <span style="font-size:20px;vertical-align:middle;">{meta['icon']}</span>
                <span style="color:#fff;font-size:15px;font-weight:700;
                             margin-left:8px;vertical-align:middle;">{bi['hi']}</span>
                <span style="color:rgba(255,255,255,0.6);font-size:12px;
                             margin-left:6px;vertical-align:middle;">/ {bi['en']}</span>
              </td>
              <td style="text-align:right;">
                <span style="background:rgba(255,255,255,0.2);color:#fff;
                             font-size:11px;padding:3px 10px;border-radius:20px;">
                  {len(items)} khabrein
                </span>
              </td>
            </tr></table>
          </div>
          <div style="background:#fff;">
            <table width="100%" cellpadding="0" cellspacing="0">{rows}</table>
          </div>
        </div>"""

    return f"""<!DOCTYPE html><html lang="hi">
<head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Aaj Ki Khabrein</title></head>
<body style="margin:0;padding:0;background:#eef2f7;
             font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:28px 0;background:#eef2f7;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;">
  <tr><td style="background:#0f172a;border-radius:14px 14px 0 0;padding:30px 36px;text-align:center;">
    <p style="margin:0 0 8px;font-size:11px;color:#475569;letter-spacing:3px;text-transform:uppercase;">Daily Morning Digest</p>
    <h1 style="margin:0 0 4px;font-size:28px;font-weight:800;color:#f8fafc;">Aaj Ki Khabrein</h1>
    <p style="margin:0 0 2px;font-size:13px;color:#e2e8f0;font-weight:500;">{today_hi}</p>
    <p style="margin:0 0 16px;font-size:12px;color:#64748b;">{today_en}</p>
    <span style="background:rgba(148,163,184,0.12);color:#94a3b8;font-size:12px;padding:5px 16px;border-radius:20px;">
      {total} khabrein &nbsp;|&nbsp; 7 categories
    </span>
  </td></tr>
  <tr><td style="background:#1e3a5f;padding:10px 36px;text-align:center;">
    <p style="margin:0;font-size:12px;color:#93c5fd;line-height:1.6;">
      Aapki personalized morning briefing &nbsp;|&nbsp; Har beat mein khabrein &nbsp;|&nbsp; Powered by GNews
    </p>
  </td></tr>
  <tr><td style="background:#eef2f7;padding:20px 6px;">{beats_html}</td></tr>
  <tr><td style="background:#0f172a;border-radius:0 0 14px 14px;padding:20px 36px;text-align:center;">
    <p style="margin:0 0 6px;font-size:11px;color:#334155;line-height:1.8;">
      Sources: Hindustan Times, Indian Express, NDTV, BBC, Reuters & more
    </p>
    <p style="margin:0;font-size:11px;color:#1e293b;">
      Auto-generated &nbsp;|&nbsp; Roz 9:00 AM IST &nbsp;|&nbsp; {datetime.now().strftime("%I:%M %p")} IST
    </p>
  </td></tr>
</table></td></tr></table>
</body></html>"""


def send_email(html: str) -> bool:
    today_en = datetime.now().strftime("%d %b %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Aaj Ki Khabrein - {today_en} | Morning News Digest"
    msg["From"]    = CONFIG["sender_email"]
    msg["To"]      = CONFIG["receiver_email"]
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(CONFIG["sender_email"], CONFIG["sender_password"])
            s.sendmail(CONFIG["sender_email"], CONFIG["receiver_email"], msg.as_string())
        log.info(f"✅ Email sent to {CONFIG['receiver_email']}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("❌ Gmail auth failed")
    except Exception as e:
        log.error(f"❌ Email failed: {e}")
    return False


def main():
    log.info("=" * 60)
    log.info("Daily News Emailer - GNews API (Rate Limit Safe)")
    log.info("=" * 60)
    news = collect_news()
    send_email(build_html(news))
    log.info("Done")


if __name__ == "__main__":
    main()
