import logging
from huey import RedisHuey, signals
from redis import ConnectionPool, SSLConnection

from renewer.extensions import config
from renewer import db
from renewer.models.common import RouteType, OperationState
from renewer.models.cdn import CdnOperation
from renewer.models.domain import DomainOperation
from renewer.smtp import send_failed_operation_alert

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
# when using a `nonretriable_task`, the first argument to the function will be
# an open session handle
nonretriable_task = huey.context_task(db.SessionHandler(), as_argument=True)

# These tasks retry every 10 minutes for four hours.
# when using a `retriable_task`, the first argument to the function will be
# an open session handle
retriable_task = huey.context_task(
    db.SessionHandler(), as_argument=True, retries=6 * 4, retry_delay=10 * 60
)


@huey.signal(signals.SIGNAL_ERROR)
def mark_operation_failed(signal, task, exc=None):
    args, kwargs = task.data

    if task.retries:
        return
    operation_id = args[0]
    route_type = args[1]
    if route_type == RouteType.ALB:
        Operation = DomainOperation
    else:
        Operation = CdnOperation
    with db.SessionHandler() as session:
        try:
            operation = session.query(Operation).get(operation_id)
        except BaseException as e:
            logger.exception(
                msg=f"exception loading operation for args {args}", exc_info=e
            )
            # assume this task doesn't follow our pattern of operation_id as the first param
            # in which case this task is not a part of a provisioning/upgrade/deprovisioning pipeline
            return
        operation.state = OperationState.FAILED.value
        session.add(operation)
        session.commit()
        send_failed_operation_alert(operation)
