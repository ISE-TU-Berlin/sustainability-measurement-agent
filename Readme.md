# Sustainability Measurements Agent (SMA)

![PyPI - Version](https://img.shields.io/pypi/v/sustainability-measurement-agent) | [![Upload Python Package](https://github.com/ISE-TU-Berlin/sustainability-measurement-agent/actions/workflows/python-publish.yml/badge.svg)](https://github.com/ISE-TU-Berlin/sustainability-measurement-agent/actions/workflows/python-publish.yml)

SMA is an open-source tool designed to help deploy, collect and report sustainability measurements on cloud-native applications. It is not itself a measurement tool, but rather a framework to orchestrate, combine and aggregate results from emerging suite of sustainability measurement tools. 

## Use / Install

```bash
pip install sustainability-measurement-agent

touch main.py
```

```python
import sys
from sma import SustainabilityMeasurementAgent, Config, SMAObserver

config = Config.from_file("examples/minimal.yaml")
sma = SustainabilityMeasurementAgent(config)
sma.connect()
def wait_for_user() -> None:
    input("Hit Enter to to Stop Measuring...")

sma.run(wait_for_user)
sma.teardown()
report_location = config.report.get("location")
if report_location:
    print(f"Report written to {report_location}")
```

```bash
$ python main.py
$ Hit Enter to to Stop Measuring...
``` 

## Capabilities (planned)
 - Configuration driven deployment and operation
 - Support for multiple measurement tools
   - Kepler
   - Scraphandre
   - cAdvisor
   - KubeWatt
   - Cloud Provider APIs (AWS, GCP, Azure)
   - KubeMetrics
 - Support for multiple scenarios
   - Continuous monitoring and reporting
   - Experiment Measurements / Benchmarking
   - Ad-hoc measurements
   - Programmatic measurements via API
   - Kubernetes Operator
 - Multiple report formats
   - CSV
   - HDF5
 - Post processing and aggregation
   - Pandas
   - Grafana Dashboards

## Contributing

### Acknowledgements

This project builds upon prior work done in the [OXN project](https://github.com/nymphbox/oxn), [GOXN project](https://github.com/JulianLegler/goxn) and [CLUE](https://github.com/ISE-TU-Berlin/Clue) and is part of the research at [ISE-TU Berlin](https.//www.tu.berlin/ise).