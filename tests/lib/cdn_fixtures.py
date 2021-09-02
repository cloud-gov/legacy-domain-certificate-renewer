import pytest

from renewer.cdn_models import CdnRoute


@pytest.fixture(scope="function")
def cdn_route(clean_db):
    route = CdnRoute()
    route.instance_id = "fixture-route"
    route.state = "provisioned"
    route.domains = "example.com"
    clean_db.add(route)
    clean_db.commit()
    return route
