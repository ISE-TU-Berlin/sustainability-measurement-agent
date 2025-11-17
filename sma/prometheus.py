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
from math import e
import uuid
import pandas as pd
import numpy as np
from typing import Any, Dict, List, Optional
import requests
from requests.adapters import Retry, HTTPAdapter
from sma import utils
from sma.service import ServiceClient, ServiceException
from sma.observations import ObservationTarget
from string import Template
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
        temp_keys = metric_template.get_identifiers()
        
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

    def range_query(self, query, start, end, step=None, timeout=None):
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
    ) -> None:
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
    ) -> None:
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

    def _range_query_to_df(self, json_data, metric_column_name) -> Optional[pd.DataFrame]:
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
            columns += ["timestamp", metric_column_name, self.name]
            rows = []
            for result in results:
                for timestamp, value in result["values"]:
                    parsed_value = self._parse_metric_string(value)
                    rows.append(
                        {
                            **result["metric"],
                            "timestamp": timestamp,
                            metric_column_name: parsed_value,
                            self.name: parsed_value,
                        }
                    )
            dataframe = pd.DataFrame(columns=columns, data=rows)
            dataframe.set_index(
                pd.to_datetime(dataframe.timestamp, utc=True, unit="s"), inplace=True
            )
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
            prometheus_metrics, metric_column_name=self.name
        )
        
        if self.data is None:
            raise ServiceException(
                message="No data returned from Prometheus for query",
                explanation=f"Query: {prometheus_query}, start: {start_timestamp}, end: {end_timestamp}",
            )
            
        return self.data
