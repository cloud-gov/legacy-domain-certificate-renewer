from renewer import huey
from renewer.aws import cloudfront
from renewer.cdn_models import CdnOperation, CdnRoute
from renewer.extensions import config


@huey.retriable_task
def associate_certificate(session, operation_id):
    operation = session.query(CdnOperation).get(operation_id)
    certificate = operation.certificate
    route = operation.route
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
def wait_for_distribution(session, operation_id):
    operation: CdnOperation = session.query(CdnOperation).get(operation_id)
    route: CdnRoute = operation.route
    waiter = cloudfront.get_waiter("distribution_deployed")
    waiter.wait(
        Id=route.dist_id,
        WaiterConfig={
            "Delay": config.AWS_POLL_WAIT_TIME_IN_SECONDS,
            "MaxAttempts": config.AWS_POLL_MAX_ATTEMPTS,
        },
    )
