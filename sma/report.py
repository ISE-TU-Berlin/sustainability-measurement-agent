

import json
from logging import getLogger
import os
from typing import Any, Dict, List, Optional
from sma.config import Config, MeasurementConfig
import datetime
from dataclasses import dataclass
import pandas as pd
from glob import glob
from string import Template

from sma.service import ServiceException



@dataclass
class RunData:
    startTime: datetime.datetime
    endTime:  datetime.datetime
    treatment_start:  datetime.datetime
    treatment_end:  datetime.datetime
    runHash: str
    
    def duration(self) -> datetime.timedelta:
        return self.endTime - self.startTime
    
    def treatment_duration(self) -> datetime.timedelta:
        return self.treatment_end - self.treatment_start
    
    def to_dict(self, kwargs: Optional[dict]) -> dict:
        meta ={
            "startTime": self.startTime.strftime("%Y_%m_%d_%H_%M_%S"),
            "endTime": self.endTime.strftime("%Y_%m_%d_%H_%M_%S") if self.endTime is not None else "",
            "treatment_start": self.treatment_start.strftime("%Y_%m_%d_%H_%M_%S") if self.treatment_start is not None else "",
            "treatment_end": self.treatment_end.strftime("%Y_%m_%d_%H_%M_%S") if self.treatment_end is not None else "",
            "runHash": self.runHash,
            "duration": self.duration().total_seconds() if self.duration() is not None else "", # type: ignore
            "treatment_duration": self.treatment_duration().total_seconds() if self.treatment_duration() is not None else "", # type: ignore
        }
        
        if kwargs:
            meta.update(kwargs)
        return meta
    
    @staticmethod
    def fields() -> List[str]:
        return [
            "startTime",
            "endTime",
            "treatment_start",
            "treatment_end",
            "runHash",
            "duration",
            "treatment_duration",
        ]
        
class Report():
    """
    Report class contains the data and metadata for collected measurements.
    
    It provided access to the run data (when, what was done), measurment metadata (unit, description, query) and raw dataframes.
    
    It can be persisted to disk or loaded from disk.
    
    """
    def __init__(self, run_data: RunData, config: Config, data: Dict[str, pd.DataFrame]) -> None:
        self.run_data = run_data
        self.config = config
        self.enviroment = None # We should store meta data about the pods and nodes here
        self.data = data
        self.logger = getLogger("sma.Report")
    
    def set_data(self, name: str, dataframe: pd.DataFrame) -> None:
        self.data[name] = dataframe    
    
    def get_dataframe(self, name: str) -> Optional[pd.DataFrame]:
        return self.data.get(name, None)
    
    
    def __getattribute__(self, name: str) -> Any:
        try:
            return super().__getattribute__(name)
        except AttributeError:
            if name in self.data:
                return self.data[name]
            raise
    
    def __getitem__(self, item) -> Any:
        if item not in self.data:
            raise KeyError(f"Measurement {item} not found in report data.")
        return self.data[item]
    
    def measurments(self) -> List[str]:
        return list(self.config.measurements.keys())
    
    #TODO: move the output, loading into a seperate class that handles reports
    @staticmethod
    def _get_location_path(config:Config, meta: dict = {}) -> str:
        location_template = Template(config.report["location"])
        return location_template.safe_substitute(
            **meta
        )
    
    def _get_or_make_report_location(self, runData: Optional[RunData] = None) -> str:
        meta = {}
        if runData is not None:
            meta = runData.to_dict(meta)
            
        location = self._get_location_path(self.config, meta)
        
        if os.path.exists(location):
            self.logger.info(f"Report location {location} exists.")
        else:
            os.makedirs(location)
            self.logger.info(f"Created report location {location}.")
        
        
        self.logger.info(f"Created report subdirectory {location}.")
        return location
    
    def persist(self, extras: Optional[dict] = None) -> None:
        
        location = self._get_or_make_report_location(self.run_data)
        
        filename_template = Template(self.config.report["filename"])
        
        for name, measurement in self.data.items():   
            self.logger.info(f"Observing measurement: {name}")
            
            filename = filename_template.safe_substitute(self.run_data.to_dict({"name": name} | (extras or {}))
            )
            #TODO: support different report formats
            full_path = os.path.join(location, filename)
            self.logger.info(f"Writing report to {full_path}")        
            measurement.to_csv(full_path) #TODO: needs to move to report config
        
        filename = "run_metadata.json"
        
        with open(os.path.join(location, filename), "w") as f:
            json.dump(self.run_data.to_dict(extras or {}), f, indent=4)
            
                
    @staticmethod
    def load_from_config(config: Config) -> List["Report"]:
        
        meta = {k:"*" for k in RunData.fields()}
        
        location = Report._get_location_path(config, meta=meta)
        reports = []
        for dirpath in glob(location):
            reports.append(Report.load_from_location(dirpath, config))
        return reports  
        
    
    @staticmethod
    def load_from_location(location: str, config: Config) -> "Report":
        runData = None
        if os.path.exists(os.path.join(location, "run_metadata.json")):
            with open(os.path.join(location, "run_metadata.json"), "r") as f:
                rdata = json.load(f)
                runData = RunData(
                    startTime=datetime.datetime.strptime(rdata["startTime"], "%Y_%m_%d_%H_%M_%S"),
                    endTime=datetime.datetime.strptime(rdata["endTime"], "%Y_%m_%d_%H_%M_%S"),
                    treatment_start=datetime.datetime.strptime(rdata["treatment_start"], "%Y_%m_%d_%H_%M_%S"),
                    treatment_end=datetime.datetime.strptime(rdata["treatment_end"], "%Y_%m_%d_%H_%M_%S"),
                    runHash=rdata["runHash"]
                )
        else:
            raise ValueError(f"Run metadata file not found in report location {location}")
        #TODO: read runData from files
        data = {}
        filename_template = Template(config.report["filename"])
       
        
        fmeta = {k: "*" for k in filename_template.get_identifiers()}
        filename_pattern = filename_template.safe_substitute(fmeta)
        
        metric_names = set(config.measurements.keys())
        
        for fname in glob(os.path.join(location, filename_pattern)):
            #TODO : support different report formats
            df = pd.read_csv(fname, index_col=0, parse_dates=True)
            #Extract name from filename
            #check if we find a matching measurement
            matched = False
            for metric_name in metric_names:
                if metric_name in fname:
                    data[metric_name] = df
                    matched = True
                    break
            if not matched:
                raise ValueError(f"Could not extract measurement name from filename {fname}")
            
            
            
        return Report(
            run_data=runData,
            config=config,
            data=data
        )
        