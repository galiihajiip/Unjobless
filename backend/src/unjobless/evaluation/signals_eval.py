"""Opportunity-signal evaluation: precision/recall per class, confusion matrix, false positives."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from unjobless.intelligence.signals import classify

DEFAULT_DATASET = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "eval" / "signals.jsonl"
EVAL_TODAY = date(2026, 11, 16)  # fixed so the dataset's deadlines evaluate reproducibly


def run(path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    mistakes = []
    expired_ok = 0
    expired_total = 0
    for r in rows:
        res = classify(r["text"], title=r.get("title") or None, today=EVAL_TODAY)
        pred = res.primary.value
        confusion[r["label"]][pred] += 1
        if pred != r["label"]:
            mistakes.append({"id": r["id"], "expected": r["label"], "predicted": pred, "reason": res.reason})
        if r.get("expired"):
            expired_total += 1
            expired_ok += int(res.recommendation.value == "EXPIRED")
    labels = sorted({*confusion, *(p for c in confusion.values() for p in c)})
    per_class = {}
    for lab in labels:
        tp = confusion[lab][lab]
        fp = sum(confusion[o][lab] for o in labels if o != lab)
        fn = sum(v for p, v in confusion[lab].items() if p != lab)
        per_class[lab] = {
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "support": tp + fn,
        }
    # "Opportunity detection" = anything actionable (vacancy/lead/referral/campaign/program) vs not.
    actionable = {
        "DIRECT_VACANCY",
        "INFORMAL_OPPORTUNITY_LEAD",
        "REFERRAL_SIGNAL",
        "RECRUITMENT_CAMPAIGN",
        "CAREER_PROGRAM",
        "SCHOLARSHIP_OR_COMPETITION",
    }
    tp = fp = fn = 0
    for gold, preds in confusion.items():
        for pred, c in preds.items():
            g, p = gold in actionable, pred in actionable
            tp += c * (g and p)
            fp += c * (not g and p)
            fn += c * (g and not p)
    accuracy = sum(confusion[label][label] for label in labels) / len(rows)
    return {
        "n": len(rows),
        "accuracy": round(accuracy, 3),
        "opportunity_detection": {
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
        },
        "direct_vacancy": per_class.get("DIRECT_VACANCY"),
        "per_class": per_class,
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "expired_detection": f"{expired_ok}/{expired_total}",
        "mistakes": mistakes,
    }


def render_markdown(r: dict[str, Any]) -> str:
    lines = [
        "# Opportunity signal evaluation",
        "",
        f"Dataset: `backend/tests/fixtures/eval/signals.jsonl` — {r['n']} synthetic Indonesian/English examples. Method: rules (no AI).",
        "",
        f"- Overall accuracy: **{r['accuracy']}**",
        f"- Opportunity detection (actionable vs not): precision **{r['opportunity_detection']['precision']}**, recall **{r['opportunity_detection']['recall']}**",
        f"- DIRECT_VACANCY: precision **{r['direct_vacancy']['precision']}**, recall **{r['direct_vacancy']['recall']}**",
        f"- Expired postings flagged EXPIRED: {r['expired_detection']}",
        "",
        "| Class | Precision | Recall | Support |",
        "|---|---|---|---|",
    ]
    for k, v in sorted(r["per_class"].items()):
        lines.append(f"| {k} | {v['precision']} | {v['recall']} | {v['support']} |")
    lines += ["", "## Confusion (gold → predicted)", ""]
    for g, preds in sorted(r["confusion"].items()):
        lines.append(f"- **{g}**: " + ", ".join(f"{p} {c}" for p, c in sorted(preds.items())))
    lines += ["", "## Misclassified examples", ""]
    lines += [
        f"- `{m['id']}` expected {m['expected']}, got {m['predicted']} — {m['reason']}" for m in r["mistakes"]
    ] or ["- none"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(json.dumps(run(), indent=1))
