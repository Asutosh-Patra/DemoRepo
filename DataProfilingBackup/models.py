from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    BigInteger,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    TIMESTAMP,
    text,
    func,
    Column,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from database import Base


# ==================================================
# 1. USERS
# ==================================================
class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    full_name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    projects = relationship(
        "Project", back_populates="created_by_user", passive_deletes=True
    )
    profiling_configs = relationship(
        "ProfilingConfig", back_populates="creator", passive_deletes=True
    )


# ==================================================
# 2. PROJECTS
# ==================================================
class Project(Base):
    __tablename__ = "projects"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    organization_name = Column(String(150), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    priority = Column(String(20), nullable=False, server_default=text("'Medium'"))
    status = Column(String(20), nullable=False, server_default=text("'Draft'"))
    start_date = Column(Date)
    end_date = Column(Date)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "priority IN ('Low', 'Medium', 'High')",
            name="chk_projects_priority",
        ),
        CheckConstraint(
            "status IN ('Draft', 'Active', 'Completed', 'Archived')",
            name="chk_projects_status",
        ),
        CheckConstraint(
            "start_date IS NULL OR end_date IS NULL OR end_date >= start_date",
            name="chk_projects_dates",
        ),
        UniqueConstraint(
            "organization_name",
            "name",
            name="uq_project_name_per_organization",
        ),
        Index("idx_projects_created_by", "created_by"),
    )

    created_by_user = relationship("User", back_populates="projects")
    connection = relationship(
        "Connection",
        back_populates="project",
        uselist=False,
        passive_deletes=True,
    )


# ==================================================
# 3. CONNECTIONS
# ==================================================
class Connection(Base):
    __tablename__ = "connections"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    name = Column(String(150), nullable=False)
    connection_role = Column(String(20), nullable=False)
    source_type = Column(String(50), nullable=False)
    connection_config = Column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    secret_ref = Column(String(255))
    status = Column(String(20), nullable=False, server_default=text("'not_tested'"))
    last_tested_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "connection_role IN ('source', 'target')",
            name="chk_connection_role",
        ),
        CheckConstraint(
            "status IN ('not_tested', 'connected', 'failed')",
            name="chk_connection_status",
        ),
    )

    project = relationship("Project", back_populates="connection")
    profiling_configs = relationship(
        "ProfilingConfig", back_populates="connection", passive_deletes=True
    )


# ==================================================
# 4. PROFILING CONFIGS
# ==================================================
class ProfilingConfig(Base):
    __tablename__ = "profiling_configs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(150), nullable=False)
    selected_objects = Column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    profiling_options = Column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_profiling_configs_connection_id", "connection_id"),
        Index("idx_profiling_configs_created_by", "created_by"),
    )

    connection = relationship("Connection", back_populates="profiling_configs")
    creator = relationship("User", back_populates="profiling_configs")
    runs = relationship(
        "ProfilingRun", back_populates="profiling_config", passive_deletes=True
    )


# ==================================================
# 5. PROFILING RUNS
# ==================================================
class ProfilingRun(Base):
    __tablename__ = "profiling_runs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    profiling_config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("profiling_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(String(20), nullable=False, server_default=text("'queued'"))
    started_at = Column(TIMESTAMP(timezone=True))
    completed_at = Column(TIMESTAMP(timezone=True))
    row_count = Column(BigInteger, nullable=False, server_default=text("0"))
    column_count = Column(Integer, nullable=False, server_default=text("0"))
    average_completeness = Column(
        Numeric(5, 2), nullable=False, server_default=text("0.00")
    )
    duplicate_rows = Column(BigInteger, nullable=False, server_default=text("0"))
    missing_values = Column(BigInteger, nullable=False, server_default=text("0"))
    error_message = Column(Text)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="chk_profiling_run_status",
        ),
        CheckConstraint(
            "row_count >= 0 AND column_count >= 0 "
            "AND duplicate_rows >= 0 AND missing_values >= 0",
            name="chk_profiling_run_counts",
        ),
        CheckConstraint(
            "average_completeness BETWEEN 0 AND 100",
            name="chk_average_completeness",
        ),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NULL "
            "OR completed_at >= started_at",
            name="chk_profiling_run_times",
        ),
        Index("idx_profiling_runs_config_id", "profiling_config_id"),
        Index("idx_profiling_runs_status", "status"),
    )

    profiling_config = relationship("ProfilingConfig", back_populates="runs")
    results = relationship(
        "ProfilingResult", back_populates="profiling_run", passive_deletes=True
    )


# ==================================================
# 6. PROFILING RESULTS
# ==================================================
class ProfilingResult(Base):
    __tablename__ = "profiling_results"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    profiling_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("profiling_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    object_name = Column(String(255), nullable=False)
    column_name = Column(String(255), nullable=False)
    data_type = Column(String(100))
    total_count = Column(BigInteger, nullable=False, server_default=text("0"))
    missing_count = Column(BigInteger, nullable=False, server_default=text("0"))
    missing_percentage = Column(
        Numeric(5, 2), nullable=False, server_default=text("0.00")
    )
    unique_count = Column(BigInteger)
    duplicate_count = Column(BigInteger)
    min_value = Column(Text)
    max_value = Column(Text)
    finding = Column(String(255))
    metrics = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "profiling_run_id",
            "object_name",
            "column_name",
            name="uq_result_per_column",
        ),
        CheckConstraint(
            "total_count >= 0 AND missing_count >= 0 "
            "AND missing_count <= total_count "
            "AND (unique_count IS NULL OR unique_count >= 0) "
            "AND (duplicate_count IS NULL OR duplicate_count >= 0)",
            name="chk_profiling_result_counts",
        ),
        CheckConstraint(
            "missing_percentage BETWEEN 0 AND 100",
            name="chk_profiling_result_percentages",
        ),
        Index("idx_profiling_results_run_id", "profiling_run_id"),
    )

    profiling_run = relationship("ProfilingRun", back_populates="results")
