from pathlib import Path

SRC = (Path(__file__).resolve().parent.parent / "main.py").read_text()


def test_uses_current_sonnet():
    assert 'CLAUDE_MODEL = "claude-sonnet-5"' in SRC


def test_no_retired_models():
    for retired in ("claude-sonnet-4-2025", "claude-opus-4-2025", "claude-3-"):
        assert retired not in SRC


def test_no_first_block_text_assumption():
    assert "content[0].text" not in SRC
