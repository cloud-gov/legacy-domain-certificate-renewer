import time
from typing import Type, Union

from renewer.aws import s3_commercial, s3_govcloud
from renewer.cdn_models import CdnOperation, CdnChallenge, CdnCertificate
from renewer.domain_models import DomainOperation, DomainChallenge, DomainCertificate
from renewer.extensions import config
from renewer.huey import retriable_task
from renewer.route_type import RouteType


TOperation = Type[Union[DomainOperation, CdnOperation]]
TCertificate = Type[Union[DomainCertificate, CdnCertificate]]
TChallenge = Type[Union[DomainChallenge, CdnChallenge]]


@retriable_task
def upload_challenge_files(session, operation_id, route_type):
    Operation: TOperation
    if route_type is RouteType.ALB:
        Operation = DomainOperation
        s3 = s3_govcloud
        bucket = config.GOVCLOUD_BUCKET
    elif route_type is RouteType.CDN:
        Operation = CdnOperation
        s3 = s3_commercial
        bucket = config.COMMERCIAL_BUCKET
    operation = session.query(Operation).get(operation_id)
    certificate = operation.certificate
    for challenge in certificate.challenges:
        if not challenge.answered:
            s3.put_object(
                Bucket=bucket,
                Body=challenge.validation_contents.encode(),
                Key=challenge.validation_path,
                ServerSideEncryption="AES256",
            )
    # sleep to make sure the file will be in S3 when we want it
    time.sleep(config.S3_PROPAGATION_TIME)
