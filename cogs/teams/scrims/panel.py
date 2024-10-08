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

import functools
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, Union

import discord
from typing_extensions import Self, Unpack

from utils import BaseView, BaseViewKwargs, SelectOneOfMany, UserSelect, default_button_doc_string

from .persistent import AwayConfirm, HomeConfirm
from .scrim import ScrimStatus

if TYPE_CHECKING:
    from bot import FuryBot

    from ..team import Team
    from .scrim import Scrim


__all__: Tuple[str, ...] = ('TeamScrimsPanel', 'ScrimPanel')


class ScrimPanel(BaseView):
    """Represents a view used to manage a scrim.

    Parameters
    Attributes
    ----------
    team: :class:`.Team`
        The team currently being viewed in the view history.
    scrim: :class:`.Scrim`
        The scrim to manage.
    """

    def __init__(self, team: Team, scrim: Scrim, **kwargs: Unpack[BaseViewKwargs]) -> None:
        self.team: Team = team
        self.scrim: Scrim = scrim
        super().__init__(**kwargs)

    @property
    def embed(self) -> discord.Embed:
        """:class:`discord.Embed`: The embed for this view."""
        home_team = self.scrim.home_team
        away_team = self.scrim.away_team
        if not home_team or not away_team:
            # One of these teams has been deleted, we can only return a dump embed with the anticipation
            # that the scrim will be cancelled.
            return self.bot.Embed(
                title='Team Scrim Information',
                description='This scrim has been cancelled due to a team being deleted.',
            )

        embed = self.team.embed(
            title='Team Scrim Information',
            description=f'This scrim was originally scheduled for {self.scrim.scheduled_for_formatted()}. This scrim is currently **{self.scrim.status.value.replace("_", " ").title()}**.',
        )
        embed.add_field(
            name='Home Team',
            value=(
                f'{home_team.display_name}\n**Confirmed Members**: '
                f'{", ".join([m.mention for m in self.scrim.home_voters]) or "No home voters."}'
            ),
            inline=False,
        )
        embed.add_field(
            name='Away Team',
            value=(
                f'{away_team.display_name}\n**Confirmed Members**: '
                f'{", ".join([m.mention for m in self.scrim.away_voters]) or "No away voters."}'
            ),
        )

        if self.scrim.status is ScrimStatus.scheduled and self.scrim.scheduled_for < discord.utils.utcnow():
            # This scrim has started
            addition = ''
            if self.scrim.scrim_chat:
                addition = f' The scrim chat is {self.scrim.scrim_chat.mention}'

            embed.add_field(
                name='Scrim In Progress', value=f'This scrim is **currently in progress**.{addition}', inline=False
            )

        embed.set_author(name=home_team.display_name, icon_url=home_team.logo)

        embed.set_footer(text=f'Scrim ID: {self.scrim.id}')
        return embed

    async def _manage_member_assignment(
        self,
        interaction: discord.Interaction[FuryBot],
        members: List[Union[discord.Member, discord.User]],
        *,
        add_vote: bool = True,
    ) -> Optional[discord.InteractionMessage]:
        await interaction.response.defer()

        home_team = self.scrim.home_team
        away_team = self.scrim.away_team

        if not home_team or not away_team:
            # One of these teams has been deleted, we must cancel this scrim
            return await self.scrim.cancel(reason='One of the teams has been deleted.')

        for member in members:
            home_member = home_team.get_member(member.id)
            team = home_team if home_member is not None else away_team

            if add_vote:
                await self.scrim.add_vote(member.id, team.id)
            else:
                await self.scrim.remove_vote(member.id, team.id)

        # Let's say we're removing / adding votes and the scrim is now scheduled due
        # to the votes, we should let the team know. #
        # NOTE: We wont cancel the scrim when we force remove votes.
        if self.scrim.status is ScrimStatus.pending_host and self.scrim.home_all_voted:
            # We need to update the scrim status to pending away and send the message
            await self.scrim.change_status(ScrimStatus.pending_away)

            view = HomeConfirm(self.scrim)
            home_message = await self.scrim.home_message()
            if home_message is None:
                # This home message has been deleted, we must cancel the scrim with the reason
                # of it having invalid data.
                await self.scrim.cancel(reason='The home team message has been deleted.')
                return await interaction.edit_original_response(embed=self.embed, view=self)

            await home_message.edit(view=None, embed=view.embed)

            # Send the message to the other channel now
            view = AwayConfirm(self.scrim)
            away_text_channel = away_team.text_channel
            if not away_text_channel:
                # Ths channel, for some reason, has been deleted. We should cancel the scrim.
                await self.scrim.cancel(reason='The away team text channel has been deleted.')
                return await interaction.edit_original_response(embed=self.embed, view=self)

            away_message = await away_text_channel.send(embed=view.embed, view=view)
            await self.scrim.edit(away_message_id=away_message.id)

        elif self.scrim.status is ScrimStatus.pending_away and self.scrim.away_all_voted:
            # We need to change the status to scheduled and edit the messages
            await self.scrim.change_status(ScrimStatus.scheduled)

            view = HomeConfirm(self.scrim)
            home_message = await self.scrim.home_message()
            if home_message is None:
                # This home message has been deleted, we must cancel the scrim with the reason
                # of it having invalid data.
                await self.scrim.cancel(reason='The home team message has been deleted.')
                return await interaction.edit_original_response(embed=self.embed, view=self)

            await home_message.edit(view=None, embed=view.embed)

            view = AwayConfirm(self.scrim)
            away_message = await self.scrim.away_message()
            if away_message:
                await away_message.edit(view=None, embed=view.embed)

        await interaction.edit_original_response(embed=self.embed, view=self)

    @discord.ui.button(label='Remove Confirmation')
    @default_button_doc_string
    async def remove_confirmation(self, interaction: discord.Interaction[FuryBot], button: discord.ui.Button[Self]) -> None:
        """Forcefully remove confirmation for a member."""
        UserSelect(after=functools.partial(self._manage_member_assignment, add_vote=False), parent=self)
        return await interaction.response.edit_message(view=self)

    @discord.ui.button(label='Force Add Confirmation')
    @default_button_doc_string
    async def force_add_confirmation(
        self, interaction: discord.Interaction[FuryBot], button: discord.ui.Button[Self]
    ) -> None:
        """Forcefully add confirmation for a member."""

        UserSelect(after=functools.partial(self._manage_member_assignment, add_vote=True), parent=self)
        return await interaction.response.edit_message(view=self)

    @discord.ui.button(label='Force Schedule Scrim')
    @default_button_doc_string
    async def force_schedule_scrim(
        self, interaction: discord.Interaction[FuryBot], button: discord.ui.Button[Self]
    ) -> Optional[discord.InteractionMessage]:
        """Forcefully set the scrim\'s status to :attr:`.ScrimStatus.scheduled`. This can not be done if the home team hasn't confirmed."""
        if not self.scrim.away_message_id:
            return await interaction.response.send_message(
                'You can not force start a scrim that has not been confirmed by the home team.', ephemeral=True
            )

        await interaction.response.defer()

        await self.scrim.change_status(ScrimStatus.scheduled)

        # Update the home message
        home_message = await self.scrim.home_message()
        if home_message is None:
            # This home message has been deleted, we must cancel the scrim.
            await self.scrim.cancel(reason='The home team message has been deleted.')
            return await interaction.edit_original_response(embed=self.embed, view=self)

        view = HomeConfirm(self.scrim)
        await home_message.edit(embed=view.embed, view=None)

        # Update the away message
        away_message = await self.scrim.away_message()
        if away_message:
            view = AwayConfirm(self.scrim)
            await away_message.edit(embed=view.embed, view=None)

        return await interaction.edit_original_response(embed=self.embed, view=self)

    @discord.ui.button(label='Cancel Scrim', style=discord.ButtonStyle.danger)
    @default_button_doc_string
    async def cancel_scrim(self, interaction: discord.Interaction[FuryBot], button: discord.ui.Button[Self]) -> None:
        """Force cancel the scrim and remove it from the database."""
        await interaction.response.defer()
        await self.scrim.cancel()

        # Go back to the TeamScrimsView, the parent of this view, and edit the original response.
        # We can't go back in the parent tree because I dont want the user to try and edit
        # a cancelled scrim.
        view = TeamScrimsPanel(self.team, target=self.target)
        await interaction.edit_original_response(embed=view.embed, view=view)


