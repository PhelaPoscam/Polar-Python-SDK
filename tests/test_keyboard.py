"""Marker parsing for the Windows (msvcrt) keyboard path."""

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
