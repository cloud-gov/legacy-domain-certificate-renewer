import json
from typing import Dict


def json_log(method, body: Dict):
    body = dict(legacy_domain_certificate_renewer=body)
    method(json.dumps(body))
