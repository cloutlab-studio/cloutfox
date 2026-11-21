import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.app import create_app
from src.api.auth import check_token
from src.api.server import APIServer
from src.core.container import Container
from src.core.logging import get_logger
from src.core.strings import get_string
from src.ui.window import Window, claim_instance

logger = get_logger("main")


def main() -> None:
    check_token()
    # Before anything reads or cleans the data folder: a second start only wakes
    # the window that is already open.
    instance = claim_instance()
    if instance is None:
        return
    container = Container()
    servers: list[APIServer] = []
    ui: list[Window] = []

    def api_failed(address: str) -> None:
        if ui:
            ui[0].bridge._log(get_string("api_port_busy", address=address))

    def start_api() -> None:
        # Only once the profiles are open: with a master password set, the API and
        # MCP stay off until it is entered.
        if servers:
            return
        server = APIServer(create_app(container))
        server.start(on_failed=api_failed)
        servers.append(server)
        container.profile_data.start_checkpoints()
        container.backups.start()

    try:
        ui.append(Window(container, on_unlocked=start_api, instance=instance))
        ui[0].run()
    finally:
        for server in servers:
            server.stop()


if __name__ == "__main__":
    main()
