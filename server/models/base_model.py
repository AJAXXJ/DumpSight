from sqlalchemy import TIMESTAMP, Column, text
from server.tools import mysql_util
from server.tools.mysql_util import Base


class BaseModel(Base):
    """
    
    """
    __abstract__ = True

    create_time = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"))
    update_time = Column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP")
    )

    def to_dict(self):
        data = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            data[column.name] = value
        return data


    @classmethod
    def create(cls, **kwargs):
        with mysql_util.session_scope() as session:
            obj = cls(**kwargs)
            session.add(obj)
            session.flush()
            return obj


    @classmethod
    def get(cls, **kwargs):
        with mysql_util.session_scope() as session:
            return session.query(cls).filter_by(**kwargs).first()


    @classmethod
    def filter(cls, **kwargs):
        with mysql_util.session_scope() as session:
            return session.query(cls).filter_by(**kwargs).all()


    @classmethod
    def all(cls):
        with mysql_util.session_scope() as session:
            return session.query(cls).all()


    @classmethod
    def delete(cls, **kwargs):
        with mysql_util.session_scope() as session:
            obj = session.query(cls).filter_by(**kwargs).first()
            if obj:
                session.delete(obj)
                return True
            return False


    @classmethod
    def update(cls, filters: dict, updates: dict):
        with mysql_util.session_scope() as session:
            obj = session.query(cls).filter_by(**filters).first()
            if not obj:
                return False
            for k, v in updates.items():
                setattr(obj, k, v)
            return True


    @classmethod
    def page(cls, page=1, page_size=10, **filters):
        with mysql_util.session_scope() as session:
            query = session.query(cls).filter_by(**filters)

            total = query.count()
            items = query.offset((page - 1) * page_size).limit(page_size).all()

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [item.to_dict() for item in items]
            }