import json

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
    monkeypatch.setenv("AWS_GOVCLOUD_REGION", "us-gov-west-1")
    monkeypatch.setenv("AWS_GOVCLOUD_ACCESS_KEY_ID", "ASIANOTAREALKEYGOV")
    monkeypatch.setenv("AWS_GOVCLOUD_SECRET_ACCESS_KEY", "NOT_A_REAL_SECRET_KEY_GOV")


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
    assert config.AWS_GOVCLOUD_REGION == "us-gov-west-1"
    assert config.AWS_GOVCLOUD_ACCESS_KEY_ID == "ASIANOTAREALKEYGOV"
    assert config.AWS_GOVCLOUD_SECRET_ACCESS_KEY == "NOT_A_REAL_SECRET_KEY_GOV"
    assert config.REDIS_HOST == "my-redis-hostname"
    assert config.REDIS_PORT == "my-redis-port"
    assert config.REDIS_PASSWORD == "my-redis-password"
