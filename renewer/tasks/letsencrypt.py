from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Type, Union, Tuple

import josepy
from OpenSSL import crypto
from acme import challenges, client, crypto_util, messages, errors
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from renewer.cdn_models import (
    CdnOperation,
    CdnAcmeUserV2,
    CdnCertificate,
    CdnRoute,
    CdnChallenge,
)
from renewer.domain_models import (
    DomainOperation,
    DomainAcmeUserV2,
    DomainCertificate,
    DomainRoute,
    DomainChallenge,
)
from renewer.extensions import config
from renewer.acme_client import AcmeClient
from renewer import huey
from renewer.types import TOperation, TCertificate, TChallenge, TUser, TRoute
from renewer.route_type import RouteType

logger = logging.getLogger(__name__)


class DNSChallengeNotFound(RuntimeError):
    def __init__(self, domain, obj):
        super().__init__(f"Cannot find DNS challenges for {domain} in {obj}")


class ChallengeNotFound(RuntimeError):
    def __init__(self, domain, obj):
        super().__init__(f"Cannot find any challenges for {domain} in {obj}")


def http_challenge(order, domain):
    """Extract authorization resource from within order resource."""

    # authorization.body.challenges is a set of ChallengeBody
    # objects.
    challenges_for_domain = [
        authorization.body.challenges
        for authorization in order.authorizations
        if authorization.body.identifier.value == domain
    ][0]

    if not challenges_for_domain:
        raise ChallengeNotFound(domain, order.authorizations)

    for challenge in challenges_for_domain:
        if isinstance(challenge.chall, challenges.HTTP01):
            return challenge

    raise DNSChallengeNotFound(domain, challenges_for_domain)


@huey.retriable_task
def create_user(session, operation_id: int, route_type: RouteType):
    Operation: TOperation
    AcmeUserV2: TUser
    if route_type is RouteType.ALB:
        Operation = DomainOperation
        AcmeUserV2 = DomainAcmeUserV2
    elif route_type is RouteType.CDN:
        Operation = CdnOperation
        AcmeUserV2 = CdnAcmeUserV2

    operation = session.query(Operation).get(operation_id)
    route = operation.route
    acme_user = AcmeUserV2()
    if route.acme_user_id is not None:
        return

    route.acme_user = acme_user

    key = josepy.JWKRSA(
        key=rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
    )
    private_key_pem_in_binary = key.key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    acme_user.private_key_pem = private_key_pem_in_binary.decode("utf-8")

    net = client.ClientNetwork(key, user_agent="cloud.gov legacy domain renewer")
    directory = messages.Directory.from_json(net.get(config.ACME_DIRECTORY).json())
    client_acme = AcmeClient(directory, net=net)

    acme_user.email = config.LETS_ENCRYPT_REGISTRATION_EMAIL
    registration = client_acme.new_account(
        messages.NewRegistration.from_data(
            email=acme_user.email, terms_of_service_agreed=True
        )
    )
    acme_user.registration_json = registration.json_dumps()
    acme_user.uri = registration.uri
    session.add(operation)
    session.add(route)
    session.add(acme_user)
    session.commit()


@huey.retriable_task
def create_private_key_and_csr(session, operation_id: int, instance_type: RouteType):
    Operation: TOperation
    Certificate: TCertificate
    if instance_type is RouteType.ALB:
        Operation = DomainOperation
        Certificate = DomainCertificate
    elif instance_type is RouteType.CDN:
        Operation = CdnOperation
        Certificate = CdnCertificate

    operation = session.query(Operation).get(operation_id)
    if operation.certificate is None:
        # note: we're not linking the cert to the route yet. This is intentional
        # we're going to link them together once we actually have a certificate
        # this is to prevent messing with the migrator, until/unless we update it
        # to understand renewals
        operation.certificate = Certificate()

    certificate = operation.certificate
    route = operation.route

    # Create private key.
    private_key = crypto.PKey()
    private_key.generate_key(crypto.TYPE_RSA, 2048)

    # Get the PEM
    private_key_pem_in_binary = crypto.dump_privatekey(crypto.FILETYPE_PEM, private_key)

    # Get the CSR for the domains
    csr_pem_in_binary = crypto_util.make_csr(
        private_key_pem_in_binary, route.domain_external_list()
    )

    # Store them as text for later
    certificate.private_key_pem = private_key_pem_in_binary.decode("utf-8")
    certificate.csr_pem = csr_pem_in_binary.decode("utf-8")

    session.add(certificate)
    session.commit()


