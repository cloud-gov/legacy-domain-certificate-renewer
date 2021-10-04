import logging

from huey import crontab

from renewer.db import SessionHandler
from renewer.json_log import json_log
from renewer.models.domain import DomainRoute
from renewer import huey

logger = logging.getLogger(__name__)


@huey.huey.periodic_task(crontab(month="*", day="*", hour="6", minute="0"))
def backport_all_manual_certs():
    with SessionHandler() as session:
        for instance in DomainRoute.find_active_instances(session):
            backport_cert(instance.instance_id)


@huey.nonretriable_task
def backport_cert(session, instance_id):
    json_log(logger.info, {"instance_id": instance_id, "message": "backporting cert"})
    instance = session.query(DomainRoute).get(instance_id)
    cert = instance.backport_manual_certs()
    if cert is not None:
        session.add(cert)
        session.commit()
        json_log(
            logger.info, {"instance_id": instance_id, "message": "backported cert"}
        )
