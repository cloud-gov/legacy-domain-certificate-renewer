import josepy
import OpenSSL
from acme import challenges, client, crypto_util, messages, errors
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from renewer.cdn_models import CdnOperation, CdnAcmeUserV2
from renewer.domain_models import DomainOperation, DomainAcmeUserV2
from renewer.extensions import config
from renewer.acme_client import AcmeClient


def alb_create_user(session, operation_id):
    operation = session.query(DomainOperation).get(operation_id)
    route = operation.route
    acme_user = DomainAcmeUserV2()
    return create_user(session, route, operation, acme_user)


def cdn_create_user(session, operation_id):
    operation = session.query(CdnOperation).get(operation_id)
    route = operation.route
    acme_user = CdnAcmeUserV2()
    return create_user(session, route, operation, acme_user)


def create_user(session, route, operation, acme_user):
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
