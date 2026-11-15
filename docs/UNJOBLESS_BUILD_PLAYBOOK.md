# UNJOBLESS
## Claude Code Build Playbook: Product Blueprint, Engineering Specification & Sequential Prompt Blocks

**Document version:** 1.0  
**Product:** Unjobless  
**Product type:** Personal-first, self-hostable AI career discovery and application intelligence web app  
**Primary market context:** Indonesia first, with support for remote opportunities that accept applicants from Indonesia  
**Deployment target:** Docker Compose on a VPS, portable to another VPS/server  
**UI target:** Responsive web + installable PWA for desktop, tablet, Android, iOS and macOS browsers

---

# HOW TO USE THIS DOCUMENT

This document is intended to be used directly with Claude Code in a project repository.

1. Create an empty Git repository named `unjobless` (or open the repository you want to use).
2. Copy the supplied UI reference image into the repository at `docs/design-references/unjobless-ui-reference.webp`. The reference image is a visual direction only. Do not reproduce the healthcare product, its name, mascot, medical content, or exact screen composition.
3. Save this Markdown file in the repository as `docs/UNJOBLESS_BUILD_PLAYBOOK.md` if desired.
4. Start Claude Code from the repository root.
5. Paste the **Master Prompt** once.
6. Execute the numbered prompt blocks sequentially. Do not paste every block in one enormous request. Each block is intentionally small enough to inspect, test, and commit independently.
7. After each block, inspect Claude Code's summary, run the stated checks, inspect the diff, and confirm the semantic commit exists before moving to the next block.
8. If Claude discovers that a later block depends on a missing prerequisite, it must stop, explain the dependency, and complete the prerequisite first. It must not silently skip requirements.

The prompts instruct Claude Code to inspect current official documentation and the actual repository before choosing or installing packages. Package names, framework APIs, Docker images, PWA tooling, browser versions, and provider API details can change. Do not blindly trust stale examples in this document.

---

# PART I — PRODUCT DEFINITION

## 1. Product summary

**Unjobless** is a personal career discovery and application intelligence workspace. It continuously gathers career-related opportunities from accessible and permitted online sources, imports opportunities from user-submitted URLs or pasted content, extracts and enriches the information, detects both formal vacancies and informal opportunity signals, matches opportunities against the user's career profile, compares up to two vacancies side by side, and helps prepare job-specific application materials.

Unjobless is not merely:

- a conventional job board;
- a simple keyword scraper;
- a generic AI CV writer;
- a social-media sentiment dashboard;
- a recruiter CRM;
- an auto-apply bot.

It is a unified personal opportunity-discovery and career decision workspace.

### Product promise

**Discover broadly. Understand deeply. Apply deliberately.**

### Main product loop

`Discover → Collect → Enrich → Verify → Match → Compare → Optimize → Apply → Track`

## 2. Product goals

1. Build a broad, extensible collection engine for public and otherwise authorized career-related information.
2. Find both formal vacancies and informal signals that could indicate an internship, job opening, referral, recruitment batch, trainee program, or other career opportunity.
3. Support multiple collection methods: approved/public APIs, permitted public web crawling, RSS/Atom, sitemaps, public ATS boards, user-submitted URLs, and pasted job content.
4. Capture rich source content and provenance rather than extracting only a few standard fields.
5. Preserve original source context and separate raw source material from AI-derived structured data.
6. Classify opportunity signals separately from sentiment, discussion, employer reputation, and general career chatter.
7. Normalize, deduplicate, enrich, and track opportunity records over time.
8. Store one master candidate profile derived from the user's latest CV and manually confirmed career information.
9. Rank opportunities against the candidate's profile and preferences.
10. Compare **no more than two vacancies at a time**, including criterion winners, transparent scores, trade-offs, and missing information.
11. Generate evidence-grounded CV recommendations and application documents for a selected vacancy.
12. Provide direct links to original application pages. Never claim that Unjobless has submitted an application unless a real, explicitly authorized integration has done so.
13. Be easy to run locally and deploy/migrate using Docker Compose on a VPS.
14. Provide a polished, installable PWA with a responsive experience across desktop, tablet, Android, iOS and macOS browsers.

## 3. Product boundaries for v1

This is initially a **private, personal-use installation for one owner**. Do not spend time building public registration, team workspaces, billing, subscriptions, payment gateways, enterprise tenancy, recruiter accounts, or a multi-tenant SaaS control plane.

However, structure data ownership and service boundaries cleanly so a future multi-user product is possible without rewriting all domain logic. Add an owner/user reference where it is sensible, but keep v1 authentication simple and secure.

### Explicit non-goals for v1

- No automatic application submission or auto-apply.
- No bypassing login, CAPTCHA, paywalls, anti-bot controls, or access restrictions.
- No scraping of private groups, private accounts, private messages, or content not authorized for collection.
- No evasion of platform terms, rate limits, robots directives, API quotas, or technical controls.
- No collection of personal data about ordinary social-media users beyond what is necessary and permitted to establish source provenance. Do not build dossiers on individuals.
- No guarantee that every social platform or website can be collected from.
- No fabricated salary, deadline, role, company, location, benefits, or hiring status.
- No claim that a match score predicts hiring success or ATS acceptance.
- No public-facing SaaS billing in v1.

## 4. Primary workflows

### Workflow A — First-time setup

1. Open private Unjobless instance.
2. Complete first-run owner setup.
3. Set personal career preferences: target roles, skills/interests, preferred locations, remote/hybrid/WFO preferences, minimum compensation if relevant, employment types, and location/commute constraints.
4. Upload the latest CV in PDF or DOCX.
5. Extract CV content and propose a structured master profile.
6. Review, correct and confirm the profile. Never silently accept potentially inaccurate AI extraction.
7. Keep the original CV and extracted profile versioned.

### Workflow B — Continuous opportunity discovery

1. Scheduler activates enabled source connectors according to per-source schedules and quotas.
2. Connectors collect only data that is accessible and permitted under the relevant source's rules.
3. Raw documents and metadata are preserved with source attribution and timestamps.
4. Text, images and permitted media references pass through the relevant extraction pipeline.
5. Classifiers identify direct vacancies, informal opportunity leads, recruitment chatter, employer sentiment, career trends, or irrelevant content.
6. Structured records are created, enriched, deduplicated and stored.
7. Vacancy freshness and source health are updated.
8. New and changed opportunities become eligible for matching.

### Workflow C — Manual URL import

1. User pastes one URL or a batch of URLs, one per line.
2. System validates the URL and applies SSRF protections.
3. The correct source connector is selected if available.
4. Otherwise use a permitted public fetch/parser strategy.
5. If a page cannot be fetched because of login, CAPTCHA, dynamic restrictions or access controls, show a clear fallback: paste the content manually.
6. Extract all accessible career-relevant content, not just a small fixed set of fields.
7. Show a review screen with original source, extracted fields, evidence, confidence and missing information.
8. User confirms before saving or merging with an existing canonical record.

### Workflow D — Paste-content import

1. User pastes copied content from a job board, social post, email, public announcement, transcript, or other source they are authorized to use.
2. User may optionally provide source URL, platform, date, author/account label, and notes.
3. Store raw pasted content separately from extracted data.
4. Run content-type detection and opportunity/sentiment classification.
5. Extract all useful information with field-level evidence and confidence.
6. Review and confirm, then save as a vacancy or an unverified lead as appropriate.

### Workflow E — Opportunity feed

1. Show formal vacancies and informal opportunity leads in clearly distinguishable categories.
2. Filters: role, skill, company, industry, location, work arrangement, employment type, seniority/education, source, date found, deadline, compensation, confidence, status and match score.
3. Show source links, first seen, last checked, last verified, and freshness.
4. Allow save, dismiss, mark interesting, mark applied, archive and report incorrect data.
5. Provide original application CTA when an application URL is known and valid.

### Workflow F — Compare two vacancies

1. User selects exactly two vacancy records.
2. Comparison UI must reject a third selection.
3. Compare profile fit and personal opportunity preferences separately.
4. Show criterion-by-criterion winner, score, evidence, uncertainty and trade-offs.
5. Allow editable user weights with sensible defaults.
6. Do not treat missing data as zero or as a win for either vacancy. Mark it `Unknown` and explain its effect on confidence.

### Workflow G — Tailored application

1. User chooses a vacancy.
2. AI identifies relevant evidence from the confirmed master profile.
3. AI proposes a job-specific CV summary, selected skills, project/experience ordering and bullet rewrites.
4. Every claim must be traceable to the user's profile or explicitly confirmed user input.
5. User reviews and accepts/rejects individual changes.
6. Generate PDF/DOCX using controlled templates.
7. Save a separate tailored version; never overwrite the master CV.
8. Link back to the vacancy's original application page.

---

# PART II — DESIGN DIRECTION

## 5. Visual reference interpretation

The supplied image is a mobile-first UI reference for visual style. Its visual qualities should be translated into Unjobless, but the product must remain a professional career intelligence dashboard.

### What to take from the reference

- Very light neutral/soft-grey canvas.
- Large rounded surfaces and generous spacing.
- White and light-grey cards with restrained depth.
- Purple/lilac as the distinctive accent.
- Soft purple gradient CTA surfaces and small glow accents.
- Strong, clean, black/dark typography.
- Minimal iconography and uncluttered composition.
- Rounded pill controls and clear hierarchy.
- Subtle translucent/glass-like surfaces used sparingly.
- Mobile layouts that feel like a polished native app while remaining web-based.

### What NOT to copy

- Do not use the reference's medical/clinical content.
- Do not copy its brand, logo, mascot, text, exact composition or proprietary artwork.
- Do not make every component purple or glowing.
- Do not use excessive glassmorphism, blur, gradients or decorative shadows.
- Do not design a mobile-only app. Desktop and tablet are first-class layouts too.
- Do not reproduce any screenshot literally. Create original Unjobless information architecture and components.

## 6. Initial design tokens

Use these as starting design tokens. Claude may tune them slightly after inspecting the supplied reference image, but must document any material change in `docs/design/`.

### Color palette

```css
:root {
  /* Main surfaces */
  --background: #F3F3F5;
  --surface: #FFFFFF;
  --surface-soft: #EBEBEF;
  --surface-muted: #E4E4E9;
  --surface-glass: rgba(255, 255, 255, 0.68);

  /* Typography */
  --foreground: #171720;
  --foreground-secondary: #555563;
  --foreground-muted: #858591;
  --border: #E1E1E7;
  --border-strong: #D2D2DA;

  /* Brand purple */
  --brand-50: #F5F0FF;
  --brand-100: #EBDDFF;
  --brand-200: #D6BEFF;
  --brand-300: #BE9CFF;
  --brand-400: #A77AF8;
  --brand-500: #8B5CF6;
  --brand-600: #7138DF;
  --brand-700: #5927B9;
  --brand-800: #401D85;

  /* Semantic */
  --success: #16865D;
  --success-soft: #E7F6EF;
  --warning: #B7791F;
  --warning-soft: #FFF5DF;
  --danger: #C04455;
  --danger-soft: #FDECEF;
  --info: #3874B8;
  --info-soft: #EAF3FE;

  /* Focus */
  --focus-ring: rgba(139, 92, 246, 0.35);
}
```

### Purple gradient

Use for primary actions and a few hero/AI surfaces only:

```css
--brand-gradient: linear-gradient(110deg, #A78BFA 0%, #8B5CF6 48%, #6D28D9 100%);
--brand-gradient-soft: linear-gradient(135deg, #E7D9FF 0%, #C9B0FF 50%, #A78BFA 100%);
--brand-glow: 0 8px 28px rgba(124, 78, 220, 0.20);
```

