"""Sentiment, topic and trend analysis — separate from opportunity detection.

Sentiment never writes vacancy state. Trends are aggregates of stored observations (reproducible),
with sample sizes and unique-source counts; small samples are flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from unjobless.db.models import JobVacancy, RawSourceDocument, RawSourceVersion, SentimentAnalysis, TopicObservation, TrendObservation
from unjobless.domain.enums import Sentiment, SentimentTarget

MIN_SAMPLE = 5

POS = [r"\b(great|good|amazing|supportive|helpful|kind|love[d]?|recommend(ed)?|fair|friendly|learned a lot|belajar banyak|seru|bagus|baik|ramah|suportif|nyaman|worth it|mantap|keren)\b"]
NEG = [r"\b(toxic|terrible|awful|bad|worst|underpaid|overworked|ghost(ed|ing)?|unfair|rude|stress(ful)?|burn ?out|telat|kecil banget|jelek|buruk|parah|capek|lembur terus|gak dibayar|nggak dibayar|ribet|lama banget|kecewa)\b"]
NEGATION = re.compile(r"\b(not|no|never|tidak|nggak|gak|ga|bukan|kurang)\s+$", re.I)
SARCASM = re.compile(r"(/s\b|\byeah right\b|\bas if\b|\bwkwk|\bhaha\b.*\b(great|mantap)\b|\bmantap\b.*\b(telat|toxic)\b)", re.I)
ASPECTS: dict[SentimentTarget, str] = {
    SentimentTarget.RECRUITMENT_PROCESS: r"(recruit|rekrut|application|lamaran|seleksi|hiring process|proses|hr\b|ghost)",
    SentimentTarget.INTERVIEW: r"(interview|wawancara|user interview|technical test)",
    SentimentTarget.INTERNSHIP_EXPERIENCE: r"(internship|magang|intern\b)",
    SentimentTarget.MANAGEMENT: r"(manager|management|atasan|mentor|lead|bos|supervisor)",
    SentimentTarget.WORK_CULTURE: r"(culture|kultur|budaya|environment|lingkungan|toxic)",
    SentimentTarget.COMPENSATION: r"(salary|gaji|pay|paid|uang saku|stipend|tunjangan|underpaid)",
    SentimentTarget.WORKLOAD: r"(workload|overtime|lembur|overworked|long hours|beban kerja|capek)",
    SentimentTarget.JOB_SEARCH: r"(job search|cari kerja|nganggur|lamar|apply(ing)? to)",
}
TOPICS: dict[str, str] = {
    "internship_opening": r"(buka magang|open internship|internship (program|position)|lowongan magang|hiring interns?)",
    "recruitment_batch": r"(batch \d+|oprec|open recruitment|recruitment season)",
    "hiring_freeze": r"(hiring freeze|stop hiring|pause hiring|freeze rekrutmen)",
    "layoffs": r"(layoffs?|phk|pemutusan hubungan kerja)",
    "campus_hiring": r"(campus (hiring|recruitment)|career fair|job fair|bursa kerja)",
    "referral": r"(referral|refer\b|orang dalam)",
    "interview_experience": r"(interview|wawancara)",
    "application_outcome": r"(rejected|ditolak|diterima|accepted|offer letter|got the offer|lolos)",
    "salary_transparency": r"(salary range|gaji (berapa|range)|transparan|stipend|uang saku)",
    "work_culture": r"(culture|kultur|toxic|lingkungan kerja)",
    "remote_work": r"(remote|wfh|wfa|hybrid)",
    "graduate_program": r"(graduate program|management trainee|odp|\bmt\b program)",
    "career_program": r"(bootcamp|fellowship|pelatihan|workshop|webinar)",
}


@dataclass
class SentimentObs:
    target: SentimentTarget
    polarity: Sentiment
    confidence: float
    sarcasm_uncertain: bool
    excerpt: str


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 3]


def _hits(pats: list[str], s: str) -> int:
    n = 0
    for p in pats:
        for m in re.finditer(p, s, re.I):
            n += -1 if NEGATION.search(s[: m.start()][-15:]) else 1
    return n


def analyze_sentiment(text: str) -> list[SentimentObs]:
    out: dict[SentimentTarget, SentimentObs] = {}
    for sent in _sentences(text)[:80]:
        pos, neg = _hits(POS, sent), _hits(NEG, sent)
        if pos == 0 and neg == 0:
            continue
        if pos > 0 and neg > 0:
            pol = Sentiment.MIXED
        elif pos > 0:
            pol = Sentiment.POSITIVE
        elif neg > 0:
            pol = Sentiment.NEGATIVE
        else:  # negated praise / negated complaint
            pol = Sentiment.NEGATIVE if pos < 0 else Sentiment.POSITIVE if neg < 0 else Sentiment.UNCERTAIN
        sarcasm = bool(SARCASM.search(sent))
        targets = [t for t, pat in ASPECTS.items() if re.search(pat, sent, re.I)] or [SentimentTarget.COMPANY]
        conf = min(0.9, 0.55 + 0.1 * (abs(pos) + abs(neg))) * (0.6 if sarcasm else 1.0)
        for t in targets:
            prev = out.get(t)
            if prev and prev.polarity != pol:
                pol2 = Sentiment.MIXED
                out[t] = SentimentObs(t, pol2, min(prev.confidence, conf), prev.sarcasm_uncertain or sarcasm, prev.excerpt)
            elif not prev or conf > prev.confidence:
                out[t] = SentimentObs(t, Sentiment.UNCERTAIN if sarcasm and conf < 0.4 else pol, round(conf, 2), sarcasm, sent[:400])
    return list(out.values())


def detect_topics(text: str) -> list[tuple[str, float, str]]:
    out = []
    for topic, pat in TOPICS.items():
        m = re.search(pat, text, re.I)
        if m:
            s, e = max(0, m.start() - 60), min(len(text), m.end() + 60)
            out.append((topic, 0.7, text[s:e].strip()))
    return out


def store_observations(db: Session, version: RawSourceVersion, text: str, *, company_id: int | None, source_id: int | None, first_party: bool, ai_payload: dict[str, Any] | None = None) -> tuple[int, int]:
    db.execute(delete(SentimentAnalysis).where(SentimentAnalysis.raw_version_id == version.id))
    db.execute(delete(TopicObservation).where(TopicObservation.raw_version_id == version.id))
    observed = version.source_published_at or version.collected_at
    n_s = 0
    obs = analyze_sentiment(text)
    method = "rules"
    if ai_payload:
        method = "ai"
        obs = [
            SentimentObs(SentimentTarget(s["target"]), Sentiment(s["polarity"]), float(s["confidence"]), bool(s["sarcasm_uncertain"]), s["excerpt"])
            for s in ai_payload.get("sentiments", []) if s.get("excerpt") and s["excerpt"] in text
        ]
    for o in obs:
        db.add(SentimentAnalysis(
            raw_version_id=version.id, source_id=source_id, company_id=company_id, target=o.target, polarity=o.polarity,
            confidence=o.confidence, sarcasm_uncertain=o.sarcasm_uncertain, is_first_party=first_party,
            language=version.language, evidence_excerpt=o.excerpt, method=method, observed_at=observed,
        ))
        n_s += 1
    topics = detect_topics(text)
    if ai_payload:
        topics += [(t["topic"][:60], float(t["confidence"]), t["excerpt"]) for t in ai_payload.get("topics", []) if t.get("excerpt") in text]
    seen = set()
    for topic, conf, ex in topics:
        if topic in seen:
            continue
        seen.add(topic)
        db.add(TopicObservation(raw_version_id=version.id, source_id=source_id, company_id=company_id, topic=topic, confidence=conf, evidence_excerpt=ex[:1000], observed_at=observed))
    db.flush()
    return n_s, len(seen)


def refresh_trends(db: Session, *, weeks: int = 12, today: date | None = None) -> int:
    """Recompute weekly trend observations from stored records (deterministic, reproducible)."""
    today = today or date.today()
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    db.execute(delete(TrendObservation).where(TrendObservation.window_start >= start))
    n = 0
    for w in range(weeks):
        ws = start + timedelta(weeks=w)
        we = ws + timedelta(days=6)
        topic_rows = db.execute(
            select(TopicObservation.topic, func.count(), func.count(func.distinct(TopicObservation.source_id)), func.count(func.distinct(TopicObservation.company_id)))
            .where(func.date(TopicObservation.observed_at).between(ws, we)).group_by(TopicObservation.topic)
        ).all()
        for topic, c, us, uc in topic_rows:
            db.add(TrendObservation(metric="topic_mentions", dimension=topic, window_start=ws, window_end=we, count=c, unique_sources=us, unique_companies=uc))
            n += 1
        vc = db.execute(
            select(func.count(), func.count(func.distinct(JobVacancy.company_id))).where(func.date(JobVacancy.first_seen_at).between(ws, we), JobVacancy.merged_into_id.is_(None))
        ).one()
        vs = db.execute(
            select(func.count(func.distinct(RawSourceDocument.source_id))).where(func.date(RawSourceDocument.first_collected_at).between(ws, we))
        ).scalar_one()
        db.add(TrendObservation(metric="new_vacancies", dimension="all", window_start=ws, window_end=we, count=vc[0], unique_sources=vs, unique_companies=vc[1]))
        sent = db.execute(
            select(SentimentAnalysis.polarity, func.count(), func.count(func.distinct(SentimentAnalysis.source_id)), func.count(func.distinct(SentimentAnalysis.company_id)))
            .where(func.date(SentimentAnalysis.observed_at).between(ws, we)).group_by(SentimentAnalysis.polarity)
        ).all()
        for pol, c, us, uc in sent:
            db.add(TrendObservation(metric="sentiment", dimension=pol.value, window_start=ws, window_end=we, count=c, unique_sources=us, unique_companies=uc))
        n += 1
    db.flush()
    return n


def describe_change(series: list[int]) -> dict[str, Any]:
    """Only claim an increase/decrease when the data supports it."""
    if len(series) < 4 or sum(series) < MIN_SAMPLE:
        return {"direction": "insufficient_data", "low_sample": True}
    half = len(series) // 2
    a, b = sum(series[:half]), sum(series[half:])
    if a == 0 and b == 0:
        return {"direction": "none", "low_sample": True}
    change = (b - a) / max(a, 1)
    low = (a + b) < MIN_SAMPLE * 2
    if abs(change) < 0.25 or low:
        return {"direction": "stable_or_unclear", "change": round(change, 2), "low_sample": low}
    return {"direction": "increase" if change > 0 else "decrease", "change": round(change, 2), "low_sample": low}
