"""
Daily Morning News Emailer — GitHub Actions Version
Bilingual (Hindi + English) | 9:00 AM IST daily
"""

import os, smtplib, hashlib, time, random, logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ── Credentials come from GitHub Secrets ─────────────────────
CONFIG = {
    "sender_email":    os.environ["SENDER_EMAIL"],
    "sender_password": os.environ["SENDER_PASSWORD"],
    "receiver_email":  os.environ["RECEIVER_EMAIL"],
    "news_per_beat":   10,
}

BEATS = ["National","International","Politics","Sports",
         "Entertainment","Science & Tech","City News"]

BEAT_BILINGUAL = {
    "National":       {"hi": "राष्ट्रीय",      "en": "National"},
    "International":  {"hi": "अंतर्राष्ट्रीय",  "en": "International"},
    "Politics":       {"hi": "राजनीति",         "en": "Politics"},
    "Sports":         {"hi": "खेल",             "en": "Sports"},
    "Entertainment":  {"hi": "मनोरंजन",         "en": "Entertainment"},
    "Science & Tech": {"hi": "विज्ञान & टेक",   "en": "Science & Tech"},
    "City News":      {"hi": "शहर",             "en": "City News"},
}

SOURCES = [
    {"name": "Hindustan Times", "url": "https://www.hindustantimes.com/",
     "selector": "h3.hdg3 a, .storyShortDetail a, .cartHolder h3 a, h2 a"},
    {"name": "Indian Express",  "url": "https://indianexpress.com/",
     "selector": "h2.title a, h3.title a, .articles h2 a, article h2 a"},
    {"name": "News18",          "url": "https://www.news18.com/",
     "selector": ".blog-list h3 a, .story-listing h3 a, article h3 a, h3 a"},
    {"name": "Moneycontrol",    "url": "https://www.moneycontrol.com/",
     "selector": "h2 a, .clearfix li a, .linked-news a"},
    {"name": "Firstpost",       "url": "https://www.firstpost.com/",
     "selector": "h2 a, h3 a, .story-title a"},
    {"name": "ABP Live",        "url": "https://www.abplive.com/",
     "selector": "h2 a, h3 a, .post-title a, .headline a"},
    {"name": "Live Hindustan",  "url": "https://www.livehindustan.com/",
     "selector": "h2 a, h3 a, .news-item a, .heading a"},
]

BEAT_KEYWORDS = {
    "National":       ["india","national","delhi","central government","modi","parliament",
                       "bharat","supreme court","high court","election commission",
                       "rajya sabha","lok sabha","cbi","ed "],
    "International":  ["world","global","international","usa","us ","china","russia",
                       "uk ","pakistan","israel","europe","un ","nato","foreign",
                       "biden","trump","war","ukraine","iran","saudi"],
    "Politics":       ["party","bjp","congress","aap","sp ","bsp","election","vote",
                       "minister","cm ","chief minister","opposition","rally","political",
                       "governor","mla","mp ","yogi","rahul"],
    "Sports":         ["cricket","ipl","football","hockey","tennis","badminton","olympic",
                       "sports","match","tournament","player","team india","bcci","fifa",
                       "trophy","league","virat","rohit","neeraj","cwc"],
    "Entertainment":  ["bollywood","film","movie","actor","actress","cinema","music",
                       "celebrity","award","ott","netflix","series","web series","singer",
                       "dance","tv show","deepika","shahrukh","salman","ranveer"],
    "Science & Tech": ["tech","technology","science","ai ","artificial intelligence",
                       "space","isro","nasa","startup","app","software","gadget","phone",
                       "internet","cyber","research","innovation","electric vehicle",
                       "ev ","5g","satellite"],
    "City News":      ["mumbai","delhi ncr","bangalore","bengaluru","hyderabad","chennai",
                       "kolkata","pune","ahmedabad","noida","gurgaon","lucknow","jaipur",
                       "local","city","traffic","metro","municipal","ward","mayor",
                       "patna","bhopal"],
}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


@dataclass
class NewsItem:
    title: str; url: str; source: str
    beat: str = "National"; score: float = 0.0
    fingerprint: str = field(init=False)
    def __post_init__(self):
        self.fingerprint = hashlib.md5(
            " ".join(self.title.lower().split()).encode()).hexdigest()