### Geometry and depth

- Card radius: 20–28px.
- Standard input/button radius: 12–16px.
- Pill radius: 999px.
- Mobile safe-area aware bottom navigation.
- Main card shadow: very soft, low opacity, broad blur.
- Avoid heavy outlines. Prefer subtle borders and surface contrast.
- Use an 8px spacing scale where practical.
- Give content room to breathe; avoid dense admin-style tables on mobile.

### Typography

- Choose a modern, highly readable sans-serif with strong Indonesian/English glyph support. Prefer a reliable system/font package after checking licensing and performance.
- Headings: semibold/bold, compact line height.
- Body: regular, comfortable line height.
- Metadata: smaller and muted but still accessible.
- Use tabular numerals for scores, counts, salary and timestamps.
- Avoid ultra-thin body text.

### Components

- Primary button: purple gradient, white label, pill or 14–18px radius, clear hover/pressed/focus states.
- Secondary button: white/soft-grey surface, dark text, subtle border.
- AI action: purple-accented but not visually louder than the page's main action.
- Cards: white surface on grey canvas, 20–24px radius.
- Inputs: soft neutral surface, visible labels, strong focus state.
- Status badges: restrained semantic colors, not rainbow decoration.
- Score visualizations: accessible color + numeric label; never color-only.
- Icons: one consistent icon family; no random mixed icon sets.

### Responsive design

- Mobile: one-column cards, compact top bar, bottom navigation, sticky primary actions where useful, safe-area support.
- Tablet: two-column modules where appropriate, collapsible navigation.
- Desktop: sidebar navigation, dense-but-readable multi-column dashboard, comparison side-by-side, larger content workspace.
- Large desktop: limit reading width for long text; do not stretch every card edge-to-edge.
- Ensure tables become mobile cards or horizontally scrollable with sticky labels where appropriate.

### Motion

- Subtle transitions, 150–220ms for ordinary interactions.
- Use motion only to clarify feedback or hierarchy.
- Respect `prefers-reduced-motion`.
- No continuous decorative animation that wastes battery or distracts.

### Accessibility

- Meet WCAG AA contrast where feasible.
- Keyboard navigation and visible focus.
- Semantic HTML and properly labelled forms.
- Accessible dialogs, menus and comboboxes.
- Screen-reader labels for icon-only controls.
- Do not rely on purple/green/red alone to convey a result.

## 7. Brand voice

- Product name: **Unjobless**.
- Tone: smart, calm, encouraging, practical, professional.
- UI copy should be concise and plain-language.
- Avoid exaggerated claims such as “guaranteed to get hired”, “100% ATS pass”, or “all jobs on the internet”.
- Suggested product line: **Discover broadly. Understand deeply. Apply deliberately.**

---

# PART III — FUNCTIONAL SPECIFICATION

## 8. Main navigation / sitemap

Suggested information architecture:

1. **Overview** — personal career dashboard, new opportunities, system/source health summary.
2. **Discover** — opportunity feed with filters and saved views.
3. **Opportunity Signals** — unverified informal leads and social/recruitment signals.
4. **Compare** — comparison workspace for a maximum of two vacancies.
5. **My Career Profile** — master profile, skills, education, projects, experience and CV versions.
6. **Applications** — saved, shortlisted, preparing, applied, interview, offer, rejected, withdrawn, archived.
7. **Import Center** — URL batch importer, paste-content importer, import history.
8. **Sources** — source registry, connector status, schedules, quota and error health.
9. **Career Intelligence** — employer sentiment, topic trends, recruitment discussions and company insights.
10. **AI Studio** — provider settings, model selection, token/usage tracking and prompt configuration.
11. **Settings** — personal preferences, appearance, PWA guidance, security, backups and system settings.

For v1, hide or mark future modules as disabled rather than rendering dead navigation.

## 9. Opportunity categories

Every collected item must be assigned one or more explicit classifications:

- `DIRECT_VACANCY` — an explicit, actionable job/internship opening.
- `INFORMAL_OPPORTUNITY_LEAD` — a possible opening mentioned informally but not sufficiently verified.
- `REFERRAL_SIGNAL` — an offer/request for referral or candidate recommendation.
- `RECRUITMENT_CAMPAIGN` — hiring batch, campus hiring, graduate program, MT, trainee program.
- `CAREER_PROGRAM` — career-related structured program, bootcamp, fellowship or similar.
- `SCHOLARSHIP_OR_COMPETITION` — optional future category; do not mix with jobs without a separate filter.
- `EMPLOYER_DISCUSSION` — discussion about an employer or recruitment process, no direct vacancy confirmed.
- `EMPLOYER_REVIEW` — experience/review about working or interning at an organization.
- `CAREER_TREND` — broader topic or trend, not an actionable opening.
- `IRRELEVANT` — unrelated content.

An item may have both a primary classification and secondary tags. Do not convert every mention of “internship” into a vacancy.

## 10. Opportunity status and verification

Suggested statuses:

- `NEW_UNREVIEWED`
- `NEEDS_REVIEW`
- `POTENTIAL_LEAD`
- `VERIFIED_OPEN`
- `LIKELY_OPEN`
- `STATUS_UNKNOWN`
- `CLOSED`
- `EXPIRED`
- `REJECTED_AS_IRRELEVANT`
- `SOURCE_UNAVAILABLE`

A social post that says “maybe opening next month” is not `VERIFIED_OPEN`.

Each opportunity should expose:

- classification;
- verification status;
- confidence score;
- evidence snippets/source locations;
- original URL/source;
- first seen;
- last seen;
- last verified;
- source publication time if known;
- deadline if explicit;
- freshness state;
- why it was recommended;
- what remains unknown.

## 11. Rich extraction requirements

Do not constrain the extractor to a tiny fixed field list. Preserve a raw source document and extract every relevant field supported by the source. The canonical structured vacancy model should include at least:

### Identity and source

- canonical opportunity ID;
- title/role;
- alternative title;
- company/employer;
- company aliases;
- company website;
- source platform/domain;
- source type;
- original source URL;
- canonical source URL;
- original application URL;
- source record/post ID where permitted;
- publisher/account label where relevant and permitted;
- source publication timestamp;
- first collected timestamp;
- last collected timestamp;
- last verified timestamp;
- raw content hash;
- collection method;
- source license/access note.

### Opportunity details

- opportunity category;
- employment type;
- seniority;
- internship duration;
- contract duration;
- recruitment batch;
- number of openings if explicit;
- department/team;
- job family;
- industry;
- work arrangement: onsite, hybrid, remote, flexible, unknown;
- workplace location(s);
- remote eligibility / eligible countries if explicit;
- travel or relocation requirement;
- working hours/timezone;
- start date;
- application opening date;
- application deadline;
- current status;
- role responsibilities;
- expected deliverables;
- reporting line/mentor if explicit.

### Candidate requirements

- education level;
- accepted majors/fields;
- minimum semester/year;
- graduation window;
- GPA requirement;
- experience requirement;
- required skills;
- preferred skills;
- tools/platforms;
- language requirements;
- certifications;
- portfolio requirements;
- legal/work eligibility requirements;
- soft skills;
- application documents;
- selection stages;
- assessment/interview details.

### Compensation and benefits

- salary/stipend minimum and maximum;
- currency;
- pay period;
- compensation type;
- whether unpaid/paid is explicit;
- benefits;
- allowances;
- equipment;
- insurance;
- meal/transport support;
- learning/mentorship benefits;
- conversion/return-offer information if explicit.

### Context and evidence

- full job description;
- original post text/caption;
- OCR text from permitted images;
- permitted transcript excerpts;
- relevant public discussion/comment excerpts if source rules allow;
- extracted entities;
- evidence references for important fields;
- confidence per field;
- inferred-vs-explicit markers;
- extraction warnings;
- review notes.

When a field is not stated, store `null`/unknown. Do not infer salary, eligibility, deadline, remote status or hiring status without clearly labelling the inference.

## 12. Sentiment, topic and signal analysis

Keep these separate analytical dimensions:

### A. Opportunity signal detection

Determine whether the content indicates:

- direct hiring;
- possible hiring;
- referral availability;
- future hiring intent;
- an application invitation;
- recruitment batch;
- career event/program;
- not an opportunity.

### B. Sentiment analysis

Determine sentiment and target separately:

- positive, neutral, negative, mixed, uncertain;
- target: company, recruitment process, internship experience, role, compensation, management, work culture, or general job search;
- evidence excerpt;
- language;
- sarcasm/irony uncertainty;
- confidence.

### C. Topic analysis

Detect and cluster topics such as internship opening, hiring freeze, campus recruitment, application experience, interview experience, salary transparency, work culture, remote work, referral, graduate program, and emerging phrases.

### D. Trend analysis

Trend results must be based on observed time-series data and counts, not model speculation. Distinguish:

- increased mentions;
- increased explicit vacancy posts;
- repeated company recruitment posts;
- increased discussion/reviews;
- unverified rumours.

Never treat high engagement or high sentiment as proof of a real vacancy.

---

# PART IV — TECHNICAL ARCHITECTURE GUIDANCE

## 13. Architecture decision principle

The user wants Claude Code to choose the final stack based on project requirements and current best practices. Therefore, do not blindly force a fashionable stack.

Claude must:

1. inspect the current repository and available environment;
2. identify the dominant workload: web UX, scheduled collection, HTML extraction, media processing, AI orchestration and database operations;
3. compare at least two reasonable architecture options;
4. inspect current official documentation for selected frameworks/packages;
5. select the simplest architecture that can safely support the requirements;
6. write Architecture Decision Records (ADRs) in `docs/architecture/`;
7. explain trade-offs, local development, Docker deployment, backup, portability and migration;
8. avoid premature microservices.

### Suggested default direction (not a mandate)

A sensible baseline to evaluate is:

- Frontend: a modern React/TypeScript framework with server rendering where useful.
- Backend/domain API: a well-supported TypeScript or Python framework, selected based on cohesive implementation and maintainability.
- Collection and parsing workers: Python is a strong candidate due to its scraping, NLP, OCR and document-processing ecosystem.
- Database: PostgreSQL.
- Search: PostgreSQL full-text search first; optionally `pgvector` for semantic matching if justified by evaluation.
- Queue/scheduler: Redis-backed task queue or another mature, self-hostable job system.
- File/media storage: filesystem volume for simple personal deployment, with an S3-compatible adapter if useful.
- Browser extraction: HTTP client + HTML parser by default; browser automation only when needed and permitted.
- AI: provider abstraction with replaceable hosted providers; do not hardcode a provider into business logic.
- Packaging: Dockerfiles + Docker Compose.
- Reverse proxy/TLS: a simple, maintained reverse proxy such as Caddy or Traefik, selected and documented.

Claude may choose a different stack, but must justify why it is better for Unjobless and its deployment constraints.

### Personal-first deployment principle

Use a private single-owner instance for v1. Avoid unnecessary external managed dependencies when they make migration harder. A portable self-hosted PostgreSQL database should be the system of record. External AI APIs may be used through configurable provider keys. Do not require Supabase to operate the core app unless Claude provides a strong reason and a clear migration strategy.

### Deployment portability

The complete application should run using a documented command such as:

```bash
docker compose up -d --build
```

The exact service composition can vary, but it must include all required runtime components and persistent volumes. A fresh VPS should be able to deploy using the documented steps without installing application runtimes directly on the host beyond Docker and Compose.

---

# PART V — DATA, CRAWLING, SAFETY AND RELIABILITY

## 14. Source connector architecture

Every source must be implemented through a connector/adapter contract. A connector should expose capabilities such as:

