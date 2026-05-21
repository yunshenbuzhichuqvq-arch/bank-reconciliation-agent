from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: T


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int

