import pytest

from renewer.aws import s3_commercial as real_s3_c
from renewer.aws import s3_govcloud as real_s3_g

from tests.lib.fake_aws import FakeAWS


class FakeS3(FakeAWS):
    def expect_put_object(self, bucket, key, object_body_bytes):
        method = "put_object"
        request = {
            "Bucket": bucket,
            "Key": key,
            "Body": object_body_bytes,
            "ServerSideEncryption": "AES256",
        }
        response = {
            "ETag": "whatsanetag",
            "ServerSideEncryption": "AES256",
        }
        self.stubber.add_response("put_object", response, request)


@pytest.fixture(autouse=True)
def s3_commercial():
    with FakeS3.stubbing(real_s3_c) as s3_stubber:
        yield s3_stubber


@pytest.fixture(autouse=True)
def s3_govcloud():
    with FakeS3.stubbing(real_s3_g) as s3_stubber:
        yield s3_stubber
