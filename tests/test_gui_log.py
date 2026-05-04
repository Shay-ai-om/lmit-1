from datetime import datetime, timezone

from lmit.gui import format_gui_log_line


def test_format_gui_log_line_adds_timestamp_to_plain_pipeline_line():
    timestamp = datetime(2026, 5, 3, 18, 45, 7, tzinfo=timezone.utc)

    assert (
        format_gui_log_line("[ITEM-START] example.pptx", now=timestamp)
        == "[2026-05-03 18:45:07 UTC] [ITEM-START] example.pptx"
    )


def test_format_gui_log_line_keeps_existing_timestamped_line():
    line = "[2026-05-03 17:30:26] ERROR: Failed after 3 attempts"

    assert format_gui_log_line(line) == line
