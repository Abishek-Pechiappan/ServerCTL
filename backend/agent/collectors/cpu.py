import psutil

# psutil.cpu_percent(interval=None) reports usage since the *previous* call, so
# the first call in a process has nothing to compare against and returns a
# meaningless 0.0.
_first_call = True

# Only used for that first call. Long enough to be a real sample, short enough
# not to matter — it happens once per process, at startup.
_FIRST_SAMPLE_SECONDS = 0.25


def cpu():
    """System-wide CPU utilisation since the previous call.

    Deliberately not interval=1. Passing an interval makes psutil *sleep* for that
    long to sample a delta, which blocked the snapshot loop for a full second on
    every cycle — so the advertised 5-second refresh was really 6+ seconds, one of
    them spent doing nothing.

    Without an interval psutil diffs against the times it recorded on the previous
    call, which the loop makes every REFRESH_SECONDS. That is a wider and
    therefore more representative sample than a 1-second spot check, at no cost.
    """
    global _first_call
    if _first_call:
        _first_call = False
        return psutil.cpu_percent(interval=_FIRST_SAMPLE_SECONDS)
    return psutil.cpu_percent(interval=None)
