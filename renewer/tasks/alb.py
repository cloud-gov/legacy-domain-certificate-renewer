from renewer import huey
from renewer.aws import alb
from renewer.domain_models import DomainOperation


@huey.retriable_task
def associate_certificate(session, operation_id):
    operation = session.query(DomainOperation).get(operation_id)
    certificate = operation.certificate
    route = operation.route
    route_alb = route.alb_proxy

    alb.add_listener_certificates(
        ListenerArn=route_alb.listener_arn,
        Certificates=[{"CertificateArn": certificate.iam_server_certificate_arn}],
    )


@huey.retriable_task
def remove_old_certificate(session, operation_id):
    operation = session.query(DomainOperation).get(operation_id)
    new_certificate = operation.certificate
    route = operation.route
    route_alb = route.alb_proxy
    old_certificate = route.certificates[0]

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
