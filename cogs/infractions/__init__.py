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

from typing import TYPE_CHECKING, Union

import discord
from discord import app_commands

from .counter import InfractionCounter
from .dm_notifications import DmNotifications
from .panel import DoesWantToCreateInfractionsSettings, InfractionsSettingsPanel
from .settings import InfractionsSettings as InfractionsSettings

if TYPE_CHECKING:
    from bot import FuryBot


class Infractions(DmNotifications, InfractionCounter):
    infractions = app_commands.Group(
        name='infractions',
        description='Manage infractions.',
        guild_only=True,
        default_permissions=discord.Permissions(moderate_members=True),
    )

    @infractions.command(name='manage', description='Manage infraction settings.')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def infractions_manage(self, interaction: discord.Interaction[FuryBot]) -> discord.InteractionMessage:
        if interaction.guild is None:
            # This shouldn't happen because of the check invariant, but in case it does resolve to a
            # guild then we need to let the developer know to address the issue,
            raise ValueError('This command should only be used in a guild.')

        await interaction.response.defer(ephemeral=True)

        settings = self.bot.get_infractions_settings(interaction.guild.id)
        if not settings:
            view = DoesWantToCreateInfractionsSettings(target=interaction)
            return await interaction.edit_original_response(view=view, embed=view.embed)

        panel = InfractionsSettingsPanel(settings=settings, target=interaction)
        return await interaction.edit_original_response(view=panel, embed=panel.embed)

    @infractions.command(name='count', description='Count the amount of infractions a member has.')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(
        member='The member to count infractions for.',
    )
    @app_commands.guild_only()
    async def infractions_count(
        self, interaction: discord.Interaction[FuryBot], member: discord.Member
    ) -> discord.InteractionMessage:
        if interaction.guild is None:
            # This shouldn't happen because of the check invariant, but in case it does resolve to a
            # guild then we need to let the developer know to address the issue,
            raise ValueError('This command should only be used in a guild.')

        await interaction.response.defer(ephemeral=True)

        settings = self.bot.get_infractions_settings(interaction.guild.id)
        if not settings:
            return await interaction.edit_original_response(
                content='No infractions settings found. Try `/infractions manage` to create them.'
            )

        if not settings.enable_infraction_counter:
            return await interaction.edit_original_response(
                content='Infraction counter is disabled. Enable it in the settings to use this command'
            )

        count = await settings.fetch_infractions_count_from(member.id)
        return await interaction.edit_original_response(content=f'{member.mention} has **{count} total infractions**.')

    @infractions.command(name='recent', description='Show the hyperlink to the most recent infraction.')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(
        member='The member to show the most recent infraction for.',
    )
    @app_commands.guild_only()
    async def infractions_recent(
        self, interaction: discord.Interaction[FuryBot], member: discord.Member
    ) -> discord.InteractionMessage:
        if interaction.guild is None:
            # This shouldn't happen because of the check invariant, but in case it does resolve to a
            # guild then we need to let the developer know to address the issue,
            raise ValueError('This command should only be used in a guild.')

        await interaction.response.defer(ephemeral=True)

        settings = self.bot.get_infractions_settings(interaction.guild.id)
        if not settings:
            return await interaction.edit_original_response(
                content='No infractions settings found. Try `/infractions manage` to create them.'
            )

        if not settings.enable_infraction_counter:
            return await interaction.edit_original_response(
                content='Infraction counter is disabled. Enable it in the settings to use this command'
            )

        infraction = await settings.fetch_most_recent_infraction_from(member.id)
        if not infraction:
            return await interaction.edit_original_response(content=f'{member.mention} has no infractions.')

        return await interaction.edit_original_response(
            content=f'{member.mention}\'s most recent infraction: [**Jump**]({infraction.url})'
        )

    @infractions.command(
        name='clear', description='Clear the infraction history for a target. This only deletes the database data.'
    )
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    @app_commands.describe(
        target='The target to clear. A role clears the all members with the role. A member clears only the member.',
    )
    async def infractions_clear(
        self, interaction: discord.Interaction[FuryBot], target: Union[discord.Member, discord.Role]
    ) -> discord.InteractionMessage:
        if interaction.guild is None:
            # This shouldn't happen because of the check invariant, but in case it does resolve to a
            # guild then we need to let the developer know to address the issue,
            raise ValueError('This command should only be used in a guild.')

        await interaction.response.defer(ephemeral=True)

        settings = self.bot.get_infractions_settings(interaction.guild.id)
        if not settings:
            return await interaction.edit_original_response(
                content='No infractions settings found. Try `/infractions manage` to create them.'
            )

        if not settings.enable_infraction_counter:
            return await interaction.edit_original_response(
                content='Infraction counter is disabled. Enable it in the settings to use this command'
            )

        if isinstance(target, discord.Role):
            members = target.members
            for member in members:
                await settings.clear_infractions(member.id)

            return await interaction.edit_original_response(
                content=f'Cleared all infractions for **{len(members)}** members that have the {target.mention} role.'
            )

        await settings.clear_infractions(target.id)
        return await interaction.edit_original_response(content=f'Cleared all infractions for {target.mention}.')

    # Clears all the infraction history in the guild without a target
    @infractions.command(name='clear-all', description='Clear the infraction history for all members in the guild.')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def infractions_clear_all(self, interaction: discord.Interaction[FuryBot]) -> discord.InteractionMessage:
        if interaction.guild is None:
            # This shouldn't happen because of the check invariant, but in case it does resolve to a
            # guild then we need to let the developer know to address the issue,
            raise ValueError('This command should only be used in a guild.')

        await interaction.response.defer(ephemeral=True)

        settings = self.bot.get_infractions_settings(interaction.guild.id)
        if not settings:
            return await interaction.edit_original_response(
                content='No infractions settings found. Try `/infractions manage` to create them.'
            )

        if not settings.enable_infraction_counter:
            return await interaction.edit_original_response(
                content='Infraction counter is disabled. Enable it in the settings to use this command'
            )

        await settings.clear_all_infractions()
        return await interaction.edit_original_response(content='Cleared all infractions for all members in the guild.')


async def setup(bot: FuryBot) -> None:
    await bot.add_cog(Infractions(bot))
