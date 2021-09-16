from enum import Enum
from typing import Union, Type


class RouteType(Enum):
    CDN = "cdn"
    ALB = "alb"