def assign_beat(title: str) -> str:
    t = title.lower()
    scores = {b: sum(1 for kw in kws if kw in t)
              for b, kws in BEAT_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "National"


def news_value_score(title: str) -> float:
    t, score = title.lower(), 5.0
    for w in ["breaking","exclusive","major","crisis","attack","death","arrest",
              "resign","record","historic","banned","verdict","blast","flood",
              "earthquake","killed","scam","fraud","terror"]:
        if w in t: score += 1.5
    for w in ["sponsored","advertisement","buy","offer","sale","top 10","how to","tips"]:
        if w in t: score -= 3.0
    return max(0.0, score)


def scrape_source(src: dict) -> list:
    items, seen = [], set()
    try:
        r = requests.get(src["url"], headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        base = "{0.scheme}://{0.netloc}".format(urlparse(src["url"]))
        for tag in soup.select(src["selector"])[:80]:
            title = tag.get_text(strip=True)
            href  = tag.get("href","") or ""
            if not title or len(title) < 25 or title in seen: continue
            if href.startswith("/"): href = base + href
            elif not href.startswith("http"): continue
            seen.add(title)
            items.append(NewsItem(title=title, url=href, source=src["name"],
                                  beat=assign_beat(title),
                                  score=news_value_score(title)))
        log.info(f"✓  {src['name']:20s} → {len(items)} items")
    except Exception as e:
        log.warning(f"✗  {src['name']:20s} → {e}")
    return items


def collect_news() -> dict:
    all_items = []
    for src in SOURCES:
        all_items.extend(scrape_source(src))
        time.sleep(random.uniform(1.0, 2.2))
    seen, unique = set(), []
    for item in all_items:
        if item.fingerprint not in seen:
            seen.add(item.fingerprint); unique.append(item)
    log.info(f"Total unique: {len(unique)}")
    cat = {b: [] for b in BEATS}
    for item in unique: cat[item.beat].append(item)
    for b in BEATS:
        cat[b].sort(key=lambda x: x.score, reverse=True)
        cat[b] = cat[b][:CONFIG["news_per_beat"]]
    return cat


# ── Email Template ────────────────────────────────────────────
BEAT_META = {
    "National":       {"color":"#1a56db","icon":"🇮🇳"},
    "International":  {"color":"#0e9f6e","icon":"🌍"},
    "Politics":       {"color":"#7e3af2","icon":"🏛️"},
    "Sports":         {"color":"#d97706","icon":"🏆"},
    "Entertainment":  {"color":"#e02424","icon":"🎬"},
    "Science & Tech": {"color":"#0891b2","icon":"🔬"},
    "City News":      {"color":"#059669","icon":"🏙️"},
}

HINDI_MONTHS = {"January":"जनवरी","February":"फ़रवरी","March":"मार्च",
                "April":"अप्रैल","May":"मई","June":"जून","July":"जुलाई",
                "August":"अगस्त","September":"सितंबर","October":"अक्टूबर",
                "November":"नवंबर","December":"दिसंबर"}
HINDI_DAYS   = {"Monday":"सोमवार","Tuesday":"मंगलवार","Wednesday":"बुधवार",
                "Thursday":"गुरुवार","Friday":"शुक्रवार",
                "Saturday":"शनिवार","Sunday":"रविवार"}


def hindi_date() -> str:
    n = datetime.now()
    return (f"{HINDI_DAYS.get(n.strftime('%A'),n.strftime('%A'))}, "
            f"{n.day} {HINDI_MONTHS.get(n.strftime('%B'),n.strftime('%B'))} {n.year}")


def build_html(news_by_beat: dict) -> str:
    total     = sum(len(v) for v in news_by_beat.values())
    today_hi  = hindi_date()
    today_en  = datetime.now().strftime("%A, %d %B %Y")
    beats_html = ""

    for beat in BEATS:
        items = news_by_beat.get(beat, [])
        if not items: continue
        meta, bi = BEAT_META[beat], BEAT_BILINGUAL[beat]
        rows = ""
        for i, item in enumerate(items, 1):
            rows += f"""
            <tr>
              <td style="padding:12px 18px;border-bottom:1px solid #f1f5f9;vertical-align:top;">
                <table width="100%" cellpadding="0" cellspacing="0"><tr>
                  <td style="width:24px;vertical-align:top;">
                    <b style="color:{meta['color']};font-size:13px;">#{i}</b>
                  </td>
                  <td style="padding-left:10px;">
                    <a href="{item.url}" style="color:#1e293b;text-decoration:none;
                       font-size:14px;font-weight:500;line-height:1.6;display:block;">
                      {item.title}
                    </a>
                    <span style="font-size:11px;color:#94a3b8;margin-top:3px;display:inline-block;">
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
                <span style="font-size:18px;vertical-align:middle;">{meta['icon']}</span>
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

  <!-- HEADER -->
  <tr><td style="background:#0f172a;border-radius:14px 14px 0 0;padding:30px 36px;text-align:center;">
    <p style="margin:0 0 8px;font-size:11px;color:#475569;letter-spacing:3px;text-transform:uppercase;">
      Daily Morning Digest
    </p>
    <h1 style="margin:0 0 4px;font-size:28px;font-weight:800;color:#f8fafc;">☀️ आज की खबरें</h1>
    <p style="margin:0 0 2px;font-size:13px;color:#e2e8f0;font-weight:500;">{today_hi}</p>
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
      &nbsp;|&nbsp; 7 trusted sources &nbsp;|&nbsp; Duplicates removed
      &nbsp;|&nbsp; Ranked by news value
    </p>
  </td></tr>

  <!-- BODY -->
  <tr><td style="background:#eef2f7;padding:20px 6px;">
    {beats_html}
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#0f172a;border-radius:0 0 14px 14px;
                 padding:20px 36px;text-align:center;">
    <p style="margin:0 0 6px;font-size:11px;color:#334155;line-height:1.8;">
      📰 Hindustan Times &nbsp;·&nbsp; Indian Express &nbsp;·&nbsp; News18
      &nbsp;·&nbsp; Moneycontrol &nbsp;·&nbsp; Firstpost
      &nbsp;·&nbsp; ABP Live &nbsp;·&nbsp; Live Hindustan
    </p>
    <p style="margin:0;font-size:11px;color:#1e293b;">
      Auto-generated · रोज 9:00 AM IST · {datetime.now().strftime("%I:%M %p")} IST
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
            s.sendmail(CONFIG["sender_email"], CONFIG["receiver_email"], msg.as_string())
        log.info(f"✅  Email sent → {CONFIG['receiver_email']}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("❌  Gmail auth failed — check SENDER_PASSWORD secret")
    except Exception as e:
        log.error(f"❌  Email failed: {e}")
    return False


def main():
    log.info("=" * 55)
    log.info("🚀  Daily News Emailer (GitHub Actions) — Starting")
    log.info("=" * 55)
    news = collect_news()
    send_email(build_html(news))
    log.info("Done ✓")

if __name__ == "__main__":
    main()
