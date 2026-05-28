from client_core.config import ClientConfig
from conf_client._version import __version__, __package_name__

CLIENT_CONFIG = ClientConfig(
    prog="conf-client",
    description="Configuration client for Ophix configuration server",
    env_file=".conf.env",
    server_url_key="CONFSERVER_URL",
    api_token_key="CONFSERVER_API_TOKEN",
    ca_cert_key="CONFSERVER_CA_CERT",
    client_name="conf",
    version=__version__,
    package_name=__package_name__,
)
