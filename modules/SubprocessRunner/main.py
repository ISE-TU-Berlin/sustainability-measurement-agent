import logging
import json
import os
import subprocess
import shlex

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import threading
from typing import Any, Dict, Optional
import threading

from sma.model import SMAObserver, Triggerable, Triggerable

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

class SubprocessrunnerSmaModule(SMAObserver, Triggerable):
    """
    SMA Module that runs a subprocess locally as treatment. This works well when SMA is 
    running inside the cluster, e.g. as a job, and for treatments that are not easily
    bottlenecked by noise."""

    def __init__(self, config: dict):
        self.config: SubprocessRunnerConfig = SubprocessRunnerConfig.from_dict(config)
        log.info(json.dumps(config, indent=4))
        if not self.config.validate():
            raise ValueError("Invalid SubprocessRunner configuration.")
        log.debug(f"Loaded SubprocessRunner configuration: {self.config}")

    # --- HOOKS

    def trigger(self, cancel: threading.Event, **kwargs) -> Optional[Dict[str, Any]]:
        self.cancel = cancel
        parameters = {**(self.config.treatment_parameters or {}), **kwargs}
        self._run_subprocess(self.config.treatment_command, parameters=parameters)

#    def onSetup(self): # on setup gone??
    def onRunStart(self, run):
        if self.config.setup_command:
            self._run_subprocess(self.config.setup_command, parameters=self.config.setup_parameters)

    # def onTeardown(self):
    def onRunEnd(self, run):
        if self.config.teardown_command:
            self._run_subprocess(self.config.teardown_command, parameters=self.config.teardown_parameters)



    # --- PRIVATE METHODS

    def _run_subprocess(self, command: str, parameters: Optional[dict] = {}, cancel: Optional[threading.Event] = None) -> int:
        log.info(f"Running subprocess command: {command}")

        # todo: cancel

        try:
            result = subprocess.run(
                shlex.split(command) + [f"--{k}={v}" for k, v in parameters.items()], 
                cwd=self.config.workdir, 
                env = self.config.env,
                capture_output=True, 
                text=True
                )
            log.debug(f"Subprocess finished with return code {result.returncode}")
            if result.stdout:
                log.debug(f"Subprocess stdout: {result.stdout}")
            if result.stderr:
                log.error(f"Subprocess stderr: {result.stderr}")
            return result.returncode
        except Exception as e:
            log.error(f"Error running subprocess: {e}")
            return -1

@dataclass
class SubprocessRunnerConfig:
    treatment_command: str
    treatment_parameters: dict
    setup_command: str
    setup_parameters: dict
    teardown_command: str
    teardown_parameters: dict
    workdir: Path
    env = {k: v for k, v in os.environ.items() # todo
       if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONHOME", "PYTHONPATH")}

    def validate(self) -> bool:
        assert(self.workdir.exists())
        return True

    @staticmethod
    def from_dict(config_yml: dict) -> "SubprocessRunnerConfig":
        config = {}
        config["treatment_command"] = config_yml.get("treatment_command")
        config["treatment_parameters"] = config_yml.get("treatment_parameters")
        config["teardown_parameters"] = config_yml.get("teardown_parameters")
        config["setup_command"] = config_yml.get("setup_command")
        config["setup_parameters"] = config_yml.get("setup_parameters")
        config["teardown_command"] = config_yml.get("teardown_command")
        config["teardown_parameters"] = config_yml.get("teardown_parameters")
        config["workdir"] = Path(config_yml["workdir"])
        return SubprocessRunnerConfig(**config)
