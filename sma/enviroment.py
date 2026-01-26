from typing import Dict, List, Optional

import pandas as pd
import logging

from sma.model import (
    DataframeResource, Node, Pod, Container, Process
)

logger = logging.getLogger("sma.environment")


#TODO: use default enviroment metadata (pods, nodes, cluster info) to offer specific functions, e.g., map pods to node, map containers to pods, etc.
#TODO: get easy metadata per pod/node/contianer, e.g., limits, cpu_max, mem_max, other cababilities...


def as_merged_df(data:Optional[List[DataframeResource]]) -> pd.DataFrame:
    if data is None or len(data) == 0:
        return pd.DataFrame()
    
    dt = None
    try:
        for df in data:
            data = df.to_dataframe()
            if dt is None:
                dt = data
            else:
                dt = pd.concat([dt, data])
    except TypeError as e:
        logger.warning(f"Error ({e}) converting environment data to dataframe: {data}")
        return pd.DataFrame()

    return dt

class Environment:
    nodes: Optional[List[Node]] = None
    pods: Optional[List[Pod]] = None
    containers: Optional[List[Container]] = None
    processes: Optional[List[Process]] = None

    def __init__(self) -> None:
        pass


    def as_dataframe(self) -> Dict[str, pd.DataFrame]:
        dataframes = {'nodes': as_merged_df(self.nodes), "pods": as_merged_df(self.pods),
                      "containers": as_merged_df(self.containers), "processes": as_merged_df(self.processes)}

        return dataframes


