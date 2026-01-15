
import datetime
import hashlib
import random
from logging import Logger, getLogger
from time import sleep
from typing import Optional

from sma.config import Config
from sma.model import (
    SMAObserver, TriggerFunction, EnvironmentCollector,
    SMARun, SMASession, ReportMetadata
)
from sma.report import Report
from sma.service import ServiceException


#TODO: we implement an observer pattern for setup, left, duration, right and teardown



def make_run_hash(start_time: datetime.datetime) -> str:
    hash_input = f"{start_time.isoformat()}_{random.random()}"
    return hashlib.sha256(hash_input.encode()).hexdigest()[:8]


class SustainabilityMeasurementAgent(object):

    def __init__(self, config: Config, observers: list[SMAObserver] = [], meta: SMASession = None) -> None:
        self.config = config
        self.logger: Logger = getLogger("sma.agent")
        self.observers: list[SMAObserver] = observers

        self.logger.debug("Initializing Environment Collector...")
        self.environment_collector: Optional[EnvironmentCollector] = self.config.create_environment_observation()
        self.session: Optional[SMASession] = None

        if meta is not None:
            self.setup(meta)

    def setup(self, session:SMASession):
        self.logger.debug("Setting up logger with session {session}")
        self.session = session
        self.notify_observers("onSetup")

    def notify_observers(self, event: str):
        for observer in self.observers:
            method = getattr(observer, event, None)
            if callable(method):
                method()
            else:
                self.logger.debug(f"tried calling inexistent event {event}")

    def register_sma_observer(self, observer: SMAObserver) -> None:
        self.observers.append(observer)

    def unregister_sma_observer(self, observer: SMAObserver) -> None:
        self.observers.remove(observer)
    
    def connect(self) -> None:
        for k, client in self.config.services.items():
            self.logger.debug(f"Pinging service {k}...")
            if client.ping():
               self.logger.info(f"Service {k} is reachable.")
            else:
               self.logger.error(f"Service {k} is not reachable.")
               raise ValueError(f"Service {k} is not reachable.")
            

    def probe(self) -> dict[str, bool]:
        """Probe all measurements to check if they are available.
        
        Returns:
            A dictionary mapping measurement names to their availability status.
        """
        results = {}
        queries = self.config.measurement_queries()
        
        for name, measurement in queries.items():   
            self.logger.debug(f"Probing measurement {name}: {measurement}")
            try:
                available = measurement.probe()
                results[name] = available
            except ServiceException as e:
                self.logger.error(f"Error probing measurement {name}: {e}")
                results[name] = False   
                 
        return results

    def observe_once(self, run_data: ReportMetadata) -> None:
        """Observe (i.e., retrieve from target) measurements for a completed run and persist to disk.
        
        Args:
            run_data: ReportMetadata containing timing and run identification data
        """
        rep = Report(metadata=run_data, config=self.config, data={}, environment=None)

        queries = self.config.measurement_queries()
        
        for name, measurement in queries.items():   
            try:
                self.logger.info(f"Querying measurement: {name}")
                #XXX: not a good pattern... should not use knowledge about internals of measurment..., labeling should happen during observation
                df = measurement.observe(start=run_data.run.startTime, end=run_data.run.endTime)
                df = measurement.label(treatment_start=run_data.run.treatment_start.timestamp(), treatment_end=run_data.run.treatment_end.timestamp(),
                                       label_column="treatment", label="Treatment")
                rep.set_data(name, df)
            except ServiceException as e:
                self.logger.error(f"Error Querying measurement {name}: {e}")

        if self.environment_collector:
            env = self.environment_collector.observe_environment(run_data.run)
            rep.environment = env
        rep.persist()


    def run(self, trigger: Optional[TriggerFunction] = None) -> None:
        """Execute a measurement run.
        
        Args:
            trigger: Optional function for trigger/continuous modes that returns file-level metadata
        """

        mode = self.config.observation.mode
        self.logger.info(f"Observation mode: {mode}")

        window = self.config.observation.window
        self.logger.info(f"Observation window: left={window.left}s, right={window.right}s, duration={window.duration}s") # type: ignore

        if self.session is None:
            raise ValueError("Session must be set before running in trigger mode.")
        
        # checks:
        if mode == "timer":
            assert window is not None, "Observation window must be defined for timer mode"
        elif mode == "trigger":
           
            if trigger is None:
                raise ValueError("Trigger function must be provided for trigger mode")
        else:
            raise ValueError(f"Unknown observation mode: {mode}")
        
        start_time = datetime.datetime.now()
        run_hash = make_run_hash(start_time)

        if window is not None:
            self.notify_observers("onLeftStarted")
            self.logger.info(f"Waiting for left window: {window.left}s")
            sleep(window.left)

        self.logger.info(f"Starting Treatment Phase")
        self.notify_observers("onStart")

        treatment_start = datetime.datetime.now()

        trigger_meta = {}
        
        if mode == "timer":
            assert window is not None
            self.logger.info(f"Waiting for treatment duration: {window.duration}s")
            sleep(window.duration)
        elif mode == "trigger":
            assert trigger is not None
            self.logger.info(f"Waiting for trigger")
            # wait for the blocking trigger function 
            trigger_meta = trigger()
            self.logger.info(f"Trigger function fired with result: {trigger_meta}")

        treatment_end = datetime.datetime.now()

        self.logger.info(f"Treatment duration: {treatment_end - treatment_start}")
        self.notify_observers("onEnd")

        if window is not None:
            self.logger.info(f"Waiting for right window: {window.right}s")
            sleep(window.right)
            self.notify_observers("onRightFinished")

        end_time = datetime.datetime.now()

        self.logger.info(f"Total observation duration: {end_time - start_time}")
        run_data = SMARun(
            startTime=start_time,
            endTime=end_time,
            treatment_start=treatment_start,
            treatment_end=treatment_end,
            runHash=run_hash,
            user_data=trigger_meta,
        )
        
        self.observe_once(ReportMetadata(
            session=self.session,
            run=run_data,
        ))



    def deploy(self) -> None:
        raise NotImplementedError("Deployment is not yet implemented.")
    
    def undeploy(self) -> None:
        raise NotImplementedError("Undeployment is not yet implemented.")
    
    def verify_deployment(self) -> bool:
        raise NotImplementedError("Deployment verification is not yet implemented.")

    def teardown(self) -> None:
        self.notify_observers("onTeardown")
        #TODO: clean up clients, connections, etc.

