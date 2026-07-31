"""
Daily Morning News Emailer — RSS Feed Based
GitHub Actions pe chalti hai | 9:00 AM IST daily
Bilingual (Hindi + English)
"""

import os, smtplib, hashlib, time, logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

# ── Credentials (GitHub Secrets se aate hain) ────────────────
CONFIG = {
    "sender_email":    os.environ["SENDER_EMAIL"],
    "sender_password": os.environ["SENDER_PASSWORD"],
    "receiver_email":  os.environ["RECEIVER_EMAIL"],
    "news_per_beat":   10,
}

# ── Beats ────────────────────────────────────────────────────
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

# ── RSS Feeds — har beat ke liye dedicated feeds ─────────────
RSS_FEEDS = {
    "National": [
        "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
        "https://indianexpress.com/section/india/feed/",
        "https://www.news18.com/rss/india.xml",
        "https://www.firstpost.com/rss/india.xml",
        "https://www.livehindustan.com/rss/national.xml",
        "https://www.bhaskar.com/rss-feed/1061/",
        "https://news.google.com/rss/search?q=india+national+news&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "International": [
        "https://www.hindustantimes.com/feeds/rss/world-news/rssfeed.xml",
        "https://indianexpress.com/section/world/feed/",
        "https://www.news18.com/rss/world.xml",
        "https://www.firstpost.com/rss/world.xml",
        "https://news.google.com/rss/search?q=world+international+news&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "Politics": [
        "https://indianexpress.com/section/political-pulse/feed/",
        "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
        "https://www.news18.com/rss/politics.xml",
        "https://www.firstpost.com/rss/politics.xml",
        "https://news.google.com/rss/search?q=india+politics+BJP+Congress+election&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "Sports": [
        "https://www.hindustantimes.com/feeds/rss/sports/rssfeed.xml",
        "https://indianexpress.com/section/sports/feed/",
        "https://www.news18.com/rss/sports.xml",
        "https://www.firstpost.com/rss/sports.xml",
        "https://news.google.com/rss/search?q=india+cricket+sports&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "Entertainment": [
        "https://www.hindustantimes.com/feeds/rss/entertainment/rssfeed.xml",
        "https://indianexpress.com/section/entertainment/feed/",
        "https://www.news18.com/rss/entertainment.xml",
        "https://www.firstpost.com/rss/entertainment.xml",
        "https://news.google.com/rss/search?q=bollywood+entertainment+movies&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "Science & Tech": [
        "https://www.hindustantimes.com/feeds/rss/technology/rssfeed.xml",
        "https://indianexpress.com/section/technology/feed/",
        "https://www.news18.com/rss/tech.xml",
        "https://www.firstpost.com/rss/tech.xml",
        "https://news.google.com/rss/search?q=technology+science+ISRO+AI+india&hl=en-IN&gl=IN&ceid=IN:en",
    ],
    "City News": [
        "https://www.hindustantimes.com/feeds/rss/cities/rssfeed.xml",
        "https://indianexpress.com/section/cities/feed/",
        "https://www.livehindustan.com/rss/city.xml",
        "https://news.google.com/rss/search?q=delhi+mumbai+bangalore+city+news&hl=en-IN&gl=IN&ceid=IN:en",
    ],
}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
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
    beat: str = "National"
    score: float = 0.0
    fingerprint: str = field(init=False)

    def __post_init__(self):
        self.fingerprint = hashlib.md5(
            " ".join(self.title.lower().split()).encode()
        ).hexdigest()


def news_value_score(title: str) -> float:
    t, score = title.lower(), 5.0
    high = ["breaking", "exclusive", "major", "crisis", "attack", "death",
            "arrest", "resign", "record", "historic", "banned", "verdict",
            "blast", "flood", "earthquake", "killed", "scam", "fraud", "terror",
            "win", "champion", "final", "launch", "first"]
    low  = ["sponsored", "advertisement", "buy", "offer", "sale", "top 10",
            "how to", "tips", "tricks", "quiz", "horoscope"]
    for w in high:
        if w in t: score += 1.5
    for w in low:
        if w in t: score -= 3.0
    return max(0.0, score)


def fetch_rss(url: str, beat: str) -> list:
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        # Try xml parser first, fallback to lxml
        for parser in ["xml", "lxml-xml", "lxml"]:
            try:
                soup = BeautifulSoup(r.content, parser)
                rss_items = soup.find_all("item")
                if rss_items:
                    break
            except Exception:
                continue

        source_name = url.split("/")[2].replace("www.", "").replace("news.", "")

        for item in rss_items[:30]:
            try:
                title_tag = item.find("title")
                link_tag  = item.find("link") or item.find("guid")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                link  = (link_tag.get_text(strip=True)
                         if link_tag else url)
                if not title or len(title) < 15:
                    continue
                # Clean title — remove source suffix like "- Hindustan Times"
                for suffix in [" - Hindustan Times", " - Indian Express",
                                " | News18", " - Firstpost", " - ABP Live",
                                " - Dainik Bhaskar", " - Live Hindustan",
                                " | Moneycontrol"]:
                    title = title.replace(suffix, "").strip()

                items.append(NewsItem(
                    title=title, url=link,
                    source=source_name, beat=beat,
                    score=news_value_score(title)
                ))
            except Exception:
                continue

        log.info(f"✓  {beat:15s} | {source_name:25s} → {len(items)} items")
    except Exception as e:
        log.warning(f"✗  {beat:15s} | {url[:50]:50s} → {e}")
    return items


