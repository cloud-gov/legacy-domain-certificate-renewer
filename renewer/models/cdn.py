import datetime
from enum import Enum
from typing import List

import sqlalchemy as sa
from sqlalchemy.ext import declarative
from sqlalchemy.dialects import postgresql
from sqlalchemy import orm
from sqlalchemy_utils.types.encrypted.encrypted_type import (
    AesGcmEngine,
    StringEncryptedType,
)

from renewer.action import Action
from renewer.extensions import config
from renewer.models.common import (
    RouteType,
    RouteModel,
    CertificateModel,
    OperationModel,
    AcmeUserV2Model,
    ChallengeModel,
    OperationState,
)

convention = {
    "ix": "idx_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = sa.MetaData(naming_convention=convention)

CdnModel = orm.declarative_base(metadata=metadata)


def db_encryption_key():
    return config.CDN_DATABASE_ENCRYPTION_KEY


class CdnUserData(CdnModel):
    """
    CdnUserData is about the Let's Encrypt user associated with a CdnRoute.
    We probably have no reason to ever think about this model in this project.
    """

    __tablename__ = "user_data"

    id = sa.Column(sa.Integer, primary_key=True)
    created_at = sa.Column(postgresql.TIMESTAMP)
    updated_at = sa.Column(postgresql.TIMESTAMP)
    deleted_at = sa.Column(postgresql.TIMESTAMP, index=True)
    email = sa.Column(sa.Text, nullable=False)
    reg = sa.Column(postgresql.BYTEA)
    key = sa.Column(postgresql.BYTEA)


class CdnRoute(CdnModel, RouteModel):
    """
    CdnRoute represents the core of the service instance
    """

    __tablename__ = "routes"

    id = sa.Column(sa.Integer, primary_key=True)
    # domain_internal is effectively the domain name of the CloudFront distribution
    domain_internal = sa.Column(sa.Text)
    # domain_external is a comma-separated list of domain names the user wants the CloudFront distribution to respond to
    domain_external = sa.Column(sa.Text)
    created_at = sa.Column(postgresql.TIMESTAMP)
    updated_at = sa.Column(postgresql.TIMESTAMP)
    deleted_at = sa.Column(postgresql.TIMESTAMP, index=True)
    instance_id = sa.Column(sa.Text, index=True, nullable=False)
    dist_id = sa.Column(sa.Text)
    origin = sa.Column(sa.Text)
    path = sa.Column(sa.Text)
    insecure_origin = sa.Column(sa.Boolean)
    challenge_json = sa.Column(postgresql.BYTEA)
    user_data_id = sa.Column(sa.Integer, sa.ForeignKey("acme_user_v2.id"))
    certificates: List["CdnCertificate"] = orm.relationship(
        "CdnCertificate",
        order_by="desc(CdnCertificate.expires)",
        primaryjoin="(foreign(CdnCertificate.route_id)) == CdnRoute.id",
        backref="route",
    )
    # state should be one of:
    # deprovisioned
    # provisioning
    # provisioned
    state = sa.Column(sa.Text, index=True, nullable=False)
    operations: List["CdnOperation"] = orm.relationship(
        "CdnOperation", backref="route", lazy="dynamic"
    )
    acme_user_id = sa.Column(sa.Integer, sa.ForeignKey("acme_user_v2.id"))
    route_type = RouteType.CDN

    def domain_external_list(self):
        return self.domain_external.split(",")

    def create_renewal_operation(self):
        operation = CdnOperation()
        operation.route = self
        return operation


class CdnCertificate(CdnModel, CertificateModel):
    __tablename__ = "certificates"

    id = sa.Column(sa.Integer, primary_key=True)
    created_at = sa.Column(postgresql.TIMESTAMP)
    updated_at = sa.Column(postgresql.TIMESTAMP)
    deleted_at = sa.Column(postgresql.TIMESTAMP, index=True)
    route_id = sa.Column(sa.Integer)
    domain = sa.Column(sa.Text)
    # cert_url is the Let's Encrypt URL for the certificate
    cert_url = sa.Column(sa.Text)
    # certificate is the actual body of the certificate chain
    # this was used by the old broker, but the renewer uses fullchain_pem and leaf_pem instead
    certificate = sa.Column(postgresql.BYTEA)
    expires = sa.Column(postgresql.TIMESTAMP, index=True)
    private_key_pem: str = sa.Column(
        StringEncryptedType(sa.Text, db_encryption_key, AesGcmEngine, "pkcs5")
    )
    csr_pem = sa.Column(sa.Text)
    challenges: List["CdnChallenge"] = orm.relationship(
        "CdnChallenge", backref="certificate", lazy="dynamic"
    )
    order_json = sa.Column(sa.Text)
    fullchain_pem = sa.Column(sa.Text)
    leaf_pem = sa.Column(sa.Text)
    iam_server_certificate_id = sa.Column(sa.Text)
    iam_server_certificate_name = sa.Column(sa.Text)
    iam_server_certificate_arn = sa.Column(sa.Text)


class CdnOperation(CdnModel, OperationModel):
    __tablename__ = "operations"

    id = sa.Column(sa.Integer, sa.Sequence("operations_id_seq"), primary_key=True)
    route_id: int = sa.Column(sa.ForeignKey(CdnRoute.id), nullable=False)
    certificate_id: int = sa.Column(sa.ForeignKey(CdnCertificate.id))
    certificate: CdnCertificate = orm.relationship(
        CdnCertificate,
        foreign_keys=[certificate_id],
        primaryjoin="CdnOperation.certificate_id == CdnCertificate.id",
    )
    state = sa.Column(
        sa.Text,
        default=OperationState.IN_PROGRESS.value,
        server_default=OperationState.IN_PROGRESS.value,
        nullable=False,
    )
    action = sa.Column(
        sa.Text,
        default=Action.RENEW.value,
        server_default=Action.RENEW.value,
        nullable=False,
    )


class CdnAcmeUserV2(CdnModel, AcmeUserV2Model):
    __tablename__ = "acme_user_v2"

    id = sa.Column(sa.Integer, autoincrement=True, primary_key=True)
    email = sa.Column(sa.String, nullable=False)
    uri = sa.Column(sa.String, nullable=False)
    private_key_pem: str = sa.Column(
        StringEncryptedType(sa.Text, db_encryption_key, AesGcmEngine, "pkcs5")
    )
    registration_json = sa.Column(sa.Text)

    routes: List[CdnRoute] = orm.relationship(
        "CdnRoute",
        backref="acme_user",
        primaryjoin="(foreign(CdnRoute.acme_user_id)) == CdnAcmeUserV2.id",
    )


class CdnChallenge(CdnModel, ChallengeModel):
    __tablename__ = "challenges"
    id = sa.Column(sa.Integer, primary_key=True)
    certificate_id = sa.Column(
        sa.Integer, sa.ForeignKey(CdnCertificate.id), nullable=False
    )
    domain = sa.Column(sa.String, nullable=False)
    validation_path = sa.Column(sa.String, nullable=False)
    validation_contents = sa.Column(sa.Text, nullable=False)
    body_json = sa.Column(sa.Text)
    answered = sa.Column(sa.Boolean, default=False)
    certificate: CdnCertificate
