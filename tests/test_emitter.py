# Internal
import typing as T
import asyncio
import unittest
from typing import NamedTuple
from asyncio import Future, CancelledError
from unittest.mock import Mock

# External
import emitter
import asynctest
from emitter import HandleMode
from emitter.errors import ListenerEventLoopError, ListenerStoppedEventLoopError

# Generic types
K = T.TypeVar("K")


class MockAwaitable(Future):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._result_called = 0

    def result(self) -> T.Any:
        self._result_called += 1
        return super().__await__()

    @property
    def time_result_was_called(self) -> int:
        return self._result_called


class Event(NamedTuple):
    data: str


# noinspection PyMethodMayBeStatic
@asynctest.strict
class EmitterTestCase(asynctest.TestCase, unittest.TestCase):
    def tearDown(self) -> None:
        emitter.remove(None, None)

    async def test_emit(self) -> None:
        self.assertFalse(await emitter.emit(Event("Wowow")))

    async def test_listener_simple(self) -> None:
        listener = Mock()

        emitter.on(Event, listener)

        e = Event("Wowow")
        self.assertTrue((await emitter.emit(e)) & HandleMode.GLOBAL)

        listener.assert_called_once_with(e)

    async def test_listener_decorator(self) -> None:
        mock = Mock()

        @emitter.on(Event)
        def listener(event: Event) -> None:
            self.assertEqual("Wowow", event.data)
            mock(event)

        e = Event("Wowow")
        self.assertTrue((await emitter.emit(e)) & HandleMode.GLOBAL)

        mock.assert_called_once_with(e)

    async def test_listener_callable_class(self) -> None:
        mock = Mock()
        this = self

        class Listener:
            def __call__(self, event: Event) -> None:
                this.assertEqual("Wowow", event.data)
                mock(event)

        emitter.on(Event, Listener())

        e = Event("Wowow")
        self.assertTrue((await emitter.emit(e)) & HandleMode.GLOBAL)

        mock.assert_called_once_with(e)

    async def test_listener_coroutine(self) -> None:
        mock = Mock()
        future = self.loop.create_future()

        @emitter.on(Event)
        async def listener(event: Event) -> None:
            await asyncio.sleep(0)
            self.assertEqual("Wowow", event.data)
            mock(event)
            future.set_result(event)

        e = Event("Wowow")
        self.assertTrue((await emitter.emit(e)) & HandleMode.GLOBAL)

        self.assertIs(e, await future)

        mock.assert_called_once_with(e)

    async def test_listener_awaitable(self) -> None:
        mock = MockAwaitable()

        @emitter.on(Event)
        def listener(event: Event) -> T.Awaitable[None]:
            self.assertEqual("Wowow", event.data)
            return mock

        mock.set_result(None)
        self.assertTrue((await emitter.emit(Event("Wowow"))) & HandleMode.GLOBAL)

        self.assertEqual(1, mock.time_result_was_called)

    async def test_listener_namespace(self) -> None:
        class A:
            pass

        namespace = A()
        listener = Mock()

        emitter.on(Event, listener, namespace=namespace)

        e = Event("Wowow")
        self.assertTrue((await emitter.emit(e, namespace=namespace)) & HandleMode.NAMESPACE)

        listener.assert_called_once_with(e)

    async def test_listener_both(self) -> None:
        class A:
            pass

        namespace = A()
        listener = Mock()
        global_listener = Mock()

        emitter.on(Event, global_listener)
        emitter.on(Event, listener, namespace=namespace)

        e = Event("Wowow")
        handled = await emitter.emit(e, namespace=namespace)

        self.assertTrue(handled & HandleMode.NAMESPACE and handled & HandleMode.GLOBAL)
        listener.assert_called_once_with(e)

    async def test_listener_coro_error(self) -> None:
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        @emitter.on(Event)
        async def listener(_: T.Any) -> None:
            await asyncio.sleep(0)
            raise RuntimeError("Ooops...")

        await emitter.emit(Event("Wowow"))

        with self.assertRaisesRegex(RuntimeError, "Ooops..."):
            await future_error

    async def test_listener_coro_handle_error_global(self) -> None:
        exc = RuntimeError("Ooops...")
        mock = Mock()
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        emitter.on(RuntimeError, mock)

        @emitter.on(Event)
        async def listener(_: T.Any) -> None:
            await asyncio.sleep(0)
            raise exc

        await emitter.emit(Event("Wowow"))

        # Allow the loop to cycle once
        await asyncio.sleep(0)
        self.assertFalse(future_error.done())

        mock.assert_called_once_with(exc)

    async def test_listener_coro_handle_error_namespace(self) -> None:
        exc = RuntimeError("Ooops...")
        mock = Mock()
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        @emitter.on(Event)
        async def listener(_: T.Any) -> None:
            await asyncio.sleep(0)
            raise exc

        emitter.on(RuntimeError, mock, namespace=listener)

        await emitter.emit(Event("Wowow"))

        # Allow the loop to cycle once
        await asyncio.sleep(0)
        self.assertFalse(future_error.done())

        mock.assert_called_once_with(exc)

    @asynctest.fail_on(unused_loop=False)
    def test_invalid_types_not_callable(self) -> None:
        with self.assertRaises(ValueError):
            emitter.on(str, "")

        with self.assertRaises(ValueError):
            emitter.on(str, 1)

        with self.assertRaises(ValueError):
            emitter.on(str, [])

        with self.assertRaises(ValueError):
            emitter.on(str, {})

    @asynctest.fail_on(unused_loop=False)
    def test_invalid_types_slotted_class_with_loop(self) -> None:
        class Listener:
            __slots__ = tuple()

            def __call__(self, event: Event) -> None:
                return None

        with self.assertRaises(TypeError):
            emitter.on(str, Listener, loop=self.loop)

    async def test_invalid_types_metaclass(self) -> None:
        mock = Mock()

        class Meta(type):
            pass

        with self.assertRaises(ValueError):
            emitter.on(Meta, mock)

        with self.assertRaises(ValueError):
            await emitter.emit(Meta("", tuple(), {}))

        mock.assert_not_called()

    async def test_invalid_types_object(self) -> None:
        mock = Mock()

        with self.assertRaises(ValueError):
            emitter.on(object, mock)

        with self.assertRaises(ValueError):
            await emitter.emit(object())

        mock.assert_not_called()

    async def test_invalid_types_base_exp(self) -> None:
        mock = Mock()

        with self.assertRaises(ValueError):
            emitter.on(BaseException, mock)

        with self.assertRaises(BaseException):
            await emitter.emit(BaseException())

        mock.assert_not_called()

    async def test_invalid_types_base_exp_subclass(self) -> None:
        mock = Mock()

        class Exp(BaseException):
            pass

        with self.assertRaises(ValueError):
            emitter.on(Exp, mock)

        with self.assertRaises(Exp):
            await emitter.emit(Exp())

        mock.assert_not_called()

    async def test_listener_cancellation(self) -> None:
        mock = Mock()
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        @emitter.on(Event)
        def listener(_: T.Any) -> None:
            fut = self.loop.create_future()
            fut.cancel()
            return fut

        emitter.on(Event, mock)

        e = Event("Wowow")
        await emitter.emit(e)

        with self.assertRaises(CancelledError):
            await future_error

        mock.assert_called_once_with(e)

    async def test_once(self) -> None:
        mock = Mock()

        emitter.on(Event, mock, once=True)

        e = Event("0")
        await asyncio.gather(
            emitter.emit(e),
            emitter.emit(Event("1")),
            emitter.emit(Event("2")),
            emitter.emit(Event("3")),
        )

        mock.assert_called_once_with(e)

    async def test_superclass_listeners(self) -> None:
        class Event2(Event):
            pass

        mock = Mock()

        emitter.on(Event, mock)

        e = Event2("")
        await emitter.emit(e)

        mock.assert_called_once_with(e)

    async def test_both_listeners(self) -> None:
        class Event2(Event):
            pass

        mock = Mock()
        mock1 = Mock()

        emitter.on(Event, mock)
        emitter.on(Event2, mock1)

        e = Event2("")
        await emitter.emit(e)

        mock.assert_called_once_with(e)
        mock1.assert_called_once_with(e)

    async def test_incorrect_loop(self) -> None:
        loop = asyncio.new_event_loop()
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        @emitter.on(Event)
        def listener(_: T.Any) -> T.Awaitable[None]:
            return loop.create_future()

        await emitter.emit(Event(""))

        with self.assertRaises(ListenerEventLoopError):
            await future_error

        loop.close()

    async def test_stopped_loop(self) -> None:
        loop = asyncio.new_event_loop()
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        @emitter.on(Event, loop=loop)
        async def listener(_: T.Any) -> None:
            return None

        await emitter.emit(Event(""))

        with self.assertRaises(ListenerStoppedEventLoopError):
            await future_error

        loop.close()
