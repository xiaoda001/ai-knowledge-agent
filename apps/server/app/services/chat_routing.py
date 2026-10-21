import re


def route_catalog(knowledge_bases, redact):
    """Build model-visible per-turn refs without exposing database identifiers."""
    catalog = []
    id_by_ref = {}
    for index, knowledge_base in enumerate(knowledge_bases, 1):
        reference = f"kb_{index}"
        catalog.append({
            "ref": reference,
            "name": redact(knowledge_base.name),
            "description": redact(getattr(knowledge_base, "description", "") or ""),
        })
        id_by_ref[reference] = knowledge_base.id
    return catalog, id_by_ref


def resolve_knowledge_base_scope(references, id_by_ref, authorized_ids):
    """Resolve exact planner refs; empty/invalid output safely falls back to authorized scope."""
    routed_ids = list(dict.fromkeys(id_by_ref[reference] for reference in references
                                    if reference in id_by_ref))
    if routed_ids:
        return routed_ids
    return list(dict.fromkeys(authorized_ids))


def cited_sources(answer: str, sources: list[dict]) -> list[dict]:
    """Keep only sources cited with the standard [n] reference syntax."""
    cited_numbers = {int(value) for value in re.findall(r"\[(\d+)\]", answer or "")}
    return [
        {**source, "source_number": index}
        for index, source in enumerate(sources, 1)
        if index in cited_numbers
    ]
