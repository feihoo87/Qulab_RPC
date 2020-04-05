import asyncio
import functools
import inspect
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable

from .exceptions import QuLabRPCError, QuLabRPCServerError, QuLabRPCTimeout
from .serialize import pack, unpack
from .utils import acceptArg, randomID

log = logging.getLogger(__name__)  # pylint: disable=invalid-name

# message type

RPC_REQUEST = b'\x01'
RPC_RESPONSE = b'\x02'
RPC_PING = b'\x03'
RPC_PONG = b'\x04'
RPC_CANCEL = b'\x05'
RPC_SHUTDOWN = b'\x06'
# RPC_LONGREQUEST = b'\x07'
# RPC_LONGRESPONSE = b'\x08'
# RPC_LEVELUPRESPONSE = b'\x09'
# RPC_STARTLONGREQUEST = b'\x0a'


class RPCMixin(ABC):
    __pending = None
    __tasks = None

    @property
    def pending(self):
        if self.__pending is None:
            self.__pending = {}
        return self.__pending

    @property
    def tasks(self):
        if self.__tasks is None:
            self.__tasks = {}
        return self.__tasks

    def start(self):
        pass

    def stop(self):
        pass

    def close(self):
        self.stop()
        for task in list(self.tasks.values()):
            task.cancel()
        self.tasks.clear()
        for fut, timeout in list(self.pending.values()):
            fut.cancel()
            timeout.cancel()
        self.pending.clear()

    def createTask(self, msgID, coro, timeout=0):
        """
        Create a new task for msgID.
        """
        if timeout > 0:
            coro = asyncio.wait_for(coro, timeout)
        task = asyncio.ensure_future(coro, loop=self.loop)
        self.tasks[msgID] = task

        def clean(fut, msgID=msgID):
            if msgID in self.tasks:
                del self.tasks[msgID]

        task.add_done_callback(clean)

    def cancelTask(self, msgID):
        """
        Cancel the task for msgID.
        """
        if msgID in self.tasks:
            self.tasks[msgID].cancel()

    def createPending(self, addr, msgID, timeout=1, cancelRemote=True):
        """
        Create a future for request, wait response before timeout.
        """
        fut = self.loop.create_future()
        self.pending[msgID] = (fut,
                               self.loop.call_later(timeout,
                                                    self.cancelPending, addr,
                                                    msgID, cancelRemote))

        def clean(fut, msgID=msgID):
            if msgID in self.pending:
                del self.pending[msgID]

        fut.add_done_callback(clean)

        return fut

    def cancelPending(self, addr, msgID, cancelRemote):
        """
        Give up when request timeout and try to cancel remote task.
        """
        if msgID in self.pending:
            fut, timeout = self.pending[msgID]
            if cancelRemote:
                self.cancelRemoteTask(addr, msgID)
            if not fut.done():
                fut.set_exception(QuLabRPCTimeout('Time out.'))

    def cancelRemoteTask(self, addr, msgID):
        """
        Try to cancel remote task.
        """
        asyncio.ensure_future(self.sendto(RPC_CANCEL + msgID, addr),
                              loop=self.loop)

    @property
    @abstractmethod
    def loop(self):
        """
        Event loop.
        """

    @abstractmethod
    async def sendto(self, data, address):
        """
        Send message to address.
        """

    __rpc_handlers = {
        RPC_PING: 'on_ping',
        RPC_PONG: 'on_pong',
        RPC_REQUEST: 'on_request',
        RPC_RESPONSE: 'on_response',
        RPC_CANCEL: 'on_cancel',
        RPC_SHUTDOWN: 'on_shutdown',
    }

    def parseData(self, data):
        msg_type, msg = data[:1], data[1:]
        if msg_type in [RPC_PING, RPC_PONG]:
            return msg_type, msg
        elif msg_type in [RPC_REQUEST, RPC_RESPONSE, RPC_CANCEL, RPC_SHUTDOWN]:
            msgID, msg = msg[:20], msg[20:]
            return msg_type, msgID, msg
        # elif msg_type in [RPC_LONGREQUEST, RPC_LONGRESPONSE]:
        #     msgID, sessionID, msg = msg[:20], msg[20:40], msg[40:]
        #     return msg_type, msgID, sessionID, msg
        else:
            raise QuLabRPCError(f'Unkown message type {msg_type}.')

    def handle(self, source, data):
        """
        Handle received data.

        Should be called whenever received data from outside.
        """
        msg_type, *args = self.parseData(data)
        log.debug(f'received request {msg_type} from {source}')
        handler = self.__rpc_handlers.get(msg_type, None)
        if handler is not None:
            getattr(self, handler)(source, *args)

    async def ping(self, addr, timeout=1):
        await self.sendto(RPC_PING, addr)
        fut = self.createPending(addr, addr, timeout, False)
        try:
            return await fut
        except QuLabRPCTimeout:
            return False

    async def pong(self, addr):
        await self.sendto(RPC_PONG, addr)

    async def request(self, address, msgID, msg):
        log.debug(f'send request {address}, {msgID.hex()}, {msg}')
        await self.sendto(RPC_REQUEST + msgID + msg, address)

    async def response(self, address, msgID, msg):
        log.debug(f'send response {address}, {msgID.hex()}, {msg}')
        await self.sendto(RPC_RESPONSE + msgID + msg, address)

    async def shutdown(self, address, msgID, roleAuth):
        await self.sendto(RPC_SHUTDOWN + msgID + roleAuth, address)

    def on_request(self, source, msgID, msg):
        """
        Handle request.

        Overwrite this method on server.
        """
        raise NotImplementedError("'on_request' not defined.")

    def on_response(self, source, msgID, msg):
        """
        Handle response.

        Overwrite this method on client.
        """
        raise NotImplementedError("'on_response' not defined.")

    def on_ping(self, source, msg):
        log.debug(f"received ping from {source}")
        asyncio.ensure_future(self.pong(source), loop=self.loop)

    def on_pong(self, source, msg):
        log.debug(f"received pong from {source}")
        if source in self.pending:
            fut, timeout = self.pending[source]
            timeout.cancel()
            if not fut.done():
                fut.set_result(True)

    def on_cancel(self, source, msgID, msg):
        self.cancelTask(msgID)

    def on_shutdown(self, source, msgID, roleAuth):
        if self.is_admin(source, roleAuth):
            raise SystemExit(0)

    def is_admin(self, source, roleAuth):
        return True


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

    async def shutdown(self, address, roleAuth):
        await self.sendto(RPC_SHUTDOWN + randomID() + roleAuth, address)

    def on_response(self, source, msgID, msg):
        """
        Client side.
        """
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

    def on_request(self, source, msgID, msg):
        """
        Received a request from source.
        """
        method, args, kw = self._unpack_request(msg)
        self.createTask(msgID,
                        self.handle_request(source, msgID, method, args, kw),
                        timeout=kw.get('timeout', 0))

    async def handle_request(self, source, msgID, method, args, kw):
        """
        Handle a request from source.
        """
        try:
            func = self.getRequestHandler(method, source=source, msgID=msgID)
            result = await self.callMethod(func, *args, **kw)
        except QuLabRPCError as e:
            result = e
        except Exception as e:
            result = QuLabRPCServerError.make(e)
        msg = pack(result)
        await self.response(source, msgID, msg)

    async def callMethod(self, func, *args, **kw):
        if 'timeout' in kw and not acceptArg(func, 'timeout'):
            del kw['timeout']
        if inspect.iscoroutinefunction(func):
            result = await func(*args, **kw)
        else:
            result = await self.loop.run_in_executor(
                self.executor, functools.partial(func, *args, **kw))
            if isinstance(result, Awaitable):
                result = await result
        return result
