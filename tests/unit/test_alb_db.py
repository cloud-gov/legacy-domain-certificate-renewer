from datetime import datetime, timedelta
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import orm

from renewer import db
from renewer.models.domain import (
    DomainRoute,
    DomainAlbProxy,
    DomainCertificate,
    DomainOperation,
    DomainAcmeUserV2,
)
from renewer import extensions


def test_can_get_session():
    with db.SessionHandler() as session:
        result = session.execute(
            "SELECT count(1) FROM certificates", bind=db.domain_engine
        )
        assert result.first() == (0,)


def test_can_create_route():
    # the assertion here is really just that no exceptions are raised

    # note that we shouldn't _actually_ be creating routes in this project
    # but this is a test we can do with an empty database
    with db.SessionHandler() as session:
        route = DomainRoute()
        route.instance_id = "12345"
        route.state = "deprovisioned"
        route.domains = ["example1.com", "example2.com", "example3.com"]

        session.add(route)
        session.commit()

        route = session.query(DomainRoute).filter_by(instance_id="12345").first()
        session.delete(route)
        session.commit()
        session.close()


def test_route_proxy_relationship(clean_db):
    proxy = DomainAlbProxy()
    proxy.alb_arn = "arn:123"
    proxy.alb_dns_name = "foo.example.com"
    proxy.listener_arn = "arn:234"
    clean_db.add(proxy)
    clean_db.commit()
    route = DomainRoute()
    route.alb_proxy_arn = "arn:123"
    route.instance_id = "1234"
    route.state = "provisioned"
    clean_db.add(route)
    clean_db.commit()
    route = clean_db.query(DomainRoute).filter_by(instance_id="1234").first()
    assert route.alb_proxy.listener_arn == "arn:234"


def test_find_instances(clean_db):
    states = [
        "provisioned",
        "deprovisioned",
        "deprovisioning",
        "this-state-should-never-exist",
    ]
    for state in states:
        domain_route = DomainRoute()
        domain_route.state = state
        domain_route.instance_id = f"id-{state}"
        clean_db.add(domain_route)
    clean_db.commit()
    clean_db.close()
    instances = DomainRoute.find_active_instances(clean_db)
    assert len(instances) == 1
    assert instances[0].state == "provisioned"


def test_need_renewal_basic(clean_db):
    """
    test whether a domain needs renewal
    This test doesn't handle cases where the domain has a
    newer cert not tracked in the database
    """
    # make a route and cert that don't need renewal
    doesnt_need_renewal_route = DomainRoute()
    doesnt_need_renewal_route.state = "provisioned"
    doesnt_need_renewal_route.instance_id = "dont-renew-me"
    doesnt_need_renewal_cert = DomainCertificate()
    doesnt_need_renewal_cert.route = doesnt_need_renewal_route
    doesnt_need_renewal_cert.expires = datetime.now() + timedelta(days=31)
    doesnt_need_renewal_old_cert = DomainCertificate()
    doesnt_need_renewal_old_cert.route = doesnt_need_renewal_route
    doesnt_need_renewal_old_cert.expires = datetime.now() - timedelta(days=31)

    # make a route that needs renewal
    needs_renewal_route = DomainRoute()
    needs_renewal_route.state = "provisioned"
    needs_renewal_route.instance_id = "renew-me"
    needs_renewal_cert = DomainCertificate()
    needs_renewal_cert.route = needs_renewal_route
    needs_renewal_cert.expires = datetime.now() + timedelta(days=10)
    needs_renewal_old_cert = DomainCertificate()
    needs_renewal_old_cert.route = needs_renewal_route
    needs_renewal_old_cert.expires = datetime.now() - timedelta(days=10)

    # commit them (this probably isn't necessary, but helps ensure we made them correctly)
    clean_db.add(doesnt_need_renewal_route)
    clean_db.add(doesnt_need_renewal_cert)
    clean_db.add(doesnt_need_renewal_old_cert)
    clean_db.add(needs_renewal_route)
    clean_db.add(needs_renewal_cert)
    clean_db.add(needs_renewal_old_cert)
    clean_db.commit()

    # check if they need renewal
    assert needs_renewal_route.needs_renewal
    assert not doesnt_need_renewal_route.needs_renewal


