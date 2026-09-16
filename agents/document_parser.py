"""
Document Parser for HireTrace.

Extracts plain text from multi-format applicant documents:
- PDF (.pdf) via pdfplumber with pypdf and optional OCR fallback
- Word (.docx) via python-docx with zero-dependency XML zip fallback
- Plain text (.txt, .md) with multi-encoding detection (UTF-8, Latin-1, CP1252)
- Rejects legacy .doc with informative guidance

All extractions feed directly into EvidenceLoader without pipeline alteration.
"""

import os
import io
import re
import json
import hashlib
import zipfile
import concurrent.futures
from pathlib import Path
from typing import Union, Optional

from agents.zip_safety import assert_zip_entry_is_safe

try:
    import defusedxml.ElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET  # nosec B405 - unreachable when defusedxml is installed


def compute_file_hash(data: bytes) -> str:
    """Computes SHA-256 digest of file bytes for deduplication."""
    return hashlib.sha256(data).hexdigest()


def infer_document_type(filename: str) -> str:
    """
    Infers document type from filename patterns for bulk ingestion.
    Returns: 'cv', 'interview', 'assessment', or 'project'.
    """
    base = os.path.basename(filename).lower()
    name, _ = os.path.splitext(base)
    # Replace separators with spaces so \b matches words separated by underscores or dashes
    normalized = re.sub(r"[_\-\s\.]+", " ", name).strip()

    if re.search(r"\b(cv|resume|curriculum|vitae)\b", normalized):
        return "cv"
    if re.search(r"\b(interview|transcript|debrief|screen|call|notes)\b", normalized):
        return "interview"
    if re.search(r"\b(assessment|test|task|takehome|challenge|coding|grader|eval)\b", normalized):
        return "assessment"
    if re.search(r"\b(rfc|project|portfolio|architecture|design|repo|spec)\b", normalized):
        return "project"

    return "cv"



def _extract_pdf(file_path: Union[str, Path]) -> str:
    """
    Extracts text from PDF using pdfplumber, falling back to pypdf and OCR.
    Enforces page-count limit (HIRETRACE_MAX_PDF_PAGES) and wall-clock timeout
    (HIRETRACE_PDF_PARSE_TIMEOUT_SECONDS).
    """
    max_pages = int(os.environ.get("HIRETRACE_MAX_PDF_PAGES", "200"))
    timeout_seconds = float(os.environ.get("HIRETRACE_PDF_PARSE_TIMEOUT_SECONDS", "15.0"))

    # 1. Inspect page count before parsing
    page_count = None
    try:
        import pypdf
        reader = pypdf.PdfReader(str(file_path))
        page_count = len(reader.pages)
    except Exception:
        pass

    if page_count is None:
        try:
            import fitz
            doc = fitz.open(str(file_path))
            page_count = len(doc)
            doc.close()
        except Exception:
            pass

    if page_count is None:
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)
        except Exception:
            pass

    if page_count is not None and page_count > max_pages:
        raise ValueError(
            f"PDF exceeds maximum page limit ({page_count} > {max_pages} pages). "
            f"Please trim the document or split into smaller sections."
        )

    # 2. Worker for parsing attempts
    def _do_extract() -> str:
        text = ""
        # Try pdfplumber (layout-aware, handles columns and tables)
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                pages_text = []
                for page in pdf.pages:
                    page_str = page.extract_text()
                    if page_str:
                        pages_text.append(page_str)
                text = "\n\n".join(pages_text).strip()
        except Exception:
            text = ""

        # Fallback to pypdf if pdfplumber produced empty or failed
        if not text:
            try:
                import pypdf
                reader = pypdf.PdfReader(str(file_path))
                pages_text = []
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        pages_text.append(extracted)
                text = "\n\n".join(pages_text).strip()
            except Exception:
                pass

        # Fallback to PyMuPDF (fitz) if available and still empty
        if not text:
            try:
                import fitz
                doc = fitz.open(str(file_path))
                pages_text = [page.get_text() for page in doc if page.get_text().strip()]
                text = "\n\n".join(pages_text).strip()
                doc.close()
            except Exception:
                pass

        # Optional OCR fallback for scanned/image PDFs if text is near-empty (< 50 chars)
        if len(text) < 50:
            try:
                import pytesseract
                from pdf2image import convert_from_path
                images = convert_from_path(str(file_path), first_page=1, last_page=5)
                ocr_text = []
                for img in images:
                    ocr_str = pytesseract.image_to_string(img)
                    if ocr_str.strip():
                        ocr_text.append(ocr_str.strip())
                if ocr_text:
                    text = "\n\n".join(ocr_text)
            except Exception:
                pass

        return text.strip()

    # 3. Enforce wall-clock timeout
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_do_extract)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            raise ValueError(
                f"PDF parsing timed out after {timeout_seconds}s. "
                f"Please retry via the async (sync=false) path."
            )


