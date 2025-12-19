"""
Purpose: Interacts with the Prometheus API.
Functionality: Provides methods to query metrics and labels from Prometheus.
Connection: Used by responses.py and validation.py to gather metrics and validate configurations.

Wrapper around the Prometheus HTTP API

Licenced under GLPv3, originally developed for the OXN project (https://github.com/nymphbox/oxn).
"""

#TODO: check if we should use the offical prometheus client library instead of requests.

import abc
import datetime
import logging
import uuid
from string import Template
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import requests
from requests.adapters import Retry, HTTPAdapter

from sma import utils
from sma.enviroment import Environment
from sma.model import ObservationTarget, MeasurementConfig
from sma.service import ServiceClient, ServiceException
from sma.model import (
    Node, Pod, Container, Process, SMARun
)
from sma.prepared_queries import prepared_queries

logger = logging.getLogger(__name__)

# NOTE: prometheus wire timestamps are in milliseconds since unix epoch utc-aware
class Prometheus(ServiceClient):
   

    def __init__(self, kwargs: Dict[str, Any] = {}) -> None:
         # enforce required fields at the class level; loader simply passes kwargs
        if "address" not in kwargs:
            raise ValueError("Prometheus service requires an 'address' field")

        if not kwargs["address"]:
            raise ValueError("Prometheus service requires an 'address' field")
        

        self.session = requests.Session()
        retries = Retry(
            total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504]
        )
        self.session.mount("http://", HTTPAdapter(max_retries=retries))
        self.base_url = kwargs["address"]
        self.endpoints = {
            "range_query": "/api/v1/query_range",
            "instant_query": "/api/v1/query",
            "targets": "/api/v1/targets",
            "labels": "/api/v1/labels",
            "metrics": "/api/v1/label/__name__/values",
            "label_values": "/api/v1/label/%s/values",
            "metric_metadata": "/api/v1/metadata",
            "target_metadata": "/api/v1/targets/metadata",
            "config": "/api/v1/status/config",
            "flags": "/api/v1/status/flags",
        }

    @staticmethod
    def build_query(metric_name:str, targets:Optional[List[ObservationTarget]]=None):
        """Build a query in the Prometheus Query Language format"""
        
        # build a dict of lables from the targets
        label_dict = {}
        if targets is not None:
            for target in targets:
                if target.match_labels is not None:
                    for k, v in target.match_labels.items():
                        label_dict[k] = v
        
        # first we apply python string templating to the metric name
        metric_template = Template(metric_name)
        temp_keys = utils.get_identifiers_of_template(metric_template)
        
        
        metric_filters = {k: v for k, v in label_dict.items() if k not in temp_keys}
        template_filters = {k: v for k, v in label_dict.items() if k in temp_keys}
        
        if len(metric_filters) > 0:
            filter_strings = [f'{k}="{v}"' for k, v in metric_filters.items()]
            filter_expr = "{" + ",".join(filter_strings) + "}"
            template_filters['SMA_SELECTORS'] = filter_expr
        
        metric_name = metric_template.safe_substitute(template_filters)
        
        
        return metric_name

       
        
        
        
        

    def target_metadata(
        self, match_target: Optional[str] = None, metric: Optional[str] = None, limit: Optional[int] = None
    ):
        """Return metadata about metric with additional target information"""

        params = {
            "match_target": match_target,
            "metric": metric,
            "limit": limit,
        }
        target_metadata = self.endpoints.get("target_metadata")
        if target_metadata is None:
            raise ServiceException(
                message="Error while getting endpoint for target_metadata",
                explanation="No target target_metadata endpoint returned",
            )
        url = self.base_url + target_metadata
        try:
            response = self.session.get(url=url, params=params)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.HTTPError) as requests_exception:
            raise ServiceException(
                message=f"Error while talking to Prometheus at {url}",
                explanation=f"{requests_exception}",
            )

    def targets(self):
        """Return an overview of the current state of Prometheus target discovery"""
        target = self.endpoints.get("targets")
        if target is None:
            raise ServiceException(
                message="Error while getting endpoint for targets",
                explanation="No target targets endpoint returned",
            )
        url = self.base_url + target
        try:
            response = self.session.get(url=url)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.HTTPError) as requests_exception:
            raise ServiceException(
                message=f"Error while talking to Prometheus at {url}",
                explanation=f"{requests_exception}",
            )

    def labels(self, start=None, end=None, match=None):
        """Return label names"""
        params = {
            "start": start,
            "end": end,
            "match": match,
        }
        labels = self.endpoints.get("labels")
        if labels is None:
            raise ServiceException(
                message="Error while getting endpoint for labels",
                explanation="No target labels endpoint returned",
            )
        url = self.base_url + labels
        try:
            response = self.session.get(
                url, params=params
            )
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.HTTPError) as requests_exception:
            raise ServiceException(
                message=f"Error while talking to Prometheus at {url}",
                explanation=f"{requests_exception}",
            )

    def metrics(self):
        metrics = self.endpoints.get("metrics")
        if metrics is None:
            raise ServiceException(
                message="Error while getting endpoint for metrics",
                explanation="No target metrics endpoint returned",
            )
        url = self.base_url + metrics
        try:
            response = self.session.get(url=url)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.HTTPError) as requests_exception:
            raise ServiceException(
                message=f"Error while talking to Prometheus at {url}",
                explanation=f"{requests_exception}",
            )

    def label_values(self, label=None, start=None, end=None, match=None):
        label_values = self.endpoints.get("label_values")
        if label_values is None:
            raise ServiceException(
                message="Error while getting endpoint for label_values",
                explanation="No target label_values endpoint returned",
            )
        endpoint = label_values % label
        url = self.base_url + endpoint

        params = {
            "start": start,
            "end": end,
            "match": match,
        }
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.HTTPError) as requests_exception:
            raise ServiceException(
                message=f"Error while talking to Prometheus at {url}",
                explanation=f"{requests_exception}",
            )

    def metric_metadata(self, metric=None, limit=None):
        metric_metadata = self.endpoints.get("metric_metadata")
        if metric_metadata is None:
            raise ServiceException(
                message="Error while getting endpoint for metric_metadata",
                explanation="No target metric_metadata endpoint returned",
            )
        url = self.base_url + metric_metadata
        params = {
            "metric": metric,
            "limit": limit,
        }
        try:
            response = self.session.get(url=url, params=params)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.HTTPError) as requests_exception:
            raise ServiceException(
                message=f"Error while talking to Prometheus at {url}",
                explanation=f"{requests_exception}",
            )

    def config(self):
        config = self.endpoints.get("config")
        if config is None:
            raise ServiceException(
                message="Error while getting endpoint for config",
                explanation="No target config endpoint returned",
            )
        url = self.base_url + config
        try:
            response = self.session.get(url=url)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.HTTPError) as requests_exception:
            raise ServiceException(
                message=f"Error while talking to Prometheus at {url}",
                explanation=f"{requests_exception}",
            )

    def flags(self):
        flags = self.endpoints.get("flags")
        if flags is None:
            raise ServiceException(
                message="Error while getting endpoint for flags",
                explanation="No target flags endpoint returned",
            )
        url = self.base_url + flags
        try:
            response = self.session.get(url=url)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.HTTPError) as requests_exception:
            raise ServiceException(
                message=f"Error while talking to Prometheus at {url}",
                explanation=f"{requests_exception}",
            )

    def instant_query(self, query, time=None, timeout=None):
        """Evaluate a Prometheus query instantly"""
        instant_query = self.endpoints.get("instant_query")
        if instant_query is None:
            raise ServiceException(
                message="Error while getting endpoint for instant_query",
                explanation="No target instant_query endpoint returned",
            )
        url = self.base_url + instant_query
        params = {
            "query": query,
            "time": time,
            "timeout": timeout,
        }
        try:
            response = self.session.get(url=url, params=params)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.HTTPError) as requests_exception:
            raise ServiceException(
                message=f"Error while talking to Prometheus at {url}",
                explanation=f"{requests_exception}",
            )

    def range_query(self, query:str, start:float, end:float, step:Optional[int]=None, timeout:Optional[int]=None):
        """Evaluate a Prometheus query over a time range"""
        range_query = self.endpoints.get("range_query")
        if range_query is None:
            raise ServiceException(
                message="Error while getting endpoint for range_query",
                explanation="No target range_query endpoint returned",
            )
        url = "/".join([self.base_url, range_query])
        params = {
            "query": query,
            "start": start,
            "end": end,
            "step": step,
            "timeout": timeout,
        }
        try:
            response = self.session.get(url=url, params=params)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.HTTPError) as requests_exception:
            raise ServiceException(
                message=f"Error while talking to Prometheus at {url}",
                explanation=f"{requests_exception}",
            )
    
    def ping(self) -> bool:
        """Check if the Prometheus server is reachable."""
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            return True
        except requests.HTTPError as e:
            logger.error(f"HTTP error while pinging Prometheus at {self.base_url}: {e}")
            return False
        except requests.ConnectionError as e:
            logger.error(f"Connection error while pinging Prometheus at {self.base_url}: {e}")
            return False
            
            


