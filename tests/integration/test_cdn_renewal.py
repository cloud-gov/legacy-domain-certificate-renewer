from datetime import date, datetime, timedelta
import json

import pytest

from renewer.models.cdn import (
    CdnOperation,
    CdnRoute,
    CdnAcmeUserV2,
    CdnCertificate,
    CdnChallenge,
)
from renewer.tasks import cdn, iam, letsencrypt, s3, renewals

from tests.lib.fake_iam import FakeIAM
from tests.lib.cdn_fixtures import make_route, make_cert


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
        ".well-known/acme-challenge/wwwchallengegoeshere",
        b"thisisthewwwchallenge",
    )
    s3_commercial.expect_put_object(
        "fake-commercial-bucket",
        ".well-known/acme-challenge/apexchallengegoeshere",
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


def test_associate_cert(clean_db, cdn_route: CdnRoute, immediate_huey, cloudfront):
    operation = cdn_route.create_renewal_operation()
    certificate = CdnCertificate()
    operation.certificate = certificate

    today = date.today().isoformat()
    certificate.iam_server_certificate_name = (
        f"{cdn_route.instance_id}-{today}-{certificate.id}"
    )
    certificate.iam_server_certificate_id = f"FAKE_CERT_ID-{cdn_route.instance_id}"
    certificate.iam_server_certificate_arn = (
        f"arn:aws:iam:1234:/cloudfront/test/{certificate.iam_server_certificate_name}"
    )

    clean_db.add_all([operation, certificate])
    clean_db.commit()

    cloudfront.expect_get_distribution_config(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id="certificate_id",
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="fakedistid",
        bucket_prefix="4321/",
    )
    cloudfront.expect_update_distribution(
        caller_reference="4321",
        domains=["example.com", "foo.com"],
        certificate_id=f"FAKE_CERT_ID-{cdn_route.instance_id}",
        origin_hostname="origin_hostname",
        origin_path="origin_path",
        distribution_id="fakedistid",
        distribution_hostname="fake1234.cloudfront.net",
        bucket_prefix="4321/",
    )

    cdn.associate_certificate(operation.id)

    clean_db.expunge_all()


def test_waits_for_update_to_finish_updating(
    clean_db, cdn_route: CdnRoute, immediate_huey, cloudfront
):
    operation = cdn_route.create_renewal_operation()

    clean_db.add_all([operation])
    clean_db.commit()

    cloudfront.expect_get_distribution(
        caller_reference=cdn_route.instance_id,
        domains=cdn_route.domain_external_list(),
        certificate_id="unimportant_for_this_test",
        origin_hostname=cdn_route.origin,
        distribution_id=cdn_route.dist_id,
        status="InProgress",
    )
    cloudfront.expect_get_distribution(
        caller_reference=cdn_route.instance_id,
        domains=cdn_route.domain_external_list(),
        certificate_id="unimportant_for_this_test",
        origin_hostname=cdn_route.origin,
        distribution_id=cdn_route.dist_id,
        status="Deployed",
    )

    # what we're really testing.
    # this test just makes sure we call get_distribution until it's Deployed
    # and that nothing blows up
    cdn.wait_for_distribution(operation.id)


def test_delete_old_certificate(
    clean_db, cdn_route: CdnRoute, iam_commercial: FakeIAM, immediate_huey
):
    operation = cdn_route.create_renewal_operation()
    now = datetime.now()
    today = date.today()
    new_certificate = make_cert(clean_db, cdn_route, now + timedelta(days=90), today)
    old_certificate = make_cert(
        clean_db, cdn_route, now + timedelta(days=30), today - timedelta(days=60)
    )
    operation.certificate = new_certificate

    clean_db.add_all([operation, new_certificate, old_certificate, cdn_route])
    clean_db.commit()

    iam_commercial.expects_delete_server_certificate(
        f"{cdn_route.instance_id}-{today - timedelta(days=60)}-{old_certificate.id}"
    )

    iam.delete_old_certificate(operation.id, cdn_route.route_type)


def test_delete_nonexistent_old_certificate(
    clean_db, cdn_route: CdnRoute, iam_commercial: FakeIAM, immediate_huey
):
    operation = cdn_route.create_renewal_operation()
    now = datetime.now()
    today = date.today()
    new_certificate = make_cert(clean_db, cdn_route, now + timedelta(days=90), today)
    old_certificate = make_cert(
        clean_db, cdn_route, now + timedelta(days=30), today - timedelta(days=60)
    )
    operation.certificate = new_certificate

    clean_db.add_all([operation, new_certificate, old_certificate, cdn_route])
    clean_db.commit()

    iam_commercial.expects_delete_server_certificate_returning_no_such_entity(
        f"{cdn_route.instance_id}-{today - timedelta(days=60)}-{old_certificate.id}"
    )

    iam.delete_old_certificate(operation.id, cdn_route.route_type)


def test_queues_all_renewals(clean_db, clean_huey, tasks):
    now = datetime.now()
    today = date.today()
    needs_renewal = make_route(clean_db, "needs-renewal", "example.com")
    needs_renewal_cert = make_cert(
        clean_db, needs_renewal, now + timedelta(days=1), today - timedelta(days=60)
    )

    doesnt_need_renewal = make_route(clean_db, "doesnt-need-renewal", "example.com")
    doesnt_need_renewal_cert = make_cert(
        clean_db,
        doesnt_need_renewal,
        now + timedelta(days=32),
        today - timedelta(days=60),
    )

    inactive = make_route(clean_db, "inactive", "example.com", "deprovisioned")
    inactive_cert = make_cert(
        clean_db, inactive, now + timedelta(days=30), today - timedelta(days=60)
    )
    clean_db.add_all(
        [
            needs_renewal,
            needs_renewal_cert,
            doesnt_need_renewal,
            doesnt_need_renewal_cert,
            inactive,
            inactive_cert,
        ]
    )
    clean_db.commit()

    renewals.renew_all_certs()
    tasks.run_queued_tasks_and_enqueue_dependents()
    needs_renewal = clean_db.query(CdnRoute).get(needs_renewal.id)
    ops = needs_renewal.operations
    inactive = clean_db.query(CdnRoute).get(inactive.id)
    doesnt_need_renewal = clean_db.query(CdnRoute).get(doesnt_need_renewal.id)
    task = clean_huey.dequeue()

    assert len(doesnt_need_renewal.operations.all()) == 0
    assert len(inactive.operations.all()) == 0
    assert task.args[0] == ops[0].id
