# Project
from .._types import ListenersMapping


def new_listener_mapping() -> ListenersMapping:
    import sys
    from platform import python_implementation
    from collections import defaultdict, OrderedDict

    return defaultdict(
        lambda: defaultdict(
            # Python 3.7+ dicts are ordered by default, and they are slightly faster than
            # OrderedDicts
            dict
            if (
                sys.version_info >= (3, 7)
                or (sys.version_info >= (3, 6) and python_implementation() == "CPython")
            )
            else OrderedDict
        )
    )
