import json
import importlib

import pytest
from renewer.config import config_from_env


@pytest.fixture()
def vcap_application():
    data = {
        "application_id": "my-app-id",
        "application_name": "my-app-name",
        "application_uris": [],
        "application_version": "my-app-version",
        "cf_api": "cf-api",
        "name": "my-app-name",
        "organization_name": "my-org-name",
        "space_name": "my-space-name",
        "process_type": "web",
        "uris": [],
        "version": "my-app-version",
    }

    return json.dumps(data)


@pytest.fixture()
def vcap_services():
    data = {
        "aws-rds": [
            {
                "credentials": {
                    "db_name": "cdn-db-name",
                    "host": "cdn-db-host",
                    "password": "cdn-db-password",
                    "port": "cdn-db-port",
                    "uri": "postgres://cdn-db-uri",
                    "username": "cdn-db-username",
                },
                "instance_name": "rds-cdn-broker",
                "label": "aws-rds",
                "name": "rds-cdn-broker",
                "plan": "medium-psql",
                "tags": ["database", "RDS"],
            }
        ],
        "user-provided": [
            {
                "credentials": {
                    "db_name": "alb-db-name",
                    "host": "alb-db-host",
                    "password": "alb-db-password",
                    "port": "alb-db-port",
                    "uri": "postgresql://alb-db-uri",
                    "username": "alb-db-username",
                },
                "instance_name": "rds-domain-broker",
                "label": "aws-rds",
                "name": "rds-domain-broker",
                "tags": ["database", "RDS"],
            }
        ],
        "redis": [
            {
                "credentials": {
                    "host": "my-redis-hostname",
                    "password": "my-redis-password",
                    "port": "my-redis-port",
                    "ports": {"6379/tcp": "my-redis-port-tuple"},
                    "uri": "my-redis-uri",
                },
                "instance_name": "my-app-name-redis",
                "label": "redis",
                "name": "my-app-name-redis",
                "plan": "standard-ha",
                "tags": ["redis", "Elasticache"],
            }
        ],
    }

    return json.dumps(data)


@pytest.fixture()
def mocked_env(vcap_application, vcap_services, monkeypatch):
    monkeypatch.setenv("VCAP_APPLICATION", vcap_application)
    monkeypatch.setenv("VCAP_SERVICES", vcap_services)
    monkeypatch.setenv("ENV", "local")
    monkeypatch.setenv("CDN_DATABASE_ENCRYPTION_KEY", "CHANGEME")
    monkeypatch.setenv("DOMAIN_DATABASE_ENCRYPTION_KEY", "CHANGEME")
    monkeypatch.setenv("LETS_ENCRYPT_REGISTRATION_EMAIL", "me@example.com")
    monkeypatch.setenv("AWS_COMMERCIAL_REGION", "us-west-1")
    monkeypatch.setenv("AWS_COMMERCIAL_ACCESS_KEY_ID", "ASIANOTAREALKEY")
    monkeypatch.setenv("AWS_COMMERCIAL_SECRET_ACCESS_KEY", "NOT_A_REAL_SECRET_KEY")
    monkeypatch.setenv("COMMERCIAL_BUCKET", "fake-commercial-bucket")
    monkeypatch.setenv("COMMERCIAL_IAM_PREFIX", "/commercial/certs")
    monkeypatch.setenv("AWS_GOVCLOUD_REGION", "us-gov-west-1")
    monkeypatch.setenv("AWS_GOVCLOUD_ACCESS_KEY_ID", "ASIANOTAREALKEYGOV")
    monkeypatch.setenv("AWS_GOVCLOUD_SECRET_ACCESS_KEY", "NOT_A_REAL_SECRET_KEY_GOV")
    monkeypatch.setenv("GOVCLOUD_BUCKET", "fake-govcloud-bucket")
    monkeypatch.setenv("GOVCLOUD_IAM_PREFIX", "/govcloud/certs")
    monkeypatch.setenv("S3_PROPAGATION_TIME", "5")
    monkeypatch.setenv("IAM_PROPAGATION_TIME", "6")
    monkeypatch.setenv("AWS_POLL_WAIT_TIME_IN_SECONDS", "30")
    monkeypatch.setenv("AWS_POLL_MAX_ATTEMPTS", "10")


@pytest.mark.parametrize("env", ["local", "development", "staging", "production"])
def test_config_doesnt_explode(env, monkeypatch, mocked_env):
    monkeypatch.setenv("ENV", env)
    config = config_from_env()
    assert config.ENV == env


