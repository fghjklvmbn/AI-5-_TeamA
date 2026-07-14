from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from ..database import Database

SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".pdf", ".docx"}
MAX_EXTRACTED_CHARS = 200_000
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")


class DocumentExtractionError(ValueError):
    pass


class DocumentEngine:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _decode_text(content: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "cp949"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise DocumentExtractionError("파일 문자 인코딩을 읽을 수 없습니다. UTF-8 파일로 다시 저장해 주세요.")

    @staticmethod
    def _extract_docx(content: bytes) -> str:
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise DocumentExtractionError("올바른 DOCX 파일이 아닙니다.") from exc
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = []
        for paragraph in root.iter(f"{ns}p"):
            line = "".join(node.text or "" for node in paragraph.iter(f"{ns}t"))
            if line.strip():
                paragraphs.append(line.strip())
        return "\n".join(paragraphs)

    @staticmethod
    def _extract_pdf(content: bytes) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise DocumentExtractionError("PDF의 텍스트를 읽을 수 없습니다.") from exc

    def extract(self, filename: str, content: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise DocumentExtractionError(f"지원하는 파일 형식은 {', '.join(sorted(SUPPORTED_EXTENSIONS))}입니다.")
        if suffix == ".docx":
            text = self._extract_docx(content)
        elif suffix == ".pdf":
            text = self._extract_pdf(content)
        else:
            text = self._decode_text(content)
            if suffix == ".json":
                try:
                    text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
                except json.JSONDecodeError as exc:
                    raise DocumentExtractionError("올바른 JSON 파일이 아닙니다.") from exc
        text = re.sub(r"[ \t]+", " ", text.replace("\x00", ""))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not text:
            raise DocumentExtractionError("파일에서 검색할 수 있는 텍스트를 찾지 못했습니다.")
        return text[:MAX_EXTRACTED_CHARS]

    @staticmethod
    def _chunks(text: str, size: int = 900, overlap: int = 120) -> list[str]:
        if len(text) <= size:
            return [text]
        chunks, start = [], 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                boundary = max(text.rfind("\n", start + size // 2, end), text.rfind(". ", start + size // 2, end))
                if boundary > start:
                    end = boundary + 1
            chunks.append(text[start:end].strip())
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
        return [chunk for chunk in chunks if chunk]

    def retrieve_context(self, user_id: str, session_id: str, query: str) -> str:
        rows = self.db.list_attachments(user_id, session_id)
        if not rows:
            return ""
        query_tokens = set(TOKEN_RE.findall(query.lower()))
        candidates = []
        order = 0
        for row in rows:
            for chunk in self._chunks(row["text_content"]):
                overlap = query_tokens & set(TOKEN_RE.findall(chunk.lower()))
                score = sum(2 if len(token) >= 4 else 1 for token in overlap)
                candidates.append((float(score), -order, row["filename"], chunk))
                order += 1
        matched = [item for item in candidates if item[0] > 0]
        selected = sorted(matched, reverse=True)[:4] if matched else candidates[: min(2, len(candidates))]
        return "\n\n".join(
            f"[첨부파일: {filename}]\n{chunk}" for _, _, filename, chunk in selected
        )[:4_000]
