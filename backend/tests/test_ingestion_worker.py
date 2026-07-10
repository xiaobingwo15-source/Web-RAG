import unittest
from unittest.mock import AsyncMock, call, patch

from app.services import ingestion_worker


class IngestionWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_marks_processing_and_forwards_parser_options(self):
        process_document = AsyncMock(return_value={"status": "processed", "chunk_count": 4})
        with (
            patch.object(ingestion_worker, "process_document", new=process_document),
            patch.object(ingestion_worker, "update_document_status") as update_status,
            patch.object(ingestion_worker.asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            await ingestion_worker.process_document_async(
                "token",
                "user-a",
                "doc-a",
                b"pdf-bytes",
                "application/pdf",
                use_ocr=True,
                pdf_parser_mode="layout",
                filename="manual.pdf",
                tenant_id="tenant-a",
            )

        update_status.assert_called_once_with("token", "doc-a", "processing")
        process_document.assert_awaited_once_with(
            "token",
            "user-a",
            "doc-a",
            b"pdf-bytes",
            "application/pdf",
            use_ocr=True,
            pdf_parser_mode="layout",
            filename="manual.pdf",
            tenant_id="tenant-a",
        )
        sleep.assert_not_awaited()

    async def test_transient_failure_retries_once_then_succeeds(self):
        process_document = AsyncMock(side_effect=[
            {"status": "failed", "error_message": "503 temporarily unavailable"},
            {"status": "processed", "chunk_count": 2},
        ])
        with (
            patch.object(ingestion_worker, "process_document", new=process_document),
            patch.object(ingestion_worker, "update_document_status") as update_status,
            patch.object(ingestion_worker.asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            await ingestion_worker.process_document_async(
                "token", "user-a", "doc-a", b"text", "text/plain"
            )

        self.assertEqual(process_document.await_count, 2)
        sleep.assert_awaited_once_with(ingestion_worker.RETRY_DELAY_SECONDS)
        self.assertEqual(
            update_status.call_args_list,
            [
                call("token", "doc-a", "processing"),
                call(
                    "token",
                    "doc-a",
                    "pending",
                    "Attempt 1 failed, retrying... (503 temporarily unavailable)",
                ),
            ],
        )

    async def test_exhausted_transient_retries_persist_final_error(self):
        process_document = AsyncMock(side_effect=[
            ConnectionError("connection reset"),
            TimeoutError("deadline exceeded"),
        ])
        with (
            patch.object(ingestion_worker, "process_document", new=process_document),
            patch.object(ingestion_worker, "update_document_status") as update_status,
            patch.object(ingestion_worker.asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            await ingestion_worker.process_document_async(
                "token", "user-a", "doc-a", b"text", "text/plain"
            )

        self.assertEqual(process_document.await_count, ingestion_worker.MAX_RETRIES)
        sleep.assert_awaited_once_with(ingestion_worker.RETRY_DELAY_SECONDS)
        self.assertEqual(update_status.call_args_list[-1], call("token", "doc-a", "failed", "deadline exceeded"))

    async def test_non_transient_failure_stops_without_retry(self):
        process_document = AsyncMock(return_value={
            "status": "failed",
            "error_message": "No text content extracted from file",
        })
        with (
            patch.object(ingestion_worker, "process_document", new=process_document),
            patch.object(ingestion_worker, "update_document_status") as update_status,
            patch.object(ingestion_worker.asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            await ingestion_worker.process_document_async(
                "token", "user-a", "doc-a", b"empty", "text/plain"
            )

        process_document.assert_awaited_once()
        sleep.assert_not_awaited()
        self.assertEqual(
            update_status.call_args_list,
            [
                call("token", "doc-a", "processing"),
                call("token", "doc-a", "failed", "No text content extracted from file"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
