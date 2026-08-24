from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

from ..database import Database
from .pipeline import ModelPipeline, PipelineUnavailable


logger = logging.getLogger(__name__)

EMOTION_RE = re.compile(
    r"(?:힘들|지쳤|피곤|기쁘|행복|슬프|외롭|화나|짜증|불안|걱정|우울|속상|"
    r"설레|두렵|무섭|후회|감정|기분|스트레스|위로|답답|허전|뿌듯|감사)"
)
SELF_RE = re.compile(
    r"(?:나는|저는|내가|제가|나의|저의|내\s|제\s|좋아|싫어|취향|선호|"
    r"습관|성격|가치관|꿈은|목표는|하고\s*싶|하기\s*싫|생각해|느껴)"
)
RELATION_RE = re.compile(
    r"(?:가족|엄마|아빠|어머니|아버지|남편|아내|연인|친구|동료|상사|아이|아들|딸)"
)
DAILY_RE = re.compile(
    r"(?:오늘|어제|요즘|아침|점심|저녁|주말|출근|퇴근|학교|회사|집에|먹었|마셨|"
    r"잤|잠이|운동|산책|일상|하루|다녀왔|만났|안녕|잘\s*지내)"
)
QUESTION_RE = re.compile(r"(?:[?？]|뭐야|뭔가요|무엇|누구|언제|어디|어떻게|왜|알려|설명)")
KNOWLEDGE_RE = re.compile(
    r"(?:뜻|정의|개념|원리|차이|방법|사용법|코드|함수|오류|에러|계산|번역|요약|"
    r"가격|날씨|역사|수도|인구|문법|공식|스펙|추천|뭐야|무엇|알려|설명)"
)
HANGUL_TITLE_RE = re.compile(r"^[가-힣]{2}$")
PORTRAIT_THEME_WORDS = (
    "온기", "공감", "배려", "도전", "성장", "성실", "열정", "안정", "자유",
    "창의", "탐구", "관계", "가족", "친구", "위로", "신뢰", "책임", "노력",
    "긍정", "용기", "평온", "여유", "소통", "진심", "감성", "활력", "희망",
    "행복", "취향", "일상", "감정", "안녕", "꿈", "목표",
)
PORTRAIT_TITLE_STOPWORDS = {
    "사용", "대화", "모습", "특징", "세션", "내용", "사실", "생각", "마음",
    "정도", "부분", "관련", "기반", "종합", "통해", "대한", "관한", "아직",
    "조금", "여러", "가지", "보여", "있어", "하며", "하고", "하는", "되어",
}


@dataclass(frozen=True, slots=True)
class WeightedTurn:
    text: str
    weight: float


