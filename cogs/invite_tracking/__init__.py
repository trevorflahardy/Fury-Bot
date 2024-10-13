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
from typing import TYPE_CHECKING, List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from typing_extensions import Unpack

from utils import RUNNING_DEVELOPMENT, BaseButtonPaginator, BaseViewKwargs, Context, human_timestamp

from .tracking import Tracker

if TYPE_CHECKING:
    import asyncpg

    from bot import FuryBot

_log = logging.getLogger(__name__)
if RUNNING_DEVELOPMENT:
    _log.setLevel(logging.DEBUG)


# skipcq: PYL-E0601
class MemberInvitesPaginator(BaseButtonPaginator[asyncpg.Record]):
    def __init__(self, data: List[asyncpg.Record], member: discord.Member, **kwargs: Unpack[BaseViewKwargs]) -> None:
        super().__init__(entries=data, per_page=3, **kwargs)
        self.member: discord.Member = member

    @property
    def total_members_invited(self) -> int:
        return sum(entry['invite_count'] for entry in self.entries)

    def format_page(self, entries: List[asyncpg.Record]) -> discord.Embed:
        embed = self.bot.Embed(
            title=f'{self.member.display_name}\'s Invites',
            description=(
                f'{self.member.display_name} has a total of **{len(self.entries)} invites** '
                f'spanning **{self.total_members_invited:,}** total invited members.\n\n'
                'Note that Fury keeps track of which member joined using which invite, but does not '
                'show it on this paginator. Have a specific member in mind? Use `/invites [member]` '
                'to see which invite they joined from.'
            ),
        )

        for invite in entries:
            expires_at = invite['expires_at']
            expires_at_fmt = human_timestamp(expires_at) if expires_at else 'Does not expire.'
            embed.add_field(
                name=invite['invite_code'],
                value='\n'.join(
                    [
                        f'Created At: {human_timestamp(invite["created_at"])}.',
                        expires_at_fmt,
                        f'Uses: **{invite["invite_count"]} total uses**.',
                    ]
                ),
            )

        return embed


