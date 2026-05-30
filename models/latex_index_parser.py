import re
import bisect
from pathlib import Path

class LatexIndexParser:
    """Scans raw LaTeX text streams to extract structural index macro parameters cleanly."""
    
    INDEX_PATTERN = re.compile(r'\\index\{')
    MACRO_START_PATTERN = re.compile(r'\\(newcommand|renewcommand|def|providecommand|DeclareRobustCommand)\b')

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
        
        # 1. CRITICAL: Standardize line breaks across ALL operating systems (\r\n -> \n)
        # This guarantees that the string layout inside Python perfectly matches QPlainTextEdit
        full_content = full_content.replace('\r\n', '\n').replace('\r', '\n')
        
        # 2. ANCHOR: Build the immutable baseline offset map immediately from raw, unmutated text
        line_offsets = cls._build_line_offset_map(full_content)
        cls._offset_map = line_offsets # Keep for backward compatibility

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
    def _scrub_macro_definitions(cls, text: str) -> str:
        """Masks structural LaTeX macro definitions using character-count matching to safely ignore noise inside templates."""
        working_chars = list(text)
        text_len = len(text)
        
        for match in cls.MACRO_START_PATTERN.finditer(text):
            idx = match.end()
            abort_scrub = False
            
            # Lookahead scanner to isolate target definition block structures securely
            while idx < text_len:
                if text[idx].isspace():
                    idx += 1
                elif text[idx] == '[':
                    # Secure Loop Guard: Prevent unclosed brackets from spinning out of boundaries
                    while idx < text_len and text[idx] != ']':
                        idx += 1
                    if idx >= text_len:
                        abort_scrub = True
                        break
                    idx += 1
                elif text[idx] == '{':
                    end_name_brace = cls._find_closing_brace_index(text, idx)
                    if end_name_brace != -1:
                        next_idx = end_name_brace + 1
                        while next_idx < text_len and (text[next_idx].isspace() or text[next_idx] == '['):
                            if text[next_idx].isspace():
                                next_idx += 1
                            elif text[next_idx] == '[':
                                while next_idx < text_len and text[next_idx] != ']':
                                    next_idx += 1
                                if next_idx >= text_len:
                                    break
                                next_idx += 1
                                
                        if next_idx < text_len and text[next_idx] == '{':
                            idx = next_idx
                            break
                    break
                else:
                    idx += 1

            if abort_scrub or idx >= text_len:
                continue

            if text[idx] == '{':
                end_pos = cls._find_closing_brace_index(text, idx)
                if end_pos != -1:
                    # Fix: Mask macro text bounds with periods ('.') instead of spaces to prevent backtracking
                    for fill_idx in range(match.start(), end_pos + 1):
                        if working_chars[fill_idx] not in ('\n', '\r'):
                            working_chars[fill_idx] = '.'
                            
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
        """Extracts main index content and parses embedded \\see and \\seealso references safely."""
        see_refs = []
        seealso_refs = []
        
        see_pattern = re.compile(r'\\seealso\{([^}]+)\}|\\see\{([^}]+)\}')
        for match in see_pattern.finditer(text):
            ref_text = match.group(1) if match.group(1) else match.group(2)
            if match.group(1):  
                seealso_refs.append(ref_text.strip())
            else:  
                see_refs.append(ref_text.strip())
        
        cleaned_text = see_pattern.sub('', text).strip()
        
        # Fix Data Corruption Hazard: Remove dangling or orphan makeindex pipe operators
        if cleaned_text.endswith('|'):
            cleaned_text = cleaned_text[:-1].strip()
        if cleaned_text.startswith('|'):
            cleaned_text = cleaned_text[1:].strip()
            
        return cleaned_text, see_refs, seealso_refs

    @classmethod
    def _build_see_reference_payload(cls, see_list: list[str], seealso_list: list[str]) -> dict:
        """Structures see/seealso references into a normalized dictionary format."""
        return {
            "see": see_list if see_list else None,
            "seealso": seealso_list if seealso_list else None,
            "has_references": bool(see_list or seealso_list)
        }
