import asyncio
import datetime
import logging
import os
import re
import time
from typing import Annotated

import discord
import pycountry
from discord.ext import tasks

import etquery
import geoip
import monitor_config

log = logging.getLogger(__name__)

_POLL_INTERVAL_MIN = 15
_POLL_INTERVAL = max(
    int(os.environ.get("POLL_INTERVAL_SECONDS", 60)), _POLL_INTERVAL_MIN
)
_RATE_LIMIT_SECONDS = 5
_COLOR_STRING = re.compile(r"\^[^^]")

_TEAM_AXIS = "1"
_TEAM_ALLIES = "2"
_TEAM_SPECTATORS = "3"

_UNKNOWN_LOCATION = ":united_nations: Unknown"


def _strip_color_codes(text: str) -> str:
    return re.sub(_COLOR_STRING, "", text)


def _build_location_field(country: str | None) -> str:
    """'country' should be ISO 3166-1 alpha-2 country code"""
    if not country or len(country) != 2:
        return _UNKNOWN_LOCATION

    country_data = pycountry.countries.get(alpha_2=country)
    if not country_data:
        return _UNKNOWN_LOCATION

    return f"{country_data.flag} {country_data.name}"


def _bucket_players(player_teams: str, status: etquery.Status) -> dict[str, list[str]]:
    player_teams = player_teams.replace("-", "")
    axis_players: list[str] = []
    allies_players: list[str] = []
    spectators: list[str] = []

    # should not happen, but let's log a warning
    if len(player_teams) != len(status.players):
        log.warning(
            f"Player count mismatch for '{status.host}:{status.port}': "
            f"{len(player_teams)} team entries for {len(status.players)} players, truncating will occur!"
        )

    for team, tup in zip(player_teams, status.players, strict=False):
        if team == _TEAM_AXIS:
            axis_players.append(_strip_color_codes(tup[2]))
        elif team == _TEAM_ALLIES:
            allies_players.append(_strip_color_codes(tup[2]))
        else:
            spectators.append(_strip_color_codes(tup[2]))

    return {
        _TEAM_AXIS: axis_players,
        _TEAM_ALLIES: allies_players,
        _TEAM_SPECTATORS: spectators,
    }


