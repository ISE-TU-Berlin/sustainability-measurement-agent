"""
1. Deploy Container
2. Start Workload
3. Retrieve Results
4. Teardown
"""


import logging
import kubernetes
import yaml

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

kubernetes.config.load_kube_config()

class LocustRunner:

    def __init__(self):
        self.namespace = "locust"
        self.k8s_client = kubernetes.client.AppsV1Api()

    def deploy_container(self):
        # Code to deploy the container
        # deployment, service = yaml.safe_load_all(
        #     open('locust-runner/locust-deployment.yaml'))
        # logger.info(
        #     f"Deploying Locust container to Kubernetes cluster with body: {deployment}")
        # self.k8s_client.create_namespaced_deployment(
        #     namespace=self.namespace, body=deployment)
        kubernetes.utils.create_from_yaml(
            kubernetes.client.ApiClient(),
            'locust-runner/locust-deployment.yaml',
            namespace=self.namespace
        )



    def start_workload(self):
        # Code to start the workload
        pass

    def retrieve_results(self):
        # Code to retrieve results
        pass

    def teardown(self):
        # Code to teardown the setup
        pass


if __name__ == "__main__":
    print(kubernetes.config.list_kube_config_contexts())
    runner = LocustRunner()
    runner.deploy_container()
    runner.start_workload()
    runner.retrieve_results()
    runner.teardown()
