import os
import ast
import json
import venv
import sys
import shutil
import hashlib
import asyncio
import logging
import aiofiles
import tempfile
import inspect
import signal
import traceback
import platform
import socket
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Callable

try:
    if platform.system() == "Windows":
        RESOURCE_AVAILABLE = False
    else:
        import resource
        RESOURCE_AVAILABLE = True
except ImportError:
    RESOURCE_AVAILABLE = False

logger = logging.getLogger(__name__)

def get_active_proxy_port() -> Optional[int]:
    common_ports = [7890, 7897, 10809, 1080, 1081, 10808, 8234, 8600, 8080, 8888]
    for port in common_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                if s.connect_ex(('127.0.0.1', port)) == 0:
                    return port
        except Exception:
            continue
    return None

class BaseTool:
    name: str = ""
    description: str = ""
    parameters_schema: Dict[str, Any] = {}

    async def execute(self, **kwargs) -> Any:
        raise NotImplementedError

    def to_sdk_format(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema
            }
        }

class PythonRuntime:
    def __init__(self, workspace: str, config: dict = None):
        self.workspace = Path(workspace)
        self.tools_dir = self.workspace / "tools"
        self.venv_root = self.tools_dir / "venvs"
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self.venv_root.mkdir(parents=True, exist_ok=True)
        self._venv_locks: Dict[str, asyncio.Lock] = {}
        self._venv_access: Dict[str, float] = {}
        self._cleanup_lock = asyncio.Lock()
        runtime_cfg = (config or {}).get("runtime", {})
        self.max_venvs = int(runtime_cfg.get("max_venvs", 20))
        self.memory_limit_mb = int(runtime_cfg.get("memory_limit_mb", 2048))
        self.file_size_limit_mb = int(runtime_cfg.get("file_size_limit_mb", 5000))
        self.cpu_time_limit_sec = int(runtime_cfg.get("cpu_time_limit_sec", 3600))
        self.pip_install_timeout_sec = int(runtime_cfg.get("pip_install_timeout_sec", 900))
        self.use_venv_pool = self._config_bool(runtime_cfg.get("use_venv_pool", True), True)
        self.auto_build_venv_profiles = self._config_bool(runtime_cfg.get("auto_build_venv_profiles", False), False)
        self.runtime_audit_hook_enabled = self._config_bool(runtime_cfg.get("runtime_audit_hook_enabled", True), True)
        self.runtime_network_enabled = self._config_bool(runtime_cfg.get("runtime_network_enabled", True), True)
        self.venv_profiles = self._build_venv_profiles(runtime_cfg.get("venv_profiles", {}))
        self.secrets = (config or {}).get("secrets", {})
        fs_cfg = (config or {}).get("filesystem", {})
        raw_paths = fs_cfg.get("allowed_paths", [])
        self.allowed_paths = []
        workspace_str = str(self.workspace.resolve())
        for p in raw_paths:
            p_expanded = p.replace("{workspace}", workspace_str)
            abs_path = os.path.abspath(p_expanded)
            if os.path.exists(abs_path) or p_expanded.endswith(os.sep) or os.path.isdir(os.path.dirname(abs_path)):
                self.allowed_paths.append(abs_path)
        self.allow_mkdir = fs_cfg.get("allow_mkdir", False)
        self.max_file_size_mb = fs_cfg.get("max_file_size_mb", 0)

    @staticmethod
    def _config_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    @staticmethod
    def _normalize_dep_list(deps: Any) -> List[str]:
        if isinstance(deps, str):
            deps = [part.strip() for part in deps.split(",")]
        if not isinstance(deps, list):
            return []
        return sorted({str(dep).strip() for dep in deps if str(dep).strip() and not str(dep).strip().startswith("#")})

    def _build_venv_profiles(self, configured_profiles: Any) -> Dict[str, List[str]]:
        defaults = {
            "env_pool_web": [
                "aiofiles", "aiohttp", "beautifulsoup4", "lxml", "requests"
            ],
            "env_pool_docs": [
                "openpyxl", "pypdf", "python-docx", "python-pptx"
            ],
            "env_pool_data": [
                "matplotlib", "networkx", "numpy", "openpyxl", "pandas",
                "scipy", "seaborn"
            ],
            "env_pool_agent": [
                "aiofiles", "aiohttp", "asyncpg", "neo4j", "openai",
                "pgvector", "pydantic", "redis", "tomli", "websockets"
            ],
        }
        profiles = {name: self._normalize_dep_list(deps) for name, deps in defaults.items()}
        if isinstance(configured_profiles, dict):
            for raw_name, raw_deps in configured_profiles.items():
                name = str(raw_name).strip()
                if not name:
                    continue
                if not name.startswith("env_pool_"):
                    name = f"env_pool_{name}"
                deps = self._normalize_dep_list(raw_deps)
                if deps:
                    profiles[name] = deps
        return profiles

    def _get_stdlib_modules(self) -> set:
        try:
            return set(sys.stdlib_module_names)
        except AttributeError:
            stdlib = set()
            for lib in sys.builtin_module_names:
                stdlib.add(lib)
            for path in sys.path:
                if 'site-packages' in path or 'dist-packages' in path:
                    continue
                try:
                    for entry in os.listdir(path):
                        if entry.endswith('.py') and entry != '__init__.py':
                            stdlib.add(entry[:-3])
                        elif os.path.isdir(os.path.join(path, entry)):
                            init = os.path.join(path, entry, '__init__.py')
                            if os.path.exists(init):
                                stdlib.add(entry)
                except:
                    pass
            return stdlib

    def is_path_allowed(self, target_path: str, for_write: bool = True) -> bool:
        if not self.allowed_paths:
            return True
        abs_target = os.path.abspath(target_path)
        for allowed in self.allowed_paths:
            try:
                if os.path.commonpath([abs_target, allowed]) == os.path.abspath(allowed):
                    return True
            except ValueError:
                continue
        return False

    def check_safety(self, code: str, is_trusted: bool = False) -> Tuple[bool, str, List[str]]:
        dangerous_attrs = {
            'system', 'popen', 'spawn', 'kill', 'remove', 'rmdir', 'unlink',
            'rename', 'truncate', 'putenv', 'unsetenv', 'setuid', 'setgid', 'chroot',
            'setrlimit', 'prctl', 'fork', 'vfork', 'execve', 'execvp', 'execl'
        }
        dangerous_funcs = {'__import__', 'exec', 'eval', 'compile', 'input',
                           'raw_input', 'breakpoint', 'globals', 'locals', 'vars',
                           'getattr', 'setattr', 'delattr'}
        dangerous_subprocess_cmds = {'rm', 'del', 'shutdown', 'reboot', 'format', 'mkfs', 'dd', 'fdisk', 'killall', 'pkill'}
        sensitive_ops_found = set()
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in dangerous_funcs:
                        if not is_trusted:
                            return False, f"Security block: forbidden function '{node.func.id}'", []
                    if isinstance(node.func, ast.Attribute):
                        if isinstance(node.func.value, ast.Name):
                            if node.func.value.id == 'os':
                                if node.func.attr in dangerous_attrs:
                                    sensitive_ops_found.add(f"os.{node.func.attr}")
                            elif node.func.value.id == 'shutil' and node.func.attr in {'rmtree', 'move'}:
                                sensitive_ops_found.add(f"shutil.{node.func.attr}")
                            elif node.func.value.id == 'subprocess':
                                sensitive_ops_found.add(f"subprocess.{node.func.attr}")
                                if node.func.attr in {'call', 'run', 'Popen', 'check_output', 'check_call'}:
                                    if len(node.args) > 0:
                                        arg = node.args[0]
                                        cmd_str = None
                                        if isinstance(arg, ast.Str):
                                            cmd_str = arg.s
                                        elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                            cmd_str = arg.value
                                        elif isinstance(arg, ast.List):
                                            parts = []
                                            for elt in arg.elts:
                                                if isinstance(elt, ast.Str):
                                                    parts.append(elt.s)
                                                elif isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                                    parts.append(elt.value)
                                            if parts:
                                                cmd_str = ' '.join(parts)
                                        if cmd_str:
                                            cmd_lower = cmd_str.lower()
                                            for dangerous_cmd in dangerous_subprocess_cmds:
                                                if dangerous_cmd in cmd_lower.split():
                                                    sensitive_ops_found.add(f"subprocess.{node.func.attr}({dangerous_cmd})")
                                                    break
                            if not is_trusted and node.func.attr in dangerous_funcs:
                                return False, f"Security block: forbidden {node.func.attr}", []
                if isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name) and node.value.id == 'os':
                        if node.attr in dangerous_attrs:
                            sensitive_ops_found.add(f"os.{node.attr}")
            if is_trusted:
                code_lower = code.lower()
                if 'reboot' in code_lower or 'shutdown' in code_lower:
                    sensitive_ops_found.add("System Reboot/Shutdown Command")
                if 'rm -rf' in code_lower or 'del /f /s /q' in code_lower:
                    sensitive_ops_found.add("Recursive Delete Command")
            return True, "Safe", list(sensitive_ops_found)
        except Exception as e:
            return False, f"Syntax error: {e}", []

    async def _cleanup_venvs(self):
        async with self._cleanup_lock:
            if len(self._venv_access) <= self.max_venvs:
                return
            sorted_items = sorted(self._venv_access.items(), key=lambda x: x[1])
            to_delete = len(self._venv_access) - self.max_venvs
            protected = {"env_base_core", *self.venv_profiles.keys()}
            deleted = 0
            for venv_hash, _ in sorted_items:
                if venv_hash in protected:
                    continue
                venv_path = self.venv_root / venv_hash
                if venv_path.exists():
                    try:
                        shutil.rmtree(venv_path)
                    except:
                        pass
                del self._venv_access[venv_hash]
                if venv_hash in self._venv_locks:
                    del self._venv_locks[venv_hash]
                deleted += 1
                if deleted >= to_delete:
                    break

    def _update_venv_access(self, venv_hash: str):
        self._venv_access[venv_hash] = asyncio.get_event_loop().time()

    async def _prepare_env(self, path: Path, clean_deps: List[str]) -> str:
        venv_hash = path.name
        async with self._get_lock(venv_hash):
            self._update_venv_access(venv_hash)
            py_exe = str(path / ("Scripts/python.exe" if os.name == 'nt' else "bin/python"))
            if os.path.exists(py_exe):
                return py_exe
            await self._cleanup_venvs()
            temp_path = path.with_name(f".{venv_hash}.tmp")
            if temp_path.exists():
                shutil.rmtree(temp_path, ignore_errors=True)
            try:
                venv.create(temp_path, with_pip=True)
                if clean_deps:
                    pip_exe = str(temp_path / ("Scripts/pip.exe" if os.name == 'nt' else "bin/pip"))
                    proc = await asyncio.create_subprocess_exec(
                        pip_exe,
                        "install",
                        "--disable-pip-version-check",
                        "--no-input",
                        "--no-warn-script-location",
                        *clean_deps
                    )
                    retcode = await asyncio.wait_for(proc.wait(), timeout=self.pip_install_timeout_sec)
                    if retcode != 0:
                        raise RuntimeError(f"pip install failed with code {retcode} for deps: {clean_deps}")
                if os.name == 'nt':
                    shutil.move(str(temp_path), str(path))
                else:
                    os.rename(str(temp_path), str(path))
                deps_marker = path / ".deps_installed"
                with open(deps_marker, "w") as f:
                    f.write("done")
                return py_exe
            except Exception as e:
                if temp_path.exists():
                    shutil.rmtree(temp_path, ignore_errors=True)
                if path.exists():
                    shutil.rmtree(path, ignore_errors=True)
                raise RuntimeError(f"Failed to prepare venv for {venv_hash}: {e}") from e

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._venv_locks:
            self._venv_locks[key] = asyncio.Lock()
        return self._venv_locks[key]

    def _extract_deps(self, code: str) -> List[str]:
        deps = set()
        mapping = {
            "pil": "pillow", "cv2": "opencv-python", "yaml": "pyyaml",
            "bs4": "beautifulsoup4", "sklearn": "scikit-learn", "skimage": "scikit-image",
            "fitz": "PyMuPDF", "docx": "python-docx", "pptx": "python-pptx",
            "dotenv": "python-dotenv", "sentence_transformers": "sentence-transformers",
            "pgvector": "pgvector", "redis": "redis", "yt_dlp": "yt-dlp",
            "pypdf": "pypdf", "pdfplumber": "pdfplumber", "openpyxl": "openpyxl",
            "lxml": "lxml", "aiohttp": "aiohttp", "aiofiles": "aiofiles",
            "watchdog": "watchdog", "fastapi": "fastapi", "uvicorn": "uvicorn",
            "json_repair": "json-repair", "pydantic": "pydantic", "tomli": "tomli",
            "websockets": "websockets", "mcp": "mcp",
            "requests": "requests", "numpy": "numpy", "pandas": "pandas",
            "matplotlib": "matplotlib", "seaborn": "seaborn", "networkx": "networkx",
            "scipy": "scipy", "cryptography": "cryptography", "openai": "openai",
            "asyncpg": "asyncpg", "neo4j": "neo4j"
        }
        stdlib = self._get_stdlib_modules()
        stdlib_lower = {m.lower() for m in stdlib}

        def add_pkg(pkg: str):
            pkg = (pkg or "").split('.')[0].strip()
            if not pkg or pkg == "__future__" or pkg.startswith("_"):
                return
            pkg_lower = pkg.lower()
            if pkg_lower in stdlib_lower:
                return
            if self._is_local_module(pkg):
                return
            deps.add(mapping.get(pkg_lower, pkg))

        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        add_pkg(n.name)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    add_pkg(node.module)
            return list(deps)
        except:
            return []

    def _is_local_module(self, pkg: str) -> bool:
        for root in [self.workspace, Path(__file__).resolve().parent]:
            try:
                if (root / f"{pkg}.py").exists() or (root / pkg / "__init__.py").exists():
                    return True
            except Exception:
                continue
        return False

    def _resolve_env_for_deps(self, clean_deps: List[str]) -> Tuple[str, List[str], str]:
        deps = self._normalize_dep_list(clean_deps)
        if not deps:
            return "env_base_core", [], "base"
        requested = set(deps)
        if self.use_venv_pool:
            candidates = []
            for profile_name, profile_deps in self.venv_profiles.items():
                profile_set = set(profile_deps)
                if requested.issubset(profile_set):
                    profile_path = self.venv_root / profile_name
                    if profile_path.exists() or self.auto_build_venv_profiles:
                        extra_count = len(profile_set - requested)
                        candidates.append((extra_count, len(profile_set), profile_name, sorted(profile_set)))
            if candidates:
                _, _, profile_name, profile_deps = min(candidates, key=lambda item: (item[0], item[1], item[2]))
                return profile_name, profile_deps, "profile"
        deps_str = "-".join(deps)
        deps_hash = hashlib.md5(deps_str.encode()).hexdigest()[:12]
        return f"env_deps_{deps_hash}", deps, "exact"

    def _build_runtime_audit_prelude(self, is_trusted: bool = False) -> str:
        if not self.runtime_audit_hook_enabled:
            return ""
        allowed_paths = [os.path.abspath(p) for p in self.allowed_paths]
        block_process = not is_trusted
        allow_network = bool(self.runtime_network_enabled)
        return f"""
import os as _audit_os
import sys as _audit_sys

_audit_allowed_paths = {json.dumps(allowed_paths, ensure_ascii=False)}
_audit_block_process = {repr(block_process)}
_audit_allow_network = {repr(allow_network)}
_audit_process_events = {{
    "os.system", "os.spawn", "os.posix_spawn", "os.exec",
    "os.fork", "subprocess.Popen"
}}
_audit_network_events = {{
    "socket.connect", "socket.bind", "socket.listen", "socket.accept"
}}
_audit_write_flags = 0
for _audit_flag_name in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND"):
    _audit_write_flags |= getattr(_audit_os, _audit_flag_name, 0)

def _audit_path_allowed(_path):
    if not _audit_allowed_paths:
        return True
    try:
        _abs_path = _audit_os.path.abspath(_audit_os.fspath(_path))
    except Exception:
        return True
    for _allowed in _audit_allowed_paths:
        try:
            if _audit_os.path.commonpath([_abs_path, _audit_os.path.abspath(_allowed)]) == _audit_os.path.abspath(_allowed):
                return True
        except ValueError:
            continue
    return False

def _audit_is_write_open(_args):
    _mode = None
    _flags = 0
    if len(_args) > 1:
        _mode = _args[1]
    if len(_args) > 2 and isinstance(_args[2], int):
        _flags = _args[2]
    if isinstance(_mode, str) and any(_marker in _mode for _marker in ("w", "a", "x", "+")):
        return True
    return bool(_flags & _audit_write_flags)

def _runtime_audit_hook(_event, _args):
    if _audit_block_process and (_event in _audit_process_events or _event.startswith("subprocess.")):
        raise PermissionError("Runtime audit denied process execution: " + _event)
    if not _audit_allow_network and (_event in _audit_network_events or _event.startswith("socket.")):
        raise PermissionError("Runtime audit denied network access: " + _event)
    if _event == "open" and _args and _audit_is_write_open(_args):
        _path = _args[0]
        if isinstance(_path, (str, bytes, _audit_os.PathLike)) and not _audit_path_allowed(_path):
            raise PermissionError("Runtime audit denied file write outside allowed paths: " + str(_path))

if hasattr(_audit_sys, "addaudithook"):
    _audit_sys.addaudithook(_runtime_audit_hook)
"""

    async def run_code(self, filename: str, code: str, args: Dict[str, Any] = None, timeout: int = None,
                       is_trusted: bool = False, extra_deps: List[str] = None, confirm_callback: Callable = None) -> dict:
        safe, msg, sensitive_ops = self.check_safety(code, is_trusted)
        if not safe:
            return {"status": "error", "message": msg, "completed": False}
        if sensitive_ops:
            prompt_msg = f"\n⚠️ [Security Alert] Script '{filename}' contains sensitive operations: {', '.join(sensitive_ops)}\nAllow execution? (y/n): "
            if confirm_callback:
                allowed = await confirm_callback(prompt_msg)
            else:
                ans = await asyncio.to_thread(input, prompt_msg)
                allowed = ans.strip().lower() == 'y'
            if not allowed:
                return {"status": "denied", "message": "User denied the execution.", "completed": True}
        if '/' in filename or '\\' in filename or filename.startswith('.'):
            filename = "script.py"
        if not filename.endswith('.py'):
            filename += '.py'
        deps = self._extract_deps(code)
        if extra_deps:
            for d in extra_deps:
                clean_dep = d.strip()
                if clean_dep and not clean_dep.startswith('#') and clean_dep not in deps:
                    deps.append(clean_dep)
        clean_deps = sorted(list(set(deps)))
        env_name, install_deps, env_mode = self._resolve_env_for_deps(clean_deps)
        env_path = self.venv_root / env_name
        py_exe = await self._prepare_env(env_path, install_deps)
        effective_timeout = timeout if timeout is not None else self.cpu_time_limit_sec
        with tempfile.TemporaryDirectory(prefix="exec_") as tmpdir:
            user_script_path = Path(tmpdir) / filename
            async with aiofiles.open(user_script_path, 'w', encoding='utf-8') as f:
                await f.write(code)
            proc_env = os.environ.copy()
            proc_env["WORKSPACE_DIR"] = str(self.workspace)
            proc_env["PYTHONDONTWRITEBYTECODE"] = "1"
            for k, v in self.secrets.items():
                proc_env[k] = str(v)
            active_port = get_active_proxy_port()
            if active_port:
                proc_env["HTTP_PROXY"] = f"http://127.0.0.1:{active_port}"
                proc_env["HTTPS_PROXY"] = f"http://127.0.0.1:{active_port}"
                proc_env["ALL_PROXY"] = f"http://127.0.0.1:{active_port}"
            prelude_lines = ["import sys\n", self._build_runtime_audit_prelude(is_trusted)]
            if RESOURCE_AVAILABLE:
                prelude_lines.append(f"""
import resource
try:
    resource.setrlimit(resource.RLIMIT_AS, ({self.memory_limit_mb} * 1024 * 1024, {self.memory_limit_mb} * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, ({self.file_size_limit_mb} * 1024 * 1024, {self.file_size_limit_mb} * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, ({self.cpu_time_limit_sec}, {self.cpu_time_limit_sec} + 1))
except Exception:
    pass
""")
            if self.allowed_paths:
                prelude_lines.append(f"""
import builtins
import os
import shutil
import sys

_original_open = builtins.open
_allowed_paths = {self.allowed_paths}

def _check_path(p, mode='r'):
    if 'w' in mode or 'a' in mode or 'x' in mode:
        abs_p = os.path.abspath(p)
        allowed = False
        for ap in _allowed_paths:
            try:
                if os.path.commonpath([abs_p, os.path.abspath(ap)]) == os.path.abspath(ap):
                    allowed = True
                    break
            except ValueError:
                pass
        if not allowed:
            raise PermissionError(f"Write access denied: {{p}} not in allowed paths {{_allowed_paths}}")
    return p

def safe_open(*args, **kwargs):
    if len(args) > 0:
        p = args[0]
    elif 'file' in kwargs:
        p = kwargs['file']
    else:
        return _original_open(*args, **kwargs)
    mode = kwargs.get('mode', 'r') if 'mode' in kwargs else (args[1] if len(args) > 1 else 'r')
    _check_path(p, mode)
    return _original_open(*args, **kwargs)

builtins.open = safe_open
_original_remove = os.remove
def safe_remove(p):
    _check_path(p, 'w')
    return _original_remove(p)
os.remove = safe_remove
os.unlink = safe_remove
_original_rename = os.rename
def safe_rename(src, dst):
    _check_path(dst, 'w')
    return _original_rename(src, dst)
os.rename = safe_rename

if hasattr(shutil, 'move'):
    _original_move = shutil.move
    def safe_move(src, dst):
        _check_path(dst, 'w')
        return _original_move(src, dst)
    shutil.move = safe_move

if hasattr(shutil, 'rmtree'):
    _original_rmtree = shutil.rmtree
    def safe_rmtree(p):
        _check_path(p, 'w')
        return _original_rmtree(p)
    shutil.rmtree = safe_rmtree
""")
            prelude_lines.append(f"""
import runpy
try:
    runpy.run_path(r'{str(user_script_path.resolve())}', run_name='__main__')
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
""")
            exec_code = "".join(prelude_lines)
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    py_exe, "-c", exec_code,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(self.workspace),
                    env=proc_env
                )
                input_data = json.dumps(args or {}).encode('utf-8')
                stdout, stderr = await asyncio.wait_for(proc.communicate(input=input_data), timeout=effective_timeout)
                stdout_dec = stdout.decode('utf-8', errors='replace').strip()
                stderr_dec = stderr.decode('utf-8', errors='replace').strip()
                if proc.returncode == 0:
                    return {
                        "status": "success",
                        "output": stdout_dec,
                        "error": stderr_dec,
                        "environment": env_name,
                        "environment_mode": env_mode,
                        "dependencies": clean_deps,
                        "installed_dependencies": install_deps,
                        "completed": False
                    }
                else:
                    error_msg = stderr_dec if stderr_dec else stdout_dec
                    if not error_msg:
                        error_msg = f"Process exited with code {proc.returncode}."
                    if "yt_dlp" in code or "yt-dlp" in code:
                        if "cookiesfrombrowser" not in code.lower() and "cookiefile" not in code.lower():
                            error_msg += "\n[System Hint]: Bilibili blocks anonymous requests. Add `cookiefile` or `cookiesfrombrowser` to your yt-dlp options."
                    if "ffmpeg" in error_msg.lower() or "ffprobe" in error_msg.lower():
                        error_msg += "\n[System Hint]: Sandbox lacks ffmpeg to merge DASH video/audio. Tell the user to use `execute_system_command` instead, as the host OS has ffmpeg."
                    if "requests" in code and "cookies" not in code.lower():
                        error_msg += "\n[System Hint]: Some websites block requests without cookies or headers. You may need to set cookies or User-Agent."
                    return {
                        "status": "error",
                        "message": error_msg,
                        "output": stdout_dec,
                        "error": stderr_dec,
                        "environment": env_name,
                        "environment_mode": env_mode,
                        "dependencies": clean_deps,
                        "installed_dependencies": install_deps,
                        "completed": False
                    }
            except asyncio.TimeoutError:
                if proc:
                    try:
                        proc.kill()
                        await proc.wait()
                    except Exception:
                        pass
                return {"status": "error", "message": f"Execution timed out after {effective_timeout} seconds.", "completed": False}
            except Exception as e:
                if proc:
                    try:
                        proc.kill()
                        await proc.wait()
                    except:
                        pass
                return {"status": "error", "message": f"Execution crashed: {str(e)}", "completed": False}

    async def run_background_process(self, filename: str, code: str, extra_deps: List[str] = None, confirm_callback: Callable = None) -> dict:
        safe, msg, sensitive_ops = self.check_safety(code, is_trusted=True)
        if not safe:
            return {"status": "error", "message": msg}
        if sensitive_ops:
            prompt_msg = f"\n⚠️ [Security Alert] Background script '{filename}' contains sensitive operations: {', '.join(sensitive_ops)}\nAllow execution? (y/n): "
            if confirm_callback:
                allowed = await confirm_callback(prompt_msg)
            else:
                ans = await asyncio.to_thread(input, prompt_msg)
                allowed = ans.strip().lower() == 'y'
            if not allowed:
                return {"status": "denied", "message": "User denied the background execution."}
        deps = self._extract_deps(code)
        if extra_deps:
            for d in extra_deps:
                clean_dep = d.strip()
                if clean_dep and not clean_dep.startswith('#') and clean_dep not in deps:
                    deps.append(clean_dep)
        clean_deps = sorted(list(set(deps)))
        env_name, install_deps, env_mode = self._resolve_env_for_deps(clean_deps)
        env_path = self.venv_root / env_name
        py_exe = await self._prepare_env(env_path, install_deps)
        if '/' in filename or '\\' in filename or filename.startswith('.'):
            filename = "background_script.py"
        if not filename.endswith('.py'):
            filename += '.py'
        user_script_path = self.workspace / filename
        async with aiofiles.open(user_script_path, 'w', encoding='utf-8') as f:
            await f.write(code)
        try:
            proc_env = os.environ.copy()
            proc_env["WORKSPACE_DIR"] = str(self.workspace)
            proc_env["PYTHONDONTWRITEBYTECODE"] = "1"
            for k, v in self.secrets.items():
                proc_env[k] = str(v)
            active_port = get_active_proxy_port()
            if active_port:
                proc_env["HTTP_PROXY"] = f"http://127.0.0.1:{active_port}"
                proc_env["HTTPS_PROXY"] = f"http://127.0.0.1:{active_port}"
                proc_env["ALL_PROXY"] = f"http://127.0.0.1:{active_port}"
            exec_code = self._build_runtime_audit_prelude(is_trusted=True) + f"""
import runpy
runpy.run_path(r'{str(user_script_path.resolve())}', run_name='__main__')
"""
            proc = await asyncio.create_subprocess_exec(
                py_exe, "-c", exec_code,
                cwd=str(self.workspace),
                env=proc_env
            )
            return {
                "status": "success",
                "message": f"Background process started with PID {proc.pid}",
                "pid": proc.pid,
                "environment": env_name,
                "environment_mode": env_mode,
                "dependencies": clean_deps,
                "installed_dependencies": install_deps
            }
        except Exception as e:
            return {"status": "error", "message": repr(e)}

