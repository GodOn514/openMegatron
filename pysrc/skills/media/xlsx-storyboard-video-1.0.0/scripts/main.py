from __future__ import annotations

import html
import json
import re
import sys
import wave
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


WORKBOOK_DEFAULT = (
    r"D:\work\xwechat_files\wxid_8hkxjywbb5x422_4ffe\msg\file\2026-05"
    r"\数智化转型动画_分镜与AI提示词.xlsx"
)

WIDTH = 1920
HEIGHT = 1080

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
RID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def col_to_index(cell_ref: str | None) -> int:
    match = re.match(r"([A-Z]+)", cell_ref or "A1")
    letters = match.group(1) if match else "A"
    value = 0
    for char in letters:
        value = value * 26 + ord(char) - 64
    return value - 1


def xml_text(element: ET.Element) -> str:
    return "".join(t.text or "" for t in element.findall(".//a:t", NS))


def normalize_target(target: str) -> str:
    if target.startswith("/"):
        return target[1:]
    if target.startswith("xl/"):
        return target
    return "xl/" + target


def read_xlsx_rows(path: Path) -> list[tuple[str, list[list[str]]]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared_strings = [xml_text(si) for si in root.findall("a:si", NS)]

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in relationships.findall("pr:Relationship", REL_NS)
        }

        sheets: list[tuple[str, list[list[str]]]] = []
        for sheet in workbook.find("a:sheets", NS).findall("a:sheet", NS):
            target = normalize_target(rel_map[sheet.attrib[RID]])
            root = ET.fromstring(archive.read(target))
            rows: list[list[str]] = []
            for row in root.findall(".//a:sheetData/a:row", NS):
                values: list[str] = []
                for cell in row.findall("a:c", NS):
                    idx = col_to_index(cell.attrib.get("r"))
                    while len(values) < idx:
                        values.append("")
                    cell_type = cell.attrib.get("t")
                    value_el = cell.find("a:v", NS)
                    inline_el = cell.find("a:is", NS)
                    value = ""
                    if cell_type == "s" and value_el is not None and value_el.text is not None:
                        value = shared_strings[int(value_el.text)]
                    elif cell_type == "inlineStr" and inline_el is not None:
                        value = xml_text(inline_el)
                    elif value_el is not None:
                        value = value_el.text or ""
                    values.append(value)
                while values and values[-1] == "":
                    values.pop()
                if any(values):
                    rows.append(values)
            sheets.append((sheet.attrib["name"], rows))
    return sheets


