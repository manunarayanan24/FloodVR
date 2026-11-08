"""Probe NVIDIA-hosted speech (Riva on NVCF) with our NVIDIA_API_KEY: TTS then ASR.

    python -m agents.tools.probe_speech

Synthesises a sentence with Magpie TTS, feeds the audio to Parakeet ASR, and
prints the round-trip transcript. Uses the same function ids as
livekit-plugins-nvidia. Never prints the key.
"""

from __future__ import annotations

import os
import sys
import time

from agents import settings  # noqa: F401 - loads agents/.env

SERVER = "grpc.nvcf.nvidia.com:443"
TTS_FN = "877104f7-e885-42b9-8de8-f6e4c6303969"   # Magpie-Multilingual
ASR_FN = "1598d209-5e27-4d3c-8079-4751568b1081"   # parakeet-1.1b-en-US streaming
TEXT = "Is the kitchen ceiling stain covered by the flood policy?"


def _auth(fn: str):
    import riva.client
    return riva.client.Auth(uri=SERVER, use_ssl=True, metadata_args=[
        ["authorization", f"Bearer {os.environ['NVIDIA_API_KEY']}"], ["function-id", fn]])


def main() -> int:
    import riva.client
    t0 = time.perf_counter()
    try:
        tts = riva.client.SpeechSynthesisService(_auth(TTS_FN))
        resp = tts.synthesize(TEXT, voice_name="Magpie-Multilingual.EN-US.Leo",
                              language_code="en-US", sample_rate_hz=16000)
        audio = resp.audio
        print(f"TTS ok: {len(audio)} bytes PCM16 @16 kHz in {time.perf_counter() - t0:.1f}s")
    except Exception as exc:  # noqa: BLE001
        print(f"TTS FAILED: {type(exc).__name__}: {str(exc)[:300]}")
        return 1
    t1 = time.perf_counter()
    try:
        asr = riva.client.ASRService(_auth(ASR_FN))
        cfg = riva.client.StreamingRecognitionConfig(
            config=riva.client.RecognitionConfig(
                encoding=riva.client.AudioEncoding.LINEAR_PCM, sample_rate_hertz=16000,
                language_code="en-US", max_alternatives=1, enable_automatic_punctuation=True,
                audio_channel_count=1),
            interim_results=False)
        chunks = (audio[i:i + 3200] for i in range(0, len(audio), 3200))
        heard = []
        for r in asr.streaming_response_generator(audio_chunks=chunks, streaming_config=cfg):
            for res in r.results:
                if res.is_final and res.alternatives:
                    heard.append(res.alternatives[0].transcript.strip())
        print(f"ASR ok in {time.perf_counter() - t1:.1f}s: {' '.join(heard)!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"ASR FAILED: {type(exc).__name__}: {str(exc)[:300]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
