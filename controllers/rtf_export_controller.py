from pathlib import Path
from models.rtf_export_model import RtfExportMetadata, RtfExportEngine
from views.rtf_export_view import RtfExportView

class IndexExportController:
    """Coordinates lifecycle pipeline tasks between Model storage and View generation."""
    def __init__(self, metadata: RtfExportMetadata):
        self.meta = metadata
        self.engine = RtfExportEngine(metadata)

    def export_project_to_rtf(self, output_filename: str = "project_index.rtf") -> bool:
        """Walks active project files, updates indices, and exports compiled RTF documents."""
        combined_index_data = {}
        active_files = self.meta.get_active_tex_files()

        if not active_files:
            return False

        for tex_file in active_files:
            # Step 1: Run fast draftmode pass
            self.engine.compile_to_aux(tex_file)
            
            # Step 2: Extract index tokens
            ind_path = self.engine.generate_ind_file(tex_file)
            
            # Step 3: Try parsing data, fallback safely if document lacks indexing targets
            try:
                file_index_data = self.engine.parse_ind(ind_path)
                # Merge current file data dictionary results to main dictionary data
                for letter, entries in file_index_data.items():
                    combined_index_data.setdefault(letter, []).extend(entries)
            except FileNotFoundError:
                continue # Skip files without active entries

        if not combined_index_data:
            return False

        # Step 4: Render out data through View
        output_filepath = self.meta.project_root / output_filename
        RtfExportView.render(combined_index_data, output_filepath)
        return True
