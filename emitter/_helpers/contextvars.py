# Standard
from sys import version_info

# Enable asyncio contextvars support in Python 3.6:
if version_info < (3, 7):
    import aiocontextvars  # type: ignore[import]

    del aiocontextvars
