#!/usr/bin/env python3

import json
import os
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, SchemaError
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent


def invalid_constant(value):
    raise ValueError(f"non-standard JSON constant: {value}")


def read_json(path):
    try:
        return json.loads(path.read_bytes(), parse_constant=invalid_constant)
    except (ValueError, UnicodeError) as error:
        raise ValueError(f"{path}: invalid JSON: {error}") from error


def json_files(root):
    for directory, folders, files in os.walk(root):
        folders[:] = sorted(name for name in folders if name not in {".git", ".venv", "__pycache__"})
        for name in sorted(files):
            if name.endswith(".json"):
                yield Path(directory) / name


def validated_documents(root=ROOT):
    root = root.resolve()
    schemas = {path: read_json(path) for path in sorted((root / "schemas").glob("*.schema.json"))}
    required = {"catalog.schema.json", "fixture.schema.json", "oracle.schema.json"}
    missing = required - {path.name for path in schemas}
    if missing:
        raise ValueError("missing schemas: " + ", ".join(sorted(missing)))
    for path, schema in schemas.items():
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as error:
            raise ValueError(f"{path}: invalid schema: {error.message[:240]}") from error
    registry = Registry().with_resources(
        (path.as_uri(), Resource.from_contents(schema)) for path, schema in schemas.items()
    )
    validators = {
        kind: Draft202012Validator({"$ref": (root / "schemas" / f"{kind}.schema.json").as_uri()}, registry=registry)
        for kind in ("catalog", "fixture")
    }
    if not (root / "catalog.json").is_file():
        raise ValueError("catalog.json is missing")
    for path in json_files(root):
        if path in schemas:
            yield path, schemas[path]
            continue
        if path == root / "catalog.json":
            kind = "catalog"
        elif path.name == "fixture.json" and len(path.relative_to(root).parts) == 3:
            kind = "fixture"
        else:
            raise ValueError(f"{path.relative_to(root)}: no schema assigned to this JSON file")
        data = read_json(path)
        error = next(validators[kind].iter_errors(data), None)
        if error is not None:
            while error.context:
                error = max(error.context, key=lambda child: len(child.absolute_path))
            raise ValueError(f"{path.relative_to(root)}: {error.json_path}: {error.message[:240]}")
        yield path, data


def main():
    count = sum(1 for _ in validated_documents())
    print(f"Validated {count} JSON files against local schemas.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"validate.py: {error}", file=sys.stderr)
        raise SystemExit(1)
