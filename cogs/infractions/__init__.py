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

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .dm_notifications import DmNotifications
from .panel import DoesWantToCreateInfractionsSettings, InfractionsSettingsPanel
from .settings import InfractionsSettings

if TYPE_CHECKING:
    from bot import FuryBot


class Infractions(DmNotifications):
    infractions = app_commands.Group(name='infractions', description='Manage infractions.', guild_only=True)

    @infractions.command(name='manage', description='Manage infraction settings.')
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def infractions_manage(self, interaction: discord.Interaction[FuryBot]) -> discord.InteractionMessage:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        settings = await InfractionsSettings.fetch_from_guild_id(interaction.guild.id, bot=self.bot)
        if not settings:
            view = DoesWantToCreateInfractionsSettings(target=interaction)
            return await interaction.edit_original_response(view=view, embed=view.embed)

        panel = InfractionsSettingsPanel(settings=settings, target=interaction)
        return await interaction.edit_original_response(view=panel, embed=panel.embed)


async def setup(bot: FuryBot) -> None:
    await bot.add_cog(Infractions(bot))
