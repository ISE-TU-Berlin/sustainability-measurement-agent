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
        self._run_subprocess(self.config.trigger_command)

    def onSetup(self):
        if self.config.setup_command:
            self._run_subprocess(self.config.setup_command)

    def onTeardown(self):
        if self.config.teardown_command:
            self._run_subprocess(self.config.teardown_command)



    # --- PRIVATE METHODS

    def _run_subprocess(self, command: str, cancel: Optional[threading.Event] = None) -> int:
        log.info(f"Running subprocess command: {command}")

        # todo: cancel

        try:
            result = subprocess.run(
                shlex.split(command), 
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
    trigger_command: str
    setup_command: str
    teardown_command: str
    workdir: Path
    env = {k: v for k, v in os.environ.items() # todo
       if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "PYTHONHOME", "PYTHONPATH")}

    def validate(self) -> bool:
        assert(self.workdir.exists())
        return True

    @staticmethod
    def from_dict(config_yml: dict) -> "SubprocessRunnerConfig":
        config = {}
        config["trigger_command"] = config_yml.get("trigger_command")
        config["setup_command"] = config_yml.get("setup_command")
        config["teardown_command"] = config_yml.get("teardown_command")
        config["workdir"] = Path(config_yml["workdir"])
        return SubprocessRunnerConfig(**config)
