"""add private key and csr to certificate, track certificate in operation

Revision ID: 0d14cc3a1cf1
Revises: 531893054cdf
Create Date: 2021-09-10 23:03:20.631787

"""
from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision = "0d14cc3a1cf1"
down_revision = "531893054cdf"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_cdn():
    op.add_column(
        "certificates",
        sa.Column(
            "private_key_pem",
            sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(),
            nullable=True,
        ),
    )
    op.add_column("certificates", sa.Column("csr_pem", sa.Text(), nullable=True))
    op.add_column(
        "operations", sa.Column("certificate_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_operations_certificate_id_certificates"),
        "operations",
        "certificates",
        ["certificate_id"],
        ["id"],
    )


def downgrade_cdn():
    op.drop_constraint(
        op.f("fk_operations_certificate_id_certificates"),
        "operations",
        type_="foreignkey",
    )
    op.drop_column("operations", "certificate_id")
    op.drop_column("certificates", "csr_pem")
    op.drop_column("certificates", "private_key_pem")


def upgrade_domain():
    op.add_column(
        "certificates",
        sa.Column(
            "private_key_pem",
            sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(),
            nullable=True,
        ),
    )
    op.add_column("certificates", sa.Column("csr_pem", sa.Text(), nullable=True))
    op.add_column(
        "operations", sa.Column("certificate_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_operations_certificate_id_certificates"),
        "operations",
        "certificates",
        ["certificate_id"],
        ["id"],
    )


def downgrade_domain():
    op.drop_constraint(
        op.f("fk_operations_certificate_id_certificates"),
        "operations",
        type_="foreignkey",
    )
    op.drop_column("operations", "certificate_id")
    op.drop_column("certificates", "csr_pem")
    op.drop_column("certificates", "private_key_pem")
