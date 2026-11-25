"""Deterministic document parsing and chunking utilities."""
from pathlib import Path
import re
from .models import Chunk, Document, DocumentSection


def parse_document(path: Path) -> Document:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        text = path.read_text(encoding="utf-8")
    elif suffix == ".pdf":
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    elif suffix == ".docx":
        from docx import Document as DocxDocument
        source = DocxDocument(str(path))
        paragraphs = [p.text for p in source.paragraphs]
        tables = ["\n".join(cell.text for row in table.rows for cell in row.cells)
                  for table in source.tables]
        text = "\n".join(paragraphs + tables)
    else:
        raise ValueError(f"Unsupported PRD format: {suffix}")
    sections: list[DocumentSection] = []
    current_heading, current_lines, current_level = path.stem, [], 1
    for line in text.splitlines():
        match = re.match(r"^(#+)\s+(.+)$", line)
        if match:
            if current_lines:
                sections.append(DocumentSection(
                    heading=current_heading, content="\n".join(current_lines),
                    level=current_level, source_location=f"section:{len(sections) + 1}",
                ))
            current_heading, current_lines = match.group(2).strip(), []
            current_level = len(match.group(1))
        else:
            if line.strip():
                current_lines.append(line.strip())
    if current_lines:
        sections.append(DocumentSection(
            heading=current_heading, content="\n".join(current_lines),
            level=current_level, source_location=f"section:{len(sections) + 1}",
        ))
    return Document(source_path=str(path), title=path.stem, sections=sections, text=text)


def chunk_document(document: Document, size: int, overlap: int) -> list[Chunk]:
    section_words = [(section.heading, section.content.split()) for section in document.sections]
    words = [word for _, values in section_words for word in values]
    step = max(1, size - overlap)
    chunks: list[Chunk] = []
    for index in range(0, len(words), step):
        text = " ".join(words[index:index + size])
        section_heading = ""
        position = 0
        for heading, values in section_words:
            if position <= index < position + len(values):
                section_heading = heading
                break
            position += len(values)
        chunks.append(Chunk(id=f"chunk-{index // step + 1}", text=text,
                            section_heading=section_heading))
    return chunks or [Chunk(id="chunk-1", text="", section_heading=document.title)]
