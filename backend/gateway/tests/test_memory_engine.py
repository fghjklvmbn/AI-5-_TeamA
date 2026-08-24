import tempfile
import unittest
from pathlib import Path

from memorypal_api.database import Database
from memorypal_api.services.memory_engine import (
    MemoryCandidate,
    MemoryEngine,
    contains_sensitive_information,
)


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

    def test_memory_list_supports_literal_search_and_type_filter(self):
        self.engine.remember(
            self.user["id"], self.session["id"],
            MemoryCandidate("preference", "재즈 100% 음악을 좋아해", 0.95, 0.8),
        )
        self.engine.remember(
            self.user["id"], self.session["id"],
            MemoryCandidate("schedule", "금요일 재즈 공연 예약", 0.9, 0.9),
        )
        self.engine.remember(
            self.other["id"], None,
            MemoryCandidate("preference", "다른 사용자의 재즈 기억", 0.9, 0.9),
        )

        preference_rows = self.db.list_memories(
            self.user["id"], memory_type="preference", query="재즈",
        )
        self.assertEqual([row["memory_type"] for row in preference_rows], ["preference"])
        self.assertEqual(len(self.db.list_memories(self.user["id"], query="100%")), 1)
        self.assertEqual(self.db.list_memories(self.user["id"], query="다른 사용자"), [])

    def test_sensitive_information_is_not_stored(self):
        result = self.engine.remember(
            self.user["id"],
            self.session["id"],
            MemoryCandidate("fact", "내 비밀번호는 super-secret-1234야", 1.0, 1.0),
        )
        self.assertIsNone(result)
        self.assertEqual(self.db.list_memories(self.user["id"]), [])

    def test_unlabeled_identifiers_and_credentials_are_not_stored(self):
        sensitive_values = (
            "900101-1234568",
            "4111 1111 1111 1111",
            "010-1234-5678",
            "010\u200b-1234-5678",
            "+82 (10) 1234-5678",
            "private.person@example.com",
            (
                "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
                "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
            ),
            "sk-proj-N7pQ2vL9xR4mT8kW3cY6uH1sB5dF0aZ",
            "N7pQ2vL9xR4mT8kW3cY6uH1sB5dF0aZ",
            "N7pQ 2vL9 xR4m T8kW 3cY6 uH1s B5dF 0aZ9",
        )
        for value in sensitive_values:
            with self.subTest(value=value):
                self.assertTrue(contains_sensitive_information(value))
                result = self.engine.remember(
                    self.user["id"],
                    self.session["id"],
                    MemoryCandidate("fact", f"기억할 값은 {value}", 1.0, 1.0),
                )
                self.assertIsNone(result)
        self.assertEqual(self.db.list_memories(self.user["id"]), [])

    def test_normal_dates_and_short_numbers_are_not_false_positives(self):
        content = "회의는 8월 20일 오후 3시에 시작해"
        self.assertFalse(contains_sensitive_information(content))
        result = self.engine.remember(
            self.user["id"], self.session["id"], MemoryCandidate("schedule", content),
        )
        self.assertIsNotNone(result)

    def test_unrelated_high_importance_memory_is_completely_excluded(self):
        self.engine.remember(self.user["id"], self.session["id"], MemoryCandidate("schedule", "다음 주 화요일 치과 예약", 1.0, 1.0))
        result = self.engine.retrieve(self.user["id"], "파이썬 반복문을 설명해줘")
        self.assertEqual(result, [])
        self.assertEqual(self.engine.as_prompt(result), "")

    def test_memory_type_appears_when_user_asks_to_recall_it(self):
        self.engine.remember(self.user["id"], self.session["id"], MemoryCandidate("preference", "나는 따뜻한 라테를 좋아해", 0.9, 0.8))
        self.engine.remember(self.user["id"], self.session["id"], MemoryCandidate("schedule", "금요일 오후에 병원 예약", 0.9, 0.8))
        result = self.engine.retrieve(self.user["id"], "내가 좋아하는 음료가 뭐였지?")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["memory_type"], "preference")

    def test_related_question_can_use_memory_without_recall_phrase(self):
        self.engine.remember(self.user["id"], self.session["id"], MemoryCandidate("schedule", "금요일 오후에 치과 예약이 있어", 0.9, 0.8))
        result = self.engine.retrieve(self.user["id"], "치과 예약은 언제야?")
        self.assertEqual(len(result), 1)
        self.assertIn("금요일", result[0]["content"])

    def test_automatic_long_term_memory_requires_support_from_two_sessions(self):
        candidate = MemoryCandidate(
            "preference", "사용자는 따뜻한 라떼를 좋아해", 0.9, 0.8,
        )
        self.db.save_conversation(
            self.user["id"], self.session["id"], "나는 따뜻한 라떼를 좋아해", "알겠어요.",
        )

        self.assertEqual(
            self.engine.automatic_long_term_candidates(self.user["id"], [candidate]),
            [],
        )

        second_session = self.db.create_session(self.user["id"])
        self.db.save_conversation(
            self.user["id"], second_session["id"], "오늘도 따뜻한 라떼를 좋아해", "기억할게요.",
        )

        self.assertEqual(
            self.engine.automatic_long_term_candidates(self.user["id"], [candidate]),
            [candidate],
        )

    def test_automatic_long_term_memory_rejects_ephemeral_types_and_weak_scores(self):
        first = self.session
        second = self.db.create_session(self.user["id"])
        for session in (first, second):
            self.db.save_conversation(
                self.user["id"], session["id"], "금요일 오후에 치과 예약이 있어", "알겠어요.",
            )
        candidates = [
            MemoryCandidate("schedule", "금요일 오후 치과 예약", 1.0, 1.0),
            MemoryCandidate("preference", "사용자는 재즈를 좋아해", 0.7, 0.6),
        ]

        self.assertEqual(
            self.engine.automatic_long_term_candidates(self.user["id"], candidates),
            [],
        )


if __name__ == "__main__":
    unittest.main()