def test_backport_from_manual_renewal(clean_db, alb, iam_govcloud):
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
        "cf-domains-renew-me-2021-03-12_12-34-12",
        datetime.strptime("2021-03-12T12:34:12Z", "%Y-%m-%dT%H:%M:%SZ"),
    )

    cert = route.backport_manual_certs()
    clean_db.add(cert)
    clean_db.commit()

    clean_db.expunge_all()
    route = clean_db.query(DomainRoute).filter_by(instance_id="renew-me").first()
    cert = route.certificates[0]
    assert (
        cert.iam_server_certificate_arn
        == "arn:aws:iam:1234:server-certificate/domains/local/cf-domains-renew-me-2021-03-12_12-34-12"
    )
    assert cert.expires is not None
    assert cert.iam_server_certificate_name == "cf-domains-renew-me-2021-03-12_12-34-12"


def test_backport_from_manual_renewal_ignores_existing(clean_db, alb, iam_govcloud):
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
    old_cert.iam_server_certificate_arn = "arn:aws:iam:1234:server-certificate/domains/local/cf-domains-renew-me-2021-01-01_12-34-56"
    old_cert.iam_server_certificate_name = "cf-domains-renew-me-2021-01-01_12-34-56"
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

    cert = route.backport_manual_certs()
    assert cert is None

    clean_db.expunge_all()
    route = clean_db.query(DomainRoute).filter_by(instance_id="renew-me").first()
    cert = route.certificates[0]
    assert (
        cert.iam_server_certificate_arn
        == "arn:aws:iam:1234:server-certificate/domains/local/cf-domains-renew-me-2021-01-01_12-34-56"
    )
    assert cert.expires is not None
    assert cert.iam_server_certificate_name == "cf-domains-renew-me-2021-01-01_12-34-56"


def test_stores_acmeuser_private_key_pem_encrypted(clean_db):

    acme_user = DomainAcmeUserV2()
    acme_user.private_key_pem = "UNENCRYPTED"
    acme_user.email = "email"
    acme_user.uri = "uri"
    clean_db.add(acme_user)
    clean_db.commit()
    row = clean_db.execute(
        f"select private_key_pem from acme_user_v2 where id='{acme_user.id}'",
        bind_arguments={"bind": db.domain_engine},
    ).first()
    assert row
    assert row[0] != "UNENCRYPTED"


def test_stores_service_instance_private_key_pem_encrypted(clean_db):

    cert = DomainCertificate()
    cert.private_key_pem = "UNENCRYPTED"
    clean_db.add(cert)
    clean_db.commit()
    row = clean_db.execute(
        f"select private_key_pem from certificates where id='{cert.id}'",
        bind_arguments={"bind": db.domain_engine},
    ).first()
    assert row
    assert row[0] != "UNENCRYPTED"


def test_get_user(clean_db):
    """
    setup:
    - user0 has 1 active, 1 inactive route
    - user1 has 2 active, 1 inactive route
    expectation:
    - user0 should be our user, because it has fewer routes
    """

    def make_route_for_user(user, state: str = "provisioned"):
        route = DomainRoute()
        route.instance_id = uuid.uuid4()
        route.acme_user = user
        route.email = "me@example.com"
        route.state = state
        return route

    to_commit = []
    user0 = DomainAcmeUserV2()
    user0.email = "me@example.com"
    user0.uri = "uri"
    to_commit.append(user0)

    user1 = DomainAcmeUserV2()
    user1.email = "me@example.com"
    user1.uri = "uri"
    to_commit.append(user1)

    to_commit.append(make_route_for_user(user0))

    for _ in range(2):
        to_commit.append(make_route_for_user(user1))

    clean_db.add_all(to_commit)
    clean_db.commit()

    next_user = DomainAcmeUserV2.get_user(clean_db)
    assert next_user.id == user0.id

    # swap a route from user1 to user0
    # now user0 has more, so user1 should be returned
    route = user1.routes[0]
    route.acme_user = user0
    clean_db.add_all([user0, user1, route])
    clean_db.commit()

    next_user = DomainAcmeUserV2.get_user(clean_db)
    assert next_user.id == user1.id

    # now add routes to both users, making them both full
    # we should get None, which indicates there are no users
    # with few enough routes
    to_commit[:] = []
    to_commit.append(make_route_for_user(user0))
    for _ in range(2):
        to_commit.append(make_route_for_user(user1))
    clean_db.add_all(to_commit)
    clean_db.commit()
    assert DomainAcmeUserV2.get_user(clean_db) is None
