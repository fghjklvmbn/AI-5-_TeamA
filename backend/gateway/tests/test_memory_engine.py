import tempfile
import unittest
from pathlib import Path

from memorypal_api.database import Database
from memorypal_api.services.memory_engine import MemoryCandidate, MemoryEngine


class MemoryEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "memorypal.db")
        self.db.initialize()
        self.user = self.db.create_user("one@example.com", "하나", "hash", "salt")
        self.other = self.db.create_user("two@example.com", "둘", "hash", "salt")
        self.session = self.db.create_session(self.user["id"])
        self.engine = MemoryEngine(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_rule_extraction_and_deduplication(self):
        candidates = self.engine.extract_rule_candidates("나는 따뜻한 라테를 좋아해. 기억해줘")
        self.assertTrue(any(item.memory_type == "preference" for item in candidates))
        self.engine.remember_many(self.user["id"], self.session["id"], candidates)
        self.engine.remember_many(self.user["id"], self.session["id"], candidates)
        normalized = {row["normalized_content"] for row in self.db.list_memories(self.user["id"])}
        self.assertEqual(len(normalized), len(self.db.list_memories(self.user["id"])))

    def test_retrieval_is_relevant_and_user_isolated(self):
        self.engine.remember(
            self.user["id"],
            self.session["id"],
            MemoryCandidate("preference", "나는 산책할 때 재즈를 듣는 걸 좋아해", 0.95, 0.8),
        )
        self.engine.remember(
            self.user["id"],
            self.session["id"],
            MemoryCandidate("schedule", "다음 주 화요일에 치과 예약이 있어", 0.9, 0.9),
        )
        result = self.engine.retrieve(self.user["id"], "산책할 때 들을 음악 추천해줘", limit=1)
        self.assertIn("재즈", result[0]["content"])
        self.assertEqual(self.engine.retrieve(self.other["id"], "산책", limit=5), [])

    def test_sensitive_information_is_not_stored(self):
        result = self.engine.remember(
            self.user["id"],
            self.session["id"],
            MemoryCandidate("fact", "내 비밀번호는 super-secret-1234야", 1.0, 1.0),
        )
        self.assertIsNone(result)
        self.assertEqual(self.db.list_memories(self.user["id"]), [])


if __name__ == "__main__":
    unittest.main()
