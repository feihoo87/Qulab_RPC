import asyncio
import logging
import weakref

import zmq
import zmq.asyncio

from .exceptions import QuLabRPCError, QuLabRPCServerError, QuLabRPCTimeout
from .rpc import RPCMixin
from .serialize import pack, unpack
from .utils import randomID
log = logging.getLogger(__name__)  # pylint: disable=invalid-name


class RPCClientMixin(RPCMixin):
    _client_defualt_timeout = 10

    def set_timeout(self, timeout=10):
        self._client_defualt_timeout = timeout

    def remoteCall(self, addr, methodNane, args=(), kw={}):
        if 'timeout' in kw:
            timeout = kw['timeout']
        else:
            timeout = self._client_defualt_timeout
        msg = pack((methodNane, args, kw))
        msgID = randomID()
        asyncio.ensure_future(self.request(addr, msgID, msg), loop=self.loop)
        return self.createPending(addr, msgID, timeout)

    def on_response(self, source, data):
        """
        Client side.
        """
        msgID, msg = data[:20], data[20:]
        if msgID not in self.pending:
            return
        fut, timeout = self.pending[msgID]
        timeout.cancel()
        result = unpack(msg)
        if not fut.done():
            if isinstance(result, Exception):
                fut.set_exception(result)
            else:
                fut.set_result(result)


class _ZMQClient(RPCClientMixin):
    def __init__(self, addr, timeout=10, loop=None):
        self._loop = loop or asyncio.get_event_loop()
        self.set_timeout(timeout)
        self.addr = addr
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
        return await super().shutdown(self.addr)

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


class ZMQRPCCallable:
    def __init__(self, methodNane, owner):
        self.methodNane = methodNane
        self.owner = owner

    def __call__(self, *args, **kw):
        fut = self.owner._zmq_client.remoteCall(self.owner._zmq_client.addr,
                                                self.methodNane, args, kw)
        fut.add_done_callback(self.owner._remoteCallDoneCallbackHook)
        return fut

    def __getattr__(self, name):
        return ZMQRPCCallable(f"{self.methodNane}.{name}", self.owner)


class ZMQClient():
    def __init__(self, addr, timeout=10, loop=None):
        self._zmq_client = _ZMQClient(addr, timeout=timeout, loop=loop)
        self.ping = self._zmq_client.ping
        self.shutdownServer = self._zmq_client.shutdownServer

    def __getattr__(self, name):
        return ZMQRPCCallable(name, self)

    def _remoteCallDoneCallbackHook(self, fut):
        """overwrite this method"""
        pass
