---
name: download-video
description: Download video/audio from a URL.
parameters:
  url:
    type: string
    description: Full video URL.
    required: true
  output_dir:
    type: string
    description: Save folder path.
    required: false
  max_height:
    type: integer
    description: Max video height (e.g., 1080, 720).
    required: false
  audio_only:
    type: boolean
    description: Extract audio as MP3.
    required: false
  subs:
    type: boolean
    description: Download subtitles.
    required: false
  cookies:
    type: string
    description: Browser cookies (chrome, edge, firefox).
    required: false
---

## RULES

1. Output EXACTLY AND ONLY a valid JSON object.
2. NO markdown formatting, NO code blocks (do not use ```), NO conversational text before or after the JSON.
3. If the URL contains "bilibili.com", you MUST set "cookies": "chrome" by default, UNLESS the user explicitly mentions "edge" or "firefox".
4. If the user specifies a resolution (e.g., "720p"), set `max_height` to the number (e.g., 720).
5. If the user asks for audio or mp3, set `audio_only: true`.
6. Omit optional parameters if not requested.

## EXAMPLES

User: Download a bilibili video https://www.bilibili.com/video/BV1xx
{"url": "https://www.bilibili.com/video/BV1xx", "cookies": "chrome"}

User: 下载B站视频，用 edge 的 cookie: https://www.bilibili.com/video/BV1xx
{"url": "https://www.bilibili.com/video/BV1xx", "cookies": "edge"}

User: Download https://youtu.be/abc in 720p to D:/Videos
{"url": "https://youtu.be/abc", "output_dir": "D:/Videos", "max_height": 720}

User: Get audio from https://www.bilibili.com/video/BV1xx
{"url": "https://www.bilibili.com/video/BV1xx", "audio_only": true, "cookies": "chrome"}