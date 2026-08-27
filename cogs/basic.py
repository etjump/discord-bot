import logging
from typing import Annotated

import discord

import dynamic_commands
from config import build_activity, resolve_commands_file

log = logging.getLogger(__name__)


class Basic(discord.Cog):
    def __init__(self, bot, config_commands) -> None:
        self.bot = bot
        self._config_commands = config_commands

    @discord.slash_command(name="ping", description="Check that the bot is responding.")
    async def ping(self, ctx: discord.ApplicationContext) -> None:
        await ctx.respond(
            f"Pong! Latency: {round(self.bot.latency * 1000)}ms", ephemeral=True
        )

    @discord.slash_command(
        name="reload", description="Reload commands from the commands.json config file."
    )
    async def reload(self, ctx: discord.ApplicationContext) -> None:
        try:
            # Resolve at call time, not at startup: the file may have been
            # created/edited after the bot started.
            commands_file = resolve_commands_file()
            count = self._config_commands.reload(self.bot, commands_file)
            # Editing the local command list isn't enough — Discord keeps its
            # own copy of the commands and must be told to match. sync_commands
            # uploads the new set and deletes commands that no longer exist.
            await self.bot.sync_commands()
        except dynamic_commands.CommandsConfigError as e:
            log.warning("Reload failed: %s", e)
            await ctx.respond(f"Reload failed: {e}", ephemeral=True)
            return
        log.info("Reloaded %d commands from %s", count, commands_file)
        await ctx.respond(
            f"Reloaded {count} commands from {commands_file.name}.", ephemeral=True
        )

    @discord.slash_command(
        name="setstatus", description="Set the bot's status message."
    )
    async def setstatus(
        self,
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
            await self.bot.change_presence(activity=None)
            log.info("Status cleared by %s", ctx.author)
            await ctx.respond("Status cleared.", ephemeral=True)
            return
        try:
            activity = build_activity(text=text.strip(), activity_type=status_type)
        except ValueError as e:
            log.warning("Failed to set status: %s", e)
            await ctx.respond(f"Failed: {e}", ephemeral=True)
            return
        await self.bot.change_presence(activity=activity)
        log.info("Status set to %s '%s' by %s", status_type, text.strip(), ctx.author)
        await ctx.respond(f"Status set: {status_type}: {text.strip()}", ephemeral=True)

    @discord.Cog.listener()
    async def on_ready(self) -> None:
        # bot.user is guaranteed to be set once connected; the assert tells
        # pyright it's not None so it can type-check bot.user.id.
        assert self.bot.user is not None
        log.info("Logged in as %s (ID %d)", self.bot.user, self.bot.user.id)

    @discord.Cog.listener()
    async def on_application_command(self, ctx: discord.ApplicationContext) -> None:
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

    @discord.Cog.listener()
    async def on_application_command_error(
        self, ctx: discord.ApplicationContext, error: Exception
    ) -> None:
        cmd = ctx.command.qualified_name if ctx.command else "?"
        log.error("Command /%s errored: %s", cmd, error, exc_info=error)
        try:
            await ctx.respond(
                "Something went wrong while running that command.", ephemeral=True
            )
        except discord.DiscordException:
            pass
