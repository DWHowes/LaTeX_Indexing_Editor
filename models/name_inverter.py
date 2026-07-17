import os
import re
import json
import sqlite3
import requests
import xml.etree.ElementTree as ET

from functools import lru_cache
from dataclasses import dataclass
from typing import Optional, Dict, List

_LC_DATE_QUALIFIER = re.compile(
    r",\s*\d{4}-?\d*\.?$"
)

PARTICLES = {
    "de", "da", "dos", "van", "von", "di", "le", "la",
    "al", "ibn", "bin", "del", "della", "du"
}

WIDOW_MARKERS = {"viuda", "vda."}
SPANISH_PARTICLE_ARTICLES = {"la", "las", "los"}
SPANISH_PREPOSITIONAL_PARTICLES = {"de", "del"}

PORTUGUESE_FILIAL_MARKERS = {"filho", "filha", "junior", "júnior"}

CJK_RANGES = [
    ("\u4e00", "\u9fff"),
    ("\u3040", "\u30ff"),
    ("\u1100", "\u11ff"),
]

GENERATIONAL_SUFFIXES = {
    "jr", "jr.", "sr", "sr.",
    "i", "ii", "iii", "iv", "v", "vi",          # Roman numerals to VI
    "1st", "2nd", "3rd", "4th", "5th",
}

HYPHENATED_ARABIC_PREFIXES = re.compile(
    r"^(al|el|abu|umm|ibn|bint)-",
    re.IGNORECASE,
)

MAC_MC = re.compile(r"^(Mac|Mc)[A-Z]", re.UNICODE)


def is_cjk(text: str) -> bool:
    return any(a <= ch <= b for ch in text for a, b in CJK_RANGES)

def split_tokens(name: str):
    return [token for token in re.split(r"\s+", name.strip()) if token]

@dataclass
class NameInversionResult:
    display_value: str
    authority_term: Optional[str] = None
    rule_suggestion: Optional[str] = None
    used_authority: bool = False

