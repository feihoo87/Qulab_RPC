import asyncio
import logging
from abc import ABC, abstractmethod

from .exceptions import QuLabRPCTimeout, QuLabRPCError

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
