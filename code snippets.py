import sqlite3
import json
from PySide6.QtCore import Qt
...
            cursor.execute("""
                CREATE TABLE index_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    heading_id INTEGER,
                    unique_id_number INTEGER,
                    file_path TEXT,
                    line INTEGER,
                    col INTEGER,
                    absolute_position INTEGER,
                    encap TEXT,
                    see TEXT,
                    seealso TEXT,
                    FOREIGN KEY(heading_id) REFERENCES index_headings(id) ON DELETE CASCADE
                )""")
...
                                see_json = json.dumps(rec.get("see")) if rec.get("see") else None
                                seealso_json = json.dumps(rec.get("seealso")) if rec.get("seealso") else None

                                cursor.execute("""
                                    INSERT INTO index_references (
                                        heading_id, unique_id_number, file_path, line, col,
                                        absolute_position, encap, see, seealso
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    heading_db_id,
                                    int(uid_num),
                                    str(f_path),
                                    int(line_coord),
                                    int(col_coord),
                                    safe_abs_pos,
                                    str(encap_val),
                                    see_json,
                                    seealso_json
                                ))
...
        import os
        import sqlite3
        import json
        ...
            ref_record = {
                ...
                "absolute_position": int(abs_pos_val) if abs_pos_val is not None else None,
                "encap": str(encap_val),
                "see": json.loads(r['see']) if r.get('see') else None,
                "seealso": json.loads(r['seealso']) if r.get('seealso') else None,
            }