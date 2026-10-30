"""Renders the README images: every [data-shot] element of images.html becomes
docs/images/<name>.png, and of images.ru.html docs/images/ru/<name>.png (both pages
share images.css). Needs Camoufox (python -m camoufox fetch).

    python docs/images/src/render.py

The app screenshots in screens/ (English) and screens/ru/ (Russian) are taken from the real window with made-up
profiles (addresses from the documentation ranges), never from real data.
"""

import functools
import http.server
import pathlib
import threading

from camoufox.sync_api import Camoufox

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE.parent
PAGES = (("images.html", OUT), ("images.ru.html", OUT / "ru"))


def main() -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}/docs/images/src"
    try:
        with Camoufox(headless=True, os="linux", i_know_what_im_doing=True) as browser:
            page = browser.new_page(viewport={"width": 1800, "height": 1200})
            for source, out in PAGES:
                out.mkdir(exist_ok=True)
                page.goto(f"{base}/{source}")
                page.evaluate("document.fonts.ready")
                page.wait_for_load_state("networkidle")
                for element in page.query_selector_all("[data-shot]"):
                    path = out / f"{element.get_attribute('data-shot')}.png"
                    element.screenshot(path=str(path))
                    print(path.relative_to(OUT))
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
