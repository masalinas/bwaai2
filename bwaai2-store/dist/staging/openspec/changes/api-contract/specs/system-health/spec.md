# Spec Delta

## Purpose

Enables operational monitoring, infrastructure liveness probing, and dependency health inspection for the PDF processing service.

## ADDED Requirements

### Requirement: Service Health Inspection
The API SHALL provide a health check endpoint at `GET /health` under the system tag, returning the operational status of the service and its dependencies, current application version, and the server timestamp.

#### Scenario: Service is fully operational
- **WHEN** a client or orchestrator issues a `GET /health` request while all subsystems are functioning
- **THEN** the server returns HTTP 200 OK with status "ok", application version, and ISO-8601 timestamp

#### Scenario: Service encounters internal failure
- **WHEN** an unrecoverable failure occurs within the health inspection check
- **THEN** the server returns HTTP 500 Internal Server Error conforming to the standard Error response schema
