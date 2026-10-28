"""The registry records serving windows, and its absence never breaks the tool."""

import builtins
import sys

import pytest

from blind_window.registry import MODEL_NAME, Registry, RegistryUnavailable


@pytest.fixture(scope="module")
def registry(tmp_path_factory):
    return Registry(tmp_path_factory.mktemp("mlruns"))


def test_recording_a_version_returns_an_increasing_number(registry):
    v1 = registry.record_version(0.0, "launch")
    v2 = registry.record_version(42.0, "label_confirmed retrain")
    assert v2 == v1 + 1


def test_versions_carry_their_serving_window_tags(registry):
    registry.close_version(1, 42.0)
    rows = registry.versions()
    assert rows[0]["served_from_day"] == "0.000"
    assert rows[0]["served_to_day"] == "42.000"
    assert rows[1]["trigger_reason"] == "label_confirmed retrain"


def test_reopening_the_same_root_sees_the_same_model(registry):
    again = Registry(registry.root)
    assert [v["version"] for v in again.versions()] == [1, 2]
    assert again.client.get_registered_model(MODEL_NAME) is not None


def test_without_mlflow_the_import_still_works_and_actions_raise(monkeypatch, tmp_path):
    """The minimal install has no mlflow; the module must import and every
    other code path must keep working. The analysis modules never import
    mlflow at module level, which this test enforces by blocking it."""
    real_import = builtins.__import__

    def no_mlflow(name, *a, **k):
        if name == "mlflow" or name.startswith("mlflow."):
            raise ImportError("blocked for the test")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_mlflow)
    for mod in list(sys.modules):
        if mod == "mlflow" or mod.startswith("mlflow."):
            monkeypatch.delitem(sys.modules, mod)
    import importlib

    import blind_window.registry as reg
    importlib.reload(reg)
    with pytest.raises(reg.RegistryUnavailable, match="registry"):
        reg.Registry(tmp_path)
    importlib.reload(reg)


def test_cli_and_analysis_import_without_touching_mlflow():
    for name in ("blind_window.cli", "blind_window.power", "blind_window.store.log_store",
                 "blind_window.policy.retrain"):
        mod = sys.modules.get(name)
        assert mod is not None
        src = open(mod.__file__).read()
        assert "import mlflow" not in src


def test_registry_unavailable_is_a_runtime_error_subclass():
    assert issubclass(RegistryUnavailable, RuntimeError)
