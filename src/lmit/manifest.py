from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

from .scanner import ScannedFile


@dataclass
class ManifestRecord:
    relative_path: str
    output_path: str
    size: int
    mtime_ns: int
    sha256: str
    status: str
    conversion_key: str | None = None
    error: str | None = None
    last_error_type: str | None = None
    retryable: bool | None = None
    missing_at_utc: str | None = None


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.records: dict[str, ManifestRecord] = {}

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        manifest = cls(path)
        if not path.exists():
            return manifest
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.get("records", {}).items():
            manifest.records[key] = _record_from_payload(value)
        return manifest

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": 1,
            "records": {key: asdict(value) for key, value in self.records.items()},
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def is_unchanged_success(
        self,
        scanned: ScannedFile,
        *,
        conversion_key: str | None = None,
    ) -> bool:
        key = scanned.manifest_key
        record = self.records.get(key)
        if record is None:
            return False
        return (
            record.status == "success"
            and record.size == scanned.size
            and record.mtime_ns == scanned.mtime_ns
            and record.sha256 == scanned.sha256
            and record.conversion_key == conversion_key
        )

    def is_unchanged_completed(
        self,
        scanned: ScannedFile,
        *,
        conversion_key: str | None = None,
    ) -> bool:
        key = scanned.manifest_key
        record = self.records.get(key)
        if record is None:
            return False
        return (
            record.status in {"success", "partial"}
            and record.size == scanned.size
            and record.mtime_ns == scanned.mtime_ns
            and record.sha256 == scanned.sha256
            and record.conversion_key == conversion_key
        )

    def unchanged_completed_output_path(
        self,
        scanned: ScannedFile,
        *,
        conversion_key: str | None = None,
    ) -> Path | None:
        key = scanned.manifest_key
        record = self.records.get(key)
        if record is None:
            return None
        output_path = Path(record.output_path)
        if (
            record.status in {"success", "partial"}
            and record.size == scanned.size
            and record.mtime_ns == scanned.mtime_ns
            and record.sha256 == scanned.sha256
            and record.conversion_key == conversion_key
        ):
            return output_path.resolve()
        return None

    def output_path_for(self, scanned: ScannedFile) -> Path | None:
        record = self.records.get(scanned.manifest_key)
        if record is None:
            return None
        return Path(record.output_path)

    def is_retry_candidate(self, scanned: ScannedFile) -> bool:
        record = self.records.get(scanned.manifest_key)
        if record is None:
            return False
        return record.status in {"failed", "partial"} and record.retryable is not False

    def mark_missing(self, present_keys: set[str]) -> list[str]:
        missing: list[str] = []
        timestamp = datetime.now(timezone.utc).isoformat()
        for key, record in self.records.items():
            if key in present_keys or record.status == "missing":
                continue
            record.status = "missing"
            record.error = "source file not found during scan"
            record.last_error_type = "source_missing"
            record.retryable = False
            record.missing_at_utc = timestamp
            missing.append(key)
        return missing

    def update(
        self,
        scanned: ScannedFile,
        output_path: Path,
        *,
        status: str,
        conversion_key: str | None = None,
        error: str | None = None,
        last_error_type: str | None = None,
        retryable: bool | None = None,
    ) -> None:
        key = scanned.manifest_key
        self.records[key] = ManifestRecord(
            relative_path=key,
            output_path=str(output_path.resolve()),
            size=scanned.size,
            mtime_ns=scanned.mtime_ns,
            sha256=scanned.sha256,
            conversion_key=conversion_key,
            status=status,
            error=error,
            last_error_type=last_error_type,
            retryable=retryable,
            missing_at_utc=None,
        )


def _record_from_payload(value: dict[str, Any]) -> ManifestRecord:
    allowed = {field.name for field in fields(ManifestRecord)}
    payload = {key: item for key, item in value.items() if key in allowed}
    return ManifestRecord(**payload)