@pytest.mark.parametrize("env", ["development", "staging", "production"])
def test_config_gets_credentials(env, monkeypatch, mocked_env):
    monkeypatch.setenv("ENV", env)
    config = config_from_env()
    assert config.CDN_BROKER_DATABASE_URI == "postgresql://cdn-db-uri"
    assert config.DOMAIN_BROKER_DATABASE_URI == "postgresql://alb-db-uri"
    assert config.RENEW_BEFORE_DAYS == 30
    assert config.AWS_COMMERCIAL_REGION == "us-west-1"
    assert config.AWS_COMMERCIAL_ACCESS_KEY_ID == "ASIANOTAREALKEY"
    assert config.AWS_COMMERCIAL_SECRET_ACCESS_KEY == "NOT_A_REAL_SECRET_KEY"
    assert config.COMMERCIAL_BUCKET == "fake-commercial-bucket"
    assert config.COMMERCIAL_IAM_PREFIX == "/commercial/certs"
    assert config.AWS_GOVCLOUD_REGION == "us-gov-west-1"
    assert config.AWS_GOVCLOUD_ACCESS_KEY_ID == "ASIANOTAREALKEYGOV"
    assert config.AWS_GOVCLOUD_SECRET_ACCESS_KEY == "NOT_A_REAL_SECRET_KEY_GOV"
    assert config.GOVCLOUD_BUCKET == "fake-govcloud-bucket"
    assert config.GOVCLOUD_IAM_PREFIX == "/govcloud/certs"
    assert config.REDIS_HOST == "my-redis-hostname"
    assert config.REDIS_PORT == "my-redis-port"
    assert config.REDIS_PASSWORD == "my-redis-password"
    assert config.LETS_ENCRYPT_REGISTRATION_EMAIL == "me@example.com"
    assert config.CDN_DATABASE_ENCRYPTION_KEY is not None
    assert config.DOMAIN_DATABASE_ENCRYPTION_KEY is not None
    assert config.S3_PROPAGATION_TIME == 5
    assert config.IAM_PROPAGATION_TIME == 6
    assert config.AWS_POLL_WAIT_TIME_IN_SECONDS == 30
    assert config.AWS_POLL_MAX_ATTEMPTS == 10

    # import these here, so it's clear we're just importing them for this test
    import renewer.extensions
    import renewer.aws
    import renewer.models.domain
    import renewer.models.cdn
    import renewer.huey

    def reload():
        # force a reload of these modules. Order is important
        importlib.reload(renewer.extensions)
        importlib.reload(renewer.aws)
        importlib.reload(renewer.models.domain)
        importlib.reload(renewer.models.cdn)
        importlib.reload(renewer.huey)

    raised = None
    try:
        # try to reload modules
        reload()
    except Exception as e:
        # cache the exception, if any
        raised = e
    finally:
        # reset the environment, so we don't mess with other tests
        monkeypatch.delenv("VCAP_APPLICATION")
        monkeypatch.delenv("VCAP_SERVICES")
        monkeypatch.delenv("AWS_GOVCLOUD_REGION")
        monkeypatch.delenv("AWS_GOVCLOUD_ACCESS_KEY_ID")
        monkeypatch.delenv("AWS_GOVCLOUD_SECRET_ACCESS_KEY")
        monkeypatch.setenv("ENV", "local")
        reload()

    # make an assertion to pass/fail the test
    assert raised is None


def test_upgrade_config(monkeypatch, vcap_application, vcap_services):
    """
    this is a special test, because the upgrade config assumes we don't want
    anything to do with AWS or Redis, so we want to make sure we can instantiate
    our models with that bare config
    """
    # import these here, so it's clear we're just importing them for this test
    import renewer.extensions
    import renewer.aws
    import renewer.models.domain
    import renewer.models.cdn

    def reload():
        # force a reload of these modules. Order is important
        importlib.reload(renewer.extensions)
        importlib.reload(renewer.aws)
        importlib.reload(renewer.models.domain)
        importlib.reload(renewer.models.cdn)

    # set up environment
    monkeypatch.setenv("VCAP_APPLICATION", vcap_application)
    monkeypatch.setenv("VCAP_SERVICES", vcap_services)
    monkeypatch.setenv("ENV", "upgrade-schema")
    monkeypatch.setenv("CDN_DATABASE_ENCRYPTION_KEY", "CHANGEME")
    monkeypatch.setenv("DOMAIN_DATABASE_ENCRYPTION_KEY", "CHANGEME")
    config = config_from_env()

    # make assertions about the config
    assert config.CDN_BROKER_DATABASE_URI == "postgresql://cdn-db-uri"
    assert config.DOMAIN_BROKER_DATABASE_URI == "postgresql://alb-db-uri"
    assert config.CDN_DATABASE_ENCRYPTION_KEY is not None
    assert config.DOMAIN_DATABASE_ENCRYPTION_KEY is not None

    raised = None
    try:
        # try to reload modules
        reload()
    except Exception as e:
        # cache the exception, if any
        raised = e
    finally:
        # reset the environment, so we don't mess with other tests
        monkeypatch.delenv("VCAP_APPLICATION")
        monkeypatch.delenv("VCAP_SERVICES")
        monkeypatch.setenv("ENV", "local")
        reload()

    # make an assertion to pass/fail the test
    assert raised is None