def _extract_docx(file_path: Union[str, Path]) -> str:
    """
    Extracts text from DOCX using python-docx with fallback to XML parsing.
    Enforces zip-bomb protections prior to decompressing XML.
    """
    # Pre-inspect zip entries for zip-bomb protection before python-docx or fallback
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            infolist = z.infolist()
            if len(infolist) > 500:
                raise ValueError(f"DOCX contains excessive entries ({len(infolist)} > 500)")
            total_uncomp = 0
            for zinfo in infolist:
                assert_zip_entry_is_safe(zinfo)
                total_uncomp += zinfo.file_size
                if total_uncomp > 200 * 1024 * 1024:
                    raise ValueError("DOCX total uncompressed size exceeds 200 MB limit")
    except ValueError as val_err:
        raise ValueError(f"Failed to parse .docx file: {val_err}") from val_err
    except Exception:
        pass

    # 1. Try python-docx
    try:
        from docx import Document
        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        
        # Include table contents
        for table in doc.tables:
            for row in table.rows:
                row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if row_text:
                    paragraphs.append(" | ".join(row_text))
                    
        return "\n\n".join(paragraphs).strip()
    except Exception:
        pass

    # 2. Zero-dependency fallback: extract word/document.xml from zip
    try:
        with zipfile.ZipFile(file_path, "r") as z:
            info = z.getinfo("word/document.xml")
            assert_zip_entry_is_safe(info)
            xml_content = z.read("word/document.xml")
            root = ET.fromstring(xml_content)  # nosec B314 - uses defusedxml
            texts = []
            for elem in root.iter():
                if elem.tag.endswith("}t") and elem.text:
                    texts.append(elem.text)
                elif elem.tag.endswith("}p"):
                    texts.append("\n")
            full_text = "".join(texts)
            cleaned = re.sub(r"\n\s*\n+", "\n\n", full_text).strip()
            return cleaned
    except Exception as err:
        raise ValueError(f"Failed to parse .docx file: {err}")


def _extract_plain_text(file_path: Union[str, Path]) -> str:
    """Extracts text from plain text or markdown files trying multiple encodings."""
    with open(file_path, "rb") as f:
        raw_bytes = f.read()

    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    for enc in encodings:
        try:
            return raw_bytes.decode(enc).strip()
        except UnicodeDecodeError:
            continue

    return raw_bytes.decode("utf-8", errors="replace").strip()


def _extract_json(file_path: Union[str, Path]) -> str:
    """
    Extracts text from JSON documents.
    Supports:
    - Dedicated text keys: {"text": "..."} or {"content": "..."}
    - Raw text JSON payloads: "plain string"
    - General JSON structures: formatted JSON string representation
    """
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        try:
            data = json.load(f)
        except Exception as e:
            raise ValueError(f"Invalid JSON document: {e}")

    if isinstance(data, dict):
        if "text" in data and isinstance(data["text"], str):
            return data["text"].strip()
        if "content" in data and isinstance(data["content"], str):
            return data["content"].strip()
        return json.dumps(data, indent=2)
    elif isinstance(data, str):
        return data.strip()
    return json.dumps(data, indent=2)


