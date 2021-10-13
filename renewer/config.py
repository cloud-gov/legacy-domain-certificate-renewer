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
        self.ACME_POLL_TIMEOUT_IN_SECONDS = self.env_parser(
            "ACME_POLL_TIMEOUT_IN_SECONDS", 90
        )


class AppConfig(Config):
    def __init__(self):
        super().__init__()
        cdn_db = self.cf_env_parser.get_service(name="rds-cdn-broker")
        self.CDN_BROKER_DATABASE_URI = normalize_db_url(cdn_db.credentials["uri"])
        alb_db = self.cf_env_parser.get_service(name="rds-domain-broker")
        self.DOMAIN_BROKER_DATABASE_URI = normalize_db_url(alb_db.credentials["uri"])
        self.AWS_COMMERCIAL_REGION = self.env_parser("AWS_COMMERCIAL_REGION")
        self.AWS_COMMERCIAL_ACCESS_KEY_ID = self.env_parser(
            "AWS_COMMERCIAL_ACCESS_KEY_ID"
        )
        self.AWS_COMMERCIAL_SECRET_ACCESS_KEY = self.env_parser(
            "AWS_COMMERCIAL_SECRET_ACCESS_KEY"
        )
        self.COMMERCIAL_BUCKET = self.env_parser("COMMERCIAL_BUCKET")
        self.COMMERCIAL_IAM_PREFIX = self.env_parser("COMMERCIAL_IAM_PREFIX")
        self.AWS_GOVCLOUD_REGION = self.env_parser("AWS_GOVCLOUD_REGION")
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = self.env_parser("AWS_GOVCLOUD_ACCESS_KEY_ID")
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = self.env_parser(
            "AWS_GOVCLOUD_SECRET_ACCESS_KEY"
        )
        # how long to wait between polling when using an boto3 waiter
        # I _think_ we're best leaving this low and relying on huey retries so the worker(s) can think about other things
        self.AWS_POLL_WAIT_TIME_IN_SECONDS = self.env_parser.int(
            "AWS_POLL_WAIT_TIME_IN_SECONDS"
        )
        # how many times to poll when using a boto3 waiter
        # I _think_ we're best leaving this low and relying on huey retries so the worker(s) can think about other things
        self.AWS_POLL_MAX_ATTEMPTS = self.env_parser.int("AWS_POLL_MAX_ATTEMPTS")
        self.GOVCLOUD_BUCKET = self.env_parser("GOVCLOUD_BUCKET")
        self.GOVCLOUD_IAM_PREFIX = self.env_parser("GOVCLOUD_IAM_PREFIX")

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
        self.CDN_DATABASE_ENCRYPTION_KEY = self.env_parser(
            "CDN_DATABASE_ENCRYPTION_KEY"
        )
        self.DOMAIN_DATABASE_ENCRYPTION_KEY = self.env_parser(
            "DOMAIN_DATABASE_ENCRYPTION_KEY"
        )
        self.S3_PROPAGATION_TIME = self.env_parser.int("S3_PROPAGATION_TIME", 10)
        self.IAM_PROPAGATION_TIME = self.env_parser.int("IAM_PROPAGATION_TIME", 10)
        self.RUN_RENEWALS = self.env_parser.bool("RUN_RENEWALS", False)
        self.RUN_BACKPORTS = self.env_parser.bool("RUN_BACKPORTS", False)
        self.MAX_ROUTES_PER_USER = 50
        self.SMTP_TLS = self.env_parser.bool("SMTP_TLS")
        self.SMTP_CERT = self.env_parser("SMTP_CERT", None)
        self.SMTP_HOST = self.env_parser("SMTP_HOST")
        self.SMTP_PORT = self.env_parser("SMTP_PORT")
        self.SMTP_USER = self.env_parser("SMTP_USER")
        self.SMTP_PASS = self.env_parser("SMTP_PASS")
        self.SMTP_TO = self.env_parser("SMTP_TO")


