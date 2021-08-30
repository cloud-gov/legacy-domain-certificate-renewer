import boto3

from renewer.extensions import config

govcloud_session = boto3.Session(
    region_name=config.AWS_GOVCLOUD_REGION,
    aws_access_key_id=config.AWS_GOVCLOUD_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_GOVCLOUD_SECRET_ACCESS_KEY,
)

alb = govcloud_session.client("elbv2")
iam_govcloud = govcloud_session.client("iam")
iam_commercial = None
