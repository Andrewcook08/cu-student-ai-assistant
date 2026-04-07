from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from neo4j import AsyncDriver
from shared.auth import decode_access_token
from shared.database import get_db
from shared.models import User
from sqlalchemy.orm import Session

__all__ = ["get_db", "get_current_user", "get_http_client", "get_neo4j_driver"]

_bearer = HTTPBearer()


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    token = credentials.credentials
    try:
        user_id = decode_access_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from None

    user = db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_http_client(request: Request) -> httpx.AsyncClient:
    """Return the shared httpx.AsyncClient from app.state (lifespan-managed)."""
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_neo4j_driver(request: Request) -> AsyncDriver:
    """Return the shared Neo4j AsyncDriver from app.state (lifespan-managed)."""
    return request.app.state.neo4j_driver  # type: ignore[no-any-return]
