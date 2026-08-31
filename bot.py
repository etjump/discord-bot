import logging
import os

import discord

import dynamic_commands
from cogs.basic import Basic
from cogs.server_monitor import ServerMonitor
from config import TOKEN, build_activity, resolve_commands_file

log = logging.getLogger("bot")

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def setup_logging() -> None:
    # Log to stderr via Python's logging module rather than print(): stdout is
    # block-buffered when piped into docker logs, so print() output often never
    # appears until the process exits. Logging keeps docker logs live.
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if level not in _LEVELS:
        level = "INFO"
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Let py-cord's own messages (connection events etc.) use our format too.
    logging.getLogger("discord").setLevel(logging.INFO)


def main() -> None:
    setup_logging()

    # Setting the activity explicitly at startup means the bot always shows its
    # own status — it doesn't inherit whatever another bot last set.
    bot = discord.Bot(activity=build_activity(), cache_app_emojis=True)
    config_commands = dynamic_commands.ConfigCommands()

    # Register BEFORE bot.run(): py-cord only uploads command definitions to
    # Discord when the bot connects, so anything added here is already live by
    # the time the bot shows as online.
    commands_file = resolve_commands_file()
    try:
        config_commands.register(bot, dynamic_commands.load_config(commands_file))
        log.info(
            "Registered %d config commands from %s",
            config_commands.count,
            commands_file,
        )
    except dynamic_commands.CommandsConfigError as e:
        # A broken commands file shouldn't take the bot down — better to come
        # online without the config commands than not at all.
        log.warning("Could not load config commands, starting without them: %s", e)

    log.info("Starting bot...")

    log.info("Adding cogs...")

    bot.add_cog(Basic(bot, config_commands))
    log.info("Registered cog 'Basic'")

    bot.add_cog(ServerMonitor(bot))
    log.info("Registered cog 'Server Monitor'")

    bot.run(TOKEN)


if __name__ == "__main__":
    main()
