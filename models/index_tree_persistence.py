import os
import sqlite3
import json  
import re
from PySide6.QtCore import Qt

class IndexTreePersistence:
    """
    Handles atomic serialization, transactional safety, and non-destructive relational 
    database reconstruction for the multi-column LaTeX Indexing Editor Tree.
    """
    @classmethod
    def save_to_db(cls, model, db_path: str, project_name: str = "", settings_dict: dict = None):
        """
        Orchestration Engine (LOCKED).
        Flattens hierarchical multi-column headings and reference tokens into an SQLite table safely.
        Delegates transactional tasks and table extraction cleanly to specialized helper methods.
        """
        if model is None or not db_path:
            return

        settings_dict = settings_dict or {}
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            
            # 1. Clear out stale structural profiles and initialize active metadata schemas
            cls._initialize_database_schemas(cursor, project_name, settings_dict)
            
            # 2. Fire deep recursive traversal to extract and commit tree node cells
            root_item = model.invisibleRootItem() if hasattr(model, "invisibleRootItem") else model
            cls._serialize_tree_node_recursive(cursor, model, root_item)
            
            conn.commit()
        except Exception as transaction_fault:
            try:
                conn.rollback()
            except Exception:
                pass
            raise transaction_fault
        finally:
            conn.close()

    @classmethod
    def load_from_db(cls, model, view, db_path: str):
        """
        Orchestration Engine (LOCKED).
        Reconstructs multi-column alignment structures using relational database paths.
        Delegates deserialization mappings and layout unrolling safely to specialized helper methods.
        """
        if not os.path.exists(db_path):
            return

        main_win = view.window()
        controller = getattr(main_win, "index_controller", None)
        if not controller:
            return

        # Initialize raw structural conditions on the tree canvas view
        view.setSortingEnabled(False)
        model.clear()
        model.setHorizontalHeaderLabels(["Index Terms", "References"])

        # 1. Safely extract raw list matrices out of the underlying database file surface
        headings, references = cls._fetch_raw_database_records(db_path)
        if not headings:
            view.setSortingEnabled(True)
            return

        # 2. Build explicit map indices translating relational reference pointers to their headings
        ref_lookup_map = cls._build_reference_lookup_index(references)

        # 3. Cleanly parse, split, and stage structural heading tracks based on sorting depths
        staged_hydration_queue = cls._prepare_staged_hydration_queue(headings)

        # 4. Stream segments through the controller's locked 2-column layout compilation channels
        model.blockSignals(True)
        try:
            cls._hydrate_model_from_queue(controller, model, staged_hydration_queue, ref_lookup_map)
        finally:
            model.blockSignals(False)

        # Re-enforce and finalize structural sorting conditions natively
        view.setSortingEnabled(True)
        model.sort(0, Qt.SortOrder.AscendingOrder)
        view.expandAll()

    @classmethod
    def _initialize_database_schemas(cls, cursor, project_name: str, settings_dict: dict):
        """
        Save Helper 1: Database Initialization.
        Materializes clean metadata tables and transaction-safe schema structures.
        """
        cursor.execute("DROP TABLE IF EXISTS project_metadata")
        cursor.execute("CREATE TABLE project_metadata (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("INSERT INTO project_metadata (key, value) VALUES (?, ?)", ("project_name", str(project_name)))
        
        for k, v in settings_dict.items():
            cursor.execute("INSERT INTO project_metadata (key, value) VALUES (?, ?)", (f"cfg_{k}", str(v)))

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

    @classmethod
    def _serialize_tree_node_recursive(cls, cursor, model, parent_qt_item, parent_db_id=None, current_depth=0, path_segments=None):
        """
        Save Helper 2: Recursive Flattening.
        Walks item arrays sequentially to parse parent-child relationship tokens.
        """
        path_segments = path_segments or []
        if not hasattr(parent_qt_item, "rowCount"):
            return

        ROLE_UID_DATA = Qt.ItemDataRole.UserRole + 1

        for i in range(parent_qt_item.rowCount()):
            heading_item = parent_qt_item.child(i, 0)
            if not heading_item:
                continue
                
            current_node_text = heading_item.text().strip()
            if not current_node_text:
                continue
            
            node_full_path_list = path_segments + [current_node_text]
            full_heading_path_str = "!".join(node_full_path_list)
            
            cursor.execute("""
                INSERT INTO index_headings (parent_id, name, depth) VALUES (?, ?, ?)
            """, (parent_db_id, full_heading_path_str, current_depth))
            
            heading_db_id = cursor.lastrowid
            
            row_parent = heading_item.parent() or model.invisibleRootItem()
            reference_cell = row_parent.child(heading_item.row(), 1)
            
            if reference_cell:
                records_list = reference_cell.data(ROLE_UID_DATA)
                if records_list and isinstance(records_list, list):
                    cls._serialize_reference_records(cursor, heading_db_id, records_list)
                    
            if heading_item.rowCount() > 0:
                cls._serialize_tree_node_recursive(cursor, model, heading_item, heading_db_id, current_depth + 1, node_full_path_list)

    @classmethod
    def _serialize_reference_records(cls, cursor, heading_db_id, records_list: list):
        """
        Save Helper 3: Record Extraction.
        Isolates and validates cross-reference strings out of raw reference cells.
        """
        for rec in records_list:
            if not rec or not isinstance(rec, dict):
                continue
                
            uid_num = rec.get("unique_id_number") or rec.get("id") or 0
            f_path = rec.get("file_path") or ""
            line_coord = rec.get("line_number") or 1
            col_coord = rec.get("column_offset") or 0
            abs_pos = rec.get("absolute_position") 
            encap_val = str(rec.get("encap") or "standard").strip()

            see_array = list(rec.get("see") or []) if isinstance(rec.get("see"), (list, tuple)) else ([rec.get("see")] if rec.get("see") else [])
            seealso_array = list(rec.get("seealso") or []) if isinstance(rec.get("seealso"), (list, tuple)) else ([rec.get("seealso")] if rec.get("seealso") else [])

            lower_encap = encap_val.lower()
            if "seealso{" in lower_encap:
                m = re.search(r'seealso\{([^}]+)\}', encap_val, re.IGNORECASE)
                if m and m.group(1).strip() not in seealso_array:
                    seealso_array.append(m.group(1).strip())
                encap_val = "standard"
            elif "see{" in lower_encap:
                m = re.search(r'see\{([^}]+)\}', encap_val, re.IGNORECASE)
                if m and m.group(1).strip() not in see_array:
                    see_array.append(m.group(1).strip())
                encap_val = "standard"

            has_ref_flag = 1 if (bool(f_path) and encap_val != "standard") or bool(see_array or seealso_array) else 0

            cursor.execute("""
                INSERT INTO index_references (
                    heading_id, unique_id_number, file_path, line, col, 
                    absolute_position, encap, see_references, seealso_references, has_references
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (heading_db_id, int(uid_num), str(f_path), int(line_coord), int(col_coord),
                  int(abs_pos) if abs_pos is not None else None, str(encap_val),
                  json.dumps(see_array), json.dumps(seealso_array), has_ref_flag))

    @classmethod
    def _fetch_raw_database_records(cls, db_path: str) -> tuple[list, list]:
        """
        Load Helper 1: Database Ingestion.
        Safely reads records out of active heading and reference matrices.
        """
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            headings = [dict(r) for r in cursor.execute("SELECT * FROM index_headings").fetchall()]
            references = [dict(r) for r in cursor.execute("SELECT * FROM index_references").fetchall()]
            conn.close()
            return headings, references
        except sqlite3.OperationalError:
            return [], []

    @classmethod
    def _build_reference_lookup_index(cls, references: list) -> dict:
        """
        Load Helper 2: Reference Indexing.
        Decodes string primitives and cross-reference scalar values out of storage arrays.
        """
        ref_lookup_map = {}
        for r in references:
            try:
                decoded_see = json.loads(r.get('see_references') or "[]")
                decoded_seealso = json.loads(r.get('seealso_references') or "[]")
            except Exception:
                decoded_see, decoded_seealso = [], []

            scalar_see = str(decoded_see[0]).strip() if decoded_see else None
            scalar_seealso = str(decoded_seealso[0]).strip() if decoded_seealso else None

            ref_lookup_map.setdefault(r['heading_id'], []).append({
                "uid": f"{r['file_path']}:{r['line']}:{r['col']}",
                "unique_id_number": int(r['unique_id_number']),
                "id": int(r['unique_id_number']), 
                "file_path": str(r['file_path']),
                "line_number": int(r['line']),
                "column_offset": int(r['col']),
                "absolute_position": r.get('absolute_position'),
                "encap": str(r.get('encap') or "standard"),
                "see": scalar_see,         
                "seealso": scalar_seealso, 
                "has_references": bool(r.get('has_references', 0) or scalar_see or scalar_seealso)
            })
        return ref_lookup_map

    @classmethod
    def _prepare_staged_hydration_queue(cls, headings: list) -> list:
        """
        Load Helper 3: String Parsing Boundary.
        Splits text path parameters and removes forced sorting (@) tags cleanly.
        """
        staged_hydration_queue = []
        for h in headings:
            full_path_str = h['name'] or ""
            if not full_path_str:
                continue
            
            raw_parts = [p.strip() for p in full_path_str.split("!") if p.strip()]
            processed_parts = []
            
            for part in raw_parts:
                if "@" in part:
                    # SYSTEM INTEGRITY ANCHOR: Isolate right-hand visual display elements completely
                    split_chunks = part.split("@", 1)
                    processed_parts.append(split_chunks[1].strip() if len(split_chunks) > 1 else split_chunks[0].strip())
                else:
                    processed_parts.append(part)

            if processed_parts:
                staged_hydration_queue.append((h['id'], processed_parts))
                
        # Sort processing components so shallow taxonomy layers compile first
        staged_hydration_queue.sort(key=lambda x: len(x[1]))
        return staged_hydration_queue

    @classmethod
    def _hydrate_model_from_queue(cls, controller, model, staged_hydration_queue: list, ref_lookup_map: dict):
        """
        Load Helper 4: Model Hydration.
        Routes text streams and cross-reference tokens straight to controller engines.
        """
        for heading_id, parts_list in staged_hydration_queue:
            attached_references = ref_lookup_map.get(heading_id, [])
            
            # 1. Compile primary structural node tracks
            controller._insert_or_merge_hierarchical_node(
                model.invisibleRootItem(), 
                parts_list, 
                attached_references
            )
            
            # 2. Unroll related cross-reference subheadings recursively 
            for ref_rec in attached_references:
                if ref_rec.get("seealso"):
                    xref_token = f"seealso:{ref_rec['seealso']}"
                    controller._insert_or_merge_hierarchical_node(
                        model.invisibleRootItem(),
                        parts_list + [xref_token],
                        []
                    )
                if ref_rec.get("see"):
                    xref_token = f"see:{ref_rec['see']}"
                    controller._insert_or_merge_hierarchical_node(
                        model.invisibleRootItem(),
                        parts_list + [xref_token],
                        []
                    )

    @classmethod
    def read_metadata(cls, db_path: str) -> tuple[str, dict]:
        extracted_name, extracted_settings = "", {}
        if not db_path or not os.path.exists(db_path):
            return extracted_name, extracted_settings
        
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM project_metadata")
            for k, v in cursor.fetchall():
                if k == "project_name":
                    extracted_name = str(v)
                elif k.startswith("cfg_"):
                    actual_key = k[4:]
                    rv = v.strip()
                    if rv.lower() == "true": extracted_settings[actual_key] = True
                    elif rv.lower() == "false": extracted_settings[actual_key] = False
                    elif rv.isdigit(): extracted_settings[actual_key] = int(rv)
                    else:
                        try: extracted_settings[actual_key] = float(rv)
                        except ValueError: extracted_settings[actual_key] = rv
        except sqlite3.OperationalError:
            pass 
        finally:
            conn.close()
        return extracted_name, extracted_settings
