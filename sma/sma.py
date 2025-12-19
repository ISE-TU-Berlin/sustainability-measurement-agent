
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
        self.environment_collector: Optional[EnvironmentCollector] = self.config.create_environment_observation()
        self.session: Optional[SMASession] = None

        if meta is not None:
            self.setup(meta)

    def setup(self, session:SMASession):
        self.session = session
        self.notify_observers("onSetup")

    def notify_observers(self, event: str):
        for observer in self.observers:
            method = getattr(observer, event, None)
            if callable(method):
                method()

    def register_sma_observer(self, observer: SMAObserver) -> None:
        self.observers.append(observer)

    def unregister_sma_observer(self, observer: SMAObserver) -> None:
        self.observers.remove(observer)
    
    def connect(self) -> None:
        for k, client in self.config.services.items():
            if client.ping():
               self.logger.info(f"Service {k} is reachable.")
            else:
               self.logger.error(f"Service {k} is not reachable.")
               raise ValueError(f"Service {k} is not reachable.")

    def observe_once(self, run_data: ReportMetadata) -> None:
        """Observe measurements for a completed run and persist to disk.
        
        Args:
            run_data: ReportMetadata containing timing and run identification data
        """
        rep = Report(metadata=run_data, config=self.config, data={}, environment=None)

        queries = self.config.measurement_queries()
        
        for name, measurement in queries.items():   
            try:
                self.logger.info(f"Observing measurement: {name}")
                #XXX: not a good pattern... should not use knowlalge about internals of measurment..., labeling should happen during observation
                df = measurement.observe(start=run_data.run.startTime, end=run_data.run.endTime)
                df = measurement.label(treatment_start=run_data.run.treatment_start.timestamp(), treatment_end=run_data.run.treatment_end.timestamp(),
                                       label_column="treatment", label="Treatment")
                rep.set_data(name, df)
            except ServiceException as e:
                self.logger.error(f"Error observing measurement {name}: {e}")

        if self.environment_collector:
            env = self.environment_collector.observe_environment(run_data.run)
            rep.environment = env
        rep.persist()

    def _run_with_timer(self) -> None:
        """Run observation in timer mode with fixed duration windows.
        """
        window = self.config.observation.window
        assert window is not None, "Observation window must be defined for timer mode"
        
        start_time = datetime.datetime.now()
        run_hash = make_run_hash(start_time)
        
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
        
        end_time = datetime.datetime.now()
        total_duration = end_time - start_time
        self.logger.info(f"Total observation duration: {total_duration}")
        
        run_data = SMARun(
            startTime=start_time,
            endTime=end_time,
            treatment_start=treatment_start,
            treatment_end=treatment_end,
            runHash=run_hash,
            user_data={
                "timer_duration": (treatment_end-treatment_start).total_seconds(),
            }
        )
        
        self.observe_once(ReportMetadata(
            session=self.session,
            run=run_data,
        ))

    def _run_with_trigger(self, trigger: TriggerFunction) -> None:
        """Run observation in trigger mode where a function controls the treatment period.
        
        Args:
            trigger: Function that executes the workload and returns file-level metadata
            location_metadata: Metadata for organizing report location
        """
        if self.session is None:
            raise ValueError("Session must be set before running in trigger mode.")

        start_time = datetime.datetime.now()
        run_hash = make_run_hash(start_time)
        window = self.config.observation.window
        if window is not None:
            sleep(window.left)
        self.notify_observers("onStart")
        
        treatment_start = datetime.datetime.now()
        
        trigger_meta = trigger()
        
        treatment_end = datetime.datetime.now()
        self.logger.info(f"Treatment duration: {treatment_end - treatment_start}")
        self.notify_observers("onEnd")
        
        if window is not None:
            sleep(window.right)
        self.notify_observers("onRight")
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

    def run(self, trigger: Optional[TriggerFunction] = None) -> None:
        """Execute a measurement run.
        
        Args:
            trigger: Optional function for trigger/continuous modes that returns file-level metadata
        """
        if self.config.observation.mode == "timer":
            self._run_with_timer()
        elif self.config.observation.mode == "trigger":
            if trigger is None:
                raise ValueError("Trigger function must be provided for trigger mode")
            self._run_with_trigger(trigger)
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

