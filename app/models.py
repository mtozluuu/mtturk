from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    crew_assignments: Mapped[list["CrewAssignment"]] = relationship(back_populates="user")
    maintenance_logs: Mapped[list["MaintenanceLog"]] = relationship(back_populates="user")


class Flight(Base):
    __tablename__ = "flights"

    id: Mapped[int] = mapped_column(primary_key=True)
    flight_no: Mapped[str] = mapped_column(String(20), nullable=False)
    flight_date: Mapped[date] = mapped_column(Date, nullable=False)
    departure_airport: Mapped[str] = mapped_column(String(10), nullable=False)
    arrival_airport: Mapped[str] = mapped_column(String(10), nullable=False)
    sched_dep: Mapped[datetime] = mapped_column(nullable=False)
    sched_arr: Mapped[datetime] = mapped_column(nullable=False)
    actual_dep: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    actual_arr: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    crew_assignments: Mapped[list["CrewAssignment"]] = relationship(back_populates="flight")
    maintenance_logs: Mapped[list["MaintenanceLog"]] = relationship(back_populates="flight")


class CrewAssignment(Base):
    __tablename__ = "crew_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    seat: Mapped[str] = mapped_column(String(50), nullable=False)
    start_time: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    flight: Mapped["Flight"] = relationship(back_populates="crew_assignments")
    user: Mapped["User"] = relationship(back_populates="crew_assignments")


class MaintenanceLog(Base):
    __tablename__ = "maintenance_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    logged_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    flight: Mapped["Flight"] = relationship(back_populates="maintenance_logs")
    user: Mapped["User"] = relationship(back_populates="maintenance_logs")
