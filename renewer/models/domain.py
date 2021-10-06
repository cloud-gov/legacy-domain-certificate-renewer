import datetime
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
from renewer.aws import alb, iam_govcloud
from renewer.extensions import config
from renewer.models.common import (
    RouteType,
    RouteModel,
    CertificateModel,
    ChallengeModel,
    AcmeUserV2Model,
    OperationModel,
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
DomainModel = declarative.declarative_base(metadata=metadata)


def db_encryption_key():
    return config.DOMAIN_DATABASE_ENCRYPTION_KEY


class DomainAlbProxy(DomainModel):
    __tablename__ = "alb_proxies"

    alb_arn = sa.Column(sa.Text, primary_key=True)
    alb_dns_name = sa.Column(sa.Text)
    listener_arn = sa.Column(sa.Text)


class DomainRoute(DomainModel, RouteModel):
    __tablename__ = "routes"

    instance_id = sa.Column("guid", sa.Text, primary_key=True)
    state = sa.Column(sa.Text, nullable=False, index=True)
    domains = sa.Column(postgresql.ARRAY(sa.Text))
    challenge_json = sa.Column(postgresql.BYTEA)
    user_data_id = sa.Column(sa.Integer)
    alb_proxy_arn = sa.Column(sa.Text)
    alb_proxy: DomainAlbProxy = orm.relationship(
        DomainAlbProxy,
        foreign_keys=[alb_proxy_arn],
        primaryjoin="DomainRoute.alb_proxy_arn == DomainAlbProxy.alb_arn",
    )
    certificates: List["DomainCertificate"] = orm.relationship(
        "DomainCertificate",
        order_by="desc(DomainCertificate.expires)",
        primaryjoin="(foreign(DomainCertificate.route_guid)) == DomainRoute.instance_id",
        backref="route",
    )
    operations: List["DomainOperation"] = orm.relationship(
        "DomainOperation", backref="route", lazy="dynamic"
    )
    acme_user_id = sa.Column(sa.Integer, sa.ForeignKey("acme_user_v2.id"))
    route_type = RouteType.ALB

    def domain_external_list(self):
        """to match CdnRoute"""
        return self.domains

    def backport_manual_certs(self):
        """
        We were for some time manually rotating certs without updating the database
        This backports certs that exist in IAM/on ELBs into the database, so we can
        use the same logic for all rotations
        """
        # get the certs for the alb
        paginator = alb.get_paginator("describe_listener_certificates")
        cert_pages = paginator.paginate(ListenerArn=self.alb_proxy.listener_arn)
        for cert_page in cert_pages:
            for cert in cert_page["Certificates"]:
                if self.instance_id in cert["CertificateArn"]:
                    arn = cert["CertificateArn"]

                    if any(
                        c.iam_server_certificate_arn == arn for c in self.certificates
                    ):
                        # we already know about this one
                        continue

                    return DomainCertificate.create_cert_for_arn(arn, self)

    def create_renewal_operation(self):
        operation = DomainOperation()
        operation.route = self
        return operation


class DomainCertificate(DomainModel, CertificateModel):
    __tablename__ = "certificates"

    id = sa.Column(sa.Integer, sa.Sequence("certificates_id_seq"), primary_key=True)
    created_at = sa.Column(postgresql.TIMESTAMP)
    updated_at = sa.Column(postgresql.TIMESTAMP)
    deleted_at = sa.Column(postgresql.TIMESTAMP, index=True)
    route_guid = sa.Column(sa.Text)
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
    challenges: List["DomainChallenge"] = orm.relationship(
        "DomainChallenge", backref="certificate", lazy="dynamic"
    )
    order_json = sa.Column(sa.Text)
    fullchain_pem = sa.Column(sa.Text)
    leaf_pem = sa.Column(sa.Text)
    iam_server_certificate_id = sa.Column(sa.Text)
    iam_server_certificate_name = sa.Column(sa.Text)
    iam_server_certificate_arn = sa.Column(sa.Text)

    @classmethod
    def create_cert_for_arn(cls, arn, route):
        name = arn.split("/")[-1]
        data = iam_govcloud.get_server_certificate(ServerCertificateName=name)
        data = data["ServerCertificate"]
        expires = data["ServerCertificateMetadata"]["Expiration"]

        cert = DomainCertificate()
        cert.route = route
        cert.created_at = datetime.datetime.now()
        cert.iam_server_certificate_arn = arn
        cert.expires = expires
        cert.iam_server_certificate_name = name

        return cert


class DomainUserData(DomainModel):
    __tablename__ = "user_data"

    id = sa.Column(sa.Integer, primary_key=True)
    created_at = sa.Column(postgresql.TIMESTAMP)
    updated_at = sa.Column(postgresql.TIMESTAMP)
    deleted_at = sa.Column(postgresql.TIMESTAMP, index=True)
    email = sa.Column(sa.Text, nullable=False)
    reg = sa.Column(postgresql.BYTEA)
    key = sa.Column(postgresql.BYTEA)


class DomainOperation(DomainModel, OperationModel):
    __tablename__ = "operations"

    id = sa.Column(sa.Integer, sa.Sequence("operations_id_seq"), primary_key=True)
    route_guid: str = sa.Column(sa.ForeignKey(DomainRoute.instance_id), nullable=False)
    certificate_id: int = sa.Column(sa.ForeignKey(DomainCertificate.id))
    certificate: DomainCertificate = orm.relationship(
        DomainCertificate,
        foreign_keys=[certificate_id],
        primaryjoin="DomainOperation.certificate_id == DomainCertificate.id",
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


class DomainAcmeUserV2(DomainModel, AcmeUserV2Model):
    __tablename__ = "acme_user_v2"

    id = sa.Column(sa.Integer, autoincrement=True, primary_key=True)
    email = sa.Column(sa.String, nullable=False)
    uri = sa.Column(sa.String, nullable=False)
    private_key_pem: str = sa.Column(
        StringEncryptedType(sa.Text, db_encryption_key, AesGcmEngine, "pkcs5")
    )
    registration_json = sa.Column(sa.Text)

    routes: List[DomainRoute] = orm.relation(
        "DomainRoute", backref="acme_user", lazy="dynamic"
    )


class DomainChallenge(DomainModel, ChallengeModel):
    __tablename__ = "challenges"
    id = sa.Column(sa.Integer, primary_key=True)
    certificate_id = sa.Column(
        sa.Integer, sa.ForeignKey(DomainCertificate.id), nullable=False
    )
    domain = sa.Column(sa.String, nullable=False)
    validation_path = sa.Column(sa.String, nullable=False)
    validation_contents = sa.Column(sa.Text, nullable=False)
    body_json = sa.Column(sa.Text)
    answered = sa.Column(sa.Boolean, default=False)
    certificate: DomainCertificate