class PortraitEngine:
    """Durable, weighted portrait analysis over every session owned by a user."""

    LEASE_SECONDS = 120
    HEARTBEAT_SECONDS = 30
    LOCAL_VECTOR_DIMENSIONS = 384
    MIN_SESSIONS = 6
    MIN_TURNS = 11
    MIN_USER_CHARACTERS = 751

    def __init__(self, db: Database):
        self.db = db

    @classmethod
    def readiness_counts(cls, db: Database, user_id: str) -> tuple[int, int, int]:
        session_count = 0
        turn_count = 0
        character_count = 0
        for session in db.list_sessions(user_id):
            history = db.get_all_history(user_id, session["id"])
            if history:
                session_count += 1
            turn_count += len(history)
            character_count += sum(
                len(str(row["user_text"] or "").strip()) for row in history
            )
        return session_count, turn_count, character_count

    @classmethod
    def readiness_error(cls, counts: tuple[int, int, int]) -> str | None:
        session_count, turn_count, character_count = counts
        if (
            session_count >= cls.MIN_SESSIONS
            and turn_count >= cls.MIN_TURNS
            and character_count >= cls.MIN_USER_CHARACTERS
        ):
            return None
        return (
            "자화상을 만들려면 대화가 더 필요합니다. "
            f"현재 세션 {session_count}/{cls.MIN_SESSIONS}개, "
            f"대화 {turn_count}/{cls.MIN_TURNS}턴, "
            f"사용자 글자 {character_count}/{cls.MIN_USER_CHARACTERS}자입니다."
        )

    @staticmethod
    def relevance_weight(text: str) -> float:
        """Give personal evidence weight while making pure knowledge requests zero."""
        clean = re.sub(r"\s+", " ", str(text or "").strip())
        if not clean:
            return 0.0
        emotional = bool(EMOTION_RE.search(clean))
        self_disclosure = bool(SELF_RE.search(clean))
        relationship = bool(RELATION_RE.search(clean))
        daily = bool(DAILY_RE.search(clean))
        knowledge_question = bool(QUESTION_RE.search(clean) and KNOWLEDGE_RE.search(clean))

        if emotional and (self_disclosure or daily or relationship):
            return 1.0
        if emotional:
            return 0.92
        if self_disclosure and (daily or relationship):
            return 0.9
        if self_disclosure:
            return 0.78
        if relationship and not knowledge_question:
            return 0.76
        if daily and not knowledge_question:
            return 0.7
        if knowledge_question:
            return 0.0
        # A plain statement can carry weak evidence, while an unclassified
        # question should not become a personality trait by accident.
        if not QUESTION_RE.search(clean) and len(clean) >= 12:
            return 0.25
        return 0.0

    @classmethod
    def _transcript_chunks(
        cls, turns: list[WeightedTurn], max_chars: int = 6200,
    ) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_chars = 0
        for turn in turns:
            text = re.sub(r"\s+", " ", turn.text).strip()[:4000]
            line = f"[가중치 {turn.weight:.2f}] {text}"
            if current and current_chars + len(line) + 1 > max_chars:
                chunks.append("\n".join(current))
                current, current_chars = [], 0
            current.append(line)
            current_chars += len(line) + 1
        if current:
            chunks.append("\n".join(current))
        return chunks

    @staticmethod
    def _paragraph(text: str, max_chars: int) -> str:
        value = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(value) <= max_chars:
            return value
        return value[: max_chars - 1].rstrip() + "…"

    @classmethod
    async def _summarize_session(
        cls,
        pipeline: ModelPipeline,
        session_title: str,
        turns: list[WeightedTurn],
    ) -> str:
        chunks = cls._transcript_chunks(turns)
        summaries: list[str] = []
        for chunk in chunks:
            try:
                summary = await pipeline.summarize_portrait_session(session_title, chunk)
            except PipelineUnavailable:
                summary = ""
            if summary:
                summaries.append(cls._paragraph(summary, 320))
        if len(summaries) > 1:
            combined = "\n".join(f"[부분 {index + 1}] {item}" for index, item in enumerate(summaries))
            try:
                consolidated = await pipeline.summarize_portrait_session(session_title, combined)
                if consolidated:
                    return cls._paragraph(consolidated, 320)
            except PipelineUnavailable:
                pass
        if summaries:
            return cls._paragraph(" ".join(summaries), 320)
        # The portrait remains usable during a temporary LLM outage. Only
        # user-authored snippets are used in this deterministic fallback.
        snippets = [cls._paragraph(turn.text, 70) for turn in sorted(
            turns, key=lambda item: item.weight, reverse=True,
        )[:3]]
        return cls._paragraph("사용자의 주요 자기표현: " + " / ".join(snippets), 320)

    @staticmethod
    def _title_from_summary(summary: str, feature_summaries: list[str]) -> str:
        """Choose a compact theme that is visibly supported by the portrait text."""
        evidence = " ".join([summary, *feature_summaries])
        ranked_themes = [
            (evidence.count(word), summary.find(word), index, word)
            for index, word in enumerate(PORTRAIT_THEME_WORDS)
            if len(word) == 2 and word in evidence
        ]
        if ranked_themes:
            # Repetition across the final summary and session evidence wins. For a
            # tie, prefer a theme explicitly stated earlier in the final summary.
            return max(
                ranked_themes,
                key=lambda item: (item[0], -(item[1] if item[1] >= 0 else 10_000), -item[2]),
            )[3]

        candidates = [
            word for word in re.findall(r"(?<![가-힣])[가-힣]{2}(?![가-힣])", evidence)
            if word not in PORTRAIT_TITLE_STOPWORDS
        ]
        if candidates:
            return max(candidates, key=lambda word: (candidates.count(word), -candidates.index(word)))
        return "마음"

    @classmethod
    def aligned_title(
        cls, title: str | None, summary: str | None, feature_summaries: list[str] | None = None,
    ) -> str:
        """Keep a generated title only when the displayed explanation supports it."""
        clean_title = str(title or "").strip()
        clean_summary = str(summary or "").strip()
        if (
            HANGUL_TITLE_RE.fullmatch(clean_title)
            and clean_title in clean_summary
            and clean_title not in PORTRAIT_TITLE_STOPWORDS
        ):
            return clean_title
        return cls._title_from_summary(clean_summary, feature_summaries or [])

    @staticmethod
    def _parse_final(raw: str, feature_summaries: list[str]) -> tuple[str, str]:
        parsed: dict = {}
        try:
            match = re.search(r"\{[\s\S]*\}", raw)
            candidate = json.loads(match.group(0) if match else raw)
            if isinstance(candidate, dict):
                parsed = candidate
        except (json.JSONDecodeError, AttributeError, TypeError):
            parsed = {}

        summary = PortraitEngine._paragraph(str(parsed.get("summary") or ""), 500)
        if not summary:
            evidence = " ".join(feature_summaries)
            summary = PortraitEngine._paragraph(
                "대화를 종합하면, " + evidence if evidence else
                "아직 자화상을 그릴 만큼 일상과 마음에 관한 대화가 충분하지 않아요.",
                500,
            )

        # A syntactically valid but unrelated two-letter title is more confusing
        # than a fallback. Require the title to be grounded in the final summary.
        title = PortraitEngine.aligned_title(
            str(parsed.get("title") or ""), summary, feature_summaries,
        )
        return title, summary

    @classmethod
    def _local_hash_vector(cls, text: str) -> list[float]:
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        compact = re.sub(r"[^0-9a-z가-힣]", "", normalized)
        features: list[str] = []
        for size in (2, 3):
            features.extend(compact[index:index + size] for index in range(max(0, len(compact) - size + 1)))
        features.extend(re.findall(r"[0-9a-z가-힣]{2,}", normalized))
        vector = [0.0] * cls.LOCAL_VECTOR_DIMENSIONS
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest, "big") % cls.LOCAL_VECTOR_DIMENSIONS
            vector[index] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude:
            vector = [value / magnitude for value in vector]
        return vector

    @classmethod
    async def _vectors(
        cls, pipeline: ModelPipeline, texts: list[str],
    ) -> tuple[list[list[float]], str]:
        try:
            vectors = await pipeline.embed_texts(texts)
            if len(vectors) != len(texts) or len({len(vector) for vector in vectors}) != 1:
                raise ValueError("embedding dimension mismatch")
            return vectors, f"lm_studio:{pipeline.settings.llm_embedding_model}"
        except (PipelineUnavailable, ValueError, TypeError):
            logger.info("Portrait embeddings unavailable; using local Korean hash vectors")
            return [cls._local_hash_vector(text) for text in texts], "local_hash_char_ngram_v1"

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if not left or len(left) != len(right):
            return 0.0
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)))

    @classmethod
    def _accuracy(
        cls,
        final_vector: list[float],
        evidence: list[tuple[list[float], float, int, int]],
    ) -> int:
        weighted: list[tuple[float, float]] = []
        relevant_messages = total_messages = 0
        for vector, session_weight, relevant, total in evidence:
            if session_weight <= 0 or relevant <= 0:
                continue
            weight = session_weight * math.sqrt(relevant)
            weighted.append((max(0.0, cls._cosine(final_vector, vector)), weight))
            relevant_messages += relevant
            total_messages += total
        if not weighted or relevant_messages <= 0:
            return 0
        similarity = sum(score * weight for score, weight in weighted) / sum(
            weight for _, weight in weighted
        )
        evidence_strength = 1.0 - math.exp(-relevant_messages / 8.0)
        session_strength = 1.0 - math.exp(-len(weighted) / 3.0)
        reliability = 0.45 + 0.35 * evidence_strength + 0.20 * session_strength
        coverage = relevant_messages / max(relevant_messages, total_messages)
        coverage_adjustment = 0.8 + 0.2 * math.sqrt(coverage)
        # This is a calibrated evidence-consistency estimate, not a measured
        # ground-truth accuracy. Keep a small uncertainty margin even when all
        # stored feature vectors point in exactly the same direction.
        return max(0, min(95, round(100 * similarity * reliability * coverage_adjustment)))

    async def _heartbeat(
        self, user_id: str, generation_id: str, worker_id: str,
    ) -> None:
        while True:
            await asyncio.sleep(self.HEARTBEAT_SECONDS)
            if not self.db.renew_portrait_lease(
                user_id, generation_id, worker_id, self.LEASE_SECONDS,
            ):
                return

    def _transition_operation(
        self,
        operation_id: str | None,
        status: str,
        *,
        progress_percent: int | None = None,
        error_code: str | None = None,
        reason: str | None = None,
    ) -> None:
        if not operation_id:
            return
        try:
            self.db.transition_operation(
                operation_id,
                status,
                progress_percent=progress_percent,
                error_code=error_code,
                reason=reason,
            )
        except (KeyError, RuntimeError, ValueError):
            logger.warning(
                "Portrait operation transition was rejected: operation_id=%s status=%s",
                operation_id,
                status,
                exc_info=True,
            )

    async def generate(
        self,
        user_id: str,
        generation_id: str,
        persona: str,
        pipeline: ModelPipeline,
        operation_id: str | None = None,
        manage_operation: bool = True,
    ) -> None:
        worker_id = str(uuid.uuid4())
        portrait = self.db.get_portrait(user_id)
        if portrait is None or portrait["generation_id"] != generation_id:
            return
        expected_auth_version = int(portrait["account_auth_version"])

        def authority_valid() -> bool:
            return self.db.is_account_fence_valid(user_id, expected_auth_version)

        def cancel_for_authority_change() -> None:
            if manage_operation:
                self._transition_operation(
                    operation_id, "cancelled", reason="account_authority_changed",
                )

        if not authority_valid():
            cancel_for_authority_change()
            return

        # A duplicate request or another app worker may arrive while a valid
        # lease exists. Wait for completion or lease expiry, then resume only if
        # this worker atomically acquires the job.
        while not self.db.claim_portrait_generation(
            user_id, generation_id, worker_id, self.LEASE_SECONDS,
        ):
            row = self.db.get_portrait(user_id)
            if row is None or row["generation_id"] != generation_id:
                return
            if row["status"] not in {"queued", "analyzing"}:
                return
            lease = row["lease_expires_at"]
            delay = 2.0
            if lease:
                try:
                    delay = max(0.2, min(15.0, (datetime.fromisoformat(lease) - datetime.now(UTC)).total_seconds() + 0.1))
                except ValueError:
                    pass
            await asyncio.sleep(delay)

        readiness_error = self.readiness_error(
            self.readiness_counts(self.db, user_id),
        )
        if readiness_error:
            failed = self.db.fail_portrait(
                user_id, generation_id, worker_id, readiness_error,
            )
            if failed and manage_operation:
                self._transition_operation(
                    operation_id, "failed", error_code="portrait_not_ready",
                    reason="portrait_minimum_evidence_not_met",
                )
            return

        if manage_operation:
            self._transition_operation(
                operation_id, "running", progress_percent=1, reason="worker_claimed",
            )
        heartbeat = asyncio.create_task(self._heartbeat(user_id, generation_id, worker_id))
        analyzed_sessions = analyzed_messages = 0
        try:
            sessions = self.db.list_sessions(user_id)
            total_sessions = len(sessions)
            feature_records: list[dict] = []
            for index, session in enumerate(sessions):
                if not authority_valid():
                    cancel_for_authority_change()
                    return
                history = self.db.get_all_history(user_id, session["id"])
                weighted_turns = [
                    WeightedTurn(str(row["user_text"]), self.relevance_weight(row["user_text"]))
                    for row in history
                ]
                relevant_turns = [turn for turn in weighted_turns if turn.weight > 0]
                total_count = len(weighted_turns)
                relevant_count = len(relevant_turns)
                session_weight = (
                    sum(turn.weight for turn in weighted_turns) / total_count if total_count else 0.0
                )
                if relevant_turns:
                    summary = await self._summarize_session(
                        pipeline, str(session["title"]), relevant_turns,
                    )
                    if not authority_valid():
                        cancel_for_authority_change()
                        return
                elif total_count:
                    summary = "자화상과 직접 관련 없는 지식·정보 중심 대화입니다."
                else:
                    summary = "아직 대화 내용이 없는 세션입니다."
                saved = self.db.save_portrait_session_feature(
                    user_id, generation_id, session["id"], total_count,
                    relevant_count, session_weight, summary, worker_id,
                )
                if not saved:
                    return
                feature_records.append({
                    "session_id": session["id"],
                    "summary": summary,
                    "weight": session_weight,
                    "relevant": relevant_count,
                    "total": total_count,
                })
                analyzed_sessions += 1
                analyzed_messages += total_count
                progress = 5 + round(70 * analyzed_sessions / max(1, total_sessions))
                if not self.db.update_portrait_progress(
                    user_id, generation_id, worker_id, analyzed_sessions,
                    analyzed_messages, progress,
                ):
                    return
                if manage_operation:
                    self._transition_operation(
                        operation_id, "running", progress_percent=progress,
                        reason="session_analyzed",
                    )

            relevant_features = [record for record in feature_records if record["weight"] > 0]
            if relevant_features:
                evidence = "\n".join(
                    f"- [세션 가중치 {record['weight']:.2f}, 관련 발화 {record['relevant']}/{record['total']}] "
                    f"{record['summary']}"
                    for record in relevant_features
                )
                raw = await pipeline.compose_portrait(evidence, persona)
                if not authority_valid():
                    cancel_for_authority_change()
                    return
                title, summary = self._parse_final(
                    raw, [record["summary"] for record in relevant_features],
                )
            else:
                title = "여백"
                summary = "아직 자화상을 그릴 만큼 일상, 감정, 취향이나 자기 생각에 관한 대화가 충분하지 않아요. 조금 더 이야기를 나눈 뒤 다시 분석하면 더 선명한 모습을 볼 수 있어요."

            if not self.db.update_portrait_progress(
                user_id, generation_id, worker_id, analyzed_sessions,
                analyzed_messages, 85,
            ):
                return
            if manage_operation:
                self._transition_operation(
                    operation_id, "running", progress_percent=85,
                    reason="embedding_started",
                )
            vector_texts = [summary] + [record["summary"] for record in feature_records]
            vectors, vector_method = await self._vectors(pipeline, vector_texts)
            if not authority_valid():
                cancel_for_authority_change()
                return
            final_vector, feature_vectors = vectors[0], vectors[1:]
            accuracy_evidence = []
            for record, vector in zip(feature_records, feature_vectors):
                updated = self.db.update_portrait_session_vector(
                    user_id,
                    generation_id,
                    record["session_id"],
                    json.dumps([round(value, 8) for value in vector], separators=(",", ":")),
                    vector_method,
                    worker_id,
                )
                if not updated:
                    return
                accuracy_evidence.append((
                    vector, record["weight"], record["relevant"], record["total"],
                ))
            accuracy = self._accuracy(final_vector, accuracy_evidence)
            if not HANGUL_TITLE_RE.fullmatch(title):
                title = "마음"
            summary = self._paragraph(summary, 500)
            if not authority_valid():
                cancel_for_authority_change()
                return
            completed = self.db.complete_portrait(
                user_id, generation_id, worker_id, title, summary, accuracy,
                analyzed_sessions, analyzed_messages, vector_method,
            )
            if completed and manage_operation:
                self._transition_operation(
                    operation_id, "succeeded", progress_percent=100,
                    reason="portrait_completed",
                )
        except asyncio.CancelledError:
            # A normal service restart must not turn a 5~20 minute analysis
            # into a failure. Requeue it and let the next process resume.
            self.db.release_portrait_lease(
                user_id, generation_id, worker_id,
            )
            if manage_operation:
                self._transition_operation(
                    operation_id, "retrying", reason="worker_shutdown",
                )
            raise
        except Exception as exc:
            logger.exception("Portrait generation failed: user_id=%s", user_id)
            failed = self.db.fail_portrait(
                user_id, generation_id, worker_id, f"자화상 분석에 실패했습니다: {exc}",
            )
            if failed and manage_operation:
                self._transition_operation(
                    operation_id, "failed", error_code="portrait_generation_failed",
                    reason="portrait_generation_failed",
                )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
