import pytest
import yaml

from modules.telelocust.main import TelelocustSmaModule, TelelocustConfig


def test_deploy():
    cnf = TelelocustConfig(
        sut_url="foobar",
        locustfile=__file__,
    )
    le_file = make_config_from_cnf(cnf)

    # Check if the deployment file contains no nodeSelector
    for doc in le_file:
        if doc['kind'] == 'Deployment':
            assert 'nodeSelector' not in doc['spec']['template']['spec']
            assert "ghcr.io/wolfkarl/telelocust" in doc['spec']['template']['spec']['containers'][0]['image']


    cnf.nodeSelector = ["kubernetes.io/arch=amd64","amazing=foo"]

    le_file = make_config_from_cnf(cnf)
    # Check if the deployment file contains the correct nodeSelector
    for doc in le_file:
        if doc['kind'] == 'Deployment':
            assert 'nodeSelector' in doc['spec']['template']['spec']
            assert doc['spec']['template']['spec']['nodeSelector'] == {
                "kubernetes.io/arch": "amd64",
                "amazing": "foo"
            }
    cnf.nodeSelector = None
    cnf.image = "myregistry/myimage:latest"
    le_file = make_config_from_cnf(cnf)
    for doc in le_file:
        if doc['kind'] == 'Deployment':
            assert "myregistry/myimage:latest" in doc['spec']['template']['spec']['containers'][0]['image']

    cnf.imagePullSecrets = "myregistrykey"
    le_file = make_config_from_cnf(cnf)
    for doc in le_file:
        if doc['kind'] == 'Deployment':
            assert "myregistrykey" in doc['spec']['template']['spec']['imagePullSecrets'][0]['name']




def make_config_from_cnf(cnf):
    tsm = TelelocustSmaModule(cnf.__dict__)

    deployment_file_path = tsm.prepare_deployment_file()

    le_file = []
    with open(deployment_file_path, 'r') as f:
        le_file = yaml.safe_load_all(f.read())
    return le_file
