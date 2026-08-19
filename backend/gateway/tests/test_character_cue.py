from memorypal_api.services.character_cue import character_cue_for


def test_character_cue_maps_answer_tone_to_safe_json():
    assert character_cue_for("와! 정말 대단해요!") == {
        "emotion": "excited",
        "intensity": 0.96,
        "gesture": "celebrate",
        "voice_style": "bright",
    }
    concerned = character_cue_for("많이 힘들었겠어요. 괜찮아요?")
    assert concerned["emotion"] in {"sad", "concerned"}
    assert concerned["gesture"] == "comfort"


def test_character_cue_is_bounded_for_untrusted_text():
    cue = character_cue_for("!" * 10_000)
    assert cue["intensity"] == 1.0
    assert set(cue) == {"emotion", "intensity", "gesture", "voice_style"}
