"""Model registry: which version served which window.

A retraining policy is meaningless without a record of what was serving when,
so every retrain registers a new version with its serving window as tags. The
backend is MLflow over SQLite (current MLflow releases refuse the plain file
backend for the registry). The module is importable without mlflow installed:
the CLI and every analysis path must keep working from the minimal install,
and a test blocks the import to prove it.
"""

from __future__ import annotations

from pathlib import Path

MODEL_NAME = "blind-window-stream-model"


class RegistryUnavailable(RuntimeError):
    """Raised when mlflow is not installed and a registry action is requested."""


def _mlflow():
    try:
        import mlflow  # noqa: PLC0415 - optional dependency, imported on use
        from mlflow.tracking import MlflowClient  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised via import blocking test
        raise RegistryUnavailable(
            "mlflow is not installed; install the [registry] extra to record versions"
        ) from exc
    return mlflow, MlflowClient


class Registry:
    """Thin wrapper owning one SQLite-backed MLflow registry."""

    def __init__(self, root: str | Path):
        mlflow, MlflowClient = _mlflow()
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        uri = f"sqlite:///{self.root / 'tracking.db'}"
        mlflow.set_tracking_uri(uri)
        self.client = MlflowClient(tracking_uri=uri, registry_uri=uri)
        try:
            self.client.create_registered_model(MODEL_NAME)
        except Exception:  # noqa: BLE001 - already-exists is the normal path on reopen
            pass

    def record_version(self, served_from_day: float, reason: str) -> int:
        """Register a new version and tag it with its serving start and the
        trigger that caused it. Returns the registry version number."""
        mv = self.client.create_model_version(MODEL_NAME, source="simulated://stream", run_id=None)
        v = int(mv.version)
        self.client.set_model_version_tag(MODEL_NAME, str(v), "served_from_day",
                                          f"{served_from_day:.3f}")
        self.client.set_model_version_tag(MODEL_NAME, str(v), "trigger_reason", reason)
        return v

    def close_version(self, version: int, served_to_day: float) -> None:
        self.client.set_model_version_tag(MODEL_NAME, str(version), "served_to_day",
                                          f"{served_to_day:.3f}")

    def versions(self) -> list[dict]:
        out = []
        for mv in self.client.search_model_versions(f"name='{MODEL_NAME}'"):
            out.append(
                {
                    "version": int(mv.version),
                    "served_from_day": mv.tags.get("served_from_day"),
                    "served_to_day": mv.tags.get("served_to_day"),
                    "trigger_reason": mv.tags.get("trigger_reason"),
                }
            )
        return sorted(out, key=lambda d: d["version"])
