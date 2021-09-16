from enum import Enum
from typing import Union, Type

from renewer.cdn_models import (
    CdnAcmeUserV2,
    CdnCertificate,
    CdnChallenge,
    CdnOperation,
    CdnRoute,
)
from renewer.domain_models import (
    DomainAcmeUserV2,
    DomainCertificate,
    DomainChallenge,
    DomainOperation,
    DomainRoute,
)


class RouteType(Enum):
    CDN = "cdn"
    ALB = "alb"


TOperation = Type[Union[DomainOperation, CdnOperation]]
TUser = Type[Union[DomainAcmeUserV2, CdnAcmeUserV2]]
TRoute = Type[Union[DomainRoute, CdnRoute]]
TCertificate = Type[Union[DomainCertificate, CdnCertificate]]
TChallenge = Type[Union[DomainChallenge, CdnChallenge]]
