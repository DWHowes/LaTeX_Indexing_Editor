import os

class TextSanitizer:
    """
    Model layer processing utility for sanitizing and normalizing 
    cross-platform file storage paths. Completely decoupled from UI views.
    """
    
    @staticmethod
    def clean_windows_path(raw_path: str) -> str:
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
