import os
import re
import json
import shelve
from functools import lru_cache
from typing import Optional, Dict
import requests

PARTICLES = {
    "de", "da", "dos", "van", "von", "di", "le", "la", "al", "ibn", "bin", "del", "della", "du"
}

CJK_RANGES = [
    ("\u4e00", "\u9fff"),  # CJK Unified Ideographs
    ("\u3040", "\u30ff"),  # Hiragana + Katakana
    ("\u1100", "\u11ff"),  # Hangul Jamo (partial)
]

def is_cjk(s: str) -> bool:
    for ch in s:
        for a, b in CJK_RANGES:
            if a <= ch <= b:
                return True
    return False

def split_tokens(name: str):
    return [t for t in re.split(r"\s+", name.strip()) if t]

class NameInverter:
    def __init__(self, viaf_cache_path: Optional[str] = None, viaf_enabled: bool = True):
        self.viaf_enabled = viaf_enabled
        self.viaf_cache_path = viaf_cache_path
        self._shelf = None
        if self.viaf_enabled and self.viaf_cache_path:
            parent = os.path.dirname(self.viaf_cache_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            try:
                self._shelf = shelve.open(self.viaf_cache_path, writeback=False)
            except Exception:
                self._shelf = None

    def close(self):
        if self._shelf:
            try:
                self._shelf.close()
            except Exception:
                pass
            self._shelf = None

    def __del__(self):
        self.close()

    @lru_cache(maxsize=1024)
    def _viaf_autosuggest(self, name: str) -> Optional[Dict]:
        if not self.viaf_enabled:
            return None
        key = f"viaf:{name}"
        if self._shelf and key in self._shelf:
            try:
                return json.loads(self._shelf[key])
            except Exception:
                pass
        try:
            resp = requests.get(
                "https://viaf.org/viaf/AutoSuggest",
                params={"query": name},
                timeout=5
            )
            if resp.ok:
                data = resp.json()
                result = data.get("result") or []
                if result:
                    top = result[0]
                    if self._shelf is not None:
                        try:
                            self._shelf[key] = json.dumps(top)
                        except Exception:
                            pass
                    return top
        except Exception:
            pass
        return None

    def invert(self, name: str, locale: Optional[str] = None, prefer_authority: bool = True) -> str:
        if not name:
            return ""

        name = name.strip()
        if prefer_authority:
            auth = self._viaf_autosuggest(name)
            if auth and "term" in auth:
                return auth["term"]

        if is_cjk(name) or (locale and locale.startswith(("zh", "ja", "ko"))):
            return name

        tokens = split_tokens(name)
        if len(tokens) == 1:
            return name

        if (locale and locale.startswith(("es", "pt"))) or (len(tokens) >= 3 and locale is None):
            family = " ".join(tokens[-2:]) if len(tokens) >= 3 else tokens[-1]
            given = " ".join(tokens[:-len(family.split())])
            return f"{family}, {given}".strip(", ")

        i = len(tokens) - 1
        while i - 1 >= 0 and tokens[i - 1].lower().strip(".,") in PARTICLES:
            i -= 1
        family = " ".join(tokens[i:])
        given = " ".join(tokens[:i])
        return f"{family}, {given}".strip(", ")