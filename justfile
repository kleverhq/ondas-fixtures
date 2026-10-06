set positional-arguments

# List available commands.
default:
    @just --list

# Prepare the isolated environment for validation and tests.
setup:
    python3 -m venv .venv
    .venv/bin/python -m pip install -r scripts/requirements.txt

# Download and verify waveform payloads; accepts installer flags.
install *args:
    @python3 -B scripts/install.py "$@"

# Print the Markdown corpus statistics table.
stats:
    @python3 -B scripts/stats.py

# Validate all repository JSON against the fixture schema.
validate:
    @.venv/bin/python -B scripts/validate.py

# Run metadata, corpus, and script checks.
check:
    @.venv/bin/python -B scripts/check.py

# Run the Python script tests.
test:
    @.venv/bin/python -B -m unittest discover -s scripts -p 'test_*.py'

# Publish an explicit fixture list; accepts --target and --dry-run.
release tag +fixtures:
    @python3 -B scripts/release.py "$@"
