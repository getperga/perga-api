import logging
from collections.abc import Iterable
from typing import Generic, TypeVar

from sqlalchemy import SQLColumnExpression, select
from sqlalchemy.engine import ScalarResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql.elements import ColumnElement

from app.models.base import BaseModel


logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
ScalarT = TypeVar('ScalarT')


class BaseService(Generic[T]):
    model: type[T]

    @classmethod
    def get_base_query(cls, db: Session, user_id: int | None = None) -> Query[T]:
        """
        Returns SQLAlchemy Query with non deleted objects.
        Also accepts optional user_id arg: all models except User are bound to specific user and can be filtered.
        """
        query = db.query(cls.model).filter(cls.model.is_deleted.is_(False))
        if user_id is not None and getattr(cls.model, 'user_id'):
            query = query.filter(cls.model.user_id == user_id)
        return query

    @classmethod
    def get_scalars_for_single_column(
        cls,
        db: Session,
        column: SQLColumnExpression[ScalarT],
        filters: Iterable[ColumnElement[bool]] = (),
    ) -> ScalarResult[ScalarT]:
        """ Returns ScalarResult for provided single column from non-deleted objects """
        query = select(column).where(
            cls.model.is_deleted.is_(False),
            *filters,
        )
        return db.scalars(query)

    @classmethod
    def get_or_create(cls, db: Session, defaults: dict | None = None, **kwargs) -> tuple[T, bool]:
        instance = cls.get_base_query(db).filter_by(**kwargs).first()
        if instance:
            return instance, False

        params = {k: v for k, v in kwargs.items()}
        params.update(defaults or {})
        instance = cls.model(**params)
        db.add(instance)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            instance = cls.get_base_query(db).filter_by(**kwargs).first()
            return instance, False

        db.refresh(instance)
        return instance, True
