import unittest

from app.services.document_enrichment import emphasize_document_text


class DocumentEnrichmentTests(unittest.TestCase):
    def test_adds_metadata_importance_header(self):
        text = "Available Colors\nBlack Stainless Steel"
        metadata = {
            "title": "RF28R7351SR Refrigerator",
            "summary": "Food showcase refrigerator product details.",
            "tags": ["refrigerator", "food showcase", "stainless steel"],
        }

        enriched = emphasize_document_text(text, metadata)

        self.assertIn("# **RF28R7351SR Refrigerator**", enriched)
        self.assertIn("**Keywords:** **refrigerator**, **food showcase**, **stainless steel**", enriched)
        self.assertIn("**Summary:** Food showcase refrigerator product details.", enriched)

    def test_bolds_heading_like_lines_without_bolding_sentences(self):
        text = "\n".join([
            "Signature Features",
            "Provides quick access to everyday items while maintaining",
            "the temperature.",
            "Black Stainless Steel",
        ])

        enriched = emphasize_document_text(text)

        self.assertIn("**Signature Features**", enriched)
        self.assertIn("Provides quick access to everyday items while maintaining", enriched)
        self.assertNotIn("**Provides quick access", enriched)
        self.assertIn("**Black Stainless Steel**", enriched)


if __name__ == "__main__":
    unittest.main()
