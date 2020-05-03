import asyncio
import logging
import weakref

import zmq
import zmq.asyncio

from .rpc import RPCClientMixin
from .exceptions import QuLabRPCError

log = logging.getLogger(__name__)  # pylint: disable=invalid-name


class _ZMQClient(RPCClientMixin):
    def __init__(self, addr, timeout=10, loop=None):
        self._loop = loop or asyncio.get_event_loop()
        self.setTimeout(timeout)
        self.addr = addr
        self.roleAuth = b''
        self._ctx = zmq.asyncio.Context()
        self.zmq_socket = self._ctx.socket(zmq.DEALER, io_loop=self._loop)
        self.zmq_socket.setsockopt(zmq.LINGER, 0)
        self.zmq_socket.connect(self.addr)
        self.zmq_main_task = None
        asyncio.ensure_future(asyncio.shield(self.run(weakref.proxy(self))),
                              loop=self.loop)

    def __del__(self):
        self.zmq_socket.close()
        self.close()
        self.zmq_main_task.cancel()

    @property
    def loop(self):
        return self._loop

    async def ping(self, timeout=1):
        return await super().ping(self.addr, timeout=timeout)

    async def shutdownServer(self):
        return await super().shutdown(self.addr, self.roleAuth)

    async def sendto(self, data, addr):
        await self.zmq_socket.send_multipart([data])

    @staticmethod
    async def run(client):
        async def main():
            while True:
                data, = await client.zmq_socket.recv_multipart()
                client.handle(client.addr, data)

        client.zmq_main_task = asyncio.ensure_future(main(), loop=client.loop)
        try:
            await client.zmq_main_task
        except asyncio.CancelledError:
            pass


class FakeLock():
    async def __aenter__(self):
        pass

    async def __aexit__(self, exc_type, exc_value, traceback):
        pass


class ZMQRPCCallable:
    def __init__(self, methodName, owner, sessionID=0):
        self.methodName = methodName
        self.owner = owner
        self.fut = None
        self.sessionID = sessionID
        self.Type = None

    async def remoteCall(self, methodName, *args, **kw):
        async with self.owner.lock:
            return await self.owner._zmq_client.remoteCall(
                self.owner._zmq_client.addr, methodName, self.sessionID, args,
                kw)

    def __call__(self, *args, **kw):
        self.fut = asyncio.ensure_future(
            self.remoteCall(self.methodName, *args, **kw))
        return self

    def __getattr__(self, name):
        return ZMQRPCCallable(f"{self.methodName}.{name}", self.owner,
                              self.sessionID)

    def __await__(self):
        return self.fut.__await__()

    async def __aenter__(self):
        if not self.fut.done():
            self.Type, self.sessionID = await self.fut
        if "AsyncContextManager" not in self.Type and "ContextManager" not in self.Type:
            raise QuLabRPCError('not a context manager')
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.remoteCall(f"{self.methodName}.__aexit__", None, None, None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.fut.done():
            self.Type, self.sessionID = await self.fut
        if "AsyncIterator" not in self.Type and "Iterator" not in self.Type:
            raise QuLabRPCError('not a iter')
        try:
            if "AsyncIterator" in self.Type:
                return await self.remoteCall(f"{self.methodName}.__anext__")
            else:
                return await self.remoteCall(f"{self.methodName}.__next__")
        except Exception as e:
            for a in e.args:
                print(a)
            raise StopAsyncIteration


class ZMQClient():
    def __init__(self, addr, timeout=10, loop=None, lock=None):
        self._zmq_client = _ZMQClient(addr, timeout=timeout, loop=loop)
        self.ping = self._zmq_client.ping
        self.lock = FakeLock() if lock is None else lock
        self.shutdownServer = self._zmq_client.shutdownServer

    def __getattr__(self, name):
        return ZMQRPCCallable(name, self)

    async def connect(self):
        await self._zmq_client.connect(self._zmq_client.addr)
