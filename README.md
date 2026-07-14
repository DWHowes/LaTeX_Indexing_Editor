# LaTeX Indexing Editor

 
A high-performance desktop application built with Python and PySide6 (Qt) designed to accelerate the indexing process for complex LaTeX documents. The system provides a real-time, non-destructive editing workspace that synchronizes layout tree views, localized relational memory stores, and active document streams simultaneously without interrupting compilation pipelines.

## Installation

### For developers

1. **Clone the repository**

   ```
   git clone https://github.com/DWHowes/LaTeX_Indexing_Editor.git
   cd LaTeX_Indexing_Editor
   ```

2. **Create a virtual environment** (Python 3.13+)

   ```
   python -m venv .venv
   ```

   Activate it:

   - Windows (PowerShell): `.venv\Scripts\Activate.ps1`
   - macOS/Linux: `source .venv/bin/activate`

   Then install the runtime dependencies:

   ```
   pip install -r requirements.txt
   ```

3. **Run the app**

   ```
   python main.py
   ```

### For indexer end users

Packaging of the app as a standalone installer isn't done yet — this section is a placeholder until a packaged build is available.
