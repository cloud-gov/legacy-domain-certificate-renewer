import pytest
import sqlalchemy as sa
from sqlalchemy import orm
from renewer import db
from renewer import models
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
        route = models.DomainRoute()
        route.instance_id = "12345"
        route.state = "deprovisioned"
        route.domains = ["example1.com", "example2.com", "example3.com"]

        session.add(route)
        session.commit()

        route = session.query(models.DomainRoute).filter_by(instance_id="12345").first()
        session.delete(route)
        session.commit()
        session.close()


def test_route_proxy_relationship(clean_db):
    proxy = models.DomainAlbProxy()
    proxy.alb_arn = "arn:123"
    proxy.alb_dns_name = "foo.example.com"
    proxy.listener_arn = "arn:234"
    clean_db.add(proxy)
    clean_db.commit()
    route = models.DomainRoute()
    route.alb_proxy_arn = "arn:123"
    route.instance_id = "1234"
    route.state = "provisioned"
    clean_db.add(route)
    clean_db.commit()
    route = clean_db.query(models.DomainRoute).filter_by(instance_id="1234").first()
    assert route.alb_proxy.listener_arn == "arn:234"
