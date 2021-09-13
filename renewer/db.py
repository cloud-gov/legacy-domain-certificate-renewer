from contextlib import AbstractContextManager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from renewer.extensions import config
from renewer.cdn_models import CdnBase
from renewer.domain_models import DomainBase

cdn_engine = create_engine(config.CDN_BROKER_DATABASE_URI)
domain_engine = create_engine(config.DOMAIN_BROKER_DATABASE_URI)
Session = sessionmaker(binds={CdnBase: cdn_engine, DomainBase: domain_engine})


def check_connections(
    session_maker=Session, cdn_binding=cdn_engine, domain_binding=domain_engine
):
    session = session_maker()
    session.execute("SELECT 1 FROM certificates", bind=cdn_binding)
    session.execute("SELECT 1 FROM certificates", bind=domain_binding)
    session.close()


class SessionHandler(AbstractContextManager):
    def __enter__(self):
        self.session = Session()
        return self.session

    def __exit__(self, *args, **kwargs):
        self.session.close()