- source identity and documentation URL;
- source category;
- allowed collection methods;
- configuration schema;
- authentication requirement, if any;
- quotas/rate limits;
- crawl policy and terms review reference;
- discovery/search method if supported;
- fetch method;
- parse/extract method;
- pagination/cursor handling;
- incremental sync capability;
- retry/backoff policy;
- health check;
- source freshness strategy;
- supported content types;
- attribution requirements.

The connector registry must be data-driven where appropriate. Adding a source should not require rewriting the core pipeline.

### Source categories to support over time

1. Official job APIs and aggregators with permitted access.
2. Public ATS job boards and documented posting endpoints.
3. Company career pages that permit automated collection.
4. Public RSS/Atom feeds.
5. Public sitemaps and structured `JobPosting` data where allowed.
6. Public web pages where crawling is permitted.
7. Social platform official APIs and permitted public surfaces.
8. Public forums/communities with permitted API/access conditions.
9. User-submitted URLs.
10. User-pasted content.
11. User-supplied documents/images they are authorized to process.

### Important collection rules

- Official API first where available and appropriate.
- Respect Terms of Service, robots directives, documented API rules, quotas and rate limits.
- Do not bypass login, CAPTCHA, paywalls, anti-bot systems, access controls or private-group boundaries.
- Do not use stolen cookies, session tokens, account credentials or unauthorized proxies.
- Do not scrape private messages, private accounts or private communities.
- Do not use fake accounts or deceptive access methods.
- Use a clear, configurable user agent and conservative request rates where appropriate.
- Store source URL and collection timestamp.
- Provide source disable/pause functionality.
- Implement an exclusion/denylist for sources that cannot be collected.
- If source permission is unclear, default to disabled and ask for manual import or approved integration.
- Social comments/replies/engagement metrics may only be collected when the platform access path permits them.
- No promise of complete internet coverage.

## 15. URL import security (SSRF)

User-submitted URLs are untrusted input. Before fetching:

- allow only `http` and `https` schemes;
- block localhost, loopback, private, link-local, multicast, reserved and cloud metadata IP ranges;
- resolve DNS and re-check the resolved IP before connection;
- defend against DNS rebinding and redirect-to-private-IP attacks;
- revalidate every redirect target;
- block nonstandard ports unless explicitly allowed;
- enforce connect/read/total timeouts;
- cap redirects, response size and decompression size;
- reject unsafe content types;
- prevent local file and non-HTTP protocols;
- isolate browser workers from internal services and secrets;
- do not expose browser debugging endpoints publicly;
- log blocked attempts without storing unnecessary sensitive data.

Never allow a URL importer to access internal Docker service names, host files, database endpoints, Redis, admin panels or cloud metadata endpoints.

## 16. Collection orchestration

Use independent schedules per source. Suggested initial target intervals are configurable, not guaranteed service levels:

- webhook/event-driven source: process immediately when legitimately delivered;
- job API/ATS source: 15–60 minutes where quota and terms allow;
- career page: 6–12 hours or a source-specific interval;
- RSS/sitemap: 1–6 hours;
- social API: source-specific quota-aware interval;
- user import: immediately enqueue.

Requirements:

- scheduler persistence;
- queue persistence or reliable re-enqueue strategy;
- retry with exponential backoff and jitter;
- per-source concurrency controls;
- global concurrency limits;
- rate limiting;
- timeout handling;
- dead-letter/failed job state;
- job cancellation;
- idempotent collection;
- cursor/checkpoint storage;
- graceful shutdown;
- pause/resume per source;
- source-specific schedule override;
- no overlapping run for the same source unless intentionally supported.

## 17. Raw storage, normalization and deduplication

Preserve raw content separately from normalized canonical entities.

Suggested processing:

`Raw item → Content hash → Source identity → Extract text/media → Classify → Extract entities → Normalize → Find possible duplicates → Merge/link → Persist evidence → Reindex`

Deduplication should use a combination of:

- normalized canonical URL;
- source-native ID;
- company identity;
- normalized title;
- location;
- application URL;
- description similarity;
- publication timeframe.

Do not merge two roles just because title and company are similar. Store cross-source relationships and provenance. Prefer a canonical opportunity with multiple source references, while retaining every source's raw data and dates.

## 18. Freshness and vacancy lifecycle

Track:

- `first_seen_at`;
- `last_seen_at`;
- `last_checked_at`;
- `last_verified_at`;
- `source_published_at`;
- `application_deadline`;
- `closed_at`;
- `status_reason`.

Use confidence-aware state transitions. A failed fetch is not proof that a job is closed. A removed posting may mean closed, hidden, changed URL or temporary source error. Explain uncertain status.

## 19. AI provider abstraction and API key rotation

The app is personal-use and may use hosted AI APIs. Do not require a local LLM for v1.

Implement a provider-agnostic AI gateway:

- provider registry;
- model registry;
- task-to-model routing;
- provider adapter interface;
- structured output validation;
- timeout and retry handling;
- token/usage tracking when provider exposes it;
- cost estimate when provider pricing is configured;
- per-task budget limits;
- manual provider/model selection;
- clear provider errors and rate-limit cooldowns;
- optional fallback to another user-configured provider when appropriate.

The user must be able to replace/rotate API keys from a private settings page. Requirements:

- never send secrets to the browser after save;
- never display full keys again; show masked value/fingerprint only;
- encrypt keys at rest using an encryption key supplied through an environment secret;
- keep encryption master secret outside the database and repository;
- support update/delete/test connection;
- allow different provider keys and models;
- document backup/restore implications for encrypted secrets;
- never write API keys into logs, error messages, analytics or git.

Do not implement key swapping as a way to evade a provider's rate limits, free-tier restrictions or account limits. Respect each provider's quotas and acceptable-use terms. Cool down a provider after a rate-limit response. A configured alternate provider is a reliability option, not a quota-evasion mechanism.

## 20. Candidate profile and CV processing

CV inputs:

- PDF text-based;
- DOCX;
- scanned PDF/image only if OCR is implemented safely;
- optionally pasted profile content.

Processing requirements:

1. Validate file type, extension, MIME and size.
2. Store original privately.
3. Extract text and page/section metadata.
4. Preserve extracted text and extraction warnings.
5. Structure candidate profile with schema validation.
6. Show editable review UI.
7. Keep profile versions and source references.
8. Never invent metrics, job titles, dates, skills, education, achievements or responsibilities.
9. Maintain evidence links from generated CV claims to profile facts.
10. Allow the user to mark a fact as verified/corrected.

Profile areas:

- contact/basic professional information;
- headline/summary;
- education;
- work/internship experience;
- organization/leadership experience;
- projects;
- skills and proficiency where user-confirmed;
- certificates;
- awards;
- publications/research;
- languages;
- portfolio/social/professional links;
- career preferences.

## 21. Matching and ranking

Do not ask the LLM to invent a score without a transparent calculation.

Recommended layers:

1. eligibility/rule filters;
2. normalized explicit skill matching;
3. semantic matching where justified;
4. role/experience relevance;
5. personal preference fit;
6. optional AI explanation/reranking for shortlist only.

Keep separate scores:

- `candidate_fit_score` — how well the candidate's evidence meets the vacancy requirements;
- `preference_fit_score` — how well the opportunity matches the user's preferred conditions;
- `data_confidence_score` — how complete/reliable the source data is.

Overall score may be calculated only with documented weights. Missing fields should not be treated as zero or a win. Expose the score breakdown and matched/missing/partial evidence.

## 22. Job comparison (maximum two)

The comparison module must enforce exactly two selected vacancy IDs at the backend/API layer, not only visually.

Compare at least:

- role and career direction;
- required skills vs candidate evidence;
- educational eligibility;
- work arrangement;
- location and commute preference;
- compensation/stipend;
- benefits;
- duration/employment type;
- deadline and recruitment stage;
- mentorship/learning opportunity if evidence exists;
- source confidence and freshness;
- red flags/unknown information.

Default comparison categories can include:

- candidate fit;
- location;
- work arrangement;
- salary/compensation;
- benefits;
- career growth/learning;
- eligibility;
- application practicality.

Allow user-defined weights. Provide criterion winner only when there is sufficient comparable information. Otherwise display `Unknown` or `Tie`. Explain each result with evidence. Avoid false precision.

## 23. CV tailoring and application preparation

- generate a tailored CV as a new immutable version;
- keep master CV unchanged;
- use only verified profile evidence;
- preserve truthful dates, titles, responsibilities and metrics;
- support Indonesian and English output;
- support section reordering;
- allow individual bullet acceptance/rejection;
- show before/after diff;
- provide cover letter draft;
- generate PDF/DOCX with stable layout;
- save source vacancy ID and generation settings;
- provide direct original application URL;
- never auto-submit an application.

---

# PART VI — DATA MODEL CHECKLIST

## 24. Suggested core entities

Claude must design a normalized PostgreSQL schema, migrations, constraints and indexes. The exact table design may differ if justified, but it must cover these concepts.

### Personal and profile

- `app_settings`
- `owner_account` or equivalent private owner record
- `career_preferences`
- `candidate_profiles`
- `candidate_profile_versions`
- `candidate_educations`
- `candidate_experiences`
- `candidate_projects`
- `candidate_skills`
- `candidate_certifications`
- `candidate_awards`
- `candidate_languages`
- `candidate_links`
- `resume_documents`
- `resume_extractions`

### Sources and collection

- `sources`
- `source_connector_configs`
- `source_policy_reviews`
- `source_runs`
- `source_run_items`
- `source_cursors`
- `source_health_events`
- `source_exclusions`
- `import_batches`
- `import_items`
- `raw_source_documents`
- `raw_source_versions`
- `source_media_assets`
- `content_transcriptions`

### Intelligence and canonical opportunities

- `companies`
- `company_aliases`
- `job_vacancies`
- `job_vacancy_sources`
- `job_requirements`
- `job_skills`
- `job_benefits`
- `job_locations`
- `job_evidence`
- `opportunity_signals`
- `signal_entities`
- `sentiment_analyses`
- `topic_clusters`
- `trend_observations`
- `deduplication_candidates`
- `vacancy_status_history`

### Personal decision workflow

- `match_analyses`
- `match_score_breakdowns`
- `job_comparisons`
- `job_comparison_items`
- `comparison_weights`
- `saved_opportunities`
- `application_records`
- `tailored_resumes`
- `cover_letters`
- `user_notes`

### AI and operations

- `ai_provider_configs` (encrypted secret references, never plaintext API keys)
- `ai_model_configs`
- `ai_usage_events`
- `ai_prompt_versions`
- `processing_jobs`
- `audit_events`
- `backup_records` if needed.

Use JSONB selectively for raw/extracted flexible payloads, but keep frequently filtered/queried core fields in typed columns. Add indexes for common filters, foreign keys, unique constraints, full-text search, and vector search only when justified.

---

# PART VII — SEQUENTIAL CLAUDE CODE PROMPTS

## How to execute the blocks

- Run one block at a time.
- Claude must summarize changed files, tests, risks and commit hash after each block.
- Claude must not claim completion when tests are failing.
- Use semantic commits with Conventional Commit format.
- Do not squash, amend, force-push or disable hooks unless explicitly instructed.
- Prefer small, reviewable diffs.
- Keep documentation synchronized with actual implementation.
- If a block reveals an architectural issue, pause and write/update an ADR before continuing.

---

# MASTER PROMPT — PROJECT OPERATING INSTRUCTIONS

Paste this once before Prompt Block 00.

