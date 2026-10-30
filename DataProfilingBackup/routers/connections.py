
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dependencies import get_db
from models import Connection, Project
from schemas import ConnectionCreate, ConnectionResponse


router = APIRouter(
    prefix="/api/connections",
    tags=["Connections"]
)

# 1. Create a connection for a project
@router.post(
    "/",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED
)
def create_connection(
    connection_data: ConnectionCreate,
    db: Session = Depends(get_db)
):
    # Check whether the project exists
    project = (
        db.query(Project)
        .filter(Project.id == connection_data.project_id)
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found."
        )

    # Check whether this project already has a connection
    existing_connection = (
        db.query(Connection)
        .filter(Connection.project_id == connection_data.project_id)
        .first()
    )

    if existing_connection is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This project already has a connection."
        )

    connection = Connection(
        project_id=connection_data.project_id,
        name=connection_data.name,
        connection_role=connection_data.connection_role,
        source_type=connection_data.source_type,
        connection_config=connection_data.connection_config,
        secret_ref=connection_data.secret_ref
    )

    db.add(connection)

    try:
        db.commit()
        db.refresh(connection)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not create connection. Check whether this project already has a connection."
        ) from exc

    return connection


# 2. Get all connections
@router.get("/", response_model=list[ConnectionResponse])
def get_connections(db: Session = Depends(get_db)):
    return (
        db.query(Connection)
        .order_by(Connection.created_at.desc())
        .all()
    )


# 3. Get one connection by its ID
@router.get("/{connection_id}", response_model=ConnectionResponse)
def get_connection(
    connection_id: UUID,
    db: Session = Depends(get_db)
):
    connection = (
        db.query(Connection)
        .filter(Connection.id == connection_id)
        .first()
    )

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Connection not found."
        )

    return connection


# 4. Get a project's connection
@router.get(
    "/project/{project_id}",
    response_model=ConnectionResponse
)
def get_project_connection(
    project_id: UUID,
    db: Session = Depends(get_db)
):
    connection = (
        db.query(Connection)
        .filter(Connection.project_id == project_id)
        .first()
    )

    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No connection found for this project."
        )

    return connection
