""" Configuration structure generation

We do some pretty exciting things here to generate the configuration
structure.

We load in all available plugins and transports and get the desired
configuration format for each (via the parameters of `from_config()` in both
cases). From there we dynamically generate named tuples which form
the structure for the configuration.

Benefits of this are:

    1. Many configuration errors can be caught early
    2. We can use the schema-related code to generate a JSON schema for the config.
       This can be used for validation, auto completion, and improving tooling in general
       (smart config editing in the management UI?)
    3. Plugins and transports can be assured of reasonable sane data

"""
import inspect
import logging
from typing import NamedTuple, Optional, Union, Mapping, Type

from lightbus import get_available_transports
from lightbus.plugins import get_plugins

logger = logging.getLogger(__name__)


def make_api_config_structure() -> NamedTuple:
    """Create a named tuple structure to hold api configuration

    Example YAML for this structure:

        # YAML root
        apis:
          default:            # <-- This is what we generate
            # Various api-level options
            rpc_timeout: 5
            event_listener_setup_timeout: 1
            event_fire_timeout: 1
            log_level: warning

            event_transport:  # <-- A key for each type of transport (event, rpc, result, schema)
              redis:          # <-- The name of the transport to use as specified in the entrypoint
                url: redis://my_host:9999/0

    """
    plugins = get_plugins()
    transports_by_type = get_available_transports()
    code = f"class ApiConfig(NamedTuple):\n"

    transport_config_structures = {}
    for transport_type, transports in transports_by_type.items():
        transport_config_structure = make_transport_selector_structure(transport_type, transports)
        transport_config_structures[transport_config_structure.__name__] = transport_config_structure
        code += f"    {transport_type}_transport: {transport_config_structure.__name__} = None\n"

    code += (
        f"    rpc_timeout: int = 5\n"
        f"    event_listener_setup_timeout: int = 1\n"
        f"    event_fire_timeout: int = 1\n"
        f"    log_level: Optional[str] = None\n"
    )

    globals_ = globals().copy()
    globals_.update(transport_config_structures)
    exec(code, globals_)
    return globals_['ApiConfig']


def make_transport_selector_structure(type_, transports):
    class_name = f"{type_.title()}TransportSelector"
    code = f"class {class_name}(NamedTuple):\n    pass\n"
    config_classes = {}
    for _, transport_name, transport_class in transports:
        transport_config_structure = make_transport_config_structure(type_, transport_class)
        if transport_config_structure:
            config_classes[transport_config_structure.__name__] = transport_config_structure
            code += f"    {transport_name}: Optional[{transport_config_structure.__name__}] = None\n"

    globals_ = globals().copy()
    globals_.update(config_classes)
    exec(code, globals_)
    return globals_[class_name]


def make_transport_config_structure(type_, transport_class):
    class_name = f"{transport_class.__name__}Config"
    code = f"class {class_name}(NamedTuple):\n    pass\n"
    vars = dict(p={})

    parameters = inspect.signature(transport_class.from_config).parameters.values()
    for parameter in parameters:
        if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.VAR_POSITIONAL):
            logger.warning(
                'Positional-only arguments are not supported in from_config() on transport {}'.format(transport_class)
            )
        elif parameter.kind in (parameter.VAR_KEYWORD, ):
            logger.warning(
                '**kwargs-style parameters are not supported in from_config() on transport {}'.format(transport_class)
            )
        else:
            name = parameter.name
            vars['p'][name] = parameter
            code += f"    {name}: p['{name}'].annotation = p['{name}'].default\n"

    globals_ = globals().copy()
    globals_.update(vars)
    exec(code, globals_)
    return globals_[class_name]


ApiConfig = make_api_config_structure()


class BusConfig(NamedTuple):
    schema_load_timeout: int = 5
    schema_add_api_timeout: int = 1
    schema_human_readable: bool = True
    log_level: str = 'debug'


class RootConfig(NamedTuple):
    bus: BusConfig = BusConfig()
    apis: Mapping[str, ApiConfig] = {}
