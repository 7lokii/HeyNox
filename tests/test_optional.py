import pytest

from nox.optional import OptionalDependencyError, available, require


def test_require_imports_stdlib() -> None:
    assert require("json").__name__ == "json"


def test_require_missing_dependency_names_extra() -> None:
    with pytest.raises(OptionalDependencyError, match=r"sounddevice.*\[audio\]"):
        require("sounddevice")
        pytest.skip("sounddevice instalado neste ambiente")
    with pytest.raises(OptionalDependencyError, match=r"nox_modulo_que_nao_existe"):
        require("nox_modulo_que_nao_existe")


def test_available_reflects_importability() -> None:
    assert available("json") is True
    assert available("nox_modulo_que_nao_existe") is False


def test_optional_dependency_error_is_importerror() -> None:
    assert issubclass(OptionalDependencyError, ImportError)