class LocalConfig(Config):
    def __init__(self):
        super().__init__()
        self.TESTING = True
        self.DEBUG = True
        self.CDN_BROKER_DATABASE_URI = "postgresql://localhost/local-development-cdn"
        self.DOMAIN_BROKER_DATABASE_URI = (
            "postgresql://localhost/local-development-domain"
        )
        self.AWS_COMMERCIAL_REGION = "us-west-1"
        self.AWS_COMMERCIAL_ACCESS_KEY_ID = "ASIANOTAREALKEY"
        self.AWS_COMMERCIAL_SECRET_ACCESS_KEY = "THIS_IS_A_FAKE_KEY"
        self.COMMERCIAL_BUCKET = "fake-commercial-bucket"
        self.COMMERCIAL_IAM_PREFIX = "/cloudfront/test/"
        self.AWS_GOVCLOUD_REGION = "us-gov-west-1"
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = "ASIANOTAREALKEYGOV"
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = "THIS_IS_A_FAKE_KEY_GOV"
        self.AWS_POLL_WAIT_TIME_IN_SECONDS = 0
        self.AWS_POLL_MAX_ATTEMPTS = 3
        self.GOVCLOUD_BUCKET = "fake-govcloud-bucket"
        self.GOVCLOUD_IAM_PREFIX = "/alb/test/"

        self.REDIS_SSL = False
        self.REDIS_HOST = "localhost"
        self.REDIS_PORT = "6379"
        self.REDIS_PASSWORD = "CHANGEME"

        self.ACME_DIRECTORY = "https://localhost:14000/dir"
        self.LETS_ENCRYPT_REGISTRATION_EMAIL = "ops@example.com"
        self.DOMAIN_DATABASE_ENCRYPTION_KEY = "feedabee"
        self.CDN_DATABASE_ENCRYPTION_KEY = "changeme"
        self.S3_PROPAGATION_TIME = 0
        self.IAM_PROPAGATION_TIME = 0
        self.RUN_RENEWALS = True
        self.RUN_BACKPORTS = True
        self.MAX_ROUTES_PER_USER = 3

        self.SMTP_HOST = "localhost"
        self.SMTP_PORT = 1025

        # when testing, this goes to a fake smtp server that only prints stuff,
        # so example.com is a safe host
        self.SMTP_TO = "doesnt-matter@example.com"
        self.SMTP_FROM = "no-reply@example.com"
        self.SMTP_TLS = False
        self.SMTP_USER = None
        self.SMTP_PASS = None
        self.RUN_CRON = True


class UpgradeSchemaConfig(Config):
    def __init__(self):
        super().__init__()
        cdn_db = self.cf_env_parser.get_service(name="rds-cdn-broker")
        self.CDN_BROKER_DATABASE_URI = normalize_db_url(cdn_db.credentials["uri"])
        alb_db = self.cf_env_parser.get_service(name="rds-domain-broker")
        self.DOMAIN_BROKER_DATABASE_URI = normalize_db_url(alb_db.credentials["uri"])
        # silly workaround - we don't have an AWS region, but the config blows up
        # if it's none. Set it to an invalid string, so we can configure but not use boto clients
        self.AWS_COMMERCIAL_REGION = "none"
        self.AWS_COMMERCIAL_ACCESS_KEY_ID = None
        self.AWS_COMMERCIAL_SECRET_ACCESS_KEY = None
        self.AWS_GOVCLOUD_REGION = "none"
        self.AWS_GOVCLOUD_ACCESS_KEY_ID = None
        self.AWS_GOVCLOUD_SECRET_ACCESS_KEY = None
        self.CDN_DATABASE_ENCRYPTION_KEY = self.env_parser(
            "CDN_DATABASE_ENCRYPTION_KEY"
        )
        self.DOMAIN_DATABASE_ENCRYPTION_KEY = self.env_parser(
            "DOMAIN_DATABASE_ENCRYPTION_KEY"
        )
