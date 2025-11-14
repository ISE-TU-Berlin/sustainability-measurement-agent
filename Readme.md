# Sustainability Measurements Agent (SMA)

SMA is an open-source tool designed to help deploy, collect and report sustainability measurements on cloud-native applications. It is not itself a measurement tool, but rather a framework to orchestrate, combine and aggregate results from emerging suite of sustainability measurement tools. 

## Capabilities
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
 - Multiple report formats
   - CSV
   - HDF5
 - Post processing and aggregation
   - Pandas
   - Grafana Dashboards

### Measurement Tools

### Data Strcuture


## Getting Started

### Agent Mode (Continuous Monitoring)
1. kustomize build ... + config

### Experiment Mode (Benchmarking)
1. install sma (`pip install sustainability-measurements-agent`)
2. sma init <config.yaml>
3. sma deploy -f <config.yaml>
4. run experiment:
   1. CLI commands:
      1. sma start -f <config.yaml>
      2. run workload
      3. sma stop -f <config.yaml>
   2. Python API:
      ```python
      from sma import SMA

      sma = SMA(config_file="config.yaml")
      sma.deploy()
      sma.start()
      # run workload
      sma.stop()
      df = sam.collect()
      ```
5. sma collect -f <config.yaml> -o <output_folder>

### Ad-hoc Measurements
1. install sma (`pip install sustainability-measurements-agent`)
2. sma init <config.yaml>
3. sma deploy -f <config.yaml>
4. sma collect -f <config.yaml> -o <output_folder> -t <timeout_in_seconds>


## Contributing

### Acknowledgements