class ResponseVariable(abc.ABC):
    def __init__(
        self,
    ):
        self.id = uuid.uuid4().hex
        """Unique identifier"""
        self.name = None
        """Name of the response variable as defined in experiment specification"""
        self.data = None
        """Observed data stored as a dataframe"""

    @property
    @abc.abstractmethod
    def short_id(self) -> str:
        pass

    @property
    def response_type(self) -> str:
        return self.__class__.__name__

    @abc.abstractmethod
    def label(
        self,
        treatment_start: float,
        treatment_end: float,
        label_column: str,
        label: str,
    ) -> pd.DataFrame:
        pass

    @abc.abstractmethod
    def observe(self, start: datetime.datetime, end: datetime.datetime) -> pd.DataFrame:
        pass

class PrometheusMetric(ResponseVariable):
    @property
    def short_id(self) -> str:
        return self.id[:8]

    def __init__(self, 
                 client: Prometheus, 
                 name: str,
                 query: str, 
                 layer: Optional[str] = None, 
                 query_type: Optional[str] = "aggregate", 
                 unit: Optional[str] = None,
                 step: Optional[int] = 60, 
                 targets: Optional[List[ObservationTarget]] = None
        ):
        super().__init__()

        self.name = name
        self.client = client
        """Prometheus API to fetch metric data represented by this response variable"""
        self.query = query
        """User-supplied prometheus metric name"""
        self.layer = layer
        self.query_type = query_type
        self.unit = unit
        self.step = step
        """User-supplied prometheus step size"""
        self.target = targets if targets is not None else []

    def __repr__(self):
        return (
            f"MetricResponse(name={self.name}, "
            f"step={self.step})"
        )

    def label(
            self,
            treatment_start: float,
            treatment_end: float,
            label_column: str,
            label: str,
    ) -> pd.DataFrame:
        """
        Label a Prometheus dataframe. Note that Prometheus returns timestamps in seconds as a float

        """

        if self.data is None:
            raise ServiceException(
                message="Cannot label dataframe",
                explanation="Dataframe is empty for response variable: " + self.name,
            )
        
        predicate = self.data["timestamp"].between(treatment_start, treatment_end)
        
        self.data[label_column] = np.where(predicate, label, "NoTreatment")
        
        return self.data


    #unsued, deprecated?
    @staticmethod
    def _instant_query_to_df(json_data):
        """Returns a pandas dataframe from prometheus instant query json response"""
        results = json_data["data"]["result"]
        first = results[0]
        columns = list(first["metric"].keys())
        columns += ["timestamp", "metric_value"]
        ddict_list = []
        for result in results:
            ddict_list.append(
                {
                    **result["metric"],
                    "timestamp": result["value"][0],
                    "metric_value": result["value"][1],
                }
            )
        dataframe = pd.DataFrame(columns=columns, data=ddict_list)
        dataframe.set_index(pd.to_datetime(dataframe.timestamp, utc=True), inplace=True)
        return dataframe

    @staticmethod
    def _parse_metric_string(metric_value):
        try:
            return int(metric_value)
        except (TypeError, ValueError):
            try:
                return float(metric_value)
            except (TypeError, ValueError):
                return metric_value

    def _range_query_to_df(self, json_data) -> Optional[pd.DataFrame]:
        """
        Return pandas dataframe from prometheus range query json response

        We index the dataframe by the supplied timestamp from Prometheus
        """
        try:
            results = json_data["data"]["result"]
            if not results:
                return None
            if len(results) == 0:
                return None
            
            check = results[0]
            columns = list(check["metric"].keys())
            columns += ["timestamp", self.name]
            rows = []
            for result in results:
                for timestamp, value in result["values"]:
                    parsed_value = self._parse_metric_string(value)
                    rows.append(
                        {
                            **result["metric"],
                            "timestamp": timestamp,
                            self.name: parsed_value,
                        }
                    )
            dataframe = pd.DataFrame(columns=columns, data=rows)
            dataframe.set_index(
                pd.to_datetime(dataframe.timestamp, utc=True, unit="s"), inplace=True
            )
            dataframe["layer"] = self.layer
            dataframe["unit"] = self.unit
            
            return dataframe
        except (IndexError, KeyError) as exc:
            raise ServiceException(
                message="Cannot create dataframe from empty Prometheus response",
                explanation=f"{exc}",
            )

    def observe(self, start: datetime.datetime, end: datetime.datetime) -> pd.DataFrame:

        start_timestamp = start.astimezone(datetime.timezone.utc).timestamp()
        end_timestamp = end.astimezone(datetime.timezone.utc).timestamp()

        prometheus_query = self.client.build_query(
            metric_name=self.query,
            targets=self.target
        )
        
        prometheus_metrics = self.client.range_query(
            query=prometheus_query,
            start=start_timestamp,
            end=end_timestamp,
            step=self.step,
        )
        self.data = self._range_query_to_df(
            prometheus_metrics
        )
        
        if self.data is None:
            raise ServiceException(
                message="No data returned from Prometheus for query",
                explanation=f"Query: {prometheus_query}, start: {start_timestamp}, end: {end_timestamp}",
            )
            
        return self.data


