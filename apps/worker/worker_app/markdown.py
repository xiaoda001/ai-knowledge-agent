def split_markdown(text: str, max_chars: int = 900) -> list[str]:
    sections = [section.strip() for section in text.split("\n\n") if section.strip()]
    chunks: list[str] = []
    current = ""
    for section in sections:
        while len(section) > max_chars:
            split_at = section.rfind(" ", 0, max_chars)
            if split_at < max_chars // 2:
                split_at = max_chars
            piece, section = section[:split_at].strip(), section[split_at:].strip()
            if current:
                chunks.append(current)
                current = ""
            if piece:
                chunks.append(piece)
        if current and len(current) + len(section) + 2 > max_chars:
            chunks.append(current)
            current = ""
        current = f"{current}\n\n{section}".strip()
    if current:
        chunks.append(current)
    return chunks
