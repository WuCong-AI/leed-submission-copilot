from __future__ import annotations

import io
import os
import mimetypes
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any


MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_FILES = 500
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024
# Render's Starter instance has a 512 MB memory ceiling. Do not materialize
# very large drawing members or PDFs in Python just to extract a small preview.
MAX_IN_MEMORY_MEMBER_BYTES = 8 * 1024 * 1024
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml", ".ifc", ".dxf", ".html", ".log"}
DRAWING_EXTENSIONS = {".pdf", ".dwg", ".dxf", ".rvt", ".rfa", ".ifc", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def _drawing_hints(name: str, text: str) -> dict[str, Any]:
    haystack = f"{name} {text}".lower()
    disciplines: list[str] = []
    keywords = {
        "architectural": ("architectural", "floor plan", "elevation", "section", "a-", "arch"),
        "mep": ("hvac", "mechanical", "plumbing", "mep", "m-", "duct", "chiller"),
        "electrical": ("electrical", "lighting", "power", "e-", "photovoltaic", "solar"),
        "structural": ("structural", "foundation", "column", "beam", "s-"),
        "landscape": ("landscape", "planting", "irrigation", "native", "habitat", "l-"),
        "civil": ("civil", "stormwater", "grading", "site plan", "c-"),
    }
    for discipline, terms in keywords.items():
        if any(term in haystack for term in terms):
            disciplines.append(discipline)
    sheets = sorted(set(re.findall(r"\b(?:[A-Z]{1,3}-?\d{1,3}(?:\.\d+)?)\b", name.upper() + " " + text.upper())))[:30]
    return {"is_drawing_candidate": name.lower().endswith(tuple(DRAWING_EXTENSIONS)), "disciplines": disciplines, "sheet_labels": sheets, "keyword_hits": [k for k in ("HVAC", "fresh air", "energy model", "EPD", "daylight", "biodiversity", "embodied carbon", "resilience", "EV charging") if k.lower() in haystack]}


def _extract_pdf(data: bytes) -> tuple[str, int, list[str]]:
    warnings: list[str] = []
    if len(data) > MAX_IN_MEMORY_MEMBER_BYTES:
        return "", 0, ["Large PDF indexed in metadata mode; text preview is deferred to keep online processing stable."]
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                warnings.append("PDF is encrypted; upload an unlocked copy for text extraction.")
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return text, len(reader.pages), warnings
    except Exception as exc:
        warnings.append(f"PDF text extraction unavailable ({type(exc).__name__}); page/image metadata retained.")
        return "", 0, warnings


def extract_file(name: str, data: bytes, content_type: str | None = None, archive_member: str | None = None, *, declared_size: int | None = None, skip_content: bool = False) -> dict[str, Any]:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"{name} exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB file limit")
    clean_name = PurePosixPath(name.replace("\\", "/")).name or "upload.bin"
    ext = PurePosixPath(clean_name).suffix.lower()
    text, page_count, warnings = "", 0, []
    if skip_content:
        warnings.append("Large drawing indexed in metadata mode; text preview is deferred to keep online processing stable.")
    elif ext in TEXT_EXTENSIONS:
        text = data[:2_000_000].decode("utf-8", errors="replace")
    elif ext == ".pdf":
        text, page_count, warnings = _extract_pdf(data)
    elif ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
        warnings.append("Image received; OCR/vision provider is not configured, so recognition uses filename metadata.")
    elif ext in {".dwg", ".rvt", ".rfa"}:
        warnings.append(f"{ext.upper()} geometry is retained as metadata; connect a CAD/BIM parser for geometry-level quantities.")
    hints = _drawing_hints(clean_name, text)
    return {"filename": clean_name, "archive_member": archive_member, "mime_type": content_type or mimetypes.guess_type(clean_name)[0] or "application/octet-stream", "extension": ext, "size_bytes": declared_size if declared_size is not None else len(data), "text": text[:100_000], "page_count": page_count, "warnings": warnings, "drawing": hints}


def extract_upload(name: str, data: bytes, content_type: str | None = None) -> list[dict[str, Any]]:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"{name} exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB file limit")
    if not name.lower().endswith(".zip"):
        return [extract_file(name, data, content_type)]
    results: list[dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        if len(members) > MAX_ARCHIVE_FILES:
            raise ValueError(f"ZIP contains more than {MAX_ARCHIVE_FILES} files")
        total = 0
        for member in members:
            path = PurePosixPath(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unsafe ZIP path rejected: {member.filename}")
            if member.file_size > MAX_FILE_BYTES or total + member.file_size > MAX_ARCHIVE_BYTES:
                raise ValueError("ZIP uncompressed size exceeds the safe processing limit")
            total += member.file_size
            if member.file_size > MAX_IN_MEMORY_MEMBER_BYTES or path.suffix.lower() == ".pdf":
                results.append(extract_file(str(path), b"", None, archive_member=str(path), declared_size=member.file_size, skip_content=True))
            else:
                payload = archive.read(member)
                results.append(extract_file(str(path), payload, None, archive_member=str(path)))
    return results


def extract_upload_path(name: str, path: str, content_type: str | None = None) -> list[dict[str, Any]]:
    """Extract a ZIP incrementally from disk so large archives do not duplicate in RAM."""
    if not name.lower().endswith(".zip"):
        with open(path, "rb") as handle:
            return [extract_file(name, handle.read(), content_type)]
    results: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        if len(members) > MAX_ARCHIVE_FILES:
            raise ValueError(f"ZIP contains more than {MAX_ARCHIVE_FILES} files")
        total = 0
        for member in members:
            member_path = PurePosixPath(member.filename.replace("\\", "/"))
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Unsafe ZIP path rejected: {member.filename}")
            if member.file_size > MAX_FILE_BYTES or total + member.file_size > MAX_ARCHIVE_BYTES:
                raise ValueError("ZIP uncompressed size exceeds the safe processing limit")
            total += member.file_size
            if member.file_size > MAX_IN_MEMORY_MEMBER_BYTES or member_path.suffix.lower() == ".pdf":
                results.append(extract_file(str(member_path), b"", None, archive_member=str(member_path), declared_size=member.file_size, skip_content=True))
            else:
                with archive.open(member, "r") as handle:
                    results.append(extract_file(str(member_path), handle.read(), None, archive_member=str(member_path)))
    return results
