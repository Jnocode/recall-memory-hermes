from memory_policy import (
    build_semantic_content,
    extract_project,
    infer_project,
    should_store_turn,
)


def test_normal_chat_is_not_persisted_as_long_term_memory():
    assert not should_store_turn("我今天吃了早餐，等一下要出門")


def test_explicit_decision_is_persisted():
    assert should_store_turn("記住：代碼縫隙採用 YouTube 與 Podcast 雙母引擎")


def test_semantic_card_contains_both_sides_and_project():
    card = build_semantic_content(
        "重大規劃：Recall 不再保存一般流水帳",
        "已確認：只保存決策與架構，普通聊天留在 session log。",
    )
    assert "[PROJECT:hermes-memory]" in card
    assert "[USER]" in card
    assert "[ASSISTANT]" in card
    assert "流水帳" in card


def test_project_inference_is_stable():
    assert infer_project("代碼縫隙 YouTube") == "codegaps"
    assert extract_project("[PROJECT:podcast][TYPE:decision] text") == "podcast"
