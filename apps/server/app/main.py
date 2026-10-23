from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.routes import admin, auth, chat, departments, documents, files, knowledge_bases, roles
from app.services.legacy_roles import ensure_legacy_read_only_role
from server_core.config import settings
from server_core.db import Base, engine
from server_core.departments import ensure_department_schema
from server_core.observability import configure_observability
from worker_app.celery_app import celery_app as worker_celery_app
from server_core import models as _models  # noqa: F401

app = FastAPI(title="Enterprise Knowledge Base API")
configure_observability(app=app, engine=engine, celery_app=worker_celery_app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Trace-ID", "X-Session-ID"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(roles.router)
app.include_router(departments.router)
app.include_router(knowledge_bases.router)
app.include_router(documents.router)
app.include_router(files.router)
app.include_router(chat.router)


def ensure_chat_message_usage_column(database_engine=engine):
    message_columns = {column["name"] for column in inspect(database_engine).get_columns("chat_messages")}
    if "usage" not in message_columns:
        usage_column = database_engine.dialect.identifier_preparer.quote("usage")
        with database_engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE chat_messages ADD COLUMN {usage_column} JSON NULL"))


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
    if "nickname" not in user_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN nickname VARCHAR(128) NOT NULL DEFAULT ''"))
    ensure_department_schema(engine)
    document_columns = {column["name"] for column in inspect(engine).get_columns("documents")}
    if "access_scope" not in document_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE documents ADD COLUMN access_scope VARCHAR(32) NOT NULL DEFAULT 'document_acl'"))
    if "description" not in {column["name"] for column in inspect(engine).get_columns("knowledge_bases")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE knowledge_bases ADD COLUMN description VARCHAR(1000) NOT NULL DEFAULT ''"))
    conversation_columns = {column["name"] for column in inspect(engine).get_columns("chat_conversations")}
    with engine.begin() as connection:
        if "memory_summary" not in conversation_columns:
            connection.execute(text("ALTER TABLE chat_conversations ADD COLUMN memory_summary TEXT NULL"))
        if "summary_through_message_id" not in conversation_columns:
            connection.execute(text("ALTER TABLE chat_conversations ADD COLUMN summary_through_message_id VARCHAR(36) NULL"))
    ensure_chat_message_usage_column(engine)
    ensure_legacy_read_only_role()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
