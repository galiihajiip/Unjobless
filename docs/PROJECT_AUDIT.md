# Unjobless — Project Audit (Prompt Block 00)

**Audit date:** 2026-11-16
**Scope:** Repository state, development environment, design reference, workloads, risks.
**Method:** Direct inspection of the working directory and local toolchain. No product code was written and no dependencies were installed.

---

## 1. Repository state

| Item | Finding |
|---|---|
| Git | **Not a repository before this block.** Initialized with `git init -b main` as part of this block (local only, no remote). |
| Branches | `main` only (new). |
| Remote | None configured. |
| Source code | **None.** No application code, package manifests, lockfiles, Dockerfiles, compose files, tests or CI config exist. |
| Prior scraper/project | None present. Nothing to migrate or reuse as code. |
| Documentation | One file: the build playbook (v1.0, 2,783 lines). |

### Files found at the repository root (before this block)

| File | Type | Disposition |
|---|---|---|
| `UNJOBLESS_CLAUDE_CODE_BUILD_PLAYBOOK.md` | Product + engineering spec | **Copied** to `docs/UNJOBLESS_BUILD_PLAYBOOK.md` (canonical, tracked). Root original left in place and git-ignored. |
| `993dfc53aa108022b43fe6b2d53f4c9f.webp` | UI style reference (WebP, sha256 `3e9d0230…a487d5`) | **Copied** to `docs/design-references/unjobless-ui-reference.webp` (tracked). Root original left in place and git-ignored. |
| `cv.docx` | The owner's personal CV (DOCX, ~200 KB) | **Left untouched and git-ignored.** Contents were deliberately *not* read during this audit. It is personal data and must never be committed, used as a test fixture, or sent to a third party without consent. It is the natural real-world input for Block 23 (CV ingestion), uploaded through the app at runtime. |
| `.DS_Store` | macOS metadata | Git-ignored. |

No existing work was moved, overwritten or deleted.

### Files added by this block

- `.gitignore` — blocks personal documents (`*.docx`, `*.pdf`, `cv.*`), `.env*` (except `.env.example`), runtime data dirs, OS/editor junk, and the root-level duplicates.
- `docs/UNJOBLESS_BUILD_PLAYBOOK.md`
- `docs/design-references/unjobless-ui-reference.webp`
- `docs/PROJECT_AUDIT.md` (this file)
- `docs/REQUIREMENTS_TRACEABILITY.md`
- `docs/IMPLEMENTATION_ROADMAP.md`

---

## 2. Development environment

Host: macOS (Darwin 25.2), **Apple Silicon arm64**, 16 GB RAM, ~143 GB free disk.

| Tool | Status | Note |
|---|---|---|
| git | 2.55.0 | OK |
| Node.js | v26.8.2 | Even-numbered line (LTS track). Pin exact version in Block 03. |
| npm / pnpm | 11.19.1 / 11.18.0 | pnpm available for a TS monorepo. |
| Python | 3.13.13 | OK for a Python worker. |
| uv / poetry | **not installed** | A Python package manager with lockfiles is needed if a Python worker is chosen (Block 01/03). |
| Docker CLI / Compose | 29.6.2 / v5.3.1 | Installed. |
| Docker daemon | **not running** | Socket missing at audit time. Must be started (Docker Desktop or equivalent) before any container work. |
| PostgreSQL / Redis | not installed on host | Expected to run in containers; host install not required. |
| Tesseract / FFmpeg / Pandoc / LibreOffice | not installed on host | Needed only for OCR/media (Block 16) and possibly DOCX/PDF export (Block 30); should be provided inside worker images, not on the host. |
| Homebrew | 6.0.18 | Available if host tooling is needed. |

**Portability note:** the dev machine is arm64; a typical VPS is x86_64. Images must build for `linux/amd64` (and ideally `linux/arm64`). Native dependencies (OCR, headless browser, PDF tooling) must be verified on both. This is recorded as a risk below.

