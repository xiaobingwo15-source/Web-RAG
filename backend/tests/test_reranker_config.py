import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services import reranker


class RerankerConfigTests(unittest.TestCase):
    def test_cohere_client_uses_settings_key(self):
        with (
            patch.object(
                reranker,
                "Settings",
                return_value=SimpleNamespace(get_cohere_api_key="cohere-from-settings"),
                create=True,
            ),
            patch.object(reranker.cohere, "ClientV2") as client_cls,
        ):
            reranker._get_cohere_client()

        client_cls.assert_called_once_with(api_key="cohere-from-settings")


if __name__ == "__main__":
    unittest.main()
