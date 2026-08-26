import logging
import os
from typing import Annotated

import discord

import dynamic_commands
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
    bot = discord.Bot(activity=build_activity())
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

    @bot.event
    async def on_ready() -> None:
        # bot.user is guaranteed to be set once connected; the assert tells
        # pyright it's not None so it can type-check bot.user.id.
        assert bot.user is not None
        log.info("Logged in as %s (ID %d)", bot.user, bot.user.id)

    @bot.event
    async def on_application_command(ctx: discord.ApplicationContext) -> None:
        # Log every slash command so docker logs show what users are doing.
        user = ctx.author
        cmd = ctx.command.qualified_name if ctx.command else "?"
        log.info(
            "Command /%s invoked by %s (ID %d) in guild %s channel %s",
            cmd,
            user,
            user.id,
            ctx.guild_id,
            ctx.channel_id,
        )

    @bot.event
    async def on_application_command_error(
        ctx: discord.ApplicationContext, error: Exception
    ) -> None:
        cmd = ctx.command.qualified_name if ctx.command else "?"
        log.error("Command /%s errored: %s", cmd, error, exc_info=error)
        try:
            await ctx.respond("Something went wrong while running that command.")
        except discord.DiscordException:
            pass

    @bot.slash_command(name="ping", description="Check that the bot is responding.")
    async def ping(ctx: discord.ApplicationContext) -> None:
        await ctx.respond(
            f"Pong! Latency: {round(bot.latency * 1000)}ms", ephemeral=True
        )

    @bot.slash_command(
        name="reload", description="Reload commands from the commands.json config file."
    )
    async def reload(ctx: discord.ApplicationContext) -> None:
        try:
            # Resolve at call time, not at startup: the file may have been
            # created/edited after the bot started.
            commands_file = resolve_commands_file()
            count = config_commands.reload(bot, commands_file)
            # Editing the local command list isn't enough — Discord keeps its
            # own copy of the commands and must be told to match. sync_commands
            # uploads the new set and deletes commands that no longer exist.
            await bot.sync_commands()
        except dynamic_commands.CommandsConfigError as e:
            log.warning("Reload failed: %s", e)
            await ctx.respond(f"Reload failed: {e}")
            return
        log.info("Reloaded %d commands from %s", count, commands_file)
        await ctx.respond(f"Reloaded {count} commands from {commands_file.name}.")

    @bot.slash_command(name="setstatus", description="Set the bot's status message.")
    async def setstatus(
        ctx: discord.ApplicationContext,
        status_type: Annotated[
            str,
            discord.Option(
                str,
                "Status type.",
                choices=[
                    discord.OptionChoice("Custom", "custom"),
                    discord.OptionChoice("Watching", "watching"),
                    discord.OptionChoice("Playing", "playing"),
                    discord.OptionChoice("Listening", "listening"),
                    discord.OptionChoice("Competing", "competing"),
                    discord.OptionChoice("Streaming", "streaming"),
                ],
            ),
        ] = "custom",
        text: Annotated[
            str, discord.Option(str, "Status text. Use '-' to clear the status.")
        ] = "Beep boop",
    ) -> None:
        if text.strip() in ("", "-"):
            # clearing means "no activity", not a status with empty text
            await bot.change_presence(activity=None)
            log.info("Status cleared by %s", ctx.author)
            await ctx.respond("Status cleared.")
            return
        try:
            activity = build_activity(text=text.strip(), activity_type=status_type)
        except ValueError as e:
            log.warning("Failed to set status: %s", e)
            await ctx.respond(f"Failed: {e}")
            return
        await bot.change_presence(activity=activity)
        log.info("Status set to %s '%s' by %s", status_type, text.strip(), ctx.author)
        await ctx.respond(f"Status set: {status_type}: {text.strip()}")

    log.info("Starting bot...")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
