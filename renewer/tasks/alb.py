import logging
import time

from renewer import huey
from renewer.aws import alb
from renewer.json_log import json_log
from renewer.models.domain import DomainOperation
from renewer.extensions import config
from renewer.models.common import RouteType

logger = logging.getLogger(__name__)


def raise_for_type(route_type: RouteType):
    if route_type is not RouteType.ALB:
        raise RuntimeError("running ALB task against non-ALB route type")


@huey.retriable_task
def associate_certificate(session, operation_id: int, route_type: RouteType):
    raise_for_type(route_type)
    operation = session.query(DomainOperation).get(operation_id)
    certificate = operation.certificate
    route = operation.route
    route_alb = route.alb_proxy
    json_log(
        logger.info,
        {
            "instance_id": route.instance_id,
            "message": f"updating certificate on alb proxy {route_alb.listener_arn}. New certificate id: {certificate.id}",
        },
    )

    alb.add_listener_certificates(
        ListenerArn=route_alb.listener_arn,
        Certificates=[{"CertificateArn": certificate.iam_server_certificate_arn}],
    )


@huey.retriable_task
def remove_old_certificate(session, operation_id: int, route_type: RouteType):
    raise_for_type(route_type)
    operation = session.query(DomainOperation).get(operation_id)
    new_certificate = operation.certificate
    route = operation.route
    route_alb = route.alb_proxy
    old_certificate = route.certificates[0]
    json_log(
        logger.info,
        {
            "instance_id": route.instance_id,
            "message": f"removing certificate on alb proxy {route_alb.listener_arn}. Old certificate id: {old_certificate.id}",
        },
    )

    if (
        old_certificate.iam_server_certificate_arn
        != new_certificate.iam_server_certificate_arn
    ):
        alb.remove_listener_certificates(
            ListenerArn=route_alb.listener_arn,
            Certificates=[
                {"CertificateArn": old_certificate.iam_server_certificate_arn}
            ],
        )

    new_certificate.route = route
    session.add(new_certificate)
    session.commit()


@huey.nonretriable_task
def wait_for_cert_update(session, operation_id: int, route_type: RouteType):
    raise_for_type(route_type)
    time.sleep(config.IAM_PROPOGATION_TIME)
