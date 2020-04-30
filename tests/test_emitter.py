# Internal
import typing as T
import asyncio
import unittest
from typing import NamedTuple
from asyncio import Future, CancelledError
from unittest.mock import Mock, call

# External
import asynctest

# External
import emitter
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


class Global:
    pass


# noinspection PyMethodMayBeStatic
@asynctest.strict
class EmitterTestCase(asynctest.TestCase, unittest.TestCase):
    def tearDown(self) -> None:
        emitter.remove(None, Global)

    async def test_emit(self) -> None:
        self.assertFalse(await emitter.emit(Event("Wowow"), Global))

    async def test_listener_simple(self) -> None:
        listener = Mock()

        emitter.on(Event, Global, listener)

        e = Event("Wowow")
        self.assertTrue(await emitter.emit(e, Global))

        listener.assert_called_once_with(e)

    async def test_listener_context(self) -> None:
        listener = Mock()

        ctx = emitter.on(Event, Global, listener, context=True)
        self.assertIsInstance(ctx, T.ContextManager)
        with ctx:
            e = Event("Wowow")
            self.assertTrue(await emitter.emit(e, Global))

            listener.assert_called_once_with(e)

        self.assertFalse(emitter.remove(Event, Global, listener))

    async def test_listener_decorator(self) -> None:
        mock = Mock()

        @emitter.on(Event, Global)
        def listener(event: Event) -> None:
            self.assertEqual("Wowow", event.data)
            mock(event)

        e = Event("Wowow")
        self.assertTrue(await emitter.emit(e, Global))

        mock.assert_called_once_with(e)

    async def test_listener_decorator_fail_context(self) -> None:
        mock = Mock()

        with self.assertRaisesRegex(
            ValueError, "Can't use context manager without a listener defined"
        ):

            @emitter.on(Event, Global, context=True)
            def listener(event: Event) -> None:
                self.assertEqual("Wowow", event.data)
                mock(event)

        e = Event("Wowow")
        self.assertFalse(await emitter.emit(e, Global))

        mock.assert_not_called()

    async def test_scoped_listener_decorator(self) -> None:
        mock = Mock()

        @emitter.on(Event, Global)
        def listener(event: Event) -> None:
            self.assertEqual("Wowow", event.data)
            mock(event)

        @emitter.on("test", Global)
        def listener(event: Event) -> None:
            self.assertEqual("Wowow", event.data)
            mock(event)

        e = Event("Wowow")
        self.assertTrue(await emitter.emit(e, Global, scope="test"))

        mock.assert_has_calls([call(e), call(e)])

    async def test_listener_callable_class(self) -> None:
        mock = Mock()
        this = self

        class Listener:
            def __call__(self, event: Event) -> None:
                this.assertEqual("Wowow", event.data)
                mock(event)

        emitter.on(Event, Global, Listener())

        e = Event("Wowow")
        self.assertTrue(await emitter.emit(e, Global))

        mock.assert_called_once_with(e)

    async def test_listener_coroutine(self) -> None:
        mock = Mock()
        future = self.loop.create_future()

        @emitter.on(Event, Global)
        async def listener(event: Event) -> None:
            await asyncio.sleep(0)
            self.assertEqual("Wowow", event.data)
            mock(event)
            future.set_result(event)

        e = Event("Wowow")
        self.assertTrue(await emitter.emit(e, Global))

        self.assertIs(e, await future)

        mock.assert_called_once_with(e)

    async def test_listener_awaitable(self) -> None:
        mock = MockAwaitable()

        @emitter.on(Event, Global)
        def listener(event: Event) -> T.Awaitable[None]:
            self.assertEqual("Wowow", event.data)
            return mock

        mock.set_result(None)
        self.assertTrue(await emitter.emit(Event("Wowow"), Global))

        self.assertEqual(1, mock.time_result_was_called)

    async def test_listener_coro_error(self) -> None:
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        @emitter.on(Event, Global)
        async def listener(_: T.Any) -> None:
            await asyncio.sleep(0)
            raise RuntimeError("Ooops...")

        await emitter.emit(Event("Wowow"), Global)

        with self.assertRaisesRegex(RuntimeError, "Ooops..."):
            await future_error

    async def test_listener_coro_handle_error(self) -> None:
        exc = RuntimeError("Ooops...")
        mock = Mock()
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        @emitter.on(Event, Global)
        async def listener(_: T.Any) -> None:
            await asyncio.sleep(0)
            raise exc

        emitter.on(RuntimeError, listener, mock)

        await emitter.emit(Event("Wowow"), Global)

        # Allow the loop to cycle once
        await asyncio.sleep(0)
        self.assertFalse(future_error.done())

        mock.assert_called_once_with(exc)

    @asynctest.fail_on(unused_loop=False)
    def test_invalid_types_not_callable(self) -> None:
        with self.assertRaises(ValueError):
            emitter.on(str, Global, "")

        with self.assertRaises(ValueError):
            emitter.on(str, Global, 1)

        with self.assertRaises(ValueError):
            emitter.on(str, Global, [])

        with self.assertRaises(ValueError):
            emitter.on(str, Global, {})

    @asynctest.fail_on(unused_loop=False)
    def test_invalid_types_slotted_class_with_loop(self) -> None:
        class Listener:
            __slots__ = tuple()

            def __call__(self, event: Event) -> None:
                return None

        with self.assertRaises(AttributeError):
            emitter.on(str, Global, Listener(), loop=self.loop)

    async def test_invalid_types_metaclass(self) -> None:
        mock = Mock()

        class Meta(type):
            pass

        with self.assertRaises(ValueError):
            emitter.on(Meta, Global, mock)

        with self.assertRaises(ValueError):
            await emitter.emit(Meta("", tuple(), {}), Global)

        mock.assert_not_called()

    async def test_invalid_types_object(self) -> None:
        mock = Mock()

        with self.assertRaises(ValueError):
            emitter.on(object, Global, mock)

        with self.assertRaises(ValueError):
            await emitter.emit(object(), Global)

        mock.assert_not_called()

    async def test_invalid_types_base_exp(self) -> None:
        mock = Mock()

        with self.assertRaises(ValueError):
            emitter.on(BaseException, Global, mock)

        with self.assertRaises(BaseException):
            await emitter.emit(BaseException(), Global)

        mock.assert_not_called()

    async def test_invalid_types_base_exp_subclass(self) -> None:
        mock = Mock()

        class Exp(BaseException):
            pass

        with self.assertRaises(ValueError):
            emitter.on(Exp, Global, mock)

        with self.assertRaises(Exp):
            await emitter.emit(Exp(), Global)

        mock.assert_not_called()

    async def test_listener_cancellation(self) -> None:
        mock = Mock()
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        @emitter.on(Event, Global)
        def listener(_: T.Any) -> None:
            fut = self.loop.create_future()
            fut.cancel()
            return fut

        emitter.on(Event, Global, mock)

        e = Event("Wowow")
        await emitter.emit(e, Global)

        with self.assertRaises(CancelledError):
            await future_error

        mock.assert_called_once_with(e)

    async def test_once(self) -> None:
        mock = Mock()

        emitter.on(Event, Global, mock, once=True)

        e = Event("0")
        results = await asyncio.gather(
            emitter.emit(e, Global),
            emitter.emit(Event("1"), Global),
            emitter.emit(Event("2"), Global),
            emitter.emit(Event("3"), Global),
        )

        self.assertListEqual([True, False, False, False], results)

        mock.assert_called_once_with(e)

    async def test_once_fail_context(self) -> None:
        mock = Mock()

        with self.assertRaisesRegex(ValueError, "Can't use context manager with a once listener"):
            emitter.on(Event, Global, mock, once=True, context=True)

        e = Event("0")
        results = await asyncio.gather(
            emitter.emit(e, Global),
            emitter.emit(Event("1"), Global),
            emitter.emit(Event("2"), Global),
            emitter.emit(Event("3"), Global),
        )

        self.assertListEqual([False, False, False, False], results)

        mock.assert_not_called()

    async def test_superclass_listeners(self) -> None:
        class Event2(Event):
            pass

        mock = Mock()

        emitter.on(Event, Global, mock)

        e = Event2("")
        await emitter.emit(e, Global)

        mock.assert_called_once_with(e)

    async def test_both_listeners(self) -> None:
        class Event2(Event):
            pass

        mock = Mock()
        mock1 = Mock()

        emitter.on(Event, Global, mock)
        emitter.on(Event2, Global, mock1)

        e = Event2("")
        await emitter.emit(e, Global)

        mock.assert_called_once_with(e)
        mock1.assert_called_once_with(e)

    async def test_incorrect_loop(self) -> None:
        loop = asyncio.new_event_loop()
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        @emitter.on(Event, Global)
        def listener(_: T.Any) -> T.Awaitable[None]:
            return loop.create_future()

        await emitter.emit(Event(""), Global)

        with self.assertRaises(ListenerEventLoopError):
            await future_error

        loop.close()

    async def test_stopped_loop(self) -> None:
        loop = asyncio.new_event_loop()
        future_error = self.loop.create_future()

        @self.loop.set_exception_handler
        def handle_error(_, ctx) -> None:
            future_error.set_exception(ctx["exception"])

        @emitter.on(Event, Global, loop=loop)
        async def listener(_: T.Any) -> None:
            return None

        await emitter.emit(Event(""), Global)

        with self.assertRaises(ListenerStoppedEventLoopError):
            await future_error

        loop.close()

    async def test_wait(self) -> None:
        task = self.loop.create_task(emitter.wait(Event, Global))
        await asyncio.sleep(0)
        e = Event("Wowow")
        self.assertTrue(await emitter.emit(e, Global))
        self.assertIs(await task, e)
