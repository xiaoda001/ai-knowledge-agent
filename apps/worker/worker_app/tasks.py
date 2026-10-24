from sqlalchemy import delete

from server_core.db import SessionLocal
from server_core.models import Chunk, Document
from worker_app.celery_app import celery_app
from worker_app.extract import extract_document_text
from worker_app.document_dates import extract_document_dates
from worker_app.markdown import split_markdown
from worker_app.vector_index import replace_document_vectors
from server_core.observability import tracer


_tracer = tracer(__name__)


@celery_app.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def ingest_document(self, doc_id: str):
    with _tracer.start_as_current_span("document.ingest") as span:
        return _ingest_document(self, doc_id, span)


def _ingest_document(self, doc_id: str, span):
    db = SessionLocal()
    try:
        doc = db.get(Document, doc_id)
        if doc is None:
            return
        doc.status = "processing"
        doc.error_message = None
        db.commit()
        text = extract_document_text(doc.storage_path)
        doc.publication_date, doc.effective_date = extract_document_dates(text)
        chunks = split_markdown(text)
        span.set_attribute("ingest.chunk_count", len(chunks))
        if not chunks:
            raise ValueError("Document has no indexable text")
        db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
        rows = []
        for idx, content in enumerate(chunks):
            row = Chunk(document_id=doc.id, text=content, ordinal=idx)
            db.add(row)
            rows.append(row)
        db.flush()
        replace_document_vectors(doc, rows)
        doc.status = "ready"
        db.commit()
    except Exception as exc:
        db.rollback()
        doc = db.get(Document, doc_id)
        if doc is not None:
            doc.status = "failed" if self.request.retries >= self.max_retries else "queued"
            # Provider errors from server_core.model_api are deliberately sanitized
            # (they contain only the HTTP status, never response bodies or keys).
            # Preserve those details so the UI can explain configuration failures.
            doc.error_message = (
                str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__
            )[:200]
            db.commit()
        raise
    finally:
        db.close()


ingest_markdown = ingest_document
