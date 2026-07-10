"""SQLAlchemy persistence model contract; API MVP uses MemoryStore until migrations are run."""
from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrganizationMember(Base):
    __tablename__ = "organization_members"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(32), default="viewer")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    location_country: Mapped[str] = mapped_column(String(120), default="")
    location_city: Mapped[str] = mapped_column(String(120), default="")
    address_text: Mapped[str] = mapped_column(Text, default="")
    building_type: Mapped[str] = mapped_column(String(120), default="Other")
    gross_floor_area: Mapped[float | None] = mapped_column(Float, nullable=True)
    leed_version: Mapped[str] = mapped_column(String(16))
    rating_family: Mapped[str] = mapped_column(String(16))
    adaptation: Mapped[str] = mapped_column(String(64))
    target_certification: Mapped[str] = mapped_column(String(32))
    current_phase: Mapped[str] = mapped_column(String(48))
    project_boundary_description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CreditRegistry(Base):
    __tablename__ = "credit_registries"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    leed_version: Mapped[str] = mapped_column(String(16))
    rating_family: Mapped[str] = mapped_column(String(16))
    adaptation: Mapped[str] = mapped_column(String(64))
    registry_path: Mapped[str] = mapped_column(String(500))
    registry_hash: Mapped[str] = mapped_column(String(128))
    loaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Credit(Base):
    __tablename__ = "credits"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    leed_version: Mapped[str] = mapped_column(String(16))
    rating_family: Mapped[str] = mapped_column(String(16))
    adaptation: Mapped[str] = mapped_column(String(64))
    credit_id: Mapped[str] = mapped_column(String(80))
    credit_code: Mapped[str] = mapped_column(String(80))
    credit_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(120))
    is_prerequisite: Mapped[bool] = mapped_column(default=False)
    max_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    module_type: Mapped[str] = mapped_column(String(80))
    registry_path: Mapped[str] = mapped_column(String(500))


class ProjectCredit(Base):
    __tablename__ = "project_credits"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    credit_id: Mapped[str] = mapped_column(ForeignKey("credits.id"))
    status: Mapped[str] = mapped_column(String(32), default="not_started")
    target_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    awarded_points: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32), default="needs_official_source")
    responsible_discipline: Mapped[str] = mapped_column(String(80), default="leed_consultant")
    notes: Mapped[str] = mapped_column(Text, default="")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(80))
    phase: Mapped[str] = mapped_column(String(48))
    discipline: Mapped[str] = mapped_column(String(80))
    related_credit_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    processing_status: Mapped[str] = mapped_column(String(32), default="uploaded")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    chunk_text: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    section_heading: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
