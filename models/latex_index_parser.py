import re
import bisect
from pathlib import Path

class LatexIndexParser:
    """Scans raw LaTeX text streams to extract structural index macro parameters cleanly."""
    
    INDEX_PATTERN = re.compile(r'\\index\b')
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
        
        full_content = full_content.replace('\r\n', '\n').replace('\r', '\n')
        line_offsets = cls._build_line_offset_map(full_content)
        working_content = cls._scrub_macro_definitions(full_content)
        running_id = start_id

        for match in cls.INDEX_PATTERN.finditer(working_content):
            absolute_index = match.start()
            line_idx, col_idx = cls._compute_coordinates(absolute_index, line_offsets)

            start_pos = match.end()
            start_pos = cls._skip_spaces_and_comments(working_content, start_pos)

            if start_pos < len(working_content) and working_content[start_pos] == '[':
                start_pos = cls._skip_optional_args(working_content, start_pos)
                start_pos = cls._skip_spaces_and_comments(working_content, start_pos)

            if start_pos >= len(working_content) or working_content[start_pos] != '{':
                continue

            inner_content, end_abs = cls._extract_balanced_braces(working_content, start_pos + 1)
            if end_abs == -1:
                continue

            end_line_idx, end_col_idx = cls._compute_coordinates(end_abs - 1, line_offsets)

            clean_inner_content, see_refs, seealso_refs = cls._extract_see_modifiers(inner_content)
            clean_inner_content, encap_format = cls._strip_global_encap_safe(clean_inner_content)
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

            safe_encap = encap_format if encap_format else "standard"
            stable_uid = f"{norm_path_str}:{line_idx}:{col_idx}"
            see_payload = cls._build_see_reference_payload(see_refs, seealso_refs)

            uid_dict = {
                "id": running_id,
                "unique_id_number": running_id,
                "uid": stable_uid,
                "file_path": norm_path_str,
                "line_number": line_idx,
                "column_offset": col_idx,
                "end_line_number": end_line_idx,
                "end_column_offset": end_col_idx,
                "absolute_index": absolute_index,
                "end_absolute_index": end_abs - 1,
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
        offsets = [0]
        for i, char in enumerate(raw_text):
            if char == '\n':
                offsets.append(i + 1)
        return offsets

    @classmethod
    def _compute_coordinates(cls, absolute_pos: int, line_offsets: list[int]) -> tuple[int, int]:
        line_idx = bisect.bisect_right(line_offsets, absolute_pos) - 1
        line_num = line_idx + 1
        col_num = (absolute_pos - line_offsets[line_idx]) + 1
        return line_num, col_num

    @classmethod
    def _extract_balanced_braces(cls, text: str, start_pos: int) -> tuple[str, int]:
        brace_count = 1
        current_pos = start_pos
        result_chars = []
        text_len = len(text)
        
        while current_pos < text_len:
            char = text[current_pos]
            if char == '\\' and (current_pos + 1 < text_len) and text[current_pos + 1] in ('{', '}'):
                result_chars.append(text[current_pos:current_pos + 2])
                current_pos += 2
                continue
                
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return "".join(result_chars), current_pos + 1
                    
            result_chars.append(char)
            current_pos += 1
        return "", -1

    @classmethod
    def _strip_global_encap_safe(cls, text: str) -> tuple[str, str]:
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
        text_len = len(text)
        while idx < text_len:
            char = text[idx]
            if char in (' ', '\t', '\r', '\n'):
                idx += 1
                continue
            if char == '%' and (idx == 0 or text[idx - 1] != '\\'):
                while idx < text_len and text[idx] != '\n':
                    idx += 1
                continue
            return idx if char == target else -1
        return -1

    @classmethod
    def _skip_spaces_and_comments(cls, text: str, idx: int) -> int:
        text_len = len(text)
        while idx < text_len:
            char = text[idx]
            if char in (' ', '\t', '\r', '\n'):
                idx += 1
                continue
            if char == '%' and (idx == 0 or text[idx - 1] != '\\'):
                while idx < text_len and text[idx] != '\n':
                    idx += 1
                continue
            break
        return idx

    @classmethod
    def _skip_optional_args(cls, text: str, idx: int) -> int:
        text_len = len(text)
        while idx < text_len:
            next_idx = cls._scan_to_char(text, idx, '[')
            if next_idx == -1:
                break
            depth = 0
            idx = next_idx
            while idx < text_len:
                c = text[idx]
                if c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
                    if depth == 0:
                        idx += 1
                        break
                idx += 1
        return idx

    @classmethod
    def _scrub_macro_definitions(cls, text: str) -> str:
        working_chars = list(text)
        text_len = len(text)
        DEF_STYLE_KEYWORDS = {'def'}

        for match in cls.MACRO_START_PATTERN.finditer(text):
            keyword = match.group(1)
            start_macro_idx = match.start()
            idx = match.end()

            if keyword in DEF_STYLE_KEYWORDS:
                while idx < text_len and text[idx] in (' ', '\t'):
                    idx += 1

                if idx >= text_len or text[idx] != '\\':
                    continue

                idx += 1
                if idx < text_len and text[idx].isalpha():
                    while idx < text_len and text[idx].isalpha():
                        idx += 1
                elif idx < text_len:
                    idx += 1

                while idx < text_len and (text[idx] in (' ', '\t') or text[idx] == '#' or text[idx].isdigit()):
                    idx += 1

            else:
                name_open = cls._scan_to_char(text, idx, '{')
                if name_open == -1:
                    continue

                name_close = cls._find_closing_brace_index(text, name_open)
                if name_close == -1:
                    continue

                idx = name_close + 1
                idx = cls._skip_optional_args(text, idx)

            body_open = cls._scan_to_char(text, idx, '{')
            if body_open == -1:
                continue

            body_close = cls._find_closing_brace_index(text, body_open)
            if body_close == -1:
                continue

            for fill_idx in range(start_macro_idx, body_close + 1):
                if working_chars[fill_idx] not in ('\n', '\r'):
                    working_chars[fill_idx] = ' '

        return "".join(working_chars)

    @classmethod
    def _find_closing_brace_index(cls, text: str, start_brace_pos: int) -> int:
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
            inner, _ = cls._extract_balanced_braces(text, match.end())
            if inner:
                ref = inner.strip()
                if keyword == "seealso":
                    seealso_refs.append(ref)
                else:
                    see_refs.append(ref)

            end_pos = match.end() + len(inner) + 1
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
        return {
            "see": see_list or [],
            "seealso": seealso_list or [],
            "has_references": bool(see_list or seealso_list)
        }
