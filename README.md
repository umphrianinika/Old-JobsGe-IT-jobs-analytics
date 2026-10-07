# jobs.ge vacancy analytics

End-to-end pipeline: **scrape -> clean -> store -> analyse -> dashboard**.

- `scraper.py` - incremental scraper (retries, logging, list + detail pages) writing to SQLite; only new vacancies are fetched on each run
- `parse.py` - Georgian date parsing with year inference, salary regex, skill extraction (unit-tested)
- `app.py` - Streamlit dashboard: top employers, skill demand, hiring trend, time-to-deadline, salary table
- `.github/workflows/scrape.yml` - runs tests and scrapes daily, committing `jobs.db`

## Run
```
pip install -r requirements.txt
pytest
python scraper.py --pages 20
streamlit run app.py
```

## Setup note
Open one vacancy page, inspect the description block (F12) and set `DESC_SELECTOR` in `scraper.py`.
Respect the site's robots.txt/terms and keep the request delay.

## Findings
_Fill in after a few weeks of data: top skills, busiest employers, typical posting lifetime..._
