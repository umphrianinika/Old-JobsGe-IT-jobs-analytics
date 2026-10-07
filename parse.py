"""Pure parsing helpers: dates, salaries, skills. No network, easy to test."""
import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

GEO_MONTHS = {"იან": 1, "თებ": 2, "მარ": 3, "აპრ": 4, "მაი": 5, "ივნ": 6,
              "ივლ": 7, "აგვ": 8, "სექ": 9, "ოქტ": 10, "ნოე": 11, "დეკ": 12}
EN_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
             "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

_TEXT_DATE = re.compile(r"(\d{1,2})\s*([^\W\d_]{3,})")
_NUM_DATE = re.compile(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?")


def parse_date(text, today=None, future=False, ref=None):
    """Parse '2 ოქტომბერი', '02.10.2026' etc. into a date (or None).

    The site omits the year, so we infer it: posting dates are never far in the
    future (roll back a year), deadlines are never before the posting date
    (roll forward a year).
    """
    today = today or date.today()
    text = (text or "").strip().lower()
    day = month = year = None
    m = _NUM_DATE.search(text)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        if m.group(3):
            year = int(m.group(3)) + (2000 if len(m.group(3)) == 2 else 0)
    else:
        m = _TEXT_DATE.search(text)
        if not m:
            return None
        day = int(m.group(1))
        key = m.group(2)[:3]
        month = GEO_MONTHS.get(key) or EN_MONTHS.get(key)
        if not month:
            return None
    explicit_year = year is not None
    try:
        d = date(year or today.year, month, day)
    except ValueError:
        return None
    if explicit_year:
        return d
    if future:
        if ref and d < ref:
            d = d.replace(year=d.year + 1)
    elif d > today + timedelta(days=7):
        d = d.replace(year=d.year - 1)
    return d


_SALARY = re.compile(
    r"(\d[\d\s,]{2,8})(?:\s*[-–—]\s*(\d[\d\s,]{2,8}))?\s*(₾|gel|ლარ\w*|\$|usd|€|eur)",
    re.I)
_SALARY_PREFIX = re.compile(
    r"(₾|\$|€)\s*(\d[\d\s,]{2,8})(?:\s*[-–—]\s*(?:₾|\$|€)?\s*(\d[\d\s,]{2,8}))?")
_CURRENCY = {"₾": "GEL", "gel": "GEL", "$": "USD", "usd": "USD", "€": "EUR", "eur": "EUR"}


def _num(s):
    return int(re.sub(r"[\s,]", "", s))


def extract_salary(text):
    """Return (min, max, currency) or (None, None, None)."""
    m = _SALARY.search(text or "")
    if not m:
        m2 = _SALARY_PREFIX.search(text or "")
        if not m2:
            return None, None, None
        lo = _num(m2.group(2))
        hi = _num(m2.group(3)) if m2.group(3) else lo
        return min(lo, hi), max(lo, hi), _CURRENCY[m2.group(1)]
    lo = _num(m.group(1))
    hi = _num(m.group(2)) if m.group(2) else lo
    cur = m.group(3).lower()
    cur = "GEL" if cur.startswith("ლარ") else _CURRENCY.get(cur, cur.upper())
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi, cur


def normalize(s):
    """Lowercase and turn every run of punctuation/hyphens/slashes into one space,
    so 'Full-Stack', 'full stack' and 'FULL  STACK' all become 'full stack'."""
    return " ".join(re.sub(r"[\W_]+", " ", (s or "").lower()).split())


SKILLS = {
    "Full-stack": r"full[\s\-]?stack", "Front-end": r"front[\s\-]?end",
    "Back-end": r"back[\s\-]?end", "Node.js": r"node\.?js", "Next.js": r"next\.?js",
    "PostgreSQL": r"postgre(?:s|sql)", "REST API": r"\brest(?:ful)?\s*apis?\b",
    "CI/CD": r"ci\s*/\s*cd", "Kubernetes": r"kubernetes|\bk8s\b",
    "Python": r"\bpython\b", "SQL": r"\bsql\b", "Excel": r"\bexcel\b|ექსელ",
    "Power BI": r"power\s*bi", "Tableau": r"\btableau\b",
    "JavaScript": r"\bjavascript\b|\bjs\b", "TypeScript": r"\btypescript\b",
    "Java": r"\bjava\b", "C#/.NET": r"c#|\.net\b", "PHP": r"\bphp\b",
    "React": r"\breact\b", "Docker": r"\bdocker\b", "AWS": r"\baws\b",
    "Git": r"\bgit\b", "Linux": r"\blinux\b", "1C": r"\b1c\b|1ც",
    "SAP": r"\bsap\b", "Photoshop": r"photoshop", "Figma": r"\bfigma\b",
    "SEO": r"\bseo\b", "Accounting": r"accounting|ბუღალტერ",
    "English": r"english|ინგლისურ", "Russian": r"russian|რუსულ",
    "Driving licence": r"driving licen|მართვის მოწმობ",
}
_SKILL_RE = {k: re.compile(v, re.I) for k, v in SKILLS.items()}


def extract_skills(text):
    return sorted(k for k, rx in _SKILL_RE.items() if rx.search(text or ""))


def english_url(url):
    """List links point at the Georgian page (summary only); the full ad text
    lives on the English version of the same id."""
    m = re.search(r"[?&]id=(\d+)", url)
    return f"https://jobs.ge/en/ads/?view=jobs&id={m.group(1)}" if m else None


EN_LINK = re.compile(r"/en/ads/\?(?=[^#]*view=jobs)(?=[^#]*\bid=\d+)")


def _find_en_link(root):
    """The 'full text in English' link tag (ინგლისურ ენაზე), or None.
    The site-wide 'ENGLISH VERSION' nav link (/en/?id=...) deliberately doesn't match."""
    for a in root.find_all("a", href=True):
        if EN_LINK.search(a["href"]) or "ინგლისურ ენაზე" in a.get_text():
            return a
    return None


def parse_detail(html):
    """Parse a vacancy page into {title, employer, description}.

    The ad is a 4-row table: 'Ad title:', 'Provided By:', 'Published: / Deadline:',
    then the full description. Georgian labels are accepted too. If the table
    can't be found we fall back to the whole page text.
    """
    soup = BeautifulSoup(html, "html.parser")
    label = soup.find(string=re.compile(r"^\s*(Ad title|დასახელება):"))
    cell = label.find_parent("td") if label else None
    table = cell.find_parent("table") if cell else None
    # Read the link's address, then drop the tag: its text ("in English") would
    # otherwise be counted as an English-language requirement by extract_skills.
    link_tag = _find_en_link(table if table is not None else soup)
    en_link = link_tag["href"] if link_tag else None
    if link_tag:
        link_tag.decompose()
    if table is None:
        text = soup.body.get_text(" ", strip=True) if soup.body else ""
        return {"title": None, "employer": None, "en_link": en_link,
                "description": " ".join(text.split())[:20000]}
    title = employer = None
    parts = []
    for row in table.find_all("tr"):
        if row.find_parent("table") is not table:
            continue  # skip rows of nested tables
        text = row.get_text(" ", strip=True)
        low = text.lower()
        if low.startswith(("ad title:", "დასახელება:")):
            title = text.split(":", 1)[1].strip()
        elif low.startswith(("provided by:", "მომწოდებელი:")):
            employer = text.split(":", 1)[1].strip()
        elif low.startswith(("published:", "გამოქვეყნდა:")):
            continue
        elif text:
            parts.append(text)
    return {"title": title, "employer": employer, "en_link": en_link,
            "description": " ".join(" ".join(parts).split())[:20000]}
