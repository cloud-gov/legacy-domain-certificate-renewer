from contextlib import AbstractContextManager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from renewer.extensions import config
from renewer.models.cdn import CdnModel
from renewer.models.domain import DomainModel

cdn_engine = create_engine(config.CDN_BROKER_DATABASE_URI)
domain_engine = create_engine(config.DOMAIN_BROKER_DATABASE_URI)
Session = sessionmaker(binds={CdnModel: cdn_engine, DomainModel: domain_engine})


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
