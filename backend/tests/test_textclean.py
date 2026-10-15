from app.textclean import strip_emoji


def test_emoji_are_removed_and_gaps_closed():
    text = "⭐ Visit LA's patch! Highlights 🎃 Visit the village 🍂 Stroll 🐑 Explore 🦉 Birds 🥧 Food…"
    assert strip_emoji(text) == "Visit LA's patch! Highlights Visit the village Stroll Explore Birds Food…"


def test_flags_keycaps_and_joiners_go_too():
    assert strip_emoji("Fun 🇺🇸 day 1️⃣ with 👨‍👩‍👧 family ❤️") == "Fun day 1 with family"


def test_plain_text_is_untouched():
    assert strip_emoji("Open 5–9 pm → ticket $13.83 (ages 3+)") == "Open 5–9 pm → ticket $13.83 (ages 3+)"
    assert strip_emoji("Line one\nLine two") == "Line one\nLine two"


def test_empty_and_emoji_only():
    assert strip_emoji(None) is None
    assert strip_emoji("🎃🍂") is None
