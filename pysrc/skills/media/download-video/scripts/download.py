#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
import json
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

DEFAULT_OUTPUT_DIR = "~/Downloads/Videos"

def sanitize_filename(name, max_len=80):
    try:
        name = os.path.basename(name)
        name = re.sub(r'[^\w\u4e00-\u9fff\-\.]', '_', name)
        if len(name) > max_len:
            base, ext = os.path.splitext(name)
            base = base[:max_len - len(ext)]
            name = base + ext
        return name
    except Exception:
        return "downloaded_media"

def is_bilibili_url(url):
    return "bilibili.com" in url or "b23.tv" in url

def normalize_bilibili_url(url):
    if not is_bilibili_url(url):
        return url

    try:
        parsed = urlparse(url)
        if "bilibili.com" not in parsed.netloc:
            return url

        match = re.search(r"/video/(BV[a-zA-Z0-9]+)", parsed.path)
        if match:
            bvid = match.group(1)
            return f"https://www.bilibili.com/video/{bvid}/"

        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    except Exception:
        return url

def normalize_browser(value):
    if not value:
        return None

    value = str(value).strip().lower()

    if value in ("chrome", "edge", "firefox"):
        return value

    return None

def has_audio_stream(filepath):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", filepath],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip() != ""
    except Exception:
        return False

def has_video_stream(filepath):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=codec_type", "-of", "csv=p=0", filepath],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.stdout.strip() != ""
    except Exception:
        return False

def merge_audio_video_if_needed(video_path, output_dir):
    try:
        if has_video_stream(video_path) and has_audio_stream(video_path):
            return video_path

        print("检测到音视频分离，尝试使用 ffmpeg 合并...")

        base_name = os.path.splitext(os.path.basename(video_path))[0]
        dir_path = os.path.dirname(video_path)

        candidates = [
            os.path.join(dir_path, f)
            for f in os.listdir(dir_path)
            if f.startswith(base_name) and f != os.path.basename(video_path)
        ]

        for other_file in candidates:
            v_has = has_video_stream(video_path)
            a_has = has_audio_stream(video_path)
            o_has_a = has_audio_stream(other_file)
            o_has_v = has_video_stream(other_file)

            if (v_has and o_has_a) or (a_has and o_has_v):
                merged_path = os.path.join(output_dir, f"{base_name}_merged.mp4")
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    video_path,
                    "-i",
                    other_file,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-map",
                    "0:v:0?",
                    "-map",
                    "1:a:0?",
                    "-map",
                    "1:v:0?",
                    "-map",
                    "0:a:0?",
                    merged_path
                ]
                subprocess.run(cmd, check=True, capture_output=True, timeout=120)
                if os.path.exists(merged_path):
                    print(f"合并完成: {merged_path}")
                    return merged_path

    except Exception as e:
        print(f"合并阶段出现错误: {e}")

    return video_path

def build_format_args(max_height=None, audio_only=False, fallback_height=None, best_only=False):
    if audio_only:
        return ["-x", "--audio-format", "mp3"]

    if fallback_height:
        return [
            "-f",
            f"bv*[height<={fallback_height}]+ba/b[height<={fallback_height}]/b",
            "--merge-output-format",
            "mp4"
        ]

    if best_only:
        return [
            "-f",
            "b",
            "--merge-output-format",
            "mp4"
        ]

    if max_height:
        return [
            "-f",
            f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
            "--merge-output-format",
            "mp4"
        ]

    return [
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4"
    ]

def get_recent_media_file(output_path, start_time):
    suffixes = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".mp3", ".m4a")
    files = [
        f for f in output_path.iterdir()
        if f.is_file() and f.suffix.lower() in suffixes and f.stat().st_mtime >= start_time
    ]

    if not files:
        files = [
            f for f in output_path.iterdir()
            if f.is_file() and f.suffix.lower() in suffixes
        ]

    if not files:
        return None

    return max(files, key=lambda f: f.stat().st_mtime)

