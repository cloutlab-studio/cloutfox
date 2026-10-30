"""Getting the person's attention when an agent asks for help.

The window comes up over every other window until the request is answered (a
plain raise is ignored by focus-stealing prevention on most Linux desktops).
The chime is played by the page (Web Audio), which the window allows without a
click first.
"""

from __future__ import annotations

import contextlib
from typing import Any


def raise_window(window: Any) -> None:
    """Un-minimise the window and keep it above other windows until `release_window`."""
    with contextlib.suppress(Exception):
        window.restore()
    with contextlib.suppress(Exception):
        window.show()
    with contextlib.suppress(Exception):
        window.on_top = True


def release_window(window: Any) -> None:
    with contextlib.suppress(Exception):
        window.on_top = False
