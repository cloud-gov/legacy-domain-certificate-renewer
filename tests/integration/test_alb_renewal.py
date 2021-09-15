import pytest

from renewer.domain_models import (
    DomainAlbProxy,
    DomainOperation,
    DomainRoute,
    DomainAcmeUserV2,
    DomainCertificate,
    DomainChallenge,
)
from renewer.tasks import letsencrypt, s3


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


def test_uploads_challenge_files(
    clean_db, alb_route: DomainRoute, immediate_huey, s3_govcloud
):

    instance_id = alb_route.instance_id
    operation = alb_route.create_renewal_operation()
    certificate = DomainCertificate()
    operation.certificate = certificate
    www_challenge = DomainChallenge()
    apex_challenge = DomainChallenge()

    www_challenge.certificate = certificate
    www_challenge.domain = "www.example.gov"
    www_challenge.validation_path = "/.well-known/acme-challenge/wwwchallengegoeshere"
    www_challenge.validation_contents = "thisisthewwwchallenge"

    apex_challenge.certificate = certificate
    apex_challenge.domain = "example.gov"
    apex_challenge.validation_path = "/.well-known/acme-challenge/apexchallengegoeshere"
    apex_challenge.validation_contents = "thisistheapexchallenge"

    clean_db.add_all([alb_route, operation, certificate, www_challenge, apex_challenge])
    clean_db.commit()

    s3_govcloud.expect_put_object(
        "fake-govcloud-bucket",
        "/.well-known/acme-challenge/wwwchallengegoeshere",
        b"thisisthewwwchallenge",
    )
    s3_govcloud.expect_put_object(
        "fake-govcloud-bucket",
        "/.well-known/acme-challenge/apexchallengegoeshere",
        b"thisistheapexchallenge",
    )

    s3.upload_challenge_files(operation.id, alb_route.route_type)


def test_answer_challenges(clean_db, alb_route: DomainRoute, immediate_huey):
    # this tests that we call answer challenges correctly.
    # We have pebble set to not validate challenges, though, because 
    # we don't have a meaningful way to validate them, so our test is 
    # pretty much limited to happy-path testing and assuming that we got 
    # the s3 stuff done correctly. 
    instance_id = alb_route.instance_id
    operation = alb_route.create_renewal_operation()
    clean_db.add(alb_route)
    clean_db.add(operation)
    clean_db.commit()
    operation_id = operation.id
    # setup
    letsencrypt.create_user(operation_id, alb_route.route_type)
    letsencrypt.create_private_key_and_csr(operation_id, alb_route.route_type)
    letsencrypt.initiate_challenges(operation_id, alb_route.route_type)
    # note: we're skipping the file upload step here, because we don't need it
    # for the test

    # function we're actually testing
    letsencrypt.answer_challenges(operation_id, alb_route.route_type)
    clean_db.expunge_all()
    
    operation = clean_db.query(DomainOperation).get(operation_id)
    certificate = operation.certificate
    assert all([c.answered for c in certificate.challenges])
