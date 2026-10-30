from fastapi import APIRouter

from ...services.browser import extensions

router = APIRouter(prefix="/extensions", tags=["extensions"])


@router.get("")
def list_extensions() -> dict:
    """Extensions added in the app's settings; a profile loads the ids in its `extensions`."""
    return {"extensions": extensions.available()}
