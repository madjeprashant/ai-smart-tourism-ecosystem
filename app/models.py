from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=True
    )

    title: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(50))
    amount: Mapped[float] = mapped_column(Float)
    destination: Mapped[str] = mapped_column(String(120), default="General")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author: Mapped[str] = mapped_column(String(80))
    destination: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    media_items: Mapped[list | None] = mapped_column(JSON, nullable=True)
    approved: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[int | None] = mapped_column(
    ForeignKey("users.id"),
    nullable=True
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    full_name: Mapped[str] = mapped_column(String(100))

    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)

    email: Mapped[str] = mapped_column(String(150), unique=True)

    phone: Mapped[str] = mapped_column(String(15), unique=True)

    password: Mapped[str] = mapped_column(String(255))

    role: Mapped[str] = mapped_column(String(20), default="traveler")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    destination: Mapped[str] = mapped_column(String(120))

    days: Mapped[int] = mapped_column(Integer)

    budget: Mapped[float] = mapped_column(Float)

    interests: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    itinerary: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
