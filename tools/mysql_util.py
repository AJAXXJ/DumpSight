from sqlalchemy import create_engine
from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base
import threading

Base = declarative_base()

class MysqlUtil:

    def __init__(self, config):
        host = config["MYSQL_HOST"]
        port = config["MYSQL_PORT"]
        user = config["MYSQL_USER"]
        password = config["MYSQL_PASSWORD"]
        database = config["MYSQL_DATABASE"]

        db_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"

        self.engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False
        )

        self.Session = scoped_session(sessionmaker(bind=self.engine))
        

    def init_db(self):
        """
        init db
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


def init_mysql_util(config):
    global _mysql_util
    with _mysql_lock:
        if _mysql_util is None:
            _mysql_util = MysqlUtil(config)


def get_mysql_util():
    if _mysql_util is None:
        raise RuntimeError("MySQL util not initialized")
    return _mysql_util