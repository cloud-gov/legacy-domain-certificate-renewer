from renewer import huey
from renewer.aws import cloudfront
from renewer.cdn_models import CdnOperation


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
