import pytest
from renewer.db import session_handler, cdn_engine, domain_engine


@pytest.fixture
def clean_db():
    with session_handler() as session:
        session.execute("TRUNCATE TABLE user_data", bind=cdn_engine)
        session.execute("TRUNCATE TABLE routes", bind=cdn_engine)
        session.execute("TRUNCATE TABLE certificates", bind=cdn_engine)
        session.execute("TRUNCATE TABLE user_data", bind=domain_engine)
        session.execute("TRUNCATE TABLE routes", bind=domain_engine)
        session.execute("TRUNCATE TABLE certificates", bind=domain_engine)
        session.execute("TRUNCATE TABLE alb_proxies", bind=domain_engine)
        session.commit()
        session.close()
        yield session
        session.execute("TRUNCATE TABLE user_data", bind=cdn_engine)
        session.execute("TRUNCATE TABLE routes", bind=cdn_engine)
        session.execute("TRUNCATE TABLE certificates", bind=cdn_engine)
        session.execute("TRUNCATE TABLE user_data", bind=domain_engine)
        session.execute("TRUNCATE TABLE routes", bind=domain_engine)
        session.execute("TRUNCATE TABLE certificates", bind=domain_engine)
        session.execute("TRUNCATE TABLE alb_proxies", bind=domain_engine)
        session.commit()
        session.close()

