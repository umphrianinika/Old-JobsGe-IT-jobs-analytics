"""Streamlit dashboard:  streamlit run app.py"""
import sqlite3
import pandas as pd
import streamlit as st

from parse import normalize

st.set_page_config(page_title="jobs.ge analytics", layout="wide")


@st.cache_data(ttl=600)
def load():
    df = pd.read_sql("SELECT * FROM vacancies", sqlite3.connect("jobs.db"),
                     parse_dates=["posted", "deadline"])
    df["skills"] = df["skills"].fillna("").apply(lambda s: [x for x in s.split(",") if x])
    title, desc = df["title"].fillna(""), df["description"].fillna("")
    df["_title"] = title.map(normalize)
    df["_text"] = (title + " " + desc).map(normalize)
    df["days_open"] = (df["deadline"] - df["posted"]).dt.days
    return df


df = load()
st.title("jobs.ge vacancy analytics")
if df.empty:
    st.warning("jobs.db is empty - run `python scraper.py` first.")
    st.stop()

lo, hi = df["posted"].min().date(), df["posted"].max().date()
rng = st.sidebar.date_input("Posted between", (lo, hi), min_value=lo, max_value=hi)
skills_all = sorted({s for row in df["skills"] for s in row})
picked = st.sidebar.multiselect("Required skills (all)", skills_all)
q = st.sidebar.text_input("Title contains")
q2 = st.sidebar.text_input("Search full description (e.g. python)")

f = df
n2 = normalize(q2)
if n2:  # matches "full stack", "Full-Stack" and "fullstack" alike
    f = f[f["_text"].str.contains(n2, regex=False)
          | f["_text"].str.replace(" ", "", regex=False).str.contains(n2.replace(" ", ""), regex=False)]
if len(rng) == 2:
    f = f[(f["posted"].dt.date >= rng[0]) & (f["posted"].dt.date <= rng[1])]
for s in picked:
    f = f[f["skills"].apply(lambda x, s=s: s in x)]
n1 = normalize(q)
if n1:
    f = f[f["_title"].str.contains(n1, regex=False)
          | f["_title"].str.replace(" ", "", regex=False).str.contains(n1.replace(" ", ""), regex=False)]

c = st.columns(3)
c[0].metric("Vacancies", len(f))
c[1].metric("Employers", f["employer"].nunique())
c[2].metric("Median days open", f["days_open"].median())

l, r = st.columns(2)
l.subheader("Top employers")
l.bar_chart(f["employer"].value_counts().head(15))
r.subheader("Most requested skills")
r.bar_chart(f["skills"].explode().value_counts().head(15))
l.subheader("Postings per week")
l.line_chart(f.set_index("posted").resample("W").size())
r.subheader("Days between posting and deadline")
r.bar_chart(f["days_open"].dropna().clip(upper=90).value_counts().sort_index())

sal = f.dropna(subset=["salary_min"])
st.subheader(f"Vacancies with a stated salary ({len(sal)})")
st.dataframe(sal[["title", "employer", "salary_min", "salary_max", "currency", "url"]],
             use_container_width=True)
st.subheader("All vacancies")
st.dataframe(f[["title", "employer", "posted", "deadline", "url"]], use_container_width=True)
