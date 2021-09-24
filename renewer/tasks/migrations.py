import logging

from huey import crontab

from renewer.db import SessionHandler
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
    logger.info(f"backporting cert for {instance_id}")
    instance = session.query(DomainRoute).get(instance_id)
    cert = instance.backport_manual_certs()
    if cert is not None:
        session.add(cert)
        session.commit()
        logger.info(f"backported cert for {instance_id}")
