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

import discord
from typing import TYPE_CHECKING, Tuple
from utils import BaseCog
import datetime
from discord.ext import commands

if TYPE_CHECKING:
    from bot import FuryBot
    from .scrim import Scrim, ScrimStatus

__all__: Tuple[str, ...] = ('ScrimEventListener',)


class ScrimEventListener(BaseCog):
    @classmethod
    def _create_scrim_cancelled_message(cls, bot: FuryBot, scrim: Scrim) -> discord.Embed:
        """Creates an embed detailing that a scrim has been cancelled.

        Parameters
        ----------
        bot: :class:`FuryBot`
            The bot instance.
        scrim: :class:`Scrim`
            The scrim that was cancelled.

        Returns
        -------
        :class:`discord.Embed`
            The embed detailing that a scrim has been cancelled.
        """
        home_embed = bot.Embed(
            title='This scrim has been cancelled.',
            description='There were not enough votes to start the scrim.\n\n'
            f'**Votes Needed from {scrim.home_team.display_name,}**: {scrim.per_team - len(scrim.home_voter_ids)}\n'
            f'**Votes Needed from {scrim.away_team.display_name}**: {scrim.per_team - len(scrim.away_voter_ids)}',
        )
        home_embed.add_field(
            name=f'{scrim.home_team.display_name} Team Votes',
            value=', '.join(m.mention for m in scrim.home_voters) or 'No members have voted.',
        )
        home_embed.add_field(
            name=f'{scrim.away_team.display_name} Team Votes',
            value=', '.join(m.mention for m in scrim.away_voters) or 'No members have voted.',
        )

        return home_embed

    # Timer listeners for scrim
    @commands.Cog.listener('on_scrim_scheduled_timer_complete')
    async def on_scrim_scheduled_timer_complete(self, *, scrim_id: int, guild_id: int) -> None:
        """|coro|

        A scrim listener that is called when a scrim has been scheduled for a certain time. This
        will check if the scrim has been confirmed then create the messages, views, and chats for the scrim.

        Parameters
        ----------
        scrim_id: :class:`int`
            The id of the scrim that has been scheduled.
        guild_id: :class:`int`
            The id of the guild that the scrim is in.
        """
        scrim = self.bot.get_scrim(scrim_id, guild_id)
        if scrim is None:
            return

        # If the scrim isn't scheduled we want to edit the messages and say that the scrim didnt start
        if scrim.status is not ScrimStatus.scheduled:
            cancelled_embed = self._create_scrim_cancelled_message(self.bot, scrim)

            home_message = await scrim.home_message()
            await home_message.edit(embed=cancelled_embed, view=None, content=None)

            # Reply to it and ping the members of this change
            await home_message.reply(
                content='@everyone, please note this scrim did not start.',
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )

            away_message = await scrim.away_message()
            if away_message is not None:
                await home_message.edit(embed=cancelled_embed, view=None, content=None)
                await home_message.reply(
                    content='@everyone, please note this scrim did not start.',
                    allowed_mentions=discord.AllowedMentions(everyone=True),
                )

            return

        scrim_chat = await scrim.create_scrim_chat()

        embed = self.bot.Embed(
            title=f'{scrim.home_team.display_name} vs {scrim.away_team.display_name}',
            description=f'Scrim has been scheduled and confirmed for {scrim.scheduled_for_formatted()}',
        )
        embed.add_field(name=scrim.home_team.display_name, value=', '.join(m.mention for m in scrim.home_voters))
        embed.add_field(name=scrim.away_team.display_name, value=', '.join(m.mention for m in scrim.away_voters))
        embed.set_footer(text='This channel will automatically delete in 4 hours.')
        await scrim_chat.send(embed=embed)

        # Create a timer to delete this channel in 4 hours and delete the scrim.
        if self.bot.timer_manager:
            scrim_delete_timer = await self.bot.timer_manager.create_timer(
                discord.utils.utcnow() + datetime.timedelta(hours=4), 'scrim_delete', scrim_id=scrim_id, guild_id=guild_id
            )
            await scrim.edit(scrim_delete_timer_id=scrim_delete_timer.id)

    @commands.Cog.listener('on_scrim_delete_timer_complete')
    async def on_scrim_delete_timer_complete(self, *, scrim_id: int, guild_id: int) -> None:
        """|coro|

        After N time the scrim and its chats are automatically deleted. This is what this listener
        is for.

        Parameters
        ----------
        scrim_id: :class:`int`
            The id of the scrim that has ended.
        guild_id: :class:`int`
            The id of the guild that the scrim is in.
        """
        scrim = self.bot.remove_scrim(scrim_id, guild_id)
        if not scrim:
            return

        # Delete the scrim chat
        chat = scrim.scrim_chat
        if chat is not None:
            await chat.delete()

        # Delete this scrim from the database
        async with self.bot.safe_connection() as connection:
            await connection.execute('DELETE FROM teams.scrims WHERE id = $1', scrim.id)

    @commands.Cog.listener('on_scrim_reminder_timer_complete')
    async def on_scrim_reminder_timer_complete(self, *, scrim_id: int, guild_id: int) -> None:
        """|coro|

        The scrim reminder timer. This will send a reminder to both teams that the scrim is about to start
        in 30 minutes.

        Parameters
        ----------
        scrim_id: :class:`int`
            The id of the scrim that is about to start.
        guild_id: :class:`int`
            The id of the guild that the scrim is in.
        """
        scrim = self.bot.get_scrim(scrim_id, guild_id)
        if not scrim:
            return

        home_message = await scrim.home_message()
        if scrim.status is ScrimStatus.scheduled:
            content = f'@everyone, this scrim is scheduled to start on {scrim.scheduled_for_formatted()}. Please be ready, a team chat will be created at that time.'
            await home_message.reply(content, allowed_mentions=discord.AllowedMentions(everyone=True))

            away_message = await scrim.away_message()
            if away_message:
                await away_message.reply(content, allowed_mentions=discord.AllowedMentions(everyone=True))

        elif scrim.status is ScrimStatus.pending_host:
            content = f'@everyone, this scrim is scheduled to start on {scrim.scheduled_for_formatted()} '
            'and I do not have enough votes from this team to confirm the scrim. **I\'m going to cancel this '
            'scrim as it\'s very unlikely the other team will confirm in time**.'
            await home_message.reply(content, allowed_mentions=discord.AllowedMentions(everyone=True))
            await scrim.cancel()

        elif scrim.status is ScrimStatus.pending_away:
            content = f'@everyone, this scrim is scheduled to start on {scrim.scheduled_for_formatted()} and I\'m waiting '
            f'on {scrim.per_team - len(scrim.away_voter_ids)} vote(s) from {scrim.away_team.display_name}.'
