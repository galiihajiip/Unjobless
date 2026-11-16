# Matching & comparison — how scores are calculated

Implementation: `backend/src/unjobless/profile/matching.py` (algorithm 1.0) and `profile/compare.py`.
Scores are transparent heuristics in [0, 1]. They **do not predict hiring success** or ATS outcomes.

## Three separate scores

| Score | Meaning | Inputs |
|---|---|---|
| `candidate_fit_score` | How well your **confirmed** profile evidences the vacancy's requirements | required skills (0.5), preferred skills (0.15), role relevance (0.2), education (0.15) |
| `preference_fit_score` | How well the vacancy matches **your preferences** | target role (0.25), work arrangement (0.2), location (0.2), employment type (0.15), compensation (0.15), industry (0.05) |
| `data_confidence_score` | How complete and reliable the **record** is | 9 completeness checks (75%) + share of explicit evidence (25%) |

`overall_score = 0.6 × candidate_fit + 0.4 × preference_fit`, only when both exist.

## Unknown is not zero

Each component is computed only when both sides have comparable information. Otherwise it is **unknown**: it is excluded from the weighted average (remaining weights renormalise) and listed under "Unknown" in the breakdown. Examples: the vacancy lists no skills, pay not stated, different currencies, location not stated.

## Eligibility

Hard blocks: excluded company/industry/keyword, GPA below the stated minimum, semester below the stated minimum. A blocked vacancy is flagged `eligible = false` and its preference fit becomes 0. Missing data needed for eligibility (e.g. your GPA) makes `eligible = null`.

## Evidence

Skill matches link to profile fact IDs (skills, projects that list the technology, experience bullets that mention it). Role relevance lists the experiences/projects whose titles overlap the vacancy title.

## Comparison (exactly two vacancies)

Criteria: candidate fit, location, work arrangement, compensation, benefits, growth/learning, eligibility, application practicality, data confidence. Each yields **A, B, Tie or Unknown** with both sides' values and a note. Weights (0–10, editable, savable as default) are summed only for decided criteria. Coverage is decided weight ÷ total weight. Below 50% coverage, or on a tie, no lean is suggested. The limit of two is enforced by the API schema, the service, and DB constraints.
