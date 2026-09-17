r"""
This application's row payloads, stored and read through the core's repository.

Since core schema 2.4.0 the project database stores the shared record, and the
repository takes and returns records. This application's scanner, loader and
tools still speak rows (``unique_id_number``, ``file_path``, ``encap`` and the
rest), and ``models.latex_record_mapping`` is the one place the two meet. These
helpers let the persistence tests say what they mean, *a LaTeX row goes in and
the same row comes back*, without restating the mapping in every test.

What the repository itself does with a record is the core's to test, and it is
tested there (``bookindexcore/tests/persistence``).
"""

from models.latex_record_mapping import payload_from_reference, reference_from_row


def base_row(unique_id=1, **overrides):
    """A complete scanner-shaped row for one ``\index`` macro."""
    row = {
        "unique_id_number": unique_id,
        "heading_raw_text": "Main",
        "uid": f"a.tex:1:{unique_id}",
        "file_path": "a.tex",
        "line_number": 1,
        "column_offset": 0,
        "absolute_position": 10,
        "absolute_end": 20,
        "encap": "standard",
        "see_references": None,
        "seealso_references": None,
        "macro_command": "index",
    }
    row.update(overrides)
    return row


def store(persistence, row) -> bool:
    """Inserts one row, as this application's pipeline would."""
    return persistence.insert_reference(reference_from_row(row))


def rewrite(persistence, row) -> bool:
    """Rewrites one stored reference from a row."""
    return persistence.update_reference(reference_from_row(row))


def fetch(persistence, entry_id):
    """One stored reference as a row, or None."""
    record = persistence.fetch_reference(entry_id)
    return payload_from_reference(record) if record is not None else None


def serialize(persistence, headings, rows) -> None:
    """A fresh scan written wholesale."""
    persistence.serialize_scraped_index_manifest(headings, [reference_from_row(r) for r in rows])


def manifest(persistence):
    """Every heading row, and every reference as a row."""
    headings, records = persistence.fetch_index_manifest()
    return headings, [payload_from_reference(r) for r in records]
