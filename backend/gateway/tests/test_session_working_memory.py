from memorypal_api.routes import (
    direct_user_note,
    note_matches_source,
    session_memory_promotion_requested,
    session_working_context,
)
from memorypal_api.services.memory_engine import MemoryCandidate


def test_session_working_context_keeps_only_latest_ten_turns():
    rows = [
        {"user_text": f"[turn-{index:02d}] 질문", "assistant_text": f"[answer-{index:02d}] 답변"}
        for index in range(12)
    ]
    context = session_working_context(rows)
    assert "[turn-00]" not in context
    assert "[turn-01]" not in context
    assert "[turn-02]" in context
    assert "[turn-11]" in context


def test_explicit_save_request_promotes_session_context():
    history = [{"assistant_text": "원하면 이 레시피를 저장해드릴까요?"}]
    assert session_memory_promotion_requested("어 저장해줘", history)
    assert session_memory_promotion_requested("응", history)
    assert not session_memory_promotion_requested("응", [{"assistant_text": "더 궁금한 게 있어?"}])
    assert not session_memory_promotion_requested("그냥 계속 이야기하자", history)


def test_direct_user_note_separates_recipe_from_save_instruction():
    text = (
        "재료 준비 (2~3인분 기준)\n"
        "신김치 1/4포기, 돼지고기 200~300g, 두부 1/2모, 대파 1대\n"
        "돼지고기를 볶고 김치와 물을 넣어 끓입니다.\n\n"
        "이글을 김치찌개 레시피로 저장해줘"
    )

    source, title = direct_user_note(text)

    assert title == "김치찌개 레시피"
    assert "돼지고기 200~300g" in source
    assert "저장해줘" not in source


def test_short_save_confirmation_does_not_become_note_body():
    assert direct_user_note("어 저장해줘")[0] == ""


def test_user_note_summary_must_overlap_with_current_source():
    source = "신김치와 돼지고기를 볶고 두부를 넣어 김치찌개를 끓인다."
    correct = MemoryCandidate("fact", "김치찌개: 신김치와 돼지고기, 두부를 사용한다.")
    unrelated = MemoryCandidate("fact", "계란찜: 계란 4개와 물을 섞어 찐다.")

    assert note_matches_source(correct, source)
    assert not note_matches_source(unrelated, source)