class TeamScrimsPanel(BaseView):
    """A view used to manage a teams scrims, alter times, etc.

    Parameters
    Attributes
    ----------
    team: :class:`.Team`
        The team to manage the scrims for.
    """

    def __init__(self, team: Team, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.team: Team = team

    @property
    def embed(self) -> discord.Embed:
        """:class:`discord.Embed`: The embed for this view."""
        embed = self.team.embed(title="Scrims")

        hosted_scrims: int = 0
        for scrim in self.team.scrims:
            if scrim.home_team == self.team:
                hosted_scrims += 1

            home_team_display_name = scrim.home_team and scrim.home_team.display_name or '<Team Deleted>'
            away_team_display_name = scrim.away_team and scrim.away_team.display_name or '<Team Deleted>'

            embed.add_field(
                name=f'Scrim {discord.utils.format_dt(scrim.scheduled_for, "R")}',
                value=f'**Team Created Scrim**: {home_team_display_name}\n'
                f'**Away Team**: {away_team_display_name}\n'
                f'**Status**: {scrim.status.value.title()}\n'
                f'**Home Team Confirmed**: {", ".join([m.mention for m in scrim.home_voters]) or "No home votes."}\n'
                f'**Away Team Confirmed**: {", ".join([m.mention for m in scrim.away_voters]) or "No away votes."}\n',
            )

        embed.description = f'**{len(self.team.scrims)}** scrims total, **{hosted_scrims}** of which they are hosting.'

        if hosted_scrims == 0:
            embed.add_field(name='No Scrims', value='This team has hosted no scrims, only played in them.', inline=False)

        return embed

    async def _manage_a_scrim_callback(self, interaction: discord.Interaction[FuryBot], values: List[str]) -> None:
        scrim = discord.utils.get(self.team.scrims, id=int(values[0]))
        if not scrim:
            # Something really went wrong!
            return await interaction.response.edit_message(embed=self.embed, view=self)

        view = ScrimPanel(self.team, scrim, target=self.target)
        return await interaction.response.edit_message(view=view, embed=view.embed)

    @discord.ui.button(label='Select a Scrim')
    @default_button_doc_string
    async def manage_a_scrim(self, interaction: discord.Interaction[FuryBot], button: discord.ui.Button[Self]) -> None:
        """Allows the user to select a scrim to manage."""
        if not self.team.scrims:
            return await interaction.response.send_message('This team has no scrims.', ephemeral=True)

        SelectOneOfMany(
            self,
            options=[
                discord.SelectOption(
                    label=scrim.scheduled_for.strftime("%A, %B %d, %Y at %I:%M %p"),
                    value=str(scrim.id),
                )
                for scrim in self.team.scrims
            ],
            placeholder='Select a scrim to manage...',
            after=self._manage_a_scrim_callback,
        )

        # The AutoRemoveSelect automatically removes all children
        # and adds itself. Once the select has been completed it will
        # add the children back and call the "_manage_a_scrim_callback" callback for us.
        return await interaction.response.edit_message(view=self)
