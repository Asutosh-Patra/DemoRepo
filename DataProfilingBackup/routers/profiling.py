
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
    case,
    create_engine,
    func,
    inspect,
    or_,
    select,
)
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dependencies import get_db
from models import (
    Connection,
    ProfilingConfig,
    ProfilingResult,
    ProfilingRun,
    User,
)
from schemas import (
    ProfilingConfigCreate,
    ProfilingConfigResponse,
    ProfilingResultResponse,
    ProfilingRunResponse,
)


env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profiling", tags=["Profiling"])


# ---------------------------------------------------------
# Helper functions for the profiling engine
# ---------------------------------------------------------

def _validate_identifier(value: str, label: str) -> str:
    """Allow ordinary PostgreSQL schema and table identifiers."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_$]*", value
    ):
        raise ValueError(f"Invalid {label} name in selected_objects.")
    return value


def _is_string_column(column) -> bool:
    return isinstance(column.type, (String, Text))


def _missing_condition(column):
    """Treat NULL and blank/whitespace-only strings as missing."""
    if _is_string_column(column):
        return or_(
            column.is_(None),
            func.trim(column) == "",
        )

    return column.is_(None)


def _to_text(value):
    """Convert database values to strings for the response model."""
    if value is None:
        return None
    return str(value)


def _profile_table(source_connection, schema_name, table_name):
    """
    Profile one selected source table.

    The source connection uses SOURCE_DATABASE_URL.
    Results are saved separately to the DataMBA application database.
    """
    metadata = MetaData()

    table = Table(
        table_name,
        metadata,
        schema=schema_name,
        autoload_with=source_connection,
    )

    columns = list(table.columns)

    # Count all rows in the selected source table.
    row_count = source_connection.execute(
        select(func.count()).select_from(table)
    ).scalar_one()

    results = []
    total_missing = 0
    total_cells = row_count * len(columns)
    total_non_missing = 0

    for column in columns:
        missing_condition = _missing_condition(column)

        missing_count = source_connection.execute(
            select(
                func.coalesce(
                    func.sum(
                        case((missing_condition, 1), else_=0)
                    ),
                    0,
                )
            ).select_from(table)
        ).scalar_one()

        non_missing_count = row_count - missing_count

        # Count distinct non-missing values.
        non_missing_value = case(
            (missing_condition, None),
            else_=column,
        )

        unique_count = source_connection.execute(
            select(
                func.count(func.distinct(non_missing_value))
            ).select_from(table)
        ).scalar_one()

        # Number of repeated occurrences beyond the first occurrence.
        duplicate_count = max(non_missing_count - unique_count, 0)

        missing_percentage = (
            (missing_count / row_count) * 100
            if row_count > 0
            else 0.0
        )

        # Min/max are useful for common comparable scalar types.
        min_value = None
        max_value = None

        comparable_types = (
            String,
            Text,
            Integer,
            BigInteger,
            SmallInteger,
            Numeric,
            Float,
            Date,
            DateTime,
        )

        if isinstance(column.type, comparable_types):
            min_value, max_value = source_connection.execute(
                select(
                    func.min(column),
                    func.max(column),
                ).select_from(table)
            ).one()

        if missing_count > 0 and duplicate_count > 0:
            finding = "Missing values and repeated values detected."
        elif missing_count > 0:
            finding = "Missing values detected."
        elif duplicate_count > 0:
            finding = "Repeated values detected."
        else:
            finding = "No missing or repeated values detected."

        distinct_ratio = (
            unique_count / non_missing_count
            if non_missing_count > 0
            else 0.0
        )

        results.append(
            {
                "object_name": f"{schema_name}.{table_name}",
                "column_name": column.name,
                "data_type": str(column.type),
                "total_count": row_count,
                "missing_count": int(missing_count),
                "missing_percentage": round(missing_percentage, 2),
                "unique_count": int(unique_count),
                "duplicate_count": int(duplicate_count),
                "min_value": _to_text(min_value),
                "max_value": _to_text(max_value),
                "finding": finding,
                "metrics": {
                    "non_missing_count": int(non_missing_count),
                    "distinct_ratio": round(distinct_ratio, 4),
                    "is_unique": (
                        duplicate_count == 0
                        and non_missing_count > 0
                    ),
                },
            }
        )

        total_missing += int(missing_count)
        total_non_missing += int(non_missing_count)

    # Count excess duplicate rows across complete records.
    # This works for the ordinary scalar columns in customers.
    duplicate_rows = 0

    groupable_types = (
        String,
        Text,
        Integer,
        BigInteger,
        SmallInteger,
        Numeric,
        Float,
        Date,
        DateTime,
        Boolean,
    )

    if columns and all(
        isinstance(column.type, groupable_types)
        for column in columns
    ):
        duplicate_groups = (
            select(
                func.count().label("group_count")
            )
            .select_from(table)
            .group_by(*columns)
            .having(func.count() > 1)
            .subquery()
        )

        duplicate_rows = source_connection.execute(
            select(
                func.coalesce(
                    func.sum(duplicate_groups.c.group_count - 1),
                    0,
                )
            )
        ).scalar_one()

    return {
        "row_count": int(row_count),
        "column_count": len(columns),
        "missing_values": total_missing,
        "non_missing_values": total_non_missing,
        "total_cells": total_cells,
        "duplicate_rows": int(duplicate_rows),
        "results": results,
    }


# ---------------------------------------------------------
# Profiling configuration endpoints
# ---------------------------------------------------------

@router.post(
    "/configs/",
    response_model=ProfilingConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profiling_config(
    config_data: ProfilingConfigCreate,
    db: Session = Depends(get_db),
):
    connection = (
        db.query(Connection)
        .filter(Connection.id == config_data.connection_id)
        .first()
    )

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    if config_data.created_by is not None:
        user = (
            db.query(User)
            .filter(User.id == config_data.created_by)
            .first()
        )

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The specified user does not exist.",
            )

    config = ProfilingConfig(
        connection_id=config_data.connection_id,
        name=config_data.name,
        selected_objects=config_data.selected_objects,
        profiling_options=config_data.profiling_options,
        created_by=config_data.created_by,
    )

    db.add(config)

    try:
        db.commit()
        db.refresh(config)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create the profiling configuration. "
                   "Check the supplied values.",
        ) from exc

    return config


@router.get(
    "/configs/",
    response_model=list[ProfilingConfigResponse],
)
def get_profiling_configs(db: Session = Depends(get_db)):
    return (
        db.query(ProfilingConfig)
        .order_by(ProfilingConfig.created_at.desc())
        .all()
    )


@router.get(
    "/configs/{config_id}",
    response_model=ProfilingConfigResponse,
)
def get_profiling_config(
    config_id: UUID,
    db: Session = Depends(get_db),
):
    config = (
        db.query(ProfilingConfig)
        .filter(ProfilingConfig.id == config_id)
        .first()
    )

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profiling configuration not found.",
        )

    return config


@router.get(
    "/connections/{connection_id}/configs/",
    response_model=list[ProfilingConfigResponse],
)
def get_configs_by_connection(
    connection_id: UUID,
    db: Session = Depends(get_db),
):
    connection = (
        db.query(Connection)
        .filter(Connection.id == connection_id)
        .first()
    )

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found.",
        )

    return (
        db.query(ProfilingConfig)
        .filter(ProfilingConfig.connection_id == connection_id)
        .order_by(ProfilingConfig.created_at.desc())
        .all()
    )


# ---------------------------------------------------------
# Execute a profiling run
# ---------------------------------------------------------

@router.post(
    "/configs/{config_id}/runs/",
    response_model=ProfilingRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_profiling_run(
    config_id: UUID,
    db: Session = Depends(get_db),
):
    config = (
        db.query(ProfilingConfig)
        .filter(ProfilingConfig.id == config_id)
        .first()
    )

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profiling configuration not found.",
        )

    if not config.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This profiling configuration is inactive.",
        )

    selected_objects = config.selected_objects or []

    if not selected_objects:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tables are selected for profiling.",
        )

    source_url = os.getenv("SOURCE_DATABASE_URL")

    if not source_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SOURCE_DATABASE_URL is not configured.",
        )

    # Create and persist the run before executing the profiling work.
    run = ProfilingRun(
        profiling_config_id=config.id,
        status="running",
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        row_count=0,
        column_count=0,
        average_completeness=0,
        duplicate_rows=0,
        missing_values=0,
        error_message=None,
    )

    db.add(run)

    try:
        db.commit()
        db.refresh(run)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create the profiling run.",
        ) from exc

    run_id = run.id
    source_engine = None

    try:
        # Use only the configured source URL for source access.
        # Do not use the DataMBA application engine for source queries.
        parsed_source_url = make_url(source_url)
        configured_database = (
            (config.connection.connection_config or {}).get("database")
        )

        if (
            configured_database
            and parsed_source_url.database
            and configured_database != parsed_source_url.database
        ):
            raise ValueError(
                "The selected connection database does not match "
                "SOURCE_DATABASE_URL."
            )

        source_engine = create_engine(
            source_url,
            pool_pre_ping=True,
        )

        combined_results = []
        total_rows = 0
        total_columns = 0
        total_missing = 0
        total_non_missing = 0
        total_cells = 0
        total_duplicate_rows = 0

        with source_engine.connect() as source_connection:
            source_inspector = inspect(source_connection)

            for selected_object in selected_objects:
                if not isinstance(selected_object, dict):
                    raise ValueError(
                        "Each selected object must contain schema and table."
                    )

                schema_name = _validate_identifier(
                    selected_object.get("schema"),
                    "schema",
                )
                table_name = _validate_identifier(
                    selected_object.get("table"),
                    "table",
                )

                if not source_inspector.has_table(
                    table_name,
                    schema=schema_name,
                ):
                    raise ValueError(
                        f"Selected table {schema_name}.{table_name} "
                        "does not exist in the source database."
                    )

                table_profile = _profile_table(
                    source_connection,
                    schema_name,
                    table_name,
                )

                total_rows += table_profile["row_count"]
                total_columns += table_profile["column_count"]
                total_missing += table_profile["missing_values"]
                total_non_missing += table_profile["non_missing_values"]
                total_cells += table_profile["total_cells"]
                total_duplicate_rows += table_profile["duplicate_rows"]

                combined_results.extend(table_profile["results"])

        # Save every column's metrics in the existing results table.
        for item in combined_results:
            db.add(
                ProfilingResult(
                    profiling_run_id=run_id,
                    object_name=item["object_name"],
                    column_name=item["column_name"],
                    data_type=item["data_type"],
                    total_count=item["total_count"],
                    missing_count=item["missing_count"],
                    missing_percentage=item["missing_percentage"],
                    unique_count=item["unique_count"],
                    duplicate_count=item["duplicate_count"],
                    min_value=item["min_value"],
                    max_value=item["max_value"],
                    finding=item["finding"],
                    metrics=item["metrics"],
                )
            )

        average_completeness = (
            (total_non_missing / total_cells) * 100
            if total_cells > 0
            else 0.0
        )

        run = (
            db.query(ProfilingRun)
            .filter(ProfilingRun.id == run_id)
            .first()
        )

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.row_count = total_rows
        run.column_count = total_columns
        run.average_completeness = round(average_completeness, 2)
        run.duplicate_rows = total_duplicate_rows
        run.missing_values = total_missing
        run.error_message = None

        db.commit()
        db.refresh(run)

    except Exception as exc:
        logger.exception("Profiling run %s failed.", run_id)

        db.rollback()

        # Keep a failed run record so the user can inspect its status.
        run = (
            db.query(ProfilingRun)
            .filter(ProfilingRun.id == run_id)
            .first()
        )

        if run is not None:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.error_message = (
                f"Profiling failed ({type(exc).__name__}). "
                "Check the source connection, selected schema/table, "
                "and source database permissions."
            )

            try:
                db.commit()
                db.refresh(run)
            except Exception:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Profiling failed and the run status could not be saved.",
                ) from exc

    finally:
        if source_engine is not None:
            source_engine.dispose()

    return run


# ---------------------------------------------------------
# Profiling run retrieval endpoints
# ---------------------------------------------------------

@router.get(
    "/runs/",
    response_model=list[ProfilingRunResponse],
)
def get_profiling_runs(db: Session = Depends(get_db)):
    return (
        db.query(ProfilingRun)
        .order_by(ProfilingRun.created_at.desc())
        .all()
    )


@router.get(
    "/runs/{run_id}",
    response_model=ProfilingRunResponse,
)
def get_profiling_run(
    run_id: UUID,
    db: Session = Depends(get_db),
):
    run = (
        db.query(ProfilingRun)
        .filter(ProfilingRun.id == run_id)
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profiling run not found.",
        )

    return run


@router.get(
    "/configs/{config_id}/runs/",
    response_model=list[ProfilingRunResponse],
)
def get_runs_by_config(
    config_id: UUID,
    db: Session = Depends(get_db),
):
    config = (
        db.query(ProfilingConfig)
        .filter(ProfilingConfig.id == config_id)
        .first()
    )

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profiling configuration not found.",
        )

    return (
        db.query(ProfilingRun)
        .filter(ProfilingRun.profiling_config_id == config_id)
        .order_by(ProfilingRun.created_at.desc())
        .all()
    )


# ---------------------------------------------------------
# Profiling result retrieval endpoint
# ---------------------------------------------------------

@router.get(
    "/runs/{run_id}/results/",
    response_model=list[ProfilingResultResponse],
)
def get_profiling_results(
    run_id: UUID,
    db: Session = Depends(get_db),
):
    run = (
        db.query(ProfilingRun)
        .filter(ProfilingRun.id == run_id)
        .first()
    )

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profiling run not found.",
        )

    return (
        db.query(ProfilingResult)
        .filter(ProfilingResult.profiling_run_id == run_id)
        .order_by(ProfilingResult.object_name, ProfilingResult.column_name)
        .all()
    )
