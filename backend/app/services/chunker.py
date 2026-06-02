import re
import uuid
from dataclasses import dataclass, field


@dataclass
class ChunkMetadata:
    """Metadata attached to each chunk describing its structural context."""
    heading: str = ""
    heading_level: int = 0
    chunk_type: str = "text"  # "text", "table", "code", "list"
    position: int = 0


@dataclass
class ChunkResult:
    """A chunk of text with its structural metadata."""
    text: str
    metadata: ChunkMetadata


# ---------------------------------------------------------------------------
# Internal: parse document into structural blocks
# ---------------------------------------------------------------------------

def _parse_blocks(text: str) -> list[dict]:
    """Parse text into structural blocks: heading, table, code, list, text.

    Each block is a dict with keys:
        type: str
        lines: list[str]
        heading: str  (current section heading)
        heading_level: int
    """
    lines = text.split("\n")
    blocks: list[dict] = []
    current_block: dict = {
        "type": "text", "lines": [], "heading": "", "heading_level": 0,
    }

    i = 0
    while i < len(lines):
        line = lines[i]

        # ---- Markdown heading ----
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            if current_block["lines"]:
                blocks.append(current_block)
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            blocks.append({
                "type": "heading",
                "lines": [line],
                "heading": heading_text,
                "heading_level": level,
            })
            current_block = {
                "type": "text", "lines": [],
                "heading": heading_text, "heading_level": level,
            }
            i += 1
            continue

        # ---- Code block (``` or ~~~) ----
        if re.match(r"^\s*(```|~~~)", line):
            if current_block["lines"]:
                blocks.append(current_block)
            fence = line.strip()[:3]
            code_lines = [line]
            i += 1
            while i < len(lines):
                code_lines.append(lines[i])
                if lines[i].strip().startswith(fence):
                    i += 1
                    break
                i += 1
            blocks.append({
                "type": "code",
                "lines": code_lines,
                "heading": current_block.get("heading", ""),
                "heading_level": current_block.get("heading_level", 0),
            })
            current_block = {
                "type": "text", "lines": [],
                "heading": current_block.get("heading", ""),
                "heading_level": current_block.get("heading_level", 0),
            }
            continue

        # ---- Table line ----
        if line.strip().startswith("|") and "|" in line[1:]:
            if current_block["type"] != "table":
                if current_block["lines"]:
                    blocks.append(current_block)
                current_block = {
                    "type": "table", "lines": [],
                    "heading": current_block.get("heading", ""),
                    "heading_level": current_block.get("heading_level", 0),
                }
            current_block["lines"].append(line)
            i += 1
            continue

        # ---- Bullet list item ----
        if re.match(r"^\s*[-*]\s+", line):
            if current_block["type"] != "list":
                if current_block["lines"]:
                    blocks.append(current_block)
                current_block = {
                    "type": "list", "lines": [],
                    "heading": current_block.get("heading", ""),
                    "heading_level": current_block.get("heading_level", 0),
                }
            current_block["lines"].append(line)
            i += 1
            continue

        # ---- Regular text ----
        if current_block["type"] != "text":
            if current_block["lines"]:
                blocks.append(current_block)
            current_block = {
                "type": "text", "lines": [],
                "heading": current_block.get("heading", ""),
                "heading_level": current_block.get("heading_level", 0),
            }
        current_block["lines"].append(line)
        i += 1

    if current_block["lines"]:
        blocks.append(current_block)

    return blocks


# ---------------------------------------------------------------------------
# Internal: sliding-window chunker (original algorithm, extracted)
# ---------------------------------------------------------------------------

