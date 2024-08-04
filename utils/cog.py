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

from typing import TYPE_CHECKING, Tuple

from discord.ext import commands

if TYPE_CHECKING:
    from bot import FuryBot

__all__: Tuple[str, ...] = ('BaseCog',)


class BaseCog(commands.Cog):
    """Implementation for a base cog class. This class is meant to be inherited from,
    instead of directly inheriting :class:`commands.Cog`. This is so if you don't have a unique
    :meth:`__init__` you don't have you add it.

    .. note::
        Down the road this will also hold special methods that all cogs can access.

    Parameters
    ----------
    bot: :class:`FuryBot`
        The bot instance.

    Attributes
    ----------
    bot: :class:`Bot`
        The bot instance.
    """

    def __init__(self, bot: FuryBot) -> None:
        self.bot: FuryBot = bot
