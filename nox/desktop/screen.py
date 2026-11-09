"""Captura de ecrã e OCR com o motor do Windows.

O OCR usa `Windows.Media.Ocr`, que já vem com o sistema e reconhece a língua
configurada no perfil (neste caso, Português). Não é preciso Tesseract nem
descarregar modelos.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from nox.desktop.guard import DesktopError
from nox.optional import require

MAX_OCR_CHARS = 6000


def screenshot(path: Path) -> Path:
    """Guarda o ecrã inteiro em PNG e devolve o caminho."""
    require("mss")
    import mss

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with mss.MSS() as capture:
            capture.shot(output=str(path))
    except Exception as exc:  # noqa: BLE001 — mss levanta erros variados
        raise DesktopError(f"não consegui capturar o ecrã: {exc}") from exc
    return path


def screen_size() -> tuple[int, int]:
    require("mss")
    import mss

    with mss.MSS() as capture:
        monitor = capture.monitors[0]
    return int(monitor["width"]), int(monitor["height"])


async def _ocr_file(path: Path) -> str:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    data = path.read_bytes()
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(data)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    engine = OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise DesktopError("o Windows não tem nenhum motor de OCR configurado")
    result = await engine.recognize_async(bitmap)
    return str(result.text)


def ocr(path: Path) -> str:
    """Texto visível numa imagem, pelo OCR do Windows."""
    try:
        import winrt.windows.media.ocr  # noqa: F401
    except ImportError as exc:
        raise DesktopError(
            'o OCR precisa do extra: pip install -e ".[desktop]" (winrt-runtime)'
        ) from exc
    try:
        text = asyncio.run(_ocr_file(path))
    except DesktopError:
        raise
    except Exception as exc:  # noqa: BLE001 — WinRT devolve erros variados
        raise DesktopError(f"o OCR falhou: {exc}") from exc
    text = " ".join(text.split())
    return text[:MAX_OCR_CHARS] + ("… (truncado)" if len(text) > MAX_OCR_CHARS else "")
