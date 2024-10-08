"""
This type stub file was generated by pyright.
"""

"""
parsedatetime/context.py

Context related classes

"""

class pdtContextStack:
    """
    A thread-safe stack to store context(s)

    Internally used by L{Calendar} object
    """

    def __init__(self) -> None: ...
    def push(self, ctx): ...
    def pop(self): ...
    def last(self): ...
    def isEmpty(self): ...

class pdtContext:
    """
    Context contains accuracy flag detected by L{Calendar.parse()}

    Accuracy flag uses bitwise-OR operation and is combined by:

        ACU_YEAR - "next year", "2014"
        ACU_MONTH - "March", "July 2014"
        ACU_WEEK - "last week", "next 3 weeks"
        ACU_DAY - "tomorrow", "July 4th 2014"
        ACU_HALFDAY - "morning", "tonight"
        ACU_HOUR - "18:00", "next hour"
        ACU_MIN - "18:32", "next 10 minutes"
        ACU_SEC - "18:32:55"
        ACU_NOW - "now"

    """

    __slots__ = ...
    ACU_YEAR = ...
    ACU_MONTH = ...
    ACU_WEEK = ...
    ACU_DAY = ...
    ACU_HALFDAY = ...
    ACU_HOUR = ...
    ACU_MIN = ...
    ACU_SEC = ...
    ACU_NOW = ...
    ACU_DATE = ...
    ACU_TIME = ...
    _ACCURACY_MAPPING = ...
    _ACCURACY_REVERSE_MAPPING = ...
    def __init__(self, accuracy=...) -> None:
        """
        Default constructor of L{pdtContext} class.

        @type  accuracy: integer
        @param accuracy: Accuracy flag

        @rtype:  object
        @return: L{pdtContext} instance
        """
        ...
    def updateAccuracy(self, *accuracy):  # -> None:
        """
        Updates current accuracy flag
        """
        ...
    def update(self, context):  # -> None:
        """
        Uses another L{pdtContext} instance to update current one
        """
        ...
    @property
    def hasDate(self):  # -> bool:
        """
        Returns True if current context is accurate to date
        """
        ...
    @property
    def hasTime(self):  # -> bool:
        """
        Returns True if current context is accurate to time
        """
        ...
    @property
    def dateTimeFlag(self):  # -> int:
        """
        Returns the old date/time flag code
        """
        ...
    @property
    def hasDateOrTime(self):  # -> bool:
        """
        Returns True if current context is accurate to date/time
        """
        ...
    def __repr__(self): ...
    def __eq__(self, ctx) -> bool: ...
