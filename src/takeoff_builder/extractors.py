from __future__ import annotations

import json
import os
import re
import zlib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import ZipFile
import xml.etree.ElementTree as ET


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_docx_text(path: Path) -> str:
    with ZipFile(path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    for paragraph in root.iter(f"{ns}p"):
        texts = [node.text or "" for node in paragraph.iter(f"{ns}t")]
        joined = "".join(texts).strip()
        if joined:
            paragraphs.append(joined)
    return "\n".join(paragraphs)


def list_zip_members(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        return sorted(info.filename for info in archive.infolist() if not info.is_dir())


def _decode_pdf_string(raw: str) -> str:
    raw = raw.replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t")
    raw = raw.replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
    return raw


def _extract_pdf_strings(block: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"\((.*?)(?<!\\)\)", block, flags=re.S):
        text = _decode_pdf_string(match.group(1))
        if text.strip():
            values.append(text)
    return values


def extract_pdf_text(path: Path, max_chars: int = 25000) -> str:
    data = path.read_bytes()
    text_chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, flags=re.S):
        stream = match.group(1)
        for candidate in (stream,):
            try:
                decoded = zlib.decompress(candidate)
            except zlib.error:
                continue
            try:
                content = decoded.decode("latin-1", errors="ignore")
            except Exception:
                continue
            for text_block in re.findall(r"BT(.*?)ET", content, flags=re.S):
                strings = _extract_pdf_strings(text_block)
                if strings:
                    text_chunks.append(" ".join(strings))
        if sum(len(chunk) for chunk in text_chunks) >= max_chars:
            break
    deduped = "\n".join(chunk.strip() for chunk in text_chunks if chunk.strip())
    deduped = re.sub(r"[ \t]+", " ", deduped)
    deduped = re.sub(r"\n{3,}", "\n\n", deduped)
    return deduped[:max_chars].strip()


def gemini_document_extraction_enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def extract_pdf_text_with_gemini(path: Path, max_chars: int = 25000) -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return ""
    if path.stat().st_size > 50 * 1024 * 1024:
        return ""

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    uploaded = _gemini_upload_file(path, "application/pdf", api_key)
    if not uploaded:
        return ""

    file_uri = uploaded["uri"]
    file_name = uploaded["name"]
    prompt = (
        "Extract the visible document text from this construction PDF as clean plain text. "
        "Preserve section headings, schedules, quantities, units, and page-local labels when possible. "
        "Do not summarize. Return only the extracted text."
    )
    try:
        text = _gemini_generate_from_file(
            api_key=api_key,
            model=model,
            file_uri=file_uri,
            mime_type="application/pdf",
            prompt=prompt,
        )
    finally:
        _gemini_delete_file(api_key, file_name)

    return text[:max_chars].strip()


def estimate_pdf_page_count(path: Path) -> int | None:
    data = path.read_bytes()
    matches = re.findall(rb"/Type\s*/Page\b", data)
    if not matches:
        return None
    return len(matches)


def _gemini_upload_file(path: Path, mime_type: str, api_key: str) -> dict[str, str] | None:
    base_url = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={quote(api_key)}"
    metadata_body = json.dumps({"file": {"display_name": path.name}}).encode("utf-8")
    start_request = Request(
        base_url,
        data=metadata_body,
        method="POST",
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(path.stat().st_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(start_request, timeout=30) as response:
            upload_url = response.headers.get("X-Goog-Upload-URL")
    except (HTTPError, URLError):
        return None
    if not upload_url:
        return None

    upload_request = Request(
        upload_url,
        data=path.read_bytes(),
        method="POST",
        headers={
            "Content-Length": str(path.stat().st_size),
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
    )
    try:
        with urlopen(upload_request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError):
        return None

    file_info = payload.get("file") or {}
    if not file_info.get("uri") or not file_info.get("name"):
        return None
    return {"uri": file_info["uri"], "name": file_info["name"]}


def _gemini_generate_from_file(api_key: str, model: str, file_uri: str, mime_type: str, prompt: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:" \
        f"generateContent?key={quote(api_key)}"
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"file_data": {"mime_type": mime_type, "file_uri": file_uri}},
                ]
            }
        ]
    }
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, json.JSONDecodeError):
        return ""

    texts: list[str] = []
    for candidate in payload.get("candidates", []):
        content = candidate.get("content") or {}
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def _gemini_delete_file(api_key: str, file_name: str) -> None:
    if not file_name:
        return
    url = f"https://generativelanguage.googleapis.com/v1beta/{quote(file_name, safe='/')}?key={quote(api_key)}"
    request = Request(url, method="DELETE")
    try:
        with urlopen(request, timeout=30):
            return
    except (HTTPError, URLError):
        return
