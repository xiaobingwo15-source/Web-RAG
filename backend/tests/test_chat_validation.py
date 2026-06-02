import unittest
from pydantic import ValidationError

from app.models.chat import ChatRequest


class ChatValidationTests(unittest.TestCase):
    def test_rejects_invalid_retrieval_mode(self):
        with self.assertRaises(ValidationError):
            ChatRequest(message="hello", retrieval_mode="invalid")

    def test_rejects_non_image_data_urls(self):
        with self.assertRaises(ValidationError):
            ChatRequest(message="hello", images=["data:text/plain;base64,abc"])


if __name__ == "__main__":
    unittest.main()
