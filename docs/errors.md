Module emitter.errors
=====================

Classes
-------

`EmitterError(...)`
:   Base exception for Emitter related errors.

    ### Ancestors (in MRO)

    * builtins.Exception
    * builtins.BaseException

    ### Descendants

    * emitter.errors.ListenerEventLoopError

`ListenerEventLoopError(...)`
:   Attempt to execute a listener bounded to a stopped event loop.

    ### Ancestors (in MRO)

    * emitter.errors.EmitterError
    * builtins.RuntimeError
    * builtins.Exception
    * builtins.BaseException

    ### Descendants

    * emitter.errors.ListenerStoppedEventLoopError

`ListenerStoppedEventLoopError(...)`
:   Attempt to execute a listener bounded to a stopped event loop.

    ### Ancestors (in MRO)

    * emitter.errors.ListenerEventLoopError
    * emitter.errors.EmitterError
    * builtins.RuntimeError
    * builtins.Exception
    * builtins.BaseException