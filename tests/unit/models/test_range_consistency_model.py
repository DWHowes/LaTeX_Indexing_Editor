"""find_range_consistency_issues -- pure function, no PySide6 dependency."""
from models.range_consistency_model import find_range_consistency_issues


def _entry(uid, pos, encap="standard", file_path="a.tex", heading_id=1):
    return {
        "unique_id_number": uid,
        "absolute_position": pos,
        "encap": encap,
        "file_path": file_path,
        "heading_id": heading_id,
    }


def test_empty_input_returns_no_issues():
    assert find_range_consistency_issues([]) == []


def test_well_formed_range_produces_no_issues():
    records = [
        _entry(1, 10, "("),
        _entry(2, 20, ")"),
    ]
    assert find_range_consistency_issues(records) == []


def test_orphaned_opener():
    records = [_entry(1, 10, "(")]
    issues = find_range_consistency_issues(records)

    assert len(issues) == 1
    assert issues[0]["kind"] == "orphaned_opener"
    assert issues[0]["entries"] == [1]


def test_orphaned_closer():
    records = [_entry(1, 10, ")")]
    issues = find_range_consistency_issues(records)

    assert len(issues) == 1
    assert issues[0]["kind"] == "orphaned_closer"
    assert issues[0]["entries"] == [1]


def test_fifo_pairing_not_lifo():
    """
    Two ranges opened before either closes: the FIFO rule pairs the first
    opener with the first closer encountered, and the second opener with
    the second closer -- not last-opened-first-closed.
    """
    records = [
        _entry(1, 10, "("),   # first opener
        _entry(2, 20, "("),   # second opener
        _entry(3, 30, ")"),   # closes the OLDEST open range (entry 1)
        _entry(4, 40, ")"),   # closes entry 2
    ]
    issues = find_range_consistency_issues(records)

    # Overlapping, since range 2 opened before range 1 closed.
    assert len(issues) == 1
    assert issues[0]["kind"] == "overlapping_ranges"
    assert issues[0]["entries"] == [1, 3, 2, 4]


def test_overlapping_ranges_not_flagged_when_sequential():
    records = [
        _entry(1, 10, "("),
        _entry(2, 20, ")"),
        _entry(3, 30, "("),
        _entry(4, 40, ")"),
    ]
    assert find_range_consistency_issues(records) == []


def test_enclosed_standard_point_is_flagged():
    records = [
        _entry(1, 10, "("),
        _entry(2, 20, "standard"),
        _entry(3, 30, ")"),
    ]
    issues = find_range_consistency_issues(records)

    assert len(issues) == 1
    assert issues[0]["kind"] == "enclosed_point"
    assert issues[0]["entries"] == [1, 3, 2]


def test_styled_point_inside_range_is_not_flagged():
    """
    A bold/italic point inside a range is a deliberate "key page" marker,
    not a missed-range artifact -- only an unstyled ("standard") point
    matches.
    """
    records = [
        _entry(1, 10, "("),
        _entry(2, 20, "textbf"),
        _entry(3, 30, ")"),
    ]
    assert find_range_consistency_issues(records) == []


def test_cross_references_are_excluded_entirely():
    records = [
        _entry(1, 10, "see{Other}"),
        _entry(2, 20, "seealso{Other}"),
    ]
    assert find_range_consistency_issues(records) == []


def test_entries_missing_file_path_or_heading_id_are_skipped():
    records = [
        {"unique_id_number": 1, "absolute_position": 10, "encap": "(", "file_path": None, "heading_id": 1},
        {"unique_id_number": 2, "absolute_position": 20, "encap": "(", "file_path": "a.tex", "heading_id": None},
    ]
    assert find_range_consistency_issues(records) == []


def test_different_files_are_not_cross_compared():
    """
    Same heading_id, different file_path -- must be scoped separately, so
    an opener in one file and a closer in another are each orphaned, not
    paired with each other.
    """
    records = [
        _entry(1, 10, "(", file_path="a.tex"),
        _entry(2, 10, ")", file_path="b.tex"),
    ]
    issues = find_range_consistency_issues(records)

    kinds = sorted(issue["kind"] for issue in issues)
    assert kinds == ["orphaned_closer", "orphaned_opener"]


def test_different_headings_in_same_file_are_not_cross_compared():
    records = [
        _entry(1, 10, "(", heading_id=1),
        _entry(2, 20, ")", heading_id=2),
    ]
    issues = find_range_consistency_issues(records)

    kinds = sorted(issue["kind"] for issue in issues)
    assert kinds == ["orphaned_closer", "orphaned_opener"]
