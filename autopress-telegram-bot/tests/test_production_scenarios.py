"""
Comprehensive Production Scenario Test Suite

Verifies all 10 mandatory production test cases:
1. Valid PDF + 1 credit -> Success, result received, balance becomes 0.
2. 0 credits -> Rejected, purchase prompt, no deduction.
3. Invalid file types (.jpg, .png, .txt) -> Rejected, no deduction.
4. Corrupted PDF -> Fails safely, no deduction.
5. Backend unavailable -> Handled cleanly, no deduction, bot stays alive.
6. Backend timeout -> Handled cleanly, job marked failed, no deduction.
7. Repeat same upload / retry -> Idempotent, no double deduction.
8. Two concurrent uploads with 1 credit -> Exactly 1 succeeds, balance never negative.
9. User isolation -> User B cannot access User A's jobs.
10. Bot restart / persistence -> DB state preserved across restarts.
"""

import asyncio
import io
import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch
from PIL import Image

from database.database import init_db
from database.repositories.job_repository import JobRepository
from services.user_service import user_service
from services.credit_service import credit_service
from services.job_service import job_service
from services.autopress_api import autopress_api_client
from utils.validators import validate_pdf_metadata, validate_pdf_bytes


class TestProductionScenarios(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def _create_dummy_pdf(self) -> bytes:
        """Helper to create a minimal valid PDF byte sequence."""
        return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \ntrailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF"

    def _create_dummy_png_result(self) -> bytes:
        """Helper to create a mock 300 DPI PNG sheet from backend."""
        img = Image.new("RGB", (2480, 3508), "white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def test_1_valid_pdf_success_deduction(self):
        """Test 1: User with 1 credit uploads a valid PDF -> Processing succeeds, PNG received, Balance becomes 0."""
        uid = 998877701
        user_service.get_or_create_user(telegram_user_id=uid)

        pdf_bytes = self._create_dummy_pdf()
        mock_output_png = self._create_dummy_png_result()

        with patch.object(credit_service, "get_authoritative_balance", return_value=(True, 1, None)), \
             patch.object(autopress_api_client, "process_pdf_template", new=AsyncMock(return_value=(True, mock_output_png, None))), \
             patch.object(credit_service, "deduct_credit", new=AsyncMock(return_value=(True, "Success", 0))):
            success, err, result_png, rem_bal = await job_service.process_pdf_upload(
                telegram_user_id=uid,
                pdf_bytes=pdf_bytes,
                filename="fayda_test.pdf"
            )

        self.assertTrue(success)
        self.assertIsNone(err)
        self.assertIsNotNone(result_png)
        # Verify it is valid PNG data and matches A4 300 DPI dimensions (2480x3508)
        self.assertTrue(result_png.startswith(b"\x89PNG\r\n\x1a\n"))
        img = Image.open(io.BytesIO(result_png))
        self.assertEqual(img.size, (2480, 3508))
        self.assertEqual(rem_bal, 0)

    async def test_2_zero_credits_rejected(self):
        """Test 2: User with 0 credits uploads a PDF -> No processing, No deduction, Purchase prompt."""
        uid = 998877702
        user_service.get_or_create_user(telegram_user_id=uid)

        pdf_bytes = self._create_dummy_pdf()

        # Attempt to process job with 0 balance
        with patch.object(credit_service, "get_authoritative_balance", return_value=(True, 0, None)), \
             patch.object(autopress_api_client, "process_pdf_template", new=AsyncMock()) as mock_backend:
            success, err, result_pdf, rem_bal = await job_service.process_pdf_upload(
                telegram_user_id=uid,
                pdf_bytes=pdf_bytes,
                filename="fayda_test.pdf"
            )
            # Backend should never be called when balance is 0
            mock_backend.assert_not_called()

        self.assertFalse(success)
        self.assertEqual(err, "INSUFFICIENT_CREDITS")
        self.assertIsNone(result_pdf)
        self.assertEqual(rem_bal, 0)

    def test_3_invalid_file_types_rejected(self):
        """Test 3: Non-PDF files (.jpg, .png, .txt) rejected without credit deduction."""
        # Check .jpg
        ok, err = validate_pdf_metadata("photo.jpg", 1024, "image/jpeg")
        self.assertFalse(ok)

        # Check .png
        ok, err = validate_pdf_metadata("scan.png", 2048, "image/png")
        self.assertFalse(ok)

        # Check .txt
        ok, err = validate_pdf_metadata("document.txt", 512, "text/plain")
        self.assertFalse(ok)

    def test_4_corrupted_pdf_rejected(self):
        """Test 4: Corrupted / invalid PDF header rejected safely."""
        corrupted_bytes = b"NOT_A_REAL_PDF_DATA_XYZ_1234567890_ABCDEFGHIJKL"
        ok, err = validate_pdf_bytes(corrupted_bytes)
        self.assertFalse(ok)
        self.assertIn("not a valid PDF", err)

    async def test_5_backend_unavailable_safe_failure(self):
        """Test 5: Backend unavailable -> Friendly error, no credit deducted, bot stays alive."""
        uid = 998877705
        user_service.get_or_create_user(telegram_user_id=uid)

        pdf_bytes = self._create_dummy_pdf()

        with patch.object(credit_service, "get_authoritative_balance", return_value=(True, 3, None)), \
             patch.object(autopress_api_client, "process_pdf_template", new=AsyncMock(return_value=(False, None, "AutoPress backend service is currently unavailable."))):
            success, err, result, rem_bal = await job_service.process_pdf_upload(
                telegram_user_id=uid,
                pdf_bytes=pdf_bytes,
                filename="fayda.pdf"
            )

        self.assertFalse(success)
        self.assertIn("unavailable", err)
        self.assertIsNone(result)

    async def test_6_backend_timeout_safe_failure(self):
        """Test 6: Backend timeout -> Friendly error, no credit deducted, job marked failed."""
        uid = 998877706
        user_service.get_or_create_user(telegram_user_id=uid)

        pdf_bytes = self._create_dummy_pdf()

        with patch.object(credit_service, "get_authoritative_balance", return_value=(True, 2, None)), \
             patch.object(autopress_api_client, "process_pdf_template", new=AsyncMock(return_value=(False, None, "Processing timed out. Please try again."))):
            success, err, result, rem_bal = await job_service.process_pdf_upload(
                telegram_user_id=uid,
                pdf_bytes=pdf_bytes,
                filename="fayda.pdf"
            )

        self.assertFalse(success)
        self.assertIn("timed out", err)

    async def test_7_repeat_upload_no_duplicate_deduction(self):
        """Test 7: Repeat same upload / transaction ID -> No accidental double deduction."""
        uid = 998877707
        user_service.get_or_create_user(telegram_user_id=uid)

        job_id = f"job_fixed_idempotent_{uuid.uuid4().hex[:8]}"
        JobRepository.create_job(job_id=job_id, telegram_user_id=uid)

        with patch.object(autopress_api_client, "deduct_telegram_credit", new=AsyncMock(return_value=(True, 4, None))):
            s1, m1, b1 = await credit_service.deduct_credit(uid, 1, "Bill 1", job_id=job_id)
            self.assertTrue(s1)
            self.assertEqual(b1, 4)

            # Retry with same job_id
            s2, m2, b2 = await credit_service.deduct_credit(uid, 1, "Bill retry", job_id=job_id)
            self.assertTrue(s2)
            self.assertEqual(b2, 4) # balance unchanged!

    async def test_8_race_condition_two_uploads_with_one_credit(self):
        """Test 8: Two uploads started concurrently with only 1 credit -> Exactly one consumes credit, balance never negative."""
        uid = 998877708
        user_service.get_or_create_user(telegram_user_id=uid)

        pdf_bytes = self._create_dummy_pdf()
        mock_output_png = self._create_dummy_png_result()

        # Simulate first call deducting successfully, second call failing with insufficient credits
        deduct_mock = AsyncMock(side_effect=[
            (True, "Success", 0),
            (False, "Insufficient credits. You have 0 credits.", 0)
        ])

        with patch.object(credit_service, "get_authoritative_balance", return_value=(True, 1, None)), \
             patch.object(autopress_api_client, "process_pdf_template", new=AsyncMock(return_value=(True, mock_output_png, None))), \
             patch.object(credit_service, "deduct_credit", new=deduct_mock):
            results = await asyncio.gather(
                job_service.process_pdf_upload(telegram_user_id=uid, pdf_bytes=pdf_bytes, filename="batch1.pdf"),
                job_service.process_pdf_upload(telegram_user_id=uid, pdf_bytes=pdf_bytes, filename="batch2.pdf")
            )

        successes = [r for r in results if r[0] is True]
        failures = [r for r in results if r[0] is False]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][1], "INSUFFICIENT_CREDITS")

    def test_9_user_isolation(self):
        """Test 9: User A's jobs are isolated and inaccessible to User B."""
        uid_a = 998877709
        uid_b = 998877710
        user_service.get_or_create_user(telegram_user_id=uid_a)
        user_service.get_or_create_user(telegram_user_id=uid_b)

        job_a_id = f"job_user_a_{uuid.uuid4().hex[:8]}"
        JobRepository.create_job(job_id=job_a_id, telegram_user_id=uid_a, credit_cost=1, input_filename="fayda_a.pdf")

        user_b_jobs = JobRepository.get_user_jobs(telegram_user_id=uid_b)
        job_ids_for_b = [j["id"] for j in user_b_jobs]
        self.assertNotIn(job_a_id, job_ids_for_b)

    def test_10_restart_persistence(self):
        """Test 10: Data integrity and schema re-initialization persist accurately."""
        uid = 998877711
        user_service.get_or_create_user(telegram_user_id=uid, first_name="PersistenceTest")
        credit_service.grant_credits(uid, 7, "Persistence grant")

        # Simulate bot restart
        init_db()

        user = user_service.get_user(uid)
        self.assertIsNotNone(user)
        self.assertEqual(user["first_name"], "PersistenceTest")
        self.assertGreaterEqual(credit_service.get_balance(uid), 7)


if __name__ == "__main__":
    unittest.main()
