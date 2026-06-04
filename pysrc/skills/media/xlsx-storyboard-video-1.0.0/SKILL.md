---
name: xlsx_storyboard_video
description: Convert an Excel storyboard workbook with scene rows and SRT subtitle rows into a HyperFrames video project for corporate training or explainer animations.
category: media
entry_function: main
parameters:
  type: object
  properties:
    workbook_path:
      type: string
      description: Path to the .xlsx storyboard workbook.
    output_dir:
      type: string
      description: Directory where the generated HyperFrames project should be created.
    project_name:
      type: string
      description: Optional project folder name; defaults to the workbook stem.
  required:
    - workbook_path
keywords: [xlsx, storyboard, 分镜, 字幕, srt, hyperframes, video, training, animation]
produces:
  project_dir: HyperFrames project folder with index.html, DESIGN.md, scenes.json, subtitles.json, narration.txt, and silent narration_fit.wav.
side_effects:
  - Creates a project folder under output_dir.
  - Does not render MP4 by itself; render with HyperFrames after optional narration replacement.
risk: low
---

# XLSX Storyboard Video

Use this skill when the user provides an Excel storyboard and asks to generate a video, animation draft, corporate training clip, or HyperFrames project from it.

## Expected Workbook

The source workbook should follow the layout used by `数智化转型动画_分镜与AI提示词.xlsx`:

- Sheet 1: overview and visual style rows.
- Sheet 2: storyboard rows with scene id, title, shot id, duration, visual design, camera motion, animation/transition, screen copy, narration, audio notes, and production notes.
- Sheet 4: SRT-style subtitle rows with index, start time, end time, subtitle text, and scene.

The script reads raw XLSX XML directly, so it can handle workbooks where `openpyxl` fails because of duplicate Excel table names.

## Workflow

1. Run the skill script with `workbook_path`, plus `output_dir` and `project_name` if desired.
2. Inspect the generated `DESIGN.md`, `assets/scenes.json`, `assets/subtitles.json`, and `index.html`.
3. Replace `assets/narration_fit.wav` with real narration if needed. The script creates a silent WAV placeholder so HyperFrames can render immediately.
4. Run HyperFrames validation from the generated project:
   - `npx hyperframes lint --json`
   - `npx hyperframes inspect --json --at <key timestamps>`
5. Render:
   - `npx hyperframes render --output renders/final.mp4 --fps 30 --quality standard --workers 2`
6. Verify with `ffprobe` and representative `ffmpeg` screenshots/contact sheet.

## Practical Notes

- Prefer the bundled Node runtime if system Node is below v22.
- If the HyperFrames cached headless shell is corrupt or unavailable, set `HYPERFRAMES_BROWSER_PATH` to a local Chrome executable and rerun inspect/render.
- For Chinese narration on Windows, `System.Speech.Synthesis.SpeechSynthesizer` with `Microsoft Huihui Desktop` is a stable offline fallback.
- If generated copy appears invisible or clipped, check for animation conflicts on shared classes and rerun `hyperframes inspect`.
