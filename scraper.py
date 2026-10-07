"""Incremental jobs.ge scraper -> SQLite.

Usage:  python scraper.py --pages 20          # only fetches NEW vacancies
        python scraper.py --pages 200 --full  # re-walk every page
"""
import argparse
import logging
import sqlite3
import time
from datetime import date, datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from parse import english_url, extract_salary, extract_skills, parse_date, parse_detail

BASE = "https://jobs.ge/"
MIN_DESC = 200  # shorter than this = probably just the one-line summary
log = logging.getLogger("jobsge")

SCHEMA = """CREATE TABLE IF NOT EXISTS vacancies (
    url TEXT PRIMARY KEY, title TEXT, employer TEXT,
    posted TEXT, deadline TEXT, description TEXT,
    salary_min INTEGER, salary_max INTEGER, currency TEXT,
    skills TEXT, first_seen TEXT, detail_lang TEXT)"""


def make_session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (portfolio project; polite scraper)"
    retry = Retry(total=4, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def list_page(session, page, cid):
    r = session.get(BASE, params={"page": page, "q": "", "cid": cid, "lid": "", "jid": ""}, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "html.parser")
    rows = []
    for a in soup.find_all("a", class_="vip"):
        tds = a.find_parent("tr").find_all("td")
        if len(tds) < 6:
            continue
        rows.append({"url": urljoin(BASE, a["href"]), "title": a.get_text(strip=True),
                     "employer": tds[3].get_text(strip=True),
                     "posted_raw": tds[4].get_text(strip=True),
                     "deadline_raw": tds[5].get_text(strip=True)})
    return rows


def fetch_parsed(session, url):
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("fetch failed %s: %s", url, e)
        return None
    return parse_detail(r.content)


def detail_page(session, url):
    """Return (parsed, lang).

    1. Parse the Georgian page (some ads have the full text right there).
    2. If it contains the 'ინგლისურ ენაზე' link - or is just a short summary - also
       open the English page and append its text, so one search covers both.
    lang is 'ge' (Georgian page only) or 'ge+en' (English text merged in).
    """
    ge = fetch_parsed(session, url)
    if ge is None:
        return None, None
    link = ge["en_link"]
    if not link and len(ge["description"]) < MIN_DESC:
        link = english_url(url)  # no link found but page is thin: try the English URL
    if not link:
        return ge, "ge"
    en = fetch_parsed(session, urljoin(BASE, link))
    if en is None or not en["description"]:
        return ge, "ge"
    merged = dict(ge)
    merged["description"] = (ge["description"] + " " + en["description"]).strip()[:40000]
    return merged, "ge+en"


def reextract(db):
    """Recompute skills + salary from the stored text (no network). Run this after
    adding skills to the dictionary in parse.py."""
    rows = db.execute("SELECT url, title, description FROM vacancies").fetchall()
    for url, title, desc in rows:
        lo, hi, cur = extract_salary(desc or "")
        db.execute("UPDATE vacancies SET salary_min=?, salary_max=?, currency=?, skills=? WHERE url=?",
                   (lo, hi, cur, ",".join(extract_skills((title or "") + " " + (desc or ""))), url))
    db.commit()
    log.info("re-extracted skills/salary for %d vacancies", len(rows))


def refresh(db, session, delay):
    """Re-fetch rows saved by older versions or with too-short descriptions."""
    rows = db.execute("SELECT url, title FROM vacancies WHERE detail_lang IS NULL OR detail_lang = 'en' "
                      "OR description IS NULL OR length(description) < ?", (MIN_DESC,)).fetchall()
    log.info("refreshing %d vacancies", len(rows))
    for url, old_title in rows:
        d, lang = detail_page(session, url)
        if d is None:
            continue
        title = d["title"] or old_title or ""
        lo, hi, cur = extract_salary(d["description"])
        db.execute("UPDATE vacancies SET title=?, description=?, salary_min=?, salary_max=?, "
                   "currency=?, skills=?, detail_lang=? WHERE url=?",
                   (title, d["description"], lo, hi, cur,
                    ",".join(extract_skills(title + " " + d["description"])), lang, url))
        db.commit()
        time.sleep(delay)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=20)
    ap.add_argument("--cid", type=int, default=6)
    ap.add_argument("--db", default="jobs.db")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch stored vacancies with missing/short descriptions, then exit")
    ap.add_argument("--reextract", action="store_true",
                    help="recompute skills/salary from stored text (no network), then exit")
    ap.add_argument("--full", action="store_true", help="don't stop at already-known pages")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    db = sqlite3.connect(args.db)
    db.execute(SCHEMA)
    if "detail_lang" not in {c[1] for c in db.execute("PRAGMA table_info(vacancies)")}:
        db.execute("ALTER TABLE vacancies ADD COLUMN detail_lang TEXT")
    known = {u for (u,) in db.execute("SELECT url FROM vacancies")}
    if args.reextract:
        reextract(db)
        return
    session, today, added = make_session(), date.today(), 0
    if args.refresh:
        refresh(db, session, args.delay)
        return

    for page in range(1, args.pages + 1):
        rows = list_page(session, page, args.cid)
        if not rows:
            log.info("page %d empty - done", page)
            break
        new = [r for r in rows if r["url"] not in known]
        for r in new:
            d, lang = detail_page(session, r["url"])
            if d is None:
                continue
            desc = d["description"]
            title, employer = d["title"] or r["title"], d["employer"] or r["employer"]
            posted = parse_date(r["posted_raw"], today)
            deadline = parse_date(r["deadline_raw"], today, future=True, ref=posted)
            lo, hi, cur = extract_salary(desc)
            db.execute("INSERT OR IGNORE INTO vacancies VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (r["url"], title, employer, posted and posted.isoformat(),
                        deadline and deadline.isoformat(), desc, lo, hi, cur,
                        ",".join(extract_skills(title + " " + desc)),
                        datetime.now(timezone.utc).isoformat(), lang))
            known.add(r["url"])
            added += 1
            time.sleep(args.delay)
        db.commit()
        log.info("page %d: %d listings, %d new", page, len(rows), len(new))
        if not new and not args.full:
            log.info("page fully known - stopping (use --full to continue)")
            break
        time.sleep(args.delay)
    log.info("added %d vacancies, total %d", added,
             db.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0])


if __name__ == "__main__":
    main()
