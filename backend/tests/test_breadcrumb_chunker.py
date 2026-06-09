"""Tests for breadcrumb augmentation in parent-child chunking."""
import asyncio
import pytest
from app.services.chunker import (
    prepend_breadcrumb,
    create_parent_child_chunks,
    create_parent_child_chunks_semantic,
    chunk_text_structured,
)


# ---------------------------------------------------------------------------
# Tests for prepend_breadcrumb
# ---------------------------------------------------------------------------

class TestPrependBreadcrumb:
    def test_heading_and_title(self):
        result = prepend_breadcrumb("some text", "Introduction", 1, "My Doc")
        assert result == "My Doc > Introduction: some text"

    def test_heading_only_no_title(self):
        result = prepend_breadcrumb("some text", "Methods", 2)
        assert result == "Methods: some text"

    def test_title_only_no_heading(self):
        result = prepend_breadcrumb("some text", "", 0, "My Doc")
        assert result == "My Doc: some text"

    def test_no_heading_no_title_returns_unchanged(self):
        result = prepend_breadcrumb("some text", "", 0)
        assert result == "some text"

    def test_empty_text_with_context(self):
        result = prepend_breadcrumb("", "Section", 1, "Doc")
        assert result == "Doc > Section: "

    def test_nested_heading_with_title(self):
        result = prepend_breadcrumb("content", "Sub Section", 3, "Report")
        assert result == "Report > Sub Section: content"

    def test_heading_level_does_not_appear_in_output(self):
        """Heading level is metadata; the breadcrumb uses heading text only."""
        result = prepend_breadcrumb("text", "Heading", 6, "Doc")
        assert result == "Doc > Heading: text"
        assert "6" not in result

    def test_whitespace_only_heading_treated_as_empty(self):
        result = prepend_breadcrumb("text", "   ", 1, "Doc")
        # Whitespace-only heading should be stripped and ignored
        assert result == "Doc: text"


# ---------------------------------------------------------------------------
# Tests for create_parent_child_chunks with breadcrumbs
# ---------------------------------------------------------------------------

class TestCreateParentChildChunks:
    def test_basic_structure_preserved(self):
        """Return format must remain {"parents": [...], "children": [...]}."""
        text = "Hello world. " * 200  # long enough to produce multiple chunks
        result = create_parent_child_chunks(text, parent_chunk_size=500, child_chunk_size=200, overlap=50)
        assert "parents" in result
        assert "children" in result
        assert len(result["parents"]) >= 1
        assert len(result["children"]) >= 1

    def test_children_reference_parent_ids(self):
        text = "Hello world. " * 200
        result = create_parent_child_chunks(text, parent_chunk_size=500, child_chunk_size=200, overlap=50)
        parent_ids = {p["id"] for p in result["parents"]}
        for child in result["children"]:
            assert child["parent_id"] in parent_ids

    def test_parent_child_ids_consistent(self):
        text = "Hello world. " * 200
        result = create_parent_child_chunks(text, parent_chunk_size=500, child_chunk_size=200, overlap=50)
        for parent in result["parents"]:
            child_ids_in_parent = set(parent["child_ids"])
            child_ids_actual = {
                c["id"] for c in result["children"] if c["parent_id"] == parent["id"]
            }
            assert child_ids_in_parent == child_ids_actual

    def test_empty_text_returns_empty(self):
        result = create_parent_child_chunks("")
        assert result == {"parents": [], "children": []}

    def test_no_heading_no_title_no_breadcrumb(self):
        """Plain text with no headings should not get a breadcrumb prefix."""
        text = "Just some plain text without any markdown headings. " * 10
        result = create_parent_child_chunks(text, parent_chunk_size=300, child_chunk_size=100, overlap=20)
        for parent in result["parents"]:
            # Should NOT contain ": " separator from breadcrumb
            assert ": " not in parent["text"] or parent["text"].startswith("Just") or parent["text"].startswith("plain")
        for child in result["children"]:
            assert ": " not in child["text"] or child["text"].startswith("Just") or child["text"].startswith("plain")

    def test_heading_appears_in_parent_text(self):
        """When doc has headings, parent text should include breadcrumb."""
        text = (
            "# Introduction\n"
            "This is the introduction section with enough text to create a chunk. "
            "We need quite a bit of content here to exceed the child chunk size. "
            "So let us add more sentences about the introduction topic.\n"
            "## Background\n"
            "This is the background section. It also needs enough text to form "
            "at least one chunk when we apply the parent chunk size setting.\n"
        )
        result = create_parent_child_chunks(
            text, parent_chunk_size=300, child_chunk_size=100, overlap=20, doc_title="Research Paper",
        )
        # At least one parent should contain the breadcrumb
        parent_texts = [p["text"] for p in result["parents"]]
        assert any("Research Paper" in t for t in parent_texts), (
            f"Expected breadcrumb in parent texts: {parent_texts}"
        )

    def test_child_gets_parent_heading_breadcrumb(self):
        """Child chunks should get the parent's heading, not a sub-heading."""
        text = (
            "# Main Section\n"
            "Content under the main section. " * 20
        )
        result = create_parent_child_chunks(
            text, parent_chunk_size=400, child_chunk_size=100, overlap=20, doc_title="Doc",
        )
        for child in result["children"]:
            if "Main Section" in child["text"]:
                assert "Doc > Main Section" in child["text"]

    def test_doc_title_only_no_heading(self):
        """When doc_title is set but no headings exist, breadcrumb should be just the title."""
        text = "Plain text content without any markdown headings. " * 20
        result = create_parent_child_chunks(
            text, parent_chunk_size=300, child_chunk_size=100, overlap=20, doc_title="My Document",
        )
        for parent in result["parents"]:
            assert parent["text"].startswith("My Document:")

    def test_nested_headings_in_breadcrumb(self):
        """Deeply nested headings should appear in the breadcrumb."""
        text = (
            "### Deep Subsection\n"
            "Content under a deeply nested heading. " * 20
        )
        result = create_parent_child_chunks(
            text, parent_chunk_size=400, child_chunk_size=100, overlap=20, doc_title="Report",
        )
        parent_texts = [p["text"] for p in result["parents"]]
        assert any("Report > Deep Subsection" in t for t in parent_texts)


