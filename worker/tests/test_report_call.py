from __future__ import annotations

from sam_worker.report_call import is_report_call, report_opening, report_overlay
from sam_worker.review_call import is_review_call, resolve_outbound_spoken
from sam_worker.sentinel_call import is_sentinel_call

BRIEF = ("report: Swing exit: +11 good days.\nAfter +1R, move the stop to the buy price\n"
         "Today's rule 41; With the change 52\nWorst week no worse.\n"
         "To use it the owner texts YES 4821; you cannot approve it on the call.")


def test_a_report_leg_is_recognised_and_not_mistaken_for_review_or_sentinel():
    meta = {"brief": BRIEF, "spoken": "report"}
    assert is_report_call(meta) and is_report_call({"brief": BRIEF}) and is_report_call({"spoken": "Report"})
    assert not is_review_call(meta) and not is_sentinel_call(meta)
    assert not is_report_call({"brief": "review: digest", "spoken": "review"}) and not is_report_call(None)


def test_sam_opens_with_the_headline_and_carries_the_report():
    meta = {"brief": BRIEF, "spoken": "report"}
    assert resolve_outbound_spoken(meta) == report_opening(meta) == (
        "Hi, it's Sam about your report. Swing exit: +11 good days. What would you like to know?")
    overlay = report_overlay(meta)
    assert "You cannot approve, change, or place anything on this call." in overlay
    assert overlay.endswith(BRIEF.removeprefix("report: "))
    assert report_opening({"spoken": "report"}).startswith("Hi, it's Sam. I don't have the report")
