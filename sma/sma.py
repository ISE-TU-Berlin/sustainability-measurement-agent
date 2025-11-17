
from curses import window
import datetime
from logging import Logger, getLogger
from time import sleep
from typing import Optional, Protocol, Callable
from sma.config import Config
from sma.service import ServiceException
import os
from string import Template


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

    
    def observe_once(self, startTime: datetime.datetime, endTime: datetime.datetime) -> None:
        queries = self.config.measurement_queries()
        location = self.config.report["location"]
        if os.path.exists(location):
            self.logger.info(f"Report location {location} exists.")
        else:
            os.makedirs(location)
            self.logger.info(f"Created report location {location}.")
        
        location = os.path.join(location, startTime.strftime("%Y-%m-%d_%H-%M-%S"))
        os.makedirs(location)
        
        self.logger.info(f"Created report subdirectory {location}.")
        filename_template = Template(self.config.report["filename"])
        
        for name, measurement in queries.items():   
            try:
                self.logger.info(f"Observing measurement: {name}")
                df = measurement.observe(start=startTime, end=endTime)
                
                filename = filename_template.safe_substitute(
                    name=name,
                    startTime=startTime.strftime("%Y%m%d_%H%M%S"),
                    endTime=endTime.strftime("%Y%m%d_%H%M%S"),
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
        self.notify_observers("onLeft")
        self.logger.info(f"Observation mode: {self.config.observation.mode}")
        
        self.logger.info(f"Observation window: left={window.left}s, right={window.right}s, duration={window.duration}s") # type: ignore

       

        sleep(window.left)
        self.notify_observers("onStart")

        sleep(window.duration)
        self.notify_observers("onEnd")
        sleep(window.right)
        self.notify_observers("onRight")
        
        endTime = datetime.datetime.now()
        totalDuration = endTime - startTime
        self.logger.info(f"Total observation duration: {totalDuration}")
        
        self.observe_once(startTime, endTime)

    
    def _run_trigger(self,trigger: Callable) -> None:
        startTime = datetime.datetime.now()
        window = self.config.observation.window
        if window is not None:
            sleep(window.left)
        self.notify_observers("onStart")
        trigger()
        self.notify_observers("onEnd")
        if window is not None:
            sleep(window.right)
        self.notify_observers("onRight")
        endTime = datetime.datetime.now()
        self.logger.info(f"Total observation duration: {endTime - startTime}")
        self.observe_once(startTime, endTime)
        
        
    
    def _run_continuous(self,trigger: Callable) -> None:
        
        self.logger.info(f"Observation mode: {self.config.observation.mode}")
        self.notify_observers("onStart")
        self.observe_continueously()
        trigger()
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

