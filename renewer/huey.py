import logging
from huey import RedisHuey
from redis import ConnectionPool, SSLConnection

from renewer.extensions import config
from renewer import db

logger = logging.getLogger(__name__)

if config.REDIS_SSL:
    redis_kwargs = dict(connection_class=SSLConnection, ssl_cert_reqs=None)
else:
    redis_kwargs = dict()

connection_pool = ConnectionPool(
    host=config.REDIS_HOST,
    port=config.REDIS_PORT,
    password=config.REDIS_PASSWORD,
    **redis_kwargs,
)
huey = RedisHuey(connection_pool=connection_pool)

# Normal task, no retries
nonretriable_task = huey.context_task(db.session_handler(), as_argument=True)

# These tasks retry every 10 minutes for four hours.
retriable_task = huey.context_task(
    db.session_handler(), as_argument=True, retries=6 * 4, retry_delay=10 * 60
)
