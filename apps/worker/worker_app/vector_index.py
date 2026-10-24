import chromadb

from server_core.config import settings
from server_core.embeddings import embed_texts


def replace_document_vectors(document, chunks) -> None:
    client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    collection = client.get_or_create_collection("knowledge_chunks")
    collection.delete(where={"document_id": document.id})
    metadata = {
        "document_id": document.id,
        "knowledge_base_id": document.knowledge_base_id,
        "access_scope": document.access_scope,
    }
    if document.publication_date is not None:
        metadata["publication_date"] = document.publication_date.isoformat()
    if document.effective_date is not None:
        metadata["effective_date"] = document.effective_date.isoformat()
    if document.department_id is not None:
        metadata["department_id"] = document.department_id
    if document.classification_level is not None:
        metadata["classification_level"] = document.classification_level
    collection.add(
        ids=[chunk.id for chunk in chunks],
        documents=[chunk.text for chunk in chunks],
        embeddings=embed_texts([chunk.text for chunk in chunks]),
        metadatas=[metadata.copy() for _ in chunks],
    )
