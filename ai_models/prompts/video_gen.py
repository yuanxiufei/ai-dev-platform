"""
Prompt templates for video generation tasks.

模板变量说明：
  - TEXT_TO_VIDEO        : {prompt}, {duration}, {style}, {resolution}
  - UI_DEMO_VIDEO        : {ui_description}, {duration}
  - VIDEO_STYLE_TEMPLATES: 预设风格描述 dict，key 为风格名称，value 为风格描述文本

Usage:
    from ai_models.prompts.video_gen import TEXT_TO_VIDEO, VIDEO_STYLE_TEMPLATES
    prompt = TEXT_TO_VIDEO.format(
        prompt="sunset over mountains",
        duration=6,
        style=VIDEO_STYLE_TEMPLATES["cinematic"],
        resolution="720x480"
    )
"""

# -- 文本 → 视频 --
# 变量：{prompt} - 视频内容描述
#       {duration} - 视频时长（秒）
#       {style} - 风格描述，推荐用 VIDEO_STYLE_TEMPLATES 中的值
#       {resolution} - 分辨率（如 "720x480"）
TEXT_TO_VIDEO = """Generate a video that visualizes the following scene:

{prompt}

Additional settings:
- Duration: {duration} seconds
- Style: {style}
- Resolution: {resolution}"""

# -- UI 演示视频 --
# 变量：{ui_description} - UI 代码/描述
#       {duration} - 视频时长（秒）
UI_DEMO_VIDEO = """Create a product demo video showcasing the following UI:

{ui_description}

Requirements:
- Duration: {duration} seconds
- Show smooth transitions between states
- Highlight key interactions
- Include subtle animations
- Professional, clean aesthetic"""

# -- 视频风格描述 --
# 可通过 generate_video(style=VIDEO_STYLE_TEMPLATES["cinematic"]) 使用
# 也可自定义风格文本
VIDEO_STYLE_TEMPLATES = {
    "cinematic": "Cinematic style with dramatic lighting, smooth camera movements, film grain, 24fps look",
    "animation": "2D animation style, vibrant colors, smooth motion, 12fps hand-drawn feel",
    "product_demo": "Clean product demo style, soft lighting, centered composition, minimal background",
    "tutorial": "Screencast tutorial style, clear annotations, highlighted cursor, step-by-step flow",
}

__all__ = [
    "TEXT_TO_VIDEO",
    "UI_DEMO_VIDEO",
    "VIDEO_STYLE_TEMPLATES",
]
