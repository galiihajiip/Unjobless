"""Modular media processing for owner-supplied or otherwise permitted content.

- Images/posters: validated with Pillow (decompression-bomb guard, size limits), metadata kept,
  OCR via the `tesseract` binary in a subprocess with CPU-time/memory/timeout limits.
- PDFs: text extraction with pypdf; scanned-PDF OCR fallback via `pdftoppm` + tesseract.
- Captions/subtitles (.vtt/.srt) and owner-provided transcripts are accepted as text.
- Audio/video speech recognition is NOT bundled (no local model by default); such files are marked
  `SKIPPED` with a manual-transcript fallback. Media is never downloaded from platforms that restrict it.

Every derived text records its kind and origin (ORIGINAL / USER_PROVIDED / MACHINE_GENERATED).
Failures never lose the original import.
"""

from __future__ import annotations

import contextlib
import io
import re
import resource
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from unjobless.core.config import get_settings
from unjobless.core.errors import ValidationFailed
from unjobless.core.logging import get_logger
from unjobless.db.models import ContentTranscription, RawSourceVersion, SourceMediaAsset
from unjobless.db.session import session_scope
from unjobless.domain.enums import ProcessingStatus, TextOrigin, TranscriptionKind
from unjobless.ingestion.filestore import get_filestore
from unjobless.intelligence.text import clean_text, guess_language

log = get_logger(__name__)

IMAGE_MIMES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}
DOC_MIMES = {"application/pdf": ".pdf"}
TEXT_MIMES = {"text/vtt": ".vtt", "application/x-subrip": ".srt", "text/plain": ".txt"}
AV_MIMES = {"audio/mpeg", "audio/mp4", "audio/wav", "audio/x-wav", "video/mp4", "video/webm", "audio/ogg"}
MAX_PIXELS = 40_000_000
OCR_TIMEOUT = 90
OCR_CPU_SECONDS = 60
OCR_MEMORY_BYTES = 1024 * 1024 * 1024
MAX_PDF_PAGES = 30
OCR_PDF_PAGES = 10

MAGIC = [
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"RIFF", "image/webp"),
    (b"GIF8", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"WEBVTT", "text/vtt"),
]


def sniff_mime(data: bytes, declared: str | None, filename: str | None) -> str:
    """Trust content, not the declared type. Returns the detected MIME or raises."""
    for magic, mime in MAGIC:
        if data.startswith(magic):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    name = (filename or "").lower()
    if name.endswith(".srt") and re.match(rb"\s*\d+\s*\r?\n\d\d:\d\d:\d\d", data[:200]):
        return "application/x-subrip"
    if (declared or "").startswith("text/") or name.endswith(".txt"):
        try:
            data[:4096].decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            pass
    if declared in AV_MIMES:
        return declared  # stored as reference only; never executed or decoded server-side
    raise ValidationFailed("Unsupported or unrecognised file type.", code="unsupported_file")


def validate_upload(data: bytes, declared: str | None, filename: str | None) -> str:
    if len(data) > get_settings().max_upload_bytes:
        raise ValidationFailed("File is too large.", code="file_too_large")
    if not data:
        raise ValidationFailed("File is empty.", code="file_empty")
    mime = sniff_mime(data, declared, filename)
    if mime in IMAGE_MIMES:
        from PIL import Image

        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
        except Exception as exc:
            raise ValidationFailed("The image could not be read safely.", code="bad_image") from exc
    return mime


def _limits() -> None:  # runs in the child process before exec
    resource.setrlimit(resource.RLIMIT_CPU, (OCR_CPU_SECONDS, OCR_CPU_SECONDS))
    with contextlib.suppress(ValueError, OSError):  # RLIMIT_AS unsupported on some platforms (e.g. macOS)
        resource.setrlimit(resource.RLIMIT_AS, (OCR_MEMORY_BYTES, OCR_MEMORY_BYTES))


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def run_tesseract(image_path: Path, langs: str = "ind+eng") -> tuple[str, float | None]:
    exe = shutil.which("tesseract")
    if not exe:
        raise RuntimeError("OCR engine (tesseract) is not installed in this environment.")
    proc = subprocess.run(  # noqa: S603 - fixed binary, no shell, file path we created
        [exe, str(image_path), "stdout", "-l", langs, "--psm", "3"],
        capture_output=True,
        timeout=OCR_TIMEOUT,
        preexec_fn=_limits,
        check=False,
    )
    if proc.returncode != 0:
        # retry with English only if Indonesian traineddata is missing
        if b"ind" in proc.stderr and langs != "eng":
            return run_tesseract(image_path, "eng")
        raise RuntimeError(f"OCR failed: {proc.stderr.decode(errors='replace')[:200]}")
    return clean_text(proc.stdout.decode("utf-8", errors="replace")), None


def pdf_text(data: bytes) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    warnings: list[str] = []
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValidationFailed("Encrypted PDFs are not supported.", code="pdf_encrypted")
    pages = reader.pages[:MAX_PDF_PAGES]
    if len(reader.pages) > MAX_PDF_PAGES:
        warnings.append(f"Only the first {MAX_PDF_PAGES} pages were read.")
    parts = []
    for i, p in enumerate(pages, start=1):
        t = p.extract_text() or ""
        if t.strip():
            parts.append(f"[page {i}]\n{t}")
    return clean_text("\n\n".join(parts)), warnings


