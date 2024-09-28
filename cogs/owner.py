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

import dataclasses
import importlib.machinery
import importlib.util
import logging
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, List

import discord
from discord.ext import commands

from utils import BaseCog, Context

if TYPE_CHECKING:
    from bot import FuryBot

_log = logging.getLogger(__name__)


@dataclasses.dataclass()
class ReloadStatus:
    module: str
    statuses: List[Any] = dataclasses.field(default_factory=list)
    exceptions: List[BaseException] = dataclasses.field(default_factory=list)


class Owner(BaseCog):
    async def cog_check(self, ctx: Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    def _reload_extension(self, extension: str) -> None:
        module = importlib.import_module(extension)

        try:
            importlib.reload(module)
        except Exception as exc:
            _log.warning(f'Failed to reload module {extension}.', exc_info=exc)
            raise exc

    def _is_discordpy_extension(self, spec: importlib.machinery.ModuleSpec, module: ModuleType) -> bool:
        spec.loader.exec_module(module)  # type: ignore
        return bool(getattr(module, 'setup', None))

    @commands.command(name='reload', description='Reload a module or extension.', aliases=['rl', 'load'])
    async def reload_modules(self, ctx: Context, *modules: str) -> discord.Message:
        async with ctx.typing():
            statuses: Dict[str, ReloadStatus] = {}
            for module_name in modules:
                spec = importlib.util.find_spec(module_name)
                if spec is None:
                    statuses[module_name] = ReloadStatus(
                        module=module_name,
                        exceptions=[commands.errors.ExtensionNotFound(module_name)],
                        statuses=[ctx.tick(False, f'Could not find module_name from name `{module_name}`.')],
                    )
                    continue

                status = ReloadStatus(module=module_name)

                # Try and load the module - if it doesn't exist we need to complain and move on.
                try:
                    module = importlib.import_module(module_name)
                except Exception as exc:
                    status.exceptions.append(exc)
                    status.statuses.append('Failed to load module, unknown exception occurred.')
                    statuses[module_name] = status
                    continue

                try:
                    self._reload_extension(module_name)
                    status.statuses.append(f'Reloaded module `{module_name}` successfully.')
                except Exception as exc:
                    status.exceptions.append(exc)
                    status.statuses.append(f'Failed to reload module `{module_name}`.')

                is_dpy_extension = self._is_discordpy_extension(spec, module)
                if is_dpy_extension:
                    status.statuses.append('Discord.py setup method detected.')

                    try:
                        if module_name in self.bot.extensions:
                            await self.bot.reload_extension(module_name)
                        else:
                            await self.bot.load_extension(module_name)

                        status.statuses.append(ctx.tick(True, label='Reloaded extension without problems.'))
                    except Exception as exc:
                        status.exceptions.append(exc)
                        status.statuses.append('Failed to reload module, unknown exception occurred.')

                status.statuses.append(ctx.tick(True, label='Reloaded entire module without problems.'))
                statuses[module_name] = status

            embed = self.bot.Embed(description='# Reload Statuses')
            for module_name, status in statuses.items():
                for exception in status.exceptions:
                    await self.bot.error_handler.log_error(
                        exception, target=ctx, event_name=f'reload-command-fail:{module_name}'
                    )

                embed.add_field(
                    name=module_name, value='\n'.join(map(lambda status: f'- {status}', status.statuses)), inline=False
                )

        return await ctx.send(embed=embed)


async def setup(bot: FuryBot):
    await bot.add_cog(Owner(bot))
