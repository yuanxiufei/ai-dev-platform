"""
语音 API — TTS 文字转语音 + STT 语音转文字

借鉴 Open WebUI Audio 集成
路径: /voice/*
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.providers.voice import (
    VoiceOrchestrator,
    TTSRequest,
    TTSResponse,
    STTRequest,
    STTResponse,
    TTSVoice,
    VoiceFormat,
)

router = APIRouter(prefix="/voice", tags=["Voice (TTS/STT)"])


# ── Request Models ────────────────────────────────

class TTSRequestModel(BaseModel):
    """TTS 请求"""
    text: str = Field(..., min_length=1, max_length=4096, description="要合成的文本")
    voice: TTSVoice = Field(default=TTSVoice.NOVA, description="语音角色")
    format: VoiceFormat = Field(default=VoiceFormat.MP3, description="音频格式")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="语速倍率")
    model: str = Field(default="tts-1", description="TTS 模型 (tts-1|tts-1-hd)")


class STTFormRequest(BaseModel):
    """STT 表单请求（通过 URL）"""
    audio_url: str = Field(..., description="音频文件 URL")
    language: str = Field(default="", description="语言代码")
    prompt: str = Field(default="", description="引导词")


# ── 全局 orchestrator ───────────────────────────

_orchestrator: VoiceOrchestrator | None = None


def get_orchestrator() -> VoiceOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = VoiceOrchestrator(openai_key=settings.OPENAI_API_KEY)
    return _orchestrator


# ── TTS Routes ────────────────────────────────────

@router.post("/tts")
async def text_to_speech(req: TTSRequestModel) -> dict[str, Any]:
    """文字转语音"""
    orch = get_orchestrator()
    if not orch.tts_available():
        raise HTTPException(status_code=503, detail="TTS 服务不可用")

    tts_req = TTSRequest(
        text=req.text,
        voice=req.voice,
        format=req.format,
        speed=req.speed,
        model=req.model,
    )

    try:
        result = await orch.text_to_speech(tts_req)
        return {
            "audio_base64": result.audio_base64,
            "audio_url": result.audio_url,
            "format": result.format,
            "duration_seconds": result.duration_seconds,
            "latency_ms": result.latency_ms,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS 合成失败: {e}")


@router.get("/tts/stream")
async def text_to_speech_stream(
    text: str = Query(..., min_length=1, max_length=4096),
    voice: str = Query(default="nova"),
    format: str = Query(default="mp3"),
    speed: float = Query(default=1.0, ge=0.25, le=4.0),
):
    """Stream TTS — 直接返回音频流"""
    from fastapi.responses import Response
    orch = get_orchestrator()

    try:
        voice_enum = TTSVoice(voice)
    except ValueError:
        voice_enum = TTSVoice.NOVA

    tts_req = TTSRequest(text=text, voice=voice_enum, speed=speed)
    result = await orch.text_to_speech(tts_req)
    audio_bytes = base64.b64decode(result.audio_base64)

    media_type = {
        "mp3": "audio/mpeg",
        "opus": "audio/opus",
        "aac": "audio/aac",
        "flac": "audio/flac",
        "wav": "audio/wav",
        "pcm": "audio/pcm",
    }.get(format, "audio/mpeg")

    return Response(content=audio_bytes, media_type=media_type)


@router.get("/voices")
async def list_voices() -> dict[str, Any]:
    """列出可用的 TTS 语音"""
    edge_voices = [
        {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓 (中文女声)", "locale": "zh-CN", "gender": "female"},
        {"id": "zh-CN-YunxiNeural", "name": "云溪 (中文男声)", "locale": "zh-CN", "gender": "male"},
        {"id": "en-US-AriaNeural", "name": "Aria (English)", "locale": "en-US", "gender": "female"},
        {"id": "en-US-GuyNeural", "name": "Guy (English)", "locale": "en-US", "gender": "male"},
    ]
    openai_voices = [
        {"id": "alloy", "name": "Alloy (中性)", "locale": "en-US", "gender": "neutral"},
        {"id": "echo", "name": "Echo (男声)", "locale": "en-US", "gender": "male"},
        {"id": "fable", "name": "Fable (英式)", "locale": "en-GB", "gender": "male"},
        {"id": "nova", "name": "Nova (女声)", "locale": "en-US", "gender": "female"},
        {"id": "onyx", "name": "Onyx (深沉)", "locale": "en-US", "gender": "male"},
        {"id": "shimmer", "name": "Shimmer (温暖)", "locale": "en-US", "gender": "female"},
    ]
    return {"edge_tts": edge_voices, "openai_tts": openai_voices}


# ── STT Routes ────────────────────────────────────

@router.post("/stt")
async def speech_to_text(
    file: UploadFile = File(...),
    language: str = Form(default=""),
    prompt: str = Form(default=""),
) -> dict[str, Any]:
    """
    语音转文字 — 上传音频文件
    
    支持格式: mp3, wav, flac, ogg, m4a, webm
    """
    orch = get_orchestrator()
    if not orch.stt_available():
        raise HTTPException(status_code=503, detail="STT 服务不可用（需要 OPENAI_API_KEY）")

    # 校验文件类型
    allowed_types = {"audio/mpeg", "audio/wav", "audio/flac", "audio/ogg",
                     "audio/mp4", "audio/webm", "audio/x-m4a"}
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"不支持的音频格式: {file.content_type}")

    audio_bytes = await file.read()
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

    stt_req = STTRequest(
        audio_base64=audio_b64,
        language=language,
        prompt=prompt,
    )

    try:
        result = await orch.speech_to_text(stt_req)
        return {
            "text": result.text,
            "language": result.language,
            "duration_seconds": result.duration_seconds,
            "segments": result.segments,
            "latency_ms": result.latency_ms,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT 转录失败: {e}")


@router.post("/stt/url")
async def speech_to_text_url(req: STTFormRequest) -> dict[str, Any]:
    """语音转文字 — 通过 URL"""
    orch = get_orchestrator()
    if not orch.stt_available():
        raise HTTPException(status_code=503, detail="STT 服务不可用（需要 OPENAI_API_KEY）")

    stt_req = STTRequest(
        audio_url=req.audio_url,
        language=req.language,
        prompt=req.prompt,
    )

    try:
        result = await orch.speech_to_text(stt_req)
        return {
            "text": result.text,
            "language": result.language,
            "duration_seconds": result.duration_seconds,
            "segments": result.segments,
            "latency_ms": result.latency_ms,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STT 转录失败: {e}")


@router.get("/tts/status")
async def voice_status() -> dict[str, Any]:
    """检查语音服务状态"""
    orch = get_orchestrator()
    return {
        "tts_available": orch.tts_available(),
        "stt_available": orch.stt_available(),
        "providers": {
            "tts": ["openai", "edge"] if orch.tts_available() else [],
            "stt": ["whisper"] if orch.stt_available() else [],
        },
    }
