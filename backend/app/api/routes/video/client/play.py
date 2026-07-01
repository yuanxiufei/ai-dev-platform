"""
Video — C端播放 API

提供视频播放相关功能：
  - 播放信息（文件URL + 元数据）
  - 增加观看计数
  - 字幕获取（多语言 SRT/VTT 支持）
  - 字幕上传与解析
"""

import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from sqlmodel import select

from app.api.deps import SessionDep, CurrentUser, commit_or_rollback
from app.models.video_models import VideoAsset, VideoSubtitle, SubtitleCue
from app.api.routes.video.client.subtitle_parser import (
    parse_subtitle_file,
    detect_format,
)

# 字幕片段每页最大条数
_MAX_SUBTITLE_CUES = 5000

router = APIRouter(prefix="/videos", tags=["video-play"])


@router.get("/{video_id}/play")
def get_play_info(
    video_id: uuid.UUID,
    session: SessionDep,
):
    """获取视频播放信息"""
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if not video.is_public:
        raise HTTPException(status_code=403, detail="Video is not public")

    # 增加观看次数
    video.view_count += 1
    session.add(video)
    commit_or_rollback(session)

    return {
        "id": str(video.id),
        "title": video.title,
        "description": video.description,
        "file_path": video.file_path,
        "thumbnail_path": video.thumbnail_path,
        "duration": video.duration,
        "tags": video.tags,
        "view_count": video.view_count,
        "created_at": video.created_at.isoformat(),
    }


@router.get("/{video_id}/subtitles")
def get_subtitles(
    video_id: uuid.UUID,
    session: SessionDep,
    lang: str = Query("zh", description="字幕语言代码, 如 zh/en/ja"),
    with_cues: bool = Query(False, description="是否返回逐条字幕片段"),
):
    """获取视频字幕 — 支持多语言 SRT/VTT

    返回视频指定语言的字幕数据。若 with_cues=True 则同时返回
    分条字幕片段（按时间排序），适用于播放器逐句渲染。
    """
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # 查找匹配语言的字幕
    subtitle = session.exec(
        select(VideoSubtitle).where(
            VideoSubtitle.video_id == video_id,
            VideoSubtitle.language == lang,
        )
    ).first()

    if not subtitle:
        # 回退：尝试任一可用语言
        subtitle = session.exec(
            select(VideoSubtitle).where(
                VideoSubtitle.video_id == video_id,
            ).limit(1)
        ).first()

    if not subtitle:
        return {
            "video_id": str(video.id),
            "language": lang,
            "subtitles": [],
            "message": "No subtitles available for this video",
        }

    result = {
        "video_id": str(video.id),
        "language": subtitle.language,
        "format": subtitle.format,
        "source": subtitle.source,
        "subtitles": [],
    }

    if with_cues:
        cues = session.exec(
            select(SubtitleCue)
            .where(SubtitleCue.subtitle_id == subtitle.id)
            .order_by(SubtitleCue.sequence)
            .limit(_MAX_SUBTITLE_CUES)
        ).all()

        result["subtitles"] = [
            {
                "sequence": c.sequence,
                "start_time": c.start_time,
                "end_time": c.end_time,
                "text": c.text,
            }
            for c in cues
        ]
    else:
        result["content"] = subtitle.content

    return result


@router.post("/{video_id}/subtitles/upload")
async def upload_subtitle(
    video_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    file: UploadFile = File(..., description="字幕文件 (.srt/.vtt/.ass)"),
    language: str = Query("zh", description="语言代码"),
):
    """上传字幕文件 — 自动解析 SRT/VTT/ASS 并存入数据库

    解析后的字幕会存储全文和逐条片段，用于播放器同步渲染。
    """
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # 格式检测
    fmt = detect_format(file.filename or "subtitle.srt")
    raw_content = (await file.read()).decode("utf-8")

    # 解析字幕
    cues = parse_subtitle_file(raw_content, fmt)
    if not cues:
        raise HTTPException(status_code=400, detail="Failed to parse subtitle file (no cues found)")

    # 存入 VideoSubtitle
    from datetime import datetime, timezone

    subtitle = VideoSubtitle(
        video_id=video_id,
        language=language,
        format=fmt,
        content=raw_content,
        source="manual",
    )
    session.add(subtitle)
    session.flush()  # 获取 subtitle.id

    # 逐条存入 SubtitleCue
    for cue in cues:
        session.add(SubtitleCue(
            subtitle_id=subtitle.id,
            sequence=cue["sequence"],
            start_time=cue["start_time"],
            end_time=cue["end_time"],
            text=cue["text"],
        ))

    commit_or_rollback(session)

    return {
        "video_id": str(video.id),
        "subtitle_id": str(subtitle.id),
        "language": language,
        "format": fmt,
        "cue_count": len(cues),
        "message": f"Subtitle uploaded and parsed: {len(cues)} cues",
    }


@router.delete("/{video_id}/subtitles/{language}")
def delete_subtitle(
    video_id: uuid.UUID,
    language: str,
    session: SessionDep,
    current_user: CurrentUser,
):
    """删除指定语言的字幕"""
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    subtitle = session.exec(
        select(VideoSubtitle).where(
            VideoSubtitle.video_id == video_id,
            VideoSubtitle.language == language,
        )
    ).first()

    if not subtitle:
        raise HTTPException(status_code=404, detail="Subtitle not found")

    # CASCADE 会自动删除关联的 SubtitleCue
    session.delete(subtitle)
    commit_or_rollback(session)

    return {"video_id": str(video_id), "language": language, "message": "Subtitle deleted"}


@router.get("/{video_id}/subtitles/languages")
def list_subtitle_languages(
    video_id: uuid.UUID,
    session: SessionDep,
):
    """列出视频所有可用字幕语言"""
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    subtitles = session.exec(
        select(VideoSubtitle).where(VideoSubtitle.video_id == video_id)
        .limit(100)  # 每视频字幕语言最多 100 种
    ).all()

    return {
        "video_id": str(video.id),
        "languages": [
            {"language": s.language, "format": s.format, "source": s.source}
            for s in subtitles
        ],
    }