@huey.retriable_task
def initiate_challenges(session, operation_id: int, instance_type: RouteType):
    Operation: TOperation
    Challenge: TChallenge

    if instance_type is RouteType.ALB:
        Operation = DomainOperation
        Challenge = DomainChallenge
    elif instance_type is RouteType.CDN:
        Operation = CdnOperation
        Challenge = CdnChallenge

    operation = session.query(Operation).get(operation_id)
    certificate = operation.certificate
    route = operation.route
    acme_user = route.acme_user

    if certificate.order_json is not None:
        return

    account_key = serialization.load_pem_private_key(
        acme_user.private_key_pem.encode(), password=None, backend=default_backend()
    )
    wrapped_account_key = josepy.JWKRSA(key=account_key)

    registration = json.loads(acme_user.registration_json)
    net = client.ClientNetwork(
        wrapped_account_key,
        user_agent="cloud.gov legacy domain renewer",
        account=registration,
    )
    directory = messages.Directory.from_json(net.get(config.ACME_DIRECTORY).json())
    client_acme = AcmeClient(directory, net=net)

    order = client_acme.new_order(certificate.csr_pem.encode())
    order_json = json.dumps(order.to_json())
    certificate.order_json = json.dumps(order.to_json())

    for domain in route.domain_external_list():
        challenge_body = http_challenge(order, domain)
        (
            challenge_response,
            challenge_validation_contents,
        ) = challenge_body.response_and_validation(wrapped_account_key)

        challenge = Challenge()
        challenge.body_json = challenge_body.json_dumps()

        challenge.domain = domain
        challenge.certificate = certificate
        challenge.validation_path = challenge_body.path
        challenge.validation_contents = challenge_validation_contents
        session.add(challenge)

    session.commit()


@huey.retriable_task
def answer_challenges(session, operation_id: int, instance_type: RouteType):
    Operation: TOperation
    Challenge: TChallenge

    if instance_type is RouteType.ALB:
        Operation = DomainOperation
        Challenge = DomainChallenge
    elif instance_type is RouteType.CDN:
        Operation = CdnOperation
        Challenge = CdnChallenge

    operation = session.query(Operation).get(operation_id)
    route = operation.route
    acme_user = route.acme_user
    certificate = operation.certificate
    challenges = certificate.challenges.all()
    unanswered = [c for c in challenges if not c.answered]

    if not unanswered:
        return

    account_key = serialization.load_pem_private_key(
        acme_user.private_key_pem.encode(), password=None, backend=default_backend()
    )
    wrapped_account_key = josepy.JWKRSA(key=account_key)

    registration = json.loads(acme_user.registration_json)
    net = client.ClientNetwork(
        wrapped_account_key,
        user_agent="cloud.gov legacy domain renewer",
        account=registration,
    )
    directory = messages.Directory.from_json(net.get(config.ACME_DIRECTORY).json())
    client_acme = AcmeClient(directory, net=net)

    for challenge in unanswered:
        if json.loads(challenge.body_json)["status"] == "valid":
            # this covers an edge case where we try to get the sane certificate
            # twice in a short period.
            # it arguably makes more sense to do when we get the challenges
            # but doing so makes testing worlds harder
            challenge.answered = True
            session.add(challenge)
            session.commit()
            continue
        challenge_body = messages.ChallengeBody.from_json(
            json.loads(challenge.body_json)
        )
        challenge_response = challenge_body.response(wrapped_account_key)
        # Let the CA server know that we are ready for the challenge.
        response = client_acme.answer_challenge(challenge_body, challenge_response)
        print(response)
        if response.body.error is not None:
            # log the error for now. We haven't reproduced this locally, so we can't act on it yet
            # but it would be interesting in the real world
            logger.error(
                f"challenge for instance {route.id} errored. Error: {response.body.error}"
            )
        challenge.answered = True
        session.add(challenge)
    session.commit()