def parse_timecode(value: str) -> float:
    match = re.match(r"(\d\d):(\d\d):(\d\d),(\d\d\d)", value.strip())
    if not match:
        return 0.0
    hours, minutes, seconds, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def safe(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def scene_kind(scene_id: str, title: str, visual: str, caption: str) -> str:
    text = f"{scene_id} {title} {visual} {caption}"
    if scene_id == "3.0-01":
        return "intro"
    if scene_id == "3.0-02":
        return "compass"
    if scene_id.startswith("3.0-"):
        return "principle"
    if scene_id.startswith("3.1-"):
        return "persona"
    if scene_id.startswith("3.2-"):
        return "retail"
    if scene_id.startswith("3.3-"):
        return "process"
    if scene_id.startswith("3.4-"):
        return "dashboard"
    if scene_id.startswith("3.5-"):
        return "lowcode"
    if scene_id.startswith("3.6-"):
        return "iteration"
    if "门店" in text:
        return "retail"
    if "数据" in text:
        return "dashboard"
    return "principle"


def scene_mood(visual: str, caption: str) -> str:
    text = f"{visual} {caption}"
    if "灰色" in text or "旧" in text or "等IT" in text or "扯皮" in text:
        return "old"
    if "彩色" in text or "新" in text or "现在" in text or "未来" in text:
        return "new"
    return "bridge"


def split_caption(caption: str) -> tuple[str, str]:
    if "：" in caption:
        left, right = caption.split("：", 1)
        return left.strip(), right.strip()
    if ":" in caption:
        left, right = caption.split(":", 1)
        return left.strip(), right.strip()
    return caption.strip(), ""


def build_scenes(rows: list[list[str]]) -> list[dict[str, object]]:
    scenes: list[dict[str, object]] = []
    start = 0.0
    for row in rows[1:]:
        values = row + [""] * 11
        duration = float(values[3])
        caption = values[7]
        label, phrase = split_caption(caption)
        scene = {
            "section": values[0],
            "title": values[1],
            "id": values[2],
            "duration": duration,
            "start": round(start, 3),
            "visual": values[4],
            "camera": values[5],
            "motion": values[6],
            "caption": caption,
            "captionLabel": label,
            "captionPhrase": phrase,
            "narration": values[8],
            "kind": scene_kind(values[2], values[1], values[4], caption),
            "mood": scene_mood(values[4], caption),
        }
        scenes.append(scene)
        start += duration
    return scenes


def build_subtitles(rows: list[list[str]]) -> list[dict[str, object]]:
    subtitles: list[dict[str, object]] = []
    for row in rows[1:]:
        values = row + [""] * 5
        start = parse_timecode(values[1])
        end = parse_timecode(values[2])
        if not values[3] or end <= start:
            continue
        subtitles.append(
            {
                "index": values[0],
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": max(0.05, round(end - start - 0.012, 3)),
                "text": values[3].replace("，，", "，"),
                "scene": values[4],
            }
        )
    return subtitles


def visual_intro() -> str:
    return """
      <div class="blueprint visual-piece">
        <div class="blueprint-ring orbit-ring"></div>
        <div class="blueprint-ring ring-two orbit-ring"></div>
        <div class="chapter-mark visual-piece">第三章</div>
        <div class="blueprint-node n1 visual-piece"></div>
        <div class="blueprint-node n2 visual-piece"></div>
        <div class="blueprint-node n3 visual-piece"></div>
      </div>
    """


def visual_compass(active: str = "") -> str:
    terms = ["转意识", "转组织", "转模式", "转方法", "转文化"]
    items = []
    for index, term in enumerate(terms):
        cls = "compass-term visual-piece"
        if active and active in term:
            cls += " active"
        items.append(
            f'<div class="{cls}" style="--i:{index};"><span>{safe(term)}</span></div>'
        )
    return f"""
      <div class="compass-wrap visual-piece">
        <div class="compass-core orbit-ring"></div>
        <div class="compass-inner visual-piece">五转</div>
        {''.join(items)}
      </div>
    """


def visual_persona(mood: str) -> str:
    return f"""
      <div class="persona-board {safe(mood)}">
        <div class="task-stack visual-piece">
          <span>任务清单</span><span>客户拜访</span><span>库存追踪</span>
        </div>
        <div class="person visual-piece">
          <div class="head"></div><div class="body"></div><div class="badge">老张</div>
        </div>
        <div class="upgrade-arrow visual-piece">数据 · 系统 · 敏捷</div>
        <div class="holo-screen visual-piece">
          <div class="kpi-row"><b>区域销量</b><span>+18%</span></div>
          <div class="bar b1"></div><div class="bar b2"></div><div class="bar b3"></div>
          <div class="advisor">领地微型CEO</div>
        </div>
      </div>
    """


def visual_retail(mood: str) -> str:
    return f"""
      <div class="retail-scene {safe(mood)}">
        <div class="shelf visual-piece"><span></span><span></span><span></span><span></span></div>
        <div class="store-owner visual-piece"></div>
        <div class="person small visual-piece"><div class="head"></div><div class="body"></div></div>
        <div class="phone visual-piece">
          <div class="phone-bar"></div><div class="phone-chart"></div><div class="phone-chip">天气</div><div class="phone-chip c2">社区</div>
        </div>
        <div class="promo-tags visual-piece"><span>陈列</span><span>促销</span><span>补货</span></div>
      </div>
    """


def visual_process(mood: str) -> str:
    return f"""
      <div class="process-map {safe(mood)}">
        <div class="doc-cloud visual-piece"><span>订单</span><span>库存</span><span>物流</span></div>
        <div class="flow-line visual-piece"></div>
        <div class="flow-nodes">
          <span class="visual-piece">任务</span><span class="visual-piece">到店</span><span class="visual-piece">盘点</span><span class="visual-piece">补货</span><span class="visual-piece">核销</span>
        </div>
        <button class="report-button visual-piece">一键上报</button>
      </div>
    """


def visual_dashboard(mood: str) -> str:
    return f"""
      <div class="dashboard-ui {safe(mood)}">
        <div class="kpi-card visual-piece"><b>销量趋势</b><span>+12.6%</span></div>
        <div class="kpi-card visual-piece"><b>竞品动态</b><span>周三特价</span></div>
        <div class="chart-panel visual-piece">
          <i style="height:48%"></i><i style="height:72%"></i><i style="height:40%"></i><i style="height:86%"></i><i style="height:66%"></i>
        </div>
        <div class="evidence visual-piece">判断有依据 · 行动有方向</div>
      </div>
    """


def visual_lowcode(mood: str) -> str:
    return f"""
      <div class="lowcode-canvas {safe(mood)}">
        <div class="palette visual-piece"><span>表单</span><span>审批</span><span>通知</span><span>规则</span></div>
        <div class="canvas visual-piece">
          <div class="node">拜访</div><div class="node">盘点</div><div class="node">补货</div><div class="node">复盘</div>
        </div>
        <div class="cursor visual-piece"></div>
        <div class="deploy visual-piece">业务自主配置</div>
      </div>
    """


def visual_iteration(mood: str) -> str:
    return f"""
      <div class="iteration-road {safe(mood)}">
        <div class="app-frame visual-piece"><span>打卡</span><span>拍照</span><span>下单</span></div>
        <div class="release-lane visual-piece">
          <i>V1</i><i>AI识别陈列</i><i>智能补货</i>
        </div>
        <div class="loop-arrow visual-piece">持续迭代</div>
      </div>
    """


def visual_principle(scene: dict[str, object]) -> str:
    active = str(scene["captionLabel"]).replace("转", "")
    return f"""
      <div class="principle-stage">
        {visual_compass(active)}
        <div class="decision-table visual-piece">
          <span>业务主导</span><span>数据看板</span><span>流程协同</span>
        </div>
      </div>
    """


def visual_markup(scene: dict[str, object]) -> str:
    kind = str(scene["kind"])
    mood = str(scene["mood"])
    if kind == "intro":
        return visual_intro()
    if kind == "compass":
        return visual_compass()
    if kind == "principle":
        return visual_principle(scene)
    if kind == "persona":
        return visual_persona(mood)
    if kind == "retail":
        return visual_retail(mood)
    if kind == "process":
        return visual_process(mood)
    if kind == "dashboard":
        return visual_dashboard(mood)
    if kind == "lowcode":
        return visual_lowcode(mood)
    if kind == "iteration":
        return visual_iteration(mood)
    return visual_principle(scene)


def scene_markup(scene: dict[str, object], index: int) -> str:
    scene_num = f"{index:02d}"
    duration = float(scene["duration"])
    return f"""
    <section
      id="scene-{scene_num}"
      class="clip scene scene-{safe(scene['kind'])} mood-{safe(scene['mood'])}"
      data-start="{scene['start']}"
      data-duration="{duration}"
      data-track-index="0"
    >
      <div class="scene-grid" data-layout-ignore></div>
      <div class="data-ribbon ribbon-a visual-piece" data-layout-ignore></div>
      <div class="data-ribbon ribbon-b visual-piece" data-layout-ignore></div>
      <div class="scene-content">
        <header class="scene-header">
          <div class="eyebrow">{safe(scene['id'])}</div>
          <div class="section-title">{safe(scene['title'])}</div>
        </header>
        <main class="scene-main">
          <div class="visual-stage">
            {visual_markup(scene)}
          </div>
          <aside class="copy-panel">
            <div class="copy-kicker">{safe(scene['captionLabel'])}</div>
            <h1 class="copy-title">{safe(scene['captionPhrase'] or scene['caption'])}</h1>
            <p class="copy-visual">{safe(scene['visual'])}</p>
            <div class="motion-row">
              <span>{safe(scene['camera'])}</span>
              <span>{safe(scene['motion'])}</span>
            </div>
          </aside>
        </main>
      </div>
    </section>
    """


def transition_markup(scene: dict[str, object], index: int) -> str:
    end = float(scene["start"]) + float(scene["duration"])
    start = max(0, end - 0.42)
    return f"""
    <div id="transition-{index:02d}" class="clip transition" data-start="{start:.3f}" data-duration="0.84" data-track-index="1" data-layout-allow-overflow>
      <div class="sweep"></div>
      <div class="sparkline"></div>
    </div>
    """


def subtitle_markup(subtitle: dict[str, object], index: int) -> str:
    return f"""
    <div id="subtitle-{index:02d}" class="clip subtitle-clip" data-start="{subtitle['start']}" data-duration="{subtitle['duration']}" data-track-index="3">
      <span>{safe(subtitle['text'])}</span>
    </div>
    """


def css() -> str:
    return """
      @font-face {
        font-family: "VideoSans";
        src: local("Microsoft YaHei UI"), local("Microsoft YaHei"), local("Noto Sans CJK SC");
      }
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body {
        width: 1920px;
        height: 1080px;
        overflow: hidden;
        background: #081529;
        color: #eaf6ff;
        font-family: "VideoSans", sans-serif;
      }
      #root {
        position: relative;
        width: 1920px;
        height: 1080px;
        overflow: hidden;
        background:
          radial-gradient(circle at 18% 18%, rgba(36, 160, 255, 0.20), transparent 33%),
          radial-gradient(circle at 78% 76%, rgba(255, 153, 48, 0.10), transparent 28%),
          #081529;
      }
      .scene {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        overflow: hidden;
        background: #081529;
      }
      .scene-grid {
        position: absolute;
        inset: 0;
        opacity: 0.28;
        background-image:
          linear-gradient(rgba(106, 177, 255, 0.10) 1px, transparent 1px),
          linear-gradient(90deg, rgba(106, 177, 255, 0.10) 1px, transparent 1px);
        background-size: 64px 64px;
      }
      .scene-grid::after {
        content: "";
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at center, transparent 0%, rgba(8, 21, 41, 0.68) 72%);
      }
      .data-ribbon {
        position: absolute;
        width: 520px;
        height: 2px;
        background: linear-gradient(90deg, transparent, rgba(94, 205, 255, 0.70), transparent);
        transform: rotate(-18deg);
      }
      .ribbon-a { left: 118px; top: 168px; }
      .ribbon-b { right: 98px; bottom: 236px; transform: rotate(16deg); background: linear-gradient(90deg, transparent, rgba(255, 176, 67, 0.55), transparent); }
      .scene-content {
        position: relative;
        z-index: 2;
        width: 100%;
        height: 100%;
        padding: 72px 96px 138px;
        display: flex;
        flex-direction: column;
        gap: 42px;
      }
      .scene-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        min-height: 74px;
        gap: 36px;
      }
      .eyebrow {
        min-width: 154px;
        padding: 15px 24px;
        border: 1px solid rgba(104, 205, 255, 0.50);
        border-radius: 999px;
        color: #7ed7ff;
        font-size: 28px;
        font-weight: 800;
        letter-spacing: 0;
        text-align: center;
        background: rgba(9, 43, 78, 0.74);
      }
      .section-title {
        flex: 1;
        color: #d6efff;
        font-size: 36px;
        font-weight: 700;
        text-align: right;
        overflow-wrap: anywhere;
      }
      .scene-main {
        flex: 1;
        min-height: 0;
        display: grid;
        grid-template-columns: minmax(860px, 1.15fr) minmax(560px, 0.85fr);
        gap: 54px;
        align-items: stretch;
      }
      .visual-stage {
        position: relative;
        min-height: 0;
        border: 1px solid rgba(127, 215, 255, 0.26);
        border-radius: 8px;
        background:
          linear-gradient(135deg, rgba(11, 45, 82, 0.86), rgba(10, 27, 52, 0.82)),
          radial-gradient(circle at 50% 40%, rgba(50, 178, 255, 0.20), transparent 55%);
        box-shadow: 0 32px 90px rgba(0, 0, 0, 0.26);
        overflow: hidden;
      }
      .visual-stage::before {
        content: "";
        position: absolute;
        inset: 22px;
        border: 1px solid rgba(144, 225, 255, 0.14);
        border-radius: 6px;
      }
      .copy-panel {
        min-width: 0;
        padding: 42px 46px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        gap: 26px;
        border: 1px solid rgba(176, 226, 255, 0.22);
        border-radius: 8px;
        background: rgba(8, 25, 48, 0.72);
      }
      .copy-kicker {
        color: #ffbc57;
        font-size: 34px;
        font-weight: 800;
        overflow-wrap: anywhere;
      }
      .copy-title {
        color: #f4fbff;
        font-size: 64px;
        line-height: 1.08;
        font-weight: 900;
        letter-spacing: 0;
        overflow-wrap: anywhere;
      }
      .copy-visual {
        color: #b9d5e9;
        font-size: 28px;
        line-height: 1.45;
        font-weight: 400;
        overflow-wrap: anywhere;
      }
      .motion-row {
        display: grid;
        gap: 12px;
      }
      .motion-row span {
        display: block;
        padding: 14px 18px;
        border-radius: 6px;
        color: #d4f2ff;
        font-size: 23px;
        line-height: 1.32;
        background: rgba(90, 186, 255, 0.12);
        border: 1px solid rgba(114, 206, 255, 0.20);
      }
      .mood-old .visual-stage {
        filter: saturate(0.58);
        background: linear-gradient(135deg, rgba(53, 63, 78, 0.92), rgba(22, 31, 45, 0.90));
      }
      .mood-old .copy-kicker { color: #f0786b; }
      .mood-new .visual-stage {
        background:
          radial-gradient(circle at 70% 38%, rgba(255, 176, 67, 0.18), transparent 35%),
          linear-gradient(135deg, rgba(8, 63, 105, 0.90), rgba(8, 28, 58, 0.90));
      }
      .blueprint,
      .compass-wrap,
      .persona-board,
      .retail-scene,
      .process-map,
      .dashboard-ui,
      .lowcode-canvas,
      .iteration-road,
      .principle-stage {
        position: absolute;
        inset: 56px;
      }
      .blueprint-ring {
        position: absolute;
        left: 50%;
        top: 50%;
        width: 520px;
        height: 520px;
        margin-left: -260px;
        margin-top: -260px;
        border: 2px solid rgba(113, 217, 255, 0.55);
        border-radius: 50%;
        box-shadow: 0 0 54px rgba(64, 188, 255, 0.24);
      }
      .ring-two { width: 710px; height: 710px; margin-left: -355px; margin-top: -355px; border-color: rgba(255, 177, 66, 0.38); }
      .chapter-mark {
        position: absolute;
        left: 50%;
        top: 50%;
        width: 420px;
        transform: translate(-50%, -50%);
        color: #f5fbff;
        font-size: 88px;
        line-height: 1;
        font-weight: 900;
        text-align: center;
      }
      .blueprint-node {
        position: absolute;
        width: 138px;
        height: 86px;
        border: 1px solid rgba(126, 215, 255, 0.62);
        border-radius: 8px;
        background: rgba(20, 92, 143, 0.42);
      }
      .n1 { left: 118px; top: 168px; }
      .n2 { right: 142px; top: 236px; }
      .n3 { left: 360px; bottom: 126px; }
      .compass-wrap {
        left: 50%;
        top: 50%;
        width: 640px;
        height: 640px;
        transform: translate(-50%, -50%);
      }
      .compass-core {
        position: absolute;
        inset: 0;
        border-radius: 50%;
        border: 2px solid rgba(126, 215, 255, 0.55);
        background:
          conic-gradient(from 20deg, rgba(55, 176, 255, 0.12), rgba(255, 180, 64, 0.22), rgba(55, 176, 255, 0.12)),
          radial-gradient(circle, rgba(12, 61, 100, 0.92), rgba(8, 26, 50, 0.84) 62%, rgba(7, 19, 38, 0.88));
        box-shadow: inset 0 0 70px rgba(60, 190, 255, 0.16), 0 0 72px rgba(45, 172, 255, 0.18);
      }
      .compass-inner {
        position: absolute;
        left: 50%;
        top: 50%;
        width: 190px;
        height: 190px;
        transform: translate(-50%, -50%);
        border-radius: 50%;
        display: grid;
        place-items: center;
        color: #081529;
        background: #8fddff;
        font-size: 56px;
        font-weight: 900;
      }
      .compass-term {
        position: absolute;
        left: 50%;
        top: 50%;
        width: 174px;
        height: 62px;
        margin-left: -87px;
        margin-top: -31px;
        transform: rotate(calc(var(--i) * 72deg - 90deg)) translateY(-288px) rotate(calc(-1 * (var(--i) * 72deg - 90deg)));
        border-radius: 999px;
        display: grid;
        place-items: center;
        color: #dff8ff;
        font-size: 27px;
        font-weight: 800;
        background: rgba(11, 42, 77, 0.86);
        border: 1px solid rgba(126, 215, 255, 0.42);
      }
      .compass-term.active {
        color: #081529;
        background: #ffbc57;
        border-color: rgba(255, 225, 164, 0.8);
        box-shadow: 0 0 34px rgba(255, 188, 87, 0.38);
      }
      .decision-table {
        position: absolute;
        right: 20px;
        bottom: 42px;
        width: 330px;
        display: grid;
        gap: 12px;
      }
      .decision-table span {
        padding: 16px 20px;
        border-radius: 7px;
        font-size: 25px;
        font-weight: 800;
        color: #eaf9ff;
        background: rgba(84, 188, 255, 0.16);
        border: 1px solid rgba(126, 215, 255, 0.35);
      }
      .persona-board,
      .retail-scene,
      .process-map,
      .dashboard-ui,
      .lowcode-canvas,
      .iteration-road {
        display: grid;
        place-items: center;
      }
      .person {
        position: absolute;
        left: 45%;
        top: 45%;
        width: 170px;
        height: 280px;
        transform: translate(-50%, -50%);
      }
      .person.small { left: 38%; top: 60%; transform: scale(0.78); }
      .head {
        width: 98px;
        height: 98px;
        margin: 0 auto;
        border-radius: 50%;
        background: #ffd9ad;
        border: 7px solid #134c78;
      }
      .body {
        width: 150px;
        height: 160px;
        margin: -4px auto 0;
        border-radius: 48px 48px 18px 18px;
        background: linear-gradient(160deg, #2fb1ff, #0c6ca5);
        border: 7px solid rgba(215, 244, 255, 0.24);
      }
      .badge {
        position: absolute;
        left: 50%;
        bottom: 42px;
        transform: translateX(-50%);
        padding: 9px 18px;
        border-radius: 999px;
        font-size: 24px;
        font-weight: 900;
        color: #08213e;
        background: #ffbc57;
      }
      .task-stack {
        position: absolute;
        left: 72px;
        top: 96px;
        width: 260px;
        display: grid;
        gap: 18px;
      }
      .task-stack span,
      .promo-tags span,
      .palette span,
      .app-frame span {
        padding: 16px 18px;
        border-radius: 7px;
        color: #eaf8ff;
        font-size: 24px;
        font-weight: 800;
        background: rgba(183, 205, 218, 0.18);
        border: 1px solid rgba(204, 226, 240, 0.24);
      }
      .upgrade-arrow {
        position: absolute;
        left: 345px;
        top: 500px;
        width: 420px;
        height: 72px;
        border-radius: 999px;
        display: grid;
        place-items: center;
        color: #081529;
        font-size: 28px;
        font-weight: 900;
        background: linear-gradient(90deg, #6bd6ff, #ffbc57);
      }
      .upgrade-arrow::after {
        content: "";
        position: absolute;
        right: -28px;
        width: 0;
        height: 0;
        border-top: 36px solid transparent;
        border-bottom: 36px solid transparent;
        border-left: 42px solid #ffbc57;
      }
      .holo-screen {
        position: absolute;
        right: 84px;
        top: 116px;
        width: 330px;
        height: 310px;
        padding: 26px;
        border-radius: 8px;
        border: 1px solid rgba(126, 215, 255, 0.45);
        background: rgba(9, 64, 105, 0.72);
        box-shadow: 0 0 48px rgba(86, 205, 255, 0.18);
      }
      .kpi-row { display: flex; justify-content: space-between; font-size: 22px; color: #eaf9ff; }
      .kpi-row span { color: #ffbc57; font-weight: 900; }
      .bar { height: 18px; margin-top: 26px; border-radius: 999px; background: #5fd0ff; }
      .b1 { width: 72%; } .b2 { width: 88%; background: #ffbc57; } .b3 { width: 58%; }
      .advisor { margin-top: 34px; font-size: 28px; font-weight: 900; color: #ffffff; }
      .shelf {
        position: absolute;
        left: 72px;
        bottom: 112px;
        width: 360px;
        height: 320px;
        border-radius: 8px;
        border: 1px solid rgba(126, 215, 255, 0.30);
        background: linear-gradient(#183958 0 22%, transparent 22% 28%, #183958 28% 50%, transparent 50% 56%, #183958 56% 78%, transparent 78%);
      }
      .shelf span {
        position: absolute;
        width: 54px;
        height: 86px;
        bottom: 22px;
        border-radius: 10px 10px 4px 4px;
        background: #ffbc57;
      }
      .shelf span:nth-child(1) { left: 38px; bottom: 34px; }
      .shelf span:nth-child(2) { left: 126px; bottom: 132px; background: #54c9ff; }
      .shelf span:nth-child(3) { left: 220px; bottom: 228px; background: #a4e389; }
      .shelf span:nth-child(4) { left: 284px; bottom: 34px; background: #54c9ff; }
      .store-owner {
        position: absolute;
        left: 455px;
        bottom: 168px;
        width: 118px;
        height: 178px;
        border-radius: 60px 60px 18px 18px;
        background: #ffc48e;
        box-shadow: inset 0 -90px 0 #455b78;
      }
      .phone {
        position: absolute;
        right: 92px;
        top: 96px;
        width: 286px;
        height: 452px;
        border-radius: 34px;
        padding: 34px 24px;
        border: 8px solid #d9f5ff;
        background: #092a4b;
      }
      .phone-bar { height: 18px; width: 46%; margin: 0 auto 34px; border-radius: 999px; background: #7bd8ff; }
      .phone-chart { height: 124px; border-radius: 8px; background: linear-gradient(135deg, rgba(84, 201, 255, 0.30), rgba(255, 188, 87, 0.36)); }
      .phone-chip { margin-top: 24px; padding: 14px; border-radius: 7px; font-size: 22px; font-weight: 900; background: rgba(126, 215, 255, 0.20); }
      .phone-chip.c2 { background: rgba(255, 188, 87, 0.20); }
      .promo-tags {
        position: absolute;
        left: 520px;
        top: 124px;
        display: grid;
        gap: 14px;
      }
      .process-map .doc-cloud {
        position: absolute;
        left: 86px;
        top: 94px;
        width: 260px;
        display: grid;
        gap: 14px;
      }
      .doc-cloud span {
        padding: 18px 20px;
        border-radius: 6px;
        color: #ffe4e0;
        font-size: 25px;
        background: rgba(220, 85, 76, 0.24);
        border: 1px solid rgba(255, 130, 115, 0.34);
      }
      .flow-line {
        position: absolute;
        left: 250px;
        right: 180px;
        top: 50%;
        height: 8px;
        border-radius: 999px;
        background: linear-gradient(90deg, #ff8c78, #6ed6ff, #ffbc57);
      }
      .flow-nodes {
        position: absolute;
        left: 310px;
        right: 150px;
        top: calc(50% - 54px);
        display: flex;
        justify-content: space-between;
      }
      .flow-nodes span {
        width: 106px;
        height: 106px;
        border-radius: 50%;
        display: grid;
        place-items: center;
        color: #081529;
        font-size: 24px;
        font-weight: 900;
        background: #7ed7ff;
        border: 6px solid rgba(255, 255, 255, 0.28);
      }
      .report-button {
        position: absolute;
        right: 92px;
        bottom: 112px;
        width: 220px;
        height: 76px;
        border: 0;
        border-radius: 999px;
        color: #081529;
        background: #ffbc57;
        font-size: 30px;
        font-weight: 900;
      }
      .dashboard-ui {
        grid-template-columns: repeat(2, minmax(220px, 1fr));
        grid-template-rows: 150px 1fr 92px;
        gap: 24px;
        padding: 72px;
      }
      .kpi-card,
      .chart-panel,
      .evidence {
        width: 100%;
        height: 100%;
        border-radius: 8px;
        border: 1px solid rgba(126, 215, 255, 0.30);
        background: rgba(10, 54, 91, 0.68);
      }
      .kpi-card { padding: 26px; }
      .kpi-card b { display: block; color: #bfeeff; font-size: 25px; }
      .kpi-card span { display: block; margin-top: 16px; color: #ffbc57; font-size: 44px; font-weight: 900; }
      .chart-panel {
        grid-column: 1 / 3;
        padding: 32px 42px;
        display: flex;
        align-items: flex-end;
        justify-content: space-around;
      }
      .chart-panel i {
        display: block;
        width: 76px;
        border-radius: 8px 8px 0 0;
        background: linear-gradient(#ffbc57, #57cbff);
      }
      .evidence {
        grid-column: 1 / 3;
        display: grid;
        place-items: center;
        color: #eaf9ff;
        font-size: 32px;
        font-weight: 900;
      }
      .lowcode-canvas {
        grid-template-columns: 220px 1fr;
        gap: 28px;
        padding: 74px;
      }
      .palette {
        display: grid;
        gap: 16px;
        align-content: center;
      }
      .canvas {
        position: relative;
        width: 100%;
        height: 100%;
        min-height: 440px;
        border-radius: 8px;
        border: 1px solid rgba(126, 215, 255, 0.28);
        background: rgba(9, 42, 74, 0.74);
      }
      .node {
        position: absolute;
        width: 150px;
        height: 78px;
        border-radius: 8px;
        display: grid;
        place-items: center;
        color: #08213e;
        font-size: 25px;
        font-weight: 900;
        background: #7ed7ff;
      }
      .node:nth-child(1) { left: 78px; top: 68px; }
      .node:nth-child(2) { left: 282px; top: 178px; background: #ffbc57; }
      .node:nth-child(3) { right: 180px; top: 104px; }
      .node:nth-child(4) { right: 84px; bottom: 72px; background: #a4e389; }
      .cursor {
        position: absolute;
        right: 190px;
        top: 238px;
        width: 0;
        height: 0;
        border-left: 38px solid #ffffff;
        border-top: 58px solid transparent;
        filter: drop-shadow(0 8px 10px rgba(0, 0, 0, 0.30));
      }
      .deploy {
        position: absolute;
        right: 92px;
        bottom: 92px;
        padding: 18px 26px;
        border-radius: 999px;
        color: #081529;
        font-size: 28px;
        font-weight: 900;
        background: #ffbc57;
      }
      .iteration-road {
        padding: 80px;
      }
      .app-frame {
        position: absolute;
        left: 108px;
        top: 118px;
        width: 280px;
        height: 500px;
        padding: 80px 28px 28px;
        border-radius: 34px;
        border: 8px solid #d9f5ff;
        background: #092a4b;
        display: grid;
        gap: 18px;
        align-content: start;
      }
      .release-lane {
        position: absolute;
        left: 390px;
        right: 36px;
        top: 210px;
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 12px;
      }
      .release-lane i {
        min-width: 116px;
        min-height: 92px;
        padding: 16px 14px;
        border-radius: 8px;
        display: grid;
        place-items: center;
        color: #08213e;
        font-size: 22px;
        line-height: 1.18;
        text-align: center;
        font-style: normal;
        font-weight: 900;
        background: #7ed7ff;
      }
      .release-lane i:nth-child(2) { min-height: 150px; background: #ffbc57; }
      .release-lane i:nth-child(3) { min-height: 210px; background: #a4e389; }
      .loop-arrow {
        position: absolute;
        right: 120px;
        bottom: 118px;
        width: 300px;
        height: 92px;
        border-radius: 999px;
        display: grid;
        place-items: center;
        color: #081529;
        font-size: 32px;
        font-weight: 900;
        background: linear-gradient(90deg, #7ed7ff, #ffbc57);
      }
      .subtitle-clip {
        position: absolute;
        z-index: 8;
        left: 160px;
        right: 160px;
        bottom: 46px;
        min-height: 84px;
        display: grid;
        place-items: center;
        padding: 18px 34px;
        border-radius: 8px;
        background: rgba(5, 13, 27, 0.76);
        border: 1px solid rgba(135, 218, 255, 0.22);
      }
      .subtitle-clip span {
        color: #f5fbff;
        font-size: 35px;
        line-height: 1.34;
        font-weight: 700;
        text-align: center;
        text-shadow: 0 2px 8px rgba(0, 0, 0, 0.62);
        overflow-wrap: anywhere;
      }
      .transition {
        position: absolute;
        inset: 0;
        z-index: 7;
        pointer-events: none;
        overflow: hidden;
      }
      .sweep {
        position: absolute;
        inset: 0;
        transform: translateX(-120%);
        background: linear-gradient(100deg, transparent 0 18%, rgba(126, 215, 255, 0.96) 34%, #ffbc57 52%, rgba(8, 21, 41, 0.98) 70%, transparent 88%);
      }
      .sparkline {
        position: absolute;
        left: 220px;
        right: 220px;
        top: 50%;
        height: 4px;
        transform-origin: left center;
        background: #ffffff;
        box-shadow: 0 0 22px rgba(255, 255, 255, 0.8);
      }
    """


def build_html(scenes: list[dict[str, object]], subtitles: list[dict[str, object]]) -> str:
    total_duration = max(
        float(scenes[-1]["start"]) + float(scenes[-1]["duration"]),
        max(float(s["end"]) for s in subtitles) + 2,
    )
    scene_html = "\n".join(scene_markup(scene, i) for i, scene in enumerate(scenes))
    transition_html = "\n".join(
        transition_markup(scene, i) for i, scene in enumerate(scenes[:-1])
    )
    subtitle_html = "\n".join(
        subtitle_markup(subtitle, i) for i, subtitle in enumerate(subtitles)
    )
    scenes_json = json.dumps(scenes, ensure_ascii=False)
    subtitles_json = json.dumps(subtitles, ensure_ascii=False)
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={WIDTH}, height={HEIGHT}" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
{css()}
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-start="0"
      data-duration="{total_duration:.3f}"
      data-width="{WIDTH}"
      data-height="{HEIGHT}"
    >
      <audio
        id="narration"
        src="assets/narration_fit.wav"
        data-start="0"
        data-duration="{total_duration:.3f}"
        data-track-index="4"
        data-volume="1"
      ></audio>
      {scene_html}
      {transition_html}
      {subtitle_html}
    </div>

    <script>
      const scenes = {scenes_json};
      const subtitles = {subtitles_json};
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      scenes.forEach((scene, index) => {{
        const id = `#scene-${{String(index).padStart(2, "0")}}`;
        const start = scene.start;
        const duration = scene.duration;
        tl.from(`${{id}} .eyebrow`, {{ x: -38, opacity: 0, duration: 0.46, ease: "power3.out" }}, start + 0.18);
        tl.from(`${{id}} .section-title`, {{ x: 46, opacity: 0, duration: 0.50, ease: "expo.out" }}, start + 0.24);
        tl.from(`${{id}} .visual-stage`, {{ y: 28, scale: 0.97, opacity: 0, duration: 0.58, ease: "back.out(1.4)" }}, start + 0.34);
        tl.from(`${{id}} .copy-kicker`, {{ y: 26, opacity: 0, duration: 0.44, ease: "power2.out" }}, start + 0.46);
        tl.from(`${{id}} .copy-title`, {{ y: 34, opacity: 0, duration: 0.55, ease: "circ.out" }}, start + 0.58);
        tl.from(`${{id}} .copy-visual`, {{ y: 22, opacity: 0, duration: 0.46, ease: "sine.out" }}, start + 0.75);
        tl.from(`${{id}} .motion-row`, {{ y: 18, opacity: 0, duration: 0.42, ease: "power1.out" }}, start + 0.92);
        tl.from(`${{id}} .visual-piece`, {{ y: 24, scale: 0.96, opacity: 0, duration: 0.48, stagger: 0.055, ease: "expo.out" }}, start + 0.52);
        const sceneEl = document.getElementById(`scene-${{String(index).padStart(2, "0")}}`);
        if (sceneEl && sceneEl.querySelector(".orbit-ring")) {{
          tl.to(`${{id}} .orbit-ring`, {{ rotation: 120, duration: Math.max(1, duration - 0.9), ease: "none" }}, start + 0.45);
        }}
        tl.to(`${{id}} .data-ribbon`, {{ x: 90, duration: Math.max(1, duration - 0.8), ease: "sine.inOut" }}, start + 0.4);
      }});
      scenes.slice(0, -1).forEach((scene, index) => {{
        const end = scene.start + scene.duration;
        const id = `#transition-${{String(index).padStart(2, "0")}}`;
        tl.fromTo(`${{id}} .sweep`, {{ xPercent: -122 }}, {{ xPercent: 122, duration: 0.84, ease: "power3.inOut" }}, end - 0.42);
        tl.fromTo(`${{id}} .sparkline`, {{ scaleX: 0, opacity: 0 }}, {{ scaleX: 1, opacity: 1, duration: 0.28, ease: "expo.out" }}, end - 0.31);
      }});
      subtitles.forEach((subtitle, index) => {{
        const id = `#subtitle-${{String(index).padStart(2, "0")}}`;
        tl.from(id, {{ y: 18, opacity: 0, duration: 0.18, ease: "power2.out" }}, subtitle.start + 0.02);
      }});
      const finalStart = scenes[scenes.length - 1].start + scenes[scenes.length - 1].duration - 0.82;
      tl.to("#scene-24 .scene-content", {{ opacity: 0, y: -18, duration: 0.72, ease: "power2.in" }}, finalStart);
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""


def write_design(project_dir: Path, overview_rows: list[list[str]]) -> None:
    overview = {row[0]: row[1] for row in overview_rows if len(row) >= 2}
    design = f"""# 数智化转型动画 Visual Identity

## Style Prompt

{overview.get("统一视觉风格", "2.5D扁平卡通 + 轻科幻数据可视化；科技蓝为主色，橙色用于高亮行动。")}

## Colors

- Background: `#081529` 深蓝科技底色
- Panel: `#0b2d52` 半透明数据面板
- Primary Accent: `#7ed7ff` 数据流与高亮线
- Action Accent: `#ffbc57` 行动、转变和关键按钮
- Old Mode: `#3d4655` 灰度低饱和旧模式

## Typography

- Chinese UI and captions: Microsoft YaHei UI / Microsoft YaHei / Noto Sans SC
- Headings use heavy weight, subtitles use high-contrast bold text with safe bottom area.

## What NOT to Do

- 不生成真实品牌 LOGO 或水印。
- 不在画面中堆叠过多文字，字幕统一由后期轨道承载。
- 旧模式保持低饱和，新模式保持明亮但不过度霓虹。
- 所有镜头保持 16:9 横版与底部字幕安全区。
"""
    (project_dir / "DESIGN.md").write_text(design, encoding="utf-8")


def parse_cli_args() -> dict[str, object]:
    if len(sys.argv) <= 1:
        return {}
    raw = sys.argv[1]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"workbook_path": raw}


