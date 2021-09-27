from typing import List

import pytest

from renewer.models.domain import DomainAlbProxy, DomainRoute, DomainCertificate


@pytest.fixture(scope="function")
def proxy(clean_db):
    arn = "arn:aws:alb:1234"
    proxy = DomainAlbProxy()
    proxy.alb_arn = arn
    proxy.alb_dns_name = "listener.example.com"
    proxy.listener_arn = "arn:aws:listener:1234"
    clean_db.add(proxy)
    clean_db.commit()
    return proxy


@pytest.fixture(scope="function")
def alb_route(clean_db, proxy) -> DomainRoute:
    route = make_route(
        clean_db, proxy, "fixture_route", ["example.com", "www.example.com"]
    )
    return route


def make_route(
    session,
    proxy: DomainAlbProxy,
    instance_id: str,
    domains: List[str],
    state: str = "provisioned",
) -> DomainRoute:
    route = DomainRoute()
    route.instance_id = instance_id
    route.state = state
    route.domains = domains
    route.alb_proxy = proxy
    session.add(route)
    session.commit()
    return route


def make_cert(
    session,
    route: DomainRoute,
    expiration,
    upload_date,
    associate_to_route: bool = True,
) -> DomainCertificate:
    certificate = DomainCertificate()
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
