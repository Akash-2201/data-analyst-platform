"""
SQLAlchemy ORM models for Dataset, PipelineStep, and Setting.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.database import Base


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    filename = Column(String, nullable=False)
    raw_storage_path = Column(String, nullable=False)
    profile_json = Column(JSON, nullable=False)
    cleaned_storage_path = Column(String, nullable=True)
    cleaned_profile_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    pipeline_steps = relationship(
        "PipelineStep",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="PipelineStep.order",
    )


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    order = Column(Integer, nullable=False)
    action = Column(String, nullable=False)
    params = Column(JSON, nullable=True)
    description = Column(String, nullable=False)
    severity = Column(String, nullable=False)

    dataset = relationship("Dataset", back_populates="pipeline_steps")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
