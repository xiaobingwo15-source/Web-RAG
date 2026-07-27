import unittest

from app.services.agents.doc_rag_agent import (
    CLARIFICATION_PROMPT,
    CORRECTIVE_RAG_SYSTEM_PROMPT,
    HYBRID_SYSTEM_PROMPT,
    META_CLARIFICATION_PROMPT,
)
from app.services.gemini import (
    CLIENT_RESPONSE_LANGUAGE_POLICY,
    RAG_SYSTEM_PROMPT,
    _build_messages,
)


class RagResponseLanguagePolicyTests(unittest.TestCase):
    def test_all_document_response_prompts_share_english_only_policy(self):
        prompts = {
            "rag": RAG_SYSTEM_PROMPT,
            "corrective_rag": CORRECTIVE_RAG_SYSTEM_PROMPT,
            "hybrid": HYBRID_SYSTEM_PROMPT,
            "clarification": CLARIFICATION_PROMPT,
            "meta_clarification": META_CLARIFICATION_PROMPT,
        }

        for name, prompt in prompts.items():
            with self.subTest(prompt=name):
                self.assertIn(CLIENT_RESPONSE_LANGUAGE_POLICY, prompt)
                self.assertIn(
                    "Always write the complete client-facing response in English",
                    prompt,
                )
                self.assertNotIn("Match the user's language", prompt)
                self.assertNotIn("answer using the available source language", prompt)

    def test_multilingual_source_text_is_preserved_for_english_answer_generation(self):
        chinese_source = "退款申请必须在购买后的十四天内提交。"
        malay_question = "Berapa lama tempoh untuk memohon bayaran balik?"

        messages = _build_messages(
            malay_question,
            history=[],
            context_chunks=[chinese_source],
            system_prompt=RAG_SYSTEM_PROMPT,
            context_sources=[{"filename": "退款政策.pdf", "page_start": 2}],
        )

        self.assertIn(CLIENT_RESPONSE_LANGUAGE_POLICY, messages[0]["content"])
        self.assertIn(chinese_source, messages[-1]["content"])
        self.assertIn(malay_question, messages[-1]["content"])
        self.assertIn("退款政策.pdf", messages[-1]["content"])

    def test_policy_distinguishes_source_facts_from_official_english_wording(self):
        self.assertIn(
            "Citations support facts found in the original-language source",
            CLIENT_RESPONSE_LANGUAGE_POLICY,
        )
        self.assertIn(
            "Do not imply that your English translation or paraphrase is official English wording",
            CLIENT_RESPONSE_LANGUAGE_POLICY,
        )


if __name__ == "__main__":
    unittest.main()
