"""
Contributor-Only License v1.0

This file is licensed under the Contributor-Only License. Usage is restricted to
non-commercial purposes. Distribution, sublicensing, and sharing of this file
are prohibited except by the original owner.

Modifications are allowed solely for contributing purposes and must not
misrepresent the original material. This license does not grant any
patent rights or trademark rights.

Full license terms are available in the LICENSE file at the root of the repository.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from concurrent import futures
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Dict,
    Final,
    List,
    Optional,
    ParamSpec,
    Tuple,
    Type,
    TypeAlias,
    TypeVar,
    Union,
)

import asyncpg
import discord
from discord.ext import commands
from typing_extensions import Concatenate, Self

from cogs.images import ApproveOrDenyImage, AttachmentRequestSettings, ImageRequest
from cogs.infractions import InfractionsSettings
from cogs.teams import Team
from cogs.teams.practices import Practice
from cogs.teams.scrims import Scrim, ScrimStatus
from utils import (
    BYPASS_SETUP_HOOK,
    BYPASS_SETUP_HOOK_CACHE_LOADING,
    RUNNING_DEVELOPMENT,
    START_TIMER_MANAGER,
    Context,
    ErrorHandler,
    TimerManager,
    _parse_environ_boolean,
    parse_initial_extensions,
)

if TYPE_CHECKING:
    import datetime

    import aiohttp
    from discord.types.embed import EmbedType

T = TypeVar("T")
P = ParamSpec("P")
PoolType: TypeAlias = "asyncpg.Pool[asyncpg.Record]"
ConnectionType: TypeAlias = "asyncpg.Connection[asyncpg.Record]"
DecoFunc: TypeAlias = Callable[Concatenate["FuryBot", P], Coroutine[T, Any, Any]]
CacheFunc: TypeAlias = Callable[Concatenate["FuryBot", ConnectionType, P], Coroutine[Any, Any, T]]

_log = logging.getLogger(__name__)
if RUNNING_DEVELOPMENT:
    _log.setLevel(logging.DEBUG)

initial_extensions: Tuple[str, ...] = (
    "cogs.infractions",
    "cogs.fun",
    "cogs.images",
    "cogs.flvs",
    "cogs.moderation",
    "cogs.owner",
    "cogs.teams",
    "cogs.teams.practices",
    "cogs.meta",
    "cogs.teams.scrims",
    "jishaku",
    "utils.error_handler",
)


def cache_loader(
    flag_name: str,
) -> Callable[[CacheFunc[P, T]], CacheFunc[P, Optional[T]]]:
    def wrapped(func: CacheFunc[P, T]) -> CacheFunc[P, Optional[T]]:
        @functools.wraps(func)
        async def call_func(self: FuryBot, connection: ConnectionType, *args: P.args, **kwargs: P.kwargs) -> Optional[T]:
            flag = _parse_environ_boolean(f"{flag_name}_CACHE")
            if not flag:
                return None

            _log.info("Loading %s cache from func %s", flag_name, func.__name__)

            try:
                res = await func(self, connection, *args, **kwargs)
            except Exception as exc:
                _log.error("Failed to load %s cache from func %s", flag_name, func.__name__, exc_info=exc)
                return None

            _log.info("Finished loading %s cache from func %s", flag_name, func.__name__)
            return res

        call_func.__cache_loader__ = True  # type: ignore
        call_func.__cache_loader_name__ = flag_name  # type: ignore

        return call_func

    return wrapped


def wrap_extension(coro: DecoFunc[P, T]) -> DecoFunc[P, T]:
    """A method to wrap an extension coroutine in the Bot class. This will handle all
    logging and error handling.

    Parameters
    ----------
    coro: DecoFunc[P, T]
        The coroutine to wrap.

    Returns
    -------
    DecoFunc[P, T]
        A wrapped function that logs and handles errors.
    """

    async def wrapped(self: FuryBot, *args: P.args, **kwargs: P.kwargs) -> T:
        ext_name, *_ = args

        start = time.time()
        try:
            result = await coro(self, *args, **kwargs)
        except commands.ExtensionFailed as exc:
            raise exc.original from exc
        except Exception as exc:
            raise exc from None

        _log.info('Loaded the "%s" extension in %s seconds', ext_name, time.time() - start)
        return result

    return wrapped


class DbContextManager:
    """A simple context manager used to manage database connections.

    Attributes
    ----------
    bot: :class:`FuryBot`
        The bot instance.
    timeout: :class:`float`
        The timeout for acquiring a connection.
    """

    __slots__: Tuple[str, ...] = (
        "bot",
        "timeout",
        "_pool",
        "_Connection",
        "_tr",
        "_connection",
    )

    def __init__(self, bot: FuryBot, *, timeout: Optional[float] = 10.0) -> None:
        self.bot: FuryBot = bot
        self.timeout: Optional[float] = timeout
        self._pool: PoolType = bot.pool
        self._connection: Optional[ConnectionType] = None
        self._tr: Optional[Any] = None

    async def acquire(self) -> ConnectionType:
        return await self.__aenter__()

    async def release(self) -> None:
        await self.__aexit__(None, None, None)

    async def __aenter__(self) -> ConnectionType:
        self._connection = connection = await self._pool.acquire(timeout=self.timeout)  # type: ignore
        self._tr = tr = connection.transaction()
        await tr.start()
        return connection  # type: ignore

    async def __aexit__(
        self,
        exc_type: Optional[Type[Exception]],
        exc: Optional[Exception],
        tb: Optional[Type[Exception]],
    ) -> None:
        if exc and self._tr:
            await self._tr.rollback()

        elif not exc and self._tr:
            await self._tr.commit()

        if self._connection:
            await self._pool.release(self._connection)  # type: ignore


class FuryBot(commands.Bot):
    """The main fury bot instance. This bot subclass contains many useful utilities
    shared between all extensions / cogs.

    Parameters
    ----------
    loop: :class:`asyncio.AbstractEventLoop`
        The current running event loop.
    session: :class:`aiohttp.ClientSession`
        A client session to use for generic requests.
    pool: :class:`asyncpg.Pool`
        A database pool connection to use for requests.
    """

    OWNER_ID: Final[int] = 146348630926819328

    if TYPE_CHECKING:
        user: discord.ClientUser  # This isn't accessed before the client has been logged in so it's OK to overwrite it.
        error_handler: ErrorHandler

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        session: aiohttp.ClientSession,
        pool: PoolType,
    ) -> None:
        self.loop: asyncio.AbstractEventLoop = loop
        self.session: aiohttp.ClientSession = session
        self.pool: PoolType = pool
        self.thread_pool: futures.ThreadPoolExecutor = futures.ThreadPoolExecutor(max_workers=20)
        self.load_time = discord.utils.utcnow()

        self.timer_manager: Optional[TimerManager] = None
        if START_TIMER_MANAGER:
            self.timer_manager = TimerManager(bot=self)

        # Mapping[guild_id, Mapping[team_id, Team]]
        self._team_cache: Dict[int, Dict[int, Team]] = {}

        # Mapping[guild_id, Mapping[scrim_id, Scrim]
        self._team_scrim_cache: Dict[int, Dict[int, Scrim]] = {}

        # Mapping[guild_id, Mapping[team_id, Mapping[practice_id, Practice]]]
        self._team_practice_cache: Dict[int, Dict[int, Dict[int, Practice]]] = {}

        # Mapping[guild_id, InfractionsSettings]
        self._infractions_settings: Dict[int, InfractionsSettings] = {}

        # Mapping[guild_id, Mapping[invite_code, Invite]]
        self._invites_cache: Dict[int, Dict[str, discord.Invite]] = {}

        super().__init__(
            command_prefix=commands.when_mentioned_or("trev.", "trev", 'fury', 'fury.'),
            help_command=None,
            description="A helpful moderation tool",
            intents=discord.Intents.all(),
            strip_after_prefix=True,
            allowed_mentions=discord.AllowedMentions.none(),
            max_messages=5000,
            activity=discord.Game(
                name='Rocket League',
                timestamps={'start': discord.utils.utcnow(), 'end': None},
            ),
        )

    @classmethod
    async def setup_pool(cls: Type[Self], *, uri: str, **kwargs: Any) -> PoolType:
        """:meth: `asyncpg.create_pool` with some extra functionality.

        Parameters
        ----------
        uri: :class:`str`
            The Postgres connection URI.
        **kwargs:
            Extra keyword arguments to pass to :meth:`asyncpg.create_pool`.
        """

        def _encode_jsonb(value: Dict[Any, Any]) -> str:
            return discord.utils._to_json(value)  # skipcq: PYL-W0212

        def _decode_jsonb(value: str) -> Dict[Any, Any]:
            return discord.utils._from_json(value)  # skipcq: PYL-W0212

        old_init = kwargs.pop("init", None)

        async def init(con: asyncpg.Connection[asyncpg.Record]) -> None:
            await con.set_type_codec(
                "jsonb",
                schema="pg_catalog",
                encoder=_encode_jsonb,
                decoder=_decode_jsonb,
                format="text",
            )
            if old_init is not None:
                await old_init(con)

        pool = await asyncpg.create_pool(uri, init=init, **kwargs)
        if not pool:
            raise RuntimeError("Failed to create the pool.")

        return pool

    @staticmethod
    def Embed(
        *,
        colour: Optional[Union[int, discord.Colour]] = None,
        color: Optional[Union[int, discord.Colour]] = None,
        title: Optional[Any] = None,
        type: EmbedType = "rich",  # skipcq: PYL-W0622
        url: Optional[Any] = None,
        description: Optional[Any] = None,
        timestamp: Optional[datetime.datetime] = None,
        author: Optional[Union[discord.User, discord.Member]] = None,
    ) -> discord.Embed:
        """Get an instance of the bot's global :class:`discord.Embed` with the default
        bot's color, "Fury blue".

        The parameters are the same as :class:`discord.Embed` except for one additional one.

        Parameters
        ----------
        author: Optional[Union[:class:`discord.User`, :class:`discord.Member`]]
            An optional author of this embed. When passed, will call :meth:`Embed.set_author` and set
            the author's name nad icon url.

        Returns
        -------
        :class:`discord.Embed`
        """
        embed = discord.Embed(
            title=title,
            description=description,
            url=url,
            color=color,
            colour=colour,
            type=type,
            timestamp=timestamp,
        )

        if not colour and not color:
            embed.colour = discord.Colour.from_str("0x4EDBFC")

        if author:
            embed.set_author(name=author.name, icon_url=author.display_avatar.url)

        return embed

    # Invite cache management
    def get_invite(self, guild_id: int, invite_code: str, /) -> Optional[discord.Invite]:
        return self._invites_cache.get(guild_id, {}).get(invite_code)

    def get_invites(self, guild_id: int, /) -> Dict[str, discord.Invite]:
        return self._invites_cache.get(guild_id, {})

    def get_all_invites(self, /) -> List[discord.Invite]:
        invites: List[discord.Invite] = []
        for guild_id in self._invites_cache:
            invites.extend(self._invites_cache[guild_id].values())

        return invites

    def add_invite(self, guild_id: int, invite: discord.Invite, /, *, label: Optional[str] = None) -> None:
        self._invites_cache.setdefault(guild_id, {})[label or invite.code] = invite

    def set_invites(self, guild_id: int, invite_mapping: Dict[str, discord.Invite], /) -> None:
        self._invites_cache[guild_id] = invite_mapping

    def remove_invite(self, guild_id: int, invite_code: str, /) -> Optional[discord.Invite]:
        return self._invites_cache.get(guild_id, {}).pop(invite_code, None)

    def clear_invites(self, guild_id: int, /) -> None:
        self._invites_cache.pop(guild_id, None)

    # Utilities for finding cache functions
    def get_cache_function(self, cache_flag_name: str) -> Optional[CacheFunc[[], Optional[Any]]]:
        # Walk through all functions on the client and locate the one with
        # "func.__cache_loader_name__" equal to the cache_flag_name
        for _name, func in inspect.getmembers(self, predicate=inspect.iscoroutinefunction):
            if getattr(func, "__cache_loader_name__", None) == cache_flag_name:
                return func

        return None

    def get_cache_functions(self) -> Dict[str, CacheFunc[[], Optional[Any]]]:
        return {
            getattr(func, '__cache_loader_name__'): func
            for _name, func in inspect.getmembers(self, predicate=inspect.iscoroutinefunction)
            if getattr(func, "__cache_loader__", None)
        }

    # Infractions settings management
    def get_infractions_settings(self, guild_id: int, /) -> Optional[InfractionsSettings]:
        """Get the infractions settings for a guild.

        Parameters
        ----------
        guild_id: :class:`int`
            The guild ID to get the settings for.

        Returns
        -------
        Optional[:class:`InfractionsSettings`]
            The infractions settings for the guild.
        """
        return self._infractions_settings.get(guild_id)

    def add_infractions_settings(self, settings: InfractionsSettings, /) -> None:
        """Add infractions settings to the cache.

        Parameters
        ----------
        settings: :class:`InfractionsSettings`
            The settings to add.
        """
        self._infractions_settings[settings.guild_id] = settings

    def remove_infractions_settings(self, guild_id: int, /) -> Optional[InfractionsSettings]:
        """Remove infractions settings from the cache.

        Parameters
        ----------
        guild_id: :class:`int`
            The guild ID to remove the settings for.

        Returns
        -------
        Optional[:class:`InfractionsSettings`]
            The settings that were removed, if they existed.
        """
        return self._infractions_settings.pop(guild_id, None)

    # Team management
    def get_teams(self, guild_id: int, /) -> List[Team]:
        """Get all teams in a guild.

        Parameters
        ----------
        guild_id: :class:`int`
            The guild ID to get teams from.

        Returns
        -------
        List[:class:`Team`]
            The teams in the guild.
        """
        return list(self._team_cache.get(guild_id, {}).values())

    def get_team(self, team_id: int, /, *, guild_id: int) -> Optional[Team]:
        """Get a team from a guild.

        Parameters
        ----------
        team_id: :class:`int`
            The team ID to get.
        guild_id: :class:`int`
            The guild ID to get the team from.

        Returns
        -------
        Optional[:class:`Team`]
            The team, if it exists.
        """
        return self._team_cache.get(guild_id, {}).get(team_id)

    def get_team_from_channel(self, channel_id: int, guild_id: int, /) -> Optional[Team]:
        return Team.from_channel(channel_id, guild_id, bot=self)

    def add_team(self, team: Team, /) -> None:
        """Add a team to the cache.

        Parameters
        ----------
        team: :class:`Team`
            The team to add.
        """
        self._team_cache.setdefault(team.guild_id, {})[team.id] = team

    def remove_team(self, team_id: int, guild_id: int, /) -> Optional[Team]:
        """Remove a team from the cache.

        Parameters
        ----------
        team_id: :class:`int`
            The team ID to remove.
        guild_id: :class:`int`
            The guild ID to remove the team from.

        Returns
        -------
        Optional[:class:`Team`]
            The team that was removed, if it existed.
        """
        return self._team_cache.get(guild_id, {}).pop(team_id, None)

    # Scrim Management
    def get_scrim(self, scrim_id: int, guild_id: int, /) -> Optional[Scrim]:
        """Get a scrim from a guild.

        Parameters
        ----------
        scrim_id: :class:`int`
            The scrim ID to get.
        guild_id: :class:`int`
            The guild ID to get the scrim from.

        Returns
        -------
        Optional[:class:`Scrim`]
            The scrim, if it exists.
        """
        return self._team_scrim_cache.get(guild_id, {}).get(scrim_id)

    def add_scrim(self, scrim: Scrim, /) -> None:
        """Add a scrim to the cache.

        Parameters
        ----------
        scrim: :class:`Scrim`
            The scrim to add.
        """
        self._team_scrim_cache.setdefault(scrim.guild_id, {})[scrim.id] = scrim

    def remove_scrim(self, scrim_id: int, guild_id: int, /) -> Optional[Scrim]:
        """Remove a scrim from the cache.

        Parameters
        ----------
        scrim_id: :class:`int`
            The scrim ID to remove.
        guild_id: :class:`int`
            The guild ID to remove the scrim from.

        Returns
        -------
        Optional[:class:`Scrim`]
            The scrim that was removed, if it existed.
        """
        return self._team_scrim_cache.get(guild_id, {}).pop(scrim_id, None)

    def get_scrims_for(self, team_id: int, guild_id: int, /) -> List[Scrim]:
        """Get all scrims for the given team in the given guild.

        Parameters
        ----------
        team_id: :class:`int`
            The team ID to get scrims for.
        guild_id: :class:`int`
            The guild ID to get scrims from.

        Returns
        -------
        List[:class:`Scrim`]
            The scrims for the team in the guild.
        """
        guild_scrims = self._team_scrim_cache.get(guild_id)
        if guild_scrims is None:
            return []

        scrims: List[Scrim] = []
        for scrim in guild_scrims.values():
            if team_id in {scrim.home_id, scrim.away_id}:
                scrims.append(scrim)

        return scrims

    # Practice Management
    def get_practice(self, practice_id: int, team_id: int, guild_id: int, /) -> Optional[Practice]:
        """Get a practice from a guild.

        Parameters
        ----------
        practice_id: :class:`int`
            The practice ID to get.
        team_id: :class:`int`
            The team ID to get the practice from.
        guild_id: :class:`int`
            The guild ID to get the practice from.

        Returns
        -------
        Optional[:class:`Practice`]
            The practice, if it exists.
        """
        return self._team_practice_cache.get(guild_id, {}).get(team_id, {}).get(practice_id)

    def get_practices(self, guild_id: int, /) -> List[Practice]:
        """Get all practices in a guild.

        Parameters
        ----------
        List[:class:`Practice`]
            The practices in the guild.
        """
        guild_practices = self._team_practice_cache.get(guild_id, {})

        practices: List[Practice] = []
        for team_practices in guild_practices.values():
            practices.extend(team_practices.values())

        return practices

    def add_practice(self, practice: Practice) -> None:
        """Add a practice to the cache.

        Parameters
        ----------
        practice: :class:`Practice`
            The practice to add.
        """
        self._team_practice_cache.setdefault(practice.guild_id, {}).setdefault(practice.team_id, {})[practice.id] = practice

    def remove_practice(self, practice_id: int, team_id: int, guild_id: int, /) -> Optional[Practice]:
        """Remove a practice from the cache.

        Parameters
        ----------
        practice_id: :class:`int`
            The practice ID to remove.
        team_id: :class:`int`
            The team ID to remove the practice from.
        guild_id: :class:`int`
            The guild ID to remove the practice from.

        Returns
        -------
        Optional[:class:`Practice`]
            The practice that was removed, if it existed.
        """
        return self._team_practice_cache.get(guild_id, {}).get(team_id, {}).pop(practice_id, None)

    def clear_practices_for(self, team_id: int, guild_id: int, /) -> None:
        """Clear all practices for a team in a guild.

        Parameters
        ----------
        team_id: :class:`int`
            The team ID to clear practices for.
        guild_id: :class:`int`
            The guild ID to clear practices from.
        """
        self._team_practice_cache.get(guild_id, {}).pop(team_id, None)

    def get_practices_for(self, team_id: int, guild_id: int, /) -> List[Practice]:
        """Get all practices for the given team in the given guild.

        Parameters
        ----------
        team_id: :class:`int`
            The team ID to get practices for.
        guild_id: :class:`int`
            The guild ID to get practices from.

        Returns
        -------
        List[:class:`Practice`]
            The practices for the team in the guild.
        """
        guild_practices = self._team_practice_cache.get(guild_id)
        if guild_practices is None:
            return []

        return list(guild_practices.get(team_id, {}).values())

    # Events
    async def on_ready(self) -> None:
        """|coro|

        Called when the client has hit READY. Please note this can be called more than once during the clients
        uptime.
        """
        _log.info("Logged in as %s", self.user.name)

        total_guilds = len(self.guilds)
        _log.info("Connected to %s servers total.", total_guilds)

        invite = discord.utils.oauth_url(self.user.id, permissions=discord.Permissions(0))
        _log.info("Invite link: %s", invite)

    async def get_context(
        self,
        origin: Union[discord.Message, discord.Interaction[Self]],  # cls: Type[commands.Context[Self]] = Context
    ) -> Context:
        return await super().get_context(origin, cls=Context)

    # Helper utilities
    def safe_connection(self, *, timeout: Optional[float] = 10.0) -> DbContextManager:
        """A context manager that will acquire a Connection from the bot's pool.

        This will neatly manage the Connection and release it back to the pool when the context is exited.

        .. code-block:: python3

            async with bot.safe_connection(timeout=10) as connection:
                await connection.execute('SELECT 1')
        """
        return DbContextManager(self, timeout=timeout)

    def create_task(self, coro: Coroutine[T, Any, Any], *, name: Optional[str] = None) -> asyncio.Task[T]:
        """Create a task from a coroutine object.

        Parameters
        ----------
        coro: :class:`~asyncio.Coroutine`
            The coroutine to create the task from.
        name: Optional[:class:`str`]
            The name of the task.

        Returns
        -------
        :class:`~asyncio.Task`
            The task that was created.
        """

        return self.loop.create_task(coro, name=name)

    def wrap(self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> asyncio.Future[T]:
        """|coro|

        A helper function to bind blocking cpu bound functions to the event loop to make them not blocking.


        Parameters
        ----------
        func: Callable[P, T]
            The function to wrap.
        *args: P.args
            The arguments to pass to the function.
        **kwargs: P.kwargs
            The keyword arguments to pass to the function.

        Returns
        -------
        asyncio.Future[T]
            The future that will be resolved when the function is done.
        """
        return self.loop.run_in_executor(self.thread_pool, functools.partial(func, *args, **kwargs))

    @wrap_extension
    async def load_extension(self, name: str, /, *, package: Optional[str] = None) -> None:
        return await super().load_extension(name, package=package)

    @wrap_extension
    async def reload_extension(self, name: str, /, *, package: Optional[str] = None) -> None:
        return await super().reload_extension(name, package=package)

    @wrap_extension
    async def unload_extension(self, name: str, /, *, package: Optional[str] = None) -> None:
        return await super().unload_extension(name, package=package)

    async def __verify_invite_expiration_timers(
        self, guild_id: int, invites: Dict[str, discord.Invite], connection: ConnectionType
    ) -> None:
        # Ensure that every invite that has an expiration time has a timer set
        # waiting for it to expire. This ensures that, for some reason, if a invite is created
        # while the bot is down we still have new timers for all them.

        # Fetch all the invites from this guild (guild_id in extra JSONB field == guild_id)
        existing_timers = await connection.fetch(
            """
            SELECT (extra->>'invite_code')::bigint AS invite_code FROM timers WHERE (extra->>'guild_id')::bigint = $1;
            """,
            guild_id,
        )
        existing_invite_codes = {entry['invite_code'] for entry in existing_timers}

        for invite_code, invite in invites.items():
            if invite_code in existing_invite_codes:
                continue

            if invite.expires_at and self.timer_manager:
                # This invite has an expiration time, we need to set a timer for it
                # to expire.
                await self.timer_manager.create_timer(
                    invite.expires_at,
                    event='invite_expired',
                    guild_id=guild_id,
                    invite_code=invite_code,
                )

    async def __cache_invites_load_guild(self, guild: discord.Guild, connection: ConnectionType) -> None:
        try:
            invites = await guild.invites()
        except discord.HTTPException:
            return None

        fetched = {invite.code: invite for invite in invites}
        self.set_invites(guild.id, fetched or {})

        if 'VANITY_URL' in guild.features:
            try:
                vanity = await guild.vanity_invite()
            except discord.HTTPException:
                # This vanity url, for some reason, failed to be fetched.
                # We'll just ignore it.
                pass
            else:
                if vanity:
                    self.add_invite(guild.id, vanity, label='VANITY')

        all_invites = self.get_invites(guild.id)
        await self.__verify_invite_expiration_timers(guild.id, all_invites, connection)

    @cache_loader('INVITES')
    async def _cache_invites(self, connection: ConnectionType) -> None:
        await self.wait_until_ready()

        tasks: List[asyncio.Task[None]] = []
        for guild in self.guilds:
            tasks.append(self.create_task(self.__cache_invites_load_guild(guild, connection)))

        await asyncio.gather(*tasks)

    @cache_loader('INFRACTIONS_SETTINGS')
    async def _cache_infractions_settings(self, connection: ConnectionType) -> None:
        infraction_settings = await connection.fetch('SELECT * FROM infractions.settings')

        for record in infraction_settings:
            settings = InfractionsSettings(data=dict(record), bot=self)
            self.add_infractions_settings(settings)

    @cache_loader("TEAMS")
    async def _cache_setup_teams(self, connection: ConnectionType) -> None:
        # NOTE: Look into views for this later down the road or something
        team_data = await connection.fetch("SELECT * FROM teams.settings")
        if not team_data:
            _log.debug("No teams to load.")
            return

        for entry in team_data:
            team_id = entry['id']
            member_data = await connection.fetch("SELECT * FROM teams.members WHERE team_id = $1", team_id)
            captain_data = await connection.fetch("SELECT * FROM teams.captains WHERE team_id = $1", team_id)

            team = Team.from_raw(dict(entry), list(map(dict, member_data)), list(map(dict, captain_data)), bot=self)
            self.add_team(team)
            _log.debug('Loaded team %s (%s)', team.display_name, team.id)

    @cache_loader("SCRIMS")
    async def _cache_setup_scrims(self, connection: ConnectionType) -> None:
        scrim_records = await connection.fetch("SELECT * FROM teams.scrims")

        for entry in scrim_records:
            data = dict(entry)
            data["status"] = ScrimStatus(data["status"])

            scrim = Scrim(self, **data)
            scrim.load_persistent_views()
            self._team_scrim_cache.setdefault(scrim.guild_id, {})[scrim.id] = scrim

    async def _load_image_request(self, data: asyncpg.Record, connection: ConnectionType) -> None:
        await self.wait_until_ready()

        # Fetch the request guild
        settings = await AttachmentRequestSettings.fetch_from_id(data['request_settings'], bot=self)
        if not settings:
            # This does not exist anymore, we cannot load it
            return

        guild = settings.guild
        channel = settings.channel
        if not guild or not channel:
            return

        attachment_data = data['attachment_payload']

        try:
            requester = guild.get_member(data['requester_id']) or await guild.fetch_member(data['requester_id'])
        except discord.NotFound:
            return

        request = ImageRequest(
            requester=requester,
            attachment=discord.Attachment(data=attachment_data, state=self._connection),
            channel=channel,
            message=data["message"],
            id=data["id"],
        )

        view = ApproveOrDenyImage(self, request)
        self.add_view(view, message_id=data["message_id"])

    @cache_loader("IMAGE_REQUESTS")
    async def _cache_setup_image_requests(self, connection: ConnectionType) -> None:
        image_requests = await connection.fetch(
            "SELECT * FROM images.requests WHERE denied_reason IS NULL OR message_id IS NULL;"
        )
        for request in image_requests:
            await self._load_image_request(request, connection=connection)

    @cache_loader("PRACTICES")
    async def _cache_setup_practices(self, connection: ConnectionType) -> None:
        practice_data = await connection.fetch("SELECT * FROM teams.practice")
        practice_member_data = await connection.fetch("SELECT * FROM teams.practice_member")
        practice_member_history_data = await connection.fetch("SELECT * FROM teams.practice_member_history")

        # Sort the member data to be {practice_id: {member_id: data}} because we can have more than one member per practice
        practice_member_mapping: Dict[int, Dict[int, Dict[Any, Any]]] = {}
        for entry in practice_member_data:
            practice_member_mapping.setdefault(entry["practice_id"], {})[entry["member_id"]] = dict(entry)

        # Sort the member history data to be {practice_id: {member_id: List[data]}} because we an have more than one
        # history entry per member per practice
        practice_member_history_mapping: Dict[int, Dict[int, List[Dict[Any, Any]]]] = {}
        for entry in practice_member_history_data:
            practice_member_history_mapping.setdefault(entry["practice_id"], {}).setdefault(entry["member_id"], []).append(
                dict(entry)
            )

        for entry in practice_data:
            # We need to create a practice from this
            practice = Practice(bot=self, data=dict(entry))

            member_data = practice_member_mapping.get(practice.id, {})
            for data in member_data.values():
                member = practice.add_member(dict(data))

                member_practice_history = practice_member_history_mapping.get(practice.id, {}).get(member.member_id, [])
                for history_entry in member_practice_history:
                    member.add_history(dict(history_entry))

            self._team_practice_cache.setdefault(practice.guild_id, {}).setdefault(practice.team_id, {})[
                practice.id
            ] = practice

    # Hooks
    async def setup_hook(self) -> None:
        if BYPASS_SETUP_HOOK:
            return

        extensions_to_load = parse_initial_extensions(initial_extensions)

        await asyncio.gather(*(self.load_extension(ext) for ext in extensions_to_load))

        if BYPASS_SETUP_HOOK_CACHE_LOADING:
            _log.info("Bypassing cache loading.")
            return

        cache_loading_functions: List[Tuple[str, Callable[..., Coroutine[Any, Any, Any]]]] = [
            item
            for item in inspect.getmembers(self, predicate=inspect.iscoroutinefunction)
            if getattr(item[1], "__cache_loader__", None)
        ]

        _log.info("Loading %s cache entries.", len(cache_loading_functions))

        async def _wrapped_cache_loader(
            cache_loading_function: Callable[..., Coroutine[Any, Any, Any]],
        ) -> None:
            async with self.safe_connection() as connection:
                try:
                    await cache_loading_function(connection=connection)
                except Exception as exc:
                    _log.warning(
                        "Failed to load cache entry %s.",
                        cache_loading_function.__name__,
                        exc_info=exc,
                    )

        for _, func in cache_loading_functions:
            self.create_task(_wrapped_cache_loader(func))

        _log.debug("Finished loading cache entries.")
