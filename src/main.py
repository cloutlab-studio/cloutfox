import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.app import create_app
from src.api.auth import check_token
from src.api.server import APIServer
from src.core.config import API_HOST, API_PORT
from src.core.container import Container
from src.core.logging import get_logger
from src.ui.window import Window

logger = get_logger("main")


def main() -> None:
    check_token()
    container = Container()
    servers: list[APIServer] = []

    def start_api() -> None:
        # Only once the profiles are open: with a master password set, the API and
        # MCP stay off until it is entered.
        if servers:
            return
        server = APIServer(create_app(container))
        server.start()
        servers.append(server)
        container.profile_data.start_checkpoints()
        container.backups.start()
        logger.info("API available at http://%s:%s/api/v1", API_HOST, API_PORT)

    try:
        Window(container, on_unlocked=start_api).run()
    finally:
        for server in servers:
            server.stop()


if __name__ == "__main__":
    main()
