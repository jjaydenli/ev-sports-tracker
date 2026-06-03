from core.pipeline_timing import PipelineTimer, format_elapsed


def test_format_elapsed_milliseconds():
    assert format_elapsed(0.452) == "452ms"


def test_format_elapsed_seconds():
    assert format_elapsed(2.5) == "2.50s"


def test_pipeline_timer_records_stages():
    timer = PipelineTimer()
    timer.record("scrape dk", 1.2)
    timer.record("normalize", 0.05)
    assert len(timer._records) == 2
    assert timer._records[0] == ("scrape dk", 1.2)


def test_pipeline_timer_disabled_is_no_op():
    timer = PipelineTimer.disabled()
    timer.record("scrape dk", 1.0)
    with timer.stage("normalize"):
        pass
    assert timer._records == []