class DoclingParser:
    """Layout-aware PDF/DOCX parsing with reading-order and table recovery.

    Falls back cleanly to the existing parser on any failure. Never let a parser
    upgrade take the pipeline down.
    """

    def __init__(self, enable_ocr: bool = False):
        self.enable_ocr = enable_ocr
        self._converter = None
        self._init_failed = False

    def _ensure(self):
        if self._converter is None and not self._init_failed:
            try:
                from docling.document_converter import DocumentConverter
                self._converter = DocumentConverter()
            except Exception as exc:
                self._init_failed = True
                raise exc
        return self._converter

    def parse(self, path: str) -> str:
        converter = self._ensure()
        if converter is None:
            raise RuntimeError("Docling converter unavailable")
        result = converter.convert(str(path))
        return result.document.export_to_markdown()


def extract_text(file_path: Union[str, Path], filename_hint: Optional[str] = None) -> str:
    """
    Extracts plain text from a supported document file.
    
    Supported formats:
      - PDF: .pdf
      - Word: .docx
      - Plain text: .txt, .md
      - JSON: .json
      
    Raises:
      FileNotFoundError: If the file does not exist.
      ValueError: If the file extension is unsupported or legacy .doc.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Determine extension
    ext = path.suffix.lower()
    if not ext and filename_hint:
        ext = Path(filename_hint).suffix.lower()

    parser_backend = os.getenv("PARSER_BACKEND", "legacy").lower()

    if ext in (".pdf", ".docx") and parser_backend in ("docling", "auto"):
        try:
            docling_parser = DoclingParser()
            docling_text = docling_parser.parse(str(path)).strip()
            if parser_backend == "auto":
                legacy_text = _extract_pdf(path) if ext == ".pdf" else _extract_docx(path)
                if len(docling_text) >= 0.6 * len(legacy_text):
                    return docling_text
                return legacy_text
            return docling_text
        except Exception:
            pass  # Fall back cleanly to legacy parser

    if ext == ".pdf":
        return _extract_pdf(path)
    elif ext == ".docx":
        return _extract_docx(path)
    elif ext in (".txt", ".md"):
        return _extract_plain_text(path)
    elif ext == ".json":
        return _extract_json(path)
    elif ext == ".doc":
        raise ValueError(
            "Legacy .doc format is not supported. Please re-save as .docx or .pdf before uploading."
        )
    else:
        raise ValueError(
            f"Unsupported file format '{ext}'. Supported formats: .pdf, .docx, .txt, .md, .json"
        )


def extract_text_from_bytes(content: bytes, filename: str) -> str:
    """
    Extracts text from in-memory bytes buffer given a filename.
    Useful for direct multipart streaming without permanent disk writes.
    """
    import tempfile

    suffix = Path(filename).suffix.lower()
    if suffix == ".doc":
        raise ValueError(
            "Legacy .doc format is not supported. Please re-save as .docx or .pdf before uploading."
        )
    if suffix not in (".pdf", ".docx", ".txt", ".md", ".json"):
        raise ValueError(
            f"Unsupported file format '{suffix}'. Supported formats: .pdf, .docx, .txt, .md, .json"
        )

    # For text/markdown, decode directly in memory
    if suffix in (".txt", ".md"):
        encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
        for enc in encodings:
            try:
                return content.decode(enc).strip()
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace").strip()

    # For JSON documents, decode and parse directly in memory
    if suffix == ".json":
        try:
            decoded = content.decode("utf-8", errors="replace").strip()
            data = json.loads(decoded)
            if isinstance(data, dict):
                if "text" in data and isinstance(data["text"], str):
                    return data["text"].strip()
                if "content" in data and isinstance(data["content"], str):
                    return data["content"].strip()
                return json.dumps(data, indent=2)
            elif isinstance(data, str):
                return data.strip()
            return json.dumps(data, indent=2)
        except Exception as e:
            raise ValueError(f"Invalid JSON document: {e}")

    # For binary formats (.pdf, .docx), write to a temp file and parse
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        return extract_text(tmp_path, filename_hint=filename)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
