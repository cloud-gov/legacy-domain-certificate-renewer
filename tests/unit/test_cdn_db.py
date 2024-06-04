from datetime import datetime, timedelta
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import orm

from renewer import db
from renewer.models.cdn import CdnRoute, CdnOperation, CdnAcmeUserV2, CdnCertificate
from renewer import extensions


def test_can_get_session():
    with db.SessionHandler() as session:
        result = session.execute(
            sa.text("SELECT count(1) FROM certificates"), bind=db.cdn_engine
        )
        assert result.first() == (0,)


def test_can_create_route():
    # the assertion here is really just that no exceptions are raised

    # note that we shouldn't _actually_ be creating routes in this project
    # but this is a test we can do with an empty database
    with db.SessionHandler() as session:
        route = CdnRoute()
        route.id = 12345
        route.instance_id = "disposable-route-id"
        route.state = "deprovisioned"
        session.add(route)
        session.commit()

        route = session.query(CdnRoute).filter_by(id=12345).first()
        session.delete(route)
        session.commit()
        session.close()


def test_check_connections():
    engine = sa.create_engine("postgresql://localhost:1234")
    Session = orm.sessionmaker(bind=engine)
    with pytest.raises(Exception):
        db.check_connections(cdn_session_maker=Session, cdn_binding=engine)

    with pytest.raises(Exception):
        db.check_connections(cdn_session_maker=Session, external_domain_binding=engine)
    db.check_connections()


def test_cdnroute_model_can_return_single_domain_in_domain_external_list(clean_db):
    route = CdnRoute()
    route.id = 12345
    route.instance_id = "disposable-route-id"
    route.state = "deprovisioned"
    route.domain_external = "example.com"
    clean_db.add(route)
    clean_db.commit()

    route = clean_db.query(CdnRoute).filter_by(id=12345).first()
    assert route.domain_external_list() == ["example.com"]


def test_cdnroute_model_can_return_multiple_domains_in_domain_external_list(clean_db):
    route = CdnRoute()
    route.id = 12345
    route.instance_id = "disposable-route-id"
    route.state = "deprovisioned"
    route.domain_external = "example1.com,example2.com,example3.com"
    clean_db.add(route)
    clean_db.commit()

    route = clean_db.query(CdnRoute).filter_by(id=12345).first()
    assert sorted(route.domain_external_list()) == sorted(
        ["example1.com", "example2.com", "example3.com"]
    )


def test_stores_acmeuser_private_key_pem_encrypted(clean_db):

    acme_user = CdnAcmeUserV2()
    acme_user.private_key_pem = "UNENCRYPTED"
    acme_user.email = "email"
    acme_user.uri = "uri"
    clean_db.add(acme_user)
    clean_db.commit()
    row = clean_db.execute(
        sa.text(f"SELECT private_key_pem FROM acme_user_v2 WHERE id='{acme_user.id}'"),
        bind_arguments={"bind": db.cdn_engine},
    ).first()
    assert row
    assert row[0] != "UNENCRYPTED"


def test_stores_service_instance_private_key_pem_encrypted(clean_db):

    cert = CdnCertificate()
    cert.private_key_pem = "UNENCRYPTED"
    clean_db.add(cert)
    clean_db.commit()
    row = clean_db.execute(
        sa.text(f"SELECT private_key_pem FROM certificates WHERE id='{cert.id}'"),
        bind_arguments={"bind": db.cdn_engine},
    ).first()
    assert row
    assert row[0] != "UNENCRYPTED"


def test_need_renewal_basic(clean_db):
    """
    test whether a domain needs renewal
    This test doesn't handle cases where the domain has a
    newer cert not tracked in the database
    """
    # make a route and cert that don't need renewal
    doesnt_need_renewal_route = CdnRoute()
    doesnt_need_renewal_route.state = "provisioned"
    doesnt_need_renewal_route.instance_id = "dont-renew-me"
    doesnt_need_renewal_cert = CdnCertificate()
    doesnt_need_renewal_cert.route = doesnt_need_renewal_route
    doesnt_need_renewal_cert.expires = datetime.now() + timedelta(days=31)
    doesnt_need_renewal_old_cert = CdnCertificate()
    doesnt_need_renewal_old_cert.route = doesnt_need_renewal_route
    doesnt_need_renewal_old_cert.expires = datetime.now() - timedelta(days=31)

    # make a route that needs renewal
    needs_renewal_route = CdnRoute()
    needs_renewal_route.state = "provisioned"
    needs_renewal_route.instance_id = "renew-me"
    needs_renewal_cert = CdnCertificate()
    needs_renewal_cert.route = needs_renewal_route
    needs_renewal_cert.expires = datetime.now() + timedelta(days=10)
    needs_renewal_old_cert = CdnCertificate()
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


def test_get_user(clean_db):
    """
    setup:
    - user0 has 1 active, 1 inactive route
    - user1 has 2 active, 1 inactive route
    expectation:
    - user0 should be our user, because it has fewer routes
    """

    def make_route_for_user(user, state: str = "provisioned"):
        route = CdnRoute()
        route.instance_id = uuid.uuid4()
        route.acme_user = user
        route.email = "me@example.com"
        route.state = state
        return route

    to_commit = []
    user0 = CdnAcmeUserV2()
    user0.email = "me@example.com"
    user0.uri = "uri"
    to_commit.append(user0)

    user1 = CdnAcmeUserV2()
    user1.email = "me@example.com"
    user1.uri = "uri"
    to_commit.append(user1)

    to_commit.append(make_route_for_user(user0))

    for _ in range(2):
        to_commit.append(make_route_for_user(user1))

    clean_db.add_all(to_commit)
    clean_db.commit()

    next_user = CdnAcmeUserV2.get_user(clean_db)
    assert next_user.id == user0.id

    # swap a route from user1 to user0
    # now user0 has more, so user1 should be returned
    route = user1.routes[0]
    route.acme_user = user0
    clean_db.add_all([user0, user1, route])
    clean_db.commit()

    next_user = CdnAcmeUserV2.get_user(clean_db)
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
    assert CdnAcmeUserV2.get_user(clean_db) is None
