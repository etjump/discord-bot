import os
from pathlib import Path

import discord
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["TOKEN"]

# Bot presence (the text shown under the bot's name). Defaults to a custom
# status "Beep boop"; set BOT_ACTIVITY to an empty value to show no status.
BOT_ACTIVITY = os.environ.get("BOT_ACTIVITY", "Beep boop")
BOT_ACTIVITY_TYPE = os.environ.get("BOT_ACTIVITY_TYPE", "custom").lower()

# Live-editable command definitions live in config/commands.json, which is
# mounted into the container and gitignored. The committed commands.json in
# the repo root is the fallback (and the template deploy.sh seeds from).
COMMANDS_FILE = Path(__file__).parent / "config" / "commands.json"
FALLBACK_COMMANDS_FILE = Path(__file__).parent / "commands.json"

_ACTIVITY_TYPES = {
    "playing": discord.ActivityType.playing,
    "watching": discord.ActivityType.watching,
    "listening": discord.ActivityType.listening,
    "competing": discord.ActivityType.competing,
    "streaming": discord.ActivityType.streaming,
}


def build_activity(
    text: str | None = None, activity_type: str | None = None
) -> discord.BaseActivity | None:
    # Used at startup (no args, reads env config) and by /setstatus (explicit
    # args). Returns None when there is no text, meaning "no status". Custom
    # statuses use a different class than the standard "Playing/Watching/..."
    # types, hence the branch.
    text = (text if text is not None else BOT_ACTIVITY) or None
    activity_type = (activity_type or BOT_ACTIVITY_TYPE).lower()
    if not text:
        return None
    if activity_type == "custom":
        return discord.CustomActivity(name=text)
    try:
        activity = _ACTIVITY_TYPES[activity_type]
    except KeyError:
        # from None: the KeyError context isn't useful — the ValueError
        # message already explains the invalid type to the user.
        raise ValueError(
            f"unknown status type '{activity_type}' "
            f"(valid: custom, {', '.join(_ACTIVITY_TYPES)})"
        ) from None
    return discord.Activity(type=activity, name=text)


def resolve_commands_file() -> Path:
    # The config/ copy wins because it's the live-editable file on the server
    # (mounted into the container, gitignored). The committed commands.json in
    # the repo root only exists as a fallback so a fresh checkout works out of
    # the box before deploy.sh has seeded config/commands.json.
    if COMMANDS_FILE.exists():
        return COMMANDS_FILE
    return FALLBACK_COMMANDS_FILE
