from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Operational status: ok, degraded, or unhealthy.")
    version: str = Field(..., description="Semantic application version.")
    timestamp: datetime = Field(..., description="Current server ISO-8601 timestamp.")
    dependencies: dict[str, str] = Field(
        default_factory=dict, description="Status of downstream dependencies."
    )
