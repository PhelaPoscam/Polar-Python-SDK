"""Marker parsing for the Windows (msvcrt) and POSIX (line) keyboard paths."""

from polar_ble_sdk.input.keyboard import NonBlockingKeyboardReader


class FakeMsvcrt:
    def __init__(self, keys: str) -> None:
        self._keys = list(keys)

    def kbhit(self) -> bool:
        return bool(self._keys)

    def getwch(self) -> str:
        return self._keys.pop(0)


def poll(keys: str) -> list[str]:
    reader = NonBlockingKeyboardReader()
    reader._win_msvcrt = FakeMsvcrt(keys)
    return reader.poll_markers()


def test_hotkey_fires_instantly() -> None:
    assert poll("s") == ["stimulus_on"]


def test_slash_prefix_keeps_free_text_intact() -> None:
    assert poll("/Start trial\r") == ["Start trial"]


def test_plain_free_text_still_works() -> None:
    assert poll("hello\r") == ["hello"]


def poll_posix(monkeypatch, line: str) -> list[str]:
    import io
    import select
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO(line))
    monkeypatch.setattr(select, "select", lambda r, w, x, t: (r, [], []))
    reader = NonBlockingKeyboardReader()
    reader._win_msvcrt = None
    return reader.poll_markers()


def test_posix_line_input(monkeypatch) -> None:
    assert poll_posix(monkeypatch, "\n") == ["marker"]  # bare Enter = SPACE
    assert poll_posix(monkeypatch, "/s trial\n") == ["s trial"]
    assert poll_posix(monkeypatch, "s\n") == ["stimulus_on"]
    assert poll_posix(monkeypatch, "") == []  # EOF