def collect_news() -> dict:
    categorized = {beat: [] for beat in BEATS}
    seen_fingerprints = set()

    for beat, feeds in RSS_FEEDS.items():
        beat_items = []
        for feed_url in feeds:
            items = fetch_rss(feed_url, beat)
            for item in items:
                if item.fingerprint not in seen_fingerprints:
                    seen_fingerprints.add(item.fingerprint)
                    beat_items.append(item)
            time.sleep(0.5)

        beat_items.sort(key=lambda x: x.score, reverse=True)
        categorized[beat] = beat_items[:CONFIG["news_per_beat"]]
        log.info(f"✅  {beat:15s} → Final: {len(categorized[beat])} items")

    return categorized


# ── Email HTML Template ───────────────────────────────────────
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
            f"{n.day} {HINDI_MONTHS.get(n.strftime('%B'), n.strftime('%B'))} {n.year}")


def build_html(news_by_beat: dict) -> str:
    total    = sum(len(v) for v in news_by_beat.values())
    today_hi = hindi_date()
    today_en = datetime.now().strftime("%A, %d %B %Y")
    beats_html = ""

    for beat in BEATS:
        items = news_by_beat.get(beat, [])
        if not items:
            continue
        meta, bi = BEAT_META[beat], BEAT_BILINGUAL[beat]
        rows = ""
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
        <div style="margin-bottom:22px;border-radius:12px;overflow:hidden;
                    border:1px solid #e2e8f0;">
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
<table width="100%" cellpadding="0" cellspacing="0"
       style="padding:28px 0;background:#eef2f7;">
<tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0"
       style="max-width:640px;width:100%;">

  <!-- HEADER -->
  <tr><td style="background:#0f172a;border-radius:14px 14px 0 0;
                 padding:30px 36px;text-align:center;">
    <p style="margin:0 0 8px;font-size:11px;color:#475569;
              letter-spacing:3px;text-transform:uppercase;">
      Daily Morning Digest
    </p>
    <h1 style="margin:0 0 4px;font-size:28px;font-weight:800;color:#f8fafc;">
      ☀️ आज की खबरें
    </h1>
    <p style="margin:0 0 2px;font-size:13px;color:#e2e8f0;font-weight:500;">
      {today_hi}
    </p>
    <p style="margin:0 0 16px;font-size:12px;color:#64748b;">{today_en}</p>
    <span style="background:rgba(148,163,184,0.12);color:#94a3b8;
                 font-size:12px;padding:5px 16px;border-radius:20px;">
      {total} khabrein &nbsp;·&nbsp; 7 categories
    </span>
  </td></tr>

  <!-- INFO STRIP -->
  <tr><td style="background:#1e3a5f;padding:10px 36px;text-align:center;">
    <p style="margin:0;font-size:12px;color:#93c5fd;line-height:1.6;">
      🔔 <b style="color:#bfdbfe;">Aapki personalized morning briefing</b>
      &nbsp;|&nbsp; RSS-powered &nbsp;|&nbsp; Duplicates removed
      &nbsp;|&nbsp; Ranked by news value
    </p>
  </td></tr>

  <!-- BEATS -->
  <tr><td style="background:#eef2f7;padding:20px 6px;">
    {beats_html}
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#0f172a;border-radius:0 0 14px 14px;
                 padding:20px 36px;text-align:center;">
    <p style="margin:0 0 6px;font-size:11px;color:#334155;line-height:1.8;">
      📰 Hindustan Times · Indian Express · News18 · Moneycontrol
      · Firstpost · ABP Live · Live Hindustan · Dainik Bhaskar
    </p>
    <p style="margin:0;font-size:11px;color:#1e293b;">
      Auto-generated · रोज 9:00 AM IST ·
      {datetime.now().strftime("%I:%M %p")} IST
    </p>
  </td></tr>

</table></td></tr></table>
</body></html>"""


def send_email(html: str) -> bool:
    today_en = datetime.now().strftime("%d %b %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"☀️ आज की खबरें — {today_en} | Morning News Digest"
    msg["From"]    = CONFIG["sender_email"]
    msg["To"]      = CONFIG["receiver_email"]
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(CONFIG["sender_email"], CONFIG["sender_password"])
            s.sendmail(CONFIG["sender_email"],
                       CONFIG["receiver_email"], msg.as_string())
        log.info(f"✅  Email sent → {CONFIG['receiver_email']}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("❌  Gmail auth failed — check SENDER_PASSWORD secret")
    except Exception as e:
        log.error(f"❌  Email failed: {e}")
    return False


def main():
    log.info("=" * 60)
    log.info("🚀  Daily News Emailer (RSS) — Starting")
    log.info("=" * 60)
    news = collect_news()
    send_email(build_html(news))
    log.info("Done ✓")


if __name__ == "__main__":
    main()
