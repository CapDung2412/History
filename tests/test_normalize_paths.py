from src.dataset.normalize_paths import ascii_slug


def test_ascii_slug_supports_vietnamese() -> None:
    assert ascii_slug("Hậu quả chất độc da cam") == "hau-qua-chat-doc-da-cam"
    assert ascii_slug("Đường 1C") == "duong-1c"