def find_cookie_file(explicit_path=None, output_dir=None, bilibili=False):
    candidates = []

    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())

    cwd = Path.cwd()
    script_dir = Path(__file__).resolve().parent
    home = Path.home()
    downloads = home / "Downloads"

    names = ["cookies.txt"]

    if bilibili:
        names = [
            "bilibili_cookies.txt",
            "bili_cookies.txt",
            "cookies_bilibili.txt",
            "cookies.txt"
        ]

    search_dirs = [
        cwd,
        script_dir,
        script_dir.parent,
        home,
        downloads,
        Path("D:/")
    ]

    if output_dir:
        search_dirs.insert(0, Path(output_dir).expanduser())

    seen = set()

    for directory in search_dirs:
        for name in names:
            candidates.append(directory / name)

    for path in candidates:
        try:
            path = path.resolve()
            if path in seen:
                continue
            seen.add(path)
            if path.is_file() and path.stat().st_size > 0:
                return str(path)
        except Exception:
            continue

    return None

def build_base_cmd(url, template):
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--retries",
        "3",
        "--fragment-retries",
        "3",
        "--sleep-requests",
        "1",
        "--output",
        template
    ]

    if is_bilibili_url(url):
        cmd.extend([
            "--user-agent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--referer",
            "https://www.bilibili.com/",
            "--add-header",
            "Origin:https://www.bilibili.com",
            "--add-header",
            "Accept-Language:zh-CN,zh;q=0.9,en;q=0.8"
        ])

    return cmd

def run_attempt(base_cmd, url, attempt, max_height, audio_only):
    cmd = base_cmd.copy()

    if attempt.get("cookies_file"):
        print(f"\n---> 正在尝试 [Cookies 文件: {attempt['cookies_file']}]...")
        cmd.extend(["--cookies", attempt["cookies_file"]])
        cmd.extend(build_format_args(max_height=max_height, audio_only=audio_only))
    elif attempt.get("browser"):
        print(f"\n---> 正在尝试 [{attempt['name']}]...")
        cmd.extend(["--cookies-from-browser", attempt["browser"]])
        cmd.extend(build_format_args(max_height=max_height, audio_only=audio_only))
    else:
        print(f"\n---> 正在尝试 [{attempt['name']}]...")
        if is_bilibili_url(url):
            cmd.extend(["--extractor-args", "bilibili:prefer_multi_flv=False"])
        cmd.extend(build_format_args(
            max_height=max_height,
            audio_only=audio_only,
            fallback_height=attempt.get("fallback_height"),
            best_only=attempt.get("best_only", False)
        ))

    cmd.append(url)
    return subprocess.run(cmd)

def build_attempts(url, max_height=None, use_cookies=None, cookies_file=None, output_dir=None):
    attempts = []

    preferred_browser = normalize_browser(use_cookies)

    auto_cookie_file = find_cookie_file(
        explicit_path=cookies_file,
        output_dir=output_dir,
        bilibili=is_bilibili_url(url)
    )

    if auto_cookie_file:
        attempts.append({
            "name": "Cookies 文件",
            "cookies_file": auto_cookie_file
        })

    browser_candidates = ["chrome", "edge", "firefox"]

    if preferred_browser in browser_candidates:
        browser_candidates.remove(preferred_browser)
        browser_candidates.insert(0, preferred_browser)

    for browser in browser_candidates:
        attempts.append({
            "name": f"{browser} Cookie",
            "browser": browser
        })

    no_cookie_heights = []

    if max_height:
        try:
            no_cookie_heights.append(min(int(max_height), 720))
        except Exception:
            no_cookie_heights.append(720)
    else:
        no_cookie_heights.append(720)

    no_cookie_heights.append(480)

    seen_heights = set()

    for height in no_cookie_heights:
        if height in seen_heights:
            continue
        seen_heights.add(height)
        attempts.append({
            "name": f"无 Cookie {height}p",
            "fallback_height": height
        })

    attempts.append({
        "name": "无 Cookie best",
        "best_only": True
    })

    return attempts

