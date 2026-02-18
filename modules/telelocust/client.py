import threading

import requests
import base64
import logging
import time

DEFAULT_URL = 'http://localhost:5123'
REQUEST_TIMEOUT = 10
WORKLOAD_POLLING_FREQUENCY_SECONDS = 1
POLLING_RETRIES = 5

log = logging.getLogger(__name__)


class TeleLocustClient:
    def __init__(self, telelocust_url=DEFAULT_URL):
        self.telelocust_url = telelocust_url
        self.token = None
        self.cancel = None
        # self.connection = requests.Session() # no use since telelocust doesn't currently support his

    def start_test_run(self, sut_host, users=10, spawn_rate=2, run_time='10s', locustfile_path=None):

        parameters = {
            'host': sut_host,
            'users': users,
            'spawn_rate': spawn_rate,
            'run_time': run_time,
        }

        if locustfile_path is not None:
            with open(locustfile_path, 'rb') as f:
                parameters['locustfile_base64'] = base64.b64encode(f.read()).decode('utf-8')


        response = requests.post(f'{self.telelocust_url}/runs/start', json=parameters)
        response.raise_for_status()
        self.token =  response.json()['token'] 
        return self.token

    def get_run_status(self):
        response = requests.get(f'{self.telelocust_url}/runs/{self.token}', timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json() 

    def wait_for_run_completion(self, cancel: threading.Event, polling_interval_seconds=WORKLOAD_POLLING_FREQUENCY_SECONDS, max_retries=POLLING_RETRIES):
        retries = 0
        self.cancel = cancel
        while not cancel.is_set():
            try:
                status = self.get_run_status()
                retries = 0  # reset retries after a successful request
            except (requests.exceptions.RequestException) as e: # e.g. timeout, connection error
                log.warning(f"Error while polling TeleLocust run status: {e}")
                if retries < POLLING_RETRIES:
                    log.warning(f"Retrying... ({retries + 1}/{POLLING_RETRIES})")
                    retries += 1
                    time.sleep(retries * polling_interval_seconds)
                    continue
                else:
                    log.error("Exceeded maximum retries while polling TeleLocust run status. Aborting.")
                    return
                    # raise RuntimeError("Failed to retrieve TeleLocust run status after multiple attempts.")

            log.info(f'Run status: {status}')
            if status['status'] != 'running':
                return status['status']

            time.sleep(polling_interval_seconds)

        return

    def abort_run(self):
        pass

    def is_finished(self):
        status = self.get_run_status()
        return status['status'] != 'running' or self.cancel.is_set()

    def download_run_data(self, output_zip_path):

        if self.token is None:
            raise ValueError("No test run token available. Start a test run first.")
        
        if not self.is_finished():
            raise RuntimeError("Test run is still running. Cannot download data until it is finished.")

        response = requests.get(f'{self.telelocust_url}/runs/{self.token}/download', timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        with open(output_zip_path, 'wb') as f:
            f.write(response.content)

if __name__ == '__main__':

    client = TeleLocustClient(DEFAULT_URL)

    client.start_test_run()
    print(f'Started test run with token: {client.token}')

    import time
    while True:
        status = client.get_run_status()
        print(f'Run status: {status}')
        if status['status'] != 'running':
            break
        time.sleep(1)
    print('Test run finished.')
    print(f'Final status: {status}')
    client.download_run_data(f"downloads/data_{client.token}.zip")