import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["TOKEN"]

# Live-editable command definitions live in config/commands.json, which is
# mounted into the container and gitignored. The committed commands.json in
# the repo root is the fallback (and the template deploy.sh seeds from).
COMMANDS_FILE = Path(__file__).parent / "config" / "commands.json"
FALLBACK_COMMANDS_FILE = Path(__file__).parent / "commands.json"


def resolve_commands_file() -> Path:
    # The config/ copy wins because it's the live-editable file on the server
    # (mounted into the container, gitignored). The committed commands.json in
    # the repo root only exists as a fallback so a fresh checkout works out of
    # the box before deploy.sh has seeded config/commands.json.
    if COMMANDS_FILE.exists():
        return COMMANDS_FILE
    return FALLBACK_COMMANDS_FILE