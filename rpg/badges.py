import json
from pathlib import Path

_MANIFEST_PATH = Path(__file__).parent.parent / "assets" / "prestige" / "manifest.json"


def _load() -> dict[int, str]:
    try:
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {int(prestige): f"<:{data['emoji_name']}:{data['id']}>" for prestige, data in manifest.items()}


PRESTIGE_BADGES = _load()


def prestige_badge(prestige: int) -> str:
    """Returns the custom badge emoji for a prestige tier, or "" for prestige 0."""
    return PRESTIGE_BADGES.get(prestige, "")
