try:
    from asyncio import get_running_loop
except ImportError:
    from asyncio import AbstractEventLoop, _get_running_loop

    # Polyfill of get_running_loop for cpython 3.6
    def get_running_loop() -> AbstractEventLoop:
        loop = _get_running_loop()
        if loop:
            return loop
        raise RuntimeError("no running event loop")