```text
You are the principal product engineer, software architect, data engineer, web crawling specialist, AI engineer, security engineer, UX engineer, QA lead, and DevOps engineer responsible for building Unjobless from scratch.

PRODUCT:
Unjobless is a private, personal-first AI Career Discovery & Application Intelligence PWA. It discovers broad career-related opportunities from accessible and permitted online sources; supports formal job vacancies and informal opportunity signals; imports batches of user-supplied URLs and pasted content; preserves raw source evidence; extracts rich structured information; analyzes opportunity signals, sentiment and career topics; deduplicates and verifies records; matches opportunities against one personal master career profile; compares a maximum of two vacancies; generates truthful job-specific CV recommendations and application documents; and links to the original application page.

OPERATING RULES:
1. Build from the actual repository state. Inspect before changing anything.
2. Do not assume the repository is empty. Never overwrite existing work without inspection and explicit reason.
3. Do not blindly force a technology stack. Evaluate the project requirements, current official documentation and maintenance status. Select the simplest maintainable architecture that satisfies the requirements.
4. Avoid premature microservices. Keep domain modules cohesive. Separate workers only where asynchronous collection, parsing or media processing requires it.
5. Prioritize Docker Compose portability to an ordinary VPS. The full system must be reproducible and migratable.
6. This is a private single-owner v1. Do not build billing, payments, public signup, enterprise tenancy or multi-user administration. Keep extension points clean.
7. Build an extensible source connector architecture. Broad discovery is a priority, but only collect data using permitted, accessible methods. Respect terms, robots directives, quotas, rate limits and privacy. Never bypass login, CAPTCHA, paywalls or access controls.
8. Support official APIs, documented ATS endpoints, permitted public career pages, RSS/Atom, sitemaps, permitted structured data, approved public web crawling, user URL import and user-pasted content. Social APIs and media processing must follow their applicable rules.
9. Never claim complete internet coverage. Be explicit about source coverage, last checked time, failures and missing data.
10. Preserve raw source documents, timestamps, URLs and field-level evidence. Keep raw content separate from AI-derived normalized data.
11. Separate direct vacancies, unverified opportunity leads, referral signals, recruitment discussions, employer sentiment, career trends and irrelevant content.
12. Sentiment analysis is not vacancy detection. Never turn a generic mention of internship into a confirmed job.
13. Never fabricate any vacancy field, salary, benefit, deadline, eligibility, company, application link or candidate achievement.
14. AI-generated CV claims must trace to user-confirmed profile evidence.
15. Enforce the maximum-two-vacancy comparison limit in the backend as well as the UI.
16. Make AI providers interchangeable. API keys must be encrypted at rest and never returned to the browser after saving. Never commit secrets. Provider fallback must not be used to evade quotas or rate limits.
17. Design the UI using the supplied reference image at `docs/design-references/unjobless-ui-reference.webp` if present. Translate its soft light-grey surfaces, purple/lilac accents, large rounded cards, subtle shadows, clean typography and minimal elegant composition into original Unjobless screens. Do not copy the reference brand, medical content, mascot or exact layout.
18. Build a genuinely responsive PWA for mobile, tablet and desktop, with iOS/Android/macOS installation guidance and graceful platform limitations.
19. Include accessibility, reduced motion, loading/empty/error states, mobile safe areas and keyboard navigation.
20. Use semantic commits. Suggested format: `feat(scope): ...`, `fix(scope): ...`, `docs(scope): ...`, `test(scope): ...`, `refactor(scope): ...`, `build(scope): ...`, `chore(scope): ...`.
21. Every implementation block must add or update tests and documentation appropriate to its scope.
22. Before a commit: format, lint, typecheck, run relevant tests, inspect `git diff`, and ensure there are no secrets or generated junk files.
23. If a test cannot run, state exactly why. Never silently skip it.
24. Prefer stable, actively maintained dependencies. Verify current versions and APIs using official documentation when network access is available. Do not install packages from abandoned examples.
25. Keep `README.md`, `.env.example`, architecture docs, setup instructions, backup/restore guide and deployment guide accurate.

QUALITY BAR:
Production-minded code, clear boundaries, typed contracts, validation at trust boundaries, structured logs, safe retries, idempotent jobs, database migrations, observability, testability, predictable errors, and simple operations.

WORK STYLE:
Work only on the current requested prompt block. Do not jump ahead and implement later blocks prematurely. First inspect the repository and relevant docs. Propose a concise plan, implement, run checks, inspect the diff, update docs, make the requested semantic commit if all checks pass, and report the commit hash plus remaining risks. If blocked, stop and report the blocker rather than inventing a workaround.
```

---

# PROMPT BLOCK 00 — DISCOVERY, REPOSITORY AUDIT AND BUILD PLAN

```text
Start Unjobless by auditing the repository and development environment. Do not implement product features yet.

Tasks:
1. Inspect all existing files, Git status, branches, package manifests, lockfiles, runtime versions, Docker files, tests and documentation.
2. Check whether the repository is genuinely empty or contains a prior scraper/project that could be reused. Do not delete or overwrite reusable components.
3. Inspect `docs/design-references/unjobless-ui-reference.webp` if present. If absent, record that the design reference must be copied into that path.
4. Map requirements from `UNJOBLESS_BUILD_PLAYBOOK.md` into epics and dependencies.
5. Identify the main workloads: web UI, scheduled crawling, user URL import, HTML parsing, possible browser extraction, OCR/transcription, AI processing, search and PWA.
6. Identify likely risks: source permissions, SSRF, duplicate data, stale vacancies, provider limits, sensitive CV data, Docker storage and backups.
7. Do not install a large set of dependencies yet.

Deliverables:
- `docs/PROJECT_AUDIT.md`
- `docs/REQUIREMENTS_TRACEABILITY.md`
- `docs/IMPLEMENTATION_ROADMAP.md`
- a proposed small-block build order;
- a list of existing code/assets worth reusing;
- explicit assumptions and unresolved decisions.

Acceptance:
- No existing work was destroyed.
- Audit findings are based on actual repository inspection.
- Every major product requirement maps to a future implementation block and test.

Commit: `docs(project): add repository audit and implementation roadmap`
```

# PROMPT BLOCK 01 — ARCHITECTURE OPTIONS AND ADRs

```text
Using the completed audit and Unjobless requirements, evaluate the architecture before implementation.

Compare at least two realistic designs. Consider:
- one full-stack framework plus a separate Python collection worker;
- a TypeScript web/backend plus Python workers;
- a Python-centered backend with a modern frontend.

Evaluate maintainability, crawling ecosystem, background jobs, AI integration, PWA, Docker portability, migration, memory footprint and operational simplicity on a single VPS.

Choose the simplest architecture that supports:
- private single-owner usage;
- broad multi-source ingestion;
- asynchronous collection and parsing;
- PostgreSQL persistence;
- rich search/filtering;
- AI provider abstraction;
- PWA;
- Docker Compose deployment.

Inspect current official documentation and package maintenance before choosing exact frameworks and packages. Record selected versions and why. Avoid microservices unless a concrete requirement justifies a separate deployable service.

Deliver:
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/ADRs/0001-architecture-style.md`
- `docs/architecture/ADRs/0002-data-and-search.md`
- `docs/architecture/ADRs/0003-collection-and-workers.md`
- `docs/architecture/ADRs/0004-ai-provider-abstraction.md`
- `docs/architecture/ADRs/0005-docker-vps-deployment.md`
- Mermaid system context, container and data-flow diagrams.

Do not build the application yet.

Acceptance: architecture is justified against requirements, not fashion; Docker and migration are addressed.

Commit: `docs(architecture): document system design and architecture decisions`
```

# PROMPT BLOCK 02 — DOMAIN MODEL AND STATE MACHINES

```text
Design the Unjobless domain model before building UI or scraping code.

Define entities and relationships for:
- source and source connector;
- source run and collection item;
- raw source document and raw version;
- company and aliases;
- canonical vacancy and source references;
- opportunity signal;
- sentiment/topic observation;
- evidence and field confidence;
- career profile and profile version;
- matching analysis;
- two-item comparison;
- saved opportunity and application record;
- tailored resume and cover letter;
- import batch and import item;
- AI provider/model configuration and usage event.

Define explicit enums/state machines for source health, import state, opportunity classification, verification state, vacancy lifecycle, application status, AI task status and collection job status.

Create an ER diagram and explain which fields are typed columns versus JSONB. Add lifecycle transition diagrams.

Deliver:
- `docs/domain/DOMAIN_MODEL.md`
- `docs/domain/STATE_MACHINES.md`
- `docs/domain/ERD.mmd`

Acceptance:
- Direct vacancy and unverified signal are separate concepts.
- Sentiment is separate from opportunity classification.
- Raw content and normalized vacancy are separate.
- One vacancy can have several source references.
- Master CV and tailored CV are separate/versioned.
- Comparison has a hard maximum of two items.

Commit: `docs(domain): define opportunity intelligence domain model`
```

# PROMPT BLOCK 03 — PROJECT SCAFFOLD AND ENGINEERING BASELINE

```text
Implement only the selected project scaffold from the approved ADRs.

Requirements:
- create a clean, understandable monorepo or repository structure;
- set runtime/tool versions using supported version managers or documented constraints;
- add package/dependency lockfiles;
- configure formatting, linting, type checking and test runners;
- establish environment configuration validation;
- establish consistent error handling;
- establish structured logging interfaces;
- configure path aliases/import boundaries if useful;
- add basic health endpoints or placeholder checks;
- add `.gitignore` and `.dockerignore`;
- ensure no secrets are committed.

Do not implement business features yet.

Suggested directory responsibilities should be clear: web, API/domain, connectors, workers, shared contracts, database, tests, docs and deployment. Adapt to chosen stack.

Acceptance:
- clean install from lockfiles works;
- format/lint/typecheck/test commands are documented;
- minimal app starts locally;
- no secrets in repository.

Commit: `build(scaffold): initialize Unjobless engineering workspace`
```

# PROMPT BLOCK 04 — DESIGN SYSTEM AND RESPONSIVE APP SHELL

```text
Build the Unjobless design system and application shell using the supplied UI reference as visual direction.

First inspect `docs/design-references/unjobless-ui-reference.webp` if present. Implement the design tokens from the playbook, adjusting only with a documented reason.

Visual requirements:
- light neutral grey background;
- white and soft-grey surfaces;
- purple/lilac brand accent and restrained gradient;
- dark high-contrast typography;
- large rounded cards;
- subtle shadows and minimal borders;
- pill-style primary actions;
- subtle glass/translucency only where useful;
- clean, uncluttered, professional composition.

Build:
- global typography and color tokens;
- button variants;
- inputs/selects/textareas;
- badges/status chips;
- cards;
- modal/dialog;
- tabs;
- dropdown/menu;
- tooltips;
- skeleton/loading states;
- empty states;
- alerts/toasts;
- responsive sidebar/topbar/bottom navigation;
- page container and responsive grid.

Create responsive app shell for mobile, tablet and desktop. Mobile must include safe-area-aware navigation and touch-friendly targets. Ensure keyboard access and reduced-motion support.

Do not use the reference medical mascot or its branding. Use original Unjobless wordmark treatment; avoid inventing elaborate logos.

Deliver/update `docs/design/DESIGN_SYSTEM.md` and tokens.

Acceptance:
- mobile width around 360px is usable;
- tablet layout is intentional;
- desktop sidebar/content layout is balanced;
- components have focus/disabled/loading states;
- no horizontal overflow except intentionally scrollable data regions.

Commit: `feat(ui): establish Unjobless design system and responsive shell`
```

# PROMPT BLOCK 05 — NAVIGATION, ROUTES AND PAGE SKELETONS

```text
Implement the main navigation and route skeleton based on the approved product information architecture.

Pages:
- Overview
- Discover
- Opportunity Signals
- Compare
- My Career Profile
- Applications
- Import Center
- Sources
- Career Intelligence
- AI Studio
- Settings

