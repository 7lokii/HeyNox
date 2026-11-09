import pytest

import nox.optional as optional
from nox.optional import OptionalDependencyError, available, require


def test_require_imports_stdlib() -> None:
    assert require("json").__name__ == "json"


def test_require_missing_dependency_names_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(name: str) -> None:
        raise ImportError(name)

    # Simula a ausência sem depender do que está instalado nesta máquina.
    monkeypatch.setattr(optional.importlib, "import_module", boom)

    with pytest.raises(OptionalDependencyError, match=r"sounddevice.*\[audio\]"):
        optional.require("sounddevice")
    with pytest.raises(OptionalDependencyError, match="nox_modulo_que_nao_existe"):
        optional.require("nox_modulo_que_nao_existe")


def test_available_reflects_importability() -> None:
    assert available("json") is True
    assert available("nox_modulo_que_nao_existe") is False


def test_optional_dependency_error_is_importerror() -> None:
    assert issubclass(OptionalDependencyError, ImportError)
