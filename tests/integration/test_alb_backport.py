from datetime import datetime

import pytest

from renewer.domain_models import DomainAlbProxy, DomainRoute, DomainCertificate
from renewer.tasks import migrations


def test_backport_all_certs(clean_db, alb, iam_govcloud, immediate_huey):
    # make a route
    proxy = DomainAlbProxy()
    proxy.alb_arn = "arn:aws:alb:123"
    proxy.alb_dns_name = "example.com"
    proxy.listener_arn = "arn:aws:listener:123"
    route = DomainRoute()
    route.state = "provisioned"
    route.instance_id = "renew-me"
    route.alb_proxy_arn = "arn:aws:alb:123"
    old_cert = DomainCertificate()
    old_cert.route = route
    old_cert.expires = datetime(year=2021, month=2, day=1, hour=0, minute=0, second=0)
    old_cert.arn = "arn:aws:iam:1234:server-certificate/domains/local/cf-domains-renew-me-2021-01-01_12-34-56"
    clean_db.add(proxy)
    clean_db.add(route)
    clean_db.add(old_cert)
    clean_db.commit()

    # get the certs for the alb
    alb.expect_get_certificates_for_listener(
        "arn:aws:listener:123",
        7,
        "arn:aws:iam:1234:server-certificate/domains/local/cf-domains-renew-me-2021-03-12_12-34-12",
    )
    iam_govcloud.expect_get_server_certificate(
        "cf-domains-renew-me-2021-03-12_12-34-12", "2021-03-12T12:34:12Z"
    )
    clean_db.expunge_all()

    # function we're actually testing
    migrations.backport_all_manual_certs()

    # flush
    clean_db.expunge_all()
    # check the cert was backported
    route = clean_db.query(DomainRoute).filter_by(instance_id="renew-me").first()
    cert = route.certificates[0]
    assert (
        cert.arn
        == "arn:aws:iam:1234:server-certificate/domains/local/cf-domains-renew-me-2021-03-12_12-34-12"
    )
    assert cert.expires is not None
    assert cert.name == "cf-domains-renew-me-2021-03-12_12-34-12"


def test_no_error_when_no_backport(clean_db, alb, iam_govcloud, immediate_huey):
    # make a route
    proxy = DomainAlbProxy()
    proxy.alb_arn = "arn:aws:alb:123"
    proxy.alb_dns_name = "example.com"
    proxy.listener_arn = "arn:aws:listener:123"
    route = DomainRoute()
    route.state = "provisioned"
    route.instance_id = "renew-me"
    route.alb_proxy_arn = "arn:aws:alb:123"
    old_cert = DomainCertificate()
    old_cert.route = route
    old_cert.expires = datetime(year=2021, month=2, day=1, hour=0, minute=0, second=0)
    old_cert.arn = "arn:aws:iam:1234:server-certificate/domains/local/cf-domains-renew-me-2021-01-01_12-34-56"
    clean_db.add(proxy)
    clean_db.add(route)
    clean_db.add(old_cert)
    clean_db.commit()

    # get the certs for the alb
    alb.expect_get_certificates_for_listener(
        "arn:aws:listener:123",
        7,
        "arn:aws:iam:1234:server-certificate/domains/local/cf-domains-renew-me-2021-01-01_12-34-56",
    )
    clean_db.expunge_all()

    # function we're actually testing
    # the test here is just that it doesn't blow up
    migrations.backport_cert("renew-me")
