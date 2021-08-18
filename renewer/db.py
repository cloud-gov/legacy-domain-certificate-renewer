from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from renewer.extensions import config
from renewer.models import CdnBase, DomainBase

cdn_engine = create_engine(config.CDN_BROKER_DATABASE_URI)
domain_engine = create_engine(config.DOMAIN_BROKER_DATABASE_URI)
Session = sessionmaker(binds={CdnBase: cdn_engine, DomainBase: domain_engine})


@contextmanager
def session_handler():
    session = Session()
    try:
        yield session
    finally:
        session.close()


def check_connections(
    session_maker=Session, cdn_binding=cdn_engine, domain_binding=domain_engine
):
    session = session_maker()
    session.execute("SELECT 1 FROM certificates", bind=cdn_binding)
    session.execute("SELECT 1 FROM certificates", bind=domain_binding)
    session.close()
