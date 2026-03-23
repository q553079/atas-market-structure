from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import sqlite3

from atas_market_structure.storage_models import AppliedMigration


@dataclass(frozen=True)
class MigrationFile:
    """One migration file discovered on disk."""

    version: str
    name: str
    path: Path
    checksum: str


class SQLiteMigrationRunner:
    """Minimal ordered SQL-file migration runner for the local SQLite store."""

    def __init__(self, *, database_path: Path, migration_dir: Path) -> None:
        self._database_path = database_path
        self._migration_dir = migration_dir

    def initialize(self, *, target_version: str | None = None) -> list[AppliedMigration]:
        """Apply pending migrations up to target_version or latest when omitted."""

        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        applied: list[AppliedMigration] = []
        with self._connect() as connection:
            self._ensure_migration_table(connection)
            applied_versions = {
                row["version"]: row
                for row in connection.execute(
                    """
                    SELECT version, name, checksum, applied_at
                    FROM schema_migrations
                    ORDER BY version
                    """,
                ).fetchall()
            }
            for migration in self._discover_migrations():
                if target_version is not None and migration.version > target_version:
                    break
                existing = applied_versions.get(migration.version)
                if existing is not None:
                    if existing["checksum"] != migration.checksum:
                        raise RuntimeError(
                            f"Migration checksum mismatch for {migration.version} {migration.name}: "
                            f"database={existing['checksum']} file={migration.checksum}",
                        )
                    continue
                script = migration.path.read_text(encoding="utf-8")
                applied_at = datetime.now(tz=UTC)
                connection.executescript(script)
                connection.execute(
                    """
                    INSERT INTO schema_migrations (
                        version,
                        name,
                        checksum,
                        applied_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        migration.version,
                        migration.name,
                        migration.checksum,
                        applied_at.isoformat(),
                    ),
                )
                applied.append(
                    AppliedMigration(
                        version=migration.version,
                        name=migration.name,
                        checksum=migration.checksum,
                        applied_at=applied_at,
                    ),
                )
        return applied

    def list_applied(self) -> list[AppliedMigration]:
        """Return applied migrations in ascending version order."""

        if not self._database_path.exists():
            return []
        with self._connect() as connection:
            self._ensure_migration_table(connection)
            rows = connection.execute(
                """
                SELECT version, name, checksum, applied_at
                FROM schema_migrations
                ORDER BY version
                """,
            ).fetchall()
        return [
            AppliedMigration(
                version=row["version"],
                name=row["name"],
                checksum=row["checksum"],
                applied_at=datetime.fromisoformat(row["applied_at"]),
            )
            for row in rows
        ]

    def latest_version(self) -> str | None:
        """Return the latest available migration version on disk."""

        migrations = self._discover_migrations()
        return migrations[-1].version if migrations else None

    def _discover_migrations(self) -> list[MigrationFile]:
        if not self._migration_dir.exists():
            return []
        migrations: list[MigrationFile] = []
        for path in sorted(self._migration_dir.glob("*.sql")):
            version, _, stem_name = path.stem.partition("_")
            if not version:
                continue
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            migrations.append(
                MigrationFile(
                    version=version,
                    name=stem_name or path.stem,
                    path=path,
                    checksum=checksum,
                ),
            )
        return migrations

    @staticmethod
    def _ensure_migration_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                checksum TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """,
        )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection
