try:
    from asyncio import get_running_loop
except ImportError:
    from asyncio import get_event_loop, AbstractEventLoop

    # A basic shim of get_running_loop for python 3.6
    def get_running_loop() -> AbstractEventLoop:
        loop = get_event_loop()
        if loop.is_running():
            return loop
        raise RuntimeError("no running event loop")
