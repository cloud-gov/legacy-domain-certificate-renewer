from datetime import date, datetime, timedelta
import json

import pytest

from renewer.domain_models import (
    DomainAlbProxy,
    DomainOperation,
    DomainRoute,
    DomainAcmeUserV2,
    DomainCertificate,
    DomainChallenge,
)
from renewer.tasks import iam, letsencrypt, s3
from renewer.tasks import alb as alb_tasks


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


def test_retrieve_certificate(clean_db, alb_route: DomainRoute, immediate_huey):
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
    letsencrypt.answer_challenges(operation_id, alb_route.route_type)

    letsencrypt.retrieve_certificate(operation_id, alb_route.route_type)
    clean_db.expunge_all()

    operation = clean_db.query(DomainOperation).get(operation_id)
    certificate = operation.certificate
    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires is not None
    assert json.loads(certificate.order_json)["body"]["status"] == "valid"


def test_upload_cert_to_iam(
    clean_db, alb_route: DomainRoute, immediate_huey, iam_govcloud
):

    operation = alb_route.create_renewal_operation()
    certificate = DomainCertificate()
    operation.certificate = certificate

    certificate.fullchain_pem = """
    -----BEGIN CERTIFICATE-----
    look! a leaf cert!
    these are longer in reality though
    -----END CERTIFICATE-----
    -----BEGIN CERTIFICATE-----
    look! an intermediate cert!
    these are longer in reality though
    -----END CERTIFICATE-----
    -----BEGIN CERTIFICATE-----
    look! a CA cert!
    these are longer in reality though
    -----END CERTIFICATE-----
    """
    certificate.leaf_pem = """
    -----BEGIN CERTIFICATE-----
    look! a leaf cert!
    these are longer in reality though
    -----END CERTIFICATE-----
    """
    certificate.private_key_pem = """
    -----BEGIN PRIVATE KEY-----
    don't look! a private key!
    these are longer in reality though
    -----END PRIVATE KEY-----
    """

    clean_db.add_all([operation, alb_route, certificate])
    clean_db.commit()
    today = date.today().isoformat()
    operation_id = operation.id

    iam_govcloud.expect_upload_server_certificate(
        name=f"{alb_route.instance_id}-{today}-{certificate.id}",
        cert=certificate.leaf_pem,
        private_key=certificate.private_key_pem,
        chain=certificate.fullchain_pem,
        path="/alb/test/",
    )

    clean_db.expunge_all()

    iam.upload_certificate(operation_id, alb_route.route_type)
    operation = clean_db.query(DomainOperation).get(operation_id)
    certificate = operation.certificate
    assert certificate.iam_server_certificate_name
    assert certificate.iam_server_certificate_name.startswith(alb_route.instance_id)
    assert certificate.iam_server_certificate_id
    assert certificate.iam_server_certificate_id.startswith("FAKE_CERT_ID")
    assert certificate.iam_server_certificate_arn
    assert certificate.iam_server_certificate_arn.startswith("arn:aws:iam")


def test_associate_cert(clean_db, alb_route: DomainRoute, immediate_huey, alb):
    operation = alb_route.create_renewal_operation()
    certificate = DomainCertificate()
    operation.certificate = certificate

    today = date.today().isoformat()
    certificate.iam_server_certificate_name = (
        f"{alb_route.instance_id}-{today}-{certificate.id}"
    )
    certificate.iam_server_certificate_id = f"FAKE_CERT_ID-{alb_route.instance_id}"
    certificate.iam_server_certificate_arn = (
        f"arn:aws:iam:1234:/alb/test/{certificate.iam_server_certificate_name}"
    )

    clean_db.add_all([operation, certificate])
    clean_db.commit()

    alb.expect_add_certificate_to_listener(
        "arn:aws:listener:1234", certificate.iam_server_certificate_arn
    )

    alb_tasks.associate_certificate(operation.id)

    clean_db.expunge_all()


def test_remove_old_cert(clean_db, alb_route: DomainRoute, immediate_huey, alb):
    operation = alb_route.create_renewal_operation()
    new_certificate = DomainCertificate()
    new_certificate.expires = datetime.now() + timedelta(days=90)
    old_certificate = DomainCertificate()
    old_certificate.route = alb_route
    old_certificate.expires = datetime.now() + timedelta(days=30)
    operation.certificate = new_certificate

    today = date.today().isoformat()
    old_certificate.iam_server_certificate_name = (
        f"{alb_route.instance_id}-{today}-{old_certificate.id}"
    )
    old_certificate.iam_server_certificate_id = (
        f"FAKE_CERT_ID-{alb_route.instance_id}-OLD"
    )
    old_certificate.iam_server_certificate_arn = (
        f"arn:aws:iam:1234:/alb/test/{old_certificate.iam_server_certificate_name}"
    )

    new_certificate.iam_server_certificate_name = (
        f"{alb_route.instance_id}-{today}-{new_certificate.id}"
    )
    new_certificate.iam_server_certificate_id = f"FAKE_CERT_ID-{alb_route.instance_id}"
    new_certificate.iam_server_certificate_arn = (
        f"arn:aws:iam:1234:/alb/test/{new_certificate.iam_server_certificate_name}"
    )

    clean_db.add_all([operation, new_certificate, old_certificate, alb_route])
    clean_db.commit()

    alb.expect_remove_certificate_from_listener(
        "arn:aws:listener:1234", old_certificate.iam_server_certificate_arn
    )

    alb_tasks.remove_old_certificate(operation.id)
    # run it twice, to make sure a retry won't nuke the good cert
    alb_tasks.remove_old_certificate(operation.id)

    clean_db.expunge_all()
