import os


TRUTHY_VALUES = {"1", "true", "yes", "on"}
PRODUCTION_VALUES = {"prod", "production"}
VALID_HISTORY_BACKENDS = {"sqlite", "turso"}


def env_flag(name):
    return os.environ.get(name, "").strip().lower() in TRUTHY_VALUES


def is_production_context():
    return (
        os.environ.get("APP_ENV", "").strip().lower() in PRODUCTION_VALUES
        or os.environ.get("STREAMLIT_ENV", "").strip().lower() in PRODUCTION_VALUES
    )


def turso_configured():
    return bool(
        os.environ.get("TURSO_DATABASE_URL")
        and os.environ.get("TURSO_AUTH_TOKEN")
    )


def sqlite_fallback_allowed():
    return env_flag("ALLOW_SQLITE_HISTORY_FALLBACK") or not is_production_context()


def resolve_history_backend():
    configured_backend = os.environ.get("HISTORY_BACKEND", "").strip().lower()
    if configured_backend:
        if configured_backend not in VALID_HISTORY_BACKENDS:
            raise RuntimeError(
                "HISTORY_BACKEND must be either 'turso' or 'sqlite'."
            )
        if configured_backend == "turso" and not turso_configured():
            raise RuntimeError(
                "HISTORY_BACKEND=turso requires TURSO_DATABASE_URL and TURSO_AUTH_TOKEN."
            )
        if configured_backend == "sqlite" and not sqlite_fallback_allowed():
            raise RuntimeError(
                "SQLite history fallback is disabled in production. "
                "Set HISTORY_BACKEND=turso with Turso credentials, or set "
                "ALLOW_SQLITE_HISTORY_FALLBACK=true for an intentional local/dev run."
            )
        return configured_backend

    if turso_configured():
        return "turso"

    if not sqlite_fallback_allowed():
        raise RuntimeError(
            "Turso history is required in production. Set HISTORY_BACKEND=turso, "
            "TURSO_DATABASE_URL, and TURSO_AUTH_TOKEN."
        )

    return "sqlite"
