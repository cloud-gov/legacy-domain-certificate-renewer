import pytest

from renewer.cdn_models import CdnOperation, CdnRoute, CdnAcmeUserV2
from renewer.tasks import letsencrypt


def test_create_acme_user_when_none_exists(clean_db, cdn_route):
    instance_id = cdn_route.id
    operation = cdn_route.create_renewal_operation()
    clean_db.add(cdn_route)
    clean_db.commit()
    letsencrypt.cdn_create_user(clean_db, operation.id)
    clean_db.expunge_all()

    cdn_route = clean_db.query(CdnRoute).get(instance_id)

    assert cdn_route.acme_user_id is not None
