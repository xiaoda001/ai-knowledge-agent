from pathlib import Path
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET


MAX_ARCHIVE_ENTRIES = 10_000
MAX_UNPACKED_BYTES = 100 * 1024 * 1024
MAX_TEXT_CHARS = 5_000_000


def _append_text(parts: list[str], value: str | None) -> None:
    if value and sum(map(len, parts)) < MAX_TEXT_CHARS:
        parts.append(value[:MAX_TEXT_CHARS - sum(map(len, parts))])


def _xml_text(data: bytes) -> list[str]:
    root = ET.fromstring(data)
    return [node.text or "" for node in root.iter() if node.tag.endswith("}t") or node.tag == "t"]


def _read_archive(path: Path) -> ZipFile:
    archive = ZipFile(path)
    entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_ENTRIES or sum(item.file_size for item in entries) > MAX_UNPACKED_BYTES:
        archive.close()
        raise ValueError("Office document expands beyond the allowed processing limit")
    return archive


def _extract_docx(path: Path) -> str:
    with _read_archive(path) as archive:
        try:
            values = _xml_text(archive.read("word/document.xml"))
        except KeyError as exc:
            raise ValueError("Invalid DOCX document") from exc
    return "\n".join(value for value in values if value.strip())


def _extract_pptx(path: Path) -> str:
    def slide_order(name: str):
        number = Path(name).stem.removeprefix("slide")
        return (0, int(number)) if number.isdigit() else (1, name)

    with _read_archive(path) as archive:
        slides = sorted((name for name in archive.namelist()
                         if name.startswith("ppt/slides/slide") and name.endswith(".xml")),
                        key=slide_order)
        parts: list[str] = []
        for slide in slides:
            _append_text(parts, " ".join(_xml_text(archive.read(slide))))
    return "\n".join(parts)


def _extract_xlsx(path: Path) -> str:
    with _read_archive(path) as archive:
        names = set(archive.namelist())
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.iter():
                if item.tag.endswith("}si") or item.tag == "si":
                    shared_strings.append("".join(_xml_text(ET.tostring(item, encoding="utf-8"))))
        worksheets = sorted(name for name in names
                            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
        parts: list[str] = []
        for sheet in worksheets:
            root = ET.fromstring(archive.read(sheet))
            for cell in root.iter():
                if not cell.tag.endswith("}c") and cell.tag != "c":
                    continue
                value = next((node.text for node in cell if node.tag.endswith("}v") or node.tag == "v"), None)
                if cell.attrib.get("t") == "inlineStr" and value is None:
                    value = "".join(node.text or "" for node in cell.iter()
                                     if node.tag.endswith("}t") or node.tag == "t")
                if cell.attrib.get("t") == "s" and value is not None:
                    try:
                        value = shared_strings[int(value)]
                    except (ValueError, IndexError):
                        value = ""
                if value:
                    _append_text(parts, value)
    return "\n".join(parts)


def extract_document_text(path: str | Path) -> str:
    file_path = Path(path)
    extension = file_path.suffix.lower()
    if extension in {".md", ".txt", ".csv"}:
        return file_path.read_text(encoding="utf-8-sig", errors="replace")[:MAX_TEXT_CHARS]
    if extension == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(file_path, strict=False)
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs cannot be indexed")
        if len(reader.pages) > 500:
            raise ValueError("PDF exceeds the 500 page processing limit")
        parts: list[str] = []
        for page in reader.pages:
            _append_text(parts, page.extract_text())
            if sum(map(len, parts)) >= MAX_TEXT_CHARS:
                break
        text = "\n".join(parts)
        if not text.strip():
            raise ValueError("PDF contains no extractable text; scanned PDFs require OCR")
        return text
    if extension in {".docx", ".xlsx", ".pptx"}:
        try:
            text = {".docx": _extract_docx, ".xlsx": _extract_xlsx, ".pptx": _extract_pptx}[extension](file_path)
        except BadZipFile as exc:
            raise ValueError("Invalid Office document") from exc
        if not text.strip():
            raise ValueError("Office document contains no extractable text")
        return text[:MAX_TEXT_CHARS]
    raise ValueError(f"Unsupported document type: {extension}")
