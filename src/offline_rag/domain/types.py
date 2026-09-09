"""Shared domain typing helpers."""

from typing import Annotated

from pydantic import Field, StringConstraints

NonEmptyStr = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(ge=1)]
Score = Annotated[float, Field(allow_inf_nan=False)]