class NameInverter:
    def __init__(self, viaf_cache_path: Optional[str] = None, viaf_enabled: bool = True):
        self.viaf_enabled = viaf_enabled
        self._shelf = None
        if viaf_enabled and viaf_cache_path:
            os.makedirs(os.path.dirname(viaf_cache_path), exist_ok=True)
            try:
                self._conn = sqlite3.connect(viaf_cache_path, check_same_thread=False)
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS cache "
                    "(key TEXT PRIMARY KEY, value TEXT, " \
                    "reason TEXT, locale TEXT, " \
                    "user_edited INTEGER DEFAULT 0, " \
                    "created_at  TEXT DEFAULT (datetime('now')))"
                )
                self._conn.commit()
            except Exception as exc:
                print(f"VIAF cache DB init failed: {exc}")
                self._conn = None

    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __del__(self):
        self.close()

    @lru_cache(maxsize=1024)
    def _viaf_autosuggest(self, name: str) -> Optional[Dict]:
        if not self.viaf_enabled:
            return None

        try:
            resp = requests.get(
                "https://viaf.org/viaf/AutoSuggest",
                params={"query": name},
                timeout=5,
                headers={
                    "User-Agent": "LaTeX Indexing Editor/1.0",
                    "Accept": "application/json",
                },
            )
            if resp.status_code != 200:
                print(
                    f"VIAF lookup HTTP {resp.status_code} for {name}: "
                    f"{resp.text[:200]}"
                )
                return None

            text = resp.text.strip()
            if not text:
                print(f"VIAF lookup returned empty response for {name}")
                return None

            try:
                data = resp.json()
            except ValueError:
                print(
                    f"VIAF lookup returned non-JSON response for {name}: "
                    f"{text[:200]}"
                )
                return None

            result = data.get("result") or []
            if result:
                return result[0]

            print(f"VIAF lookup returned no results for: {name}")
        except Exception as exc:
            print(f"VIAF lookup failed for {name}: {exc}")

        return None
    
    def _extract_viaf_ids_from_entry(self, entry: Dict) -> List[str]:
        if not entry:
            return []

        candidates = []
        for key in ("viafid", "recordID", "id"):
            val = entry.get(key)
            if val:
                vid = str(val).strip()
                if vid and vid not in candidates:
                    candidates.append(vid)
        return candidates

    def _parse_viaf_html_heading(self, html: str) -> Optional[str]:
        """Parse modern VIAF landing page HTML for a canonical authority heading.

        Strategy (in order):
        1. JSON-LD <script type="application/ld+json"> ... "name"/"headline"
        2. Next.js payload in <script id="__NEXT_DATA__"> ... search recursively
        3. OpenGraph / Twitter meta tags (og:title / twitter:title)
        4. <h1> / <title> fallbacks
        """
        if not html:
            return None

        def _try_json_ld(h):
            m = re.search(
                r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                h,
                re.IGNORECASE | re.DOTALL,
            )
            if not m:
                return None
            try:
                payload = json.loads(m.group(1))
            except Exception:
                return None

            # prefer top-level name/headline
            if isinstance(payload, dict):
                for key in ("name", "headline", "title", "label"):
                    val = payload.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
                # @graph items
                graph = payload.get("@graph")
                if isinstance(graph, list):
                    for item in graph:
                        if isinstance(item, dict):
                            for key in ("name", "headline", "title"):
                                val = item.get(key)
                                if isinstance(val, str) and val.strip():
                                    return val.strip()
            return None

        def _try_next_data(h):
            m = re.search(
                r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
                h,
                re.IGNORECASE | re.DOTALL,
            )
            if not m:
                return None
            try:
                payload = json.loads(m.group(1))
            except Exception:
                return None

            # recursive search for name-like keys
            keys_of_interest = {"name", "title", "headline", "displayName", "preferredName", "mainHeading", "heading"}
            def _recurse(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in keys_of_interest and isinstance(v, str) and v.strip():
                            return v.strip()
                        res = _recurse(v)
                        if res:
                            return res
                elif isinstance(obj, list):
                    for el in obj:
                        res = _recurse(el)
                        if res:
                            return res
                return None

            return _recurse(payload.get("props") or payload)

        def _try_meta(h):
            m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']', h, re.IGNORECASE)
            if m and m.group(1).strip():
                return m.group(1).strip()
            m = re.search(r'<meta[^>]+name=["\']twitter:title["\'][^>]*content=["\']([^"\']+)["\']', h, re.IGNORECASE)
            if m and m.group(1).strip():
                return m.group(1).strip()
            return None

        def _try_heading_title(h):
            m = re.search(r'<h1[^>]*>(.*?)</h1>', h, re.IGNORECASE | re.DOTALL)
            if m:
                txt = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if txt:
                    return txt
            m = re.search(r'<title[^>]*>(.*?)</title>', h, re.IGNORECASE | re.DOTALL)
            if m:
                txt = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if txt:
                    return txt
            return None

        # Try JSON-LD
        val = _try_json_ld(html)
        if val:
            return val

        # Try Next.js payload
        val = _try_next_data(html)
        if val:
            return val

        # Meta tags
        val = _try_meta(html)
        if val:
            return val

        # h1 / title fallback
        val = _try_heading_title(html)
        if val:
            return val

        return None

    def _fetch_viaf_authority_heading(self, viaf_id: str) -> Optional[str]:
        """Resolve a VIAF cluster ID to the best available inverted authority heading.

        Strategy order:
        1. VIAF cluster JSON  — fast, usually returns multiple inverted headings;
            prefer the LC-sourced one.
        2. justlinks.json → LC Linked Data Service (SKOS JSON)  — authoritative
            LC NAF heading, already in inverted form, preferred for professional indexes.
        3. Structured XML endpoints  — legacy; frequently 404 on modern records.
        4. HTML landing page parse  — last resort; fragile against VIAF redesigns.
        """
        if not viaf_id:
            return None

        headers = {
            "User-Agent": "LaTeX Indexing Editor/1.0",
            "Accept": "application/json, application/xml, text/html",
        }

        # ── Strategy 1: VIAF cluster JSON ────────────────────────────────────────
        # /viaf/{id}/viaf.json → mainHeadings.data[].text  (already inverted)
        # Prefer the LC-sourced heading; fall back to the first available.
        try:
            resp = requests.get(
                f"https://viaf.org/viaf/{viaf_id}/viaf.json",
                timeout=8,
                headers=headers,
            )
            if resp.status_code == 200:
                data = resp.json()
                headings = (data.get("mainHeadings") or {}).get("data") or []
                if isinstance(headings, dict):
                    # API sometimes returns a single dict instead of a list
                    headings = [headings]
                lc_text: Optional[str] = None
                first_text: Optional[str] = None
                for entry in headings:
                    sources = (entry.get("sources") or {}).get("s") or []
                    if isinstance(sources, str):
                        sources = [sources]
                    text = (entry.get("text") or "").strip()
                    if not text:
                        continue
                    if first_text is None:
                        first_text = text
                    if any(str(s).startswith("LC") for s in sources):
                        lc_text = text
                        break
                result = lc_text or first_text
                if result:
                    return result
        except Exception as exc:
            print(f"VIAF cluster JSON failed for {viaf_id}: {exc}")

        # ── Strategy 2: justlinks.json → LC Linked Data Service ──────────────────
        # /viaf/{id}/justlinks.json  → { "LC": ["n79021400", ...], ... }
        # id.loc.gov/authorities/names/{lc_id}.skos.json → SKOS graph
        # madsrdf:authoritativeLabel is the definitive inverted LC NAF heading.
        try:
            jl_resp = requests.get(
                f"https://viaf.org/viaf/{viaf_id}/justlinks.json",
                timeout=6,
                headers=headers,
            )
            if jl_resp.status_code == 200:
                links = jl_resp.json()
                lc_ids: List[str] = links.get("LC") or []
                if isinstance(lc_ids, str):
                    lc_ids = [lc_ids]
                for lc_id in lc_ids[:3]:
                    result = self._fetch_lc_authority_heading(lc_id.strip())
                    if result:
                        return result
        except Exception as exc:
            print(f"VIAF justlinks lookup failed for {viaf_id}: {exc}")

        # ── Strategy 3: legacy structured XML endpoints ───────────────────────────
        for ep in ("viaf.xml", "rdf.xml", "marc.xml", "marcxml"):
            try:
                url = f"https://viaf.org/viaf/{viaf_id}/{ep}"
                resp = requests.get(url, timeout=7, headers=headers)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                body = resp.text or ""
                if not (resp.headers.get("Content-Type", "").find("xml") != -1
                        or body.strip().startswith("<")):
                    continue
                try:
                    root = ET.fromstring(resp.content)
                except ET.ParseError:
                    continue
                # VIAF XML: mainHeadings/data/text
                el = root.find(".//mainHeadings//data//text")
                if el is not None and (el.text or "").strip():
                    return el.text.strip()
                el = root.find(".//mainHeadings//text") or root.find(
                    ".//mainHeadings//name"
                )
                if el is not None and (el.text or "").strip():
                    return el.text.strip()
                # MARC XML: datafield[@tag='100'] subfields
                for datafield in root.findall(".//datafield"):
                    tag = (
                        datafield.get("tag") or datafield.get("name") or ""
                    ).strip()
                    if tag == "100":
                        parts = [
                            sf.text.strip()
                            for sf in datafield.findall("subfield")
                            if sf.text
                        ]
                        if parts:
                            return " ".join(parts).strip()
                # Generic subfield 'a' sweep
                parts = [
                    sf.text.strip()
                    for sf in root.findall(".//subfield")
                    if (sf.get("code") or "").lower() == "a" and sf.text
                ]
                if parts:
                    return " ".join(parts).strip()
            except Exception:
                continue

        # ── Strategy 4: HTML landing page parse ──────────────────────────────────
        try:
            html_url = f"https://viaf.org/viaf/{viaf_id}"
            resp = requests.get(html_url, timeout=8, headers=headers)
            resp.raise_for_status()
            html = resp.text or ""
            heading = self._parse_viaf_html_heading(html)
            if heading:
                return heading
        except Exception:
            pass

        return None
    
    def fetch_authority_from_autosuggest_entry(self, entry: Dict) -> Optional[str]:
        if not entry:
            return None

        # ── Fast path: LC ID is present directly in the AutoSuggest payload ──
        # AutoSuggest returns source-library IDs as top-level fields.
        # "lc" is the LC NAF control number — go straight to LC Linked Data
        # rather than bouncing through VIAF's cluster endpoints.
        lc_id = (entry.get("lc") or "").strip()
        if lc_id:
            heading = self._fetch_lc_authority_heading(lc_id)
            if heading:
                return heading
            print(f"LC Linked Data returned nothing for {lc_id!r}; falling back to VIAF resolution")

        # ── Slow path: resolve via VIAF cluster ──────────────────────────────
        candidates = self._extract_viaf_ids_from_entry(entry)
        if not candidates:
            return entry.get("term") or entry.get("name") or None

        for vid in candidates:
            heading = self._fetch_viaf_authority_heading(vid)
            if heading:
                return heading

        return entry.get("term") or entry.get("name") or None

    def _strip_lc_date_qualifier(self, heading: str) -> str:
        """Remove trailing LC date qualifiers from an authority heading.

        'Churchill, Winston, 1874-1965'  → 'Churchill, Winston'
        'Jones, John Paul, 1946-'        → 'Jones, John Paul'
        'Aristotle'                      → 'Aristotle'
        'Smith, J. D.'                   → 'Smith, J. D.'
        """
        return _LC_DATE_QUALIFIER.sub("", heading).rstrip(", ")

    def _fetch_lc_authority_heading(self, lc_id: str) -> Optional[str]:
        """Query the LC Linked Data Service for a single LC NAF control number.

        Returns the best available inverted heading, or None if unreachable
        or no usable label is found.
        """
        if not lc_id:
            return None

        headers = {
            "User-Agent": "LaTeX Indexing Editor/1.0",
            "Accept": "application/json",
        }

        url = f"https://id.loc.gov/authorities/names/{lc_id}.skos.json"
        try:
            resp = requests.get(url, timeout=7, headers=headers)
            if resp.status_code != 200:
                print(f"LC SKOS lookup HTTP {resp.status_code} for {lc_id}")
                return None
            graph: List[Dict] = resp.json()
        except Exception as exc:
            print(f"LC SKOS fetch failed for {lc_id}: {exc}")
            return None

        MADS_AUTH = "http://www.loc.gov/mads/rdf/v1#authoritativeLabel"
        SKOS_PREF = "http://www.w3.org/2004/02/skos/core#prefLabel"
        SKOS_ALT  = "http://www.w3.org/2004/02/skos/core#altLabel"

        mads_label: Optional[str] = None
        pref_label: Optional[str] = None
        alt_label:  Optional[str] = None

        for node in graph:
            for pred, slot in (
                (MADS_AUTH, "mads_label"),
                (SKOS_PREF, "pref_label"),
                (SKOS_ALT,  "alt_label"),
            ):
                if locals()[slot] is not None:
                    continue
                for val in (node.get(pred) or []):
                    if isinstance(val, dict):
                        raw = (val.get("@value") or "").strip()
                        lang = val.get("@language", "")
                        if lang and not lang.startswith("en"):
                            continue
                    else:
                        raw = str(val).strip()
                    if raw:
                        if slot == "mads_label":
                            mads_label = raw
                        elif slot == "pref_label":
                            pref_label = raw
                        else:
                            alt_label = raw
                        break

        chosen = mads_label or pref_label or alt_label
        if chosen:
            cleaned = self._strip_lc_date_qualifier(chosen)
            # Strip trailing MARC punctuation ("Churchill, Winston," → "Churchill, Winston")
            return cleaned.rstrip(",.")
        return None
   
    def _fast_invert(self, name: str, locale: Optional[str] = None) -> str:
        """Invert a natural-order personal name to indexing form without network I/O.

        Returns the name in ``Surname, Given`` form using a cascade of structural
        rules.  The result is used as a fallback when VIAF/LC authority lookup is
        disabled or returns nothing, and as the ``rule_suggestion`` value shown
        alongside the authority term in ``NameInversionDialog``.

        Processing order
        ----------------
        1. **Already-inverted guard** — if the name contains a comma it is returned
        unchanged to prevent double-inversion.
        2. **CJK passthrough** — names containing CJK characters, or whose locale
        starts with ``zh``, ``ja``, or ``ko``, are returned unchanged because
        family-name-first order is already correct.
        3. **Single-token passthrough** — mononyms and single-word inputs are
        returned unchanged; authority lookup handles these via VIAF.
        4. **Generational suffix stripping** — a trailing token matching
        ``GENERATIONAL_SUFFIXES`` (``Jr.``, ``Sr.``, ``III``, ``2nd``, etc.)
        is removed before inversion and reappended after:
        ``John Smith Jr.`` → ``Smith, John, Jr.``
        5. **Hyphenated Arabic prefix** — if the final token begins with a
        hyphenated prefix (``al-``, ``el-``, ``abu-``, ``umm-``, ``ibn-``,
        ``bint-``) it is treated as the surname regardless of position:
        ``Abdel Fattah el-Sisi`` → ``el-Sisi, Abdel Fattah``.
        6. **Mac/Mc two-token surname** — when ``Mac`` or ``Mc`` appears as a
        standalone token immediately before a capitalised component, the pair
        is combined as the family name:
        ``John Mac Donald`` → ``Mac Donald, John``.
        Single-token forms (``MacDougall``) fall through to standard logic.
        7. **Portuguese filial markers** — a trailing token in
        ``PORTUGUESE_FILIAL_MARKERS`` (``filho``, ``filha``, ``junior``, etc.)
        causes the last two tokens to be treated as the family name:
        ``João Silva Filho`` → ``Silva Filho, João``.
        8. **Spanish/Portuguese connectors** — detects ``de``, ``del``, and
        ``de la / de los / de las`` constructions and applies heuristics based
        on prefix length, suffix length, widow markers (``viuda``, ``vda.``),
        and locale to determine the family-name boundary.
        9. **Standard particle walk** — walks backwards from the last token,
        absorbing any space-separated particles in ``PARTICLES`` (``van``,
        ``von``, ``de``, ``al``, etc.) into the family name:
        ``Ludwig van Beethoven`` → ``van Beethoven, Ludwig``.

        Parameters
        ----------
        name:
            Natural-order personal name, e.g. ``"Winston Churchill"`` or
            ``"Gabriel García Márquez"``.
        locale:
            BCP 47 locale hint (e.g. ``"es"``, ``"pt"``, ``"ar"``).  Used to
            activate locale-sensitive branches; may be ``None``.

        Returns
        -------
        str
            Inverted name in indexing form, or the original string if no
            inversion rule applies.
        """
            # ── Already inverted ──────────────────────────────────────────────────────
        if "," in name:
            return name

        # ── CJK passthrough ───────────────────────────────────────────────────────
        if is_cjk(name) or (locale and locale.startswith(("zh", "ja", "ko"))):
            return name

        tokens = split_tokens(name)
        if len(tokens) <= 1:
            return name

        lower_tokens = [token.lower().strip(".,") for token in tokens]

        # ── Strip generational suffix ─────────────────────────────────────────────
        suffix = ""
        if lower_tokens[-1] in GENERATIONAL_SUFFIXES:
            suffix = tokens[-1]
            tokens = tokens[:-1]
            lower_tokens = lower_tokens[:-1]
            if len(tokens) <= 1:
                # e.g. "Cher Jr." — mononym with suffix; leave as-is after stripping
                result = tokens[0] if tokens else name
                return f"{result}, {suffix}" if suffix else result

        # ── Hyphenated Arabic prefix (al-Rashid, el-Sisi, abu-Bakr) ─────────────
        # Treat the final token as the surname if it carries a hyphenated prefix,
        # regardless of position.
        if HYPHENATED_ARABIC_PREFIXES.match(tokens[-1]):
            family = tokens[-1]
            given  = " ".join(tokens[:-1])
            result = f"{family}, {given}".strip(", ")
            return f"{result}, {suffix}" if suffix else result

        # ── Mac/Mc compound surname (two trailing tokens) ─────────────────────────
        # "Duncan MacDougall" → "MacDougall, Duncan"
        # "John Mac Donald"   → "Mac Donald, John"  (space form, two tokens)
        if len(tokens) >= 3:
            if MAC_MC.match(tokens[-1]):
                # Single-token Mac/Mc: treat last token as family name (falls through
                # to standard logic below — no special case needed).
                pass
            elif tokens[-2].lower() in ("mac", "mc"):
                # Two-token form: "Mac Donald" — combine last two as family name.
                # (MAC_MC itself requires an uppercase letter immediately after
                # "Mac"/"Mc" *within the same token* -- e.g. "MacDonald" -- so it
                # can never match a bare "Mac"/"Mc" token on its own; checking
                # membership in ("mac", "mc") directly is what actually detects
                # this space-separated form.)
                family = " ".join(tokens[-2:])
                given  = " ".join(tokens[:-2])
                result = f"{family}, {given}".strip(", ")
                return f"{result}, {suffix}" if suffix else result

        # ── Portuguese filial markers ─────────────────────────────────────────────
        if len(tokens) >= 3 and lower_tokens[-1] in PORTUGUESE_FILIAL_MARKERS:
            family = " ".join(tokens[-2:])
            given  = " ".join(tokens[:-2])
            result = f"{family}, {given}".strip(", ")
            return f"{result}, {suffix}" if suffix else result

        # ── Spanish/Portuguese connectors ─────────────────────────────────────────
        def _last_spanish_connector():
            for idx in range(len(tokens) - 1):
                if lower_tokens[idx] == "del":
                    return idx, 1
                if lower_tokens[idx] == "de":
                    if idx + 1 < len(tokens) and lower_tokens[idx + 1] in SPANISH_PARTICLE_ARTICLES:
                        return idx, 2
                    return idx, 1
            return None, 0

        connector_index, connector_length = _last_spanish_connector()
        if connector_index is not None and (
            locale and locale.startswith(("es", "pt"))
            or "de" in lower_tokens
            or "del" in lower_tokens
        ):
            if connector_index >= 2 and lower_tokens[connector_index - 1] in WIDOW_MARKERS:
                family_start = connector_index - 2
                family = " ".join(tokens[family_start:])
                given  = " ".join(tokens[:family_start])
                result = f"{family}, {given}".strip(", ")
                return f"{result}, {suffix}" if suffix else result

            prefix_len  = connector_index
            suffix_len  = len(tokens) - (connector_index + connector_length)

            if connector_length == 2 and prefix_len <= 2:
                family = " ".join(tokens[connector_index + connector_length:])
                given  = " ".join(tokens[: connector_index + connector_length])
                result = f"{family}, {given}".strip(", ")
                return f"{result}, {suffix}" if suffix else result

            if lower_tokens[connector_index] == "del" and prefix_len <= 2:
                family = " ".join(tokens[connector_index + connector_length:])
                given  = " ".join(tokens[: connector_index + connector_length])
                result = f"{family}, {given}".strip(", ")
                return f"{result}, {suffix}" if suffix else result

            if lower_tokens[connector_index] == "de" and prefix_len == 1 and suffix_len == 1:
                family = " ".join(tokens[connector_index + connector_length:])
                given  = " ".join(tokens[: connector_index + connector_length])
                result = f"{family}, {given}".strip(", ")
                return f"{result}, {suffix}" if suffix else result

            if prefix_len >= 3:
                family = " ".join(tokens[1:])
                given  = tokens[0]
                result = f"{family}, {given}".strip(", ")
                return f"{result}, {suffix}" if suffix else result

        # ── Standard particle walk (van, von, de, etc.) ───────────────────────────
        i = len(tokens) - 1
        while i - 1 >= 0 and tokens[i - 1].lower().strip(".,") in PARTICLES:
            i -= 1

        family = " ".join(tokens[i:])
        given  = " ".join(tokens[:i])
        result = f"{family}, {given}".strip(", ")
        return f"{result}, {suffix}" if suffix else result

    def invert(self, name: str, locale: Optional[str] = None, prefer_authority: bool = True) -> NameInversionResult:
        if not name:
            return NameInversionResult("", None, None, False)

        name = name.strip()
        rule_value = self._fast_invert(name, locale)

        authority_term = None
        if prefer_authority:
            cache_key = f"resolved:{name}"

            # ── Check cache first ──────────────────────────────────────────────
            if self._conn is not None:
                try:
                    row = self._conn.execute(
                        "SELECT value FROM cache WHERE key = ?", (cache_key,)
                    ).fetchone()
                    if row is not None:
                        authority_term = row[0] or None
                except Exception:
                    pass

            # ── Cache miss: go live ────────────────────────────────────────────
            if authority_term is None:                        # ← was `is not None`
                viaf_entry = self._viaf_autosuggest(name)
                if viaf_entry:
                    authority_term = self.fetch_authority_from_autosuggest_entry(viaf_entry)

                print(f"Caching resolved heading: {authority_term!r}")
                if self._conn is not None:
                    try:
                        self._conn.execute(
                            "INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)",
                            (cache_key, authority_term or "")
                        )
                        self._conn.commit()
                    except Exception:
                        pass

        if authority_term:
            return NameInversionResult(
                display_value=authority_term,
                authority_term=authority_term,
                rule_suggestion=rule_value,
                used_authority=True,
            )

        return NameInversionResult(
            display_value=rule_value,
            authority_term=None,
            rule_suggestion=rule_value,
            used_authority=False,
        )

    def cache_resolved_heading(
        self,
        name: str,
        heading: str,
        reason: Optional[str] = None,
        locale: Optional[str] = None,
        user_edited: bool = False,
    ) -> None:
        """Write a user-confirmed heading to the cache, overwriting any prior entry."""
        if not self._conn or not name or not heading:
            return
        try:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache "
                "(key, value, reason, locale, user_edited) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    f"resolved:{name.strip()}",
                    heading.strip(),
                    reason,
                    locale,
                    1 if user_edited else 0,
                )
            )
            self._conn.commit()
            print(f"User correction cached: {name!r} → {heading!r} (reason={reason!r})")
        except Exception as exc:
            print(f"Failed to cache user correction for {name!r}: {exc}")
