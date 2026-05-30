import unittest

from app.services.gemini import ImportanceMarkerStripper, strip_importance_markers


class GeminiFormattingTests(unittest.TestCase):
    def test_strips_importance_markers_from_full_text(self):
        self.assertEqual(
            strip_importance_markers("The **RF28R7351SR** has **Food Showcase Door**."),
            "The RF28R7351SR has Food Showcase Door.",
        )

    def test_strips_importance_markers_across_stream_chunks(self):
        stripper = ImportanceMarkerStripper()

        output = "".join([
            stripper.feed("The *"),
            stripper.feed("*RF28R7351SR"),
            stripper.feed("** has value."),
            stripper.flush(),
        ])

        self.assertEqual(output, "The RF28R7351SR has value.")


if __name__ == "__main__":
    unittest.main()
