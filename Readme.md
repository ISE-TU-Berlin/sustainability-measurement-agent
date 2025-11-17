# Sustainability Measurements Agent (SMA)

[![PyPI - Version](https://img.shields.io/pypi/v/sustainability-measurement-agent)](https://pypi.org/project/sustainability-measurement-agent/) | [![Upload Python Package](https://github.com/ISE-TU-Berlin/sustainability-measurement-agent/actions/workflows/python-publish.yml/badge.svg)](https://github.com/ISE-TU-Berlin/sustainability-measurement-agent/actions/workflows/python-publish.yml)

SMA is an open-source tool designed to help deploy, collect and report sustainability measurements on cloud-native applications. It is not itself a measurement tool, but rather a framework to orchestrate, combine and aggregate results from emerging suite of sustainability measurement tools. 


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

### Configuration
SMA is configured via YAML files. See the `examples/` folder for sample configurations. The configuration allows to specify which measurement tools to use, how to deploy them, and how to collect and report the measurements.

<!-- TODO: Add more detailed configuration documentation -->

### API 

<!-- TODO: Add API documentation -->

## Development

1. Install pipenv: `pip install pipenv`
2. Install dependencies: `pipenv install --dev`
3. Activate virtual environment: `pipenv shell`
4. Do your thing. Eventually with tests.
5. If you add new dependencies, run `pipenv lock --pre` to update the `Pipfile.lock`.
6. If you want to release a new version, update the version in `pyproject.toml` and run `pipenv run pyproject-pipenv --fix` and commit the changes.
7. Tag your release: `git tag vx.y.z` and `git push --tags`
8. Create a new release on GitHub, this will trigger the upload to PyPI via GitHub Actions.

### Acknowledgements

This project builds upon prior work done in the [OXN project](https://github.com/nymphbox/oxn), [GOXN project](https://github.com/JulianLegler/goxn) and [CLUE](https://github.com/ISE-TU-Berlin/Clue) and is part of the research at [ISE-TU Berlin](https.//www.tu.berlin/ise).