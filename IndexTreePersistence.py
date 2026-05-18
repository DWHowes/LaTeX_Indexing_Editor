import os
import sqlite3
import json  
from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem
from PySide6.QtWidgets import QStyle

# --- REMOVED THE TOP-LEVEL INDEX_TREE_VIEW IMPORT TO COMPLETELY ELIMINATE THE CIRCULAR LOOP ---

class IndexTreePersistence:
    """
    Handles atomic serialization, transactional safety, and non-destructive relational 
    database reconstruction for the multi-column LaTeX Indexing Editor Tree.
    """

    @classmethod
    def save_to_db(cls, model, db_path: str, project_name: str = "", settings_dict: dict = None):
        """Flattens hierarchical multi-column headings and reference tokens into an SQLite table safely."""
        if model is None or not db_path:
            return

        if settings_dict is None:
            settings_dict = {}

        ROLE_UID_DATA = Qt.ItemDataRole.UserRole + 1
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()

            # Materialize clean metadata schemas
            cursor.execute("DROP TABLE IF EXISTS project_metadata")
            cursor.execute("CREATE TABLE project_metadata (key TEXT PRIMARY KEY, value TEXT)")
            cursor.execute("INSERT INTO project_metadata (key, value) VALUES (?, ?)", ("project_name", str(project_name)))
            
            for setting_key, setting_value in settings_dict.items():
                cursor.execute("INSERT INTO project_metadata (key, value) VALUES (?, ?)", (f"cfg_{setting_key}", str(setting_value)))

            # Initialize database tables
            cursor.execute("DROP TABLE IF EXISTS index_references")
            cursor.execute("DROP TABLE IF EXISTS index_headings")
            
            cursor.execute("""
                CREATE TABLE index_headings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    parent_id INTEGER,
                    name TEXT,
                    depth INTEGER
                )""")
                
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
                    see_references TEXT,       
                    seealso_references TEXT,   
                    has_references INTEGER,    
                    FOREIGN KEY(heading_id) REFERENCES index_headings(id) ON DELETE CASCADE
                )""")

            # Recursive walk tracking fully qualified absolute concatenated path strings
            def serialize_row_node(parent_qt_item, parent_db_id=None, current_depth=0, path_segments=None):
                if path_segments is None:
                    path_segments = []

                if not hasattr(parent_qt_item, "rowCount"):
                    return

                for i in range(parent_qt_item.rowCount()):
                    heading_item = parent_qt_item.child(i, 0)
                    if not heading_item:
                        continue
                        
                    current_node_text = heading_item.text().strip()
                    if not current_node_text:
                        continue
                    
                    # Accumulate individual segments to preserve structural parent-subheading relationships flawlessly
                    node_full_path_list = path_segments + [current_node_text]
                    full_heading_path_str = "!".join(node_full_path_list)
                    
                    # Store the absolute unified path string into the 'name' column for proper token-splitting on load
                    cursor.execute("""
                        INSERT INTO index_headings (parent_id, name, depth)
                        VALUES (?, ?, ?)
                    """, (parent_db_id, full_heading_path_str, current_depth))
                    
                    heading_db_id = cursor.lastrowid
                    
                    row_parent = heading_item.parent() or model.invisibleRootItem()
                    row_index = heading_item.row()
                    
                    reference_cell = row_parent.child(row_index, 1)
                    if reference_cell:
                        records_list = reference_cell.data(ROLE_UID_DATA)
                        
                        if records_list and isinstance(records_list, list):
                            for rec in records_list:
                                if not rec or not isinstance(rec, dict):
                                    continue
                                    
                                uid_num = rec.get("unique_id_number") or rec.get("id") or 0
                                f_path = rec.get("file_path") or rec.get("path") or ""
                                line_coord = rec.get("line_number") or rec.get("line") or 1
                                col_coord = rec.get("column_offset") or rec.get("col") or 0
                                abs_pos = rec.get("absolute_position") 
                                encap_val = rec.get("encap") or "standard" 

                                see_array = rec.get("see") or []
                                seealso_array = rec.get("seealso") or []
                                has_ref_flag = 1 if (rec.get("has_references") or bool(see_array or seealso_array)) else 0

                                json_see = json.dumps(see_array) if isinstance(see_array, list) else json.dumps([])
                                json_seealso = json.dumps(seealso_array) if isinstance(seealso_array, list) else json.dumps([])

                                safe_abs_pos = int(abs_pos) if abs_pos is not None else None

                                cursor.execute("""
                                    INSERT INTO index_references (
                                        heading_id, unique_id_number, file_path, line, col, 
                                        absolute_position, encap, see_references, seealso_references, has_references
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    heading_db_id,
                                    int(uid_num),
                                    str(f_path),
                                    int(line_coord),
                                    int(col_coord),
                                    safe_abs_pos, 
                                    str(encap_val),
                                    json_see,        
                                    json_seealso,    
                                    has_ref_flag     
                                ))
                        
                    if heading_item.rowCount() > 0:
                        serialize_row_node(heading_item, heading_db_id, current_depth + 1, node_full_path_list)

            root_item = model if hasattr(model, "invisibleRootItem") else model
            serialize_row_node(root_item.invisibleRootItem() if hasattr(root_item, "invisibleRootItem") else root_item)
            conn.commit()
            
        except Exception as transaction_fault:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"CRITICAL: Failed to flatten index tables to database file surface: {transaction_fault}")
            raise transaction_fault
        finally:
            conn.close()

    @classmethod
    def load_from_db(cls, model, view, db_path: str):
        """
        Reconstructs multi-column alignment structures using relational database paths.
        Guarantees that the heading-subheading relationship is perfectly preserved on load
        by extracting full path maps and sorting elements strictly by taxonomy depth layers.
        """
        # ----------------------------------------------------------------------
        # DEFERRED INLINE IMPORT: Safe lazy-load completely clears the circular boot crash
        # ----------------------------------------------------------------------
        from IndexTreeView import CaseInsensitiveItem  

        main_win = view.window()
        controller = getattr(main_win, "index_controller", None)
        if not controller:
            return

        ROLE_UID_DATA = Qt.ItemDataRole.UserRole + 1

        view.setSortingEnabled(False)
        model.clear()
        model.setHorizontalHeaderLabels(["Index Terms", "References"])

        if not os.path.exists(db_path):
            view.setSortingEnabled(True)
            return

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            headings = [dict(r) for r in cursor.execute("SELECT * FROM index_headings").fetchall()]
            references = [dict(r) for r in cursor.execute("SELECT * FROM index_references").fetchall()]
            conn.close()
        except sqlite3.OperationalError:
            view.setSortingEnabled(True)
            return

        if not headings:
            view.setSortingEnabled(True)
            return

        ref_lookup_map = {}
        for r in references:
            h_id = r['heading_id']
            line_val = r['line']
            col_val = r['col']
            f_path = r['file_path']
            uid_num = r['unique_id_number']
            abs_pos_val = r.get('absolute_position')
            encap_val = r.get('encap') or "standard"

            raw_see = r.get('see_references')
            raw_seealso = r.get('seealso_references')
            raw_has_ref = r.get('has_references', 0)

            try:
                decoded_see = json.loads(raw_see) if raw_see else []
            except Exception:
                decoded_see = []

            try:
                decoded_seealso = json.loads(raw_seealso) if raw_seealso else []
            except Exception:
                decoded_seealso = []

            ref_record = {
                "uid": f"{f_path}:{line_val}:{col_val}",
                "unique_id_number": int(uid_num),
                "id": int(uid_num), 
                "file_path": str(f_path),
                "line_number": int(line_val),
                "column_offset": int(col_val),
                "line": int(line_val),
                "col": int(col_val),
                "absolute_position": int(abs_pos_val) if abs_pos_val is not None else None,
                "encap": str(encap_val),
                "see": decoded_see if decoded_see else None,
                "seealso": decoded_seealso if decoded_seealso else None,
                "has_references": bool(raw_has_ref or decoded_see or decoded_seealso)
            }
            ref_lookup_map.setdefault(h_id, []).append(ref_record)

        # Reconstruct the clean path segments array list explicitly splitting on the exclamation delimiter standard
        staged_hydration_queue = []
        for h in headings:
            full_path_str = h['name'] or ""
            if not full_path_str:
                continue
            
            parts_list = [p.strip() for p in full_path_str.split("!") if p.strip()]
            if parts_list:
                staged_hydration_queue.append((h['id'], parts_list))
                
        # Sort processing elements by path length (parents always go FIRST)
        staged_hydration_queue.sort(key=lambda x: len(x[1]))

        model.blockSignals(True)
        try:
            for heading_id, parts_list in staged_hydration_queue:
                attached_references = ref_lookup_map.get(heading_id, [])
                
                # Route the creation request straight through your controller's verified, strict 2-column recursive builder.
                controller._insert_or_merge_hierarchical_node(
                    model.invisibleRootItem(), 
                    parts_list, 
                    attached_references
                )
        finally:
            model.blockSignals(False)

        view.setSortingEnabled(True)
        model.sort(0, Qt.SortOrder.AscendingOrder)
        view.expandAll()

    @classmethod
    def read_metadata(cls, db_path: str) -> tuple[str, dict]:
        """Queries the database footprint cleanly to isolate and unpack settings configurations."""
        extracted_name = ""
        extracted_settings = {}
        
        if not db_path or not os.path.exists(db_path):
            return extracted_name, extracted_settings
        
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM project_metadata")
            rows = cursor.fetchall()
            
            for key_str, value_str in rows:
                if not key_str:
                    continue
                    
                if key_str == "project_name":
                    extracted_name = str(value_str)
                elif key_str.startswith("cfg_"):
                    actual_key = key_str[4:]
                    raw_val = value_str.strip()
                    
                    if raw_val.lower() == "true":
                        extracted_settings[actual_key] = True
                    elif raw_val.lower() == "false":
                        extracted_settings[actual_key] = False
                    elif raw_val.isdigit():
                        extracted_settings[actual_key] = int(raw_val)
                    else:
                        try:
                            extracted_settings[actual_key] = float(raw_val)
                        except ValueError:
                            extracted_settings[actual_key] = raw_val
                            
        except sqlite3.OperationalError:
            pass 
        finally:
            conn.close()
            
        return extracted_name, extracted_settings
