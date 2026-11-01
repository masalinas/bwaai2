# Spec Delta

## Purpose

Provides health inspection and dependency connectivity verification for the FastAPI backend service.

## ADDED Requirements

### Requirement: Service and Dependency Health Inspection
The API SHALL expose `GET /health` under the system tag, executing a Redis ping check and returning the operational health status, version string, and ISO-8601 timestamp.

#### Scenario: All systems operational
- **WHEN** a client issues `GET /health` and Redis responds successfully to ping
- **THEN** the server returns HTTP 200 with status "ok", version "1.0.0", and dependency redis marked "healthy"

#### Scenario: Redis connection failure
- **WHEN** Redis is unreachable or fails to respond to ping
- **THEN** the server reports degraded status or returns HTTP 500 conforming to the unified Error schema
