# Opportunity Signal Engine — Evaluation

Method: deterministic rules + bilingual lexicon (`backend/src/unjobless/intelligence/signals.py`), **no AI**. All examples are synthetic (no real people or posts).

## Protocol and honesty note

Three sets were used, in this order:

1. `signals.jsonl` (36) — written first and used for rule tuning.
2. `signals_holdout.jsonl` (16) — written as a held-out set. **First evaluation: accuracy 0.438**, opportunity recall 0.5 (precision 1.0). That exposed overfitting; vocabulary and rule ordering were then generalised, so this set also became a tuning set.
3. `signals_test.jsonl` (18) — written afterwards and evaluated **once, with no tuning afterwards**. Its numbers are the ones to trust.

| Set | Role | Accuracy | Opportunity precision | Opportunity recall | DIRECT_VACANCY P / R |
|---|---|---|---|---|---|
| signals.jsonl | tuning | 1.0 | 1.0 | 1.0 | 1.0 / 1.0 |
| signals_holdout.jsonl | tuning (after first eval) | 1.0 | 1.0 | 1.0 | 1.0 / 1.0 |
| signals_test.jsonl | **untouched test** | 0.667 | 1.0 | 0.9 | 1.0 / 1.0 |

## Interpretation

- The engine is **precision-first**: across all sets no non-opportunity was classified as an opportunity, and no discussion/review was promoted to `DIRECT_VACANCY`.
- Recall on fine-grained classes is limited (test accuracy 0.667). Misses fall into the low-confidence `CAREER_TREND` fallback, which is excluded from the vacancy feed — they are lost signals, not false vacancies.
- Items with confidence < 0.7 are sent to the optional AI classifier when a provider is configured; that path was **not** evaluated here (no API key in the test environment).
- Sample sizes are small (n=18 test). Treat these as smoke-level numbers, not a benchmark.

## Known false-negative patterns (test set)

- `t-en-2`: expected REFERRAL_SIGNAL, got INFORMAL_OPPORTUNITY_LEAD
- `t-id-3`: expected INFORMAL_OPPORTUNITY_LEAD, got CAREER_TREND
- `t-en-3`: expected EMPLOYER_DISCUSSION, got CAREER_TREND
- `t-id-4`: expected EMPLOYER_DISCUSSION, got CAREER_TREND
- `t-en-4`: expected EMPLOYER_REVIEW, got CAREER_TREND
- `t-en-9`: expected IRRELEVANT, got CAREER_TREND

## Reproduce

```bash
cd backend && uv run python -m unjobless.evaluation.signals_eval
```

---

## Test-set detail

Dataset: `backend/tests/fixtures/eval/signals.jsonl` — 18 synthetic Indonesian/English examples. Method: rules (no AI).

- Overall accuracy: **0.667**
- Opportunity detection (actionable vs not): precision **1.0**, recall **0.9**
- DIRECT_VACANCY: precision **1.0**, recall **1.0**
- Expired postings flagged EXPIRED: 0/0

| Class | Precision | Recall | Support |
|---|---|---|---|
| CAREER_PROGRAM | 1.0 | 1.0 | 1 |
| CAREER_TREND | 0.167 | 1.0 | 1 |
| DIRECT_VACANCY | 1.0 | 1.0 | 3 |
| EMPLOYER_DISCUSSION | None | 0.0 | 2 |
| EMPLOYER_REVIEW | 1.0 | 0.5 | 2 |
| INFORMAL_OPPORTUNITY_LEAD | 0.5 | 0.5 | 2 |
| IRRELEVANT | 1.0 | 0.667 | 3 |
| RECRUITMENT_CAMPAIGN | 1.0 | 1.0 | 1 |
| REFERRAL_SIGNAL | 1.0 | 0.5 | 2 |
| SCHOLARSHIP_OR_COMPETITION | 1.0 | 1.0 | 1 |

## Confusion (gold → predicted)

- **CAREER_PROGRAM**: CAREER_PROGRAM 1
- **CAREER_TREND**: CAREER_TREND 1
- **DIRECT_VACANCY**: DIRECT_VACANCY 3
- **EMPLOYER_DISCUSSION**: CAREER_TREND 2
- **EMPLOYER_REVIEW**: CAREER_TREND 1, EMPLOYER_REVIEW 1
- **INFORMAL_OPPORTUNITY_LEAD**: CAREER_TREND 1, INFORMAL_OPPORTUNITY_LEAD 1
- **IRRELEVANT**: CAREER_TREND 1, IRRELEVANT 2
- **RECRUITMENT_CAMPAIGN**: RECRUITMENT_CAMPAIGN 1
- **REFERRAL_SIGNAL**: INFORMAL_OPPORTUNITY_LEAD 1, REFERRAL_SIGNAL 1
- **SCHOLARSHIP_OR_COMPETITION**: SCHOLARSHIP_OR_COMPETITION 1

## Misclassified examples

- `t-en-2` expected REFERRAL_SIGNAL, got INFORMAL_OPPORTUNITY_LEAD — Hiring is mentioned but key details are missing: role, application_path, details.
- `t-id-3` expected INFORMAL_OPPORTUNITY_LEAD, got CAREER_TREND — Career-related content without an opportunity.
- `t-en-3` expected EMPLOYER_DISCUSSION, got CAREER_TREND — Career-related content without an opportunity.
- `t-id-4` expected EMPLOYER_DISCUSSION, got CAREER_TREND — Career-related content without an opportunity.
- `t-en-4` expected EMPLOYER_REVIEW, got CAREER_TREND — Career-related content without an opportunity.
- `t-en-9` expected IRRELEVANT, got CAREER_TREND — Career-related content without an opportunity.