def _sliding_window_chunk(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Original sliding-window chunking with paragraph/sentence boundary detection."""
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            para_break = text.rfind("\n\n", start + chunk_size // 2, end)
            if para_break > start:
                end = para_break + 2
            else:
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


# ---------------------------------------------------------------------------
# Internal: assemble chunks from parsed blocks
# ---------------------------------------------------------------------------

def _chunk_blocks(
    blocks: list[dict], chunk_size: int, overlap: int,
) -> list[ChunkResult]:
    """Combine structural blocks into sized chunks.

    Rules:
    - Atomic blocks (table, code, list) are never split mid-block.
    - A new heading always flushes the buffer (starts a new chunk).
    - Text blocks are split with sliding-window when they exceed chunk_size.
    """
    results: list[ChunkResult] = []
    buffer: list[tuple[str, str, str, int]] = []  # (text, type, heading, level)
    buffer_len = 0

    def _flush():
        nonlocal buffer, buffer_len
        if not buffer:
            return
        combined = "\n".join(t for t, _, _, _ in buffer)
        # chunk_type = dominant type; if mixed, call it "text"
        types = {bt for _, bt, _, _ in buffer}
        chunk_type = (types.pop() if len(types) == 1 else "text")
        _, _, h, hl = buffer[0]
        results.append(ChunkResult(
            text=combined.strip(),
            metadata=ChunkMetadata(heading=h, heading_level=hl, chunk_type=chunk_type),
        ))
        buffer = []
        buffer_len = 0

    for block in blocks:
        block_text = "\n".join(block["lines"]).strip()
        if not block_text:
            continue

        block_type: str = block["type"]
        heading: str = block.get("heading", "")
        heading_level: int = block.get("heading_level", 0)

        # New heading always flushes previous content
        if block_type == "heading":
            _flush()
            buffer.append((block_text, "heading", heading, heading_level))
            buffer_len = len(block_text)
            continue

        # Atomic blocks: table, code, list
        if block_type in ("table", "code", "list"):
            # Oversized atomic block: flush buffer, emit as its own chunk
            if len(block_text) > chunk_size:
                _flush()
                results.append(ChunkResult(
                    text=block_text,
                    metadata=ChunkMetadata(
                        heading=heading, heading_level=heading_level,
                        chunk_type=block_type,
                    ),
                ))
                continue

            # Would overflow buffer -> flush first
            if buffer_len + len(block_text) + (1 if buffer_len else 0) > chunk_size:
                _flush()

            buffer.append((block_text, block_type, heading, heading_level))
            buffer_len += len(block_text) + (1 if buffer_len > len(block_text) else 0)
            continue

        # Text block that fits easily
        if len(block_text) <= chunk_size:
            if buffer_len + len(block_text) + (1 if buffer_len else 0) > chunk_size:
                _flush()
            buffer.append((block_text, "text", heading, heading_level))
            buffer_len += len(block_text) + (1 if buffer_len > len(block_text) else 0)
            continue

        # Large text block: flush buffer then sliding-window split
        _flush()
        for chunk in _sliding_window_chunk(block_text, chunk_size, overlap):
            results.append(ChunkResult(
                text=chunk,
                metadata=ChunkMetadata(
                    heading=heading, heading_level=heading_level,
                    chunk_type="text",
                ),
            ))

    _flush()

    # Assign sequential positions
    for idx, result in enumerate(results):
        result.metadata.position = idx

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_text_structured(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[ChunkResult]:
    """Structure-aware chunking.  Returns chunks with metadata."""
    if chunk_size is None:
        from app.config import Settings
        chunk_size = Settings().chunk_size
    if overlap is None:
        from app.config import Settings
        overlap = Settings().chunk_overlap

    if not text or not text.strip():
        return []

    text = text.strip()

    blocks = _parse_blocks(text)
    return _chunk_blocks(blocks, chunk_size, overlap)


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Backward-compatible entry point.  Returns list[str].

    When ``structure_aware_chunking`` is enabled (default) the structured
    pipeline runs internally; only the plain text is returned so existing
    callers keep working.
    """
    from app.config import Settings
    settings = Settings()

    if settings.structure_aware_chunking:
        results = chunk_text_structured(text, chunk_size, overlap)
        return [r.text for r in results]

    # --- original simple sliding-window (no structure) ---
    if chunk_size is None:
        chunk_size = settings.chunk_size
    if overlap is None:
        overlap = settings.chunk_overlap

    if not text or not text.strip():
        return []

    text = text.strip()

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            para_break = text.rfind("\n\n", start + chunk_size // 2, end)
            if para_break > start:
                end = para_break + 2
            else:
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


def create_parent_child_chunks(
    text: str,
    parent_chunk_size: int | None = None,
    child_chunk_size: int | None = None,
    overlap: int | None = None,
) -> dict:
    """Split text into parent and child chunks for hierarchical retrieval.

    Strategy:
    - Parent chunks (default 1500 chars): broad context returned to the LLM.
    - Child chunks (default 500 chars): fine-grained units that get embedded
      and searched.  When a child matches, the parent is returned instead.

    Args:
        text: Full document text to chunk.
        parent_chunk_size: Character size for parent chunks (default from Settings).
        child_chunk_size: Character size for child chunks (default from Settings).
        overlap: Character overlap between consecutive chunks (default from Settings).

    Returns:
        {
            "parents": [
                {"id": str, "text": str, "child_ids": [str, ...]},
                ...
            ],
            "children": [
                {"text": str, "parent_id": str, "position_in_parent": int},
                ...
            ],
        }
    """
    if parent_chunk_size is None or child_chunk_size is None or overlap is None:
        from app.config import Settings
        settings = Settings()
        if parent_chunk_size is None:
            parent_chunk_size = settings.parent_chunk_size
        if child_chunk_size is None:
            child_chunk_size = settings.child_chunk_size
        if overlap is None:
            overlap = settings.chunk_overlap

    if not text or not text.strip():
        return {"parents": [], "children": []}

    # Step 1: create parent chunks at the larger size
    parent_texts = chunk_text(text, chunk_size=parent_chunk_size, overlap=overlap)

    parents = []
    children = []

    for parent_text in parent_texts:
        parent_id = str(uuid.uuid4())

        # Step 2: split each parent into child chunks at the smaller size
        child_texts = chunk_text(parent_text, chunk_size=child_chunk_size, overlap=overlap)

        # Edge case: if parent is short enough to be a single child, keep it as-is
        if not child_texts:
            child_texts = [parent_text]

        child_ids = []
        for position, child_text in enumerate(child_texts):
            child_id = str(uuid.uuid4())
            child_ids.append(child_id)
            children.append({
                "id": child_id,
                "text": child_text,
                "parent_id": parent_id,
                "position_in_parent": position,
            })

        parents.append({
            "id": parent_id,
            "text": parent_text,
            "child_ids": child_ids,
        })

    return {"parents": parents, "children": children}
