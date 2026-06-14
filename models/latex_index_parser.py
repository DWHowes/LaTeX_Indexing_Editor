import re
import bisect
from pathlib import Path

class LatexIndexParser:
    """Scans raw LaTeX text streams to extract structural index macro parameters cleanly."""
    
    INDEX_PATTERN = re.compile(r'\\index\{')
    # Modified macro start pattern: supports word boundaries or direct backslash triggers (\def\fn)
    MACRO_START_PATTERN = re.compile(r'\\(newcommand|renewcommand|providecommand|DeclareRobustCommand|def)(?=\b|\\)')

    @classmethod
    def parse_file(cls, file_path: str, start_id: int = 1) -> tuple[list[tuple[list, dict]], int]:
        extracted_payloads = []
        path_obj = Path(file_path).resolve()
        norm_path_str = path_obj.as_posix()
        
        if not path_obj.exists() or not path_obj.is_file():
            return extracted_payloads, start_id

        try:
            full_content = path_obj.read_text(encoding='utf-8')
        except Exception as e:
            print(f"ERROR: Failed to read file {norm_path_str} for indexing: {e}")
            return extracted_payloads, start_id
        
        # Standardize line breaks across ALL operating systems (\r\n -> \n)
        # This guarantees that the string layout inside Python perfectly matches QPlainTextEdit
        full_content = full_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # Build the immutable baseline offset map immediately from raw, unmutated text
        line_offsets = cls._build_line_offset_map(full_content)
        # cls._offset_map = line_offsets # Keep for backward compatibility

        # Scrubbing uses strict 1:1 character index masking (preserving exact \n positions)
        working_content = cls._scrub_macro_definitions(full_content)
        running_id = start_id
        for match in cls.INDEX_PATTERN.finditer(working_content):
            absolute_index = match.start()
            
            start_pos = match.end()
            inner_content = cls._extract_balanced_braces(working_content, start_pos)
            
            if not inner_content:
                continue

            # Extract see/seealso references BEFORE cleaning
            clean_inner_content, see_refs, seealso_refs = cls._extract_see_modifiers(inner_content)
            
            # Strip encapsulation from cleaned content
            clean_inner_content, encap_format = cls._strip_global_encap_safe(clean_inner_content)

            # Process individual layout tiers cleanly
            levels = cls._split_levels_safe(clean_inner_content)
            
            parts_list = []
            for level in levels:
                level_cleaned = level.strip().replace('\n', ' ')
                level_cleaned = " ".join(level_cleaned.split())
                
                if not level_cleaned:
                    continue
                
                display_text = cls._extract_display_string_safe(level_cleaned)
                parts_list.append(display_text.strip())
            
            if not parts_list:
                continue

            # Compute coordinates
            line_idx, col_idx = cls._compute_coordinates(absolute_index, line_offsets)
            safe_encap = encap_format if encap_format else "standard"
            stable_uid = f"{norm_path_str}:{line_idx}:{col_idx}"

            # Build reference metadata
            see_payload = cls._build_see_reference_payload(see_refs, seealso_refs)

            # Enhanced UID dictionary with cross-reference data
            uid_dict = {
                "id": running_id,
                "unique_id_number": running_id,
                "uid": stable_uid,
                "file_path": norm_path_str,
                "line_number": line_idx,
                "column_offset": col_idx,
                "absolute_index": absolute_index,
                "encap": safe_encap,
                "see": see_payload["see"],           
                "seealso": see_payload["seealso"],   
                "has_references": see_payload["has_references"]  
            }
            
            extracted_payloads.append((parts_list, uid_dict))
            running_id += 1

        return extracted_payloads, running_id

    @classmethod
    def _build_line_offset_map(cls, raw_text: str) -> list[int]:
        """Calculates absolute start index positions for every text row to allow O(log N) coordinate lookups."""
        offsets = [0]
        for i, char in enumerate(raw_text):
            if char == '\n':
                offsets.append(i + 1)
        return offsets

    @classmethod
    def _compute_coordinates(cls, absolute_pos: int, line_offsets: list[int]) -> tuple[int, int]:
        """Maps an absolute character index to 1-based (line, column) coordinate pairing cleanly."""
        line_idx = bisect.bisect_right(line_offsets, absolute_pos) - 1
        line_num = line_idx + 1
        col_num = (absolute_pos - line_offsets[line_idx]) + 1
        return line_num, col_num

    @classmethod
    def _extract_balanced_braces(cls, text: str, start_pos: int) -> str:
        """Performs precise bracket pairing checks, parsing deeply nested parameter blocks securely with escape guards."""
        brace_count = 1
        current_pos = start_pos
        result_chars = []
        text_len = len(text)
        
        while current_pos < text_len:
            char = text[current_pos]
            
            # Escape sequence guard: skip literal brace character sequences like \{ or \}
            if char == '\\' and (current_pos + 1 < text_len) and text[current_pos + 1] in ('{', '}'):
                result_chars.append(text[current_pos:current_pos+2])
                current_pos += 2
                continue
                
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return "".join(result_chars)
                    
            result_chars.append(char)
            current_pos += 1
        return ""

    @classmethod
    def _strip_global_encap_safe(cls, text: str) -> tuple[str, str]:
        """Strips text-formatting or range modifiers from formatting bounds handling escaped operators."""
        text = text.strip().replace(r'\string', '')
        brace_level = 0
        text_len = len(text)
        
        for i in range(text_len - 1, -1, -1):
            char = text[i]
            if char == '}':
                brace_level += 1
            elif char == '{':
                brace_level -= 1
            elif char == '|' and brace_level == 0:
                # Safe Guard Check: Ensure the makeindex pipe operator isn't explicitly escaped via a backslash
                if i > 0 and text[i-1] == '\\':
                    continue
                    
                clean_path = text[:i].strip()
                encap_format = text[i+1:].strip()
                if encap_format in ('(', ')'):
                    encap_format = "range"
                return clean_path, encap_format
                
        return text, "standard"

    @classmethod
    def _scan_to_char(cls, text: str, idx: int, target: str) -> int:
        """
        Advance idx forward through optional whitespace and LaTeX comment lines
        until we reach `target` or a non-whitespace, non-comment character.

        Returns the index of `target` if found, or -1 if something else is hit first.

        Handles:
        - Blank space / tabs
        - Full-line and inline comments  (% ... \\n)
        """
        text_len = len(text)
        while idx < text_len:
            char = text[idx]

            if char in (' ', '\t', '\r', '\n'):
                idx += 1
                continue

            # Unescaped '%' starts a comment — skip to end of line
            if char == '%' and (idx == 0 or text[idx - 1] != '\\'):
                while idx < text_len and text[idx] != '\n':
                    idx += 1
                continue

            # We've hit a real character
            return idx if char == target else -1

        return -1

    @classmethod
    def _skip_optional_args(cls, text: str, idx: int) -> int:
        """
        Skip any number of optional argument blocks [...] that may appear between
        the name block and the body block (e.g. [1], [default value]).

        Handles nested brackets inside the default-value form:  [some {text}]
        Returns the index of the first character that is not part of an optional block.
        """
        text_len = len(text)
        while idx < text_len:
            # Consume whitespace / comments before deciding
            next_idx = cls._scan_to_char(text, idx, '[')
            if next_idx == -1:
                # Not a '[' — stop here (caller will look for '{')
                break

            # Balance brackets (default values can contain braces but not nested [])
            depth = 0
            idx = next_idx
            while idx < text_len:
                c = text[idx]
                if c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
                    if depth == 0:
                        idx += 1   # step past the closing ']'
                        break
                idx += 1

        return idx

    @classmethod
    def _scrub_macro_definitions(cls, text: str) -> str:
        """
        Masks structural LaTeX macro definitions to prevent their bodies from
        being parsed as live index entries.

        Strict MVC Compliance: Completely free of type reflection or file I/O.
        Preserves newline characters so vertical editor coordinates stay stable.

        Supported forms
        ---------------
        \\newcommand{\\name}[n][default]{body}
        \\renewcommand{\\name}[n]{body}
        \\providecommand{\\name}[n]{body}
        \\DeclareRobustCommand{\\name}[n]{body}
        \\def\\name#1#2{body}          ← no brace-wrapped name block
        """

        working_chars = list(text)
        text_len = len(text)

        # Keyword set that uses \def-style syntax (no brace-wrapped name block).
        # These are followed immediately by the control-sequence name token, then
        # optional #-parameter tokens, then the replacement body in braces.
        DEF_STYLE_KEYWORDS = {'def'}

        for match in cls.MACRO_START_PATTERN.finditer(text):
            keyword = match.group(1)          # e.g. 'newcommand', 'def'
            start_macro_idx = match.start()   # position of the leading '\'
            idx = match.end()                 # first char after the keyword token

            # ------------------------------------------------------------------
            # Handle the name token
            # ------------------------------------------------------------------
            if keyword in DEF_STYLE_KEYWORDS:
                # \def syntax:  \def\cmdname#1#2{body}
                #
                # After the keyword, skip whitespace then consume the control
                # sequence name  (\cmdname).  The name is NOT brace-wrapped.
                # We just scan forward until we exit the name token (i.e. hit a
                # character that cannot be part of a control word: space, {, #).
                while idx < text_len and text[idx] in (' ', '\t'):
                    idx += 1

                if idx >= text_len or text[idx] != '\\':
                    # Malformed or exotic \def variant — skip safely
                    continue

                # Consume the backslash and the control word letters
                idx += 1  # skip '\'
                if idx < text_len and text[idx].isalpha():
                    # Multi-letter control word
                    while idx < text_len and text[idx].isalpha():
                        idx += 1
                elif idx < text_len:
                    # Single non-letter control symbol  (\def\,{body})
                    idx += 1

                # Consume any #n parameter tokens  (#1, #2, …)
                while idx < text_len and text[idx] in (' ', '\t') or (text[idx] == '#') or text[idx].isdigit():
                    idx += 1

            else:
                # \newcommand / \renewcommand / \providecommand / \DeclareRobustCommand
                #
                # Syntax:  \newcommand{\cmdname}[n][default]{body}
                #
                # Consume the name block  {\cmdname}  then optional args [n][default].

                name_open = cls._scan_to_char(text, idx, '{')
                if name_open == -1:
                    continue

                name_close = cls._find_closing_brace_index(text, name_open)
                if name_close == -1:
                    continue

                idx = name_close + 1  # resume AFTER the name block

                # Skip any optional argument blocks:  [1]  or  [default value]
                idx = cls._skip_optional_args(text, idx)

            # ------------------------------------------------------------------
            # Find and balance the BODY block  { ... }
            # ------------------------------------------------------------------
            body_open = cls._scan_to_char(text, idx, '{')
            if body_open == -1:
                # No body block found (e.g. \def\foo\bar  — aliasing, not defining)
                continue

            body_close = cls._find_closing_brace_index(text, body_open)
            if body_close == -1:
                continue

            # ------------------------------------------------------------------
            # Mask from the macro keyword through the end of the body
            # Preserve '\n' / '\r' so editor line/column offsets stay intact.
            # ------------------------------------------------------------------
            for fill_idx in range(start_macro_idx, body_close + 1):
                if working_chars[fill_idx] not in ('\n', '\r'):
                    working_chars[fill_idx] = ' '

        return "".join(working_chars)

    @classmethod
    def _find_closing_brace_index(cls, text: str, start_brace_pos: int) -> int:
        """Locates the balancing closing brace index position tracking escaped backslash tokens."""
        brace_count = 0
        text_len = len(text)
        idx = start_brace_pos
        
        while idx < text_len:
            char = text[idx]
            if char == '\\' and (idx + 1 < text_len) and text[idx + 1] in ('{', '}'):
                idx += 2
                continue
                
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return idx
            idx += 1
            
        return -1

    @classmethod
    def _split_levels_safe(cls, text: str) -> list[str]:
        """Splits multi-tiered indices delimited by makeindex operators safely handling brace-grouped blocks."""
        levels = []
        current_part = []
        brace_level = 0
        idx = 0
        text_len = len(text)
        
        while idx < text_len:
            char = text[idx]
            
            if char == '\\' and (idx + 1 < text_len) and text[idx + 1] in ('!', '@', '|', '{', '}'):
                current_part.append(text[idx:idx+2])
                idx += 2
                continue
                
            if char == '{':
                brace_level += 1
            elif char == '}':
                brace_level -= 1
                
            if char == '!' and brace_level == 0:
                levels.append("".join(current_part))
                current_part = []
            else:
                current_part.append(char)
            idx += 1
            
        final_segment = "".join(current_part)
        levels.append(final_segment)
        return levels

    @classmethod
    def _extract_display_string_safe(cls, level_text: str) -> str:
        """Parses sort keys from display targets if delimited by the makeindex sorting operator safely."""
        brace_level = 0
        idx = 0
        text_len = len(level_text)
        
        while idx < text_len:
            char = level_text[idx]
            if char == '\\' and (idx + 1 < text_len) and level_text[idx + 1] == '@':
                idx += 2
                continue
                
            if char == '{':
                brace_level += 1
            elif char == '}':
                brace_level -= 1
            elif char == '@' and brace_level == 0:
                return level_text[idx+1:].strip()
            idx += 1
            
        return level_text.strip()

    @classmethod
    def _extract_see_modifiers(cls, text: str) -> tuple[str, list[str], list[str]]:
        see_refs = []
        seealso_refs = []
        cleaned_chars = list(text)

        see_pattern = re.compile(r'\\(seealso|see)\{')
        for match in see_pattern.finditer(text):
            keyword = match.group(1)
            inner = cls._extract_balanced_braces(text, match.end())
            if inner:  # skip empty \see{} or \seealso{}
                ref = inner.strip()
                if keyword == "seealso":
                    seealso_refs.append(ref)
                else:
                    see_refs.append(ref)

            # Mask out the full match including braces from cleaned output
            # regardless of whether inner was empty, to avoid leaving \see{} debris
            end_pos = match.end() + len(inner) + 1  # +1 for closing brace
            for i in range(match.start(), end_pos):
                if i < len(cleaned_chars):
                    cleaned_chars[i] = ' '

        cleaned_text = "".join(cleaned_chars).strip()

        if cleaned_text.endswith('|'):
            cleaned_text = cleaned_text[:-1].strip()
        if cleaned_text.startswith('|'):
            cleaned_text = cleaned_text[1:].strip()

        return cleaned_text, see_refs, seealso_refs

    @classmethod
    def _build_see_reference_payload(cls, see_list: list[str], seealso_list: list[str]) -> dict:
        """Structures see/seealso references into a normalized dictionary format."""
        return {
            "see": see_list or [],
            "seealso": seealso_list or [],
            "has_references": bool(see_list or seealso_list)
        }
