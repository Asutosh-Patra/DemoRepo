
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


# ==================================================
# COMMON
# ==================================================
class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ==================================================
# 1. USERS
# ==================================================
class UserCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(ORMBase):
    id: UUID
    full_name: str
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ==================================================
# 2. PROJECTS
# ==================================================
class ProjectCreate(BaseModel):
    organization_name: str = Field(min_length=1, max_length=150)
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    priority: Literal["Low", "Medium", "High"] = "Medium"
    status: Literal["Draft", "Active", "Completed", "Archived"] = "Draft"
    start_date: date | None = None
    end_date: date | None = None
    created_by: UUID | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date cannot be before start_date")
        return self


class ProjectResponse(ORMBase):
    id: UUID
    organization_name: str
    name: str
    description: str | None
    priority: str
    status: str
    start_date: date | None
    end_date: date | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


# ==================================================
# 3. CONNECTIONS
# ==================================================
class ConnectionCreate(BaseModel):
    project_id: UUID
    name: str = Field(min_length=1, max_length=150)
    connection_role: Literal["source", "target"]
    source_type: str = Field(min_length=1, max_length=50)
    connection_config: dict[str, Any] = Field(default_factory=dict)
    secret_ref: str | None = None


class ConnectionResponse(ORMBase):
    id: UUID
    project_id: UUID
    name: str
    connection_role: str
    source_type: str
    connection_config: dict[str, Any]
    secret_ref: str | None
    status: str
    last_tested_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ==================================================
# 4. PROFILING CONFIGS
# ==================================================
class ProfilingConfigCreate(BaseModel):
    connection_id: UUID
    name: str = Field(min_length=1, max_length=150)
    selected_objects: list[dict[str, Any]] = Field(default_factory=list)
    profiling_options: dict[str, Any] = Field(default_factory=dict)
    created_by: UUID | None = None


class ProfilingConfigResponse(ORMBase):
    id: UUID
    connection_id: UUID
    name: str
    selected_objects: list[dict[str, Any]]
    profiling_options: dict[str, Any]
    is_active: bool
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


# ==================================================
# 5. PROFILING RUNS
# ==================================================
class ProfilingRunResponse(ORMBase):
    id: UUID
    profiling_config_id: UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    row_count: int
    column_count: int
    average_completeness: Decimal
    duplicate_rows: int
    missing_values: int
    error_message: str | None
    created_at: datetime


# ==================================================
# 6. PROFILING RESULTS
# ==================================================
class ProfilingResultResponse(ORMBase):
    id: UUID
    profiling_run_id: UUID
    object_name: str
    column_name: str
    data_type: str | None
    total_count: int
    missing_count: int
    missing_percentage: Decimal
    unique_count: int | None
    duplicate_count: int | None
    min_value: str | None
    max_value: str | None
    finding: str | None
    metrics: dict[str, Any]
    created_at: datetime
