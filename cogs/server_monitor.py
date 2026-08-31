import asyncio
import datetime
import logging
import re
import time
from typing import Annotated

import discord

import etquery

log = logging.getLogger(__name__)

_RATE_LIMIT_SECONDS = 5
_COLOR_STRING = re.compile(r"\^[^^]")

_TEAM_AXIS = "1"
_TEAM_ALLIES = "2"


def _strip_color_codes(text: str) -> str:
    return re.sub(_COLOR_STRING, "", text)


class ServerMonitor(discord.Cog):
    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot
        self._last_query: dict[int, float] = {}
        self._emoji_cache: dict[str, discord.GuildEmoji | discord.AppEmoji | None] = {}

    # returns the time remaining until the user can use the command again,
    # or 'None' if they aren't currently rate limited
    # FIXME: in theory, this grows 'self._last_query' infinitely -
    # this isn't a realistic concern with our userbase, but this should be reworked
    # such that we remove the entry from the dict, once the time has expired.
    def _check_rate_limit(self, ctx: discord.ApplicationContext) -> float | None:
        now = time.monotonic()
        last = self._last_query.get(ctx.author.id)

        if last is not None and now - last < _RATE_LIMIT_SECONDS:
            return last + _RATE_LIMIT_SECONDS - now

        self._last_query[ctx.author.id] = now
        return None

    def _get_emoji(self, name: str) -> discord.GuildEmoji | discord.AppEmoji | None:
        if name not in self._emoji_cache:
            self._emoji_cache[name] = discord.utils.get(self.bot.emojis, name=name)
        return self._emoji_cache[name]

    def _build_timestamp(self) -> str:
        now = datetime.datetime.now().astimezone()
        offset = now.strftime("%z")  # "+0200"
        tz = f"{offset[:-2]}:{offset[-2:]}"  # "+02:00"
        return now.strftime("%Y-%m-%d %H:%M:%S") + f" ({tz})"

    def _build_embed(self, status: etquery.Status) -> discord.Embed:
        hostname = status.info.get("sv_hostname", "Unknown hostname")
        mapname = status.info.get("mapname", "Unknown map")
        mod_name = status.info.get("gamename", "Unknown mod")
        mod_version = status.info.get("mod_version", "Unknown mod version")
        max_clients = status.info.get("sv_maxclients", "-")
        private_clients = status.info.get("sv_privateClients", "-")
        players = len(status.players)

        embed = discord.Embed(
            title=_strip_color_codes(hostname),
            color=discord.Colour.from_rgb(134, 168, 134),
        )

        embed.add_field(name="Address", value=f"`{status.host}:{status.port}`")
        # TODO: fetch IP geolocation when server gets added
        # embed.add_field(name="Country", value=":united_nations: Unknown")
        embed.add_field(name="", value="")
        # TODO: actually check the status - this is relevant only for the monitoring loop
        embed.add_field(name="Status", value=":green_circle: Online")

        embed.add_field(name="Map", value=mapname)
        embed.add_field(
            name="Players", value=f"{players}/{max_clients}({private_clients})"
        )
        embed.add_field(name="Mod", value=f"{mod_name} {mod_version}")

        # don't worry about listing players if there are none
        if not players:
            return embed

        player_teams = status.info.get("P")
        player_list: list[str] = []
        if player_teams is None:
            for tup in status.players:
                player_list.append(_strip_color_codes(tup[2]))

            embed.add_field(name="Players", value="\n".join(player_list), inline=False)
        else:
            player_teams = player_teams.replace("-", "")
            axis_players: list[str] = []
            allies_players: list[str] = []
            spectators: list[str] = []

            for i, tup in enumerate(status.players):
                if player_teams[i] == _TEAM_AXIS:
                    axis_players.append(_strip_color_codes(tup[2]))
                elif player_teams[i] == _TEAM_ALLIES:
                    allies_players.append(_strip_color_codes(tup[2]))
                else:
                    spectators.append(_strip_color_codes(tup[2]))

            if len(axis_players) or len(allies_players):
                flag_axis = self._get_emoji("tjbot_flag_axis")
                flag_allies = self._get_emoji("tjbot_flag_allies")

                embed.add_field(
                    name=f"{flag_axis} Axis" if flag_axis else "Axis",
                    value="\n".join(axis_players),
                )
                embed.add_field(
                    name=f"{flag_allies} Allies" if flag_allies else "Allies",
                    value="\n".join(allies_players),
                )

                # empty field to make spectators align to 3 columns
                embed.add_field(name="", value="")

            if len(spectators):
                flag_spec = self._get_emoji("tjbot_flag_spec")
                columns = [spectators[i::3] for i in range(3)]

                spec_title = f"{flag_spec} Spectators" if flag_spec else "Spectators"
                for idx, col in enumerate(columns):
                    # zero-width whitespace to hide the column names for columns 2 & 3,
                    # as Discord automatically strips any regular whitespace,
                    # which messes up the vertical spacing
                    embed.add_field(
                        name=spec_title if idx == 0 else "\u200b", value="\n".join(col)
                    )

        return embed

    @discord.slash_command(name="serverstatus", description="Get status from a server")
    async def getstatus(
        self,
        ctx: discord.ApplicationContext,
        addr: Annotated[
            str,
            discord.Option(str, "Server to query status from, optionally with :port."),
        ],
    ) -> None:
        assert self.bot.user is not None
        remaining = self._check_rate_limit(ctx)

        if remaining is not None:
            log.info(
                f"Rejecting command /serverstatus from user {ctx.author} due to rate limiting"
            )
            await ctx.respond(
                f"Please wait **{remaining:.2f}s** before using this command again.",
                ephemeral=True,
            )
            return

        # ack immediately and defer, so the Discord response doesn't time out
        # if the queried server does not respond
        await ctx.defer(ephemeral=True)

        try:
            host, port = etquery.parse_address(addr)
        except ValueError as e:
            await ctx.respond(f"Invalid address: {e}", ephemeral=True)
            return

        try:
            payload = await asyncio.to_thread(etquery.query_status, host, port)
            status = etquery.parse_status(payload, host, port)
        except etquery.QueryError as e:
            await ctx.respond(f"Query failed: {e}", ephemeral=True)
            return

        # we don't use Discord's built-in timestamp, or embed.timestamp here because:
        # * Discord built-in timestamp cannot be used in footers, and adding it
        #   as a field would generate a visually distracting ticker in the embed
        # * Embed native timestamp has no formatting options, and default is overly verbose
        embed = self._build_embed(status)
        embed.set_footer(
            text=f"TJBot Server Monitor  |  Status fetched at {self._build_timestamp()}",
            icon_url=self.bot.user.display_avatar.url,
        )
        await ctx.respond(embed=embed, ephemeral=True)
