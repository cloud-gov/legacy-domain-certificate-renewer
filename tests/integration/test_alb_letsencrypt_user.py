import pytest

from renewer.domain_models import (
    DomainAlbProxy,
    DomainOperation,
    DomainRoute,
    DomainAcmeUserV2,
)
from renewer.tasks import letsencrypt


def test_create_acme_user_when_none_exists(clean_db, alb_route):
    instance_id = alb_route.instance_id
    operation = alb_route.create_renewal_operation()
    clean_db.add(alb_route)
    clean_db.commit()
    letsencrypt.alb_create_user(clean_db, operation.id)
    clean_db.expunge_all()

    alb_route = clean_db.query(DomainRoute).get(instance_id)

    assert alb_route.acme_user_id is not None
