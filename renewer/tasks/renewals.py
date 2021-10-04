import logging

from huey import crontab

from renewer.models.cdn import CdnRoute
from renewer.db import SessionHandler
from renewer.json_log import json_log
from renewer.models.domain import DomainRoute
from renewer.huey import huey
from renewer.tasks import alb, cdn, iam, letsencrypt, s3

logger = logging.getLogger(__name__)


@huey.periodic_task(crontab(month="*", day="*", hour="12", minute="0"))
def renew_all_certs():
    routes = []
    with SessionHandler() as session:
        for Route in (CdnRoute, DomainRoute):
            routes.extend(Route.find_active_instances(session))
        for route in routes:
            if route.needs_renewal:
                queue_all_tasks(route, session)


def queue_all_tasks(route, session):
    json_log(
        logger.info,
        {
            "instance_id": route.instance_id,
            "type": route.route_type,
            "message": "queuing renewal",
        },
    )
    if isinstance(route, DomainRoute):
        get_renewal_pipeline = get_domain_renewal_pipeline
    elif isinstance(route, CdnRoute):
        get_renewal_pipeline = get_cdn_renewal_pipeline
    else:
        raise NotImplementedError(
            f"Expected one of DomainRoute, CdnRoute, got {type(route)}"
        )
    pipeline = get_renewal_pipeline(route, session)
    huey.enqueue(pipeline)


def get_domain_renewal_pipeline(alb_route: DomainRoute, session):
    operation = alb_route.create_renewal_operation()
    session.add(operation)
    session.commit()
    pipeline = (
        letsencrypt.create_user.s(operation.id, alb_route.route_type)
        .then(
            letsencrypt.create_private_key_and_csr, operation.id, alb_route.route_type
        )
        .then(letsencrypt.initiate_challenges, operation.id, alb_route.route_type)
        .then(s3.upload_challenge_files, operation.id, alb_route.route_type)
        .then(letsencrypt.answer_challenges, operation.id, alb_route.route_type)
        .then(letsencrypt.retrieve_certificate, operation.id, alb_route.route_type)
        .then(iam.upload_certificate, operation.id, alb_route.route_type)
        .then(alb.associate_certificate, operation.id, alb_route.route_type)
        .then(alb.remove_old_certificate, operation.id, alb_route.route_type)
        .then(alb.wait_for_cert_update, operation.id, alb_route.route_type)
        .then(iam.delete_old_certificate)
    )
    return pipeline


def get_cdn_renewal_pipeline(cdn_route: CdnRoute, session):
    operation = cdn_route.create_renewal_operation()
    session.add(operation)
    session.commit()
    pipeline = (
        letsencrypt.create_user.s(operation.id, cdn_route.route_type)
        .then(
            letsencrypt.create_private_key_and_csr, operation.id, cdn_route.route_type
        )
        .then(letsencrypt.initiate_challenges, operation.id, cdn_route.route_type)
        .then(s3.upload_challenge_files, operation.id, cdn_route.route_type)
        .then(letsencrypt.answer_challenges, operation.id, cdn_route.route_type)
        .then(letsencrypt.retrieve_certificate, operation.id, cdn_route.route_type)
        .then(iam.upload_certificate, operation.id, cdn_route.route_type)
        .then(cdn.associate_certificate, operation.id, cdn_route.route_type)
        .then(cdn.wait_for_distribution, operation.id, cdn_route.route_type)
        .then(iam.delete_old_certificate)
    )
    return pipeline
