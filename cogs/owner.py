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
import re
from types import ModuleType
from typing import TYPE_CHECKING, Annotated, Any, Callable, Coroutine, Dict, List, Optional, Sequence, TypeVar

import discord
from discord.ext import commands
from typing_extensions import ParamSpec

from utils import RUNNING_DEVELOPMENT, BaseCog, Context, human_join

P = ParamSpec('P')
T = TypeVar('T')

if TYPE_CHECKING:
    from bot import FuryBot

_log = logging.getLogger(__name__)
if RUNNING_DEVELOPMENT:
    _log.setLevel(logging.DEBUG)


def to_markdown_table(data: Sequence[Dict[Any, Any]], padding: int = 0) -> str:
    # Get all the keys from the first element.
    keys = list(data[0].keys())

    # Determine the maximum length of each column.
    col_widths = {key: max(len(str(key)), max(len(str(row.get(key, ''))) for row in data)) for key in keys}

    # Adjust column widths for padding.
    col_widths = {key: width + 2 * padding for key, width in col_widths.items()}

    # Create the header row.
    header = '|'.join(f'{" " * padding}{key:<{col_widths[key] - padding}}{" " * padding}' for key in keys)
    header = f'|{header}|'

    # Create the separator row.
    separator = '|'.join(['-' * (col_widths[key] + 2) for key in keys])
    separator = f'|{separator}|'

    # Create the data rows.
    rows: List[str] = []
    for row in data:
        row_data = '|'.join(
            f'{" " * padding}{str(row.get(key, "")):<{col_widths[key] - padding}}{" " * padding}' for key in keys
        )
        row_data = f'|{row_data}|'
        rows.append(row_data)

    return '\n'.join([header, separator, *rows])


def to_code_block(text: str, language: str = '') -> str:
    return f'```{language}\n{text}\n```'


@dataclasses.dataclass()
class ReloadStatus:
    module: str
    statuses: List[Any] = dataclasses.field(default_factory=list)
    exceptions: List[BaseException] = dataclasses.field(default_factory=list)


class CodeBlockStripper(commands.Converter[str]):
    code_block_regex = re.compile(r'\`\`\`(?:\w+)?\n?(?P<code>.+?)\n?\`\`\`', re.DOTALL)

    async def convert(self, ctx: Context, argument: str) -> str:
        # If this is some code block, grab the inner code.
        match = self.code_block_regex.match(argument)
        if match:
            return match.group('code')

        return argument


class Owner(BaseCog):
    async def cog_check(self, ctx: Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @staticmethod
    def _reload_extension(extension: str) -> None:
        module = importlib.import_module(extension)

        try:
            importlib.reload(module)
        except Exception as exc:
            _log.warning('Failed to reload module %s.', extension, exc_info=exc)
            raise exc

    @staticmethod
    def _is_discordpy_extension(spec: importlib.machinery.ModuleSpec, module: ModuleType) -> bool:
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

    @staticmethod
    async def __sql__operation(
        ctx: Context, func: Callable[P, Coroutine[Any, Any, T]], *args: P.args, **kwargs: P.kwargs
    ) -> Optional[T]:
        """
        Does a SQL operation and returns the result. Will let the user know of errors, if any, and return
        ``None`` if an error occurred.
        """
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            await ctx.send(to_code_block(str(exc), language='sql'))
            return None

    @commands.group(invoke_without_command=True, name='sql', description='Run SQL queries.')
    @commands.is_owner()
    async def sql(self, ctx: Context, *, sql: Annotated[str, CodeBlockStripper]) -> Optional[discord.Message]:
        if ctx.invoked_subcommand:
            return None

        return await ctx.invoke(self.execute, sql=sql)

    @sql.command(name='fetchrow', description='Fetch a single row from the database.')
    async def fetchrow(self, ctx: Context, *, sql: Annotated[str, CodeBlockStripper]) -> Optional[discord.Message]:
        async with ctx.typing(), self.bot.safe_connection() as connection:
            _log.debug('Executing SQL query: %s', sql)

            status = await self.__sql__operation(ctx, connection.fetchrow, sql)
            if not status:
                await ctx.message.add_reaction('❌')
                return await ctx.send('No results found.')

            markdown = to_markdown_table([dict(status)], padding=2)
            code_block = to_code_block(markdown, language='sql')
            if len(code_block) > 2000:
                # If the code block is too long, get angry at the user.
                await ctx.message.add_reaction('❌')
                return await ctx.send('The result is too long to display.')

            return await ctx.send(code_block)

    @sql.command(name='fetch', description='Fetch all rows from the database.')
    async def fetch(self, ctx: Context, *, sql: Annotated[str, CodeBlockStripper]) -> Optional[discord.Message]:
        async with ctx.typing(), self.bot.safe_connection() as connection:
            _log.debug('Executing SQL query: %s', sql)

            status = await self.__sql__operation(ctx, connection.fetch, sql)
            if not status:
                await ctx.message.add_reaction('❌')
                return await ctx.send('No results found.')

            markdown = to_markdown_table(list(map(dict, status)), padding=2)
            code_block = to_code_block(markdown, language='sql')
            if len(code_block) > 2000:
                # If the code block is too long, get angry at the user.
                await ctx.message.add_reaction('❌')
                return await ctx.send('The result is too long to display.')

            return await ctx.send(code_block)

    @sql.command(name='execute', description='Execute a query without fetching any results.')
    async def execute(self, ctx: Context, *, sql: Annotated[str, CodeBlockStripper]) -> Optional[discord.Message]:
        async with ctx.typing(), self.bot.safe_connection() as connection:
            _log.debug('Executing SQL query: %s', sql)

            status = await self.__sql__operation(ctx, connection.execute, sql)
            return await ctx.send(to_code_block(str(status), language='sql'))

    @commands.group(name='cache', description='Reload a cache function through the bot.', invoke_without_command=True)
    @commands.is_owner()
    async def cache(self, ctx: Context) -> Optional[discord.Message]:
        if ctx.invoked_subcommand:
            return

        # Show all available cache loading functions on the bot.
        loaders = self.bot.get_cache_functions()
        human_loaders = human_join(loaders.keys(), transform=lambda e: f"`{e}`")
        return await ctx.send(f'Available cache functions: {human_loaders}.')

    @cache.command(name='reload', description='Reload a cache function through the bot.')
    @commands.is_owner()
    async def reload_cache(self, ctx: Context, *cache_names: str) -> Optional[discord.Message]:
        statuses: List[str] = []
        async with ctx.typing(), self.bot.safe_connection() as connection:
            cache_functions = self.bot.get_cache_functions()

            for cache_name in cache_names:
                func = cache_functions.get(cache_name.upper())
                if not func:
                    statuses.append(f'Failed to find cache function `{cache_name}`.')
                    continue

                # If we have found it, call it and store it for later
                await func(self.bot, connection)
                statuses.append(f'Loaded cache function `{cache_name}`.')

        return await ctx.send('\n'.join(statuses))


async def setup(bot: FuryBot):
    await bot.add_cog(Owner(bot))