def download(
    url: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    max_height: Optional[int] = None,
    audio_only: bool = False,
    list_formats: bool = False,
    with_subs: bool = False,
    use_cookies: Optional[str] = None,
    cookies_file: Optional[str] = None,
) -> int:
    try:
        url = normalize_bilibili_url(url)
        output_path = Path(output_dir).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"输出目录异常: {e}")
        return 1

    template = os.path.join(str(output_path), "%(title)s.%(ext)s")
    base_cmd = build_base_cmd(url, template)

    if list_formats:
        cookie_file = find_cookie_file(
            explicit_path=cookies_file,
            output_dir=str(output_path),
            bilibili=is_bilibili_url(url)
        )

        cmd = base_cmd.copy()

        if cookie_file:
            print(f"使用 Cookies 文件: {cookie_file}")
            cmd.extend(["--cookies", cookie_file])

        if is_bilibili_url(url):
            cmd.extend(["--extractor-args", "bilibili:prefer_multi_flv=False"])

        cmd.extend(["-F", url])
        result = subprocess.run(cmd)
        return result.returncode

    if with_subs:
        base_cmd.extend(["--write-subs", "--sub-lang", "zh,en,ja"])

    attempts = build_attempts(
        url=url,
        max_height=max_height,
        use_cookies=use_cookies,
        cookies_file=cookies_file,
        output_dir=str(output_path)
    )

    success = False
    result = None
    start_time = time.time() - 2

    for attempt in attempts:
        try:
            result = run_attempt(base_cmd, url, attempt, max_height, audio_only)
            if result.returncode == 0:
                success = True
                break
            print("\n[!] 当前策略失败，准备尝试下一种方案...")
        except Exception as e:
            print(f"\n[!] 命令执行异常: {e}")

    if not success:
        print(f"\n所有下载尝试均失败 (最终错误码: {result.returncode if result else 1})")
        return result.returncode if result else 1

    try:
        video_file = get_recent_media_file(output_path, start_time)

        if not video_file:
            print("下载进程结束，但未找到匹配的视频文件。")
            return 1

        safe_name = sanitize_filename(video_file.name)

        if safe_name != video_file.name:
            new_path = video_file.parent / safe_name
            try:
                video_file.rename(new_path)
                video_file = new_path
            except Exception as e:
                print(f"文件名净化失败: {e}")

        if not audio_only:
            video_file_str = merge_audio_video_if_needed(str(video_file), str(output_path))
        else:
            video_file_str = str(video_file)

        size_mb = os.path.getsize(video_file_str) / (1024 * 1024)
        print("\n下载并处理完成!")
        print(f"最终文件: {video_file_str} ({size_mb:.1f} MB)")
        return 0

    except Exception as e:
        print(f"后期处理阶段发生错误: {e}")
        return 1

def parse_json_arg(raw):
    try:
        params = json.loads(raw)
        if isinstance(params, dict) and "url" in params:
            return params
    except Exception as e:
        print(f"JSON 参数解析失败: {e}")
    return None

def main():
    try:
        if len(sys.argv) == 2 and sys.argv[1].strip().startswith("{"):
            params = parse_json_arg(sys.argv[1])
            if params:
                exit_code = download(
                    url=params["url"],
                    output_dir=params.get("output_dir", DEFAULT_OUTPUT_DIR),
                    max_height=params.get("max_height"),
                    audio_only=params.get("audio_only", False),
                    list_formats=params.get("list_formats", False),
                    with_subs=params.get("subs", False),
                    use_cookies=params.get("cookies"),
                    cookies_file=params.get("cookies_file"),
                )
                sys.exit(exit_code)

        parser = argparse.ArgumentParser()
        parser.add_argument("url")
        parser.add_argument("resolution", nargs="?")
        parser.add_argument("output", nargs="?", default=DEFAULT_OUTPUT_DIR)
        parser.add_argument("-a", "--audio", action="store_true", dest="audio")
        parser.add_argument("-F", "--list-formats", action="store_true", dest="list_formats")
        parser.add_argument("--subs", action="store_true", dest="subs")
        parser.add_argument("--cookies", metavar="BROWSER", dest="cookies")
        parser.add_argument("--cookies-file", metavar="PATH", dest="cookies_file")
        args = parser.parse_args()

        max_h = None

        if args.resolution:
            try:
                max_h = int(args.resolution.lower().replace("p", ""))
            except Exception:
                pass

        exit_code = download(
            url=args.url,
            output_dir=args.output,
            max_height=max_h,
            audio_only=args.audio,
            list_formats=args.list_formats,
            with_subs=args.subs,
            use_cookies=args.cookies,
            cookies_file=args.cookies_file,
        )
        sys.exit(exit_code)

    except Exception as e:
        print(f"程序发生未知崩溃: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()