# ---------------------------------------------------------------------------
# Tests for create_parent_child_chunks_semantic with breadcrumbs
# ---------------------------------------------------------------------------

class TestCreateParentChildChunksSemanticBreadcrumbs:
    def _mock_embed_fn(self):
        topic_vectors = {
            "The cat sat on the mat.": [1.0, 0.0, 0.0],
            "It was a fluffy cat.": [0.8, 0.5, 0.3],
            "The cat liked to nap.": [0.6, 0.3, 0.7],
            "Quantum physics is complex.": [0.0, 1.0, 0.0],
            "Particles behave as waves.": [0.0, 0.9, 0.1],
            "The observer effect is real.": [0.0, 1.0, 0.1],
        }

        async def embed_fn(texts):
            return [topic_vectors.get(t, [0.5, 0.5, 0.0]) for t in texts]

        return embed_fn

    def test_returns_parents_and_children(self):
        embed_fn = self._mock_embed_fn()
        text = (
            "The cat sat on the mat. It was a fluffy cat. The cat liked to nap. "
            "Quantum physics is complex. Particles behave as waves. The observer effect is real."
        )
        result = asyncio.run(
            create_parent_child_chunks_semantic(text, embed_fn=embed_fn, threshold=0.5)
        )
        assert "parents" in result
        assert "children" in result
        assert len(result["parents"]) >= 1
        assert len(result["children"]) >= 1

    def test_children_reference_valid_parent_ids(self):
        embed_fn = self._mock_embed_fn()
        text = (
            "The cat sat on the mat. It was a fluffy cat. "
            "Quantum physics is complex. Particles behave as waves."
        )
        result = asyncio.run(
            create_parent_child_chunks_semantic(text, embed_fn=embed_fn, threshold=0.5)
        )
        parent_ids = {p["id"] for p in result["parents"]}
        for child in result["children"]:
            assert child["parent_id"] in parent_ids

    def test_empty_text_returns_empty(self):
        async def embed_fn(texts):
            return [[0.0] * 3 for _ in texts]

        result = asyncio.run(
            create_parent_child_chunks_semantic("", embed_fn=embed_fn)
        )
        assert result == {"parents": [], "children": []}

    def test_doc_title_appears_in_semantic_chunks(self):
        """doc_title should be prepended to semantic parent and child chunks."""
        embed_fn = self._mock_embed_fn()
        text = (
            "The cat sat on the mat. It was a fluffy cat. The cat liked to nap. "
            "Quantum physics is complex. Particles behave as waves. The observer effect is real."
        )
        result = asyncio.run(
            create_parent_child_chunks_semantic(
                text, embed_fn=embed_fn, threshold=0.5, doc_title="Animal Science",
            )
        )
        for parent in result["parents"]:
            assert parent["text"].startswith("Animal Science"), (
                f"Expected breadcrumb in parent: {parent['text'][:60]}"
            )
        for child in result["children"]:
            assert child["text"].startswith("Animal Science"), (
                f"Expected breadcrumb in child: {child['text'][:60]}"
            )


# ---------------------------------------------------------------------------
# Integration: chunk_text_structured still works independently
# ---------------------------------------------------------------------------

class TestChunkTextStructuredStillWorks:
    def test_returns_chunk_results(self):
        text = "# Heading\nSome content here.\n## Sub\nMore content."
        results = chunk_text_structured(text, chunk_size=200, overlap=20)
        assert len(results) >= 1
        # Verify headings are captured
        headings = [r.metadata.heading for r in results]
        assert any(h != "" for h in headings), f"Expected at least one heading, got {headings}"

    def test_empty_text_returns_empty(self):
        assert chunk_text_structured("") == []
