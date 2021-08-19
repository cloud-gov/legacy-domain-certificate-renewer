from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import orm

from renewer import db
from renewer.domain_models import (
    DomainRoute,
    DomainAlbProxy,
    DomainCertificate,
    find_active_instances,
)
from renewer import extensions


def test_can_get_session():
    with db.session_handler() as session:
        result = session.execute(
            "SELECT count(1) FROM certificates", bind=db.domain_engine
        )
        assert result.first() == (0,)


def test_can_create_route():
    # the assertion here is really just that no exceptions are raised

    # note that we shouldn't _actually_ be creating routes in this project
    # but this is a test we can do with an empty database
    with db.session_handler() as session:
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
    instances = find_active_instances(clean_db)
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
    doesnt_need_renewal_cert.id = 10
    doesnt_need_renewal_cert.expires = datetime.now() + timedelta(days=31)
    doesnt_need_renewal_old_cert = DomainCertificate()
    doesnt_need_renewal_old_cert.route = doesnt_need_renewal_route
    doesnt_need_renewal_old_cert.id = 11
    doesnt_need_renewal_old_cert.expires = datetime.now() - timedelta(days=31)

    # make a route that needs renewal
    needs_renewal_route = DomainRoute()
    needs_renewal_route.state = "provisioned"
    needs_renewal_route.instance_id = "renew-me"
    needs_renewal_cert = DomainCertificate()
    needs_renewal_cert.route = needs_renewal_route
    needs_renewal_cert.id = 0
    needs_renewal_cert.expires = datetime.now() + timedelta(days=10)
    needs_renewal_old_cert = DomainCertificate()
    needs_renewal_old_cert.route = needs_renewal_route
    needs_renewal_old_cert.id = 1
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
