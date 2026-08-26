import discord

import dynamic_commands
from config import TOKEN, resolve_commands_file


def main() -> None:
    bot = discord.Bot()
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

    bot.run(TOKEN)


if __name__ == "__main__":
    main()