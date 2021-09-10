import pytest
import sqlalchemy as sa
from sqlalchemy import orm
from renewer import db
from renewer import cdn_models
from renewer import extensions


def test_can_get_session():
    with db.session_handler() as session:
        result = session.execute(
            "SELECT count(1) FROM certificates", bind=db.cdn_engine
        )
        assert result.first() == (0,)


def test_can_create_route():
    # the assertion here is really just that no exceptions are raised

    # note that we shouldn't _actually_ be creating routes in this project
    # but this is a test we can do with an empty database
    with db.session_handler() as session:
        route = cdn_models.CdnRoute()
        route.id = 12345
        route.instance_id = "disposable-route-id"
        route.state = "deprovisioned"
        session.add(route)
        session.commit()

        route = session.query(cdn_models.CdnRoute).filter_by(id=12345).first()
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
    route = cdn_models.CdnRoute()
    route.id = 12345
    route.instance_id = "disposable-route-id"
    route.state = "deprovisioned"
    route.domain_external = "example.com"
    clean_db.add(route)
    clean_db.commit()

    route = clean_db.query(cdn_models.CdnRoute).filter_by(id=12345).first()
    assert route.domain_external_list() == ["example.com"]


def test_cdnroute_model_can_return_multiple_domains_in_domain_external_list(clean_db):
    route = cdn_models.CdnRoute()
    route.id = 12345
    route.instance_id = "disposable-route-id"
    route.state = "deprovisioned"
    route.domain_external = "example1.com,example2.com,example3.com"
    clean_db.add(route)
    clean_db.commit()

    route = clean_db.query(cdn_models.CdnRoute).filter_by(id=12345).first()
    assert sorted(route.domain_external_list()) == sorted(
        ["example1.com", "example2.com", "example3.com"]
    )


def test_renew_creates_operation(clean_db):
    route = cdn_models.CdnRoute()
    route.state = "provisioned"
    route.id = 1234
    route.instance_id = "renew-me"
    clean_db.add(route)
    clean_db.commit()

    route = clean_db.query(cdn_models.CdnRoute).filter_by(id=1234).first()
    route.renew()

    operation = clean_db.query(cdn_models.CdnOperation).filter_by(route_id=1234).first()
    assert operation is not None
    assert operation.route == route
    assert operation.action == "renew"


def test_stores_acmeuser_private_key_pem_encrypted(clean_db):

    acme_user = cdn_models.CdnAcmeUserV2()
    acme_user.private_key_pem = "UNENCRYPTED"
    acme_user.email = "email"
    acme_user.uri = "uri"
    clean_db.add(acme_user)
    clean_db.commit()
    row = clean_db.execute(
        f"select private_key_pem from acme_user_v2 where id='{acme_user.id}'",
        bind_arguments={"bind": db.cdn_engine},
    ).first()
    assert row
    assert row[0] != "UNENCRYPTED"


def test_stores_service_instance_private_key_pem_encrypted(clean_db):

    cert = cdn_models.CdnCertificate()
    cert.private_key_pem = "UNENCRYPTED"
    clean_db.add(cert)
    clean_db.commit()
    row = clean_db.execute(
        f"select private_key_pem from certificates where id='{cert.id}'",
        bind_arguments={"bind": db.cdn_engine},
    ).first()
    assert row
    assert row[0] != "UNENCRYPTED"
