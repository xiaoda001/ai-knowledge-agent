from datetime import date, datetime


def version_key(document) -> tuple[str, str]:
    return document.knowledge_base_id, (document.filename or "").strip().casefold()


def _date_key(document) -> date:
    return document.effective_date or document.publication_date or document.created_at.date()


def current_document_ids(documents: list, today: date | None = None) -> set[str]:
    """Select the dated current version; ambiguous undated duplicates fail closed."""
    today = today or date.today()
    groups = {}
    for document in documents:
        groups.setdefault(version_key(document), []).append(document)
    current_ids = set()
    for versions in groups.values():
        dated = [document for document in versions
                 if document.effective_date or document.publication_date]
        if len(versions) > 1:
            # If the family is ambiguous, do not assume the newest upload is effective.
            candidates = dated
        else:
            candidates = versions
        candidates = [document for document in candidates
                      if not (document.effective_date or document.publication_date)
                      or (document.effective_date or document.publication_date) <= today]
        if not candidates:
            continue
        winner = max(candidates, key=lambda document: (
            _date_key(document), document.created_at or datetime.min, document.id,
        ))
        current_ids.add(winner.id)
    return current_ids


def document_version_states(documents: list, today: date | None = None) -> dict[str, str]:
    today = today or date.today()
    ready = [document for document in documents if document.status == "ready"]
    current_ids = current_document_ids(ready, today)
    family_sizes = {}
    for document in ready:
        key = version_key(document)
        family_sizes[key] = family_sizes.get(key, 0) + 1
    states = {}
    for document in documents:
        if document.status == "expired":
            states[document.id] = "expired"
        elif document.status != "ready":
            states[document.id] = document.status
        elif ((document.effective_date or document.publication_date)
              and (document.effective_date or document.publication_date) > today):
            states[document.id] = "scheduled"
        elif (family_sizes[version_key(document)] > 1
              and not (document.effective_date or document.publication_date)):
            states[document.id] = "needs_review"
        elif document.id in current_ids:
            states[document.id] = "current"
        else:
            states[document.id] = "superseded"
    return states