def write_silent_wav(path: Path, duration: float, sample_rate: int = 24000) -> None:
    frame_count = max(1, int(duration * sample_rate))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        chunk = b"\x00\x00" * sample_rate
        full_chunks, remainder = divmod(frame_count, sample_rate)
        for _ in range(full_chunks):
            wav.writeframes(chunk)
        if remainder:
            wav.writeframes(b"\x00\x00" * remainder)


def main() -> int:
    args = parse_cli_args()
    workbook_value = args.get("workbook_path") or args.get("xlsx_path") or args.get("path")
    if not workbook_value:
        print(json.dumps({
            "status": "error",
            "completed": False,
            "message": "Missing required workbook_path."
        }, ensure_ascii=False))
        return 2
    workbook = Path(str(workbook_value)).expanduser()
    if not workbook.exists():
        print(json.dumps({
            "status": "error",
            "completed": False,
            "message": f"Workbook not found: {workbook}"
        }, ensure_ascii=False))
        return 2

    output_dir = Path(str(args.get("output_dir") or Path.cwd() / "generated-videos")).expanduser()
    project_name = str(args.get("project_name") or workbook.stem or "xlsx-storyboard-video")
    project_name = re.sub(r"[^a-zA-Z0-9._\-\u4e00-\u9fff]+", "-", project_name).strip("-") or "xlsx-storyboard-video"
    project_dir = output_dir / project_name
    assets_dir = project_dir / "assets"
    renders_dir = project_dir / "renders"
    assets_dir.mkdir(parents=True, exist_ok=True)
    renders_dir.mkdir(parents=True, exist_ok=True)

    sheets = read_xlsx_rows(workbook)
    overview_rows = sheets[0][1]
    shot_rows = sheets[1][1]
    subtitle_rows = sheets[3][1]

    scenes = build_scenes(shot_rows)
    subtitles = build_subtitles(subtitle_rows)
    total_duration = float(scenes[-1]["start"]) + float(scenes[-1]["duration"])

    write_design(project_dir, overview_rows)
    (assets_dir / "scenes.json").write_text(
        json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (assets_dir / "subtitles.json").write_text(
        json.dumps(subtitles, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    narration_text = "\n".join(str(item["text"]) for item in subtitles)
    (assets_dir / "narration.txt").write_text(narration_text, encoding="utf-8")
    write_silent_wav(assets_dir / "narration_fit.wav", total_duration)
    (project_dir / "index.html").write_text(build_html(scenes, subtitles), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "success",
                "completed": True,
                "project": str(project_dir),
                "scenes": len(scenes),
                "subtitles": len(subtitles),
                "duration": total_duration,
                "index": str(project_dir / "index.html"),
                "narration_text": str(assets_dir / "narration.txt"),
                "silent_audio": str(assets_dir / "narration_fit.wav"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
