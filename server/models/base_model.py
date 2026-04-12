from sqlalchemy import TIMESTAMP, Column, text
from server.tools.mysql_util import Base, get_mysql_util


class BaseModel(Base):
    __abstract__ = True

    create_time = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"))
    update_time = Column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP")
    )

    def to_dict(self):
        """将 ORM 对象转换为字典"""
        data = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            data[column.name] = value
        return data

    # -------------------- CRUD --------------------

    @classmethod
    def create(cls, **kwargs):
        with get_mysql_util().session_scope() as session:
            obj = cls(**kwargs)
            session.add(obj)
            session.flush()
            return obj.to_dict()  # ✅ 直接返回 dict

    @classmethod
    def get(cls, **kwargs):
        with get_mysql_util().session_scope() as session:
            obj = session.query(cls).filter_by(**kwargs).first()
            return obj.to_dict() if obj else None

    @classmethod
    def filter(cls, **kwargs):
        with get_mysql_util().session_scope() as session:
            objs = session.query(cls).filter_by(**kwargs).all()
            return [obj.to_dict() for obj in objs]

    @classmethod
    def all(cls):
        with get_mysql_util().session_scope() as session:
            objs = session.query(cls).all()
            return [obj.to_dict() for obj in objs]

    @classmethod
    def delete(cls, **kwargs):
        with get_mysql_util().session_scope() as session:
            obj = session.query(cls).filter_by(**kwargs).first()
            if obj:
                session.delete(obj)
                return True
            return False

    @classmethod
    def update(cls, filters: dict, updates: dict):
        with get_mysql_util().session_scope() as session:
            obj = session.query(cls).filter_by(**filters).first()
            if not obj:
                return False
            for k, v in updates.items():
                setattr(obj, k, v)
            session.flush()  # 提交更新
            return obj.to_dict()  # ✅ 返回更新后的 dict

    @classmethod
    def page(cls, page=1, page_size=10, **filters):
        with get_mysql_util().session_scope() as session:
            query = session.query(cls).filter_by(**filters)
            total = query.count()
            items = query.offset((page - 1) * page_size).limit(page_size).all()
            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": [item.to_dict() for item in items]
            }