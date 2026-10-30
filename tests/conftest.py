import pytest

from src.services.browser import camoufox_fetch

REAL_ENSURE = camoufox_fetch.ensure
REAL_START = camoufox_fetch.start


@pytest.fixture(autouse=True)
def no_camoufox_download(monkeypatch):
    """Tests never download the browser; test_camoufox_fetch uses the real functions."""
    monkeypatch.setattr(camoufox_fetch, "ensure", lambda say: None)
    monkeypatch.setattr(camoufox_fetch, "start", lambda log=None: False)
