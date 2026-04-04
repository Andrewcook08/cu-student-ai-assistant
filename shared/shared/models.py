from datetime import datetime

from sqlalchemy import (
    JSON,
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
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    dept: Mapped[str] = mapped_column(String(4), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    credits: Mapped[str | None] = mapped_column(String(20))
    description: Mapped[str | None] = mapped_column(Text)
    prerequisites_raw: Mapped[str | None] = mapped_column(Text)
    topic_titles: Mapped[str | None] = mapped_column(Text)
    instruction_mode: Mapped[str | None] = mapped_column(String(50))
    campus: Mapped[str | None] = mapped_column(String(100))
    grading_mode: Mapped[str | None] = mapped_column(String(50))
    session: Mapped[str | None] = mapped_column(String(100))
    dates: Mapped[str | None] = mapped_column(String(50))

    sections: Mapped[list["Section"]] = relationship("Section", back_populates="course")
    attributes: Mapped[list["CourseAttribute"]] = relationship(
        "CourseAttribute", back_populates="course"
    )


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("course_id", "crn"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(Integer, ForeignKey("courses.id"), nullable=False)
    crn: Mapped[str] = mapped_column(String(10), nullable=False)
    section_number: Mapped[str | None] = mapped_column(String(5))
    type: Mapped[str | None] = mapped_column(String(5))
    meets: Mapped[str | None] = mapped_column(String(100))
    instructor: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str | None] = mapped_column(String(20))
    campus: Mapped[str | None] = mapped_column(String(10))
    dates: Mapped[str | None] = mapped_column(String(20))

    course: Mapped["Course"] = relationship("Course", back_populates="sections")


class CourseAttribute(Base):
    __tablename__ = "course_attributes"
    __table_args__ = (UniqueConstraint("course_code", "college", "category"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_code: Mapped[str] = mapped_column(String(10), ForeignKey("courses.code"), nullable=False)
    college: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)

    course: Mapped["Course"] = relationship("Course", back_populates="attributes")


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    type: Mapped[str | None] = mapped_column(String(50))
    total_credits: Mapped[str | None] = mapped_column(String(10))

    requirements: Mapped[list["Requirement"]] = relationship(
        "Requirement", back_populates="program"
    )


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(Integer, ForeignKey("programs.id"), nullable=False)
    sort_order: Mapped[int | None] = mapped_column(Integer)
    requirement_type: Mapped[str | None] = mapped_column(String(20))
    course_code: Mapped[str | None] = mapped_column(String(60))
    name: Mapped[str | None] = mapped_column(Text)
    credits: Mapped[str | None] = mapped_column(String(10))
    raw_id: Mapped[str | None] = mapped_column(Text)

    program: Mapped["Program"] = relationship("Program", back_populates="requirements")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    program_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("programs.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    completed_courses: Mapped[list["CompletedCourse"]] = relationship(
        "CompletedCourse", back_populates="user"
    )
    decisions: Mapped[list["StudentDecision"]] = relationship(
        "StudentDecision", back_populates="user"
    )


class CompletedCourse(Base):
    __tablename__ = "completed_courses"
    __table_args__ = (UniqueConstraint("user_id", "course_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    course_code: Mapped[str] = mapped_column(String(10), nullable=False)
    grade: Mapped[str | None] = mapped_column(String(5))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="completed_courses")


class StudentDecision(Base):
    __tablename__ = "student_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    course_code: Mapped[str] = mapped_column(String(10), nullable=False)
    decision_type: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="decisions")


class ToolAuditLog(Base):
    __tablename__ = "tool_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    session_id: Mapped[str | None] = mapped_column(String(100))
    tool_name: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[dict | None] = mapped_column(JSON)
    result_summary: Mapped[str | None] = mapped_column(Text)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
