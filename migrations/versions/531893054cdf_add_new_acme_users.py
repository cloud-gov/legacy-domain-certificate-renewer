"""add new acme users

Revision ID: 531893054cdf
Revises: fed9ab0d1672
Create Date: 2021-09-02 22:34:56.794291

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "531893054cdf"
down_revision = "fed9ab0d1672"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_cdn():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "acme_user_v2",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("uri", sa.String(), nullable=False),
        sa.Column("private_key_pem", sa.Text(), nullable=True),
        sa.Column("registration_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_acme_user_v2")),
    )
    op.add_column("routes", sa.Column("acme_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_routes_acme_user_id_acme_user_v2"),
        "routes",
        "acme_user_v2",
        ["acme_user_id"],
        ["id"],
    )
    # ### end Alembic commands ###


def downgrade_cdn():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        op.f("fk_routes_acme_user_id_acme_user_v2"), "routes", type_="foreignkey"
    )
    op.drop_column("routes", "acme_user_id")
    op.drop_table("acme_user_v2")
    # ### end Alembic commands ###


def upgrade_domain():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "acme_user_v2",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("uri", sa.String(), nullable=False),
        sa.Column("private_key_pem", sa.Text(), nullable=True),
        sa.Column("registration_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_acme_user_v2")),
    )
    op.add_column("routes", sa.Column("acme_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_routes_acme_user_id_acme_user_v2"),
        "routes",
        "acme_user_v2",
        ["acme_user_id"],
        ["id"],
    )
    # ### end Alembic commands ###


def downgrade_domain():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        op.f("fk_routes_acme_user_id_acme_user_v2"), "routes", type_="foreignkey"
    )
    op.drop_column("routes", "acme_user_id")
    op.drop_table("acme_user_v2")
    # ### end Alembic commands ###
