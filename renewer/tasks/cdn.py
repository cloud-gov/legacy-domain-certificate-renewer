import logging

from renewer import huey
from renewer.aws import cloudfront
from renewer.json_log import json_log
from renewer.models.cdn import CdnOperation, CdnRoute
from renewer.extensions import config
from renewer.models.common import RouteType


logger = logging.getLogger(__name__)


def raise_for_type(route_type: RouteType):
    if route_type is not RouteType.CDN:
        raise RuntimeError("running CDN task against non-CDN route type")


@huey.retriable_task
def associate_certificate(session, operation_id: int, route_type: RouteType):
    raise_for_type(route_type)
    operation = session.query(CdnOperation).get(operation_id)
    certificate = operation.certificate
    route = operation.route

    json_log(
        logger.info,
        {
            "instance_id": route.instance_id,
            "message": f"updating certificate on cloudfront. New certificate id: {certificate.id}",
        },
    )
    config = cloudfront.get_distribution_config(Id=route.dist_id)
    config["DistributionConfig"]["ViewerCertificate"][
        "IAMCertificateId"
    ] = certificate.iam_server_certificate_id
    cloudfront.update_distribution(
        DistributionConfig=config["DistributionConfig"],
        Id=route.dist_id,
        IfMatch=config["ETag"],
    )
    certificate.route = route

    session.add(certificate)
    session.commit()


@huey.retriable_task
def wait_for_distribution(session, operation_id: int, route_type: RouteType):
    raise_for_type(route_type)
    operation: CdnOperation = session.query(CdnOperation).get(operation_id)
    route: CdnRoute = operation.route
    json_log(
        logger.info,
        {
            "instance_id": route.instance_id,
            "message": "waiting for cloudfront distribution",
        },
    )
    waiter = cloudfront.get_waiter("distribution_deployed")
    waiter.wait(
        Id=route.dist_id,
        WaiterConfig={
            "Delay": config.AWS_POLL_WAIT_TIME_IN_SECONDS,
            "MaxAttempts": config.AWS_POLL_MAX_ATTEMPTS,
        },
    )
