"""Config-file driven slash commands.

Commands are defined in commands.json instead of code so that adding or editing
a simple command on the server is just a file edit + restart (or /reload) — no
git commit or Docker rebuild. This module turns those config entries into real
py-cord command objects.
"""

import json
import logging
from collections.abc import Iterable
from pathlib import Path

import discord

log = logging.getLogger("dynamic_commands")


class CommandsConfigError(Exception):
    pass


def load_config(path: Path) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise CommandsConfigError(f"commands file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise CommandsConfigError(f"invalid JSON in {path}: {e}") from e

    if not isinstance(data, dict) or not isinstance(data.get("commands"), list):
        raise CommandsConfigError(
            f'{path} must be an object containing a "commands" list'
        )

    commands = data["commands"]
    for i, entry in enumerate(commands):
        if (
            not isinstance(entry, dict)
            or not entry.get("name")
            or not entry.get("response")
        ):
            raise CommandsConfigError(
                f'command #{i} in {path} needs "name" and "response"'
            )

    return commands


def make_responder(response: str):
    # Each command gets its own closure capturing its response text. The
    # response can't be a plain function parameter: py-cord treats every
    # parameter of a command callback as a user-supplied option.
    async def responder(ctx: discord.ApplicationContext) -> None:
        await ctx.respond(response)

    return responder


def build_commands(commands: Iterable[dict]) -> list[discord.SlashCommand]:
    result = []
    for entry in commands:
        result.append(
            discord.SlashCommand(
                make_responder(entry["response"]),
                name=entry["name"],
                description=entry.get("description") or "No description provided.",
            )
        )
    return result


class ConfigCommands:
    def __init__(self) -> None:
        self._registered: list[discord.SlashCommand] = []

    @property
    def count(self) -> int:
        return len(self._registered)

    def register(self, bot: discord.Bot, commands: Iterable[dict]) -> None:
        for cmd in build_commands(commands):
            bot.add_application_command(cmd)
            self._registered.append(cmd)
        log.debug("Registered %d config commands", self.count)

    def unregister(self, bot: discord.Bot) -> None:
        for cmd in self._registered:
            bot.remove_application_command(cmd)
        self._registered.clear()

    def reload(self, bot: discord.Bot, path: Path) -> int:
        # Validate and build the NEW commands before dropping the current ones,
        # so an invalid config leaves the working commands untouched.
        old_count = self.count
        commands = load_config(path)
        self.unregister(bot)
        self.register(bot, commands)
        log.debug("Reloaded config commands: %d -> %d", old_count, self.count)
        return self.count
