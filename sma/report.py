

import datetime
import json
import os
from glob import glob
from logging import getLogger
from string import Template
from typing import Any, Dict, List, Optional

import pandas as pd

from sma import utils
from sma.config import Config
from sma.enviroment import Environment
from sma.model import (
    SMASession, SMARun, ReportMetadata,
    Node, Pod, Container, Process
)


class Report:
    """
    Report class contains the data and metadata for collected measurements.
    
    It provided access to the run data (when, what was done), measurment metadata (unit, description, query) and raw dataframes.
    
    It can be persisted to disk or loaded from disk.
    
    """
    def __init__(self, metadata: ReportMetadata, config: Config, data: Dict[str, pd.DataFrame], environment: Optional[
        Environment]) -> None:
        self.logger = getLogger("sma.Report")

        self.metadata : ReportMetadata = metadata
        self.run_data : SMARun = metadata.run  # Convenience property for backward compatibility
        self.config : Config = config
        self.environment : Optional[Environment] = environment # We should store meta data about the pods and nodes here
        self.observations : Dict[str, pd.DataFrame] = data

        
        # Calculate and validate location once
        self.location = self._calculate_location()
    
    def set_data(self, name: str, dataframe: pd.DataFrame) -> None:
        self.observations[name] = dataframe
    
    def get_dataframe(self, name: str) -> Optional[pd.DataFrame]:
        return self.observations.get(name, None)
    
    
    def __getattribute__(self, name: str) -> Any:
        try:
            return super().__getattribute__(name)
        except AttributeError:
            if name in self.observations:
                return self.observations[name]
            raise
    
    def __getitem__(self, item) -> Any:
        if item not in self.observations:
            raise KeyError(f"Measurement {item} not found in report data.")
        return self.observations[item]
    
    def measurments(self) -> List[str]:
        return list(self.config.measurements.keys())

    def persist(self, extras: Optional[dict] = None) -> None:
        """Persist report data and metadata to disk."""
        ReportIO.persist(self, extras)  # Delegate to ReportIO implementation

    def _calculate_location(self) -> str:
        """Calculate and validate the location path for this report."""
        context = ReportIO._build_location_context(self.metadata)
        location_template = Template(self.config.report.location)
        location = location_template.safe_substitute(**context)
        ReportIO._validate_location(location)
        return location

    def _get_or_make_report_location(self) -> str:
        """Ensure report location directory exists and return the path."""
        if os.path.exists(self.location):
            self.logger.info(f"Report location {self.location} exists.")
        else:
            os.makedirs(self.location)
            self.logger.info(f"Created report location {self.location}.")
        return self.location


