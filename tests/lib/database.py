import pytest
from renewer.db import SessionHandler, cdn_engine, domain_engine


@pytest.fixture(scope="function")
def clean_db():
    with SessionHandler() as session:
        session.execute("TRUNCATE TABLE user_data", bind=cdn_engine)
        session.execute("TRUNCATE TABLE routes CASCADE", bind=cdn_engine)
        session.execute("TRUNCATE TABLE operations CASCADE", bind=cdn_engine)
        session.execute("TRUNCATE TABLE certificates CASCADE", bind=cdn_engine)
        session.execute("TRUNCATE TABLE challenges CASCADE", bind=cdn_engine)
        session.execute("TRUNCATE TABLE acme_user_v2 CASCADE", bind=cdn_engine)
        session.execute("TRUNCATE TABLE user_data", bind=domain_engine)
        session.execute("TRUNCATE TABLE routes CASCADE", bind=domain_engine)
        session.execute("TRUNCATE TABLE operations CASCADE", bind=domain_engine)
        session.execute("TRUNCATE TABLE certificates CASCADE", bind=domain_engine)
        session.execute("TRUNCATE TABLE challenges CASCADE", bind=domain_engine)
        session.execute("TRUNCATE TABLE acme_user_v2 CASCADE", bind=domain_engine)
        session.execute("TRUNCATE TABLE alb_proxies", bind=domain_engine)
        session.commit()
        session.close()
        yield session
        session.execute("TRUNCATE TABLE user_data", bind=cdn_engine)
        session.execute("TRUNCATE TABLE routes CASCADE", bind=cdn_engine)
        session.execute("TRUNCATE TABLE operations CASCADE", bind=cdn_engine)
        session.execute("TRUNCATE TABLE certificates CASCADE", bind=cdn_engine)
        session.execute("TRUNCATE TABLE challenges CASCADE", bind=cdn_engine)
        session.execute("TRUNCATE TABLE acme_user_v2 CASCADE", bind=cdn_engine)
        session.execute("TRUNCATE TABLE user_data", bind=domain_engine)
        session.execute("TRUNCATE TABLE routes CASCADE", bind=domain_engine)
        session.execute("TRUNCATE TABLE operations CASCADE", bind=domain_engine)
        session.execute("TRUNCATE TABLE certificates CASCADE", bind=domain_engine)
        session.execute("TRUNCATE TABLE challenges CASCADE", bind=domain_engine)
        session.execute("TRUNCATE TABLE acme_user_v2 CASCADE", bind=domain_engine)
        session.execute("TRUNCATE TABLE alb_proxies", bind=domain_engine)
        session.commit()
        session.close()