class ToolManager:
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self.tools[tool.name] = tool

    def get_schemas(self) -> List[Dict[str, Any]]:
        return [t.to_sdk_format() for t in self.tools.values()]

    async def call(self, name: str, arguments: str, session_id: str = None) -> str:
        if name not in self.tools:
            return json.dumps({"status": "error", "message": f"Tool {name} not found"})
        try:
            args = json.loads(arguments)
            tool = self.tools[name]
            sig = inspect.signature(tool.execute)
            if "session_id" in sig.parameters and session_id:
                args["session_id"] = session_id
            res = await tool.execute(**args)
            if isinstance(res, str):
                return res
            elif isinstance(res, dict):
                return json.dumps(res, ensure_ascii=False)
            else:
                return str(res)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

class SearchMemoryTool(BaseTool):
    def __init__(self, agent):
        self.name = "search_long_term_memory"
        self.description = "Retrieve historical data and long-term memory."
        self.parameters_schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        self.agent = agent

    async def execute(self, query: str, session_id: str = None):
        return await self.agent.execute_memory_search(query, session_id)

class MemorizeFactTool(BaseTool):
    def __init__(self, agent):
        self.name = "memorize_critical_fact"
        self.description = "Commit a critical fact or state change to persistent memory."
        self.parameters_schema = {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]}
        self.agent = agent

    async def execute(self, fact: str):
        return await self.agent.execute_memorize_fact(fact)

