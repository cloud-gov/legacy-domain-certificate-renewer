import pytest

from renewer.cdn_models import CdnOperation, CdnRoute, CdnAcmeUserV2
from renewer.tasks import letsencrypt


def test_create_acme_user_when_none_exists(
    clean_db, cdn_route: CdnRoute, immediate_huey
):
    instance_id = cdn_route.id
    operation = cdn_route.create_renewal_operation()
    clean_db.add(cdn_route)
    clean_db.add(operation)
    clean_db.commit()
    letsencrypt.create_user(operation.id, cdn_route.route_type)
    clean_db.expunge_all()

    cdn_route = clean_db.query(CdnRoute).get(instance_id)

    assert cdn_route.acme_user_id is not None


def test_create_private_key(clean_db, cdn_route: CdnRoute, immediate_huey):
    instance_id = cdn_route.instance_id
    operation = cdn_route.create_renewal_operation()
    clean_db.add(cdn_route)
    clean_db.add(operation)
    clean_db.commit()
    operation_id = operation.id
    letsencrypt.create_user(operation.id, cdn_route.route_type)

    letsencrypt.create_private_key_and_csr(operation.id, cdn_route.route_type)
    clean_db.expunge_all()
    operation = clean_db.query(CdnOperation).get(operation_id)
    certificate = operation.certificate
    assert certificate.private_key_pem is not None
    assert certificate.csr_pem is not None
    assert "BEGIN PRIVATE KEY" in certificate.private_key_pem
    assert "BEGIN CERTIFICATE REQUEST" in certificate.csr_pem


def test_gets_new_challenges(clean_db, cdn_route: CdnRoute, immediate_huey):

    instance_id = cdn_route.instance_id
    operation = cdn_route.create_renewal_operation()
    clean_db.add(cdn_route)
    clean_db.add(operation)
    clean_db.commit()
    operation_id = operation.id
    letsencrypt.create_user(operation.id, cdn_route.route_type)
    letsencrypt.create_private_key_and_csr(operation.id, cdn_route.route_type)

    letsencrypt.initiate_challenges(operation.id, cdn_route.route_type)
    clean_db.expunge_all()
    operation = clean_db.query(CdnOperation).get(operation_id)
    certificate = operation.certificate
    assert certificate.challenges.count() == 2
    assert certificate.order_json is not None
    for challenge in certificate.challenges:
        assert challenge.validation_path.startswith("/.well-known")