class InviteTracker(Tracker):

    async def _invites_for_member(self, ctx: Context, member: discord.Member) -> discord.Message:
        guild = member.guild
        async with self.bot.safe_connection() as connection:
            # Fetch the invites created by this member in this server and who
            # they have invited.
            data = await connection.fetch(
                """
                SELECT
                    invite_code,
                    created_at,
                    expires_at,
                    uses AS invite_count
                FROM
                    invite_tracker.invites i
                WHERE
                    i.guild_id = $1 AND i.user_id = $2
                """,
                guild.id,
                member.id,
            )

        if not data:
            # This member has not created any invites in this server
            await ctx.send(f'{member.mention} has not created any invites in this server.')

        view = MemberInvitesPaginator(data, member, target=ctx)
        return await ctx.send(embed=view.embed, view=view)

    async def _global_invites(self, ctx: Context) -> None:
        guild = ctx.guild
        if not guild:
            await ctx.send('This command must be used in a guild.')
            return

        # Fetch some invite statistics from this guild, including the top 5 invites,
        # the total number of invites created, and the total number of members invited.
        async with self.bot.safe_connection() as connection:
            data = await connection.fetch(
                """
                SELECT
                    invite_code,
                    created_at,
                    expires_at,
                    uses AS invite_count
                FROM
                    invite_tracker.invites i
                WHERE
                    i.guild_id = $1
                ORDER BY
                    invite_count DESC
                LIMIT 5;
                """,
                guild.id,
            )

            total_invites = await connection.fetchval(
                """
                SELECT
                    SUM(uses)
                FROM
                    invite_tracker.invites i
                WHERE
                    i.guild_id = $1;
                """,
                guild.id,
            )

            total_members_invited = await connection.fetchval(
                """
                SELECT
                    COUNT(DISTINCT user_id)
                FROM
                    invite_tracker.invite_users iu
                JOIN
                    invite_tracker.invites i
                ON
                    i.id = iu.invite_id
                WHERE
                    i.guild_id = $1;
                """,
                guild.id,
            )

        if not data:
            await ctx.send('No invites have been created in this server.')
            return

        embed = self.bot.Embed(
            title='Global Invite Stats',
            description=(
                f'This server has a total of **{total_invites:,} invites** '
                f'and has invited **{total_members_invited:,} members**.'
            ),
        )

        for invite in data:
            expires_at = invite['expires_at']
            expires_at_fmt = human_timestamp(expires_at) if expires_at else 'Does not expire.'
            embed.add_field(
                name=invite['invite_code'],
                value='\n'.join(
                    [
                        f'Created At: {human_timestamp(invite["created_at"])}.',
                        expires_at_fmt,
                        f'Uses: **{invite["invite_count"]} total uses**.',
                    ]
                ),
            )

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="invites", description='See stats about the invites in the server.')
    @commands.guild_only()
    @app_commands.guild_only()
    async def invites(self, ctx: Context, member: Optional[discord.Member] = None) -> None:
        """See stats about the invites in the server.

        If a member is provided, see the invites created by that member. If not, see global stats for
        the guild this command was invoked in.

        Parameters
        ----------
        member: discord.Member
            The member to see the invites for.
        """
        async with ctx.typing(ephemeral=True):
            if member:
                await self._invites_for_member(ctx, member)
            else:
                await self._global_invites(ctx)

    # EVENTS FOR INVITE TRACKING

    async def _log_member_joined_by_invite(self, member: discord.Member, invite: discord.Invite) -> None:
        async with self.bot.safe_connection() as connection:
            # Insert into invite_tracker.invite_uses only if the invite is being tracked
            # in invite_tracker.invites
            await connection.execute(
                """
                INSERT INTO invite_tracker.invite_users (invite_id, user_id, joined_at)
                SELECT i.id, $1, $2
                FROM invite_tracker.invites i
                WHERE i.guild_id = $3 AND i.invite_code = $4
                ON CONFLICT DO UPDATE
                SET joined_at = EXCLUDED.joined_at;
                """,
                member.id,
                discord.utils.utcnow(),
                member.guild.id,
                invite.code,
            )

    @commands.Cog.listener('on_invite_update')
    async def on_invite_update(self, member: discord.Member, invite: discord.Invite) -> None:
        """
        Called when a member has joined a given guild using an invite.

        Updates the invite in the tracking database.

        """
        _log.debug('Invite %s updated', invite.code)

        await self._log_member_joined_by_invite(member, invite)

        uses = invite.uses
        if not uses:
            _log.debug('Invite %s has no uses, cannot do anything.', invite.code)
            return

        guild = member.guild
        async with self.bot.safe_connection() as connection:

            inviter = invite.inviter
            if not inviter:
                # For some reason, the person who created this invite, the inviter, is not available.
                # All we can do is try and make an update in the database (if this invite is being tracked)
                # and return. We cannot insert a new entry
                _log.debug('Fallback to updating invite %s in the database', invite.code)
                await connection.execute(
                    """
                    UPDATE invite_tracker.invites
                    SET uses = $1
                    WHERE guild_id = $2 AND invite_code = $3;
                    """,
                    uses,
                    guild.id,
                    invite.code,
                )
                return

            # Update the invite in the tracking DB
            _log.debug('Updating invite %s in the database for uses %s', invite.code, uses)
            await connection.execute(
                """
                INSERT INTO invite_tracker.invites (
                    guild_id,
                    user_id,
                    invite_code,
                    created_at,
                    expires_at,
                    uses
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (guild_id, invite_code) DO UPDATE
                SET uses = EXCLUDED.uses
                RETURNING id;
                """,
                guild.id,
                inviter.id,
                invite.code,
                invite.created_at,
                invite.expires_at,
                uses,
            )


async def setup(bot: FuryBot) -> None:
    await bot.add_cog(InviteTracker(bot))
