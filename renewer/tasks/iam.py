from datetime import date
from typing import Union
import logging

from botocore.exceptions import ClientError

from renewer import huey
from renewer.extensions import config
from renewer.aws import iam_govcloud, iam_commercial
from renewer.json_log import json_log
from renewer.models.common import RouteType, OperationModel, CertificateModel
from renewer.models.cdn import CdnOperation, CdnCertificate, CdnRoute
from renewer.models.domain import DomainOperation, DomainCertificate, DomainRoute

logger = logging.getLogger(__name__)


@huey.retriable_task
def upload_certificate(session, operation_id: int, instance_type: RouteType):
    Operation: OperationModel
    Certificate: CertificateModel

    if instance_type is RouteType.ALB:
        Operation = DomainOperation
        Certificate = DomainCertificate
        iam = iam_govcloud
        iam_cert_prefix = config.GOVCLOUD_IAM_PREFIX
    elif instance_type is RouteType.CDN:
        Operation = CdnOperation
        Certificate = CdnCertificate
        iam = iam_commercial
        iam_cert_prefix = config.COMMERCIAL_IAM_PREFIX

    operation = session.query(Operation).get(operation_id)
    certificate = operation.certificate
    route = operation.route
    json_log(
        logger.info,
        {
            "instance_id": route.instance_id,
            "message": f"uploading certificate id {certificate.id}",
        },
    )

    if certificate.iam_server_certificate_arn is not None:
        return

    today = date.today().isoformat()
    certificate.iam_server_certificate_name = (
        f"{route.instance_id}-{today}-{certificate.id}"
    )
    try:
        response = iam.upload_server_certificate(
            Path=iam_cert_prefix,
            ServerCertificateName=certificate.iam_server_certificate_name,
            CertificateBody=certificate.leaf_pem,
            PrivateKey=certificate.private_key_pem,
            CertificateChain=certificate.fullchain_pem,
        )
    except ClientError as e:
        # TODO: there's an edge case here, where we uploaded the certificate but
        # failed to persist the metadata to the database. If that happens, we really
        # need to get the metadata back from IAM.
        if (
            e.response["Error"]["Code"] == "EntityAlreadyExistsException"
            and certificate.iam_server_certificate_id is not None
        ):
            return
        else:
            raise e

    certificate.iam_server_certificate_id = response["ServerCertificateMetadata"][
        "ServerCertificateId"
    ]
    certificate.iam_server_certificate_arn = response["ServerCertificateMetadata"][
        "Arn"
    ]

    session.add(certificate)
    session.commit()


@huey.retriable_task
def delete_old_certificate(session, operation_id: int, instance_type: RouteType):
    Operation: OperationModel
    Certificate: CertificateModel

    if instance_type is RouteType.ALB:
        Operation = DomainOperation
        Certificate = DomainCertificate
        iam = iam_govcloud
        iam_cert_prefix = config.GOVCLOUD_IAM_PREFIX
    elif instance_type is RouteType.CDN:
        Operation = CdnOperation
        Certificate = CdnCertificate
        iam = iam_commercial
        iam_cert_prefix = config.COMMERCIAL_IAM_PREFIX

    operation = session.query(Operation).get(operation_id)
    new_certificate = operation.certificate
    route = operation.route

    old_certificate = route.certificates[1]
    json_log(
        logger.info,
        {
            "instance_id": route.instance_id,
            "message": f"deleting certificate id {old_certificate.id}",
        },
    )

    if old_certificate.iam_server_certificate_name is None:
        json_log(
            logger.warning,
            {
                "instance_id": route.instance_id,
                "message": "not deleting certificate with unknown name",
                "certificate_id": old_certificate.id,
            },
        )
        return

    try:
        iam.delete_server_certificate(
            ServerCertificateName=old_certificate.iam_server_certificate_name
        )
    except iam.exceptions.NoSuchEntityException:
        return
