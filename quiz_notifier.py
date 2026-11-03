import os, re, json, smtplib, hashlib
from email.message import EmailMessage
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtp

URL = "https://ams.mitsgwalior.in/student/dashboard"
COOKIE = os.environ["AMS_COOKIE"]               # browser DevTools > Network > dashboard request > Cookie header
SMTP_USER = os.environ["GMAIL_USER"]
SMTP_PASS = os.environ["GMAIL_APP_PASSWORD"]    # Google Account > Security > App passwords
TO = os.environ.get("NOTIFY_TO", SMTP_USER)
REMIND_MIN = [60, 15, 5]                        # reminders before start
SELECTORS = "tr, li, .card"                     # adjust after inspecting the page
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")


def send(subject, body):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = SMTP_USER, TO, subject
    m.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(m)


def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save(st):
    json.dump(st, open(STATE, "w"), indent=1)


def parse_quizzes(html):
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for el in soup.select(SELECTORS):
        if el.select(SELECTORS):          # skip containers, keep innermost
            continue
        text = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if not re.search(r"quiz", text, re.I) or text in seen:
            continue
        seen.add(text)
        try:
            start = dtp.parse(text, fuzzy=True, dayfirst=True)
        except Exception:
            start = None
        out.append({"id": hashlib.md5(text.encode()).hexdigest(), "text": text, "start": start})
    return out


def main():
    st = load()
    r = requests.get(URL, headers={"Cookie": COOKIE, "User-Agent": "Mozilla/5.0"}, timeout=30)
    if "login" in r.url.lower() or r.status_code in (401, 403):
        if not st.get("_expired"):
            send("AMS session expired", "Update AMS_COOKIE in your notifier.")
            st["_expired"] = True
            save(st)
        return
    st.pop("_expired", None)

    now = datetime.now()                  # run on a machine set to IST
    for q in parse_quizzes(r.text):
        e = st.setdefault(q["id"], {"new": False, "rem": []})
        when = q["start"].strftime("%d %b %Y, %I:%M %p") if q["start"] else "time not found"
        if not e["new"]:
            send(f"New quiz posted ({when})", f"{q['text']}\n\nStart: {when}\n{URL}")
            e["new"] = True
        if q["start"]:
            mins = (q["start"] - now).total_seconds() / 60
            for m in REMIND_MIN:
                if 0 < mins <= m and m not in e["rem"]:
                    send(f"Quiz starts in {int(mins)} min ({when})", f"{q['text']}\n\n{URL}")
                    e["rem"].append(m)
                    break
    save(st)


if __name__ == "__main__":
    main()