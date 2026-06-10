import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.config import DEFAULT_OCR_MODEL, Settings
from app.services import gemini


class ModelProviderTests(unittest.TestCase):
    def tearDown(self):
        gemini._llm_clients.clear()

    def test_openrouter_provider_uses_openrouter_base_and_models(self):
        settings = SimpleNamespace(
            get_model_provider="openrouter",
            get_openrouter_api_key="openrouter-key",
            get_openrouter_model="openrouter-primary",
            get_openrouter_fallback_model="openrouter-fallback",
            frontend_url="http://localhost:5173",
        )

        with (
            patch.object(gemini, "Settings", return_value=settings),
            patch.object(gemini, "AsyncOpenAI") as client_cls,
        ):
            gemini.get_llm_client()
            models = gemini._models_to_try()

        client_cls.assert_called_once()
        kwargs = client_cls.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "openrouter-key")
        self.assertEqual(kwargs["base_url"], gemini.OPENROUTER_BASE_URL)
        self.assertEqual(models, ["openrouter-primary", "openrouter-fallback"])

    def test_mistral_provider_uses_mistral_base_and_single_model(self):
        settings = SimpleNamespace(
            get_model_provider="mistral",
            get_mistral_api_key="mistral-key",
            get_mistral_model="mistral-large-latest",
        )

        with (
            patch.object(gemini, "Settings", return_value=settings),
            patch.object(gemini, "AsyncOpenAI") as client_cls,
        ):
            gemini.get_llm_client()
            models = gemini._models_to_try()

        client_cls.assert_called_once()
        kwargs = client_cls.call_args.kwargs
        self.assertEqual(kwargs["api_key"], "mistral-key")
        self.assertEqual(kwargs["base_url"], gemini.MISTRAL_BASE_URL)
        self.assertNotIn("default_headers", kwargs)
        self.assertEqual(models, ["mistral-large-latest"])

    def test_missing_mistral_key_fails_clearly(self):
        settings = SimpleNamespace(
            get_model_provider="mistral",
            get_mistral_api_key="",
            get_mistral_model="mistral-large-latest",
        )

        with patch.object(gemini, "Settings", return_value=settings):
            with self.assertRaisesRegex(RuntimeError, "MISTRAL_API_KEY"):
                gemini.get_llm_client()


class OcrModelConfigTests(unittest.TestCase):
    def test_legacy_ocr_model_aliases_to_current_default(self):
        with patch.object(Settings, "_get_db_setting", return_value=None):
            settings = Settings(ocr_model="google/gemini-2.0-flash-001")

            self.assertEqual(settings.get_ocr_model, DEFAULT_OCR_MODEL)

    def test_db_ocr_model_aliases_to_current_default(self):
        with patch.object(Settings, "_get_db_setting", return_value="google/gemini-2.0-flash-001"):
            settings = Settings(ocr_model="other/model")

            self.assertEqual(settings.get_ocr_model, DEFAULT_OCR_MODEL)


class FakeDelta:
    content = "hello"


class FakeChoice:
    delta = FakeDelta()


class FakeChunk:
    choices = [FakeChoice()]


class FakeStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        if getattr(self, "_used", False):
            raise StopAsyncIteration
        self._used = True
        return FakeChunk()


class FakeCompletions:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return FakeStream()


class FakeChat:
    def __init__(self):
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self):
        self.chat = FakeChat()


class MistralStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_uses_mistral_model_and_preserves_tokens(self):
        settings = SimpleNamespace(
            get_model_provider="mistral",
            get_mistral_model="mistral-large-latest",
        )
        client = FakeClient()

        with (
            patch.object(gemini, "Settings", return_value=settings),
            patch.object(gemini, "get_client", return_value=SimpleNamespace(update_current_generation=lambda **_: None)),
        ):
            chunks = [
                chunk
                async for chunk in gemini.generate_chat_response_stream(
                    client,
                    "hello",
                    history=[],
                )
            ]

        self.assertEqual(chunks, ["hello"])
        self.assertEqual(client.chat.completions.kwargs["model"], "mistral-large-latest")
        self.assertTrue(client.chat.completions.kwargs["stream"])


if __name__ == "__main__":
    unittest.main()
