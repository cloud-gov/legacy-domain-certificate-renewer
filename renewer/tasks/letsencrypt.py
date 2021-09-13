import json
from typing import Type, Union

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
from renewer.route_type import RouteType

TOperation = Type[Union[DomainOperation, CdnOperation]]
TUser = Type[Union[DomainAcmeUserV2, CdnAcmeUserV2]]
TRoute = Type[Union[DomainRoute, CdnRoute]]
TCertificate = Type[Union[DomainCertificate, CdnCertificate]]
TChallenge = Type[Union[DomainChallenge, CdnChallenge]]


class DNSChallengeNotFound(RuntimeError):
    def __init__(self, domain, obj):
        super().__init__(f"Cannot find DNS challenges for {domain} in {obj}")


class ChallengeNotFound(RuntimeError):
    def __init__(self, domain, obj):
        super().__init__(f"Cannot find any challenges for {domain} in {obj}")


def dns_challenge(order, domain):
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
        if isinstance(challenge.chall, challenges.DNS01):
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
        challenge_body = dns_challenge(order, domain)
        (
            challenge_response,
            challenge_validation_contents,
        ) = challenge_body.response_and_validation(wrapped_account_key)

        challenge = Challenge()
        challenge.body_json = challenge_body.json_dumps()

        challenge.domain = domain
        challenge.certificate = certificate
        challenge.validation_domain = challenge_body.validation_domain_name(domain)
        challenge.validation_contents = challenge_validation_contents
        session.add(challenge)

    session.commit()