For each page create a polished page header, breadcrumb if appropriate, primary action, loading state, empty state and responsive layout. Use realistic but clearly marked mock data only until APIs are connected. Do not show fake live counts as real metrics.

Hide future modules behind a feature flag or a clearly disabled state; do not create dead buttons.

Acceptance:
- route navigation works;
- active route state is clear;
- mobile navigation works;
- page shells are consistent;
- all actions either work or are explicitly disabled with explanation.

Commit: `feat(navigation): add Unjobless workspace routes and page shells`
```

# PROMPT BLOCK 06 — DATABASE, MIGRATIONS AND SEEDING

```text
Implement the PostgreSQL schema according to the approved domain model.

Requirements:
- use versioned migrations, not manual-only schema changes;
- define primary keys, foreign keys, unique constraints and check constraints;
- use timezone-aware timestamps;
- use JSONB only for flexible payloads, not every field;
- add indexes for source/time/status/company/title/location/skills and common feed filters;
- add full-text search indexes where supported;
- leave vector extensions optional until the embedding use case is justified;
- define deletion and retention behavior;
- seed only safe development examples clearly marked as fixtures;
- support clean database creation from zero;
- support migration from one application version to the next.

Implement repository/data access boundaries and transaction helpers as appropriate.

Add tests for constraints, relationships and migration-from-empty behavior.

Deliver `docs/database/SCHEMA.md` and a schema diagram.

Acceptance:
- fresh database migrations succeed;
- constraints prevent invalid state;
- no application code relies on undocumented manual DB steps.

Commit: `feat(database): add versioned Unjobless PostgreSQL schema`
```

# PROMPT BLOCK 07 — PRIVATE OWNER ACCESS AND APP SECURITY BASELINE

```text
Implement secure private single-owner access for v1.

Requirements:
- no public sign-up;
- first-run owner bootstrap must be safe and one-time;
- use a strong password or supported passkey/auth method appropriate to the chosen stack;
- secure session cookies: HttpOnly, Secure in production, SameSite appropriate, bounded lifetime;
- CSRF protection where applicable;
- brute-force protection and sensible login throttling;
- session revocation/logout;
- private route/API authorization;
- no owner secrets in client bundles;
- security headers and safe CORS policy;
- audit important settings/key changes without logging secrets.

Do not add multi-tenant billing or organization roles.

Acceptance:
- unauthenticated users cannot access personal data, APIs, files or settings;
- bootstrap cannot be repeated after initial owner creation;
- security tests cover auth boundaries.

Commit: `feat(auth): secure private Unjobless owner workspace`
```

# PROMPT BLOCK 08 — SOURCE REGISTRY AND CONNECTOR CONTRACT

```text
Implement the source registry and the common source connector contract. Do not scrape real sources in this block.

Each connector should declare:
- source ID/name/domain/category;
- official documentation/terms URL;
- permitted access method;
- enabled/disabled state;
- configuration schema;
- auth requirement and secret reference if needed;
- rate limit/quota settings;
- default schedule;
- supported discovery/fetch/parse capabilities;
- pagination/cursor support;
- incremental sync support;
- health check;
- retry/backoff defaults;
- content types supported;
- provenance requirements.

Build:
- connector interface/protocol;
- connector registry/factory;
- source configuration storage;
- enable/disable/pause/resume controls;
- source policy review fields;
- source health model;
- mock connector for tests.

A source with unclear permissions must remain disabled until reviewed. Add a source exclusion/denylist.

Acceptance:
- a new mock connector can be added without modifying the core ingestion pipeline;
- source settings persist;
- disabled sources cannot collect.

Commit: `feat(sources): add extensible source registry and connector contract`
```

# PROMPT BLOCK 09 — RAW INGESTION AND EVIDENCE STORE

```text
Implement the raw source ingestion layer.

Requirements:
- preserve original raw text/content where retention is allowed;
- preserve source URL, source ID, source-native ID when allowed, publication time, collection time and collection method;
- calculate stable content hashes;
- store raw versions when content changes;
- store extracted text separately from HTML or metadata;
- store media references and permitted downloaded assets separately;
- enforce content size limits;
- avoid storing secrets, cookies or session headers;
- support retention policies and safe deletion;
- provide traceability from canonical vacancy/signal back to the raw source.

Add tests for identical content hashes, changed content versions, missing metadata and oversized payloads.

Commit: `feat(ingestion): preserve raw source documents and evidence provenance`
```

# PROMPT BLOCK 10 — SOURCE POLICY, ROBOTS, RATE LIMITS AND SSRF GUARDS

```text
Implement the safety and access-control layer before building URL fetchers.

Requirements:
1. URL validation with HTTP/HTTPS allowlist.
2. DNS resolution and private/reserved IP blocking.
3. Revalidate redirect targets and defend against DNS rebinding.
4. Block localhost, loopback, private networks, link-local, multicast, reserved ranges and cloud metadata endpoints.
5. Enforce response size, content type, redirect count and timeouts.
6. Apply per-source rate limits and concurrency caps.
7. Implement source policy configuration including robots directives and documented source rules where applicable.
8. Provide an explicit source allowlist and denylist.
9. Never bypass login, CAPTCHA, paywalls, anti-bot systems or access restrictions.
10. Isolate browser automation from internal services and secrets.
11. Log blocked requests safely without recording sensitive request data.

Create security tests, including redirect-to-private-IP and DNS/IP validation cases.

Acceptance:
- malicious user-submitted URLs cannot reach internal services;
- rate limits are enforced;
- source policy can disable collection;
- no access-control bypass exists.

Commit: `feat(security): enforce safe URL fetching and source access policies`
```

# PROMPT BLOCK 11 — COLLECTION QUEUE, SCHEDULER AND WORKER LIFECYCLE

```text
Implement background collection infrastructure using the chosen queue/scheduler technology.

Requirements:
- enqueue source run;
- per-source schedule;
- manual run-now;
- pause/resume source;
- retry with exponential backoff and jitter;
- idempotency keys;
- per-source concurrency cap;
- global concurrency cap;
- timeouts;
- cancellation where possible;
- failed/dead-letter state;
- persisted checkpoints/cursors;
- graceful worker shutdown;
- stale/locked-job recovery;
- run history and status counters.

Do not build source-specific scrapers yet. Use the mock connector.

Add integration tests for success, failure, retry, duplicate enqueue, pause, timeout and worker restart.

Commit: `feat(jobs): add persistent collection queue and scheduler`
```

# PROMPT BLOCK 12 — FIRST REAL CONNECTORS: APPROVED JOB APIs AND ATS

```text
Implement the first source connectors using sources with documented and permitted public job access. Do not assume a platform has an API merely because a page is publicly viewable.

Candidate connector types to investigate:
- documented job aggregator APIs with supported Indonesia coverage;
- public Greenhouse job boards;
- public Lever postings;
- public Ashby job boards;
- other documented ATS endpoints only after validating their current public-use rules.

For every source:
1. inspect current official documentation;
2. record terms/access method and quotas;
3. implement connector-specific configuration;
4. implement pagination and incremental sync if possible;
5. map every supported field to the canonical raw/normalized model;
6. store original URL and application URL;
7. avoid inventing salary, deadline, remote status or missing fields;
8. add source-specific fixtures and contract tests;
9. provide sample configuration in `.env.example` or source settings without secrets.

Do not scrape prohibited platforms. Do not pretend these connectors cover all jobs on those platforms.

Acceptance:
- connectors can be independently enabled/disabled;
- source health reports quota/errors;
- normalized records retain source provenance.

Commit: `feat(connectors): add documented job API and ATS connectors`
```

# PROMPT BLOCK 13 — PERMITTED CAREER-PAGE CRAWLER

```text
Implement a generic public career-page crawler for explicitly enabled and permitted domains.

Capabilities:
- fetch robots/sitemap/RSS where applicable;
- discover candidate job URLs from approved paths/selectors;
- parse structured JobPosting data when present;
- extract main content with a maintained readable-content parser;
- capture canonical URL and relevant metadata;
- use conditional requests/ETag/Last-Modified where supported;
- detect changes using content hashes;
- respect crawl delay, quotas, domain concurrency and exclusions;
- avoid crawling unrelated site sections;
- do not bypass access controls or bot protections;
- provide source-specific overrides without forking the whole crawler.

Add an admin/source UI to register an allowed domain, policy notes, crawl paths, interval and extraction selector overrides. Default new domains to disabled pending review.

Acceptance:
- tests use local fixture HTML, not uncontrolled live websites;
- crawler only visits enabled domains;
- changes create source versions;
- blocked pages are reported as unavailable rather than bypassed.

Commit: `feat(crawler): add policy-aware public career page crawler`
```

# PROMPT BLOCK 14 — UNIVERSAL URL IMPORTER

```text
Build the Universal URL Importer for one or multiple user-supplied URLs.

UX:
- textarea accepts one URL per line;
- paste multiple URLs;
- validate and show invalid lines before submission;
- remove duplicates within the batch;
- show detected domain/source;
- allow optional user note and category hint;
- submit batch to background queue;
- display per-item status: queued, fetching, extracted, needs review, saved, duplicate, blocked, unavailable, failed;
- show actionable failure reason and paste-content fallback.

Backend:
- use SSRF-safe fetcher from previous block;
- use a matching connector when available;
- otherwise use only permitted public page extraction;
- preserve raw content and metadata;
- apply size/time/redirect limits;
- never bypass login/CAPTCHA/paywall/anti-bot protections;
- allow retry after user correction;
- make import idempotent.

Acceptance:
- a batch does not fail entirely because one URL fails;
- every item has its own state and provenance;
- unsafe URLs are blocked;
- manual fallback works.

Commit: `feat(import): add secure batch URL opportunity importer`
```

# PROMPT BLOCK 15 — PASTE CONTENT IMPORTER

```text
Build the paste-content importer for copied career-related information.

Inputs:
- raw pasted text;
- optional source URL;
- optional platform/source name;
- optional author/account label (only when appropriate and public);
- optional publication timestamp;
- optional content type hint;
- optional user notes;
- optional pasted OCR/transcript text.

Requirements:
- preserve exact pasted text;
- store metadata and content hash;
- classify content type;
- enqueue extraction;
- show review UI;
- support batch paste records if useful;
- allow user correction and source URL addition;
- keep unverified leads distinct from confirmed vacancies.

Acceptance:
- paste import works even if original platform cannot be crawled;
- all extracted fields link back to source text spans or evidence excerpts where possible.

Commit: `feat(import): add paste-based opportunity content importer`
```

# PROMPT BLOCK 16 — MULTIMODAL CONTENT PROCESSING

```text
Implement a modular media-processing pipeline for user-supplied or otherwise permitted content.

Supported processing where access and licensing permit:
- images/poster OCR;
- image metadata and alt text;
- PDF text extraction;
- scanned PDF OCR fallback;
- audio transcription;
- video transcript extraction from permitted sources;
- captions/subtitles where available;
- media language detection.

Use local/open-source tools where practical and optional provider adapters where local processing is insufficient. Do not make the app dependent on one paid media API.

Requirements:
- validate file types and size;
- malware/content safety checks appropriate to file handling;
- isolate parsing processes;
- limit CPU/memory/time;
- store media references and derived text with provenance;
- record whether transcript/OCR is original, user-provided or machine-generated;
- never bypass platform restrictions to download media;
- provide processing failure status and manual text fallback.

Acceptance:
- sample images/posters produce reviewable OCR text;
- extracted text retains media provenance;
- failures do not lose the original import.

