import os
from pathlib import Path

import pytest
import yaml

from app.main import app


def resolve_contract_path(custom_env: str | None = None) -> Path:
    """Resolve OpenAPI contract path across environments:

    1. Environment variable CONTRACT_PATH (or custom_env override)
    2. ../contracts/openapi.yaml (zip/staged layout)
    3. ../bwaai2-store/contracts/openapi.yaml (dev multi-repo layout)
    """
    env_val = custom_env if custom_env is not None else os.getenv("CONTRACT_PATH")
    if env_val:
        return Path(env_val).resolve()

    backend_root = Path(__file__).resolve().parent.parent

    # Check zip/staged layout (sibling 'contracts/' folder)
    zip_layout = backend_root.parent / "contracts" / "openapi.yaml"
    if zip_layout.exists():
        return zip_layout.resolve()

    # Check dev multi-repo layout
    dev_layout = backend_root.parent / "bwaai2-store" / "contracts" / "openapi.yaml"
    if dev_layout.exists():
        return dev_layout.resolve()

    # CWD relative fallbacks
    cwd_zip = Path("../contracts/openapi.yaml").resolve()
    if cwd_zip.exists():
        return cwd_zip

    return Path("../bwaai2-store/contracts/openapi.yaml").resolve()


def test_contract_path_resolution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Environment variable override
    dummy_contract = tmp_path / "test_openapi.yaml"
    dummy_contract.write_text("openapi: 3.1.0\n", encoding="utf-8")
    monkeypatch.setenv("CONTRACT_PATH", str(dummy_contract))
    assert resolve_contract_path() == dummy_contract.resolve()

    # 2. Default resolution to existing contract
    monkeypatch.delenv("CONTRACT_PATH", raising=False)
    resolved = resolve_contract_path()
    assert resolved.exists(), f"Resolved contract does not exist: {resolved}"
    assert resolved.name == "openapi.yaml"


def test_openapi_contract_parity() -> None:
    # 1. Locate the single source of truth contract
    contract_file = resolve_contract_path()
    assert contract_file.exists(), f"Contract file not found at {contract_file}"

    with open(contract_file, encoding="utf-8") as f:
        contract = yaml.safe_load(f)

    # 2. Get FastAPI runtime generated OpenAPI spec
    runtime_spec = app.openapi()

    # 3. Verify Paths Parity
    expected_paths = set(contract["paths"].keys())
    runtime_paths = set(runtime_spec["paths"].keys())

    missing_paths = expected_paths - runtime_paths
    assert not missing_paths, f"FastAPI is missing paths defined in contract: {missing_paths}"

    # 4. Verify HTTP Methods and Operation IDs
    for path in expected_paths:
        expected_methods = contract["paths"][path]
        runtime_methods = runtime_spec["paths"][path]

        for method, expected_op in expected_methods.items():
            assert method in runtime_methods, f"Path {path} is missing method {method}"
            runtime_op = runtime_methods[method]

            # Verify operationId matches contract
            assert runtime_op.get("operationId") == expected_op.get("operationId"), (
                f"operationId mismatch for {method.upper()} {path}: "
                f"expected {expected_op.get('operationId')}, got {runtime_op.get('operationId')}"
            )

            # Verify tags match contract
            assert runtime_op.get("tags") == expected_op.get("tags"), (
                f"tags mismatch for {method.upper()} {path}: "
                f"expected {expected_op.get('tags')}, got {runtime_op.get('tags')}"
            )

            # Verify expected responses exist
            for code in expected_op.get("responses", {}):
                assert str(code) in runtime_op.get("responses", {}), (
                    f"Response code {code} missing on {method.upper()} {path}"
                )

    # 5. Verify Critical Component Schemas exist
    expected_schemas = set(contract.get("components", {}).get("schemas", {}).keys())
    runtime_schemas = set(runtime_spec.get("components", {}).get("schemas", {}).keys())

    missing_schemas = expected_schemas - runtime_schemas
    assert not missing_schemas, (
        f"FastAPI OpenAPI components/schemas is missing schemas: {missing_schemas}"
    )
