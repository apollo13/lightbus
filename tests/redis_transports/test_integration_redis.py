import asyncio

import logging
import pytest
import lightbus


@pytest.mark.run_loop
async def test_bus_fixture(bus: lightbus.BusNode):
    """Just sanity check the fixture"""

    pool_rpc = await bus.bus_client.rpc_transport.get_redis_pool()
    pool_result = await bus.bus_client.result_transport.get_redis_pool()
    pool_event = await bus.bus_client.event_transport.get_redis_pool()

    with await pool_rpc as redis_rpc, await pool_result as redis_result, await pool_event as redis_event:
        # Each transport should have its own connection
        assert redis_rpc is not redis_result
        assert redis_result is not redis_event
        assert redis_rpc is not redis_event

        # Check they are all looking at the same redis instance
        await redis_rpc.set('X', 1)
        assert await redis_result.get('X')
        assert await redis_rpc.get('X')

        info = await redis_rpc.info()
        assert int(info['clients']['connected_clients']) == 3


@pytest.mark.run_loop
async def test_rpc(bus: lightbus.BusNode, dummy_api):
    """Full rpc call integration test"""

    async def co_call_rpc():
        asyncio.sleep(1)
        return await bus.my.dummy.my_proc.call_async(field='Hello! 😎')

    async def co_consume_rpcs():
        return await bus.bus_client.consume_rpcs(apis=[dummy_api])

    (call_task, ), (consume_task, ) = await asyncio.wait([co_call_rpc(), co_consume_rpcs()], return_when=asyncio.FIRST_COMPLETED)
    consume_task.cancel()
    assert call_task.result() == 'value: Hello! 😎'