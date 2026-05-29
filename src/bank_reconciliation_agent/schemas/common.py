from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class ErrorCode(StrEnum):
    MISSING_COLUMNS = "MISSING_COLUMNS"
    DUPLICATE_FLOW_ID = "DUPLICATE_FLOW_ID"
    INVALID_FILE_FORMAT = "INVALID_FILE_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TOO_MANY_ROWS = "TOO_MANY_ROWS"
    INVALID_DATA_TYPE = "INVALID_DATA_TYPE"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"


class ApiResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: T | None = None
    error_code: str | None = None


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int

