""" 
The MIT License (MIT)

Copyright (c) 2020-present NextChai

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import TYPE_CHECKING, List, Literal, Mapping, Optional, Tuple, Type, Union, cast

import discord
from discord.utils import MISSING
from typing_extensions import Self

from utils import QueryBuilder

from . import ScrimStatus
from .persistent import AwayConfirm, AwayForceConfirm, HomeConfirm

if TYPE_CHECKING:
    from bot import FuryBot

    from ..team import Team, TeamMember

__all__: Tuple[str, ...] = ('Scrim',)


@dataclasses.dataclass(init=True, repr=True, eq=True)
class Scrim:
    """Represents a scrim between two teams.

    Parameters
    ----------
    bot: :class:`FuryBot`
        The bot instance.
    id: :class:`int`
        The id of the scrim.
    guild_id: :class:`int`
        The id of the guild the scrim is in.
    creator_id: :class:`int`
        The id of the user who created the scrim.
    per_team: :class:`int`
        The number of players per team.
    home_id: :class:`int`
        The id of the home team.
    away_id: :class:`int`
        The id of the away team.
    home_message_id: :class:`int`
        The id of the message in the home team's text channel.
    away_message_id: :class:`int`
        The id of the message in the away team's text channel.
    status: :class:`ScrimStatus`
        The status of the scrim.
    home_voter_ids: List[:class:`int`]
        The ids of the users who have voted for the home team.
    away_voter_ids: List[:class:`int`]
        The ids of the users who have voted for the away team.
    away_confirm_anyways_voter_ids: List[:class:`int`]
        The ids of the users who have voted to confirm the scrim anyways.
        Defaults to an empty list.
    away_confirm_anyways_message_id: Optional[:class:`int`]
        The id of the message in the away team's text channel.
    scheduled_for: :class:`datetime.datetime`
        The time the scrim is scheduled for.
    scrim_chat_id: Optional[:class:`int`]
        The id of the scrim chat.
    """

    bot: FuryBot
    id: int
    guild_id: int
    creator_id: int
    per_team: int
    home_id: int
    away_id: int
    home_message_id: int
    away_message_id: Optional[int]
    status: ScrimStatus
    home_voter_ids: List[int]
    away_voter_ids: List[int]
    away_confirm_anyways_voter_ids: List[int]
    away_confirm_anyways_message_id: Optional[int]
    scheduled_for: datetime.datetime
    scrim_chat_id: Optional[int]

    # Items for timers
    scrim_scheduled_timer_id: Optional[int]
    scrim_reminder_timer_id: Optional[int]
    scrim_delete_timer_id: Optional[int]

    @classmethod
    async def create(
        cls: Type[Self],
        when: datetime.datetime,
        /,
        *,
        home_team: Team,
        away_team: Team,
        per_team: int,
        creator_id: int,
        bot: FuryBot,
    ) -> Self:
        """|coro|

        A class method to create a new scrim at the given specifications.

        Parameters
        ----------
        when: :class:`datetime.datetime`
            The time the scrim is scheduled for.
        home_team: :class:`Team`
            The home team.
        away_team: :class:`Team`
            The away team.
        per_team: :class:`int`
            The number of players per team.
        creator_id: :class:`int`
            The id of the user who created the scrim.
        bot: :class:`FuryBot`
            The bot instance.
        """
        # Let's create the home message
        status = ScrimStatus.pending_host

        async with bot.safe_connection() as connection:
            data = await connection.fetchrow(
                'INSERT INTO teams.scrims(guild_id, creator_id, per_team, home_id, away_id, status, scheduled_for) '
                'VALUES ($1, $2, $3, $4, $5, $6, $7) '
                'RETURNING *',
                home_team.guild_id,
                creator_id,
                per_team,
                home_team.id,
                away_team.id,
                status.value,
                when,
            )
            assert data

            clean = dict(data)
            clean['status'] = status  # Fix the status

            scrim: Self = cls(bot, **clean)

            # Now send the home message
            home_channel = home_team.text_channel
            view = HomeConfirm(scrim)

            message = await home_channel.send(
                embed=view.embed, view=view, content='@everyone', allowed_mentions=discord.AllowedMentions(everyone=True)
            )
            await scrim.edit(home_message_id=message.id)

        if bot.timer_manager:
            scrim_scheduled_timer = await bot.timer_manager.create_timer(
                when, 'scrim_scheduled', scrim_id=scrim.id, guild_id=home_team.guild_id
            )

            # If the scrim is more than a day out, create a reminder
            scrim_reminder_timer = None
            if (when - discord.utils.utcnow()).days > 1:
                scrim_reminder_timer = await bot.timer_manager.create_timer(
                    when - datetime.timedelta(minutes=30), 'scrim_reminder', scrim_id=scrim.id, guild_id=home_team.guild_id
                )

            await scrim.edit(
                scrim_scheduled_timer_id=scrim_scheduled_timer.id,
                scrim_reminder_timer_id=scrim_reminder_timer and scrim_reminder_timer.id,
            )

        bot.add_scrim(scrim)
        return scrim

    @property
    def home_team(self) -> Team:
        """:class:`Team`: The home team."""
        team = self.bot.get_team(self.home_id, guild_id=self.guild_id)
        assert team
        return team

    @property
    def away_team(self) -> Team:
        """:class:`Team`: The away team."""
        team = self.bot.get_team(self.away_id, guild_id=self.guild_id)
        assert team
        return team

    @property
    def guild(self) -> discord.Guild:
        """Optional[:class:`discord.Guild`]: The guild the scrim is in. Can be None if the guild is not found."""
        return cast(discord.Guild, self.bot.get_guild(self.guild_id))

    @property
    def home_voters(self) -> List[TeamMember]:
        """Get a list of the home team's voters.

        Returns
        --------
        List[:class:`TeamMember`]
        """
        members = self.home_team.team_members
        return [member for (member_id, member) in members.items() if member_id in self.home_voter_ids]

    @property
    def away_voters(self) -> List[TeamMember]:
        """Get a list of the away team's voters.

        Returns
        --------
        List[:class:`TeamMember`]
        """
        members = self.away_team.team_members
        return [member for (member_id, member) in members.items() if member_id in self.away_voter_ids]

    @property
    def away_confirm_anyways_voters(self) -> List[TeamMember]:
        """Get a list of the away team's voters for confirming the scrim anyways.

        Returns
        -------
        List[:class:`TeamMember`]
        """
        members = self.away_team.team_members
        return [member for (member_id, member) in members.items() if member_id in self.away_confirm_anyways_voter_ids]

    @property
    def home_all_voted(self) -> bool:
        """:class:`bool`: Whether the home team has all voted."""
        return len(self.home_voter_ids) >= self.per_team

    @property
    def away_all_voted(self) -> bool:
        """:class:`bool`: Whether the away team has all voted."""
        return len(self.away_voter_ids) >= self.per_team

    @property
    def scrim_chat(self) -> Optional[discord.TextChannel]:
        """Optional[:class:`discord.TextChannel`]: The scrim chat. Can be None if the channel is not found."""
        if not self.scrim_chat_id:
            return None

        return cast(discord.TextChannel, self.guild.get_channel(self.scrim_chat_id))

    def load_persistent_views(self) -> None:
        """A helper method to load the persistent views for the scrim."""
        view = HomeConfirm(self)
        self.bot.add_view(view, message_id=self.home_message_id)

        if self.away_message_id:
            view = AwayConfirm(self)
            self.bot.add_view(view, message_id=self.away_message_id)

        if self.away_confirm_anyways_message_id:
            view = AwayForceConfirm(self)
            self.bot.add_view(view, message_id=self.away_confirm_anyways_message_id)

    def scheduled_for_formatted(self) -> str:
        """:class:`str`: The time the scrim is scheduled for in a human readable format."""
        return f'{discord.utils.format_dt(self.scheduled_for, "F")} ({discord.utils.format_dt(self.scheduled_for, "R")})'

    async def home_message(self) -> discord.Message:
        """|coro|

        Returns
        --------
        :class:`discord.Message`
            The message in the home team's text channel.
        """
        channel = self.home_team.text_channel
        return await channel.fetch_message(self.home_message_id)

    async def away_message(self) -> Optional[discord.Message]:
        """|coro|

        Returns
        --------
        Optional[:class:`discord.Message`]
            The message in the away team's text channel. ``None`` if there is no message in the away channel.
        """
        if not self.away_message_id:
            return None

        channel = self.away_team.text_channel
        return await channel.fetch_message(self.away_message_id)

    async def away_confirm_anyways_message(self) -> Optional[discord.Message]:
        """|coro|

        Fetches the away confirm anyways message.

        Returns
        -------
        Optional[:class:`discord.Message`]
            The message in the away team's text channel. ``None`` if there is no message in the away channel.
        """
        if not self.away_confirm_anyways_message_id:
            return

        channel = self.away_team.text_channel
        return await channel.fetch_message(self.away_confirm_anyways_message_id)

    async def edit(
        self,
        *,
        scrim_chat_id: Optional[int] = MISSING,
        scrim_scheduled_timer_id: Optional[int] = MISSING,
        scrim_reminder_timer_id: Optional[int] = MISSING,
        scrim_delete_timer_id: Optional[int] = MISSING,
        scheduled_for: datetime.datetime = MISSING,
        away_confirm_anyways_message_id: Optional[int] = MISSING,
        away_message_id: Optional[int] = MISSING,
        away_confirm_anyways_voter_ids: List[int] = MISSING,
        home_message_id: int = MISSING,
    ) -> None:
        """|coro|

        Edit the given scrim and edit its state.

        Parameters
        ----------
        scrim_chat_id: Optional[:class:`int`]
            The ID of the scrim chat.
        scrim_scheduled_timer_id: Optional[:class:`int`]
            The ID of the scheduled timer.
        scrim_reminder_timer_id: Optional[:class:`int`]
            The ID of the reminder timer.
        scrim_delete_timer_id: Optional[:class:`int`]
            The ID of the delete timer.
        scheduled_for: :class:`datetime.datetime`
            The time the scrim is scheduled for.
        away_confirm_anyways_message_id: Optional[:class:`int`]
            The ID of the away confirm anyways message.
        away_message_id: Optional[:class:`int`]
            The ID of the away message.
        away_confirm_anyways_voter_ids: List[:class:`int`]
            The IDs of the away team's voters for confirming the scrim anyways.
        home_message_id: :class:`int`
            The ID of the home message.
        """
        builder = QueryBuilder('teams.scrims')
        builder.add_condition('id', self.id)

        if scrim_chat_id is not MISSING:
            builder.add_arg('scrim_chat_id', scrim_chat_id)
            self.scrim_chat_id = scrim_chat_id
        if scrim_scheduled_timer_id is not MISSING:
            builder.add_arg('scrim_scheduled_timer_id', scrim_scheduled_timer_id)
            self.scrim_scheduled_timer_id = scrim_scheduled_timer_id
        if scrim_reminder_timer_id is not MISSING:
            builder.add_arg('scrim_reminder_timer_id', scrim_reminder_timer_id)
            self.scrim_reminder_timer_id = scrim_reminder_timer_id
        if scrim_delete_timer_id is not MISSING:
            builder.add_arg('scrim_delete_timer_id', scrim_delete_timer_id)
            self.scrim_delete_timer_id = scrim_delete_timer_id
        if scheduled_for is not MISSING:
            builder.add_arg('scheduled_for', scheduled_for)
            self.scheduled_for = scheduled_for
        if away_confirm_anyways_message_id is not MISSING:
            builder.add_arg('away_confirm_anyways_message_id', away_confirm_anyways_message_id)
            self.away_confirm_anyways_message_id = away_confirm_anyways_message_id
        if away_message_id is not MISSING:
            builder.add_arg('away_message_id', away_message_id)
            self.away_message_id = away_message_id
        if away_confirm_anyways_voter_ids is not MISSING:
            builder.add_arg('away_confirm_anyways_voter_ids', away_confirm_anyways_voter_ids)
            self.away_confirm_anyways_voter_ids = away_confirm_anyways_voter_ids
        if home_message_id is not MISSING:
            builder.add_arg('home_message_id', home_message_id)
            self.home_message_id = home_message_id

        async with self.bot.safe_connection() as connection:
            await builder(connection)

    async def create_scrim_chat(self) -> discord.TextChannel:
        """|coro|

        A helper method to create the scrim chat and assign the correct permissions to those
        who have opted to play.

        Returns
        -------
        :class:`discord.TextChannel`
            The created text channel.
        """
        overwrites: Mapping[Union[discord.Member, discord.Role], discord.PermissionOverwrite] = {
            m.member or await m.fetch_member(): discord.PermissionOverwrite(view_channel=True)
            for m in [*self.away_team.team_members.values(), *self.home_team.team_members.values()]
        }
        overwrites[self.guild.default_role] = discord.PermissionOverwrite(view_channel=False)

        channel = await self.home_team.category_channel.create_text_channel(
            name='scrim-chat',
            topic=f'Scrim chat for {self.home_team.display_name} vs {self.away_team.display_name}',
            overwrites=overwrites,
        )

        await self.edit(scrim_chat_id=channel.id)

        return channel

    # TODO: Move this to the edit method.
    async def change_status(
        self, status: Literal[ScrimStatus.scheduled, ScrimStatus.pending_away, ScrimStatus.pending_host], /
    ) -> None:
        """|coro|

        Change the status of the scrim.

        Parameters
        ----------
        scrim: :class:`ScrimStatus`
            The new status of the scrim.
        """
        self.status = status

        async with self.bot.safe_connection() as connection:
            await connection.execute('UPDATE teams.scrims SET status = $1 WHERE id = $2', status.value, self.id)

    async def add_vote(self, member_id: int, team_id: int) -> None:
        """|coro|

        Add a vote to the scrim.

        Parameters
        ----------
        member_id: :class:`int`
            The ID of the member who you want to add.
        team_id: :class:`int`
            The ID of the team to cast the vote to.

        Raises
        ------
        ValueError
            The member has already voted.
        """
        if team_id == self.home_id:
            if member_id in self.home_voter_ids:
                raise ValueError('Member has already voted.')

            self.home_voter_ids.append(member_id)
        elif team_id == self.away_id:
            if member_id in self.away_voter_ids:
                raise ValueError('Member has already voted.')

            self.away_voter_ids.append(member_id)
        else:
            raise ValueError(f'Team with id {team_id} is not valid for this scrim.')

        column = 'home_voter_ids' if team_id == self.home_id else 'away_voter_ids'
        async with self.bot.safe_connection() as connection:
            await connection.execute(
                f'UPDATE teams.scrims SET {column} = array_append({column}, $1) WHERE id = $2', member_id, self.id
            )

    async def remove_vote(self, member_id: int, team_id: int) -> None:
        """|coro|

        Remove a vote from the scrim.

        Parameters
        ----------
        member_id: :class:`int`
            The ID of the member who you want to remove.
        team_id: :class:`int`
            The ID of the team to remove the vote from.

        Raises
        ------
        ValueError
            The member has not voted.
        """
        if team_id == self.home_id:
            if member_id not in self.home_voter_ids:
                raise ValueError('Member has not voted.')

            self.home_voter_ids.remove(member_id)
        elif team_id == self.away_id:
            if member_id not in self.away_voter_ids:
                raise ValueError('Member has not voted.')

            self.away_voter_ids.remove(member_id)
        else:
            raise ValueError(f'Team with id {team_id} is not valid for this scrim.')

        column = 'home_voter_ids' if team_id == self.home_id else 'away_voter_ids'
        async with self.bot.safe_connection() as connection:
            await connection.execute(
                f'UPDATE teams.scrims SET {column} = array_remove({column}, $1) WHERE id = $2', member_id, self.id
            )

    async def reschedle(self, when: datetime.datetime, *, editor: discord.abc.User) -> None:
        """Reschedules the scrim for the updated time.

        Parameters
        ----------
        when: :class:`datetime.datetime`
            The new time to schedule the scrim for.
        editor: :class:`discord.abc.User`
            The user who is rescheduling the scrim.
        """
        # Let's update the scrim's messages from the old time to the new time and update the scrim
        await self.edit(scheduled_for=when)

        # Now let's update the messages, if any
        home_message = await self.home_message()
        view = HomeConfirm(self)
        await home_message.edit(embed=view.embed)
        await home_message.reply(
            content=f'@everyone, this scrim has been rescheduled by {editor.mention}',
            allowed_mentions=discord.AllowedMentions(everyone=True, users=False),
        )

        # Check for an away message, if any
        away_message = await self.away_message()
        if away_message is not None:
            view = AwayConfirm(self)
            await away_message.edit(embed=view.embed)
            await away_message.reply(
                content=f'@everyone, this scrim has been rescheduled by a moderator.',
                allowed_mentions=discord.AllowedMentions(everyone=True, users=False),
            )

    async def cancel(self) -> None:
        """|coro|

        Cancels the given scrim and deletes all messages associated with it
        """
        async with self.bot.safe_connection() as connection:
            await connection.execute('DELETE FROM teams.scrims WHERE id = $1', self.id)

            timer_ids: List[int] = []

            if self.scrim_scheduled_timer_id:
                timer_ids.append(self.scrim_scheduled_timer_id)

            if self.scrim_reminder_timer_id:
                timer_ids.append(self.scrim_reminder_timer_id)

            if self.scrim_delete_timer_id:
                timer_ids.append(self.scrim_delete_timer_id)

            if timer_ids:
                await connection.execute('DELETE FROM timers WHERE id = ANY($1)', timer_ids)

        # Just in case the bot was waiting on one of these timers, restart the timer loop
        if self.bot.timer_manager:
            self.bot.timer_manager.restart_task()

        self.bot.remove_scrim(self.id, self.guild_id)

        embed = self.bot.Embed(
            title='Scrim Cancelled',
            description=f'The scrim scheduled for {self.scheduled_for_formatted()} has been cancelled.',
        )
        embed.set_footer(text='This scrim has been cancelled.')

        home_message = await self.home_message()
        await home_message.edit(embed=embed, view=None)
        await home_message.reply(
            '@everyone, this scrim has been cancelled.',
            allowed_mentions=discord.AllowedMentions(everyone=True),
        )

        away_message = await self.away_message()
        if away_message is not None:
            await away_message.edit(embed=embed, view=None)
            await away_message.reply(
                '@everyone, this scrim has been cancelled.',
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )

        away_confirm_anyways = await self.away_confirm_anyways_message()
        if away_confirm_anyways is not None:
            await away_confirm_anyways.delete()

        chat = self.scrim_chat
        if chat is not None:
            await chat.delete()

        # NOTE: Need to add timer deletion here