def ocr_pdf(data: bytes) -> str:
    exe = shutil.which("pdftoppm")
    if not exe or not ocr_available():
        raise RuntimeError("Scanned-PDF OCR needs pdftoppm and tesseract, which are not installed here.")
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "in.pdf"
        pdf.write_bytes(data)
        subprocess.run(  # noqa: S603
            [exe, "-r", "200", "-l", str(OCR_PDF_PAGES), "-png", str(pdf), str(Path(tmp) / "p")],
            capture_output=True,
            timeout=OCR_TIMEOUT,
            preexec_fn=_limits,
            check=True,
        )
        texts = []
        for img in sorted(Path(tmp).glob("p*.png")):
            t, _ = run_tesseract(img)
            texts.append(t)
        return clean_text("\n\n".join(texts))


def parse_captions(text: str) -> str:
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s == "WEBVTT" or s.isdigit() or "-->" in s or s.startswith(("NOTE", "STYLE")):
            continue
        lines.append(re.sub(r"<[^>]+>", "", s))
    return clean_text("\n".join(dict.fromkeys(lines)))


@dataclass
class MediaResult:
    status: ProcessingStatus
    text: str | None
    kind: TranscriptionKind | None
    message: str | None


def extract_media_text(data: bytes, mime: str) -> MediaResult:
    if mime in IMAGE_MIMES:
        if not ocr_available():
            return MediaResult(
                ProcessingStatus.SKIPPED,
                None,
                None,
                "OCR is not available on this server; paste the poster text manually.",
            )
        suffix = IMAGE_MIMES[mime]
        with tempfile.NamedTemporaryFile(suffix=suffix) as f:
            f.write(data)
            f.flush()
            text, _ = run_tesseract(Path(f.name))
        return MediaResult(ProcessingStatus.SUCCEEDED, text, TranscriptionKind.OCR, None)
    if mime == "application/pdf":
        text, warnings = pdf_text(data)
        if len(text) >= 40:
            return MediaResult(
                ProcessingStatus.SUCCEEDED, text, TranscriptionKind.PDF_TEXT, "; ".join(warnings) or None
            )
        try:
            return MediaResult(
                ProcessingStatus.SUCCEEDED,
                ocr_pdf(data),
                TranscriptionKind.OCR,
                "Scanned PDF: text produced by OCR.",
            )
        except Exception as exc:
            return MediaResult(
                ProcessingStatus.SKIPPED, None, None, f"No text layer and OCR unavailable: {exc}"
            )
    if mime in ("text/vtt", "application/x-subrip"):
        return MediaResult(
            ProcessingStatus.SUCCEEDED,
            parse_captions(data.decode("utf-8", errors="replace")),
            TranscriptionKind.CAPTION,
            None,
        )
    if mime == "text/plain":
        return MediaResult(
            ProcessingStatus.SUCCEEDED,
            clean_text(data.decode("utf-8", errors="replace")),
            TranscriptionKind.USER_PROVIDED,
            None,
        )
    if mime in AV_MIMES:
        return MediaResult(
            ProcessingStatus.SKIPPED,
            None,
            None,
            "Speech transcription is not configured. Paste a transcript or upload captions instead.",
        )
    return MediaResult(ProcessingStatus.FAILED, None, None, "Unsupported media type.")


def attach_media(
    db: Session, version: RawSourceVersion, data: bytes, mime: str, *, url: str | None = None
) -> SourceMediaAsset:
    ref, sha = get_filestore().put(
        data,
        namespace="media",
        suffix=IMAGE_MIMES.get(mime) or DOC_MIMES.get(mime) or TEXT_MIMES.get(mime, ""),
    )
    asset = SourceMediaAsset(
        version_id=version.id,
        kind="image"
        if mime.startswith("image/")
        else "pdf"
        if mime == "application/pdf"
        else "audio_video"
        if mime in AV_MIMES
        else "text",
        url=url,
        blob_ref=ref,
        mime=mime,
        sha256=sha,
        byte_size=len(data),
        permitted_download=True,
        processing_status=ProcessingStatus.QUEUED,
    )
    db.add(asset)
    db.flush()
    return asset


def process_media_asset(media_id: int) -> None:
    with session_scope() as db:
        asset = db.get(SourceMediaAsset, media_id)
        if asset is None or asset.processing_status == ProcessingStatus.SUCCEEDED:
            return
        version = db.get(RawSourceVersion, asset.version_id)
        try:
            data = get_filestore().get(asset.blob_ref or "")
            res = extract_media_text(data, asset.mime or "")
        except Exception as exc:
            log.warning("media_failed", media=media_id, error_type=type(exc).__name__)
            asset.processing_status, asset.processing_error = ProcessingStatus.FAILED, str(exc)[:500]
            return
        asset.processing_status = res.status
        asset.processing_error = res.message
        if res.text and res.kind and version is not None:
            db.add(
                ContentTranscription(
                    version_id=version.id,
                    media_id=asset.id,
                    kind=res.kind,
                    origin=TextOrigin.ORIGINAL
                    if res.kind in (TranscriptionKind.PDF_TEXT, TranscriptionKind.CAPTION)
                    else TextOrigin.MACHINE_GENERATED,
                    text=res.text[:200_000],
                    engine="tesseract" if res.kind == TranscriptionKind.OCR else res.kind.value.lower(),
                    language=guess_language(res.text),
                )
            )
            version.processing_status = ProcessingStatus.QUEUED  # re-analyse with the new text
    from unjobless.jobs.queue import defer

    if version is not None:
        defer("process_version", queueing_lock=f"version-{version.id}", version_id=version.id)
