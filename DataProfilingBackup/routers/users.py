
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from dependencies import get_db
from models import User
from schemas import UserCreate, UserResponse

router = APIRouter(
    prefix="/api/users",
    tags=["Users"],
)

password_hash = PasswordHash.recommended()


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    # Hash the password before storing it
    hashed_password = password_hash.hash(user_data.password)

    user = User(
        full_name=user_data.full_name,
        email=str(user_data.email).lower(),
        password_hash=hashed_password,
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        )

    return user


@router.get(
    "/",
    response_model=list[UserResponse],
)
def get_users(
    db: Session = Depends(get_db),
):
    return db.query(User).order_by(User.created_at.desc()).all()


@router.get(
    "/{user_id}",
    response_model=UserResponse,
)
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
):
    from uuid import UUID

    try:
        parsed_user_id = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID format.",
        )

    user = db.query(User).filter(User.id == parsed_user_id).first()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return user
