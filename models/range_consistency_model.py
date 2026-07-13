from collections import defaultdict


def _position_key(entry: dict):
    """
    Sort key for document order within a single file. absolute_position is
    the authoritative coordinate everywhere else in this codebase; falls
    back to (line_number, column_offset) only for the pathological case of
    a record missing it (shouldn't happen for a fully loaded project, but
    entries with absolute_position always sort before ones without it
    rather than raising on a None comparison).
    """
    pos = entry.get("absolute_position")
    if pos is not None:
        return (0, pos)
    return (1, entry.get("line_number") or 0, entry.get("column_offset") or 0)


def _entry_id(entry: dict) -> int:
    return int(entry.get("unique_id_number") or entry.get("id") or 0)


def _is_cross_reference(entry: dict) -> bool:
    encap = str(entry.get("encap") or "")
    return encap.startswith("see{") or encap.startswith("seealso{")


def find_range_consistency_issues(records: list) -> list:
    r"""
    Scans a project's live \index reference records for range-pairing
    inconsistencies caused by an external auto-indexer's multi-pass scans
    missing an already-open range for a term. Re-derives opener/closer
    pairing from scratch by document position rather than trusting the
    existing is_range_closer/range_partner_id fields, since those are
    exactly what's being audited here.

    Comparisons are scoped to (file_path, heading_id) groups -- two
    same-named terms in different files are never compared, and
    cross-reference entries (encap "see{...}"/"seealso{...}") are excluded
    entirely since they carry no page number.

    Returns a list of issue dicts:
        {
            "kind": "orphaned_opener" | "orphaned_closer" |
                     "overlapping_ranges" | "enclosed_point",
            "file_path": str,
            "heading_id": int,
            "entries": [unique_id_number, ...],   # meaning documented below
        }

    "entries" ordering per kind:
      orphaned_opener / orphaned_closer : [entry_id]
      overlapping_ranges : [first_open_id, first_close_id, second_open_id, second_close_id]
      enclosed_point       : [range_open_id, range_close_id, point_id]

    No separate "enclosed range" kind: \index{term|(} / |)} markers are
    anonymous, so when two ranges for the same heading are open at once,
    nothing in the source records which opener a given closer belongs to
    -- "range 2 nested inside range 1" and "range 2 overlaps past range
    1's end" are two different *interpretations* of the exact same raw
    marker sequence, not two distinguishable patterns. FIFO pairing below
    (closer always ends the OLDEST still-open range) resolves every such
    case as "overlapping" -- consistently, and safely, since the merge fix
    for it only ever consolidates ranges, never deletes discussed text.
    """
    groups: dict = defaultdict(list)
    for entry in records:
        if _is_cross_reference(entry):
            continue
        file_path = entry.get("file_path")
        heading_id = entry.get("heading_id")
        if not file_path or heading_id is None:
            continue
        groups[(file_path, heading_id)].append(entry)

    issues: list = []

    for (file_path, heading_id), group_entries in groups.items():
        group_entries.sort(key=_position_key)

        openers = []
        closers = []
        points = []
        for entry in group_entries:
            encap = entry.get("encap")
            if encap == "(":
                openers.append(entry)
            elif encap == ")":
                closers.append(entry)
            else:
                points.append(entry)

        # Merge openers/closers back into one position-ordered stream so
        # pairing follows real document order regardless of how the two
        # lists happened to interleave.
        open_close_stream = sorted(openers + closers, key=_position_key)

        # FIFO (queue), not LIFO -- matches project_load_worker.py's own
        # range pairing (see its docstring): a makeindex/imakeidx range for
        # a single key never nests, so the next ")" closes the OLDEST
        # still-open range for this heading, not the most recently opened
        # one. This is also what lets "first reference" / "second
        # reference" below mean what a human would expect them to mean in
        # document order, matching how overlapping/enclosed ranges were
        # described when this checker was scoped.
        valid_ranges = []  # list of (open_entry, close_entry)
        open_queue = []
        for entry in open_close_stream:
            if entry.get("encap") == "(":
                open_queue.append(entry)
            else:  # ")"
                if open_queue:
                    opener = open_queue.pop(0)
                    valid_ranges.append((opener, entry))
                else:
                    issues.append({
                        "kind": "orphaned_closer",
                        "file_path": file_path,
                        "heading_id": heading_id,
                        "entries": [_entry_id(entry)],
                    })
        for opener in open_queue:
            issues.append({
                "kind": "orphaned_opener",
                "file_path": file_path,
                "heading_id": heading_id,
                "entries": [_entry_id(opener)],
            })

        valid_ranges.sort(key=lambda pair: _position_key(pair[0]))

        # FIFO pairing guarantees open_i < open_j implies close_i < close_j
        # for every pair of valid_ranges (it assigns the k-th open to the
        # k-th close in document order, by construction) -- so a later
        # range's closer can never land before an earlier range's own
        # closer here. Only "does the next range start before this one
        # ends" is left to check.
        for i in range(len(valid_ranges)):
            open_i, close_i = valid_ranges[i]
            for j in range(i + 1, len(valid_ranges)):
                open_j, close_j = valid_ranges[j]
                if _position_key(open_j) >= _position_key(close_i):
                    continue  # Rj starts at or after Ri ends -- unrelated
                issues.append({
                    "kind": "overlapping_ranges",
                    "file_path": file_path,
                    "heading_id": heading_id,
                    "entries": [
                        _entry_id(open_i), _entry_id(close_i),
                        _entry_id(open_j), _entry_id(close_j),
                    ],
                })

        for point in points:
            # Only an unstyled point matches an unstyled range's "plain
            # page" semantic. A styled point (textbf, textit, etc.)
            # landing inside a range is a common deliberate indexing
            # convention -- marking one page as the key/defining
            # discussion while the range covers general coverage nearby --
            # not a missed-range artifact, so it's skipped rather than
            # flagged.
            if point.get("encap") != "standard":
                continue
            point_key = _position_key(point)
            for open_entry, close_entry in valid_ranges:
                if _position_key(open_entry) < point_key < _position_key(close_entry):
                    issues.append({
                        "kind": "enclosed_point",
                        "file_path": file_path,
                        "heading_id": heading_id,
                        "entries": [
                            _entry_id(open_entry), _entry_id(close_entry),
                            _entry_id(point),
                        ],
                    })
                    break

    return issues
