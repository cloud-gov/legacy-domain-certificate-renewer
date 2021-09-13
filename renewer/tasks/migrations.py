from huey import crontab

from renewer.db import SessionHandler

from renewer.domain_models import find_active_instances, DomainRoute
from renewer import huey


@huey.huey.periodic_task(crontab(month="*", day="*", hour="6", minute="0"))
def backport_all_manual_certs():
    with SessionHandler() as session:
        for instance in find_active_instances(session):
            backport_cert(instance.instance_id)


@huey.retriable_task
def backport_cert(session, instance_id):
    instance = session.query(DomainRoute).get(instance_id)
    cert = instance.backport_manual_certs()
    session.add(cert)
    session.commit()