class AmendMemoryTool(BaseTool):
    def __init__(self, agent):
        self.name = "amend_or_forget_memory"
        self.description = "Erase or correct erroneous facts from long-term memory databases."
        self.parameters_schema = {"type": "object", "properties": {"target_fact": {"type": "string"}}, "required": ["target_fact"]}
        self.agent = agent

    async def execute(self, target_fact: str):
        return await self.agent.execute_amend_memory(target_fact)

class UpdateCoreMemoryTool(BaseTool):
    def __init__(self, agent):
        self.name = "update_core_memory"
        self.description = "Update the Core Memory scratchpad with dynamic short-term states."
        self.parameters_schema = {"type": "object", "properties": {"updates": {"type": "string"}}, "required": ["updates"]}
        self.agent = agent

    async def execute(self, updates: str, session_id: str = None):
        return await self.agent.execute_update_core(session_id, updates)

class UpdateClinicalRuleTool(BaseTool):
    def __init__(self, agent):
        self.name = "update_clinical_rule"
        self.description = "Add a new mandatory clinical guideline or operational rule to the system's procedural memory."
        self.parameters_schema = {"type": "object", "properties": {"rule": {"type": "string"}}, "required": ["rule"]}
        self.agent = agent

    async def execute(self, rule: str):
        return await self.agent.execute_update_clinical_rule(rule)

