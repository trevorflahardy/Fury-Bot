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

import logging
from typing import TYPE_CHECKING, Final

import discord
from discord.ext import commands

from utils import RUNNING_DEVELOPMENT, BaseCog

if TYPE_CHECKING:
    from bot import FuryBot

POLL_PERIOD: Final[int] = 25

_log = logging.getLogger(__name__)
if RUNNING_DEVELOPMENT:
    _log.setLevel(logging.DEBUG)


class Tracker(BaseCog):
    def __init__(self, bot: FuryBot) -> None:
        self.bot: FuryBot = bot
        super().__init__(bot)

    @commands.Cog.listener('on_invite_expired_timer_complete')
    async def on_invite_expired_timer_complete(self, guild_id: int, invite_code: str) -> None:
        """Called when an invite expires. Removes the invite from the tracking list."""
        self.bot.remove_invite(guild_id, invite_code)

    @commands.Cog.listener('on_invite_create')
    async def on_invite_created(self, invite: discord.Invite) -> None:
        """Called when an invite is created. Adds the invite to the tracking list."""
        guild = invite.guild
        if not guild:
            return

        _log.debug('Adding invite %s to guild %s', invite.code, guild.id)
        self.bot.add_invite(guild.id, invite)

        # Create a timer for this invite, if it has an expiration date.
        expiration = invite.expires_at
        if not expiration:
            _log.debug('Invite %s does not expire', invite.code)
            return

        _log.debug('Invite %s expires at %s', invite.code, expiration)
        if self.bot.timer_manager:
            await self.bot.timer_manager.create_timer(
                expiration,
                event='invite_expired',
                guild_id=guild.id,
                invite_code=invite.code,
            )

    async def _delete_invite_timer(self, guild_id: int, invite_code: str) -> None:
        async with self.bot.safe_connection() as connection:
            await connection.execute(
                """
                DELETE FROM timers
                WHERE (extra->>'guild_id')::bigint = $1 AND (extra->>'invite_code') = $2
                """,
                guild_id,
                invite_code,
            )

    @commands.Cog.listener('on_invite_delete')
    async def on_invite_deleted(self, invite: discord.Invite) -> None:
        """Called when an invite is deleted. Removes the invite from the tracking list."""
        guild = invite.guild
        if not guild:
            return

        _log.debug('Removing invite %s from guild %s', invite.code, guild.id)

        self.bot.remove_invite(guild.id, invite.code)

        # Try and delete the timer for this as well, if it exists.
        await self._delete_invite_timer(guild.id, invite.code)

    @commands.Cog.listener('on_guild_channel_delete')
    async def on_guild_channel_deleted(self, channel: discord.abc.GuildChannel) -> None:
        """Called when a guild channel is deleted. Removes any invites associated with the channel."""
        guild = channel.guild
        if not guild:
            return

        _log.debug('Removing invites associated with channel %s in guild %s', channel.id, guild.id)

        invites = self.bot.get_invites(guild.id)
        for invite in invites.values():
            invite_channel_id = invite.channel and invite.channel.id

            if invite_channel_id == channel.id:
                self.bot.remove_invite(guild.id, invite.code)

                # Try and delete the timer for this as well, if it exists.
                await self._delete_invite_timer(guild.id, invite.code)

    @commands.Cog.listener('on_guild_join')
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Called when the bot joins a guild. Adds all invites in the guild to the tracking list."""
        _log.debug('Bot joined guild %s, getting all invites.', guild.id)
        invites = await guild.invites()
        for invite in invites:
            self.bot.add_invite(guild.id, invite)

            # Create a timer for this invite, if it has an expiration date.
            expiration = invite.expires_at
            if not expiration:
                continue

            _log.debug('Invite %s expires at %s, creating timer for new guild join', invite.code, expiration)
            if self.bot.timer_manager:
                await self.bot.timer_manager.create_timer(
                    expiration,
                    event='invite_expired',
                    guild_id=guild.id,
                    invite_code=invite.code,
                )

    @commands.Cog.listener('on_guild_available')
    async def on_guild_available(self, guild: discord.Guild) -> None:
        # Fetch all the invites again, in case they were deleted while the bot was offline.
        try:
            invites = await guild.invites()
        except discord.HTTPException:
            invite_mapping = {}
        else:
            invite_mapping = {invite.code: invite for invite in invites}

        async with self.bot.safe_connection() as connection:
            invite_codes = set(invite_mapping.keys())

            existing_timers = await connection.fetch(
                """
                SELECT extra->>'invite_code' AS invite_code
                FROM timers
                WHERE (extra->>'guild_id')::bigint = $1
                AND (extra->>'invite_code')::text = ANY($2)
                """,
                guild.id,
                invite_codes,
            )
            existing_timer_invite_codes = {row['invite_code'] for row in existing_timers}

            # Grab all the invite codes that are missing from the existing timers.
            missing_invite_codes = invite_codes - existing_timer_invite_codes

            for missing_invite_code in missing_invite_codes:
                invite = invite_mapping[missing_invite_code]

                expires_at = invite.expires_at
                if not expires_at:
                    continue

                # This invite is missing from the timers, so we need to create a new timer for it.
                if self.bot.timer_manager:
                    await self.bot.timer_manager.create_timer(
                        expires_at,
                        event='invite_expired',
                        guild_id=guild.id,
                        invite_code=invite.code,
                    )

    @commands.Cog.listener('on_guild_remove')
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Called when the bot leaves a guild. Removes all invites in the guild from the tracking list."""
        self.bot.clear_invites(guild.id)

        # Try and delete all timers associated with this guild.
        async with self.bot.safe_connection() as connection:
            await connection.execute(
                """
                DELETE FROM timers
                WHERE (extra->>'guild_id')::bigint = $1
                """,
                guild.id,
            )

    @commands.Cog.listener('on_member_join')
    async def on_member_join(self, member: discord.Member) -> None:
        invites = await member.guild.invites()
        if not invites:
            _log.debug('No invites found for guild %s', member.guild.id)
            return

        # Sort the invites here by code, so we can compare them later.
        invites.sort(key=lambda i: i.code)

        # Grab the cached invites and sort them by code as well.
        existing_invites = list(self.bot.get_invites(member.guild.id).values())
        existing_invites.sort(key=lambda i: i.code)

        # Zipping the two lists together allows us to compare them in order.
        for old, new in zip(existing_invites, invites):
            _log.debug(
                'Comparing old invite %s to new invite %s (%s vs. %s)', old.code, new.code or 0, old.uses or 0, new.uses or 0
            )

            if (old.uses or 0) < (new.uses or 0):
                # We found the invite that was used. Dispatch a new event here
                # so we can cleanly handle this in another cog or somewhere else.
                _log.debug('Found invite for member %s, dispatching.', member.id)
                self.bot.dispatch('invite_update', member, new)
                return
