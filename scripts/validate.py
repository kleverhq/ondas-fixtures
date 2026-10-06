#!/usr/bin/env python3

import json
import os
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, SchemaError

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
    schema_path = root / "schemas" / "fixture.schema.json"
    if not schema_path.is_file():
        raise ValueError("missing schema: fixture.schema.json")
    schema = read_json(schema_path)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError(f"{schema_path}: invalid schema: {error.message[:240]}") from error
    validator = Draft202012Validator(schema)
    for path in json_files(root):
        if path == schema_path:
            yield path, schema
            continue
        if path.name != "fixture.json" or len(path.relative_to(root).parts) != 3:
            raise ValueError(f"{path.relative_to(root)}: no schema assigned to this JSON file")
        data = read_json(path)
        error = next(validator.iter_errors(data), None)
        if error is not None:
            while error.context:
                error = max(error.context, key=lambda child: len(child.absolute_path))
            raise ValueError(f"{path.relative_to(root)}: {error.json_path}: {error.message[:240]}")
        yield path, data


def main():
    count = sum(1 for _ in validated_documents())
    print(f"Validated {count} JSON files against the local fixture schema.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"validate.py: {error}", file=sys.stderr)
        raise SystemExit(1)
