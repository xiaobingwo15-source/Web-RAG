import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services import embeddings


def settings_for(provider: str = "gemini", dimension: int = 768) -> SimpleNamespace:
    return SimpleNamespace(
        get_embedding_provider=provider,
        get_google_api_key="google-key",
        get_embedding_model="gemini-embedding-001",
        get_embedding_dimension=dimension,
        get_local_embedding_model="intfloat/multilingual-e5-base",
        get_local_embedding_device="cpu",
    )


class FakeEmbedding:
    def __init__(self, values):
        self.values = values


class FakeEmbeddingModels:
    def __init__(self):
        self.calls = []

    async def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        contents = kwargs["contents"]
        count = 1 if isinstance(contents, str) else len(contents)
        return SimpleNamespace(
            embeddings=[FakeEmbedding([0.0] * 768) for _ in range(count)]
        )


class FakeGeminiClient:
    def __init__(self):
        self.aio = SimpleNamespace(models=FakeEmbeddingModels())


class FakeRateLimitedEmbeddingModels:
    def __init__(self):
        self.calls = []
        self.failed_once = False

    async def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        contents = kwargs["contents"]
        if isinstance(contents, list) and len(contents) == 5 and not self.failed_once:
            self.failed_once = True
            raise RuntimeError("429 RESOURCE_EXHAUSTED. {'details': [{'retryDelay': '29s'}]}")
        count = 1 if isinstance(contents, str) else len(contents)
        return SimpleNamespace(
            embeddings=[FakeEmbedding([0.0] * 768) for _ in range(count)]
        )


class EmbeddingProviderSelectionTests(unittest.TestCase):
    def tearDown(self):
        embeddings._embedding_client = None
        embeddings._embedding_client_key = None

    def test_gemini_provider_uses_google_client(self):
        with (
            patch.object(embeddings, "Settings", return_value=settings_for("gemini")),
            patch.object(embeddings.genai, "Client") as client_cls,
        ):
            embeddings.get_embedding_client()

        client_cls.assert_called_once_with(api_key="google-key")

    def test_gemini_provider_rebuilds_client_when_google_api_key_changes(self):
        first = settings_for("gemini")
        second = settings_for("gemini")
        second.get_google_api_key = "rotated-google-key"

        with (
            patch.object(embeddings, "Settings", side_effect=[first, second]),
            patch.object(
                embeddings.genai,
                "Client",
                side_effect=lambda api_key: {"api_key": api_key},
            ) as client_cls,
        ):
            client_one = embeddings.get_embedding_client()
            client_two = embeddings.get_embedding_client()

        self.assertEqual(client_one["api_key"], "google-key")
        self.assertEqual(client_two["api_key"], "rotated-google-key")
        self.assertEqual(client_cls.call_count, 2)

    def test_local_provider_uses_sentence_transformers_adapter(self):
        with patch.object(
            embeddings,
            "Settings",
            return_value=settings_for("local_sentence_transformers"),
        ):
            client = embeddings.get_embedding_client()

        self.assertIsInstance(client, embeddings.LocalSentenceTransformersClient)
        self.assertEqual(client.model_name, "intfloat/multilingual-e5-base")
        self.assertEqual(client.device, "cpu")


class GeminiEmbeddingTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_embedding_uses_retrieval_query_task_type(self):
        client = FakeGeminiClient()

        with patch.object(embeddings, "Settings", return_value=settings_for()):
            await embeddings.get_embedding(client, "question")

        self.assertEqual(
            client.aio.models.calls[0]["config"]["task_type"],
            "RETRIEVAL_QUERY",
        )

    async def test_document_embeddings_use_retrieval_document_task_type(self):
        client = FakeGeminiClient()

        with patch.object(embeddings, "Settings", return_value=settings_for()):
            await embeddings.get_embeddings(client, ["chunk one", "chunk two"])

        self.assertEqual(
            client.aio.models.calls[0]["config"]["task_type"],
            "RETRIEVAL_DOCUMENT",
        )

    async def test_document_embeddings_are_split_at_gemini_batch_limit(self):
        client = FakeGeminiClient()
        texts = [f"chunk {index}" for index in range(205)]

        with patch.object(embeddings, "Settings", return_value=settings_for()):
            vectors = await embeddings.get_embeddings(client, texts)

        self.assertEqual(len(vectors), 205)
        self.assertEqual(
            [len(call["contents"]) for call in client.aio.models.calls],
            [100, 100, 5],
        )
        self.assertTrue(
            all(call["config"]["task_type"] == "RETRIEVAL_DOCUMENT" for call in client.aio.models.calls)
        )

    async def test_document_embedding_batch_retries_with_gemini_retry_delay(self):
        client = SimpleNamespace(aio=SimpleNamespace(models=FakeRateLimitedEmbeddingModels()))
        texts = [f"chunk {index}" for index in range(105)]

        with (
            patch.object(embeddings, "Settings", return_value=settings_for()),
            patch.object(embeddings.asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            vectors = await embeddings.get_embeddings(client, texts)

        self.assertEqual(len(vectors), 105)
        self.assertEqual(
            [len(call["contents"]) for call in client.aio.models.calls],
            [100, 5, 5],
        )
        sleep.assert_awaited_once_with(29.0)


class LocalEmbeddingTests(unittest.IsolatedAsyncioTestCase):
    async def test_e5_query_and_document_prefixes_are_applied(self):
        client = embeddings.LocalSentenceTransformersClient(
            model_name="intfloat/multilingual-e5-base",
            device="cpu",
        )
        captured_texts = []

        def fake_encode(texts):
            captured_texts.extend(texts)
            return [[1.0] + [0.0] * 767 for _ in texts]

        client.encode = fake_encode

        with patch.object(
            embeddings,
            "Settings",
            return_value=settings_for("local_sentence_transformers"),
        ):
            await embeddings.get_embedding(client, "how many tables?")
            await embeddings.get_embeddings(client, ["table chunk"])

        self.assertEqual(
            captured_texts,
            ["query: how many tables?", "passage: table chunk"],
        )

    async def test_dimension_mismatch_fails_before_insert(self):
        client = embeddings.LocalSentenceTransformersClient(
            model_name="intfloat/multilingual-e5-base",
            device="cpu",
        )
        client.encode = lambda texts: [[1.0, 0.0, 0.0]]

        with (
            patch.object(
                embeddings,
                "Settings",
                return_value=settings_for("local_sentence_transformers", dimension=768),
            ),
            self.assertRaisesRegex(RuntimeError, "Embedding dimension mismatch"),
        ):
            await embeddings.get_embedding(client, "short vector")


if __name__ == "__main__":
    unittest.main()
