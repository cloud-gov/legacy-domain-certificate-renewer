"""stop using arn and name

Revision ID: 95e3ab2a28dd
Revises: 23319464f990
Create Date: 2021-10-05 23:42:27.009229

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.declarative import declarative_base


# revision identifiers, used by Alembic.
revision = "95e3ab2a28dd"
down_revision = "23319464f990"
branch_labels = None
depends_on = None

Base = declarative_base()


class DomainCertificate(Base):
    __tablename__ = "certificates"

    id = sa.Column(sa.Integer, sa.Sequence("certificates_id_seq"), primary_key=True)
    arn = sa.Column(sa.Text)
    name = sa.Column(sa.Text)
    iam_server_certificate_name = sa.Column(sa.Text)
    iam_server_certificate_arn = sa.Column(sa.Text)


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_cdn():
    pass


def downgrade_cdn():
    pass


def upgrade_domain():
    """
    cdn-broker's db didn't previously track arns, names, or IDs, so I added them to the cdn-broker db and to
    the domain-broker db. When I did that, I created new columns, instead of updating the mappings
    to point to the existing columns. This shoves all the data from before into the new columns,
    because that feels easier to reason about than dropping the new ones and aliasing the new names
    to the old columns.
    """
    bind = op.get_bind()
    session = orm.Session(bind=bind)
    for certificate in session.query(DomainCertificate):
        if certificate.arn is not None:
            certificate.iam_server_certificate_arn = certificate.arn
            session.add(certificate)
        if certificate.name is not None:
            certificate.iam_server_certificate_name = certificate.name
            session.add(certificate)
    session.commit()


def downgrade_domain():
    pass
