from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    credits: Mapped[int | None] = mapped_column(Integer)
    subject: Mapped[str | None] = mapped_column(String(10))
    topic_titles: Mapped[str | None] = mapped_column(Text)  # pipe-delimited variant titles

    sections: Mapped[list["Section"]] = relationship("Section", back_populates="course")
    attributes: Mapped[list["CourseAttribute"]] = relationship(
        "CourseAttribute", back_populates="course"
    )


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("course_id", "crn"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id"), nullable=False)
    crn: Mapped[str] = mapped_column(String(20), nullable=False)
    semester: Mapped[str | None] = mapped_column(String(20))
    instructor: Mapped[str | None] = mapped_column(String(255))
    days: Mapped[str | None] = mapped_column(String(20))
    time_start: Mapped[str | None] = mapped_column(String(10))
    time_end: Mapped[str | None] = mapped_column(String(10))
    location: Mapped[str | None] = mapped_column(String(100))
    seats_total: Mapped[int | None] = mapped_column(Integer)
    seats_available: Mapped[int | None] = mapped_column(Integer)

    course: Mapped["Course"] = relationship("Course", back_populates="sections")


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    degree_type: Mapped[str | None] = mapped_column(String(50))  # BS, MS, PhD, etc.
    department: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)

    requirements: Mapped[list["Requirement"]] = relationship(
        "Requirement", back_populates="program"
    )


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(Integer, ForeignKey("programs.id"), nullable=False)
    requirement_type: Mapped[str | None] = mapped_column(String(50))  # core, elective, etc.
    course_code: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    credits_required: Mapped[int | None] = mapped_column(Integer)

    program: Mapped["Program"] = relationship("Program", back_populates="requirements")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    major: Mapped[str | None] = mapped_column(String(100))
    year: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    completed_courses: Mapped[list["CompletedCourse"]] = relationship(
        "CompletedCourse", back_populates="user"
    )
    decisions: Mapped[list["StudentDecision"]] = relationship(
        "StudentDecision", back_populates="user"
    )


class CompletedCourse(Base):
    __tablename__ = "completed_courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    course_code: Mapped[str] = mapped_column(String(20), nullable=False)
    grade: Mapped[str | None] = mapped_column(String(5))
    semester: Mapped[str | None] = mapped_column(String(20))

    user: Mapped["User"] = relationship("User", back_populates="completed_courses")


class StudentDecision(Base):
    __tablename__ = "student_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    course_code: Mapped[str] = mapped_column(String(20), nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)  # interested, planning, etc.
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="decisions")


class ToolAuditLog(Base):
    __tablename__ = "tool_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CourseAttribute(Base):
    __tablename__ = "course_attributes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id"), nullable=False)
    attribute: Mapped[str] = mapped_column(String(100), nullable=False)

    course: Mapped["Course"] = relationship("Course", back_populates="attributes")
