"""Settings loaded from `.env` and SHELFKEEP_* environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LOAN_DAYS = 14


@dataclass(frozen=True)
class Settings:
    loan_days: int = DEFAULT_LOAN_DAYS


def parse_env_file(text):
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def load_settings(env_path=".env", environ=None):
    environ = os.environ if environ is None else environ
    path = Path(env_path)
    values = parse_env_file(path.read_text(encoding="utf-8")) if path.exists() else {}
    values.update({k: v for k, v in environ.items() if k.startswith("SHELFKEEP_")})
    return Settings(loan_days=int(values.get("SHELFKEEP_LOAN_DAYS", DEFAULT_LOAN_DAYS)))
