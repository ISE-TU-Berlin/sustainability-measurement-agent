"""onRunStart failures must abort the run: a swallowed skaffold/smoke failure burns a 9 min trial measuring nothing."""
import logging

from sma.sma import SustainabilityMeasurementAgent


class Boom:
    def onRunStart(self): raise RuntimeError("skaffold run failed")
    def onReport(self, report=None): raise RuntimeError("cosmetic")


def test_on_run_start_propagates():
    sma = SustainabilityMeasurementAgent.__new__(SustainabilityMeasurementAgent)
    sma.observers = [Boom()]
    sma.logger = logging.getLogger("t")
    try:
        sma.notify_observers("onRunStart"); assert False, "onRunStart error must propagate"
    except RuntimeError as e:
        assert "skaffold" in str(e)
    sma.notify_observers("onReport")   # non-fatal events still only log


if __name__ == "__main__":
    test_on_run_start_propagates()
    print("ok")
