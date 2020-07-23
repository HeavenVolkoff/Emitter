# Standard
from typing import NamedTuple
from asyncio import Future, CancelledError
from unittest.mock import Mock, call
import typing as T
import asyncio
import unittest

# External
from emitter.error import ListenerEventLoopError, ListenerStoppedEventLoopError
import emitter
import asynctest

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

    async def test_listener_scope(self) -> None:
        mock = Mock()

        emitter.on(Event, Global, lambda _: mock(0))
        emitter.on("scope", Global, lambda _: mock(1))
        emitter.on(Exception, Global, lambda _: mock(2), scope="scope")
        emitter.on("scope.test", Global, lambda _: mock(3))
        emitter.on("scope...test.", Global, lambda _: mock(4))
        emitter.on(RuntimeError, Global, lambda _: mock(5), scope="scope.test.")
        emitter.on("scope.test.deep", Global, lambda _: mock(6))
        emitter.on("scope.test.deep.owo", Global, lambda _: mock(7))
        emitter.on(ValueError, Global, lambda _: mock(8), scope="scope..test....deep..owo.")
        emitter.on("scope..test....deep..owo.", Global, lambda _: mock(9))

        e = Event("Wowow")
        self.assertTrue(await emitter.emit(e, Global))
        mock.assert_called_once_with(0)
        mock.reset_mock()
        self.assertTrue(await emitter.emit(e, Global, scope=("scope", "test", "deep", "owo")))
        mock.assert_has_calls([call(7), call(9), call(6), call(3), call(4), call(1), call(0)])
        mock.reset_mock()
        self.assertTrue(await emitter.emit(e, Global, scope="..scope.test..."))
        mock.assert_has_calls([call(3), call(4), call(1), call(0)])
        mock.reset_mock()
        with self.assertRaises(ValueError):
            await emitter.emit(ValueError(), Global)
        self.assertTrue(await emitter.emit(ValueError(), Global, scope="scope"))
        mock.assert_has_calls([call(2)])
        mock.reset_mock()
        self.assertTrue(
            await emitter.emit(RuntimeError(), Global, scope=("scope", "test", "deep", "owo"))
        )
        mock.assert_has_calls(
            [call(7), call(9), call(6), call(5), call(3), call(4), call(2), call(1)]
        )
        mock.reset_mock()
        self.assertTrue(await emitter.emit(ValueError(), Global, scope=".scope.test.deep.owo"))
        mock.assert_has_calls(
            [call(8), call(7), call(9), call(6), call(3), call(4), call(2), call(1)]
        )
        mock.reset_mock()

    async def test_listener_order(self) -> None:
        event = ConnectionError("Test")
        order_mock = Mock()

        @emitter.on(Exception, Global, raise_on_exc=True)
        def exception_1_listener(exc: Exception):
            assert exc is event
            order_mock("Exception 1")

        @emitter.on(Exception, Global, raise_on_exc=True)
        def exception_2_listener(exc: Exception):
            assert exc is event
            order_mock("Exception 2")

        @emitter.on(OSError, Global, raise_on_exc=True)
        def os_error_1_listener(exc: Exception):
            assert exc is event
            order_mock("OSError 1")

        @emitter.on(OSError, Global, raise_on_exc=True)
        def os_error_2_listener(exc: Exception):
            assert exc is event
            order_mock("OSError 2")

        @emitter.on(ConnectionError, Global, raise_on_exc=True)
        def connection_error_1_listener(exc: Exception):
            assert exc is event
            order_mock("ConnectionError 1")

        @emitter.on(ConnectionError, Global, raise_on_exc=True)
        def connection_error_2_listener(exc: Exception):
            assert exc is event
            order_mock("ConnectionError 2")

        @emitter.on("error", Global, raise_on_exc=True)
        def scoped_error_1_listener(exc: Exception):
            assert exc is event
            order_mock("ConnectionError scope=error 1")

        @emitter.on("error", Global, raise_on_exc=True)
        def scoped_error_2_listener(exc: Exception):
            assert exc is event
            order_mock("ConnectionError scope=error 2")

        @emitter.on("error.connection", Global, raise_on_exc=True)
        def scoped_error_connection_1_listener(exc: Exception):
            assert exc is event
            order_mock("ConnectionError scope=error.connection 1")

        @emitter.on("error.connection", Global, raise_on_exc=True)
        def scoped_error_connection_2_listener(exc: Exception):
            assert exc is event
            order_mock("ConnectionError scope=error.connection 2")

        self.assertTrue(await emitter.emit(event, Global, scope="error.connection"))

        order_mock.assert_has_calls(
            [
                call("ConnectionError scope=error.connection 1"),
                call("ConnectionError scope=error.connection 2"),
                call("ConnectionError scope=error 1"),
                call("ConnectionError scope=error 2"),
                call("ConnectionError 1"),
                call("ConnectionError 2"),
                call("OSError 1"),
                call("OSError 2"),
                call("Exception 1"),
                call("Exception 2"),
            ]
        )

    async def test_listener_context(self) -> None:
        listener = Mock()

        ctx = emitter.on_context(Event, Global, listener)
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

    async def test_listener_raise_error(self) -> None:
        mock = Mock()

        self.loop.set_exception_handler(mock)

        @emitter.on(Event, Global, raise_on_exc=True)
        async def listener(_: T.Any) -> None:
            await asyncio.sleep(0)
            raise RuntimeError("Ooops...")

        with self.assertRaisesRegex(RuntimeError, "Ooops..."):
            await emitter.emit(Event("Wowow"), Global)

        await asyncio.sleep(0)

        mock.assert_not_called()

    async def test_listener_coro_error_no_raise(self) -> None:
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

    async def test_listener_handle_raise_error(self) -> None:
        exc = RuntimeError("Ooops...")
        mock = Mock()
        mock1 = Mock()

        self.loop.set_exception_handler(mock1)

        @emitter.on(Event, Global, raise_on_exc=True)
        async def listener(_: T.Any) -> None:
            await asyncio.sleep(0)
            raise exc

        emitter.on(RuntimeError, listener, mock)

        await emitter.emit(Event("Wowow"), Global)

        # Allow the loop to cycle once
        await asyncio.sleep(0)
        mock1.assert_not_called()
        mock.assert_called_once_with(exc)

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
    def test_emit_sync(self) -> None:
        mock = Mock()

        @emitter.on(Event, Global)
        def listener(event: Event) -> None:
            self.assertEqual("Wowow", event.data)
            mock(event)

        @emitter.on(Event, Global)
        async def listener(event: Event) -> None:
            await asyncio.sleep(0)
            self.assertEqual("Wowow", event.data)
            mock(event)

        e = Event("Wowow")
        self.assertTrue(emitter.emit(e, Global, sync=True))

        mock.assert_called_once_with(e)

    async def test_emit_sync_in_async(self) -> None:
        mock = Mock()

        @emitter.on(Event, Global)
        def listener(event: Event) -> None:
            self.assertEqual("Wowow", event.data)
            mock(event)

        @emitter.on(Event, Global)
        async def listener(event: Event) -> None:
            await asyncio.sleep(0)
            self.assertEqual("Wowow", event.data)
            mock(event)

        e = Event("Wowow")
        self.assertTrue(emitter.emit(e, Global, sync=True))

        await asyncio.sleep(1)

        mock.assert_called_once_with(e)

    async def test_emit_none(self) -> None:
        mock = Mock()
        emitter.on("test", Global, mock)

        with self.assertRaisesRegex(
            ValueError, "Event type can only be None when accompanied of a scope"
        ):
            await emitter.emit(None, Global)

        mock.assert_not_called()

        self.assertTrue(await emitter.emit(None, Global, scope="test"))

        mock.assert_called_once_with(None)

    @asynctest.fail_on(unused_loop=False)
    def test_invalid_types_not_callable(self) -> None:
        with self.assertRaisesRegex(ValueError, "Listener must be callable"):
            emitter.on(str, Global, "")

        with self.assertRaisesRegex(ValueError, "Listener must be callable"):
            emitter.on(str, Global, 1)

        with self.assertRaisesRegex(ValueError, "Listener must be callable"):
            emitter.on(str, Global, [])

        with self.assertRaisesRegex(ValueError, "Listener must be callable"):
            emitter.on(str, Global, {})

    async def test_slotted_class_with_loop(self) -> None:
        mock = Mock()
        event = Event("")

        class Listener:
            __slots__ = tuple()

            def __call__(self, e: Event) -> None:
                mock(e)

        emitter.on(Event, Global, Listener(), loop=self.loop)
        self.assertTrue(await emitter.emit(event, Global))
        mock.assert_called_once_with(event)

    async def test_invalid_types_metaclass(self) -> None:
        mock = Mock()

        class Meta(type):
            pass

        with self.assertRaises(ValueError):
            emitter.on(Meta, Global, mock)

        with self.assertRaises(ValueError):
            await emitter.emit(Meta("", tuple(), {}), Global)

        mock.assert_not_called()

    async def test_invalid_types_none(self) -> None:
        mock = Mock()

        with self.assertRaises(ValueError):
            emitter.on(None, Global, mock)

        with self.assertRaises(ValueError):
            await emitter.emit(object(), Global)

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
        self.assertTrue(await emitter.emit(e, Global))
        mock.assert_called_once_with(e)
        mock.reset_mock()

        self.assertFalse(await emitter.emit(Event("1"), Global))
        mock.assert_not_called()

        self.assertFalse(await emitter.emit(Event("2"), Global))
        mock.assert_not_called()

        self.assertFalse(await emitter.emit(Event("3"), Global))
        mock.assert_not_called()

    async def test_once_emit_before_remove(self) -> None:
        e = Event("0")
        mock = Mock()

        emitter.on(Event, Global, mock, once=True)
        emit_task = asyncio.gather(
            emitter.emit(e, Global),
            emitter.emit(e, Global),
            emitter.emit(e, Global),
            emitter.emit(e, Global),
            emitter.emit(e, Global),
        )
        emitter.remove(None, Global)

        results = await emit_task
        self.assertIn(True, results)
        results.remove(True)
        self.assertListEqual([False, False, False, False], results)
        mock.assert_called_once_with(e)

    async def test_once_emit_after_remove(self) -> None:
        mock = Mock()

        emitter.on(Event, Global, mock, once=True)
        emitter.remove(None, Global)

        e = Event("0")
        results = await asyncio.gather(
            emitter.emit(e, Global),
            emitter.emit(e, Global),
            emitter.emit(e, Global),
            emitter.emit(e, Global),
            emitter.emit(e, Global),
        )
        self.assertListEqual([False, False, False, False, False], results)
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

    async def test_context(self) -> None:
        e = Event("")
        mock = Mock()
        mock2 = Mock()
        self.assertFalse(await emitter.emit(e, Global))

        with emitter.context() as context:
            self.assertFalse(await emitter.emit(e, Global))
            self.assertFalse(await emitter.emit(None, Global, scope="test"))
            mock.assert_not_called()
            mock2.assert_not_called()

            @emitter.on(Event, Global)
            def main_listener(_: T.Any) -> None:
                emitter.on("test", Global, mock)

            self.assertTrue(await emitter.emit(e, Global))
            self.assertTrue(await emitter.emit(None, Global, scope="test"))
            mock.assert_called_once_with(None)
            mock.reset_mock()

            @emitter.on(Event, Global)
            async def async_main_listener(_: T.Any) -> None:
                await asyncio.sleep(0)
                emitter.on("test", Global, mock2)

            self.assertTrue(await emitter.emit(e, Global))
            self.assertTrue(await emitter.emit(None, Global, scope="test"))
            mock.assert_called_once_with(None)
            mock.reset_mock()
            mock2.assert_called_once_with(None)
            mock2.reset_mock()

            emitter.remove(None, Global, context=context)

            self.assertFalse(await emitter.emit(e, Global))
            self.assertFalse(await emitter.emit(None, Global, scope="test"))
            mock.assert_not_called()
            mock2.assert_not_called()

    async def test_wrap_listeners_context(self) -> None:
        mock = Mock()

        with emitter.context() as ctx:
            listeners = ctx.wrap_listeners(Global)

        emitter.on("test", listeners, mock)

        self.assertTrue(await emitter.emit(None, Global, scope="test"))
        mock.assert_called_once_with(None)
        mock.reset_mock()

        self.assertTrue(await emitter.emit(None, listeners, scope="test"))
        mock.assert_called_once_with(None)
        mock.reset_mock()

        self.assertTrue(emitter.remove("test", Global, mock, context=ctx))
        self.assertFalse(await emitter.emit(None, Global, scope="test"))
        self.assertFalse(await emitter.emit(None, listeners, scope="test"))
        mock.assert_not_called()

        emitter.on("test", listeners, mock)

        self.assertTrue(await emitter.emit(None, Global, scope="test"))
        mock.assert_called_once_with(None)
        mock.reset_mock()

        self.assertTrue(await emitter.emit(None, listeners, scope="test"))
        mock.assert_called_once_with(None)
        mock.reset_mock()

        self.assertTrue(emitter.remove("test", listeners, mock))
        self.assertFalse(await emitter.emit(None, Global, scope="test"))
        self.assertFalse(await emitter.emit(None, listeners, scope="test"))
        mock.assert_not_called()

    async def test_context_stack(self) -> None:
        mock = Mock()

        with emitter.context() as ctx0:
            emitter.on("test", Global, lambda x: mock(1))

            @emitter.on("test", Global)
            async def async_main_listener0(_: T.Any) -> None:
                await asyncio.sleep(0)
                emitter.on("test", Global, lambda x: mock(2))
                emitter.remove("test", Global, async_main_listener0)

        with emitter.context() as ctx1:
            emitter.on("test", Global, lambda x: mock(3))

            with emitter.context() as ctx2:
                emitter.on("test", Global, lambda x: mock(4))

            with emitter.context():

                @emitter.on("test", Global)
                async def async_main_listener1(_: T.Any) -> None:
                    await asyncio.sleep(0)
                    emitter.on("test", Global, lambda x: mock(5))
                    emitter.remove("test", Global, async_main_listener1)

                with emitter.context():
                    emitter.on("test", Global, lambda x: mock(6))

        with emitter.context() as ctx3:
            listener0 = ctx3.wrap_listeners(Global)

        with emitter.context():
            emitter.on("test", listener0, lambda x: mock(7))

            with emitter.context() as ctx5:
                listener1 = ctx5.wrap_listeners(Global)

            @emitter.on("test", Global)
            async def setup_remove(_: T.Any) -> None:
                await asyncio.sleep(0)
                emitter.remove("test", Global)

        emitter.on("test", listener1, lambda x: mock(8))

        self.assertTrue(await emitter.emit(None, Global, scope="test"))
        mock.assert_has_calls([call(1), call(3), call(4), call(6), call(7), call(8)])
        mock.reset_mock()
        self.assertTrue(await emitter.emit(None, Global, scope="test"))
        mock.assert_has_calls([call(1), call(3), call(4), call(6), call(2), call(5)])
        mock.reset_mock()
        emitter.remove(None, Global, context=ctx2)
        self.assertTrue(await emitter.emit(None, Global, scope="test"))
        mock.assert_has_calls([call(1), call(3), call(6), call(2), call(5)])
        mock.reset_mock()
        emitter.remove(None, Global, context=ctx0)
        self.assertTrue(await emitter.emit(None, Global, scope="test"))
        mock.assert_has_calls([call(3), call(6), call(5)])
        mock.reset_mock()
        emitter.remove(None, Global, context=ctx1)
        self.assertFalse(await emitter.emit(None, Global, scope="test"))
        mock.assert_not_called()

    async def test_concomitant_context(self) -> None:
        async def test_context(scope: str, time: T.Union[int, float]) -> None:
            mock = Mock()
            mock2 = Mock()

            with emitter.context() as context:

                @emitter.on(scope, Global)
                def main_listener(_: T.Any) -> None:
                    emitter.on(scope, Global, mock)

                await emitter.emit(None, Global, scope=scope)
                mock.assert_not_called()
                mock2.assert_not_called()
                await emitter.emit(None, Global, scope=scope)
                mock.assert_called_once_with(None)
                mock2.assert_not_called()
                mock.reset_mock()

                @emitter.on(scope, Global)
                async def async_main_listener(_: T.Any) -> None:
                    await asyncio.sleep(0)
                    emitter.on(scope, Global, mock2)

                await asyncio.sleep(time)

                await emitter.emit(None, Global, scope=scope)
                mock.assert_called_once_with(None)
                mock2.assert_not_called()
                mock.reset_mock()
                await emitter.emit(None, Global, scope=scope)
                mock.assert_called_once_with(None)
                mock.reset_mock()
                mock2.assert_called_once_with(None)
                mock2.reset_mock()

                emitter.remove(None, Global, context=context)

                await emitter.emit(None, Global, scope=scope)
                mock.assert_not_called()
                mock2.assert_not_called()

        await asyncio.gather(
            test_context("test0", 0),
            test_context("test1", 0),
            test_context("test2", 0),
            test_context("test3", 0),
            test_context("test4", 0),
            test_context("test5", 0),
            test_context("test6", 0),
            test_context("test7", 0),
            test_context("test8", 0),
            test_context("test9", 0),
        )

        await asyncio.gather(
            test_context("test0", 0),
            test_context("test1", 0.1),
            test_context("test2", 0.2),
            test_context("test3", 0.3),
            test_context("test4", 0.4),
            test_context("test5", 0.5),
            test_context("test6", 0.6),
            test_context("test7", 0.7),
            test_context("test8", 0.8),
            test_context("test9", 0.9),
        )

        await asyncio.gather(
            test_context("test0", 0),
            test_context("test1", 0.5),
            test_context("test2", 0.4),
            test_context("test3", 0.7),
            test_context("test4", 0.9),
            test_context("test5", 0.5),
            test_context("test6", 0.3),
            test_context("test7", 0.3),
            test_context("test8", 0.1),
            test_context("test9", 0.32),
        )

    # TODO: Test multiple loops
