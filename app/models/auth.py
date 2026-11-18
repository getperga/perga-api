from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, false, true
from sqlalchemy.orm import relationship

from app.const.planner import WeekStartDay
from app.core.database import Base
from app.models.base import BaseModel


__all__ = (
    'AuthSession',
    'User',
)


class User(BaseModel):
    __tablename__ = "users"

    username: str = Column(String(length=64), unique=True, index=True, nullable=False)
    email: str = Column(String(length=64), unique=True, index=True, nullable=False)
    hashed_password: str | None = Column(String(length=128), nullable=True)
    is_active: bool = Column(Boolean, default=True, server_default=true(), nullable=False)

    # the PostgreSQL trigger created by Alembic revision 0014_auth_sessions increments this version
    # when the password or account status changes; sessions issued with an earlier version become invalid.
    auth_epoch = Column(BigInteger, server_default='0', nullable=False)

    # external auth
    google_id: str | None = Column(String(length=128), unique=True, index=True, nullable=True)

    # Preferences
    week_start_day: str = Column(String(length=32), default=WeekStartDay.MONDAY, nullable=False)
    merge_weekends: bool = Column(Boolean, default=False, server_default=false(), nullable=False)

    # Relationships
    planner_agendas = relationship("PlannerAgenda", back_populates="user")
    planner_day_items = relationship("PlannerDayItem", back_populates="user")
    planner_agenda_items = relationship("PlannerAgendaItem", back_populates="user")
    notes = relationship("Note", back_populates="user")
    notes_folders = relationship("NotesFolder", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email}, is_active={self.is_active})>"


class AuthSession(Base):
    __tablename__ = 'auth_sessions'

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    auth_epoch = Column(BigInteger, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
