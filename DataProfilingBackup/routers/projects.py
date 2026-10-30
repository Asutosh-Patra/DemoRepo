
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dependencies import get_db
from models import Project, User
from schemas import ProjectCreate, ProjectResponse

router = APIRouter(
    prefix="/api/projects",
    tags=["Projects"],
)


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    project_data: ProjectCreate,
    db: Session = Depends(get_db),
):
    # If a creator was supplied, make sure that user exists.
    if project_data.created_by is not None:
        user = db.query(User).filter(
            User.id == project_data.created_by
        ).first()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The specified user does not exist.",
            )

    project = Project(
        organization_name=project_data.organization_name,
        name=project_data.name,
        description=project_data.description,
        priority=project_data.priority,
        status=project_data.status,
        start_date=project_data.start_date,
        end_date=project_data.end_date,
        created_by=project_data.created_by,
    )

    db.add(project)

    try:
        db.commit()
        db.refresh(project)
    except IntegrityError as exc:
        db.rollback()

        # The database has a unique constraint on
        # organization_name + name.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A project with this name already exists "
                "for this organization."
            ),
        ) from exc

    return project


@router.get(
    "/",
    response_model=list[ProjectResponse],
)
def get_projects(
    db: Session = Depends(get_db),
):
    return (
        db.query(Project)
        .order_by(Project.created_at.desc())
        .all()
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
)
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
):
    project = (
        db.query(Project)
        .filter(Project.id == project_id)
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )

    return project
