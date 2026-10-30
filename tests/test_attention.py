"""An agent's request for help raises the window until it is answered."""

from src.ui import attention


class FakeWindow:
    def __init__(self):
        self.calls = []
        self.on_top = False

    def restore(self):
        self.calls.append("restore")

    def show(self):
        self.calls.append("show")


def test_window_stays_on_top_until_released():
    window = FakeWindow()
    attention.raise_window(window)
    assert window.calls == ["restore", "show"] and window.on_top is True
    attention.release_window(window)
    assert window.on_top is False


def test_a_window_that_cannot_rise_does_not_raise():
    class Broken:
        def restore(self):
            raise RuntimeError("gone")

    attention.raise_window(Broken())
    attention.release_window(object())
