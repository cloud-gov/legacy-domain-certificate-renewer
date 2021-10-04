import datetime
from enum import Enum
from typing import Union, Type

from renewer.extensions import config


class RouteType(str, Enum):
    CDN = "cdn"
    ALB = "alb"


class OperationState(Enum):
    IN_PROGRESS = "in progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RouteModel:
    @property
    def needs_renewal(self):
        return all([c.needs_renewal for c in self.certificates])

    @classmethod
    def find_active_instances(cls, session):
        query = session.query(cls).filter(cls.state == "provisioned")
        routes = query.all()
        return routes


class CertificateModel:
    @property
    def needs_renewal(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        return self.expires < now + datetime.timedelta(days=config.RENEW_BEFORE_DAYS)


class OperationModel:
    pass


class AcmeUserV2Model:
    pass


class ChallengeModel:
    pass
