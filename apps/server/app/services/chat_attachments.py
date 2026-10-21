from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException
from starlette.datastructures import UploadFile
from starlette.concurrency import run_in_threadpool

from worker_app.extract import extract_document_text


SUPPORTED_EXTENSIONS = {".md", ".txt", ".csv", ".pdf", ".docx", ".xlsx", ".pptx"}
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
MAX_ATTACHMENT_CONTEXT_CHARS = 50_000


async def extract_chat_attachment(file: UploadFile) -> dict[str, str | bool]:
    filename = "".join(character for character in Path((file.filename or "").replace("\\", "/")).name.strip()
                        if character.isprintable())[:255]
    extension = Path(filename).suffix.lower()
    if not filename or extension not in SUPPORTED_EXTENSIONS:
        await file.close()
        raise HTTPException(415, "附件仅支持 PDF、Word、Excel、PowerPoint、TXT、CSV 和 Markdown")

    try:
        with TemporaryDirectory(prefix="chat-attachment-") as directory:
            path = Path(directory) / f"attachment{extension}"
            size = 0
            with path.open("wb") as output:
                while data := await file.read(64 * 1024):
                    size += len(data)
                    if size > MAX_ATTACHMENT_BYTES:
                        raise HTTPException(413, "聊天附件不能超过 20 MiB")
                    output.write(data)
            if size == 0:
                raise HTTPException(422, "附件不能为空")
            text = await run_in_threadpool(extract_document_text, path)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "无法从附件提取文本，请确认文件格式正确且包含可提取的文字") from None
    finally:
        await file.close()

    if not text.strip():
        raise HTTPException(422, "附件中没有可提取的文字；扫描版 PDF 暂不支持 OCR")

    bounded_text = text[:MAX_ATTACHMENT_CONTEXT_CHARS]
    return {
        "filename": filename,
        "text": bounded_text,
        "truncated": len(text) > len(bounded_text),
    }