---

## 3. Design reference inspection

`docs/design-references/unjobless-ui-reference.webp` shows three mobile screens of an unrelated healthcare assistant app.

**Observed qualities to translate (consistent with playbook §5–6 tokens):**

- Very light grey canvas (~`#EEEEF1`), close to the playbook `--background: #F3F3F5`.
- Large rounded device-like containers and cards (≈24–32 px radius); soft, broad, low-opacity shadows.
- Hero/AI card with a soft lilac→purple gradient and white text; pill-shaped input inside it.
- Primary CTA: full-width pill with a saturated purple gradient (`#A78BFA → #6D28D9` range) and a white circular icon button attached on one side.
- Circular white icon buttons (notification, back, search) on grey.
- 2×2 grid of soft-grey "tool" cards: small icon in a circle, corner arrow (↗), bold title, muted one-line description.
- Floating pill bottom navigation with an active "pill within pill" state, plus a separate circular purple FAB.
- Typography: bold, tightly-set dark headings; light, muted secondary copy.
- Small purple "chip" label above the hero heading; onboarding pagination dots.

**Explicitly not to copy:** the "Bionex" name and logo, the purple mascot character, all medical copy (clinical questions, ICD-10, drug interactions, stewardship), and the exact three-screen composition.

**Design caution for Unjobless:** the reference is mobile-only and very low-density. Unjobless also needs desktop/tablet layouts with denser data (feeds, comparisons, source health). The secondary copy in the reference is very light grey and likely fails WCAG AA; Unjobless should keep muted text at or above the playbook's `--foreground-muted: #858591` only for non-essential metadata, and verify contrast.

---

## 4. Main workloads

| Workload | Nature | Notes |
|---|---|---|
| Web UI (PWA) | Interactive, SSR-friendly, responsive | 11 IA sections; desktop/tablet/mobile; installable. |
| Domain API | CRUD + business rules | Profile, vacancies, comparison (max 2), tracker, settings, auth. |
| Scheduled collection | Background, long-running, rate-limited | Per-source schedules, retries, cursors, no overlap. |
| User URL import | Background, untrusted input | SSRF-safe fetch, per-item state, paste fallback. |
| HTML parsing / structured data | CPU-light, library-heavy | Readability-style extraction, JSON-LD `JobPosting`. |
| Browser extraction | Heavy, optional | Only when needed and permitted; must be network-isolated. |
| OCR / transcription | CPU/memory-heavy, optional | Posters, scanned PDFs, audio/video captions. |
| AI processing | Network-bound, quota-limited | Extraction, classification, CV structuring/tailoring; provider-agnostic. |
| Search & filtering | DB-bound | Postgres FTS first; vectors only if justified. |
| Document export | CPU-light | PDF/DOCX CV and cover letter generation. |
| Backup/restore | Operational | DB dump + file volume + encrypted settings. |

---

## 5. Key risks

