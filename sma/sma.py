
from curses import window
from dataclasses import dataclass
import datetime
from logging import Logger, getLogger
from time import sleep
from typing import List, Optional, Protocol, Callable
from sma.config import Config, MeasurementConfig
from sma.report import Report, RunData
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



class TriggerFunction(Protocol):
    def __call__(self) -> Optional[dict]:
        pass

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
        raise NotImplementedError("Continuous observation mode is not yet implemented.")
    
    def make_run_hash(self, startTime: datetime.datetime) -> str:
        hash_input = f"{startTime.isoformat()}_{random.random()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:8]
    
    
    #TODO: impove interface, to much dependency on report structure
    def observe_once(self, runData: RunData, extras: Optional[dict] = None) -> None:
        if runData.endTime is None or runData.treatment_start is None or runData.treatment_end is None:
            raise ValueError("endTime, treatment_start, and treatment_end must be defined for observe_once")
        
        rep = Report(run_data=runData, config=self.config, data={})
        
        queries = self.config.measurement_queries()
        
        for name, measurement in queries.items():   
            try:
                self.logger.info(f"Observing measurement: {name}")
                df = measurement.observe(start=runData.startTime, end=runData.endTime)
                df = measurement.label(treatment_start=runData.treatment_start.timestamp(),  treatment_end=runData.treatment_end.timestamp(),
                label_column="treatment", label="Treatment")
                rep.set_data(name, df)
            except ServiceException as e:
                self.logger.error(f"Error observing measurement {name}: {e}")

        rep.persist(extras=extras)

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

    
    def _run_trigger(self,trigger: TriggerFunction) -> None:
        startTime = datetime.datetime.now()
        runHash = self.make_run_hash(startTime)
        window = self.config.observation.window
        if window is not None:
            sleep(window.left)
        self.notify_observers("onStart")
        
        treatment_start = datetime.datetime.now()
        
        meta = trigger()
        
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
        
        self.observe_once(run_data, extras=meta)
        
        
    
    def _run_continuous(self,trigger: TriggerFunction) -> None:
        startTime = datetime.datetime.now()
        runHash = self.make_run_hash(startTime)
        self.logger.info(f"Observation mode: {self.config.observation.mode}")
        self.notify_observers("onStart")
        self.observe_continueously()
        
        _ = trigger()
       
        endTime = datetime.datetime.now()
        self.logger.info(f"Total observation duration: {endTime - startTime}")
        self.notify_observers("onEnd")
        
        

    def run(self, trigger: Optional[TriggerFunction] = None) -> None:
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
    

    def deploy(self) -> None:
        raise NotImplementedError("Deployment is not yet implemented.")
    
    def undeploy(self) -> None:
        raise NotImplementedError("Undeployment is not yet implemented.")
    
    def verify_deployment(self) -> bool:
        raise NotImplementedError("Deployment verification is not yet implemented.")

    def teardown(self) -> None:
        self.notify_observers("onTeardown")
        #TODO: clean up clients, connections, etc.

