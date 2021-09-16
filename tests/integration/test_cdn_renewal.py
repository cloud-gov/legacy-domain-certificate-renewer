from datetime import date
import json

import pytest

from renewer.cdn_models import (
    CdnOperation,
    CdnRoute,
    CdnAcmeUserV2,
    CdnCertificate,
    CdnChallenge,
)
from renewer.tasks import iam, letsencrypt, s3


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


def test_uploads_challenge_files(
    clean_db, cdn_route: CdnRoute, immediate_huey, s3_commercial
):

    instance_id = cdn_route.instance_id
    operation = cdn_route.create_renewal_operation()
    certificate = CdnCertificate()
    operation.certificate = certificate
    www_challenge = CdnChallenge()
    apex_challenge = CdnChallenge()

    www_challenge.certificate = certificate
    www_challenge.domain = "www.example.gov"
    www_challenge.validation_path = "/.well-known/acme-challenge/wwwchallengegoeshere"
    www_challenge.validation_contents = "thisisthewwwchallenge"

    apex_challenge.certificate = certificate
    apex_challenge.domain = "example.gov"
    apex_challenge.validation_path = "/.well-known/acme-challenge/apexchallengegoeshere"
    apex_challenge.validation_contents = "thisistheapexchallenge"

    clean_db.add_all([cdn_route, operation, certificate, www_challenge, apex_challenge])
    clean_db.commit()

    s3_commercial.expect_put_object(
        "fake-commercial-bucket",
        "/.well-known/acme-challenge/wwwchallengegoeshere",
        b"thisisthewwwchallenge",
    )
    s3_commercial.expect_put_object(
        "fake-commercial-bucket",
        "/.well-known/acme-challenge/apexchallengegoeshere",
        b"thisistheapexchallenge",
    )

    s3.upload_challenge_files(operation.id, cdn_route.route_type)


def test_answer_challenges(clean_db, cdn_route: CdnRoute, immediate_huey):
    # this tests that we call answer challenges correctly.
    # We have pebble set to not validate challenges, though, because
    # we don't have a meaningful way to validate them, so our test is
    # pretty much limited to happy-path testing and assuming that we got
    # the s3 stuff done correctly.
    instance_id = cdn_route.instance_id
    operation = cdn_route.create_renewal_operation()
    clean_db.add(cdn_route)
    clean_db.add(operation)
    clean_db.commit()
    operation_id = operation.id
    # setup
    letsencrypt.create_user(operation_id, cdn_route.route_type)
    letsencrypt.create_private_key_and_csr(operation_id, cdn_route.route_type)
    letsencrypt.initiate_challenges(operation_id, cdn_route.route_type)
    # note: we're skipping the file upload step here, because we don't need it
    # for the test

    # function we're actually testing
    letsencrypt.answer_challenges(operation_id, cdn_route.route_type)
    clean_db.expunge_all()

    operation = clean_db.query(CdnOperation).get(operation_id)
    certificate = operation.certificate
    assert all([c.answered for c in certificate.challenges])


def test_retrieve_certificate(clean_db, cdn_route: CdnRoute, immediate_huey):
    instance_id = cdn_route.instance_id
    operation = cdn_route.create_renewal_operation()
    clean_db.add(cdn_route)
    clean_db.add(operation)
    clean_db.commit()
    operation_id = operation.id
    # setup
    letsencrypt.create_user(operation_id, cdn_route.route_type)
    letsencrypt.create_private_key_and_csr(operation_id, cdn_route.route_type)
    letsencrypt.initiate_challenges(operation_id, cdn_route.route_type)
    letsencrypt.answer_challenges(operation_id, cdn_route.route_type)

    letsencrypt.retrieve_certificate(operation_id, cdn_route.route_type)
    clean_db.expunge_all()

    operation = clean_db.query(CdnOperation).get(operation_id)
    certificate = operation.certificate
    assert certificate.fullchain_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.leaf_pem.count("BEGIN CERTIFICATE") == 1
    assert certificate.expires is not None
    assert json.loads(certificate.order_json)["body"]["status"] == "valid"


def test_upload_cert_to_iam(
    clean_db, cdn_route: CdnRoute, immediate_huey, iam_commercial
):

    operation = cdn_route.create_renewal_operation()
    certificate = CdnCertificate()
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

    clean_db.add_all([operation, cdn_route, certificate])
    clean_db.commit()
    today = date.today().isoformat()
    operation_id = operation.id

    iam_commercial.expect_upload_server_certificate(
        name=f"{cdn_route.instance_id}-{today}-{certificate.id}",
        cert=certificate.leaf_pem,
        private_key=certificate.private_key_pem,
        chain=certificate.fullchain_pem,
        path="/cloudfront/test/",
    )

    clean_db.expunge_all()

    iam.upload_certificate(operation_id, cdn_route.route_type)
    operation = clean_db.query(CdnOperation).get(operation_id)
    certificate = operation.certificate
    assert certificate.iam_server_certificate_name
    assert certificate.iam_server_certificate_name.startswith(cdn_route.instance_id)
    assert certificate.iam_server_certificate_id
    assert certificate.iam_server_certificate_id.startswith("FAKE_CERT_ID")
    assert certificate.iam_server_certificate_arn
    assert certificate.iam_server_certificate_arn.startswith("arn:aws:iam")
