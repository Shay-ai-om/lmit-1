from datetime import datetime, timezone

from lmit.gui import compute_initial_window_size, format_gui_log_line


def test_format_gui_log_line_adds_timestamp_to_plain_pipeline_line():
    timestamp = datetime(2026, 5, 3, 18, 45, 7, tzinfo=timezone.utc)

    assert (
        format_gui_log_line("[ITEM-START] example.pptx", now=timestamp)
        == "[2026-05-03 18:45:07 UTC] [ITEM-START] example.pptx"
    )


def test_format_gui_log_line_keeps_existing_timestamped_line():
    line = "[2026-05-03 17:30:26] ERROR: Failed after 3 attempts"

    assert format_gui_log_line(line) == line


def test_compute_initial_window_size_prefers_taller_default_when_content_is_short():
    assert compute_initial_window_size(
        requested_width=980,
        requested_height=840,
        screen_width=1920,
        screen_height=1080,
    ) == (1040, 1000, 900, 760)


def test_compute_initial_window_size_respects_screen_ceiling():
    assert compute_initial_window_size(
        requested_width=1200,
        requested_height=980,
        screen_width=1280,
        screen_height=900,
    ) == (1200, 820, 900, 760)