Commit: `feat(media): add permitted OCR and audio-video text extraction pipeline`
```

# PROMPT BLOCK 17 — CONTENT CLASSIFICATION AND OPPORTUNITY SIGNAL DETECTION

```text
Implement the Opportunity Signal Engine. This is a core differentiator.

Do not classify content using only a static keyword list. Combine:
- configurable multilingual seed keywords;
- keyword expansion/synonym lists;
- deterministic rules;
- lightweight NLP/classification;
- optional LLM classification for ambiguous items;
- context/evidence extraction.

Languages initially: Indonesian and English. Include informal/slang terms where useful, such as magang, loker, lowker, intern, internship, hiring, recruitment, open recruitment, batch, trainee, MT, referral, kirim CV, DM, and related variants. Keep terms configurable and test for false positives.

Classifications:
- DIRECT_VACANCY;
- INFORMAL_OPPORTUNITY_LEAD;
- REFERRAL_SIGNAL;
- RECRUITMENT_CAMPAIGN;
- CAREER_PROGRAM;
- EMPLOYER_DISCUSSION;
- EMPLOYER_REVIEW;
- CAREER_TREND;
- IRRELEVANT.

For each result, produce:
- primary and secondary classification;
- confidence;
- evidence excerpt(s);
- entities: company, role, location, dates, contact/application URL where publicly stated;
- explicit vs inferred field markers;
- verification status recommendation;
- reason for classification;
- ambiguity flags.

Critical examples to test:
- direct hiring announcement;
- informal referral offer;
- “maybe hiring next month” rumour;
- person asking whether a company has internship openings;
- negative internship review with no vacancy;
- unrelated use of the word “internship”;
- old/expired hiring post;
- recruitment poster with missing details.

Never convert an unverified signal to a verified vacancy merely because the confidence score is high. Verification requires evidence rules.

Acceptance:
- evaluation dataset and precision/recall report exist;
- false-positive cases are documented;
- output is structured and schema-validated.

Commit: `feat(intelligence): detect formal vacancies and informal opportunity signals`
```

# PROMPT BLOCK 18 — SENTIMENT, TOPIC AND TREND ANALYSIS

```text
Implement sentiment, topic and trend analysis as separate capabilities from opportunity detection.

Sentiment dimensions:
- positive, neutral, negative, mixed, uncertain;
- target entity/aspect: company, recruitment process, interview, internship experience, manager/mentorship, work culture, compensation, workload, role or job search;
- evidence excerpts;
- language;
- sarcasm/irony uncertainty;
- confidence.

Topic dimensions:
- internship opening;
- recruitment batch;
- hiring freeze;
- campus hiring;
- referral;
- interview experience;
- application outcome;
- stipend/salary transparency;
- work culture;
- remote/hybrid/WFO;
- career program;
- emerging topic.

Trend requirements:
- aggregate observed time-series records;
- show count and time window;
- distinguish posts from unique sources and unique companies;
- do not describe an increase unless data supports it;
- flag low sample sizes;
- do not infer company hiring intent from general positive sentiment.

Provide filters by company/topic/date/source and link every insight to underlying public source records.

Acceptance:
- sentiment does not affect vacancy state directly;
- trends are reproducible from stored observations;
- small samples are visibly labelled.

Commit: `feat(intelligence): add employer sentiment topic and recruitment trend analysis`
```

# PROMPT BLOCK 19 — MULTILINGUAL EXTRACTION AND CANONICAL NORMALIZATION

```text
Implement structured extraction and normalization for Indonesian and English career content.

Extract all relevant vacancy fields in the playbook, not only title/company/location. Use a versioned schema and structured AI outputs. Validate every response.

Requirements:
- field-level evidence;
- field-level confidence;
- explicit/inferred/missing marker;
- normalized employment type;
- normalized work arrangement;
- location normalization;
- compensation parsing with currency and pay period;
- deadline/date parsing with timezone uncertainty;
- skill taxonomy/aliases;
- education/semester/GPA normalization;
- benefits and responsibilities extraction;
- application URL extraction;
- source language and normalized language where appropriate.

Never hallucinate missing fields. If parsing is uncertain, preserve the raw value and mark needs review.

Acceptance:
- JSON schema validation;
- golden fixtures for Indonesian and English examples;
- no inferred salary/deadline without explicit evidence;
- all derived fields link to source evidence.

Commit: `feat(extraction): normalize rich vacancy data with field-level evidence`
```

# PROMPT BLOCK 20 — COMPANY RESOLUTION AND DEDUPLICATION

```text
Implement company entity resolution and opportunity deduplication.

Company resolution:
- normalize legal and trading names;
- manage aliases;
- use domain/website as supporting evidence;
- distinguish similarly named companies;
- allow manual correction.

Vacancy deduplication:
- canonical URL;
- source-native ID;
- application URL;
- company identity;
- normalized title;
- location;
- description similarity;
- dates.

Requirements:
- create candidate duplicate groups;
- auto-merge only when confidence/rules justify it;
- send ambiguous cases to review;
- preserve all source references and raw documents;
- retain status history;
- do not merge different locations/levels when they are genuinely separate vacancies.

Add a merge-review UI and undo/audit trail.

Acceptance:
- same vacancy from two sources can become one canonical record with two source references;
- distinct roles do not merge incorrectly in fixtures;
- merge decisions are traceable.

Commit: `feat(data): add company resolution and cross-source vacancy deduplication`
```

# PROMPT BLOCK 21 — FRESHNESS, DEADLINE AND VACANCY LIFECYCLE

```text
Implement vacancy lifecycle and freshness management.

Track first seen, last seen, last checked, last verified, source publication time, application deadline, closed date, source availability and status reason.

Rules:
- failed fetch is not proof a job is closed;
- old publication date is not proof the job is expired unless supported by evidence;
- explicit past deadline can mark expired with a documented rule;
- source disappearance should be uncertain until corroborated;
- repeated current source confirmation can increase confidence;
- manual user correction must be supported;
- preserve historical state changes.

Add a scheduled status recheck for enabled sources within their permitted collection limits.

Acceptance:
- vacancy state transitions are deterministic and tested;
- uncertain records are visibly uncertain;
- feed can filter new, active, closing soon, expired and unknown.

Commit: `feat(vacancies): track opportunity freshness and lifecycle status`
```

# PROMPT BLOCK 22 — SEARCH, FILTERING AND DISCOVERY FEED

```text
Build the Discover and Opportunity Signals experience using real database queries.

Requirements:
- full-text search;
- filters for role/title, company, industry, source, role type, skills, location, remote/hybrid/onsite, education, deadline, compensation, status, freshness and confidence;
- sort by newest, best profile fit, preference fit, deadline and data confidence;
- saved filters/views if useful;
- clear badges distinguishing verified vacancy from unverified lead;
- source and update timestamps;
- direct original source/application links;
- save/dismiss/mark interesting actions;
- pagination or cursor loading appropriate to expected volume;
- responsive cards on mobile and data-rich view on desktop.

Do not display mock metrics as production truth. Show honest empty/loading/error states.

Acceptance:
- filters combine correctly;
- pagination is stable;
- mobile UI remains readable;
- original source attribution is visible.

Commit: `feat(discover): build searchable personalized opportunity feed`
```

# PROMPT BLOCK 23 — MASTER CAREER PROFILE AND CV INGESTION

```text
Implement personal career profile and CV upload/extraction.

Supported formats: PDF and DOCX; scanned PDF/image OCR as an optional fallback.

Process:
1. validate file and size;
2. private storage;
3. text extraction;
4. section detection;
5. schema-based AI structuring;
6. evidence linking;
7. profile review/edit;
8. confirm and version.

Profile sections:
- education;
- work/internship experience;
- organization/leadership;
- projects;
- skills;
- certifications;
- awards;
- research/publications;
- languages;
- links/portfolio;
- summary/headline.

Requirements:
- master CV never overwritten by tailored outputs;
- user can maintain multiple source CV versions but designate one active profile;
- support Indonesian and English;
- never invent metrics or facts;
- extraction warnings and uncertain facts must be reviewable;
- file access is private.

Acceptance:
- user can upload, review, correct, save and version a CV;
- original document remains unchanged;
- evidence provenance is stored.

Commit: `feat(profile): add private CV ingestion and editable master career profile`
```

# PROMPT BLOCK 24 — PERSONAL PREFERENCES AND OPPORTUNITY MATCHING

```text
Implement career preferences and matching.

Preferences include:
- target roles/job families;
- preferred industries;
- desired skills to develop;
- employment types;
- preferred work arrangement;
- preferred cities/regions;
- remote eligibility;
- commute/location preference (manual area input; do not require precise location);
- minimum compensation when relevant;
- education/semester eligibility;
- career goals;
- excluded industries/companies/conditions.

Matching layers:
1. eligibility filters;
2. explicit skill match;
3. semantic relevance where justified;
4. experience/project evidence relevance;
5. personal preference fit;
6. data confidence.

Keep `candidate_fit_score`, `preference_fit_score` and `data_confidence_score` distinct. Explain the breakdown and evidence. Missing fields are unknown, not automatically zero.

Use deterministic calculations for numeric scores. LLM may explain or rerank a shortlist but must not invent evidence.

Acceptance:
- user can edit preferences;
- match changes after profile/preferences changes;
- explanations link to candidate evidence and vacancy requirements;
- score calculation is tested and documented.

Commit: `feat(matching): add evidence-based career opportunity matching`
```

# PROMPT BLOCK 25 — TWO-VACANCY COMPARISON

```text
Build the Job Comparison workspace with a strict maximum of two vacancies.

Hard limit:
- frontend prevents selecting a third;
- API validates exactly two distinct vacancy IDs;
- service rejects zero, one or more than two items as appropriate to endpoint design;
- tests cover attempts to submit three or duplicated IDs.

Compare:
- role/career direction;
- candidate fit;
- skills;
- eligibility;
- location/commute preference;
- work arrangement;
- compensation/stipend;
- benefits;
- duration/employment type;
- deadline and recruitment stage;
- mentorship/learning evidence;
- source confidence/freshness;
- missing information and red flags.

Provide:
- criterion winner: A, B, Tie or Unknown;
- evidence for each side;
- editable comparison weights;
- separate candidate-fit and preference-fit scores;
- optional overall score with transparent weights;
- trade-off summary;
- recommendation with uncertainty;
- saved comparison history.

Do not assume the numerically highest score is always the user's best choice. Explain trade-offs. Do not treat missing salary or location as a zero score.

Acceptance:
- no more than two vacancies can be compared;
- score math is reproducible;
- missing fields are handled fairly;
- responsive side-by-side comparison becomes stacked cards on mobile.

Commit: `feat(compare): add transparent maximum-two vacancy comparison`
```

# PROMPT BLOCK 26 — AI PROVIDER GATEWAY AND SETTINGS

```text
Implement the AI provider abstraction for personal-use Unjobless.

Provider requirements:
- adapter interface;
- provider/model registry;
- task routing;
- structured JSON output support;
- token/usage event tracking;
- estimated cost where pricing configuration is available;
- timeout/retry handling;
- error classification;
- rate-limit cooldown;
- manual model selection;
- optional configured fallback provider;
- per-task budget and output token limits.

Settings UI:
- provider name;
- model name;
- API key add/update/delete;
- masked key status;
- test connection;
- active/default provider;
- task-specific model selection where useful;
- usage history.

Security:
- encrypt API keys at rest using an application master encryption key from environment;
- never expose decrypted keys to frontend;
- do not log keys/prompts containing personal information;
- never commit secrets;
- document how to backup/restore the encrypted settings and master key;
- never rotate keys to evade provider quota/rate-limit rules.

Include at least two provider adapters only if their current API documentation supports the required operations. Keep one adapter sufficient for initial runtime if needed.

