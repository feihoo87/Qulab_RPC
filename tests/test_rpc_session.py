import asyncio
import contextlib

import pytest

from qurpc import *


class Error(QuLabRPCError):
    pass


class MySrv:
    def __init__(self, sid=''):
        self.sid = sid

        class Test:
            def hello(self):
                return "hello, world"

        self.sub = Test()

    def add(self, a, b):
        return a + b

    async def add_async(self, a, b):
        await asyncio.sleep(0.2)
        return a + b

    def add_fut(self, a, b):
        return self.add_async(a, b)

    def error(self):
        raise Error('error')

    def serverError(self):
        return 1 / 0

    async def sleep(self, t):
        await asyncio.sleep(t)

    def gen(self):
        get = None
        for i in range(10):
            get = yield i if get is None else get

    async def async_gen(self):
        get = None
        for i in range(10):
            await asyncio.sleep(0.01)
            get = yield i if get is None else get

    @contextlib.contextmanager
    def context(self, x):
        try:
            yield x
        finally:
            pass

    async def async_context(self, x):
        class AContext():
            def __init__(self, x):
                self.x = x

            async def __aenter__(self):
                return self.x

            async def __aexit__(self, exc_type, exc_value, traceback):
                pass

        return AContext(x)


@pytest.fixture()
def server(event_loop):
    s = ZMQServer(loop=event_loop)
    s.set_module(MySrv())
    s.start()
    yield s
    s.close()


@pytest.mark.asyncio
async def test_gen(server, event_loop):
    c = ZMQClient('tcp://127.0.0.1:%d' % server.port,
                  timeout=0.7,
                  loop=event_loop)
    await c.connect()
    v1 = []
    v2 = list(range(10))
    async for v in c.gen():
        v1.append(v)

    assert len(v1) == len(v2)
    assert v1 == v2


@pytest.mark.asyncio
async def test_async_gen(server, event_loop):
    c = ZMQClient('tcp://127.0.0.1:%d' % server.port,
                  timeout=0.7,
                  loop=event_loop)
    await c.connect()
    v1 = []
    v2 = list(range(10))
    async for v in c.async_gen():
        v1.append(v)

    assert len(v1) == len(v2)
    assert v1 == v2
