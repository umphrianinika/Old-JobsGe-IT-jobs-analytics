from datetime import date
from parse import normalize, english_url, extract_salary, extract_skills, parse_date, parse_detail

T = date(2026, 10, 2)


def test_georgian_date():
    assert parse_date("2 ოქტომბერი", T) == date(2026, 10, 2)


def test_posted_rolls_back_year():
    assert parse_date("28 დეკემბერი", date(2026, 1, 3)) == date(2025, 12, 28)


def test_deadline_rolls_forward():
    ref = date(2025, 12, 28)
    assert parse_date("5 იანვარი", date(2025, 12, 28), future=True, ref=ref) == date(2026, 1, 5)


def test_numeric_and_bad_dates():
    assert parse_date("02.10.2026", T) == date(2026, 10, 2)
    assert parse_date("n/a", T) is None
    assert parse_date("31 ნოემბერი", T) is None


def test_salary():
    assert extract_salary("ხელფასი 2000-3000 ₾") == (2000, 3000, "GEL")
    assert extract_salary("Salary: 1 500 GEL") == (1500, 1500, "GEL")
    assert extract_salary("up to $4,000") == (4000, 4000, "USD")
    assert extract_salary("no pay info") == (None, None, None)


def test_skills():
    s = extract_skills("Python, SQL and Power BI; ინგლისური ენა; JavaScript")
    assert {"Python", "SQL", "Power BI", "JavaScript"} <= set(s)
    assert "Java" not in s


HTML = """<table><tr><td><table>
<tr><td>Ad title: <b>Full-Stack Developer</b></td></tr>
<tr><td>Provided By: <b><a href="#">York Towers</a></b></td></tr>
<tr><td>Published: <b>01 October</b> / Deadline: <b>01 November</b></td></tr>
<tr><td>Stack: PHP / React / Docker. Salary 3000-4000 $ <b>Apply now</b></td></tr>
</table></td></tr></table>"""


def test_english_url():
    assert english_url("https://jobs.ge/ge/?view=jobs&id=757647") == "https://jobs.ge/en/ads/?view=jobs&id=757647"
    assert english_url("https://jobs.ge/?view=client") is None


def test_parse_detail():
    d = parse_detail(HTML)
    assert d["title"] == "Full-Stack Developer" and d["employer"] == "York Towers"
    assert "Docker" in d["description"] and "Published" not in d["description"]
    assert extract_salary(d["description"]) == (3000, 4000, "USD")
    assert parse_date("01 October", T) == date(2026, 10, 1)


def test_parse_detail_fallback():
    assert "hello" in parse_detail("<html><body><p>hello</p></body></html>")["description"]


class FakeResp:
    def __init__(self, html): self.content = html.encode()
    def raise_for_status(self): pass


class FakeSession:
    def __init__(self, ge, en):
        self.ge, self.en, self.calls = ge, en, []
    def get(self, url, timeout=0):
        self.calls.append(url)
        return FakeResp(self.en if "/en/" in url else self.ge)


def _page(body):
    return ("<table><tr><td>დასახელება: <b>T</b></td></tr><tr><td>მომწოდებელი: <b>E</b></td></tr>"
            f"<tr><td>გამოქვეყნდა: x</td></tr><tr><td>{body}</td></tr></table>")


LINK = '<a href="/en/ads/?view=jobs&amp;id=1">ინგლისურ ენაზე</a>'
GE_URL = "https://jobs.ge/ge/?view=jobs&id=1"


def test_en_link_detected_but_nav_link_ignored():
    assert parse_detail(_page("იხილეთ " + LINK))["en_link"] == "/en/ads/?view=jobs&id=1"
    nav = '<a href="https://jobs.ge/en/?id=1&view=jobs">ENGLISH VERSION</a>'
    assert parse_detail(nav + _page("full georgian text"))["en_link"] is None


def test_follows_english_link_and_merges():
    from scraper import detail_page
    s = FakeSession(_page("მოკლე ტექსტი " + LINK), _page("We need python and SQL " * 3))
    d, lang = detail_page(s, GE_URL)
    assert lang == "ge+en" and "python" in d["description"] and "მოკლე" in d["description"]
    assert s.calls[1] == "https://jobs.ge/en/ads/?view=jobs&id=1"
    assert extract_skills(d["description"]) == ["Python", "SQL"]


def test_full_georgian_page_is_not_followed():
    from scraper import detail_page
    s = FakeSession(_page("სრული ტექსტი " * 40), _page("english"))
    d, lang = detail_page(s, GE_URL)
    assert lang == "ge" and len(s.calls) == 1


def test_thin_page_without_link_tries_english_url():
    from scraper import detail_page
    s = FakeSession(_page("short"), _page("Python developer needed"))
    d, lang = detail_page(s, GE_URL)
    assert lang == "ge+en" and "Python" in d["description"]


def test_link_text_not_counted_as_english_skill():
    d = parse_detail(_page("იხილეთ სრული ტექსტი " + LINK))
    assert "ინგლისურ" not in d["description"] and "English" not in extract_skills(d["description"])


def test_normalize_makes_search_separator_insensitive():
    assert normalize("Full-Stack  Developer") == "full stack developer"
    assert normalize("full stack") in normalize("We need a Full-Stack/React dev")
    assert "fullstack" in normalize("Full-Stack").replace(" ", "")


def test_fullstack_skill_variants():
    for txt in ("Full-Stack Developer", "full stack engineer", "Fullstack dev"):
        assert "Full-stack" in extract_skills(txt)
    assert {"Node.js", "PostgreSQL", "CI/CD"} <= set(extract_skills("Node.js, Postgres and CI/CD"))