| # | Risk | Impact | Mitigation (block) |
|---|---|---|---|
| R1 | **Source permissions / ToS** — many job and social platforms prohibit scraping. | Legal/ethical; account or IP bans. | Connector contract with policy review; default-disabled sources; paste fallback (08, 10, 12–15). |
| R2 | **SSRF** via user URLs reaching Postgres/Redis/metadata endpoints. | Critical security. | DNS-resolve + IP checks, redirect revalidation, network-isolated fetcher (10, 14, 42). |
| R3 | **Prompt injection** from scraped/pasted content. | Data corruption, secret leakage. | Treat content as data; no LLM tools; schema-validated outputs (27, 42). |
| R4 | **Duplicate data** across sources. | Noisy feed, wrong comparisons. | Canonical vacancy + multiple source refs; review queue for ambiguous merges (20). |
| R5 | **Stale vacancies** shown as open. | Wasted applications. | Lifecycle rules; failed fetch ≠ closed; visible uncertainty (21). |
| R6 | **AI provider limits/cost**. | Stalled pipelines, unexpected bills. | Cooldowns, per-task budgets, usage tracking; no quota evasion (26). |
| R7 | **Sensitive CV data** (contact details, history). | Privacy breach. | Private storage, auth on all files, redaction before AI calls, no CV in logs, `.gitignore` already blocks `*.docx` (07, 23, 27). |
| R8 | **Hallucinated CV claims / vacancy fields**. | Dishonest applications. | Evidence linking, explicit/inferred markers, user acceptance per claim (19, 23, 29). |
| R9 | **API key exposure**. | Account abuse. | Encryption at rest with env master key; masked display; log redaction (26, 35). |
| R10 | **Docker storage & backups** — volumes lost on VPS migration. | Data loss. | Named volumes, documented backup/restore, migration test (35, 38, 40). |
| R11 | **arm64 dev vs amd64 VPS**. | Images or native libs fail on deploy. | Multi-arch builds; smoke test on amd64 (38, 40). |
| R12 | **Small-VPS memory footprint** — headless browser + OCR + Postgres + app on 2–4 GB. | OOM, instability. | Optional heavy workers, concurrency limits, resource caps (01, 37). |
| R13 | **False-positive "opportunities"** from informal content (e.g. any mention of "magang"). | Unusable feed. | Precision-focused evaluation set; separate lead vs vacancy states (17, 36). |
| R14 | **Block ordering**: several blocks use AI before the AI gateway (Block 26) exists. | Rework or stubbed AI. | See roadmap §3 — recommended re-sequencing. |
| R15 | **Scope size** — 44 blocks for a solo owner. | Long time-to-value. | MVP cut in roadmap §5. |

---

## 6. Existing code/assets worth reusing

| Asset | Reuse |
|---|---|
| Build playbook | Source of truth for requirements; tracked at `docs/UNJOBLESS_BUILD_PLAYBOOK.md`. |
| UI reference image | Visual direction for Block 04 and 41. |
| Playbook design tokens (§6) | Starting CSS tokens for Block 04. |
| Playbook entity checklist (§24) | Starting point for the domain model (Block 02) and schema (Block 06). |
| Playbook signal examples (Block 17) and evaluation cases (Block 36) | Seed for the evaluation dataset. |
| Owner's `cv.docx` | **Runtime input only** (Block 23 manual acceptance test). Not a fixture, not committed. |

No prior code exists to reuse.

---

## 7. Assumptions

1. Single private owner; no public signup, billing or tenancy in v1 (playbook §3).
2. Primary market Indonesia; content in Indonesian and English.
3. Local development happens on this Apple Silicon Mac; production on a generic Linux VPS with Docker Compose.
4. Hosted AI APIs are acceptable; the owner will supply their own keys at runtime.
5. The design reference may be committed to the repository as a style reference (it is used only internally for visual direction, never shipped in the app).
6. Network access is available during later blocks for checking current official documentation before choosing packages.

## 8. Unresolved decisions (owner input needed)

| # | Decision | Needed by |
|---|---|---|
| D1 | Final stack (e.g. TS full-stack + Python worker vs Python-centred backend). | Block 01 |
| D2 | Accept the recommended block re-sequencing (roadmap §3)? | Before Block 16 |
| D3 | Which AI provider(s) the owner has keys for. | Block 26 |
| D4 | VPS size/architecture and whether a domain/subdomain exists. | Block 01 (sizing), Block 39 |
| D5 | Default UI language (Indonesian, English, or toggle with which default). | Block 04/05 |
| D6 | Git remote (GitHub/GitLab/none) and whether CI should run there. | Block 03 / 36 |
| D7 | Initial target companies / ATS boards to enable first. | Block 12 |
| D8 | Off-server backup destination. | Block 35 |
| D9 | Whether to include `SCHOLARSHIP_OR_COMPETITION` in v1 or defer. | Block 02 |
