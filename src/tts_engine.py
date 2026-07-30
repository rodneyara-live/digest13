from pathlib import Path
import edge_tts
from config import PROJECT_ROOT, TTS_VOICE


async def synthesize(text: str, output_path: Path | None = None) -> bytes:
    if output_path is None:
        output_path = PROJECT_ROOT / "resumen.mp3"
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(str(output_path))
    return output_path.read_bytes()
