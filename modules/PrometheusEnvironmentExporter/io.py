from .enviroment import Environment
import os
import pandas as pd
from .model import Node, Pod, Container, Process
from logging import getLogger

logger = getLogger("sma.ReportIO")


def _serialize_environment(environment: Environment, filepath: str) -> None:
    """Serialize environment data to HDF5 file using as_dataframe method."""
    # Get dataframes dict from environment
    try:
        dataframes_dict = environment.as_dataframe()

        if not os.path.exists(filepath) and not os.path.isdir(filepath):
            os.makedirs(filepath)
        for key, df in dataframes_dict.items():
            if df is not None and not df.empty:
                df.to_parquet(os.path.join(filepath, f"{key}.parquet"),)
    except Exception as e:
        logger.error(f"Failed to serialize environment: {e}")
        raise



def _deserialize_environment(filepath: str) -> Environment:
    """Deserialize environment data from HDF5 file."""
    environment = Environment()

    def check_if_metric(key :str):
        return os.path.exists(os.path.join(filepath, f"{key}.parquet"))

    def load_metric(key :str) -> pd.DataFrame:
        return pd.read_parquet(os.path.join(filepath, f"{key}.parquet"))

    try:

        # Load nodes
        if check_if_metric('nodes'):
            nodes_df = load_metric('nodes')
            environment.nodes = []
            # Group by node name to reconstruct labels dict
            for node_name in nodes_df['node'].unique():
                node_rows = nodes_df[nodes_df['node'] == node_name]
                labels = dict(zip(node_rows['label'], node_rows['value']))
                environment.nodes.append(Node(name=node_name, labels=labels))
        else:
            environment.nodes = []

        # Load pods
        if check_if_metric('pods'):
            pods_df = load_metric('pods')
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
        if check_if_metric('containers'):
            containers_df = load_metric('containers')
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
        if check_if_metric('processes'):
            processes_df = load_metric('processes')
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
        logger.error(f"Failed to deserialize environment from {filepath}: {e}")
        raise

    return environment