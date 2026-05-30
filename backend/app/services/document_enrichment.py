import re


SECTION_LABELS = {
    "available colors",
    "colors",
    "features",
    "signature features",
    "key features",
    "specifications",
    "product specifications",
    "description",
    "model",
    "price",
    "keywords",
    "summary",
}


def _bold(value: str) -> str:
    value = value.strip()
    if not value or value.startswith("**") and value.endswith("**"):
        return value
    return f"**{value}**"


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip().strip(":")
    if not stripped or len(stripped) > 90:
        return False

    words = stripped.split()
    if re.match(r"^(?:Provides|Contains|Includes|Allows|Offers|Supports|Enables|Designed|Made|Built)\b", stripped):
        return False
    if len(words) > 5 and any(word.lower() in {"to", "the", "while", "with", "and", "or", "for", "of", "in"} for word in words):
        return False

    lowered = stripped.lower()
    if lowered in SECTION_LABELS:
        return True

    if re.match(r"^#{1,6}\s+", line):
        return True

    if re.match(r"^(?:\d+[\).]\s*)?[A-Z][A-Za-z0-9/&+,\- ™®]{2,}$", stripped):
        words = stripped.split()
        return len(words) <= 8 and not stripped.endswith((".", ",", ";"))

    return False


def emphasize_document_text(text: str, metadata: dict | None = None) -> str:
    """Add lightweight Markdown importance cues before chunking and embedding."""
    metadata = metadata or {}
    title = str(metadata.get("title") or "").strip()
    tags = [str(tag).strip() for tag in metadata.get("tags", []) if str(tag).strip()]
    summary = str(metadata.get("summary") or "").strip()

    header: list[str] = []
    if title:
        header.append(f"# {_bold(title)}")
    if tags:
        header.append("**Keywords:** " + ", ".join(_bold(tag) for tag in tags))
    if summary:
        header.append("**Summary:** " + summary)

    body_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if _looks_like_heading(stripped):
            if stripped.startswith("#"):
                body_lines.append(re.sub(r"^(#{1,6}\s+)(.+)$", lambda m: f"{m.group(1)}{_bold(m.group(2))}", line))
            else:
                body_lines.append(_bold(stripped))
            continue

        body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if not header:
        return body
    if not body:
        return "\n".join(header)
    return "\n".join(header) + "\n\n" + body
