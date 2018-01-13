import asyncio
import logging
from typing import Sequence, Tuple, Any

from lightbus.transports.base import ResultTransport, RpcTransport, EventTransport
from lightbus.message import RpcMessage, EventMessage, ResultMessage


logger = logging.getLogger(__name__)


class DebugRpcTransport(RpcTransport):

    async def call_rpc(self, rpc_message: RpcMessage):
        """Publish a call to a remote procedure"""
        logger.debug("Faking dispatch of message {}".format(rpc_message))

    async def consume_rpcs(self, api) -> Sequence[RpcMessage]:
        """Consume RPC calls for the given API"""
        logger.debug("Faking consumption of RPCs. Waiting 1 second before issuing fake RPC call...")
        await asyncio.sleep(0.1)
        logger.debug("Issuing fake RPC call")
        return self._get_fake_messages()

    def _get_fake_messages(self):
        return [RpcMessage(api_name='my_company.auth', procedure_name='check_password', kwargs=dict(
            username='admin',
            password='secret',
        ))]


class DebugResultTransport(ResultTransport):

    def get_return_path(self, rpc_message: RpcMessage) -> str:
        return 'debug://foo'

    async def send_result(self, rpc_message: RpcMessage, result_message: ResultMessage, return_path: str):
        logger.info("Faking sending of result: {}".format(result_message))

    async def receive_result(self, rpc_message: RpcMessage, return_path: str) -> ResultMessage:
        logger.info("⌛ Faking listening for results. Will issue fake result in 0.5 seconds...")
        await asyncio.sleep(0.1)  # This is relied upon in testing
        logger.debug('Faking received result')

        return ResultMessage(result='Fake result')


class DebugEventTransport(EventTransport):

    def __init__(self):
        self._task = None
        self._reload = False
        self._events = set()

    async def send_event(self, event_message: EventMessage):
        """Publish an event"""
        logger.info(" Faking sending of event {}.{} with kwargs: {}".format(
            event_message.api_name,
            event_message.event_name,
            event_message.kwargs
        ))

    async def fetch_events(self) -> Tuple[Sequence[EventMessage], Any]:
        """Consume RPC events for the given API"""

        logger.info("⌛ Faking listening for events {}.".format(self._events))

        try:
            self._task = asyncio.ensure_future(asyncio.sleep(0.1))
            await self._task
        except asyncio.CancelledError as e:
            if self._reload:
                logger.debug('Event transport reloading.')
                event_messages = []
                self._reload = False
            else:
                raise
        else:
            logger.debug('Faking received result')
            event_messages = self._get_fake_messages()

        return event_messages, None

    async def start_listening_for(self, api_name, event_name):
        logger.info('Beginning to listen for {}.{}'.format(api_name, event_name))
        self._events.add('{}.{}'.format(api_name, event_name))
        if self._task:
            logger.debug('Existing consumer task running, cancelling')
            self._reload = True
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError as e:
                pass

    async def stop_listening_for(self, api_name, event_name):
        pass

    def _get_fake_messages(self):
        return [
            EventMessage(api_name='my_company.auth',
                         event_name='user_registered', kwargs={'example': 'value'})
        ]
