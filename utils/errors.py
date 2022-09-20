from typing import Any, Tuple

import discord
from discord import app_commands


class ApplicationCommandException(app_commands.AppCommandError):

    """A custom exception raised when an operation fails in an application command's
    callback.

    This inherits :class:`discord.AppCommandError` and :class:`BotException`.

    Parameters
    ----------
    interaction: :class:`discord.Interaction`
        The interaction created from the command invocation.

    Attributes
    ----------
    interaction: :class:`discord.Interaction`
        The interaction created from the command invocation.
    """

    __slots__: Tuple[str, ...] = ()

    def __init__(self, interaction: discord.Interaction, *args: Any, **kwargs: Any) -> None:
        self.interaction: discord.Interaction = interaction
        super().__init__(*args, **kwargs)


class AutocompleteValidationException(ApplicationCommandException, app_commands.TransformerError):
    """An exception raised when validating the input from an autocomplete
    fails.

    This inherits :class:`ApplicationCommandException`.
    """

    pass


class BadArgument(ApplicationCommandException):
    """An exception raised when a command argument is invalid.

    This inherits :class:`ApplicationCommandException`.
    """

    pass


class TimerNotFound(Exception):
    """An exception raised when a timer is not found.

    This inherits from :class:`BotException`

    Parameters
    ----------
    id: :class:`int`
        The ID of the timer that was not found.

    Attributes
    ----------
    id: :class:`int`
        The ID of the timer.
    """

    __slots__: Tuple[str, ...] = ('id',)

    def __init__(self, id: int) -> None:
        super().__init__(f'Timer {id} was not found!')
        self.id: int = id