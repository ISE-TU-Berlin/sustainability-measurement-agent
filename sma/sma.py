
import datetime
import hashlib
import importlib
import random
from contextlib import contextmanager
from logging import Logger, getLogger
from time import sleep
from typing import Generator, Optional

from sma.config import Config
from sma.model import (
    SMAObserver, TriggerFunction,
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

        self.session: Optional[SMASession] = None
        self.meta_session: Optional[SMASession] = meta

        self.modules = {}
        self.load_modules()

        # if meta is not None:
        # now always call setup with or without given session:
        # self.setup(meta) ---> now happening in start_session context manager

    
    @contextmanager
    def start_session(self) -> Generator[None, None, None]:
        self.logger.debug("Starting session...")
        try:
            if self.meta_session:
                self.setup(self.meta_session)
            else:
                self.setup(SMASession(name=f"SMA Session {datetime.datetime.now().isoformat()}"))
            self.notify_observers("onSessionStart")
            yield 
        finally:
            self.notify_observers("onSessionEnd")
            self.teardown()

    def load_modules(self) -> None:
        """Load SMA modules as per configuration and reguister them as observers."""
        for module_id, module_config in self.config.modules.items():
            self.logger.info(f"Loading module: {module_id}")
            module_name = module_config.get("module")
            if not module_name:
                self.logger.error(f"Module configuration for {module_id} missing 'module' key.")
                continue

            module_cfg = module_config.get("config", {})
            path = f"modules.{module_name}.main"
            klass_name = f"{module_name.capitalize()}SmaModule"  # Placeholder; in real code, determine class name dynamically
            self.logger.debug(f"Importing module class {klass_name} from {path}...")
            
            module = importlib.import_module(path)
            klass = getattr(module, klass_name)
            module_instance = klass(module_cfg)
            self.register_sma_observer(module_instance)
            self.modules[module_id] = module_instance

        self.logger.info(f"Loaded modules: {list(self.modules)}")


    def setup(self, session:SMASession):
        self.notify_observers("onSetup")
        self.logger.debug("Setting up logger with session {session}")
        self.session = session

    def notify_observers(self, event: str, **kwargs) -> None:
        self.logger.info(f"Notifying observers of event: {event}")
        if not (hasattr(SMAObserver, event)):
            self.logger.warning(f"Observer does not implement event {event}")

        for observer in self.observers:
            method = getattr(observer, event, None)
            if callable(method):
                method(**kwargs)
            else:
                self.logger.debug(f"tried calling inexistent event {event} on observer {observer}")

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




    def run(self, trigger: Optional[TriggerFunction] = None) -> None:
        """Execute a measurement run.
        
        Args:
            trigger: Optional function for trigger/continuous modes that returns file-level metadata
        """

        assert self.session is not None, "Session must be set before running, use with start_session context manager."

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
        elif mode == "module":
            assert trigger is None, "Trigger function should not be provided for module mode"
            md = self.modules[self.config.observation.module_trigger]
            assert hasattr(md, 'trigger') and callable(getattr(md, 'trigger')), \
                f"Module {md} must have a callable 'trigger' function"
        else:
            raise ValueError(f"Unknown observation mode: {mode}")
        
        start_time = datetime.datetime.now()
        run_hash = make_run_hash(start_time)

        if window is not None:
            self.notify_observers("onLeftStart")
            self.logger.info(f"Waiting for left window: {window.left}s")
            sleep(window.left)
            self.notify_observers("onLeftEnd")

        self.logger.info(f"Starting Treatment Phase")
        self.notify_observers("onTreatmentStart")
        treatment_start = datetime.datetime.now()

        trigger_meta = {}
        
        if mode == "timer":
            assert window is not None
            self.logger.info(f"Waiting for treatment duration: {window.duration}s")
            sleep(window.duration)
        elif mode == "module":
            module_id = self.config.observation.module_trigger
            assert module_id is not None
            self.logger.info(f"Waiting for module trigger from module: {module_id}")
            module = self.modules[module_id]
            trigger_meta = module.trigger()
            self.logger.info(f"Module {module_id} trigger function completed with result: {trigger_meta}")
        elif mode == "trigger":
            assert trigger is not None
            self.logger.info(f"Waiting for trigger")
            # wait for the blocking trigger function 
            trigger_meta = trigger()
            self.logger.info(f"Trigger function fired with result: {trigger_meta}")

        treatment_end = datetime.datetime.now()

        self.logger.info(f"Treatment duration: {treatment_end - treatment_start}")
        self.notify_observers("onTreatmentEnd")

        if window is not None:
            self.notify_observers("onRightStart")
            self.logger.info(f"Waiting for right window: {window.right}s")
            sleep(window.right)
            self.notify_observers("onRightEnd")
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

        self.notify_observers("onRunEnd", run=run_data)

    def observe_once(self, run_data: ReportMetadata, overwrite: bool = False) -> None:
        """Observe (i.e., retrieve from target) measurements for a completed run and persist to disk.
        
        Args:
            run_data: ReportMetadata containing timing and run identification data
        """
        rep = Report(metadata=run_data, config=self.config, data={})

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

        rep.persist()
        self.notify_observers("onReport", report=rep)

    def deploy(self) -> None:
        raise NotImplementedError("Deployment is not yet implemented.") # todo: as module?
    
    def undeploy(self) -> None:
        raise NotImplementedError("Undeployment is not yet implemented.")
    
    def verify_deployment(self) -> bool:
        raise NotImplementedError("Deployment verification is not yet implemented.")

    # now handled via context manager 
    def teardown(self) -> None:
        self.notify_observers("onSessionEnd")
        self.notify_observers("onTeardown")
        #TODO: clean up clients, connections, etc.