Acceptance:
- user can replace a key without rebuilding frontend;
- full key is never returned after save;
- provider errors are understandable;
- tests use mocked provider responses.

Commit: `feat(ai): add secure configurable AI provider gateway`
```

# PROMPT BLOCK 27 — AI EXTRACTION, CLASSIFICATION AND PROMPT VERSIONING

```text
Centralize AI prompt templates and structured output schemas.

Requirements:
- prompt templates versioned in code or database;
- schemas versioned and validated;
- task-specific model selection;
- strict output parsing;
- retry only on recoverable format errors;
- no unlimited loops;
- store prompt/model/version metadata with AI result;
- minimize personal data passed to provider;
- support redaction of unnecessary CV contact details for matching tasks;
- distinguish source text from model-generated interpretation;
- keep provider adapter out of domain logic.

Create tasks for:
- CV structuring;
- job description extraction;
- opportunity signal classification;
- sentiment/topic classification;
- company/role entity extraction;
- job enrichment;
- match explanation;
- comparison explanation;
- CV tailoring;
- cover letter drafting.

Acceptance:
- every AI task has schema, prompt version and tests;
- malformed output cannot corrupt canonical data;
- source evidence is preserved.

Commit: `feat(ai): add versioned structured intelligence pipelines`
```

# PROMPT BLOCK 28 — SOURCE HEALTH AND OBSERVABILITY DASHBOARD

```text
Build the Sources dashboard and operational health views.

Show per source:
- enabled/paused state;
- last successful run;
- last attempted run;
- next scheduled run;
- items discovered;
- new/changed/duplicate items;
- errors and retries;
- quota/rate-limit state when known;
- average run duration;
- source freshness;
- policy review status.

Include:
- run now;
- pause/resume;
- enable/disable;
- view run history;
- view failed items;
- change interval within safe limits;
- edit source configuration;
- view source documentation/policy note.

Never label a source “real-time” unless it is genuinely event-driven. Use clear terms like “last checked” and “next check”.

Acceptance:
- dashboard reflects actual persisted run data;
- source controls work;
- error states are actionable;
- no source failure silently disappears.

Commit: `feat(operations): add source health and collection observability dashboard`
```

# PROMPT BLOCK 29 — CV TAILORING AND COVER LETTER

```text
Implement truthful, evidence-grounded application preparation.

For a selected vacancy:
- select relevant evidence from confirmed master profile;
- identify matching and missing requirements;
- propose a tailored headline/summary;
- propose skill ordering;
- propose project/experience ordering;
- rewrite bullet points without changing facts;
- identify claims requiring user confirmation;
- draft a cover letter in Indonesian or English;
- show before/after diff;
- allow accept/reject/edit at claim or section level.

Rules:
- no invented skills, technologies, metrics, job titles, dates or achievements;
- don't claim a missing skill is possessed;
- do not keyword-stuff unnaturally;
- do not guarantee ATS pass or job acceptance;
- preserve master CV;
- store each tailored result as a new version connected to vacancy ID and source evidence.

Acceptance:
- every generated claim is evidence-linked or flagged for user input;
- edits are reviewable;
- one tailored CV cannot overwrite another.

Commit: `feat(application): add evidence-based CV tailoring and cover letters`
```

# PROMPT BLOCK 30 — DOCUMENT TEMPLATE AND EXPORT

```text
Implement CV document templates and exports.

Requirements:
- clean ATS-friendly templates;
- professional modern visual template inspired by Unjobless but not overly decorative;
- Indonesian and English text support;
- PDF and DOCX output if feasible with selected libraries;
- stable page breaks and margins;
- consistent typography;
- selectable text in PDF where possible;
- links remain clickable;
- avoid icons/columns that break parsing in ATS-friendly template;
- preview before download;
- versioned export files;
- export metadata linked to vacancy and profile version.

Create at least two templates: `ATS Classic` and `Modern Professional`.

Test long CVs, short CVs, multi-page content, long skill lists and Indonesian characters.

Acceptance:
- exported document matches preview closely;
- generated file opens successfully;
- master CV is not changed;
- output is stored privately.

Commit: `feat(export): generate ATS-friendly PDF and DOCX application documents`
```

# PROMPT BLOCK 31 — APPLICATION TRACKER AND DIRECT APPLY LINKS

```text
Build a personal application tracker.

Statuses:
- saved;
- shortlisted;
- preparing;
- applied;
- assessment;
- interview;
- offer;
- rejected;
- withdrawn;
- archived.

Features:
- status timeline;
- application date;
- deadline reminder;
- notes;
- contact/interview notes only when user enters them;
- attached tailored CV/cover letter version;
- original vacancy/source link;
- follow-up date;
- filters and search.

Direct apply:
- open the original application URL in a safe new tab/window;
- clearly indicate external destination;
- validate and display the destination domain;
- do not claim application submitted;
- allow user to mark as applied manually.

Acceptance:
- tracker states persist;
- direct links resolve to stored original destination;
- status history is retained.

Commit: `feat(tracker): add personal application tracking and direct apply links`
```

# PROMPT BLOCK 32 — PWA AND CROSS-DEVICE EXPERIENCE

```text
Implement Unjobless as an installable responsive PWA.

First inspect current maintained PWA tooling and official browser documentation. Choose the simplest supported approach for the selected frontend framework.

Requirements:
- web app manifest;
- original Unjobless app icons and maskable icon assets;
- theme/background colors based on design tokens;
- service worker;
- installability checks;
- update lifecycle and “new version available” UX;
- offline fallback shell;
- cache static assets safely;
- do not aggressively cache private CVs, API responses, AI results, or sensitive data;
- clear offline/online state;
- responsive mobile/tablet/desktop layouts;
- iOS safe areas and standalone display handling;
- Android install flow;
- macOS desktop browser support;
- keyboard, screen reader and reduced-motion behavior.

Push notifications are optional and should only be implemented if the target browser/platform supports the required capabilities. Do not promise identical iOS, Android and desktop notification behavior. Provide in-app notifications as a reliable baseline.

Create a PWA installation/help page explaining how to add Unjobless to the home screen on iOS and Android and install it on desktop browsers.

Acceptance:
- manifest is valid;
- service worker behaves correctly;
- app shell can load offline after a prior visit;
- sensitive data is not cached in shared/public cache;
- test mobile widths and standalone mode.

Commit: `feat(pwa): make Unjobless installable and responsive across devices`
```

# PROMPT BLOCK 33 — IMPORT HISTORY, REVIEW QUEUE AND MANUAL CORRECTIONS

```text
Build the Import Center review workflow.

Features:
- batch history;
- per-URL/content state;
- parsed preview;
- raw source view;
- extracted field evidence;
- confidence and missing-data indicators;
- edit/correct fields;
- confirm as vacancy;
- confirm as unverified lead;
- reject as irrelevant;
- merge with existing vacancy;
- retry failed processing;
- paste-content fallback;
- audit record of user corrections.

Acceptance:
- no uncertain lead is silently promoted to verified vacancy;
- user correction is preserved;
- batch-level and item-level errors are visible.

Commit: `feat(import): add extraction review and human verification workflow`
```

# PROMPT BLOCK 34 — CAREER INTELLIGENCE AND COMPANY INSIGHTS

```text
Build Career Intelligence pages using stored source observations.

Views:
- company overview;
- recent vacancy activity;
- recurring internship/recruitment patterns;
- public employer sentiment by topic;
- recruitment discussion trends;
- common requirements/skills observed;
- source count and data confidence;
- source references for each insight.

Rules:
- do not treat social sentiment as objective fact about a company;
- show sample size and time window;
- distinguish first-party company statements from third-party opinions;
- identify potentially biased/limited samples;
- avoid personal dossiers;
- do not infer sensitive personal traits;
- use careful language such as “public posts observed” or “sampled discussions suggest”.

Acceptance:
- every insight is traceable to underlying records;
- metrics are computed from data;
- low sample sizes are labelled.

Commit: `feat(intelligence): add evidence-linked company and recruitment insights`
```

# PROMPT BLOCK 35 — SETTINGS, BACKUP, RESTORE AND EXPORT

```text
Implement application settings and data portability.

Settings:
- career preferences;
- appearance/theme;
- default language;
- source schedules;
- AI provider configuration;
- collection limits;
- data retention;
- notification preferences;
- security/session controls.

Backup:
- PostgreSQL logical backup;
- persistent file/media volume backup;
- configuration backup excluding plaintext secrets;
- encrypted AI key settings handling;
- versioned backup manifest;
- checksum verification;
- backup retention policy.

Restore:
- documented restore into a clean Docker deployment;
- schema migration order;
- storage restore;
- encryption master-key requirement;
- post-restore integrity check.

Export:
- export career profile;
- export vacancy records;
- export comparison/application history;
- export source registry metadata.

Acceptance:
- backup can be restored in a clean test environment;
- no secrets appear in export;
- data export is usable and documented.

Commit: `feat(operations): add portable backup restore and personal data export`
```

# PROMPT BLOCK 36 — TESTING, EVALUATION DATASET AND QUALITY GATES

```text
Create a comprehensive test and evaluation suite for Unjobless.

Testing levels:
- unit tests;
- connector contract tests;
- parser fixture tests;
- API integration tests;
- database migration tests;
- queue/retry tests;
- UI component tests;
- end-to-end tests;
- security tests;
- Docker smoke tests;
- backup/restore test.

Create a privacy-safe evaluation dataset with synthetic or properly authorized/anonymized examples in Indonesian and English:
- formal job vacancy;
- internship poster;
- informal referral;
- possible future hiring rumour;
- job-search question;
- employer review;
- negative interview experience;
- unrelated content containing “internship”;
- expired opening;
- duplicated job across sources;
- incomplete salary/location/deadline data;
- OCR poster;
- pasted social post.

Evaluate:
- opportunity detection precision/recall;
- classification confusion matrix;
- field extraction accuracy;
- entity resolution accuracy;
- deduplication precision;
- stale/closed status correctness;
- CV fact preservation;
- match explanation evidence coverage;
- comparison score reproducibility.

Do not optimize only for recall. Broad collection must not turn into an unusable feed full of false positives.

Define release gates and report known limitations.

Acceptance:
- CI runs checks automatically;
- critical security and domain tests pass;
- evaluation report is documented.

Commit: `test(quality): add end-to-end and opportunity intelligence evaluation suite`
```

# PROMPT BLOCK 37 — PERFORMANCE AND RESOURCE LIMITS

```text
Profile the application and background workers. Optimize only measured bottlenecks.

Test:
- feed pagination at realistic record counts;
- full-text filtering;
- batch URL import;
- source concurrency;
- HTML parsing memory;
- OCR/media task resource limits;
- queue backlog behavior;
- AI timeout/retry behavior;
- database query plans;
- PWA asset size.

Add configurable limits for:
- max imported URLs per batch;
- max response bytes;
- max file size;
- max pages per crawl run;
- max crawl depth;
- max browser duration;
- max OCR/transcription duration;
- per-source concurrency;
- global worker concurrency;
- AI output tokens/cost per task.

Do not introduce complex caching or microservices without evidence.

Acceptance:
- bottlenecks and resource limits documented;
- no runaway worker process;
- failed work can be retried safely.

Commit: `perf(system): profile and optimize collection and discovery workloads`
```

# PROMPT BLOCK 38 — DOCKERFILES AND LOCAL DOCKER COMPOSE

```text
Containerize the complete Unjobless application for reproducible local development and VPS deployment.

