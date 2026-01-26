import requests
import base64

DEFAULT_URL = 'http://localhost:5123'

class TeleLocustClient:
    def __init__(self, telelocust_url=DEFAULT_URL):
        self.telelocust_url = telelocust_url
        self.token = None

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
        response = requests.get(f'{self.telelocust_url}/runs/{self.token}')
        response.raise_for_status()
        return response.json() 

    def is_finished(self):
        status = self.get_run_status()
        return status['status'] != 'running'

    def download_run_data(self, output_zip_path):

        if self.token is None:
            raise ValueError("No test run token available. Start a test run first.")
        
        if not self.is_finished():
            raise RuntimeError("Test run is still running. Cannot download data until it is finished.")

        response = requests.get(f'{self.telelocust_url}/runs/{self.token}/download')
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