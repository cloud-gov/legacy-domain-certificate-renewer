import pytest

from renewer.models.cdn import CdnRoute, CdnCertificate


@pytest.fixture(scope="function")
def cdn_route(clean_db):
    route = CdnRoute()
    route.instance_id = "fixture-route"
    route.state = "provisioned"
    route.domain_external = "example.com,www.example.com"
    route.dist_id = "fakedistid"
    route.origin = "cloudfront-origin.cf.local"
    clean_db.add(route)
    clean_db.commit()
    return route


def make_route(session, instance_id: str, domains: str, state: str = "provisioned"):
    route = CdnRoute()
    route.instance_id = instance_id
    route.state = state
    route.domain_external = domains
    session.add(route)
    session.commit()
    return route


def make_cert(session, route, expiration, upload_date, associate_to_route: bool = True):
    certificate = CdnCertificate()
    certificate.expires = expiration
    if associate_to_route:
        certificate.route = route

    certificate.iam_server_certificate_name = (
        f"{route.instance_id}-{upload_date.isoformat()}-{certificate.id}"
    )
    certificate.iam_server_certificate_id = (
        f"FAKE_CERT_ID-{route.instance_id}-{certificate.id}"
    )
    certificate.iam_server_certificate_arn = (
        f"arn:aws:iam:1234:/alb/test/{certificate.iam_server_certificate_name}"
    )
    session.add(certificate)
    session.commit()
    return certificate