Requirements:
- production-ready Dockerfile(s);
- multi-stage builds where beneficial;
- non-root runtime users;
- minimal runtime images;
- pinned/controlled dependency installation;
- health checks;
- graceful signal handling;
- no secrets baked into images;
- `.dockerignore`;
- Docker Compose services for web/API, worker/scheduler if separate, PostgreSQL, Redis/queue if required, and optional object storage/reverse proxy;
- named persistent volumes;
- explicit networks;
- resource considerations;
- startup dependency health checks;
- database migration command/job;
- development override file if needed.

The application must be runnable on a normal Docker-compatible VPS. Do not require Kubernetes.

Create:
- `Dockerfile` files;
- `compose.yaml` or `docker-compose.yml`;
- optional `compose.dev.yaml`;
- `.env.example`;
- health-check scripts;
- `docs/deployment/DOCKER.md`.

Acceptance:
- fresh clone can build and run using documented Docker Compose commands;
- persistent data survives container recreation;
- containers run as non-root where feasible;
- secrets are provided at runtime, not embedded.

Commit: `build(docker): containerize Unjobless for portable Compose deployment`
```

# PROMPT BLOCK 39 — VPS DEPLOYMENT, TLS AND DOMAIN

```text
Create a secure and reproducible VPS deployment guide and production Compose profile.

Assume a clean Linux VPS with Docker Engine and Docker Compose plugin. The user may have a domain/subdomain.

Requirements:
- DNS prerequisites;
- firewall ports;
- reverse proxy and automatic TLS using a maintained solution;
- HTTPS-only public access;
- secure cookie/proxy configuration;
- no public exposure of PostgreSQL, Redis, internal worker ports or admin/debug ports;
- production environment variables;
- persistent volume paths;
- startup order and migrations;
- health checks;
- restart policies;
- log rotation/limits;
- upload size limits;
- backup schedule;
- update/redeploy process;
- rollback plan;
- safe admin/bootstrap setup;
- PWA domain/HTTPS requirements.

Provide commands that can be copied safely. Explain placeholders. Never include real secrets.

Acceptance:
- a fresh VPS deployment is documented end-to-end;
- external access is only through the reverse proxy;
- internal services remain private;
- TLS and backup/restore are explained.

Commit: `docs(deploy): document secure Docker VPS production deployment`
```

# PROMPT BLOCK 40 — MIGRATION AND PORTABILITY TEST

```text
Prove Unjobless can be migrated to another VPS/server.

Test procedure:
1. deploy a clean instance using Docker Compose;
2. create owner and sample profile;
3. import sample URLs and pasted content;
4. run collection and AI processing with mocked or configured provider;
5. create comparison and tailored document;
6. take database and file backups;
7. restore into a separate clean environment;
8. run migrations and integrity checks;
9. verify imported records, source references, profile versions and files;
10. verify AI provider secrets are available only if the encryption master key is securely restored.

Document downtime assumptions, required secrets, DNS cutover and rollback.

Acceptance:
- restore test passes;
- all persistent data is accounted for;
- no hidden dependency on the original VPS filesystem or managed service.

Commit: `test(deploy): verify Unjobless backup restore and server migration`
```

# PROMPT BLOCK 41 — FINAL UX POLISH AND CROSS-DEVICE QA

```text
Perform a complete UI/UX quality pass against the supplied style reference and the Unjobless design tokens.

Test target sizes:
- small phone around 360px;
- modern iPhone viewport with safe areas;
- Android phone viewport;
- tablet portrait and landscape;
- laptop around 1366px wide;
- desktop around 1440px and larger.

Review:
- typography scale;
- contrast;
- spacing;
- card hierarchy;
- responsive navigation;
- comparison readability;
- long job descriptions;
- large filter sets;
- empty/loading/error states;
- keyboard focus;
- dialogs/menus;
- PWA standalone mode;
- touch target sizing;
- safe-area padding;
- reduced motion;
- install instructions.

Fix visual inconsistencies. Do not add unnecessary decoration. Use purple gradients sparingly. Ensure information density is appropriate for a career research tool while retaining the reference's clean elegant aesthetic.

Acceptance:
- no critical responsive overflow;
- no dead action buttons;
- key workflows are usable on phone and desktop;
- accessibility issues are documented and critical ones fixed.

Commit: `fix(ui): polish responsive Unjobless experience across devices`
```

# PROMPT BLOCK 42 — SECURITY REVIEW AND RELEASE CANDIDATE

```text
Conduct a final security and release-candidate review.

Review:
- authentication and session controls;
- SSRF and URL import defenses;
- file upload validation;
- HTML parsing/browser isolation;
- XSS prevention for scraped content;
- SQL injection protection;
- CSRF/CORS/security headers;
- secret encryption and logging redaction;
- private data access;
- dependency vulnerabilities;
- container users and network exposure;
- database backup exposure;
- prompt injection from scraped content;
- unsafe LLM tool/action execution;
- data retention/deletion;
- source permissions and collection policy.

Treat all scraped/pasted content as untrusted data, not instructions. A job post must never be allowed to instruct the AI system to reveal secrets, alter settings, call tools, or execute code. Do not give LLMs unrestricted browser, filesystem, shell or database access.

Create:
- `docs/security/SECURITY_REVIEW.md`;
- `docs/security/THREAT_MODEL.md`;
- `docs/release/KNOWN_LIMITATIONS.md`;
- a release checklist.

Run all tests, lint, typecheck, build and Docker smoke tests. Report unresolved high/critical findings honestly. Do not declare production-ready with unresolved critical security issues.

Commit: `chore(release): complete security review and prepare Unjobless release candidate`
```

# PROMPT BLOCK 43 — FINAL README AND OPERATOR HANDBOOK

```text
Write the final developer README and operator handbook based on the actual implementation.

README must explain:
- what Unjobless does;
- major capabilities;
- architecture overview;
- prerequisites;
- local development;
- environment configuration;
- database migration;
- running tests;
- adding a source connector;
- adding an AI provider;
- importing URLs and pasted content;
- PWA installation;
- Docker Compose deployment;
- VPS deployment link;
- backup and restore;
- troubleshooting;
- security and source collection policy.

Operator handbook must explain:
- how to check source health;
- how to pause a source;
- how to rotate an AI API key;
- how to review unverified opportunity leads;
- how to correct bad extraction;
- how to verify vacancy status;
- how to restore backup;
- how to migrate VPS.

Ensure instructions match actual command names and paths. Remove obsolete instructions.

Acceptance:
- new developer can run the project from a clean clone;
- owner can deploy and operate without manually guessing steps.

Commit: `docs(readme): publish Unjobless developer and operator handbook`
```

---

# PART VIII — RELEASE ACCEPTANCE CHECKLIST

## 25. Product acceptance

- [ ] Private owner setup works; no public sign-up.
- [ ] Latest CV can be uploaded and reviewed.
- [ ] Master profile is editable and versioned.
- [ ] Career preferences can be saved.
- [ ] Source registry supports independent connectors.
- [ ] Source policy and health are visible.
- [ ] Scheduled collection works with retries and checkpoints.
- [ ] At least the initial documented job API/ATS connectors work.
- [ ] Permitted career-page collection works against fixtures and approved sources.
- [ ] Batch URL importer works.
- [ ] Paste-content importer works.
- [ ] Failed/blocked URLs have a manual paste fallback.
- [ ] Raw source content and provenance are preserved.
- [ ] Rich vacancy extraction includes field evidence and confidence.
- [ ] Direct vacancies and informal signals are separate.
- [ ] Sentiment and topic analysis are separate from vacancy classification.
- [ ] OCR/media extraction works for supported permitted inputs.
- [ ] Duplicate vacancies preserve multiple source references.
- [ ] Vacancy freshness and status uncertainty are visible.
- [ ] Opportunity feed filtering and sorting work.
- [ ] Candidate fit, preference fit and data confidence remain separate.
- [ ] Comparison enforces a maximum of two vacancies.
- [ ] Comparison explains wins, unknowns and trade-offs.
- [ ] CV tailoring preserves factual integrity.
- [ ] Master CV is never overwritten.
- [ ] PDF/DOCX export works.
- [ ] Direct apply links open original destinations.
- [ ] Application tracker works.
- [ ] AI API keys can be safely added/updated/deleted.
- [ ] AI usage/cost telemetry works to the extent supported by providers.
- [ ] PWA installs on supported browsers.
- [ ] Responsive UI works on mobile/tablet/desktop.
- [ ] Docker Compose starts the full system.
- [ ] Backup/restore and migration are tested.

## 26. Technical acceptance

- [ ] All DB changes use migrations.
- [ ] No secret is committed or exposed to browser code.
- [ ] SSRF protections have tests.
- [ ] Scraped content is treated as untrusted input.
- [ ] No source access restriction is bypassed.
- [ ] Workers use bounded concurrency and resource limits.
- [ ] Retries are idempotent.
- [ ] Source errors are observable.
- [ ] Logs do not expose CV contents or API keys unnecessarily.
- [ ] Docker services use persistent volumes for required state.
- [ ] Internal DB/queue ports are not public in production.
- [ ] Fresh deployment and restore are reproducible.

## 27. Suggested MVP launch scope

A realistic initial launch should not wait for every social platform connector. The first useful release should include:

1. Master CV and preferences.
2. Source registry and scheduler.
3. A small but reliable set of documented job APIs/ATS connectors.
4. Permitted company career-page crawler.
5. Batch URL import and paste-content import.
6. Rich extraction and review workflow.
7. Opportunity signal detection for Indonesian and English content.
8. Searchable opportunity feed.
9. Basic evidence-based matching.
10. Two-vacancy comparison.
11. CV tailoring and PDF/DOCX export.
12. Docker deployment and backup/restore.

Then expand source coverage connector by connector. Track quality and coverage transparently.

---

# PART IX — IMPORTANT EXECUTION NOTES FOR CLAUDE CODE

## 28. Do not implement all blocks in one run

This playbook is intentionally split into small blocks. A broad project can fail when the coding agent changes many systems at once without verification.

For each block, Claude should:

1. inspect existing code and relevant docs;
2. state the exact scope;
3. identify dependencies;
4. implement the smallest complete increment;
5. add tests;
6. run formatting, linting, type checks and relevant test suites;
7. inspect the final diff;
8. update docs;
9. commit with the specified semantic message;
10. report files, checks, commit hash and known limitations.

## 29. Semantic commit examples

Use Conventional Commit messages with meaningful scopes:

```text
feat(profile): add editable master career profile
feat(import): add batch URL importer
feat(signals): classify informal internship announcements
feat(connectors): add documented ATS connector
feat(compare): enforce two-vacancy comparison limit
feat(pwa): add installable web app support
fix(crawler): prevent redirect to private network address
fix(matching): treat missing requirements as unknown
refactor(ai): isolate provider adapters from domain services
test(signals): add Indonesian opportunity detection fixtures
docs(deploy): add Docker VPS deployment guide
build(docker): add production Compose profile
chore(release): prepare first personal beta
```

Never use a commit message like `update`, `fix stuff`, `changes`, or `final`.

## 30. What “done” means

A feature is not done because a page exists or the happy path works once. It is done when:

- persisted data is correct;
- validation and authorization are enforced server-side;
- failure and empty states are handled;
- tests cover important behavior;
- provenance is preserved where relevant;
- UI is responsive and accessible;
- docs are updated;
- Docker runtime is compatible;
- logs and errors are useful;
- no known critical security issue remains.

---

# END OF UNJOBLESS BUILD PLAYBOOK

**Recommended starting sequence:** Master Prompt → Prompt Blocks 00 through 10. Review the architecture and security foundation before implementing real connectors. Then continue sequentially. Do not start with an enormous scraper; start with the connector contract, source policy, raw evidence model and secure importer so the collection engine remains extensible and safe.
