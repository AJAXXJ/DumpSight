from main import app
from sqlalchemy import create_engine
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base
import threading

Base = declarative_base()

class MysqlUtil:

    def __init__(self):
        host = app.config.get("MYSQL_HOST", "localhost")
        port = app.config.get("MYSQL_PORT", 3306)
        user = app.config.get("MYSQL_USER", "root")
        password = app.config.get("MYSQL_PASSWORD", "")
        database = app.config.get("MYSQL_DATABASE", "")

        db_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"

        self.mysql_client = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False
        )

        self.Session = scoped_session(sessionmaker(bind=self.mysql_client))

    def create_tables(self):
        """
        create all ORM table
        """
        Base.metadata.create_all(self.engine)

    def get_session(self):
        """
        get session
        """
        return self.Session()
    
    @contextmanager
    def session_scope(self):
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

_mysql_util = None
_mysql_lock = threading.Lock()

def get_mysql_util() -> MysqlUtil:
    global _mysql_util
    if _mysql_util is None:
        with _mysql_lock:
            if _mysql_util is None:
                _mysql_util = MysqlUtil()
    return _mysql_util