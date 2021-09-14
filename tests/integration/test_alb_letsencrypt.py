import pytest

from renewer.domain_models import (
    DomainAlbProxy,
    DomainOperation,
    DomainRoute,
    DomainAcmeUserV2,
)
from renewer.tasks import letsencrypt


def test_create_acme_user_when_none_exists(
    clean_db, alb_route: DomainRoute, immediate_huey
):
    instance_id = alb_route.instance_id
    operation = alb_route.create_renewal_operation()
    clean_db.add(alb_route)
    clean_db.add(operation)
    clean_db.commit()
    letsencrypt.create_user(operation.id, alb_route.route_type)
    clean_db.expunge_all()

    alb_route = clean_db.query(DomainRoute).get(instance_id)

    assert alb_route.acme_user_id is not None


def test_create_private_key(clean_db, alb_route: DomainRoute, immediate_huey):
    instance_id = alb_route.instance_id
    operation = alb_route.create_renewal_operation()
    clean_db.add(alb_route)
    clean_db.add(operation)
    clean_db.commit()
    operation_id = operation.id
    letsencrypt.create_user(operation.id, alb_route.route_type)

    letsencrypt.create_private_key_and_csr(operation.id, alb_route.route_type)
    clean_db.expunge_all()
    operation = clean_db.query(DomainOperation).get(operation_id)
    certificate = operation.certificate
    assert certificate.private_key_pem is not None
    assert certificate.csr_pem is not None
    assert "BEGIN PRIVATE KEY" in certificate.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in certificate.csr_pem


def test_gets_new_challenges(clean_db, alb_route: DomainRoute, immediate_huey):

    instance_id = alb_route.instance_id
    operation = alb_route.create_renewal_operation()
    clean_db.add(alb_route)
    clean_db.add(operation)
    clean_db.commit()
    operation_id = operation.id
    letsencrypt.create_user(operation.id, alb_route.route_type)
    letsencrypt.create_private_key_and_csr(operation.id, alb_route.route_type)

    letsencrypt.initiate_challenges(operation.id, alb_route.route_type)
    clean_db.expunge_all()
    operation = clean_db.query(DomainOperation).get(operation_id)
    certificate = operation.certificate
    assert certificate.challenges.count() == 2
    assert certificate.order_json is not None
    for challenge in certificate.challenges:
        assert challenge.validation_path.startswith("/.well-known")
