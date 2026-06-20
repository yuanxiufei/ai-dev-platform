"""
语音 Provider — STT (Whisper) + TTS (OpenAI / Edge TTS)

借鉴 Open WebUI 的 Audio 集成：
- STT: OpenAI Whisper API + 本地 Whisper 备选
- TTS: OpenAI TTS API + Edge TTS（免费离线）备选
"""

from __future__ import annotations

import base64
import io
import os
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx


# ── 统一语音接口 ─────────────────────────────────

class VoiceFormat(str, Enum):
    """音频格式"""
    MP3 = "mp3"
    OPUS = "opus"
    AAC = "aac"
    FLAC = "flac"
    WAV = "wav"
    PCM = "pcm"


class TTSVoice(str, Enum):
    """TTS 语音"""
    ALLOY = "alloy"        # 中性
    ECHO = "echo"          # 男声
    FABLE = "fable"        # 英式男声
    NOVA = "nova"          # 女声
    ONYX = "onyx"          # 深沉男声
    SHIMMER = "shimmer"    # 温暖女声
    # 中文语音
    ZH_CN_XIAOXIAO = "zh-CN-XiaoxiaoNeural"   # Edge TTS 中文女声
    ZH_CN_YUNXI = "zh-CN-YunxiNeural"          # Edge TTS 中文男声


@dataclass
class TTSRequest:
    """TTS 语音合成请求"""
    text: str
    voice: TTSVoice = TTSVoice.NOVA
    format: VoiceFormat = VoiceFormat.MP3
    speed: float = 1.0           # 0.25 ~ 4.0
    model: str = "tts-1"         # tts-1 | tts-1-hd
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TTSResponse:
    """TTS 语音合成响应"""
    audio_base64: str = ""       # Base64 编码音频
    audio_url: str = ""          # 音频 URL
    format: str = "mp3"
    duration_seconds: float = 0.0
    latency_ms: float = 0.0


@dataclass
class STTRequest:
    """STT 语音转文字请求"""
    audio_base64: str = ""       # Base64 编码音频
    audio_url: str = ""          # 音频 URL（二选一）
    language: str = ""           # ISO 639-1，留空自动检测
    prompt: str = ""             # 引导词（提升识别准确率）
    model: str = "whisper-1"     # whisper-1
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class STTResponse:
    """STT 语音转文字响应"""
    text: str = ""
    language: str = ""
    duration_seconds: float = 0.0
    segments: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0


# ── OpenAI TTS Provider ──────────────────────────

