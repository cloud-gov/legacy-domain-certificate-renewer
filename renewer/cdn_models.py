import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy.ext import declarative
from sqlalchemy.dialects import postgresql
from sqlalchemy import orm
from sqlalchemy_utils.types.encrypted.encrypted_type import (
    AesGcmEngine,
    StringEncryptedType,
)

from renewer.extensions import config

CdnBase = declarative.declarative_base()


def db_encryption_key():
    return config.DATABASE_ENCRYPTION_KEY


class CdnUserData(CdnBase):
    """
    CdnUserData is about the Let's Encrypt user associated with a CdnRoute.
    We probably have no reason to ever think about this model in this project.
    """

    __tablename__ = "user_data"

    id = sa.Column(sa.Integer, primary_key=True)
    created_at = sa.Column(postgresql.TIMESTAMP)
    updated_at = sa.Column(postgresql.TIMESTAMP)
    deleted_at = sa.Column(postgresql.TIMESTAMP)
    email = sa.Column(sa.Text, nullable=False)
    reg = sa.Column(postgresql.BYTEA)
    key = sa.Column(postgresql.BYTEA)


class CdnRoute(CdnBase):
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
    deleted_at = sa.Column(postgresql.TIMESTAMP)
    instance_id = sa.Column(sa.Text)
    dist_id = sa.Column(sa.Text)
    origin = sa.Column(sa.Text)
    path = sa.Column(sa.Text)
    insecure_origin = sa.Column(sa.Boolean)
    challenge_json = sa.Column(postgresql.BYTEA)
    user_data_id = sa.Column(sa.Integer, sa.ForeignKey(CdnUserData.id))
    user_data = orm.relationship(CdnUserData)
    certificates = orm.relationship("CdnCertificate")
    # state should be one of:
    # deprovisioned
    # provisioning
    # provisioned
    state = sa.Column(sa.Text)

    def domain_external_list(self):
        return self.domain_external.split(",")


class CdnCertificate(CdnBase):
    __tablename__ = "certificates"

    id = sa.Column(sa.Integer, primary_key=True)
    created_at = sa.Column(postgresql.TIMESTAMP)
    updated_at = sa.Column(postgresql.TIMESTAMP)
    deleted_at = sa.Column(postgresql.TIMESTAMP)
    route_id = sa.Column(sa.Integer, sa.ForeignKey(CdnRoute.id))
    route = orm.relationship(CdnRoute, back_populates="certificates")
    domain = sa.Column(sa.Text)
    # cert_url is the Let's Encrypt URL for the certificate
    cert_url = sa.Column(sa.Text)
    # certificate is the actual body of the certificate chain
    certificate = sa.Column(postgresql.BYTEA)
    expires = sa.Column(postgresql.TIMESTAMP)
