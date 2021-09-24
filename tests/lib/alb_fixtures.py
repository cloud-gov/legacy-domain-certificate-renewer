import pytest

from renewer.models.domain import DomainAlbProxy, DomainRoute


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
def alb_route(clean_db, proxy):
    route = DomainRoute()
    route.instance_id = "fixture-route"
    route.state = "provisioned"
    route.domains = ["example.com", "www.example.com"]
    route.alb_proxy = proxy
    clean_db.add(route)
    clean_db.commit()
    return route