class OpenAITTSProvider:
    """OpenAI TTS API"""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(60.0, connect=10.0),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        t0 = time.perf_counter()

        payload = {
            "model": request.model,
            "input": request.text,
            "voice": request.voice.value if request.voice.value.startswith("zh-") else request.voice.value,
            "response_format": request.format.value,
            "speed": request.speed,
        }

        resp = await self.client.post("/audio/speech", json=payload)
        resp.raise_for_status()
        audio_bytes = resp.content
        latency = (time.perf_counter() - t0) * 1000

        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        # 估算时长（mp3 约 16 kbps）
        estimated_duration = len(audio_bytes) / 2000

        return TTSResponse(
            audio_base64=audio_b64,
            format=request.format.value,
            duration_seconds=estimated_duration,
            latency_ms=latency,
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── Edge TTS Provider (免费离线) ─────────────────

class EdgeTTSProvider:
    """
    Microsoft Edge TTS — 免费语音合成

    通过 Edge TTS 的 HTTP API 合成语音。
    中文语音质量优秀，无需 API Key。
    """

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0),
                headers={"Content-Type": "application/ssml+xml"},
            )
        return self._client

    def is_available(self) -> bool:
        return True  # 纯 HTTP，无需 API key

    def _build_ssml(self, text: str, voice: str, rate: str) -> str:
        """构建 SSML"""
        return (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="en-US">'
            f'<voice name="{voice}">'
            f'<prosody rate="{rate}">{text}</prosody>'
            f"</voice></speak>"
        )

    def _get_voice_name(self, voice: TTSVoice) -> str:
        """支持的 Edge 语音名称"""
        edge_voices: dict[str, str] = {
            "zh-CN-XiaoxiaoNeural": "zh-CN-XiaoxiaoNeural",
            "zh-CN-YunxiNeural": "zh-CN-YunxiNeural",
            "en-US-AriaNeural": "en-US-AriaNeural",
            "en-US-GuyNeural": "en-US-GuyNeural",
        }
        if voice.value in edge_voices:
            return edge_voices[voice.value]
        # 中文 TTS 用中文语音，否则用英文
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in voice.value)
        return "zh-CN-XiaoxiaoNeural" if has_chinese else "en-US-AriaNeural"

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        t0 = time.perf_counter()

        voice_name = self._get_voice_name(request.voice)
        rate = f"{request.speed:.0%}"
        ssml = self._build_ssml(request.text, voice_name, rate)

        # Edge TTS 公开 API
        url = "https://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1"
        params = {"TrustedClientToken": "6A5AA1D9EA0F4D5B88E62B933A9F2B5D"}
        headers = {
            **self.client.headers,
            "Accept": "*/*",
            "Origin": "chrome-extension://jdiccldimpdaibmpdkjbjigehemkchah",
        }

        resp = await self._client.post(url, params=params, headers=headers, content=ssml)
        resp.raise_for_status()
        audio_bytes = resp.content
        latency = (time.perf_counter() - t0) * 1000

        # Edge TTS 默认 mp3
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
        estimated_duration = len(audio_bytes) / 2000

        return TTSResponse(
            audio_base64=audio_b64,
            format="mp3",
            duration_seconds=estimated_duration,
            latency_ms=latency,
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── OpenAI Whisper STT Provider ──────────────────

class WhisperSTTProvider:
    """OpenAI Whisper STT API"""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def transcribe(self, request: STTRequest) -> STTResponse:
        t0 = time.perf_counter()

        # 获取音频字节
        if request.audio_base64:
            audio_bytes = base64.b64decode(request.audio_base64)
        elif request.audio_url:
            async with httpx.AsyncClient() as dl:
                resp = await dl.get(request.audio_url)
                resp.raise_for_status()
                audio_bytes = resp.content
        else:
            raise ValueError("audio_base64 或 audio_url 必须提供一个")

        # 写临时文件
        suffix = ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            data: dict[str, Any] = {"model": request.model}
            if request.language:
                data["language"] = request.language
            if request.prompt:
                data["prompt"] = request.prompt

            with open(tmp_path, "rb") as f:
                files = {"file": f}
                resp = await self.client.post(
                    "/audio/transcriptions",
                    files=files,
                    data=data,
                )
            resp.raise_for_status()
            result = resp.json()
        finally:
            os.unlink(tmp_path)

        latency = (time.perf_counter() - t0) * 1000
        estimated_duration = len(audio_bytes) / 16000  # 16kHz 单声道估算

        return STTResponse(
            text=result.get("text", ""),
            language=result.get("language", request.language),
            duration_seconds=estimated_duration,
            segments=result.get("segments", []),
            latency_ms=latency,
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── 统一语音编排器 ──────────────────────────────

class VoiceOrchestrator:
    """
    语音服务编排器 — STT + TTS 统一入口

    TTS 回退链: OpenAI TTS → Edge TTS（免费兜底）
    STT: OpenAI Whisper（唯一引擎，可扩展本地 Whisper）
    """

    def __init__(self, openai_key: str = ""):
        self._tts_openai = OpenAITTSProvider(openai_key) if openai_key else None
        self._tts_edge = EdgeTTSProvider()
        self._stt = WhisperSTTProvider(openai_key) if openai_key else None

    def tts_available(self) -> bool:
        return (self._tts_openai and self._tts_openai.is_available()) or self._tts_edge.is_available()

    def stt_available(self) -> bool:
        return self._stt is not None and self._stt.is_available()

    async def text_to_speech(self, request: TTSRequest) -> TTSResponse:
        """文字转语音，OpenAI → Edge 回退"""
        if self._tts_openai and self._tts_openai.is_available():
            try:
                return await self._tts_openai.synthesize(request)
            except Exception:
                pass
        return await self._tts_edge.synthesize(request)

    async def speech_to_text(self, request: STTRequest) -> STTResponse:
        """语音转文字"""
        if not self._stt or not self._stt.is_available():
            raise RuntimeError("Whisper STT 不可用，请设置 OPENAI_API_KEY")
        return await self._stt.transcribe(request)

    async def close(self):
        for p in [self._tts_openai, self._tts_edge, self._stt]:
            if p:
                await p.close()
