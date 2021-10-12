from datetime import date, datetime, timedelta
import json
import uuid

import pytest

from renewer.models.domain import (
    DomainAlbProxy,
    DomainOperation,
    DomainRoute,
    DomainAcmeUserV2,
    DomainCertificate,
    DomainChallenge,
)
from renewer.tasks import iam, letsencrypt, s3
from renewer.tasks import alb as alb_tasks
from renewer.tasks import renewals

from tests.lib.fake_iam import FakeIAM
from tests.lib.alb_fixtures import make_cert, make_route


def make_route_for_user(user, state: str = "provisioned"):
    route = DomainRoute()
    route.instance_id = uuid.uuid4()
    route.acme_user = user
    route.email = "me@example.com"
    route.state = state
    return route


def test_create_acme_user_associates_exisiting_user(
    clean_db, alb_route: DomainRoute, immediate_huey
):
    instance_id = alb_route.instance_id
    operation = alb_route.create_renewal_operation()
    user = DomainAcmeUserV2()
    user.email = "me@example.com"
    user.uri = "uri"
    clean_db.add(alb_route)
    clean_db.add(operation)
    clean_db.add(user)
    clean_db.commit()
    letsencrypt.create_user(operation.id, alb_route.route_type)

    alb_route = clean_db.query(DomainRoute).get(instance_id)

    assert alb_route.acme_user_id == user.id


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
        ".well-known/acme-challenge/wwwchallengegoeshere",
        b"thisisthewwwchallenge",
    )
    s3_govcloud.expect_put_object(
        "fake-govcloud-bucket",
        ".well-known/acme-challenge/apexchallengegoeshere",
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
    today = date.today()
    now = datetime.now()
    certificate = make_cert(clean_db, alb_route, now + timedelta(days=90), today, False)
    operation.certificate = certificate

    clean_db.add_all([operation, certificate])
    clean_db.commit()

    alb.expect_add_certificate_to_listener(
        "arn:aws:listener:1234", certificate.iam_server_certificate_arn
    )

    alb_tasks.associate_certificate(operation.id, alb_route.route_type)

    clean_db.expunge_all()


def test_remove_old_cert(clean_db, alb_route: DomainRoute, immediate_huey, alb):
    operation = alb_route.create_renewal_operation()
    now = datetime.now()
    today = date.today()
    new_certificate = make_cert(
        clean_db, alb_route, now + timedelta(days=90), today, False
    )
    old_certificate = make_cert(
        clean_db, alb_route, now + timedelta(days=30), today - timedelta(days=60)
    )
    old_certificate.route = alb_route
    operation.certificate = new_certificate

    clean_db.add_all([operation, new_certificate, old_certificate, alb_route])
    clean_db.commit()

    alb.expect_remove_certificate_from_listener(
        "arn:aws:listener:1234", old_certificate.iam_server_certificate_arn
    )

    alb_tasks.remove_old_certificate(operation.id, alb_route.route_type)
    # run it twice, to make sure a retry won't nuke the good cert
    alb_tasks.remove_old_certificate(operation.id, alb_route.route_type)

    clean_db.expunge_all()


def test_remove_old_cert_without_arn(
    clean_db, alb_route: DomainRoute, immediate_huey, alb
):
    operation = alb_route.create_renewal_operation()
    now = datetime.now()
    today = date.today()
    new_certificate = make_cert(
        clean_db, alb_route, now + timedelta(days=90), today, False
    )
    old_certificate = make_cert(
        clean_db, alb_route, now + timedelta(days=30), today - timedelta(days=60)
    )
    old_certificate.route = alb_route
    old_certificate.iam_server_certificate_arn = None
    old_certificate.iam_server_certificate_name = None
    operation.certificate = new_certificate

    clean_db.add_all([operation, new_certificate, old_certificate, alb_route])
    clean_db.commit()

    alb_tasks.remove_old_certificate(operation.id, alb_route.route_type)

    clean_db.expunge_all()


def test_delete_old_certificate_without_name(
    clean_db, alb_route: DomainRoute, iam_govcloud: FakeIAM, immediate_huey
):
    operation = alb_route.create_renewal_operation()
    now = datetime.now()
    today = date.today()
    new_certificate = make_cert(clean_db, alb_route, now + timedelta(days=90), today)
    old_certificate = make_cert(
        clean_db, alb_route, now + timedelta(days=30), today - timedelta(days=60)
    )
    old_certificate.iam_server_certificate_arn = None
    old_certificate.iam_server_certificate_name = None
    operation.certificate = new_certificate

    clean_db.add_all([operation, new_certificate, old_certificate, alb_route])
    clean_db.commit()

    iam.delete_old_certificate(operation.id, alb_route.route_type)


def test_delete_old_certificate(
    clean_db, alb_route: DomainRoute, iam_govcloud: FakeIAM, immediate_huey
):
    operation = alb_route.create_renewal_operation()
    now = datetime.now()
    today = date.today()
    new_certificate = make_cert(clean_db, alb_route, now + timedelta(days=90), today)
    old_certificate = make_cert(
        clean_db, alb_route, now + timedelta(days=30), today - timedelta(days=60)
    )
    operation.certificate = new_certificate

    clean_db.add_all([operation, new_certificate, old_certificate, alb_route])
    clean_db.commit()

    iam_govcloud.expects_delete_server_certificate(
        f"{alb_route.instance_id}-{(today - timedelta(days=60)).isoformat()}-{old_certificate.id}"
    )

    iam.delete_old_certificate(operation.id, alb_route.route_type)


def test_delete_nonexistent_old_certificate(
    clean_db, alb_route: DomainRoute, iam_govcloud: FakeIAM, immediate_huey
):
    operation = alb_route.create_renewal_operation()
    now = datetime.now()
    today = date.today()
    new_certificate = make_cert(clean_db, alb_route, now + timedelta(days=90), today)
    old_certificate = make_cert(
        clean_db, alb_route, now + timedelta(days=30), today - timedelta(days=60)
    )
    operation.certificate = new_certificate

    iam_govcloud.expects_delete_server_certificate_returning_no_such_entity(
        f"{alb_route.instance_id}-{(today - timedelta(days=60)).isoformat()}-{old_certificate.id}"
    )

    iam.delete_old_certificate(operation.id, alb_route.route_type)


def test_queues_all_renewals(clean_db, clean_huey, proxy, tasks):
    now = datetime.now()
    today = date.today()
    needs_renewal = make_route(clean_db, proxy, "needs-renewal", ["example.com"])
    needs_renewal_cert = make_cert(
        clean_db, needs_renewal, now + timedelta(days=30), today - timedelta(days=60)
    )

    doesnt_need_renewal = make_route(
        clean_db, proxy, "doesnt-need-renewal", ["example.com"]
    )
    doesnt_need_renewal_cert = make_cert(
        clean_db,
        doesnt_need_renewal,
        now + timedelta(days=32),
        today - timedelta(days=60),
    )

    inactive = make_route(clean_db, proxy, "inactive", ["example.com"], "deprovisioned")
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
    needs_renewal = clean_db.query(DomainRoute).get(needs_renewal.instance_id)
    ops = needs_renewal.operations
    inactive = clean_db.query(DomainRoute).get(inactive.instance_id)
    doesnt_need_renewal = clean_db.query(DomainRoute).get(
        doesnt_need_renewal.instance_id
    )
    task = clean_huey.dequeue()

    assert len(doesnt_need_renewal.operations.all()) == 0
    assert len(inactive.operations.all()) == 0
    assert task.args[0] == ops[0].id
