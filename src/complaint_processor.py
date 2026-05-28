# FILE: src/complaint_processor.py
"""Complaint loading, Thai date parsing, severity scoring, and topic modeling."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


OUTPUT_DIR = Path("outputs")
CLOSED_STATUS = "ประเมินผลเสร็จสิ้น"


def parse_thai_date(date_str: object) -> dt.date | None:
    """Parse DD/MM/YYYY Buddhist Era text into a Common Era date."""
    if date_str is None or pd.isna(date_str):
        return None
    text = str(date_str).strip()
    if not text or text.lower() == "nan":
        return None
    match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", text)
    if not match:
        return None
    day, month, buddhist_year = map(int, match.groups())
    try:
        return dt.date(buddhist_year - 543, month, day)
    except ValueError:
        return None


def load_complaints(xlsx_path: str | Path) -> pd.DataFrame:
    """Load complaint workbook and add normalized date/status columns."""
    df = pd.read_excel(Path(xlsx_path), engine="openpyxl")
    for column in df.select_dtypes(include=["object"]).columns:
        df[column] = df[column].astype(str).str.strip()
    df["date_received"] = df["วันที่รับเรื่อง"].apply(parse_thai_date)
    df["date_completed"] = df["วันที่เสร็จ"].apply(parse_thai_date)
    df["is_open"] = df["สถานะ"] != CLOSED_STATUS
    today = dt.date.today()
    df["days_open"] = df.apply(
        lambda row: (today - row["date_received"]).days if row["is_open"] and row["date_received"] else np.nan,
        axis=1,
    )
    df["resolution_days"] = df.apply(
        lambda row: (row["date_completed"] - row["date_received"]).days
        if (not row["is_open"]) and row["date_received"] and row["date_completed"]
        else np.nan,
        axis=1,
    )
    df["เขต"] = df["เขต"].replace({"": "ไม่ระบุ", "nan": "ไม่ระบุ", "None": "ไม่ระบุ"}).fillna("ไม่ระบุ")
    df["ชุมชน"] = df["ชุมชน"].replace({"": "ไม่ระบุ", "nan": "ไม่ระบุ", "None": "ไม่ระบุ"}).fillna("ไม่ระบุ")
    print(f"Loaded {len(df)} complaints. Open: {int(df['is_open'].sum())} | Closed: {int((~df['is_open']).sum())}")
    return df


def _tokenize_thai(text: str) -> list[str]:
    """Tokenize Thai text with pythainlp when installed, otherwise use whitespace."""
    try:
        from pythainlp.tokenize import word_tokenize

        tokens = word_tokenize(text, engine="newmm", keep_whitespace=False)
    except Exception:
        tokens = re.findall(r"\S+", text)
    return [str(token).strip() for token in tokens if str(token).strip()]


def _lookup_base_severity(value: object, lookup: dict[str, int]) -> int:
    """Find severity by exact or partial complaint type match."""
    text = str(value).strip()
    if text in lookup:
        return int(lookup[text])
    for key, score in lookup.items():
        if key in text:
            return int(score)
    return 3


def apply_severity_scores(df: pd.DataFrame, severity_lookup_path: str | Path, keyword_path: str | Path) -> pd.DataFrame:
    """Add base severity, keyword boost, and capped severity score columns."""
    lookup = json.loads(Path(severity_lookup_path).read_text(encoding="utf-8"))
    keywords = json.loads(Path(keyword_path).read_text(encoding="utf-8"))
    result = df.copy()
    result["base_severity"] = result["ประเภทคำร้อง"].apply(lambda value: _lookup_base_severity(value, lookup))

    def boost_for_text(value: object) -> int:
        text = "" if pd.isna(value) else str(value)
        tokens = set(_tokenize_thai(text))
        boosts = [int(boost) for keyword, boost in keywords.items() if keyword in tokens or keyword in text]
        return max(boosts) if boosts else 0

    result["keyword_boost"] = result["เรื่องร้องทุกข์"].apply(boost_for_text)
    result["severity_score"] = (result["base_severity"] + result["keyword_boost"]).clip(upper=10).astype(int)
    print("Severity distribution:")
    print(result["severity_score"].value_counts().sort_index().to_string())
    return result


def compute_resolution_baseline(df: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    """Compute mean and median resolution days by complaint type and save JSON."""
    closed = df[(df["is_open"] == False) & df["resolution_days"].notna()].copy()
    baseline: dict[str, dict[str, float | int]] = {}
    if not closed.empty:
        grouped = closed.groupby("ประเภทคำร้อง")["resolution_days"].agg(["mean", "median", "count"]).sort_values("mean")
        for complaint_type, row in grouped.iterrows():
            baseline[str(complaint_type)] = {
                "mean_days": round(float(row["mean"]), 2),
                "median_days": round(float(row["median"]), 2),
                "count": int(row["count"]),
            }
        print("Top 5 fastest types:")
        print(grouped.head(5).to_string())
        print("Top 5 slowest types:")
        print(grouped.tail(5).to_string())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "resolution_baseline.json").write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
    return baseline


def _fallback_topic_model(processed_texts: list[str], n_topics: int) -> tuple[list[int], dict[int, str]]:
    """Create topic labels with TF-IDF and KMeans when BERTopic is unavailable."""
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    n_clusters = max(1, min(n_topics, len(processed_texts)))
    vectorizer = TfidfVectorizer(max_features=500)
    matrix = vectorizer.fit_transform(processed_texts)
    model = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
    topics = model.fit_predict(matrix).tolist()
    terms = np.array(vectorizer.get_feature_names_out())
    labels: dict[int, str] = {}
    for topic_id in range(n_clusters):
        center = model.cluster_centers_[topic_id]
        top_terms = terms[np.argsort(center)[-3:][::-1]]
        labels[topic_id] = "/".join(top_terms.tolist()) if len(top_terms) else f"topic_{topic_id}"
    return topics, labels


def run_topic_modeling(df: pd.DataFrame, n_topics: int = 10) -> pd.DataFrame:
    """Assign topic IDs and labels to complaint descriptions and save summary CSV."""
    result = df.copy()
    valid = result["เรื่องร้องทุกข์"].notna() & (result["เรื่องร้องทุกข์"].astype(str).str.len() > 5)
    texts = result.loc[valid, "เรื่องร้องทุกข์"].astype(str).tolist()
    result["topic_id"] = -1
    result["topic_label"] = "unassigned"
    if not texts:
        return result
    try:
        from pythainlp.corpus import thai_stopwords

        stopwords = set(thai_stopwords())
    except Exception:
        stopwords = set()
    processed = []
    for text in texts:
        tokens = [token for token in _tokenize_thai(text) if token not in stopwords and len(token) > 1]
        processed.append(" ".join(tokens) or text)
    try:
        from bertopic import BERTopic
        from sentence_transformers import SentenceTransformer

        embedding_model = SentenceTransformer("airesearch/wangchanberta-base-att-spm-uncased")
        topic_model = BERTopic(embedding_model=embedding_model, nr_topics=n_topics, min_topic_size=15, language="multilingual", verbose=False)
        topics, _ = topic_model.fit_transform(processed)
        labels = {
            int(topic_id): "/".join(str(word) for word, _ in topic_model.get_topic(topic_id)[:3])
            for topic_id in set(topics)
            if int(topic_id) >= 0 and topic_model.get_topic(topic_id)
        }
    except Exception:
        print("BERTopic unavailable, using TF-IDF + KMeans fallback")
        topics, labels = _fallback_topic_model(processed, n_topics)
    result.loc[valid, "topic_id"] = topics
    result.loc[valid, "topic_label"] = [labels.get(int(topic), f"topic_{topic}") for topic in topics]
    summary = result.loc[valid].groupby(["topic_id", "topic_label"]).size().reset_index(name="count").sort_values("count", ascending=False)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUTPUT_DIR / "complaint_topics.csv", index=False, encoding="utf-8-sig")
    print("Top topics:")
    print(summary.head(10).to_string(index=False))
    return result


def process_complaints(
    xlsx_path: str | Path,
    severity_lookup_path: str | Path,
    keyword_path: str | Path,
    run_nlp: bool = True,
) -> pd.DataFrame:
    """Run complaint loading, scoring, baseline, optional NLP, and save CSV output."""
    df = apply_severity_scores(load_complaints(xlsx_path), severity_lookup_path, keyword_path)
    compute_resolution_baseline(df)
    if run_nlp:
        df = run_topic_modeling(df)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / "complaints_enriched.csv", index=False, encoding="utf-8-sig")
    print(f"Complaints output saved -> {OUTPUT_DIR / 'complaints_enriched.csv'}")
    return df
