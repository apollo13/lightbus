import asyncio
import os
import urllib.parse
from copy import copy
from typing import AsyncGenerator, Awaitable

import pytest

import lightbus
from lightbus import TransactionalEventTransport, BusNode
from lightbus.transports.base import TransportRegistry
from lightbus.transports.transactional import DbApiConnection
from lightbus.utilities.async import block

if False:
    import aiopg


@pytest.fixture()
def pg_url():
    return os.environ.get("PG_URL", "postgres://postgres@localhost:5432/postgres")


@pytest.fixture()
def pg_kwargs(pg_url):
    parsed = urllib.parse.urlparse(pg_url)
    assert parsed.scheme == "postgres"
    return {
        "dbname": parsed.path.strip("/") or "postgres",
        "user": parsed.username or "postgres",
        "password": parsed.password,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
    }


@pytest.yield_fixture()
def aiopg_connection(pg_kwargs, loop):
    import aiopg

    connection = block(aiopg.connect(loop=loop, **pg_kwargs), loop=loop, timeout=2)
    yield connection
    connection.close()


@pytest.yield_fixture()
def psycopg2_connection(pg_kwargs, loop):
    import psycopg2

    connection = psycopg2.connect(**pg_kwargs)
    yield connection
    connection.close()


@pytest.fixture()
def aiopg_cursor(aiopg_connection, loop):
    cursor = block(aiopg_connection.cursor(), loop=loop, timeout=1)
    block(cursor.execute("DROP TABLE IF EXISTS lightbus_processed_events"), loop=loop, timeout=1)
    block(cursor.execute("DROP TABLE IF EXISTS lightbus_event_outbox"), loop=loop, timeout=1)
    return cursor


@pytest.fixture()
def dbapi_database(aiopg_connection, aiopg_cursor, loop):
    return DbApiConnection(aiopg_connection, aiopg_cursor)


def verification_connection() -> Awaitable["aiopg.Connection"]:
    import aiopg

    return aiopg.connect(**pg_kwargs(pg_url()), loop=asyncio.get_event_loop())


@pytest.fixture()
def get_outbox():

    async def inner():
        async with verification_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT * FROM lightbus_event_outbox")
                return await cursor.fetchall()

    return inner


@pytest.fixture()
def get_processed_events():

    async def inner():
        async with verification_connection() as connection:
            async with connection.cursor() as cursor:
                await cursor.execute("SELECT * FROM lightbus_processed_events")
                return await cursor.fetchall()

    return inner


@pytest.fixture()
def messages_in_redis(redis_client):

    async def inner(api_name, event_name):
        return await redis_client.xrange(f"{api_name}.{event_name}:stream")

    return inner


@pytest.fixture()
def transactional_bus_factory(dummy_bus: BusNode, new_redis_pool, loop):
    pool = new_redis_pool(maxsize=10000)

    async def inner():
        transport = TransactionalEventTransport(
            child_transport=lightbus.RedisEventTransport(
                redis_pool=pool, consumer_group_prefix="test_cg", consumer_name="test_consumer"
            )
        )
        config = dummy_bus.bus_client.config
        transport_registry = TransportRegistry().load_config(config)
        transport_registry.set_event_transport("default", transport)
        client = lightbus.BusClient(config=config, transport_registry=transport_registry, loop=loop)
        bus = lightbus.BusNode(name="", parent=None, bus_client=client)
        return bus

    return inner


@pytest.fixture()
def transactional_bus(dummy_bus: BusNode, new_redis_pool, aiopg_connection, aiopg_cursor, loop):
    transport = TransactionalEventTransport(
        child_transport=lightbus.RedisEventTransport(
            redis_pool=new_redis_pool(maxsize=10000),
            consumer_group_prefix="test_cg",
            consumer_name="test_consumer",
        )
    )
    registry = dummy_bus.bus_client.transport_registry
    registry.set_event_transport("default", transport)

    database = DbApiConnection(aiopg_connection, aiopg_cursor)
    block(database.migrate(), loop=loop, timeout=1)
    block(aiopg_cursor.execute("COMMIT"), loop=loop, timeout=1)
    block(aiopg_cursor.execute("BEGIN"), loop=loop, timeout=1)

    return dummy_bus


@pytest.yield_fixture()
def test_table(aiopg_cursor, loop):
    block(aiopg_cursor.execute("DROP TABLE IF EXISTS test_table"), loop=loop, timeout=1)
    block(aiopg_cursor.execute("CREATE TABLE test_table (pk VARCHAR(100))"), loop=loop, timeout=1)
    block(aiopg_cursor.execute("COMMIT"), loop=loop, timeout=1)
    block(aiopg_cursor.execute("BEGIN"), loop=loop, timeout=1)

    class TestTable(object):

        async def total_rows(self):
            await aiopg_cursor.execute("SELECT COUNT(*) FROM test_table")
            return (await aiopg_cursor.fetchone())[0]

    yield TestTable()

    block(aiopg_cursor.execute("DROP TABLE test_table"), loop=loop, timeout=1)
    block(aiopg_cursor.execute("COMMIT"), loop=loop, timeout=1)
    block(aiopg_cursor.execute("BEGIN"), loop=loop, timeout=1)
