import os
import re
import tomlkit
from urllib.parse import urlparse, urlunparse

class ConfigScrubber:
    def __init__(self, sensitive_keys=None):
        self.sensitive_keys = sensitive_keys or {
            'api_key', 'password', 'pwd', 'secret',
            'token', 'uri', 'url', 'access_key', 'sk'
        }
        self.uri_pattern = re.compile(
            r'(\w+://)([^:]+):([^@]+)@',
            re.IGNORECASE
        )

    def _mask_uri(self, uri_str):
        try:
            parsed = urlparse(uri_str)
            if parsed.password or parsed.username:
                netloc = f"{parsed.username or 'user'}:******@{parsed.hostname}"
                if parsed.port:
                    netloc += f":{parsed.port}"
                return urlunparse(parsed._replace(netloc=netloc))
            return uri_str
        except:
            return "******"

    def _process(self, data):
        if isinstance(data, dict):
            for k, v in data.items():
                k_lower = k.lower()
                if any(sk in k_lower for sk in self.sensitive_keys):
                    if isinstance(v, str) and ("://" in v):
                        data[k] = self._mask_uri(v)
                    elif isinstance(v, str):
                        data[k] = "******"
                else:
                    self._process(v)
        elif isinstance(data, list):
            for item in data:
                self._process(item)
        return data

    def _scrub_comment_line(self, line: str) -> str:
        if '#' not in line:
            return line
        sharp_pos = line.find('#')
        before = line[:sharp_pos]
        comment = line[sharp_pos+1:]
        scrubbed_comment = comment
        for key in self.sensitive_keys:
            pattern = re.compile(
                r'\b(' + re.escape(key) + r')\s*[:=]\s*(["\']?)([^"\'\s#]+)\2',
                re.IGNORECASE
            )
            scrubbed_comment = pattern.sub(r'\1 = \2******\2', scrubbed_comment)
            pattern2 = re.compile(
                r'\b(' + re.escape(key) + r')(?:[-\s]+)([a-zA-Z0-9_\-]+)\b',
                re.IGNORECASE
            )
            scrubbed_comment = pattern2.sub(r'\1 = "******"', scrubbed_comment)
        scrubbed_comment = self.uri_pattern.sub(
            lambda m: f"{m.group(1)}{m.group(2)}:******@", scrubbed_comment
        )
        return before + '#' + scrubbed_comment

    def scrub_and_print_local(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        files = [f for f in os.listdir(current_dir) if f.endswith('.toml')]

        if not files:
            print("No .toml files found in current directory.")
            return

        for filename in files:
            print(f"{'='*20} FILE: {filename} {'='*20}")
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    doc = tomlkit.parse(f.read())
                self._process(doc)
                output = tomlkit.dumps(doc)
                lines = output.splitlines(keepends=True)
                scrubbed_lines = [self._scrub_comment_line(line) for line in lines]
                print(''.join(scrubbed_lines))
            except Exception as e:
                print(f"Error processing {filename}: {e}")
            print(f"{'='*50}\n")

if __name__ == "__main__":
    scrubber = ConfigScrubber()
    scrubber.scrub_and_print_local()