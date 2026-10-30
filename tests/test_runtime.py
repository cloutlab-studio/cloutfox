from src.ui.runtime import LOG_LIMIT, Runtime


def test_marks_follow_the_running_set():
    rt = Runtime()
    rt.failed.update({"a", "b", "gone"})
    rt.track({"a", "b", "c"}, running={"a", "c"})
    # A failure mark lasts until the profile runs again or is gone.
    assert rt.failed == {"b"}
    assert rt.since("a") and rt.since("c") and not rt.since("b")
    rt.track({"a", "b", "c"}, running=set())
    assert not rt.since("a")


def test_log_keeps_the_latest_lines_with_ids():
    rt = Runtime()
    for i in range(LOG_LIMIT + 5):
        rt.add_log(f"line {i}")
    lines = rt.log_lines()
    assert len(lines) == LOG_LIMIT
    assert lines[-1]["text"] == f"line {LOG_LIMIT + 4}"
    assert lines[-1]["id"] == LOG_LIMIT + 5
