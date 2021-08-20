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

from renewer.extensions import config, alb, iam_govcloud

DomainBase = declarative.declarative_base()


def find_active_instances(session):
    domain_query = session.query(DomainRoute).filter(DomainRoute.state == "provisioned")
    domain_routes = domain_query.all()
    return domain_routes


class DomainAlbProxy(DomainBase):
    __tablename__ = "alb_proxies"

    alb_arn = sa.Column(sa.Text, primary_key=True)
    alb_dns_name = sa.Column(sa.Text)
    listener_arn = sa.Column(sa.Text)


class DomainRoute(DomainBase):
    __tablename__ = "routes"

    instance_id = sa.Column("guid", sa.Text, primary_key=True)
    state = sa.Column(sa.Text)
    domains = sa.Column(postgresql.ARRAY(sa.Text))
    challenge_json = sa.Column(postgresql.BYTEA)
    user_data_id = sa.Column(sa.Integer)
    alb_proxy_arn = sa.Column(sa.Text, sa.ForeignKey(DomainAlbProxy.alb_arn))
    alb_proxy = orm.relationship(DomainAlbProxy)
    certificates = orm.relationship(
        "DomainCertificate", order_by="desc(DomainCertificate.expires)"
    )

    def domain_external_list(self):
        """to match CdnRoute"""
        return self.domains

    @property
    def needs_renewal(self):
        return all([c.needs_renewal for c in self.certificates])

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

                    if any(c.arn == arn for c in self.certificates):
                        # we already know about this one
                        continue

                    return DomainCertificate.create_cert_for_arn(arn, self)


class DomainCertificate(DomainBase):
    __tablename__ = "certificates"

    id = sa.Column(sa.Integer, sa.Sequence("certificates_id_seq"), primary_key=True)
    created_at = sa.Column(postgresql.TIMESTAMP)
    updated_at = sa.Column(postgresql.TIMESTAMP)
    deleted_at = sa.Column(postgresql.TIMESTAMP)
    route_guid = sa.Column(sa.Integer, sa.ForeignKey(DomainRoute.instance_id))
    route = orm.relationship(DomainRoute, back_populates="certificates")
    domain = sa.Column(sa.Text)
    # cert_url is the Let's Encrypt URL for the certificate
    cert_url = sa.Column(sa.Text)
    # certificate is the actual body of the certificate chain
    certificate = sa.Column(postgresql.BYTEA)
    arn = sa.Column(sa.Text)
    name = sa.Column(sa.Text)
    expires = sa.Column(postgresql.TIMESTAMP)

    @property
    def needs_renewal(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        return self.expires < now + datetime.timedelta(days=config.RENEW_BEFORE_DAYS)

    @classmethod
    def create_cert_for_arn(cls, arn, route):
        name = arn.split("/")[-1]
        data = iam_govcloud.get_server_certificate(ServerCertificateName=name)
        data = data["ServerCertificate"]
        expires = data["ServerCertificateMetadata"]["Expiration"]
        expires = datetime.datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ")

        cert = DomainCertificate()
        cert.route = route
        cert.created_at = datetime.datetime.now()
        cert.arn = arn
        cert.expires = expires
        cert.name = name

        return cert


class DomainUserData(DomainBase):
    __tablename__ = "user_data"

    id = sa.Column(sa.Integer, primary_key=True)
    created_at = sa.Column(postgresql.TIMESTAMP)
    updated_at = sa.Column(postgresql.TIMESTAMP)
    deleted_at = sa.Column(postgresql.TIMESTAMP)
    email = sa.Column(sa.Text, nullable=False)
    reg = sa.Column(postgresql.BYTEA)
    key = sa.Column(postgresql.BYTEA)
