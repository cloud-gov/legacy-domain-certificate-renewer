import pytest

from renewer import smtp
from renewer.models.cdn import CdnRoute
from renewer.models.domain import DomainRoute


@pytest.mark.parametrize("Route", [DomainRoute, CdnRoute])
def test_email_doesnt_explode(clean_db, Route):
    route = Route(instance_id="whatevs", state="provisioned")
    operation = route.create_renewal_operation()
    smtp.send_failed_operation_alert(operation)
