from django import db


def uses_django_db(f):
    """Ensures Django discards any broken database connections

    Django normally cleans up connections once a web request has
    been processed. However, here we are not serving web requests
    and are outside of Django's request handling logic. We therefore
    need to make sure we cleanup any broken database connections.
    """
    # TODO: Move this into middleware
    #       (Tracked in: https://github.com/adamcharnock/lightbus/issues/6)

    def wrapped(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except (db.InterfaceError, db.OperationalError):
            db.connection.close()
            raise

    return wrapped
