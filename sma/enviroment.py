from typing import Dict, List

import pandas as pd

from sma.model import (
    DataframeResource, Node, Pod, Container, Process
)


#TODO: use default enviroment metadata (pods, nodes, cluster info) to offer specific functions, e.g., map pods to node, map containers to pods, etc.
#TODO: get easy metadata per pod/node/contianer, e.g., limits, cpu_max, mem_max, other cababilities...


def as_merged_df(data:List[DataframeResource]) -> pd.DataFrame:
    dt = None
    for df in data:
        data = df.to_dataframe()
        if dt is None:
            dt = data
        else:
            dt = pd.concat([dt, data])

    return dt

class Environment:
    nodes: List[Node]
    pods: List[Pod]
    containers: List[Container]
    processes: List[Process]

    def __init__(self) -> None:
        pass

    def nodes(self) -> List[Node]:
        return self.nodes

    def pods(self) -> List[Pod]:
        return self.pods

    def containers(self) -> List[Container]:
        return self.containers

    def processes(self) -> List[Process]:
        return self.processes


    def as_dataframe(self) -> Dict[str, pd.DataFrame]:
        dataframes = {'nodes': as_merged_df(self.nodes), "pods": as_merged_df(self.pods),
                      "containers": as_merged_df(self.containers), "processes": as_merged_df(self.processes)}

        return dataframes


