import pytest

from renewer.cdn_models import CdnRoute


@pytest.fixture(scope="function")
def cdn_route(clean_db):
    route = CdnRoute()
    route.instance_id = "fixture-route"
    route.state = "provisioned"
    route.domain_external = "example.com,www.example.com"
    route.dist_id = "fakedistid"
    clean_db.add(route)
    clean_db.commit()
    return route
