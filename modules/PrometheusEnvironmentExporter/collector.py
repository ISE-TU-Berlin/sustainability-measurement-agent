import logging
from sma.prometheus import Prometheus, PrometheusMetric
from sma.config import measurement_config_to_prometheus_query
from .enviroment import  Environment
from .model import Node, Pod, Container, Process
from sma.model import SMARun
from typing import Dict, List
from .prepared_queries import prepared_queries

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class PrometheusEnvironmentCollector:
    def __init__(self, prometheus_client: Prometheus) -> None:

        logger.debug("Initializing Prometheus Environment Collector for Prometheus at " + prometheus_client.base_url)
        self.prometheus = prometheus_client

        if not self.prometheus.ping():
            raise ValueError("Prometheus service is not configured to collect environment.")

        self.queries: Dict[str,PrometheusMetric] = {
            "node_infos": measurement_config_to_prometheus_query(prepared_queries["node_infos"], "node_info", self.prometheus),
            "pod_infos": measurement_config_to_prometheus_query(prepared_queries["pod_infos"], "pod_info", self.prometheus),
            "node_metadata": measurement_config_to_prometheus_query(prepared_queries["node_metadata"], "node_metadata", self.prometheus ),
            "container_infos": measurement_config_to_prometheus_query(prepared_queries["container_infos"], "container_info", self.prometheus),

        }



    def _observe_node_infos(self, run: "SMARun") -> List[Node]:
        node_info = self.queries["node_infos"].observe(start=run.startTime,end=run.endTime).reset_index(drop=True).drop(
            columns=['timestamp', 'layer', 'unit', 'app_kubernetes_io_instance', 'app_kubernetes_io_version',
                     'helm_sh_chart', 'instance', 'kubeproxy_version', 'service']).drop_duplicates().set_index('node')

        nodes : List[Node] = node_info.apply(lambda row: Node(name=row.name, labels=row.to_dict()), axis=1).values.tolist()

        return nodes

    def _observe_pod_infos(self, run: "SMARun") -> List[Pod]:
        useless_tags = ['__name__', 'app_kubernetes_io_component', 'app_kubernetes_io_instance',
                        'app_kubernetes_io_managed_by', 'app_kubernetes_io_name',
                        'app_kubernetes_io_part_of', 'app_kubernetes_io_version',
                        'helm_sh_chart', 'pod_info', 'layer', 'unit']
        pod_info = self.queries["pod_infos"].observe(run.startTime, run.endTime)

        pod_list : List[Pod] = []
        pods = pod_info.drop(columns=useless_tags + ['timestamp'], errors='ignore').reset_index()
        pods = pods.groupby(['pod', 'node', 'namespace', 'created_by_kind', 'created_by_name', 'host_network', 'uid'])[
            'timestamp'].agg(['min', 'max', 'count']).reset_index()

        for _, row in pods.iterrows():
            pod = Pod(
                name=row['pod'],
                namespace=row['namespace'],
                node_name=row['node'],
                labels={
                    "uid": row['uid'],
                    "created_by": row['created_by_kind'],
                    "created_by_name": row['created_by_name'],
                    "host_network": row['host_network'],

                }
            )
            pod.lifetime_start = row['min']
            pod.lifetime_end = row['max']

            pod_list.append(pod)
        return pod_list

    def _observe_containers(self, run: "SMARun") -> List[Container]:
        container_info = self.queries["container_infos"].observe(run.startTime, run.endTime)

        container_list : List[Container] = []

        useless_tags = ['layer', 'unit', 'app_kubernetes_io_instance', 'app_kubernetes_io_version', 'helm_sh_chart',
                        'instance', 'kubeproxy_version', 'service', '__name__', 'app_kubernetes_io_managed_by',
                        'app_kubernetes_io_part_of', 'app_kubernetes_io_name', 'app_kubernetes_io_component', 'job']

        containers = container_info.drop(columns=useless_tags + ['timestamp'], errors='ignore').reset_index()
        containers = containers.groupby(['node', 'pod', 'container', 'container_id', 'image_id', 'namespace', 'uid'])[
            'timestamp'].agg(['min', 'max', 'count']).reset_index()

        for _, row in containers.iterrows():
            container = Container(
                name=row['container'],
                pod_name=row['pod'],
                namespace=row['namespace'],
                node_name=row['node'],
                labels={
                    "image": row['image_id'],
                    "uid": row['uid']
                }
            )
            container.lifetime_start = row['min']
            container.lifetime_end = row['max']

            container_list.append(container)
        return container_list

    def _observe_processes(self, run: "SMARun") -> List[Process]:

        processes : List[Process] = []
        return processes



    def observe_environment(self, run: "SMARun") -> Environment:
        # Implement Prometheus queries to collect environment data
        env = Environment()

        try:
            nodes = self._observe_node_infos(run)
            logger.debug(f"Observed {nodes} from Prometheus")
            env.nodes = nodes
        except KeyError as e:
            logger.warning(f"Error observing node infos: {e}")

        try:
            pods = self._observe_pod_infos(run)
            logger.debug(f"Observed {pods} from Prometheus")
            env.pods = pods
        except KeyError as e:
            logger.warning(f"Error observing pod infos: {e}")

        try:
            containers = self._observe_containers(run)
            logger.debug(f"Observed {containers} containers from Prometheus")
            env.containers = containers
        except KeyError as e:
            logger.warning(f"Error observing container infos: {e}")

        try:
            processes = self._observe_processes(run)
            logger.debug(f"Observed {processes} processes from Prometheus")
            env.processes = processes
        except KeyError as e:
            logger.warning(f"Error observing process infos: {e}")

        #TODO: do a assignment model, so we can map pods to nodes, containers to pods, etc.

        return env