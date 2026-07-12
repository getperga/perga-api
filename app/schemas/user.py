from pydantic import BaseModel, computed_field, Field

from app.const.planner import WeekStartDay


class UserSchema(BaseModel):
    id: int
    username: str
    email: str
    week_start_day: WeekStartDay
    merge_weekends: bool
    google_id: str | None = None
    hashed_password: str | None = Field(None, exclude=True)

    @computed_field
    @property
    def has_password(self) -> bool:
        return bool(self.hashed_password)

    class Config:
        from_attributes = True

class UserCreateSchema(BaseModel):
    username: str
    email: str
    password: str
    week_start_day: WeekStartDay = WeekStartDay.MONDAY
    merge_weekends: bool = False


class UserUpdateSchema(BaseModel):
    username: str | None = None
    email: str | None = None
    week_start_day: WeekStartDay | None = None
    merge_weekends: bool | None = None


class PasswordChangeSchema(BaseModel):
    current_password: str | None = None  # can be None in case of google auth signup
    new_password: str
