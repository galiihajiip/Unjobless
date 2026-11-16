# Known limitations (v0.1.0)

## Coverage & collection
- Coverage is limited to **sources you enable** and **content you import**. There is no social-media API connector in v1; social posts come in via paste/upload.
- Included connectors: Greenhouse, Lever and Ashby public job boards, and a generic career-page crawler (robots.txt-compliant, same-domain only). Many Indonesian job boards (e.g. JobStreet, Glints, Kalibrr) have no documented public API for this use. Import their pages by URL (where fetchable) or paste the content.
- Pages that need login, JavaScript rendering or show a CAPTCHA are reported as unavailable. **No headless browser** is bundled. Example: Glints answers automated requests (pages and sitemaps) with 403 + a Cloudflare CAPTCHA, so it cannot be collected automatically. Use the browser clipper (Import Center › Paste content) or paste.
- Collection is scheduled (minimum interval 5 minutes), never real-time.

## Intelligence quality
- The rule-based signal engine is precision-first. On the untouched synthetic test set: accuracy 0.67, opportunity precision 1.0, recall 0.9 (n=18, small). See [SIGNALS_EVAL.md](../evaluation/SIGNALS_EVAL.md).
- Rule-based extraction covers common Indonesian/English patterns (salary in Rp/juta, Indonesian dates, cities, a skills taxonomy of ~100 skills). Unusual formats need review or the optional AI provider.
- The AI-assisted paths (classification of ambiguous posts, extraction, CV structuring, tailoring, letters) are implemented and unit-tested with mocked providers, but **were not evaluated against a live model** in this build: no API key was available.
- Sentiment analysis is lexicon-based without the AI provider; sarcasm is flagged only heuristically.
- Location normalisation knows major Indonesian cities. Other countries are matched only by name.
- Deduplication is conservative: the same role listed separately in one ATS stays separate. Cross-source duplicates with different URLs may need the manual merge queue.

## Profile & documents
- CV structuring without AI uses section heuristics. Unusual CV layouts need manual editing (the draft editor supports this).
- Scanned-PDF CVs need OCR (available in the Docker image, not on a bare host).
- Audio/video speech transcription is not bundled. Captions (.vtt/.srt) or pasted transcripts are supported.
- PDF export uses DejaVu Sans in Docker. Rare scripts outside its coverage may not render.

## Product & platform
- Single owner; no multi-user, roles or sharing.
- Password authentication only (no passkeys/2FA yet).
- Notifications are in-app only (deadline/follow-up banners). No push notifications.
- Light theme only.
- The interface is in English; generated documents can be Indonesian or English.
- Match scores are transparent heuristics, **not** predictions of hiring success or ATS acceptance.
- Unjobless never submits applications.
