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

from functools import partial
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Concatenate,
    Coroutine,
    Generic,
    List,
    ParamSpec,
    Tuple,
    TypeAlias,
    TypeVar,
    Union,
)

import discord
from discord.app_commands import AppCommandChannel, AppCommandThread

if TYPE_CHECKING:
    from bot import FuryBot

    from .view import BaseView

__all__: Tuple[str, ...] = (
    'ChannelSelect',
    'UserSelect',
    'RoleSelect',
    'MentionableSelect',
    'SelectOneOfMany',
    'SelectEater',
)

T = TypeVar('T')
P = ParamSpec('P')
ItemT = TypeVar('ItemT', bound='discord.ui.Item[Any]')
SFT = TypeVar('SFT', bound='discord.abc.Snowflake')
SFTC = TypeVar('SFTC', bound='discord.abc.Snowflake', contravariant=True)
ViewMixinT = TypeVar('ViewMixinT', bound='BaseView')
AfterCallback: TypeAlias = Callable[[discord.Interaction['FuryBot'], List[T]], Any]


class ViewChildrenSaver(Generic[ViewMixinT], discord.ui.Item[ViewMixinT]):
    """A helper class to manage the cleanup of a select. This dynamically removes
    all children from its parent and adds them back when the select is closed.
    """

    def __init__(self, parent: ViewMixinT, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._parent: ViewMixinT = parent
        self._original_children: List[discord.ui.Item[ViewMixinT]] = parent.children
        self._parent.clear_items()
        self._parent.add_item(self)
        super().__init__(*args, **kwargs)

    def _readd_children(self) -> Any:
        self._parent.clear_items()
        for child in self._original_children:
            self._parent.add_item(child)


class SelectOneOfMany(Generic[ViewMixinT]):
    """A helper class to manage the cleanup of a select. This dynamically removes
    all children from the parent, and then readds them when the select is closed.

    Parameters
    ----------
    parent: :class:`BaseView`
        The parent view to add the select to.
    options: List[:class:`discord.SelectOption`]
        The options to add to the select.
    after: Callable[[:class:`discord.Interaction`, List[:class:`str`]], Coroutine]
        The callback to call when the select is closed.
    placeholder: :class:`str`
        The placeholder to use for the select.
    max_values: :class:`int`
        The maximum number of values that can be selected.
    """

    def __init__(
        self,
        parent: ViewMixinT,
        /,
        *,
        options: List[discord.SelectOption],
        after: Callable[[discord.Interaction[FuryBot], List[str]], Coroutine[Any, Any, Any]],
        placeholder: str = 'Select one...',
        max_values: int = 1,
    ) -> None:
        self._parent: ViewMixinT = parent
        self._original_children: List[discord.ui.Item[ViewMixinT]] = parent.children
        self._parent.clear_items()

        self._after: Callable[[discord.Interaction[FuryBot], List[str]], Coroutine[Any, Any, Any]] = after

        self.options: List[discord.SelectOption] = options
        for chunk in discord.utils.as_chunks(self.options, 25):
            select: discord.ui.Select[ViewMixinT] = discord.ui.Select(
                options=chunk, placeholder=placeholder, max_values=max_values
            )
            select.callback = partial(self._select_callback, select=select)
            self._parent.add_item(select)

    async def _select_callback(
        self, interaction: discord.Interaction[FuryBot], select: discord.ui.Select[ViewMixinT]
    ) -> None:
        self._parent.clear_items()
        for child in self._original_children:
            self._parent.add_item(child)

        values = select.values
        await self._after(interaction, values)


class RelaySelect(Generic[T, ViewMixinT], ViewChildrenSaver[ViewMixinT], discord.ui.Item[ViewMixinT]):
    """A helper class that will redirect the callback of a select to a different callback.
    This is so we can dynamically handle the callback of a select without having to subclass
    it every time and create repeat code.

    You should never manually create an instance of this class.

    The following classes implement this:

    - :class:`ChannelSelect`
    - :class:`RoleSelect`
    - :class:`UserSelect`
    - :class:`MentionableSelect`

    Example
    -------
    .. code-block:: python3

        class MyView(BaseView):
            async def channel_select_after(self, interaction: discord.Interaction, values: List[Channel], item: ChannelSelect) -> None:
                ...

            @discord.ui.button(label="Click me for a select!")
            async def launch_select(self, interaction: discord.Interaction, button: discord.ui.Button[Self]) -> None:
                select = ChannelSelect(after=self.channel_select_after)
                await respond(view=self)
    """

    def __init__(self, after: AfterCallback[T], parent: ViewMixinT, *args: Any, **kwargs: Any) -> None:
        self.after: AfterCallback[T] = after
        self._parent: ViewMixinT = parent
        super().__init__(parent, *args, **kwargs)

    @property
    def view(self) -> ViewMixinT:
        return self._parent

    async def callback(self, interaction: discord.Interaction[FuryBot]) -> None:
        self._readd_children()
        # It's hard to annotate that this class has access to a "values" property,
        # and that args and kwargs are the correct type. It's MUCH easier to type ignore
        # this and leave it than it is to try and fix it.
        await self.after(interaction, self.values)  # type: ignore


class ChannelSelect(
    RelaySelect[Union[AppCommandChannel, AppCommandThread], ViewMixinT],
    discord.ui.ChannelSelect[ViewMixinT],
):
    """Allows an after parameter to be passed to the callback of a channel select. Optionally,
    you can pass additional args and kwargs to be passed to the callback.
    """

    ...


class RoleSelect(Generic[ViewMixinT], RelaySelect[discord.Role, ViewMixinT], discord.ui.RoleSelect[ViewMixinT]):
    """Allows an after parameter to be passed to the callback of a role select. Optionally,
    you can pass additional args and kwargs to be passed to the callback.
    """

    ...


class UserSelect(
    RelaySelect[Union[discord.Member, discord.User], ViewMixinT],
    discord.ui.UserSelect[ViewMixinT],
):
    """Allows an after parameter to be passed to the callback of a user select. Optionally,
    you can pass additional args and kwargs to be passed to the callback.
    """

    ...


class MentionableSelect(
    RelaySelect[Union[discord.Member, discord.User, discord.Role], ViewMixinT],
    discord.ui.MentionableSelect[ViewMixinT],
):
    """Allows an after parameter to be passed to the callback of a mentionable select. Optionally,
    you can pass additional args and kwargs to be passed to the callback.
    """

    ...


class SelectEater(Generic[P, ViewMixinT]):
    """A normal Select instance works by adding itself to the parent view after removing all the children.
    Under normal circumstances that's okay, but when you want multiple instances it's not going to work. The
    sub-selects will store the original children as their parent selects.. it becomes a nightmare.

    To combat this we're going to do some top-level trickery. We're going to store the parent's children and then
    handle everything special.

    .. code-block:: python3

        eater = SelectEater(after=..., parent=self)
        eater.add_select(RoleSelect(...))
        eater.add_select(UserSelect(...)
    """

    def __init__(
        self,
        after: Callable[Concatenate[discord.Interaction[FuryBot], P], Coroutine[Any, Any, Any]],
        parent: ViewMixinT,
    ) -> None:
        self._after: Callable[Concatenate[discord.Interaction[FuryBot], P], Coroutine[Any, Any, Any]] = after
        self._parent: ViewMixinT = parent
        self._original_children: List[discord.ui.Item[ViewMixinT]] = parent.children

        self._children: List[RelaySelect[Any, ViewMixinT]] = []

        # It's safe to clear the parent's children because we have a copy of them.
        parent.clear_items()

    def add_select(self, select: RelaySelect[Any, ViewMixinT]) -> None:
        select.callback = self._wrapped_callback

        # Every time a RelaySelect instance is created, it will clear the parent's children
        # then add itself. We don't want that, so we're going to clear the parent's children
        # then add all our children back.
        self._parent.clear_items()

        self._children.append(select)

        for child in self._children:
            self._parent.add_item(child)

    def _readd_children(self) -> None:
        for child in self._original_children:
            self._parent.add_item(child)

    async def _wrapped_callback(self, interaction: discord.Interaction[FuryBot], *args: P.args, **kwargs: P.kwargs) -> None:
        self._readd_children()
        await self._after(interaction, *args, **kwargs)
