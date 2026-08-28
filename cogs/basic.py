import logging
from typing import Annotated

import discord

import dynamic_commands
from config import build_activity, resolve_commands_file

log = logging.getLogger(__name__)


class Basic(discord.Cog):
    def __init__(
        self, bot: discord.Bot, config_commands: dynamic_commands.ConfigCommands
    ) -> None:
        self.bot = bot
        self._config_commands = config_commands

    @discord.slash_command(name="help", description="Display available commands.")
    async def help(self, ctx: discord.ApplicationContext) -> None:
        # If invoked via DM, 'guild_permissions' don't exists
        perms = (
            ctx.author.guild_permissions
            if isinstance(ctx.author, discord.Member)
            else None
        )

        admin_cmds = []
        general_cmds = []

        for cmd in self.bot.application_commands:
            if not isinstance(cmd, discord.SlashCommand):
                continue

            required = cmd.default_member_permissions

            if required is None:
                general_cmds.append(cmd)
            elif perms is not None and (
                perms.administrator or perms.is_superset(required)
            ):
                admin_cmds.append(cmd)

        embed = discord.Embed(
            title="Commands",
            description="List of commands available for you to use.",
            color=discord.Colour.from_rgb(134, 168, 134),
        )

        assert self.bot.user is not None
        embed.set_author(name="TJBot", icon_url=self.bot.user.display_avatar.url)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(
            text="Commands you may have access to via overrides are not listed here."
        )

        general_fmt = "\n".join(
            [f"**/{cmd.name}** - {cmd.description}" for cmd in general_cmds]
        )
        embed.add_field(
            name="General commands",
            value=general_fmt,
            inline=False,
        )

        if admin_cmds:
            admin_fmt = "\n".join(
                [f"**/{cmd.name}** - {cmd.description}" for cmd in admin_cmds]
            )
            embed.add_field(
                name="Admin commands",
                value=admin_fmt,
                inline=False,
            )

        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(name="ping", description="Check that the bot is responding.")
    async def ping(self, ctx: discord.ApplicationContext) -> None:

        await ctx.respond(
            f"Pong! Latency: {round(self.bot.latency * 1000)}ms", ephemeral=True
        )

    @discord.slash_command(
        name="reload",
        description="Reload commands from the `commands.json` config file.",
        default_member_permissions=discord.Permissions(administrator=True),
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
        name="setstatus",
        description="Set the bot's status message.",
        default_member_permissions=discord.Permissions(administrator=True),
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
