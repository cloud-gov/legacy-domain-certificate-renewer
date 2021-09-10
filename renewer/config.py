import re

from cfenv import AppEnv
from environs import Env


def config_from_env():
    environments = {
        "local": LocalConfig,
        "development": AppConfig,
        "staging": AppConfig,
        "production": AppConfig,
        "upgrade-schema": UpgradeSchemaConfig,
    }
    env = Env()
    return environments[env("ENV")]()


def normalize_db_url(url):
    # sqlalchemy no longer lets us use postgres://
    # it requires postgresql://
    if url.split(":")[0] == "postgres":
        url = url.replace("postgres:", "postgresql:", 1)
    return url


class Config:
    def __init__(self):
        self.env_parser = Env()
        self.cf_env_parser = AppEnv()
        self.ENV = self.env_parser("ENV")
        self.RENEW_BEFORE_DAYS = 30


class AppConfig(Config):
    def __init__(self):
        super().__init__()
        cdn_db = self.cf_env_parser.get_service(name="rds-cdn-broker")
        self.CDN_BROKER_DATABASE_URI = normalize_db_url(cdn_db.credentials["uri"])
        alb_db = self.cf_env_parser.get_service(name="rds-domain-broker")
        self.DOMAIN_BROKER_DATABASE_URI = normalize_db_url(alb_db.credentials["uri"])
        self.AWS_GOVCLOUD_REGION = self.env_parser("AWS_GOVCLOUD_REGION")
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = self.env_parser("AWS_GOVCLOUD_ACCESS_KEY_ID")
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = self.env_parser(
            "AWS_GOVCLOUD_SECRET_ACCESS_KEY"
        )
        redis = self.cf_env_parser.get_service(label=re.compile("redis.*"))

        if not redis:
            raise MissingRedisError

        self.ACME_DIRECTORY = "https://acme-v02.api.letsencrypt.org/directory"
        self.REDIS_HOST = redis.credentials["host"]
        self.REDIS_PORT = redis.credentials["port"]
        self.REDIS_PASSWORD = redis.credentials["password"]
        self.REDIS_SSL = True
        self.LETS_ENCRYPT_REGISTRATION_EMAIL = self.env_parser(
            "LETS_ENCRYPT_REGISTRATION_EMAIL"
        )
        self.DATABASE_ENCRYPTION_KEY = self.env_parser("DATABASE_ENCRYPTION_KEY")


class LocalConfig(Config):
    def __init__(self):
        super().__init__()
        self.TESTING = True
        self.DEBUG = True
        self.CDN_BROKER_DATABASE_URI = "postgresql://localhost/local-development-cdn"
        self.DOMAIN_BROKER_DATABASE_URI = (
            "postgresql://localhost/local-development-domain"
        )
        self.AWS_GOVCLOUD_REGION = "us-gov-west-1"
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = "ASIANOTAREALKEYGOV"
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = "THIS_IS_A_FAKE_KEY_GOV"

        self.REDIS_SSL = False
        self.REDIS_HOST = "localhost"
        self.REDIS_PORT = "6379"
        self.REDIS_PASSWORD = "CHANGEME"

        self.ACME_DIRECTORY = "https://localhost:14000/dir"
        self.LETS_ENCRYPT_REGISTRATION_EMAIL = "ops@example.com"
        self.DATABASE_ENCRYPTION_KEY = "feedabee"


class UpgradeSchemaConfig(Config):
    def __init__(self):
        super().__init__()
        cdn_db = self.cf_env_parser.get_service(name="rds-cdn-broker")
        self.CDN_BROKER_DATABASE_URI = normalize_db_url(cdn_db.credentials["uri"])
        alb_db = self.cf_env_parser.get_service(name="rds-domain-broker")
        self.DOMAIN_BROKER_DATABASE_URI = normalize_db_url(alb_db.credentials["uri"])
        # silly workaround - we don't have an AWS region, but the config blows up
        # if it's none. Set it to an invalid string, so we can configure but not use boto clients
        self.AWS_GOVCLOUD_REGION = "none"
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = None
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = None
        self.DATABASE_ENCRYPTION_KEY = self.env_parser("DATABASE_ENCRYPTION_KEY")
