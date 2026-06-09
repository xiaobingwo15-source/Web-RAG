import unittest

from app.services.agents.doc_rag_agent import lost_in_the_middle_reorder


class LostInMiddleReorderTests(unittest.TestCase):
    """Tests for the Lost-in-the-Middle chunk reordering strategy."""

    def test_empty_chunks(self):
        """Empty input returns empty output."""
        chunks, sources = lost_in_the_middle_reorder([], [])
        self.assertEqual(chunks, [])
        self.assertEqual(sources, [])

    def test_single_chunk_unchanged(self):
        """Single chunk is returned as-is."""
        chunks = ["chunk A"]
        sources = [{"score": 0.9, "id": "a"}]
        out_chunks, out_sources = lost_in_the_middle_reorder(chunks, sources)
        self.assertEqual(out_chunks, ["chunk A"])
        self.assertEqual(out_sources, [{"score": 0.9, "id": "a"}])

    def test_two_chunks_unchanged(self):
        """Two chunks are returned as-is (no benefit from reordering)."""
        chunks = ["chunk A", "chunk B"]
        sources = [{"score": 0.9, "id": "a"}, {"score": 0.8, "id": "b"}]
        out_chunks, out_sources = lost_in_the_middle_reorder(chunks, sources)
        self.assertEqual(out_chunks, ["chunk A", "chunk B"])
        self.assertEqual(out_sources, sources)

    def test_three_chunks_interleaved(self):
        """Three chunks: best at front, 2nd-best at end, 3rd in middle."""
        chunks = ["chunk A", "chunk B", "chunk C"]
        sources = [
            {"score": 0.9, "id": "a"},  # best
            {"score": 0.8, "id": "b"},  # 2nd
            {"score": 0.7, "id": "c"},  # 3rd
        ]
        out_chunks, out_sources = lost_in_the_middle_reorder(chunks, sources)
        # Expected: [best, 3rd, 2nd-best] = [A, C, B]
        self.assertEqual(out_chunks, ["chunk A", "chunk C", "chunk B"])
        self.assertEqual(out_sources[0]["id"], "a")  # best at front
        self.assertEqual(out_sources[-1]["id"], "b")  # 2nd-best at end
        self.assertEqual(out_sources[1]["id"], "c")  # 3rd in middle

    def test_five_chunks_full_interleave(self):
        """Five chunks with descending scores get properly interleaved."""
        chunks = [f"chunk {c}" for c in "ABCDE"]
        sources = [
            {"score": 0.95, "id": "a"},  # 1st
            {"score": 0.85, "id": "b"},  # 2nd
            {"score": 0.75, "id": "c"},  # 3rd
            {"score": 0.65, "id": "d"},  # 4th
            {"score": 0.55, "id": "e"},  # 5th
        ]
        out_chunks, out_sources = lost_in_the_middle_reorder(chunks, sources)
        # Expected: [1st, 3rd, 4th, 5th, 2nd] = [A, C, D, E, B]
        self.assertEqual(out_chunks, ["chunk A", "chunk C", "chunk D", "chunk E", "chunk B"])
        self.assertEqual(out_sources[0]["id"], "a")   # best at front
        self.assertEqual(out_sources[-1]["id"], "b")   # 2nd-best at end
        self.assertEqual(out_sources[1]["id"], "c")    # 3rd in middle
        self.assertEqual(out_sources[2]["id"], "d")    # 4th in middle
        self.assertEqual(out_sources[3]["id"], "e")    # 5th in middle

    def test_unordered_scores_sorted_correctly(self):
        """Scores not in descending order are still handled correctly."""
        chunks = ["chunk A", "chunk B", "chunk C"]
        sources = [
            {"score": 0.5, "id": "a"},  # lowest
            {"score": 0.9, "id": "b"},  # highest
            {"score": 0.7, "id": "c"},  # middle
        ]
        out_chunks, out_sources = lost_in_the_middle_reorder(chunks, sources)
        # Sorted: [(b, 0.9), (c, 0.7), (a, 0.5)]
        # Interleave: [b, a, c] -> best at front, 2nd-best at end
        self.assertEqual(out_chunks, ["chunk B", "chunk A", "chunk C"])
        self.assertEqual(out_sources[0]["id"], "b")  # best at front
        self.assertEqual(out_sources[-1]["id"], "c")  # 2nd-best at end
        self.assertEqual(out_sources[1]["id"], "a")   # worst in middle

    def test_rerank_score_preferred(self):
        """rerank_score is preferred over score when both exist."""
        chunks = ["chunk A", "chunk B", "chunk C"]
        sources = [
            {"score": 0.3, "rerank_score": 0.9, "id": "a"},  # high rerank
            {"score": 0.9, "rerank_score": 0.5, "id": "b"},  # low rerank
            {"score": 0.6, "rerank_score": 0.7, "id": "c"},  # mid rerank
        ]
        out_chunks, out_sources = lost_in_the_middle_reorder(chunks, sources)
        # Sorted by rerank_score desc: [(idx0=a, 0.9), (idx2=c, 0.7), (idx1=b, 0.5)]
        # Interleave: [idx0, idx1, idx2] = [a, b, c]
        self.assertEqual(out_chunks, ["chunk A", "chunk B", "chunk C"])
        self.assertEqual(out_sources[0]["id"], "a")  # best rerank at front
        self.assertEqual(out_sources[-1]["id"], "c")  # 2nd-best rerank at end

    def test_no_scores_falls_back_to_order(self):
        """When no score fields exist, original order is preserved with interleaving."""
        chunks = ["chunk A", "chunk B", "chunk C"]
        sources = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        out_chunks, out_sources = lost_in_the_middle_reorder(chunks, sources)
        # All scores are 0, stable sort preserves order: [(a, 0), (b, 0), (c, 0)]
        # Interleave: [a, c, b]
        self.assertEqual(out_chunks, ["chunk A", "chunk C", "chunk B"])
        self.assertEqual(out_sources[0]["id"], "a")
        self.assertEqual(out_sources[-1]["id"], "b")
        self.assertEqual(out_sources[1]["id"], "c")

    def test_empty_sources_handled(self):
        """Empty source dicts (from web search) don't crash the reorder."""
        chunks = ["chunk A", "chunk B", "chunk C"]
        sources = [{}, {}, {"score": 0.9}]
        out_chunks, out_sources = lost_in_the_middle_reorder(chunks, sources)
        # Sorted by score desc: [(idx2, 0.9), (idx0, 0), (idx1, 0)]
        # Interleave: [idx2, idx1, idx0] = [C, B, A]
        self.assertEqual(out_chunks, ["chunk C", "chunk B", "chunk A"])
        # Best (score=0.9) at front, 2nd-best (score=0, idx0) at end
        self.assertEqual(out_sources[0], {"score": 0.9})
        self.assertEqual(out_sources[-1], {})

    def test_alignment_preserved(self):
        """Chunks and sources stay aligned 1:1 after reordering."""
        chunks = [f"content_{i}" for i in range(6)]
        sources = [{"score": 1.0 - i * 0.1, "id": f"src_{i}"} for i in range(6)]
        out_chunks, out_sources = lost_in_the_middle_reorder(chunks, sources)
        # Verify alignment: each chunk matches its source
        for chunk, src in zip(out_chunks, out_sources):
            chunk_idx = chunk.split("_")[1]
            src_idx = src["id"].split("_")[1]
            self.assertEqual(chunk_idx, src_idx)

    def test_many_chunks(self):
        """Reorder works correctly with a larger number of chunks."""
        n = 10
        chunks = [f"chunk {i}" for i in range(n)]
        sources = [{"score": 1.0 - i * 0.05, "id": str(i)} for i in range(n)]
        out_chunks, out_sources = lost_in_the_middle_reorder(chunks, sources)
        self.assertEqual(len(out_chunks), n)
        self.assertEqual(len(out_sources), n)
        # Best at front, 2nd-best at end
        self.assertEqual(out_sources[0]["id"], "0")  # highest score
        self.assertEqual(out_sources[-1]["id"], "1")  # 2nd highest score
        # All IDs present
        self.assertEqual(set(s["id"] for s in out_sources), set(str(i) for i in range(n)))


if __name__ == "__main__":
    unittest.main()