class ServerMonitor(discord.Cog):
    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot
        self._last_query: dict[int, float] = {}
        self._emoji_cache: dict[str, discord.GuildEmoji | discord.AppEmoji | None] = {}
        self._monitored_servers: list[monitor_config.MonitoredServer] = []
        self._need_config_write = False
        self._messages: dict[tuple[str, int], discord.Message] = {}

    @discord.Cog.listener()
    async def on_ready(self) -> None:
        # guard against starting the loop twice, if the bot reconnects
        if self._monitor_loop.is_running():
            log.debug("Monitoring loop already online, ignoring 'on_ready' event")
            return
        self._monitor_loop.start()

    def cog_unload(self) -> None:
        self._monitor_loop.cancel()

    @tasks.loop(seconds=_POLL_INTERVAL)
    async def _monitor_loop(self) -> None:
        # the entire loop is wrapped in a broad try-except so that a weird edge case
        # that may throw an exception does not kill the entire thing
        try:
            try:
                self._monitored_servers = monitor_config.load_config(
                    monitor_config.SERVERS_FILE
                )
            except monitor_config.MonitorConfigError as e:
                log.error(f"Failed to load config for server monitoring: {e}")
                return

            queries = [
                asyncio.to_thread(self._query_server, server.host, server.port)
                for server in self._monitored_servers
            ]
            results = await asyncio.gather(*queries)
            online = sum(1 for status in results if status.is_online)
            log.info(
                f"Status received from {online}/{len(self._monitored_servers)} servers"
            )

            # flip to false in case last update modified config
            self._need_config_write = False

            updated = 0
            attempted = 0

            for server, status in zip(self._monitored_servers, results, strict=False):
                channel = self.bot.get_channel(server.channel_id)
                if not isinstance(channel, discord.TextChannel):
                    log.warning(
                        f"Selected channel for server '{server.host}:{server.port}' is not a text channel, skipping message"
                    )
                    continue

                assert self.bot.user is not None
                embed = self._build_embed(status, server.name)
                embed.set_footer(
                    text=f"TJBot Server Monitor  |  Last updated on {self._build_timestamp()}",
                    icon_url=self.bot.user.display_avatar.url,
                )

                attempted += 1

                if server.message_id:
                    # may still end up calling '_send_message',
                    # if the message this tries to edit has been deleted
                    message = await self._edit_message(channel, server, embed)
                else:
                    message = await self._send_message(channel, server, embed)

                if message:
                    self._validate_cached_data(server, status, message)
                    updated += 1

                # pace the edits 1s apart for each server, so we don't hit API limits
                await asyncio.sleep(1.0)

            log.info(f"Updated {updated}/{attempted} status messages")

            if self._need_config_write:
                try:
                    log.debug(
                        f"Updating server monitor config '{monitor_config.SERVERS_FILE}'"
                    )
                    monitor_config.save_config(
                        monitor_config.SERVERS_FILE, self._monitored_servers
                    )
                except OSError as e:
                    log.error(
                        f"Failed to update server monitor config - existing cached data may be invalid: {e}"
                    )
        except Exception:
            log.exception("Unexpected error occurred while polling servers:")

    @_monitor_loop.before_loop
    async def before_monitor(self) -> None:
        log.info("Waiting for the bot to be online to start server monitoring...")
        await self.bot.wait_until_ready()

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

    def _build_embed_summary(
        self, embed: discord.Embed, status: etquery.Status
    ) -> None:
        """Builds the upper half of the server status embed:
        title
        address     location     status
        map         playercount  mod"""
        hostname = status.info.get("sv_hostname", "Unknown hostname")
        mapname = status.info.get("mapname", "Unknown map")
        mod_name = status.info.get("gamename", "Unknown mod")
        mod_version = status.info.get("mod_version", "Unknown mod version")
        max_clients = status.info.get("sv_maxclients", "-")
        private_clients = status.info.get("sv_privateClients", "-")

        embed.title = _strip_color_codes(hostname)

        embed.add_field(name="Address", value=f"`{status.host}:{status.port}`")
        embed.add_field(
            name="Location", value=f"{_build_location_field(status.location)}"
        )
        embed.add_field(name="Status", value=":green_circle: Online")

        embed.add_field(name="Map", value=mapname)
        embed.add_field(
            name="Players",
            value=f"{len(status.players)}/{max_clients}({private_clients})",
        )
        embed.add_field(name="Mod", value=f"{mod_name} {mod_version}")

        # cache the server name
        status.name = _strip_color_codes(hostname)

    def _add_players_to_columns(
        self, embed: discord.Embed, names: list[str], title: str
    ) -> None:
        columns = [names[i::3] for i in range(3)]

        for idx, col in enumerate(columns):
            # zero-width whitespace to hide the column names for columns 2 & 3,
            # as Discord automatically strips any regular whitespace,
            # which messes up the vertical spacing
            embed.add_field(name=title if idx == 0 else "\u200b", value="\n".join(col))

    def _build_player_list(self, embed: discord.Embed, status: etquery.Status) -> None:
        # every server should have this, but fallback to just un-categorized
        # list of player in case it's not there somehow
        player_teams = status.info.get("P")
        if player_teams is None:
            player_list: list[str] = []
            for tup in status.players:
                player_list.append(_strip_color_codes(tup[2]))

            self._add_players_to_columns(embed, player_list, "Players")
            return

        player_bucket = _bucket_players(player_teams, status)

        if len(player_bucket[_TEAM_AXIS]) or len(player_bucket[_TEAM_ALLIES]):
            flag_axis = self._get_emoji("tjbot_flag_axis")
            flag_allies = self._get_emoji("tjbot_flag_allies")

            embed.add_field(
                name=f"{flag_axis} Axis" if flag_axis else "Axis",
                value="\n".join(player_bucket[_TEAM_AXIS]),
            )
            embed.add_field(
                name=f"{flag_allies} Allies" if flag_allies else "Allies",
                value="\n".join(player_bucket[_TEAM_ALLIES]),
            )

            # empty field to make spectators align to 3 columns
            embed.add_field(name="", value="")

        if len(player_bucket[_TEAM_SPECTATORS]):
            flag_spec = self._get_emoji("tjbot_flag_spec")
            spec_title = f"{flag_spec} Spectators" if flag_spec else "Spectators"
            self._add_players_to_columns(
                embed, player_bucket[_TEAM_SPECTATORS], spec_title
            )

    def _build_offline_embed(
        self,
        embed: discord.Embed,
        status: etquery.Status,
        cached_name: str | None = None,
    ) -> None:
        embed.title = cached_name if cached_name else "Unknown server"

        embed.add_field(name="Address", value=f"`{status.host}:{status.port}`")
        embed.add_field(
            name="Location", value=f"{_build_location_field(status.location)}"
        )
        embed.add_field(name="Status", value=":red_circle: Offline")

        embed.add_field(name="Map", value="Unknown")
        embed.add_field(name="Players", value="-/-(-)")
        embed.add_field(name="Mod", value="Unknown")

    def _build_embed(
        self, status: etquery.Status, cached_name: str | None = None
    ) -> discord.Embed:
        embed = discord.Embed(
            color=discord.Colour.from_rgb(134, 168, 134),
        )

        if not status.is_online:
            self._build_offline_embed(embed, status, cached_name)
            return embed

        self._build_embed_summary(embed, status)

        # don't worry about listing players if there are none
        if len(status.players):
            self._build_player_list(embed, status)

        return embed

    def _query_server(self, host: str, port: int) -> etquery.Status:
        try:
            payload = etquery.query_status(host, port)
            status = etquery.parse_status(payload, host, port)
        except etquery.QueryError as e:
            log.warning(f"Query failed: {e}")
            return etquery.Status.offline(host, port)
        except Exception:
            log.exception(f"Unexpected error while querying server '{host}:{port}':")
            log.warning(f"Server '{host}:{port}' marked as offline!")
            return etquery.Status.offline(host, port)

        status.location = geoip.country_lookup(host)

        log.debug(f"Received status from server {host}:{port}")
        return status

    async def _send_message(
        self,
        channel: discord.TextChannel,
        server: monitor_config.MonitoredServer,
        embed: discord.Embed,
    ) -> discord.Message | None:
        """Returns the message on successful send, None if error occurred"""
        try:
            message = await channel.send(embed=embed)
            # cache so we don't need to fetch on edit
            self._messages[f"{server.host}:{server.port}", message.id] = message
            return message
        except (discord.Forbidden, discord.HTTPException, discord.InvalidArgument) as e:
            log.error(
                f"Failure while trying to create message for monitored server '{server.host}:{server.port}': {e}"
            )

    async def _edit_message(
        self,
        channel: discord.TextChannel,
        server: monitor_config.MonitoredServer,
        embed: discord.Embed,
    ) -> discord.Message | None:
        """Returns the message on successful edit, None if error occurred.
        Ensure 'server.message_id' is valid before calling this!
        """
        assert server.message_id is not None

        try:
            # try to find the message from cache - if not found, fetch it
            message = self._messages.get(
                (f"{server.host}:{server.port}", server.message_id)
            )
            if not message:
                log.debug(
                    f"Message for monitored server '{server.host}:{server.port}' not found in local cache, fetching"
                )
                message = await channel.fetch_message(server.message_id)
                self._messages[f"{server.host}:{server.port}", message.id] = message

            message = await message.edit(embed=embed)
            return message
        except discord.NotFound:
            log.info(
                f"Message containing monitoring for server '{server.host}:{server.port}' no longer found, creating new one"
            )
            # try to remove existing message from cache - this may not exists
            # if the message was deleted from Discord while the bot was offline
            self._messages.pop(
                (f"{server.host}:{server.port}", server.message_id), None
            )
            return await self._send_message(channel, server, embed)
        except (discord.Forbidden, discord.HTTPException, discord.InvalidArgument) as e:
            log.error(
                f"Failure while tying to edit message for monitored server '{server.host}:{server.port}', skipping update: {e}"
            )

    def _validate_cached_data(
        self,
        server: monitor_config.MonitoredServer,
        status: etquery.Status,
        message: discord.Message,
    ) -> None:
        # flag update if name is not cached
        if status.name and server.name != status.name:
            log.debug(
                f"Cached server name changed for monitored server '{server.host}:{server.port}': '{server.name}' -> '{status.name}'"
            )
            server.name = status.name
            self._need_config_write = True

        # flag update if message id changed
        if server.message_id != message.id:
            log.debug(
                f"Message ID changed for monitored server '{server.host}:{server.port}': '{server.message_id}' -> '{message.id}'"
            )
            server.message_id = message.id
            self._need_config_write = True

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

        status.location = await asyncio.to_thread(geoip.country_lookup, host)

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