class ExecuteSystemCommandTool(BaseTool):
    def __init__(self, agent):
        self.name = "execute_system_command"
        self.description = "Execute a local system command safely."
        self.parameters_schema = {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
        self.agent = agent

    async def execute(self, command: str):
        return await self.agent.execute_system_cmd(command)

class WriteAndExecuteScriptTool(BaseTool):
    def __init__(self, agent):
        self.name = "write_and_execute_script"
        self.description = "Execute Python script in isolated temporary virtual environment."
        self.parameters_schema = {"type": "object", "properties": {"filename": {"type": "string"}, "code": {"type": "string"}}, "required": ["filename", "code"]}
        self.agent = agent

    async def execute(self, filename: str, code: str, session_id: str = None):
        return await self.agent.execute_write_and_run(filename, code, session_id)

class RegisterNewToolTool(BaseTool):
    def __init__(self, agent):
        self.name = "register_new_tool"
        self.description = "Register a new or upgraded extension tool."
        self.parameters_schema = {"type": "object", "properties": {"tool_name": {"type": "string"}, "tool_description": {"type": "string"}, "parameters_schema": {"type": "string"}, "code": {"type": "string"}}, "required": ["tool_name", "tool_description", "parameters_schema", "code"]}
        self.agent = agent

    async def execute(self, tool_name: str, tool_description: str, parameters_schema: str, code: str):
        return await self.agent.execute_register_tool(tool_name, tool_description, parameters_schema, code)

class ExtensionTool(BaseTool):
    def __init__(self, name: str, description: str, schema: Dict[str, Any], py_path: str, runtime: PythonRuntime):
        self.name = name
        self.description = description
        self.parameters_schema = schema
        self.py_path = py_path
        self.runtime = runtime

    async def execute(self, **kwargs) -> Any:
        try:
            async with aiofiles.open(self.py_path, 'r', encoding='utf-8') as f:
                code = await f.read()
        except Exception as e:
            return {"status": "error", "message": f"Failed to read tool code: {e}"}
        filename = os.path.basename(self.py_path)
        return await self.runtime.run_code(filename, code, args=kwargs)

class SkillTool(BaseTool):
    def __init__(self, name: str, description: str, schema: Dict[str, Any], code: str, runtime: PythonRuntime):
        self.name = name
        self.description = description
        self.parameters_schema = schema
        self.code = code
        self.runtime = runtime

    async def execute(self, **kwargs) -> Any:
        wrapper_code = f"""
{self.code}

import json
result = run(**json.loads('''{json.dumps(kwargs)}'''))
print(json.dumps({{"result": result}}))
"""
        res = await self.runtime.run_code(f"{self.name}.py", wrapper_code)
        if res.get("status") == "success":
            try:
                output = json.loads(res["output"].strip())
                return output.get("result", res["output"])
            except:
                return res["output"]
        return {"error": res.get("message", "Execution failed")}

class OpenClawSkillTool(BaseTool):
    def __init__(self, name: str, description: str, code: str, requirements: List[str], runtime: PythonRuntime, agent=None):
        self.name = name.replace(".", "_").replace(" ", "_").replace("-", "_")
        self.description = description
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "kwargs_json": {
                    "type": "string",
                    "description": "JSON formatted string containing all arguments required by this skill's documentation."
                }
            }
        }
        self.code = code
        self.requirements = requirements
        self.runtime = runtime
        self.agent = agent

    async def execute(self, kwargs_json: str = "{}", session_id: str = None) -> Any:
        wrapper_code = f"""
import os
import sys
import json

os.environ['OPENCLAW_ARGS'] = '''{kwargs_json}'''

{self.code}
"""
        async def confirm_cb(msg):
            if self.agent and hasattr(self.agent, '_request_user_confirmation'):
                return await self.agent._request_user_confirmation(msg)
            ans = await asyncio.to_thread(input, msg)
            return ans.strip().lower() in ('y', 'yes')
        res = await self.runtime.run_code(
            filename=f"oc_{self.name}.py",
            code=wrapper_code,
            is_trusted=True,
            extra_deps=self.requirements,
            confirm_callback=confirm_cb
        )
        if res.get("status") in ["success", "error"]:
            return res
        return {"status": "error", "message": res.get("message", "Execution failed")}
