"""(3.11) Cut points → addressable spans. The arithmetic, without ffmpeg.

Detection is ffmpeg's and already exists (`scenes=<threshold>`, §6.2). This is the part where
an off-by-one silently re-points every `time_range=` on a record, so it is pure and tested
directly.
"""

from __future__ import annotations

from corpus import cutting

# ---- points to spans ---------------------------------------------------------------- #

def test_n_cuts_yield_n_plus_one_spans():
    assert cutting.spans_from_cuts([10.0, 20.0], 30.0) == [
        (0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]


def test_no_cuts_yield_one_whole_span():
    """The honest representation of "found no boundaries" — and the signal the authoring pass
    needs in order to reach for a different strategy rather than accept the result."""
    assert cutting.spans_from_cuts([], 30.0) == [(0.0, 30.0)]


def test_the_last_span_closes_at_duration():
    spans = cutting.spans_from_cuts([5.0], 12.5)
    assert spans[-1][1] == 12.5


def test_cuts_are_sorted_and_deduplicated():
    assert cutting.spans_from_cuts([20.0, 10.0, 10.0], 30.0) == [
        (0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]


def test_out_of_range_cuts_are_dropped_not_raised():
    """A boundary list is an observation. One that disagrees with the duration is the
    detector's problem to survive, not a reason to fail a record."""
    assert cutting.spans_from_cuts([-3.0, 0.0, 10.0, 30.0, 99.0], 30.0) == [
        (0.0, 10.0), (10.0, 30.0)]


def test_zero_duration_yields_nothing():
    assert cutting.spans_from_cuts([1.0], 0.0) == []


# ---- the over-segmentation floor ---------------------------------------------------- #

def test_a_cluster_keeps_its_FIRST_boundary():
    """The correctness question in this module. A detector firing at 10.0/10.1/10.2 found ONE
    transition across three adjacent frames, and the true boundary is the earliest of them.

    Merging the short spans into their predecessor instead — the first thing I wrote — moves
    the boundary to 10.2 and mis-addresses the region by the cluster's width. De-clustering
    the POINTS keeps it at 10.0."""
    spans = cutting.spans_from_cuts([10.0, 10.1, 10.2, 20.0], 30.0, min_seconds=1.0)
    assert spans == [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0)]


def test_a_cut_too_close_to_the_start_is_dropped():
    """Separation is measured from the origin, not just from the previous cut, so a detection
    in the opening moments does not produce an unusable leading fragment."""
    spans = cutting.spans_from_cuts([0.2, 10.0], 30.0, min_seconds=1.0)
    assert spans == [(0.0, 10.0), (10.0, 30.0)]


def test_a_short_tail_folds_back():
    """The final span's end IS the duration and cannot move, so it is the one case a merge
    still has to handle."""
    spans = cutting.spans_from_cuts([10.0, 29.8], 30.0, min_seconds=1.0)
    assert spans == [(0.0, 10.0), (10.0, 30.0)]


def test_the_floor_never_empties_the_list():
    spans = cutting.spans_from_cuts([0.1, 0.2], 0.5, min_seconds=10.0)
    assert len(spans) == 1 and spans[0][0] == 0.0


# ---- fixed interval ----------------------------------------------------------------- #

def test_fixed_interval_grids_the_timeline():
    assert cutting.fixed_interval_spans(10.0, 3.0) == [
        (0.0, 3.0), (3.0, 6.0), (6.0, 9.0), (9.0, 10.0)]


def test_fixed_interval_shorter_than_one_step_is_one_span():
    assert cutting.fixed_interval_spans(2.0, 5.0) == [(0.0, 2.0)]


def test_fixed_interval_rejects_nonsense():
    assert cutting.fixed_interval_spans(10.0, 0.0) == []
    assert cutting.fixed_interval_spans(0.0, 5.0) == []


# ---- the address ------------------------------------------------------------------- #

def test_address_is_the_existing_time_range_grammar():
    assert cutting.address_for((0.0, 14.0)) == "time_range=0-14"
    assert cutting.address_for((14.25, 30.5)) == "time_range=14.25-30.5"


def test_address_drops_trailing_zeros_for_stable_spelling():
    """Stored addresses are compared as strings by lint and by the ledger's anchors, so one
    span must always spell the same way."""
    assert cutting.address_for((12.000, 20.100)) == "time_range=12-20.1"


# ---- the stamp --------------------------------------------------------------------- #

def test_stamp_merges_the_declaration_unrenamed():
    declared = {"id": "scene-threshold@0.1.0", "threshold": 0.3}
    s = cutting.stamp(declared, [(0.0, 5.0), (5.0, 10.0)], 10.0)
    assert s == {"id": "scene-threshold@0.1.0", "threshold": 0.3,
                 "cuts": 2, "duration": 10.0}
    assert declared == {"id": "scene-threshold@0.1.0", "threshold": 0.3}  # not mutated


def test_stamp_tolerates_an_unknown_duration():
    """`_probe_video` is best-effort — a record drafted where ffprobe failed has no duration,
    and the stamp must still be writable rather than blocking the cut."""
    s = cutting.stamp({"id": "keyframe@0.1.0"}, [(0.0, 1.0)], None)
    assert "duration" not in s and s["cuts"] == 1


def test_strategy_family_splits_off_the_version():
    assert cutting.strategy_family("scene-threshold@0.1.0") == "scene-threshold"
    assert cutting.strategy_family("fixed-interval@2.5.1") == "fixed-interval"
    assert cutting.strategy_family("") == ""
