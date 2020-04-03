import asyncio
import functools
import inspect
import logging
from abc import abstractmethod
from collections.abc import Awaitable
from concurrent.futures import ThreadPoolExecutor

import zmq
import zmq.asyncio

from .exceptions import QuLabRPCError, QuLabRPCServerError, QuLabRPCTimeout
from .rpc import RPCMixin
from .serialize import pack, unpack
from .utils import acceptArg, randomID

log = logging.getLogger(__name__)  # pylint: disable=invalid-name


class RPCServerMixin(RPCMixin):
    def _unpack_request(self, msg):
        try:
            method, args, kw = unpack(msg)
        except:
            raise QuLabRPCError("Could not read packet: %r" % msg)
        return method, args, kw

    @property
    def executor(self):
        return None

    @abstractmethod
    def getRequestHandler(self, methodNane, source, msgID):
        """
        Get suitable handler for request.

        You should implement this method yourself.
        """

    def on_request(self, source, data):
        """
        Received a request from source.
        """
        msgID, msg = data[:20], data[20:]
        method, args, kw = self._unpack_request(msg)
        self.createTask(msgID,
                        self.handle_request(source, msgID, method, *args,
                                            **kw),
                        timeout=kw.get('timeout', 0))

    async def handle_request(self, source, msgID, method, *args, **kw):
        """
        Handle a request from source.
        """
        try:
            func = self.getRequestHandler(method, source=source, msgID=msgID)
            if 'timeout' in kw and not acceptArg(func, 'timeout'):
                del kw['timeout']
            if inspect.iscoroutinefunction(func):
                result = await func(*args, **kw)
            else:
                result = await self.loop.run_in_executor(
                    self.executor, functools.partial(func, *args, **kw))
                if isinstance(result, Awaitable):
                    result = await result
        except QuLabRPCError as e:
            result = e
        except Exception as e:
            result = QuLabRPCServerError.make(e)
        msg = pack(result)
        await self.response(source, msgID, msg)


class ZMQServer(RPCServerMixin):
    def __init__(self, bind='*', port=None, loop=None):
        self.zmq_main_task = None
        self.zmq_ctx = None
        self.zmq_socket = None
        self.bind = bind
        self._port = 0 if port is None else port
        self._loop = loop or asyncio.get_event_loop()
        self._module = None

    def set_module(self, mod):
        self._module = mod

    async def sendto(self, data, address):
        self.zmq_socket.send_multipart([address, data])

    def getRequestHandler(self, methodNane, **kw):
        path = methodNane.split('.')
        ret = getattr(self._module, path[0])
        for n in path[1:]:
            ret = getattr(ret, n)
        return ret

    @property
    def loop(self):
        return self._loop

    @property
    def port(self):
        return self._port

    def set_socket(self, sock):
        self.zmq_socket = sock

    def start(self):
        super().start()
        self.zmq_ctx = zmq.asyncio.Context.instance()
        self.zmq_main_task = asyncio.ensure_future(self.run(), loop=self.loop)

    def stop(self):
        if self.zmq_main_task is not None and not self.zmq_main_task.done():
            self.zmq_main_task.cancel()
        super().stop()

    async def run(self):
        with self.zmq_ctx.socket(zmq.ROUTER, io_loop=self._loop) as sock:
            sock.setsockopt(zmq.LINGER, 0)
            addr = f"tcp://{self.bind}" if self._port == 0 else f"tcp://{self.bind}:{self._port}"
            if self._port != 0:
                sock.bind(addr)
            else:
                self._port = sock.bind_to_random_port(addr)
            self.set_socket(sock)
            while True:
                addr, data = await sock.recv_multipart()
                log.debug('received data from %r' % addr.hex())
                self.handle(addr, data)