class ReportIO:
    """
    Handles persistence and loading of Report objects with version awareness.

    Report Structure:
    {location}/
      ├── manifest.json          # Index of all files + version info
      ├── session.json           # Session metadata
      ├── run.json               # Run metadata
      ├── config.yaml            # Copy of measurement config
      ├── environment.json       # Environment data (optional)
      └── data/
          ├── metric1.csv        # One file per measurement
          └── metric2.csv
    """

    CURRENT_VERSION = "1.0"
    MANIFEST_FILE = "manifest.json"
    SESSION_FILE = "session.json"
    RUN_FILE = "run.json"
    CONFIG_FILE = "config.yaml"
    ENVIRONMENT_FILE = "environment.h5"
    DATA_DIR = "data"

    @staticmethod
    def _build_location_context(run_data: Optional[ReportMetadata] = None) -> dict:
        """Build template context for location path from run_data and run_extras."""
        context = {}
        if run_data:
            context.update(run_data.to_dict({}))
        return context

    @staticmethod
    def _validate_location(location: str) -> None:
        """Validate that location path is safe (relative, no path traversal)."""
        if os.path.isabs(location):
            raise ValueError(f"Report location must be relative, not absolute: {location}")
        # Check for path traversal attempts
        path_parts = location.split(os.path.sep)
        if ".." in path_parts:
            raise ValueError(f"Report location contains unsafe '..' component: {location}")

    @staticmethod
    def persist(report: Report, extras: Optional[dict] = None) -> str:
        """
        Persist report to disk with deterministic, human-readable structure.

        Returns:
            str: Location where report was saved
        """
        location = report._get_or_make_report_location()
        data_dir = os.path.join(location, ReportIO.DATA_DIR)
        os.makedirs(data_dir, exist_ok=True)

        report.logger.info(f"Persisting report to {location}")

        # 1. Save all measurement data files
        data_files = {}
        for name, df in report.observations.items():
            filename = f"{name}.{report.config.report.format}"
            filepath = os.path.join(data_dir, filename)

            # Save based on format
            if report.config.report.format == "csv":
                df.to_csv(filepath)
            else:
                raise ValueError(f"Unsupported report format: {report.config.report.format}")

            data_files[name] = {
                "filename": filename,
                "rows": len(df),
                "columns": list(df.columns)
            }
            report.logger.debug(f"Saved measurement '{name}' to {filepath}")

        # 2. Save session metadata
        session_data = {
            "name": report.metadata.session.name,
            "extras": report.metadata.session.extras or {}
        }
        with open(os.path.join(location, ReportIO.SESSION_FILE), "w") as f:
            json.dump(session_data, f, indent=4)

        # 3. Save run metadata
        run_data = {
            "startTime": report.metadata.run.startTime.strftime("%Y_%m_%d_%H_%M_%S"),
            "endTime": report.metadata.run.endTime.strftime("%Y_%m_%d_%H_%M_%S"),
            "treatment_start": report.metadata.run.treatment_start.strftime("%Y_%m_%d_%H_%M_%S"),
            "treatment_end": report.metadata.run.treatment_end.strftime("%Y_%m_%d_%H_%M_%S"),
            "runHash": report.metadata.run.runHash,
            "duration": report.metadata.run.duration().total_seconds(),
            "treatment_duration": report.metadata.run.treatment_duration().total_seconds(),
            "user_data": report.metadata.run.user_data or {}
        }
        if extras:
            run_data["extras"] = extras

        with open(os.path.join(location, ReportIO.RUN_FILE), "w") as f:
            json.dump(run_data, f, indent=4)

        # 4. Save config
        if report.config.config_file and os.path.exists(report.config.config_file):
            import shutil
            shutil.copy2(report.config.config_file, os.path.join(location, ReportIO.CONFIG_FILE))
            report.logger.info(f"Copied config file to report location.")
        else:
            # Fallback: save basic config info
            report.logger.warning("No config file available to copy.")

        # 5. Save environment data if present
        has_environment = False
        if report.environment:
            ReportIO._serialize_environment(report.environment, os.path.join(location, ReportIO.ENVIRONMENT_FILE))
            has_environment = True
            report.logger.info("Saved environment data")

        # 6. Save manifest (enables version-aware loading)
        manifest = {
            "version": ReportIO.CURRENT_VERSION,
            "created_at": datetime.datetime.now().isoformat(),
            "format": report.config.report.format,
            "data_files": data_files,
            "files": {
                "session": ReportIO.SESSION_FILE,
                "run": ReportIO.RUN_FILE,
                "config": ReportIO.CONFIG_FILE,
                "environment": ReportIO.ENVIRONMENT_FILE if has_environment else None
            }
        }
        with open(os.path.join(location, ReportIO.MANIFEST_FILE), "w") as f:
            json.dump(manifest, f, indent=4)

        report.logger.info(f"Report persisted successfully to {location}")
        return location

    @staticmethod
    def _serialize_environment(environment: Environment, filepath: str) -> None:
        """Serialize environment data to HDF5 file using as_dataframe method."""
        # Get dataframes dict from environment
        try:
            dataframes_dict = environment.as_dataframe()

            # Save each dataframe to HDF5 with appropriate keys
            with pd.HDFStore(filepath, mode='w') as store:
                for key, df in dataframes_dict.items():
                    if df is not None and not df.empty:
                        store[key] = df
        except Exception as e:
            getLogger("sma.Report").error(f"Failed to serialize environment: {e}")
            raise


    @staticmethod
    def _deserialize_environment(filepath: str) -> Environment:
        """Deserialize environment data from HDF5 file."""
        environment = Environment()

        try:
            with pd.HDFStore(filepath, mode='r') as store:
                # Load nodes
                if 'nodes' in store:
                    nodes_df = store['nodes']
                    environment.nodes = []
                    # Group by node name to reconstruct labels dict
                    for node_name in nodes_df['node'].unique():
                        node_rows = nodes_df[nodes_df['node'] == node_name]
                        labels = dict(zip(node_rows['label'], node_rows['value']))
                        environment.nodes.append(Node(name=node_name, labels=labels))
                else:
                    environment.nodes = []

                # Load pods
                if 'pods' in store:
                    pods_df = store['pods']
                    environment.pods = []
                    for _, row in pods_df.iterrows():
                        environment.pods.append(Pod(
                            name=row['pod'],
                            namespace=row['namespace'],
                            node_name=row['node'],
                            labels=row['labels'] if pd.notna(row['labels']) else {}
                        ))
                else:
                    environment.pods = []

                # Load containers
                if 'containers' in store:
                    containers_df = store['containers']
                    environment.containers = []
                    for _, row in containers_df.iterrows():
                        environment.containers.append(Container(
                            name=row['container'],
                            pod_name=row['pod'],
                            namespace=row['namespace'],
                            node_name=row['node'],
                            labels=row['labels'] if pd.notna(row['labels']) else {}
                        ))
                else:
                    environment.containers = []

                # Load processes
                if 'processes' in store:
                    processes_df = store['processes']
                    environment.processes = []
                    for _, row in processes_df.iterrows():
                        process = Process(
                            pid=int(row['pid']),
                            name=row['name']
                        )
                        process.container_name = row.get('container') if pd.notna(row.get('container')) else None
                        process.pod_name = row.get('pod') if pd.notna(row.get('pod')) else None
                        process.namespace = row.get('namespace') if pd.notna(row.get('namespace')) else None
                        process.node_name = row.get('node') if pd.notna(row.get('node')) else None
                        environment.processes.append(process)
                else:
                    environment.processes = []

        except Exception as e:
            getLogger("sma.Report").error(f"Failed to deserialize environment from {filepath}: {e}")
            raise

        return environment

    @staticmethod
    def load_from_config(config: Config, **search_overrides) -> List["Report"]:
        """Load all reports matching the location template pattern.

        Args:
            config: Configuration containing report location template
            **search_overrides: Override specific template variables (e.g., experiment_id="exp_123")
                              Unspecified variables will be wildcarded with "*"
        """
        logger = getLogger("sma.Report")

        # Get all template variables from location template
        location_template = Template(config.report.location)
        template_vars = utils.get_identifiers_of_template(location_template)

        # Build search context with wildcards for all variables
        meta = {var: "*" for var in template_vars}
        # Apply any overrides
        meta.update(search_overrides)

        # Build location pattern with wildcards
        location_pattern = location_template.safe_substitute(**meta)

        # Find all directories matching the pattern
        reports = []
        for dirpath in glob(location_pattern):
            if not os.path.isdir(dirpath):
                continue

            # Check if it's a valid report directory (has manifest or run_metadata.json)
            has_manifest = os.path.exists(os.path.join(dirpath, ReportIO.MANIFEST_FILE))
            has_legacy = os.path.exists(os.path.join(dirpath, "run_metadata.json"))

            if not (has_manifest or has_legacy):
                logger.debug(f"Skipping {dirpath}, not a valid report directory")
                continue

            try:
                report = ReportIO.load_from_location(dirpath, config)
                reports.append(report)
                logger.info(f"Loaded report from {dirpath}")
            except Exception as e:
                # Log but continue loading other reports
                logger.warning(f"Failed to load report from {dirpath}: {e}")

        logger.info(f"Loaded {len(reports)} report(s) matching pattern {location_pattern}")
        return reports

    @staticmethod
    def load_from_location(location: str, config: Config) -> "Report":
        """
        Load report from disk location with version-aware loading.

        Args:
            location: Path to report directory
            config: Configuration (uses stored config if available)

        Returns:
            Report: Loaded report instance
        """
        logger = getLogger("sma.Report")

        if not os.path.exists(location):
            raise FileNotFoundError(f"Report location does not exist: {location}")

        # Check for manifest file (version 1.0+)
        manifest_path = os.path.join(location, ReportIO.MANIFEST_FILE)
        if os.path.exists(manifest_path):
            with open(manifest_path, "r") as f:
                manifest = json.load(f)

            version = manifest.get("version", "1.0")
            logger.info(f"Loading report version {version} from {location}")

            if version == "1.0":
                return ReportIO._load_v1_0(location, manifest, config)
            else:
                logger.warning(f"Unknown report version {version}, attempting compatible load")
                return ReportIO._load_v1_0(location, manifest, config)
        else:
            raise ValueError(f"Report location {location} does not contain a manifest file.")

    @staticmethod
    def _load_v1_0(location: str, manifest: dict, config: Config) -> "Report":
        """Load version 1.0 report format with manifest."""
        logger = getLogger("sma.Report")

        # Load session metadata
        session_path = os.path.join(location, manifest["files"]["session"])
        with open(session_path, "r") as f:
            session_data = json.load(f)

        session = SMASession(
            name=session_data["name"],
            extras=session_data.get("extras")
        )

        # Load run metadata
        run_path = os.path.join(location, manifest["files"]["run"])
        with open(run_path, "r") as f:
            run_data = json.load(f)

        run = SMARun(
            startTime=datetime.datetime.strptime(run_data["startTime"], "%Y_%m_%d_%H_%M_%S"),
            endTime=datetime.datetime.strptime(run_data["endTime"], "%Y_%m_%d_%H_%M_%S"),
            treatment_start=datetime.datetime.strptime(run_data["treatment_start"], "%Y_%m_%d_%H_%M_%S"),
            treatment_end=datetime.datetime.strptime(run_data["treatment_end"], "%Y_%m_%d_%H_%M_%S"),
            runHash=run_data["runHash"],
            user_data=run_data.get("user_data")
        )

        # Load all data files from manifest
        data = {}
        data_dir = os.path.join(location, ReportIO.DATA_DIR)
        report_format = manifest.get("format", "csv")

        for name, file_info in manifest["data_files"].items():
            filepath = os.path.join(data_dir, file_info["filename"])

            if report_format == "csv":
                data[name] = pd.read_csv(filepath, index_col=0, parse_dates=True)
            else:
                logger.warning(f"Unsupported format {report_format}, attempting CSV load")
                data[name] = pd.read_csv(filepath, index_col=0, parse_dates=True)

            logger.debug(f"Loaded measurement '{name}' from {filepath}")

        # Load environment if present
        environment = None
        env_file = manifest["files"].get("environment")
        if env_file:
            env_path = os.path.join(location, env_file)
            if os.path.exists(env_path):
                environment = ReportIO._deserialize_environment(env_path)
                logger.info("Loaded environment data")

        metadata = ReportMetadata(session=session, run=run)

        return Report(
            metadata=metadata,
            config=config,
            data=data,
            environment=environment
        )
