import unittest
import uuid
from database.database import init_db
from database.repositories.job_repository import JobRepository
from services.user_service import user_service


class TestJobs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_job_lifecycle(self):
        """Verify job creation and state transitions."""
        uid = 998877665
        user_service.get_or_create_user(telegram_user_id=uid)

        job_id = f"job_test_{uuid.uuid4().hex[:8]}"
        job = JobRepository.create_job(job_id=job_id, telegram_user_id=uid, credit_cost=1, input_filename="fayda.pdf")
        self.assertEqual(job["status"], "PENDING")

        JobRepository.update_status(job_id, "PROCESSING")
        job = JobRepository.get_job(job_id)
        self.assertEqual(job["status"], "PROCESSING")

        JobRepository.update_status(job_id, "COMPLETED")
        job = JobRepository.get_job(job_id)
        self.assertEqual(job["status"], "COMPLETED")
        self.assertIsNotNone(job["completed_at"])


if __name__ == "__main__":
    unittest.main()
