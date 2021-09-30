from datetime import datetime, timedelta, timezone

import pytest

from renewer.aws import iam_commercial as real_iam_c
from renewer.aws import iam_govcloud as real_iam_g
from tests.lib.fake_aws import FakeAWS


class FakeIAM(FakeAWS):
    def expect_upload_server_certificate(
        self, name: str, cert: str, private_key: str, chain: str, path: str
    ):
        now = datetime.now(timezone.utc)
        three_months_from_now = now + timedelta(90)
        method = "upload_server_certificate"
        request = {
            "Path": path,
            "ServerCertificateName": name,
            "CertificateBody": cert,
            "PrivateKey": private_key,
            "CertificateChain": chain,
        }
        response = {
            "ServerCertificateMetadata": {
                "ServerCertificateId": "FAKE_CERT_ID_XXXXXXXX",
                "Path": path,
                "ServerCertificateName": name,
                "Arn": f"arn:aws:iam::000000000000:server-certificate{path}{name}",
                "UploadDate": now,
                "Expiration": three_months_from_now,
            }
        }
        self.stubber.add_response(method, response, request)

    def expect_upload_server_certificate_raising_duplicate(
        self, name: str, cert: str, private_key: str, chain: str, path: str
    ):
        self.stubber.add_client_error(
            "upload_server_certificate",
            service_error_code="EntityAlreadyExistsException",
            service_message="already got one",
            expected_params={
                "Path": path,
                "ServerCertificateName": name,
                "CertificateBody": cert,
                "PrivateKey": private_key,
                "CertificateChain": chain,
            },
        )

    def expects_delete_server_certificate(self, name: str):
        self.stubber.add_response(
            "delete_server_certificate", {}, {"ServerCertificateName": name}
        )

    def expects_delete_server_certificate_returning_no_such_entity(self, name: str):
        self.stubber.add_client_error(
            "delete_server_certificate",
            service_error_code="NoSuchEntity",
            service_message="'Ain't there.",
            http_status_code=404,
            expected_params={"ServerCertificateName": name},
        )

    def expect_get_server_certificate(
        self, name: str, expiration: datetime, path: str = None
    ):
        if path is None:
            path = "/"
        response = {
            "ServerCertificate": {
                "ServerCertificateMetadata": {
                    "Path": path,
                    "ServerCertificateName": name,
                    "ServerCertificateId": "this-needs-to-be-sixteen-digits",
                    "Arn": f"arn:aws:iam:123456:{path}{name}",
                    "UploadDate": datetime.strptime(
                        "2021-08-05T16:49:16Z", "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "Expiration": expiration,
                },
                "CertificateBody": "string",
                "CertificateChain": "string",
                "Tags": [{"Key": "string", "Value": "string"}],
            }
        }
        self.stubber.add_response(
            "get_server_certificate", response, {"ServerCertificateName": name}
        )


@pytest.fixture(autouse=True)
def iam_commercial():
    with FakeIAM.stubbing(real_iam_c) as iam_stubber:
        yield iam_stubber


@pytest.fixture(autouse=True)
def iam_govcloud():
    with FakeIAM.stubbing(real_iam_g) as iam_stubber:
        yield iam_stubber
