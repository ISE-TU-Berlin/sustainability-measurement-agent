
from curses import window
from dataclasses import dataclass
import datetime
from logging import Logger, getLogger
from time import sleep
from typing import List, Optional, Protocol, Callable
from sma.config import Config
from sma.service import ServiceException
import os
from string import Template
import pandas as pd
import random
import hashlib


#TODO: we implement an observer pattern for setup, left, duration, right and teardown

class SMAObserver(Protocol):
    def onSetup(self) -> None:
        pass

    def onLeft(self) -> None:
        pass

    def onStart(self) -> None:
        pass

    def onEnd(self) -> None:
        pass

    def onRight(self) -> None:
        pass

    def onTeardown(self) -> None:
        pass


@dataclass
class RunData:
    startTime: datetime.datetime
    endTime: Optional[datetime.datetime]
    treatment_start: Optional[datetime.datetime]
    treatment_end: Optional[datetime.datetime]
    runHash: str
    
    def duration(self) -> Optional[datetime.timedelta]:
        if self.endTime is None:
            return None
        return self.endTime - self.startTime
    
    def treatment_duration(self) -> Optional[datetime.timedelta]:
        if self.treatment_start is None or self.treatment_end is None:
            return None
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

class SustainabilityMeasurementAgent(object):

    def __init__(self, config: Config, observers: list[SMAObserver] = []) -> None:
        self.config = config
        self.logger: Logger = getLogger("sma.agent")
        self.observers: list[SMAObserver] = observers

        self.notify_observers("onSetup")

    def notify_observers(self, event: str):
        for observer in self.observers:
            method = getattr(observer, event, None)
            if callable(method):
                method()

    def register_observer(self, observer: SMAObserver) -> None:
        self.observers.append(observer)

    def unregister_observer(self, observer: SMAObserver) -> None:
        self.observers.remove(observer)
    
    def connect(self) -> None:
        for k, client in self.config.services.items():
            if client.ping():
               self.logger.info(f"Service {k} is reachable.")
            else:
               self.logger.error(f"Service {k} is not reachable.")
               raise ValueError(f"Service {k} is not reachable.")

    def observe_continueously(self) -> None:
        pass
    
    def make_run_hash(self, startTime: datetime.datetime) -> str:
        hash_input = f"{startTime.isoformat()}_{random.random()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:8]
    
    def _get_location_path(self, meta: dict = {}) -> str:
        location_template = Template(self.config.report["location"])
        return location_template.safe_substitute(
            **meta
        )
    
    def _get_or_make_report_location(self, runData: Optional[RunData] = None) -> str:
        meta = {}
        if runData is not None:
            meta = runData.to_dict(meta)
            
        location = self._get_location_path(meta)
        
        if os.path.exists(location):
            self.logger.info(f"Report location {location} exists.")
        else:
            os.makedirs(location)
            self.logger.info(f"Created report location {location}.")
        
        
        self.logger.info(f"Created report subdirectory {location}.")
        return location
    
    def load_measurements(self) -> List[pd.DataFrame]:
        meta = {k:"*" for k in RunData.fields()}
        
        location = self._get_location_path(meta=meta)
        filename_template = Template(self.config.report["filename"])
        from glob import glob
        dataframes: List[pd.DataFrame] = []
        
        
        filename_pattern = filename_template.safe_substitute(meta | {"name": "*"})
        
        
        for fname in glob(os.path.join(location, filename_pattern)):
            self.logger.info(f"Loading measurement from {fname}")
            #TODO : support different report formats
            df = pd.read_csv(fname, index_col=0, parse_dates=True)
            dataframes.append(df)
        return dataframes
    
    def observe_once(self, runData: RunData) -> None:
        queries = self.config.measurement_queries()
        if runData.endTime is None or runData.treatment_start is None or runData.treatment_end is None:
            raise ValueError("endTime, treatment_start, and treatment_end must be defined for observe_once")
        
        location = self._get_or_make_report_location(runData)
        
        self.logger.info(f"Created report subdirectory {location}.")
        filename_template = Template(self.config.report["filename"])
        
        for name, measurement in queries.items():   
            try:
                self.logger.info(f"Observing measurement: {name}")
                df = measurement.observe(start=runData.startTime, end=runData.endTime)
                df = measurement.label(treatment_start=runData.treatment_start.timestamp(), treatment_end=runData.treatment_end.timestamp(),
                                        label_column="treatment", label="Treatment")
                filename = filename_template.safe_substitute(runData.to_dict({"name": name})
                )
                #TODO: support different report formats
                full_path = os.path.join(location, filename)
                self.logger.info(f"Writing report to {full_path}")        
                df.to_csv(full_path) #TODO: needs to move to report config
            except ServiceException as e:
                self.logger.error(f"Error observing measurement {name}: {e}")
    

    def _run_timer(self) -> None:
        window = self.config.observation.window
        assert window is not None, "Observation window must be defined for timer mode"
        
        startTime = datetime.datetime.now()
        runHash = self.make_run_hash(startTime)
        
        self.notify_observers("onLeft")
        self.logger.info(f"Observation mode: {self.config.observation.mode}")
        
        self.logger.info(f"Observation window: left={window.left}s, right={window.right}s, duration={window.duration}s") # type: ignore

       

        sleep(window.left)
        self.notify_observers("onStart")
        treatment_start = datetime.datetime.now()
        sleep(window.duration)
        treatment_end = datetime.datetime.now()
        self.logger.info(f"Treatment duration: {treatment_end - treatment_start}")
        self.notify_observers("onEnd")
        sleep(window.right)
        self.notify_observers("onRight")
        
        endTime = datetime.datetime.now()
        totalDuration = endTime - startTime
        self.logger.info(f"Total observation duration: {totalDuration}")
        
        run_data = RunData(
            startTime=startTime,
            endTime=endTime,
            treatment_start=treatment_start,
            treatment_end=treatment_end,
            runHash=runHash
        )
        
        self.observe_once(run_data)

    
    def _run_trigger(self,trigger: Callable) -> None:
        startTime = datetime.datetime.now()
        runHash = self.make_run_hash(startTime)
        window = self.config.observation.window
        if window is not None:
            sleep(window.left)
        self.notify_observers("onStart")
        treatment_start = datetime.datetime.now()
        trigger()
        treatment_end = datetime.datetime.now()
        self.logger.info(f"Treatment duration: {treatment_end - treatment_start}")
        self.notify_observers("onEnd")
        if window is not None:
            sleep(window.right)
        self.notify_observers("onRight")
        endTime = datetime.datetime.now()
        self.logger.info(f"Total observation duration: {endTime - startTime}")
        run_data = RunData(
            startTime=startTime,
            endTime=endTime,
            treatment_start=treatment_start,
            treatment_end=treatment_end,
            runHash=runHash
        )
        self.observe_once(run_data)
        
        
    
    def _run_continuous(self,trigger: Callable) -> None:
        startTime = datetime.datetime.now()
        runHash = self.make_run_hash(startTime)
        self.logger.info(f"Observation mode: {self.config.observation.mode}")
        self.notify_observers("onStart")
        self.observe_continueously()
        
        trigger()
       
        endTime = datetime.datetime.now()
        self.logger.info(f"Total observation duration: {endTime - startTime}")
        self.notify_observers("onEnd")
        
        

    def run(self, trigger: Optional[Callable] = None) -> None:
        if self.config.observation.mode == "timer":
            self._run_timer()
        elif self.config.observation.mode == "trigger":
            if trigger is None:
                raise ValueError("Trigger function must be provided for trigger mode")
            self._run_trigger(trigger)
        elif self.config.observation.mode == "continuous":
            if trigger is None:
                raise ValueError("Trigger function must be provided for continuous mode")
            self._run_continuous(trigger)
        else:
            raise ValueError(f"Unknown observation mode: {self.config.observation.mode}")
    

    def teardown(self) -> None:
        self.notify_observers("onTeardown")
        #TODO: clean up clients, connections, etc.

