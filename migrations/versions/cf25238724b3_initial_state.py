"""initial-state

Revision ID: cf25238724b3
Revises: 
Create Date: 2021-08-24 18:50:57.014125

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "cf25238724b3"
down_revision = None
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_cdn():
    # yes, this is essentially a rename. No, I'm not going to make it not happen, because
    # I already spent too much time trying :sob:
    op.drop_index("uix_routes_instance_id", table_name="routes")
    op.create_index(
        op.f("idx_routes_instance_id"), "routes", ["instance_id"], unique=False
    )


def downgrade_cdn():
    op.drop_index(op.f("idx_routes_instance_id"), table_name="routes")
    op.create_index("uix_routes_instance_id", "routes", ["instance_id"], unique=False)


def upgrade_domain():
    pass


def downgrade_domain():
    pass
