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

from typing import TYPE_CHECKING, Any, Callable, Coroutine, Generic, Tuple

import discord
from discord.ui.select import BaseSelect, BaseSelectT
from typing_extensions import Self, TypeVarTuple, Unpack

if TYPE_CHECKING:
    from utils.view import BaseView

ITs = TypeVarTuple("ITs")


class BasicInputModal(discord.ui.Modal, Generic[Unpack[ITs]]):
    """A very simple modal that allows other callbacks to wait for its
    completion then manually handle child values.

    Please note this is TypeVarTuple generic, meaning you can do ``BasicInputModal[discord.ui.TextInput[Any], discord.ui.Button[Any]]``
    and the childen will reflect this.
    """

    if TYPE_CHECKING:
        children: Tuple[Unpack[ITs]]

    def __init__(
        self, after: Callable[[Self, discord.Interaction], Coroutine[Any, Any, Any]], *args: Any, **kwargs: Any
    ) -> None:
        self.after: Callable[..., Coroutine[Any, Any, Any]] = after
        super().__init__(*args, **kwargs)

    async def on_submit(self, interaction: discord.Interaction, /) -> None:
        await self.after(self, interaction)
        self.stop()


class AutoRemoveSelect(BaseSelect['BaseView']):
    """A select that removes all children from its parent and replaces them with itself.
    After the user selects an option, the select is removed and the original children are
    added back to the parent.

    Parameters
    ----------
    parent: :class:`BaseView`
        The parent view of the select.
    calback: Callable[[Any, :class:`discord.Interaction`], Coroutine[Any, Any, Any]]
        The callback to be called when the user selects an option.

    Attributes
    ----------
    parent: :class:`BaseView`
        The parent view of the select.
    """

    def __init__(
        self,
        item: BaseSelectT,
        parent: BaseView,
        callback: Callable[[BaseSelectT, discord.Interaction], Coroutine[Any, Any, Any]],
    ) -> None:
        item.__class__.__name__ = self.__class__.__name__
        setattr(item, 'callback', self.callback)

        self.parent: BaseView = parent
        self.item: BaseSelectT = item

        self._callback: Callable[[BaseSelectT, discord.Interaction], Coroutine[Any, Any, Any]] = callback
        self._original_children = parent.children

        parent.clear_items()
        parent.add_item(item)

    async def callback(self, interaction: discord.Interaction) -> Any:
        self.parent.clear_items()
        for child in self._original_children:
            self.parent.add_item(child)

        await self._callback(self.item, interaction)
