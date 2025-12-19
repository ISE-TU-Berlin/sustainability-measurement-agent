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
Make sure you have Python 3.8+ as well as hdf5 and jupyter installed. You may need to install additional dependencies depending on your setup, e.g., c-blosc lzo bzip2 gcc.
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

### Architecture and Lifecycle

SMA follows a simple lifecycle:
[![SMA Lifecycle](docs/lifecycle.svg)](docs/lifecycle.svg)

Fully driven by configuration files, SMA connects to external services (e.g., Prometheus), deploys measurement tools (e.g., Kepler), and once instrcuted via the API (`run()`), starts the observation according to the configured mode (trigger, timer, continuous). Finally, SMA collects the measurement data, generates reports, and tears down any deployed infrastructure (if configured to do so).

SMA exposes an observer API (`SMAObserver`), which allows to hook into the lifecycle events (see the diagram) to extend SMA's functionality programmatically, or to integrate into experiment frameworks.

### Configuration

SMA is configured via YAML files. See the `examples/` folder for sample configurations. The configuration allows to specify which measurement tools to use, how to deploy them, and how to collect and report the measurements.

#### Configuration Structure

The configuration file consists of the following main sections:

##### 1. Version
```yaml
sma:
  version: 0.0.1
```
Specifies the SMA configuration schema version.

##### 2. Deployment (Optional)
```yaml
deployment:
  namespace: sma
  install: true
```

Controls automatic deployment of measurement infrastructure.

| Field | Type | Description |
|-------|------|-------------|
| `namespace` | String | Kubernetes namespace where SMA components will be deployed |
| `install` | Boolean | Whether to automatically install/deploy measurement tools |

##### 3. Services
```yaml
services:
  prometheus:
    address: http://130.149.158.132:32426
    # Optional: Deploy Prometheus via Helm
    chart: prometheus-community/prometheus
    version: 14.6.0
    values:
      - service.type: NodePort
        service.nodePort: 30900
```

Defines external services used for data collection, sofar we only support Prometheus.

| Field | Description |
|-------|-------------|
| `prometheus.address` | URL of the Prometheus server for metrics collection |
| `prometheus.chart` | (Optional) Helm chart repository and name for deploying Prometheus |
| `prometheus.version` | (Optional) Helm chart version to deploy |
| `prometheus.values` | (Optional) List of Helm values to override default configuration |

##### 4. Sensors (Optional)
```yaml
sensors:
  kepler:
    chart: kepler/kepler
    version: 0.8.1
    values:
      - global:
          prometheus:
            enabled: true
```

Defines measurement sensors/tools to deploy via Helm charts.

| Field | Description |
|-------|-------------|
| `<sensor_name>.chart` | Helm chart repository and name for the sensor |
| `<sensor_name>.version` | Helm chart version to deploy |
| `<sensor_name>.values` | List of Helm values to override default configuration |

**Supported Sensors:**
- **Kepler**: Kubernetes-based Efficient Power Level Exporter
- **Scaphandre**: Host-level power consumption metrics
- **cAdvisor**: Container resource usage and performance metrics
- **Kube Metrics**: Kubernetes metrics server

##### 5. Observation
```yaml
observation:
  mode: trigger 
  window:
    left: 10s   
    right: 10s 
    duration: 10s
  targets:
    - name: sut
      namespace: kubeai
```

| Field | Options/Type | Description |
|-------|--------------|-------------|
| `mode` | `trigger`, `timer`, `continuous` | **trigger**: Measurement starts/stops based on a Python function that blocks<br>**timer**: Measurement based on time window settings<br>**continuous**: Collects data until stopped, with a blocking Python function |
| `window.left` | Duration (e.g., `10s`) | Time to capture before the measurement trigger |
| `window.right` | Duration (e.g., `10s`) | Time to capture after the measurement trigger |
| `window.duration` | Duration (e.g., `10s`) | Total measurement duration |
| `targets[].name` | String | Name identifier for the target workload |
| `targets[].namespace` | String | Kubernetes namespace of the target workload |

Depoending on the mode, SMA will not use of all of the windowing parameters, e.g., duration is only considered in `timer` mode. Both `left` and `right` windows are optional and mean, SMA will wait before handing off the measurement to the next API call.

##### 6. Measurements
```yaml
measurements:
  # Custom PromQL query
  - measurement_name:
      type: aggregate
      layer: pod         
      query: <PromQL query>
      step: 30           
      unit: watts       
      target:
        - all        
  
  # Prepared query (predefined)
  - pod-consumption:
      type: aggregate
      layer: pod
      prepared_query: pod_kepler_energy_consumption
      step: 30
      unit: watts
      sensors:
        - kepler
      target:
        - sut
```

| Field | Options/Type | Description |
|-------|--------------|-------------|
| `type` | `raw`, `aggregate` | **raw**: Unprocessed metric data<br>**aggregate**: Aggregated/computed metrics |
| `layer` | `substrate`,`pod`, `node`, `process` | The abstraction level being measured |
| `query` | PromQL string | Prometheus query to retrieve the metric. Supports template variables:<br>`${namespace}`: Replaced with target namespace<br>`${SMA_SELECTORS}`: Additional label filters |
| `prepared_query` | String | Use a predefined query from SMA for common metrics (alternative to `query`) |
| `sensors` | List of strings | List of sensors required for this measurement (used with `prepared_query`) |
| `step` | Integer (seconds) | Sampling interval in seconds |
| `unit` | String | Measurement unit (e.g., `watts`, `joules`, `cpu_time_seconds`, `metadata`) |
| `target` | List of strings | Target names to measure, or `all` for all defined targets |

**Query Methods:**
- **Custom Query**: Use `query` field with custom PromQL
- **Prepared Query**: Use `prepared_query` field with predefined SMA queries (e.g., `pod_kepler_energy_consumption`, `node_scaphandre_energy_consumption`)

**Example Measurements:**
- **CPU Usage**: Container CPU usage across namespaces
- **Wall Power**: Physical power consumption from smart plugs (e.g., Shelly)
- **Pod Power (Kepler)**: Per-pod energy consumption via Kepler
- **Node Power (Scaphandre)**: Host-level power measurements
- **Container Info**: Metadata about running containers

##### 7. Report
```yaml
report:
  format: csv          # Output format
  location: reports/${startTime}_${runHash}/
  filename: "${name}_${startTime}.csv"
  post_processor:
    - name: overview
      type: notebook
      notebook: reports/overview.ipynb
    - name: validation
      type: sma
      module: sma.validation.Validator
```

| Field | Type | Description |
|-------|------|-------------|
| `format` | String | Output format (currently supports `csv`) |
| `location` | String | Directory path for reports. Supports template variables:<br>`${startTime}`: Timestamp when measurement started<br>`${runHash}`: Unique hash for the measurement run |
| `filename` | String | File naming pattern. Supports template variables:<br>`${name}`: Measurement name<br>`${startTime}`: Measurement start time |
| `post_processor` | List | (Optional) Post-processing steps to run after data collection |
| `post_processor[].name` | String | Identifier for the post-processor |
| `post_processor[].type` | `notebook`, `sma` | Type of post-processor: `notebook` for Jupyter notebooks, `sma` for built-in SMA modules |
| `post_processor[].notebook` | String | Path to Jupyter notebook (when `type: notebook`) |
| `post_processor[].module` | String | Python module path (when `type: sma`) |



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