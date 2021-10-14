from contextlib import AbstractContextManager
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from renewer.json_log import json_log
from renewer.extensions import config
from renewer.models.cdn import CdnModel
from renewer.models.domain import DomainModel

logger = logging.getLogger(__name__)

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
        json_log(logger.debug, {"message": "opening db session"})
        self.session_registry = scoped_session(Session)
        session = self.session_registry()
        return session

    def __exit__(self, *args, **kwargs):
        json_log(logger.debug, {"message": "closing db session"})
        self.session_registry.remove()
