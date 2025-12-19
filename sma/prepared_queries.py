from typing import Dict

from sma.model import MeasurementConfig

prepared_queries: Dict[str, MeasurementConfig] = {}

prepared_queries["container_infos"] = MeasurementConfig(
    name="container_infos",
    type="raw",
    layer="container",
    unit="metadata",
    target_names=["all"],
    query="kube_pod_container_info"
)

prepared_queries["node_infos"] = MeasurementConfig(
    name="node_infos",
    type="raw",
    layer="node",
    unit="metadata",
    target_names=["all"],
    query="kube_node_info"
)

prepared_queries["pod_infos"] = MeasurementConfig(
    name="pod_infos",
    type="raw",
    layer="pod",
    unit="metadata",
    target_names=["all"],
    query="kube_pod_info"
)

prepared_queries["node_metadata"] = MeasurementConfig(
    name="node_metadata",
    type="raw",
    layer="node",
    unit="metadata",
    target_names=["all"],
    query="kubelet_node_name"
)