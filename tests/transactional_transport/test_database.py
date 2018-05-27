import pytest

from lightbus import EventMessage
from lightbus.exceptions import UnsupportedOptionValue
from lightbus.transports.transactional import DbApiConnection
from tests.transactional_transport.conftest import verification_connection

pytestmark = pytest.mark.unit

# Utility functions


async def total_processed_events():
    async with verification_connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) FROM lightbus_processed_events")
            return (await cursor.fetchone())[0]


async def outbox_size():
    async with verification_connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT COUNT(*) FROM lightbus_event_outbox")
            return (await cursor.fetchone())[0]


async def get_processed_events():
    async with verification_connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT * FROM lightbus_processed_events")
            return await cursor.fetchall()


async def get_outbox():
    async with verification_connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT * FROM lightbus_event_outbox")
            return await cursor.fetchall()


# Tests


@pytest.mark.run_loop
async def test_migrate(dbapi_database: DbApiConnection):
    await dbapi_database.migrate()
    # The following would fail if the tables didn't exist
    assert await total_processed_events() == 0
    assert await outbox_size() == 0


@pytest.mark.run_loop
async def test_transaction_start_commit(dbapi_database: DbApiConnection):
    await dbapi_database.migrate()
    await dbapi_database.start_transaction()
    await dbapi_database.store_processed_event(
        EventMessage(api_name="api", event_name="event", id="123")
    )
    await dbapi_database.commit_transaction()
    assert await total_processed_events() == 1


@pytest.mark.run_loop
async def test_transaction_start_rollback(dbapi_database: DbApiConnection):
    await dbapi_database.migrate()
    await dbapi_database.start_transaction()
    await dbapi_database.store_processed_event(
        EventMessage(api_name="api", event_name="event", id="123")
    )
    await dbapi_database.rollback_transaction()
    assert await total_processed_events() == 0


@pytest.mark.run_loop
async def test_transaction_start_rollback_continue(dbapi_database: DbApiConnection):
    # Check we can still use the connection following a rollback
    await dbapi_database.migrate()
    await dbapi_database.start_transaction()
    await dbapi_database.store_processed_event(
        EventMessage(api_name="api", event_name="event", id="123")
    )
    await dbapi_database.rollback_transaction()  # Rollback
    await dbapi_database.store_processed_event(
        EventMessage(api_name="api", event_name="event", id="123")
    )
    assert await total_processed_events() == 1


@pytest.mark.run_loop
async def test_is_event_duplicate_true(dbapi_database: DbApiConnection):
    await dbapi_database.migrate()
    message = EventMessage(api_name="api", event_name="event", id="123")
    await dbapi_database.store_processed_event(message)
    assert await dbapi_database.is_event_duplicate(message) == True


@pytest.mark.run_loop
async def test_is_event_duplicate_false(dbapi_database: DbApiConnection):
    await dbapi_database.migrate()
    message = EventMessage(api_name="api", event_name="event", id="123")
    assert await dbapi_database.is_event_duplicate(message) == False


@pytest.mark.run_loop
async def test_send_event_ok(dbapi_database: DbApiConnection):
    await dbapi_database.migrate()
    message = EventMessage(api_name="api", event_name="event", kwargs={"field": "abc"}, id="123")
    options = {"key": "value"}
    await dbapi_database.send_event(message, options)
    assert await outbox_size() == 1
    retrieved_message, options = await dbapi_database.consume_pending_events(
        message_id="123"
    ).__anext__()
    assert retrieved_message.id == "123"
    assert retrieved_message.get_kwargs() == {"field": "abc"}
    assert retrieved_message.get_metadata() == {
        "api_name": "api",
        "event_name": "event",
        "id": "123",
    }
    assert options == {"key": "value"}


@pytest.mark.run_loop
async def test_send_event_bad_option_value(dbapi_database: DbApiConnection):
    await dbapi_database.migrate()
    message = EventMessage(api_name="api", event_name="event", kwargs={"field": "abc"}, id="123")
    options = {"key": range(1, 100)}  # not json-serializable
    with pytest.raises(UnsupportedOptionValue):
        await dbapi_database.send_event(message, options)


@pytest.mark.run_loop
async def test_remove_pending_event(dbapi_database: DbApiConnection):
    await dbapi_database.migrate()
    message = EventMessage(api_name="api", event_name="event", kwargs={"field": "abc"}, id="123")
    await dbapi_database.send_event(message, options={})
    assert await outbox_size() == 1
    await dbapi_database.remove_pending_event(message_id="123")
    assert await outbox_size() == 0