@huey.retriable_task
def retrieve_certificate(session, operation_id: int, instance_type: RouteType):
    def cert_from_fullchain(fullchain_pem: str) -> Tuple[str, str]:
        """extract cert_pem from fullchain_pem

        Reference https://github.com/certbot/certbot/blob/b42e24178aaa3f1ad1323acb6a3a9c63e547893f/certbot/certbot/crypto_util.py#L482-L518
        """
        cert_pem_regex = re.compile(
            b"-----BEGIN CERTIFICATE-----\r?.+?\r?-----END CERTIFICATE-----\r?",
            re.DOTALL,  # DOTALL (/s) because the base64text may include newlines
        )

        certs = cert_pem_regex.findall(fullchain_pem.encode())
        if len(certs) < 2:
            raise RuntimeError(
                "failed to extract cert from fullchain: fewer than 2 certificates in chain"
            )

        certs_normalized = [
            crypto.dump_certificate(
                crypto.FILETYPE_PEM, crypto.load_certificate(crypto.FILETYPE_PEM, cert)
            ).decode()
            for cert in certs
        ]

        return certs_normalized[0], "".join(certs_normalized[1:])

    Operation: TOperation
    Challenge: TChallenge

    if instance_type is RouteType.ALB:
        Operation = DomainOperation
        Challenge = DomainChallenge
    elif instance_type is RouteType.CDN:
        Operation = CdnOperation
        Challenge = CdnChallenge

    operation = session.query(Operation).get(operation_id)
    route = operation.route
    acme_user = route.acme_user
    certificate = operation.certificate

    if certificate.leaf_pem is not None:
        return

    account_key = serialization.load_pem_private_key(
        acme_user.private_key_pem.encode(), password=None, backend=default_backend()
    )
    wrapped_account_key = josepy.JWKRSA(key=account_key)

    registration = json.loads(acme_user.registration_json)
    net = client.ClientNetwork(
        wrapped_account_key,
        user_agent="cloud.gov external domain broker",
        account=registration,
    )
    directory = messages.Directory.from_json(net.get(config.ACME_DIRECTORY).json())
    client_acme = AcmeClient(directory, net=net)

    order_json = json.loads(certificate.order_json)
    # The csr_pem in the JSON is a binary string, but finalize_order() expects
    # utf-8?  So we set it here from our saved copy.
    order_json["csr_pem"] = certificate.csr_pem
    order = messages.OrderResource.from_json(order_json)

    deadline = datetime.now() + timedelta(seconds=config.ACME_POLL_TIMEOUT_IN_SECONDS)
    try:
        finalized_order = client_acme.poll_and_finalize(orderr=order, deadline=deadline)
    except messages.Error as e:
        # this means we're trying to fulfill an order that's already fulfilled
        if """Order's status ("valid")""" in e.detail:
            # Check if we got a certificate already. Do we have a cert, and does its expiration look good?
            next_month = datetime.now() + timedelta(days=31)
            next_month = next_month.replace(tzinfo=timezone.utc)
            if certificate.expires is not None and certificate.expires > next_month:
                return
            else:
                finalized_order = client_acme.get_cert_for_finalized_order(
                    order, deadline
                )
        else:
            logger.error(
                f"failed to retrieve certificate for {route.domain_names} with code {e.code}, {e.description}, {e.detail}"
            )
            raise e
    except errors.ValidationError as e:
        logger.error(
            f"failed to retrieve certificate for {route.domain_names} with errors {e.failed_authzrs}"
        )
        # if we fail validation, nuke the cert record and its challenges.
        # this way, when we retry from the beginning, we won't try to reuse them
        # the bad new is that we'll still retry this task a bunch of times before the pipeline fails
        operation.certificate = None
        session.add(operation)
        session.commit()
        raise e

    certificate.leaf_pem, certificate.fullchain_pem = cert_from_fullchain(
        finalized_order.fullchain_pem
    )
    x509 = crypto.load_certificate(crypto.FILETYPE_PEM, certificate.leaf_pem.encode())
    not_after_bytes = x509.get_notAfter()
    if not_after_bytes is not None:
        # None check should be an extreme edge case, but it makes mypy happy :shrug:
        not_after = not_after_bytes.decode("utf-8")
        certificate.expires = datetime.strptime(not_after, "%Y%m%d%H%M%Sz")
    else:
        raise RuntimeError("failed to get not_after")
    certificate.order_json = json.dumps(finalized_order.to_json())
    session.add(route)
    session.add(certificate)
    session.commit()
