import discord

import dynamic_commands
from config import TOKEN, build_activity, resolve_commands_file


def main() -> None:
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
        print(f"Registered {config_commands.count} commands from {commands_file}")
    except dynamic_commands.CommandsConfigError as e:
        # A broken commands file shouldn't take the bot down — better to come
        # online without the config commands than not at all.
        print(f"WARNING: could not load config commands ({e})")

    @bot.event
    async def on_ready() -> None:
        print(f"Logged in as {bot.user}")

    @bot.slash_command(name="reload", description="Reload commands from the commands.json config file.")
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
            await ctx.respond(f"Reload failed: {e}")
            return
        await ctx.respond(f"Reloaded {count} commands from {commands_file.name}.")

    @bot.slash_command(name="setstatus", description="Set the bot's status message.")
    async def setstatus(
        ctx: discord.ApplicationContext,
        status_type: discord.Option(
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
        ) = "custom",
        text: discord.Option(str, "Status text. Use '-' to clear the status.") = "Beep boop",
    ) -> None:
        if text.strip() in ("", "-"):
            # clearing means "no activity", not a status with empty text
            await bot.change_presence(activity=None)
            await ctx.respond("Status cleared.")
            return
        try:
            activity = build_activity(text=text.strip(), activity_type=status_type)
        except ValueError as e:
            await ctx.respond(f"Failed: {e}")
            return
        await bot.change_presence(activity=activity)
        await ctx.respond(f"Status set: {status_type}: {text.strip()}")

    bot.run(TOKEN)


if __name__ == "__main__":
    main()