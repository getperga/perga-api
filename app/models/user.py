from sqlalchemy import Column, String, Boolean, true, false
from sqlalchemy.orm import relationship

from app.const.planner import WeekStartDay
from app.models.base import BaseModel


__all__ = (
    'User',
)


class User(BaseModel):
    __tablename__ = "users"

    username = Column(String(length=64), unique=True, index=True, nullable=False)
    email = Column(String(length=64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(length=128), nullable=False)
    is_active = Column(Boolean, default=True, server_default=true(), nullable=False)

    # external auth
    google_id = Column(String(length=128), unique=True, index=True, nullable=True)

    # Preferences
    week_start_day = Column(String(length=32), default=WeekStartDay.MONDAY, nullable=False)
    merge_weekends = Column(Boolean, default=False, server_default=false(), nullable=False)

    # Relationships
    planner_agendas = relationship("PlannerAgenda", back_populates="user")
    planner_day_items = relationship("PlannerDayItem", back_populates="user")
    planner_agenda_items = relationship("PlannerAgendaItem", back_populates="user")
    notes = relationship("Note", back_populates="user")
    notes_folders = relationship("NotesFolder", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, email={self.email}, is_active={self.is_active})>"
