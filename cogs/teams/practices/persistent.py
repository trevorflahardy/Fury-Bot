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

from typing import TYPE_CHECKING, Optional, List
from typing_extensions import Self

import discord

if TYPE_CHECKING:
    from bot import FuryBot
    from .practice import Practice, PracticeMember


class UnabletoAttendModal(discord.ui.Modal):
    reason: discord.ui.TextInput[Self] = discord.ui.TextInput(
        label='Why Can\'t You Attend?',
        style=discord.TextStyle.long,
        custom_id="reason-to-not-attend",
        placeholder="Enter why you can\'t attend here.",
        required=True,
    )

    def __init__(self, *, practice: Practice, member: discord.Member) -> None:
        self.practice: Practice = practice
        self.member: discord.Member = member
        super().__init__(timeout=None, title="Why Can't You Attend?")

    async def interaction_check(self, interaction: discord.Interaction, /) -> Optional[bool]:
        if interaction.user != self.member:
            return await interaction.response.send_message("Hey! This isn\'t yours!", ephemeral=True)

        return True

    async def on_submit(self, interaction: discord.Interaction[FuryBot], /) -> None:
        # We need to create a new attending member entry and provide the reason
        await interaction.response.send_message(
            "Thanks for letting me know, I\'ve made a mark on your record.", ephemeral=True
        )

        await self.practice.handle_member_unable_to_join(member=self.member, reason=self.reason.value)


class PracticeView(discord.ui.View):
    def __init__(self, practice: Practice) -> None:
        self.practice: Practice = practice
        super().__init__(timeout=None)

    @property
    def embed(self) -> discord.Embed:
        team = self.practice.team
        started_by = self.practice.started_by

        embed = self.practice.bot.Embed(
            title=f'{team.display_name} Practice.',
            description=f'A practice started by {started_by.mention} on {self.practice.format_start_time()} is currently in progress.',
        )

        embed.add_field(name='Voice Channel', value=self.practice.team.voice_channel.mention, inline=False)

        attending_members: List[PracticeMember] = []
        unable_to_attend: List[PracticeMember] = []
        for member in self.practice.members:
            if not member.attending:
                unable_to_attend.append(member)
            else:
                attending_members.append(member)

        embed.add_field(
            name='Attending Members',
            value='\n'.join([member.mention for member in attending_members]),
            inline=False,
        )

        if unable_to_attend:
            embed.add_field(
                name='Unable to Attend', value='\n'.join([member.mention for member in unable_to_attend]), inline=False
            )

        embed.add_field(
            name='How Do I Attend?',
            value=f'**To attend your team practice, join your team\'s voice channel, {team.voice_channel.mention}. '
            'Your team practice time will be recorded once you leave the voice channel.**',
            inline=False,
        )

        embed.add_field(
            name='I Can\'t Attend!',
            value='Press the "I Can\'t Attend" button below to let us know why you can\'t attend. '
            'This will be recorded on your attendance record.',
        )

        return embed

    async def update_message(self) -> None:
        """|coro|

        Updates the message this persistent view is attached to with the updated embed.

        This is called whenever a practice member joins or leaves a voice channel.
        """
        message_id = self.practice.message_id
        message = await self.practice.team.text_channel.fetch_message(message_id)
        await message.edit(view=self, embed=self.embed)

    @discord.ui.button(label="I Can\'t Attend", style=discord.ButtonStyle.red, custom_id='unable-to-attend')
    async def handle_unable_to_attend(
        self, interaction: discord.Interaction[FuryBot], button: discord.ui.Button[Self]
    ) -> None:
        assert isinstance(interaction.user, discord.Member)
        await interaction.response.send_modal(UnabletoAttendModal(practice=self.practice, member=interaction.user))