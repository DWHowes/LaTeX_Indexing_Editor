import os

class TextSanitizer:
    """
    Model layer processing utility for sanitizing and normalizing 
    cross-platform file storage paths. Completely decoupled from UI views.
    """
    
    @staticmethod
    def normalize_file_path(raw_path: str) -> str:
        """
        Removes hidden control characters, strips enclosing quotes, 
        and normalizes slashes to cross-platform safe formats.
        """
        if not raw_path:
            return ""
        
        # Cast to string and strip enclosing quote artifacts or white-spaces
        cleaned = str(raw_path).strip().strip("'\"")
        
        # Eliminate structural control character leakage (null bytes, newlines)
        cleaned = cleaned.replace('\x00', '').replace('\n', '').replace('\r', '')
        
        # Convert slashes to system-native separators safely
        normalized = os.path.normpath(cleaned)
        
        # Resolve to absolute format if the file physically exists on the disk
        if os.path.exists(normalized):
            normalized = os.path.normpath(os.path.abspath(normalized))
        
        return normalized
    
    @staticmethod
    def sanitize(raw_file_contents_string: str) -> str:
        """
        Model Layer Business Logic Contract.
        Normalizes line endings and clears non-printable control blocks 
        to safeguard document character index positioning maps.
        """
        if not raw_file_contents_string:
            return ""

        # Normalize carriage-return line structures to standard Unix layouts
        # This prevents coordinate calculations from drifting inside the editor view
        processed_text = str(raw_file_contents_string).replace("\r\n", "\n").replace("\r", "\n")
        
        # Strip disruptive absolute structural control bytes (e.g., Null characters)
        processed_text = processed_text.replace("\x00", "")
        
        return processed_text
