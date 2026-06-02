def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    if chunk_size is None:
        from app.config import Settings
        chunk_size = Settings().chunk_size
    if overlap is None:
        from app.config import Settings
        overlap = Settings().chunk_overlap
    if not text or not text.strip():
        return []

    text = text.strip()

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            # Try to break at paragraph boundary
            para_break = text.rfind("\n\n", start + chunk_size // 2, end)
            if para_break > start:
                end = para_break + 2
            else:
                # Try to break at sentence boundary
                for delim in [". ", "! ", "? ", "\n"]:
                    sent_break = text.rfind(delim, start + chunk_size // 2, end)
                    if sent_break > start:
                        end = sent_break + len(delim)
                        break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = max(start + 1, end - overlap)

    return chunks