# MeasurementConfig extension with Prometheus-specific methods
# Base dataclass is defined in model.py
def measurement_config_to_prometheus_query(
    config: MeasurementConfig,
    name: str,
    client: Prometheus,
    named_targets: Optional[Dict[str, ObservationTarget]] = None,
) -> PrometheusMetric:
    """Convert MeasurementConfig to PrometheusMetric query."""
    targets: List[ObservationTarget] = []
    if config.target_names is None or named_targets is None:
        targets = []
    elif "all" in config.target_names:
        targets = list(named_targets.values())
    else:
        for tname in config.target_names:
            if tname not in named_targets:
                raise KeyError(f"measurement {config.name} references unknown target '{tname}'")
            targets.append(named_targets[tname])

    return PrometheusMetric(
        client=client,
        name=name,
        query=config.query,
        layer=config.layer,
        unit=config.unit,
        query_type=config.type,
        step=config.step,
        targets=targets,
    )

class PrometheusEnvironmentCollector:
    def __init__(self, prometheus_client: Prometheus) -> None:

        self.prometheus = prometheus_client

        if not self.prometheus.ping():
            raise ValueError("Prometheus service is not configured to collect environment.")

        self.queries: Dict[str, "PrometheusMetric"] = {
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

        nodes = self._observe_node_infos(run)
        env.nodes = nodes

        pods = self._observe_pod_infos(run)
        env.pods = pods

        containers = self._observe_containers(run)
        env.containers = containers

        processes = self._observe_processes(run)
        env.processes = processes

        #TODO: do a assignment model, so we can map pods to nodes, containers to pods, etc.

        return env
