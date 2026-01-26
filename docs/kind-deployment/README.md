# Setting up a testing cluster with kind

- [ ] Install kind
- [ ] Create Cluster

```shell
kind create cluster --name smac
```

- [ ] Install Prometheues with Helm

[Deploy using Helm Chart - Kepler](https://sustainable-computing.io/archive/installation/kepler-helm/)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
    --namespace monitoring \
    --create-namespace \
    --set prometheus.prometheusSpec.scrapeInterval=5s \
    --set prometheus.prometheusSpec.scrapeTimeout=1s \
    --set prometheus.service.nodePort=30990 \
    --set prometheus.service.type=NodePort \
    --set grafana.service.nodePort=30930 \
    --set grafana.service.type=NodePort \
    # --set alertmanager.service.nodePort=32000 \
    # --set alertmanager.service.type=NodePort \
    # --set prometheus-node-exporter.service.nodePort=32001 \
    # --set prometheus-node-exporter.service.type=NodePort
    --wait
```

- [ ] Install Kepler with Helm

```sh
helm repo add kepler https://sustainable-computing-io.github.io/kepler-helm-chart
helm repo update

helm install kepler kepler/kepler \
    --namespace kepler \
    --create-namespace \
    --set serviceMonitor.enabled=true \
    --set serviceMonitor.labels.release=prometheus 
```

- [ ] Install Metrics Server

```shell
helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/
helm upgrade --install metrics-server metrics-server/metrics-server --set args="{--kubelet-insecure-tls}" -n kube-system
```

- [ ] ~~Forward Prometheus to localhost:9090~~
- [ ] Run SMA with the kind example config

```shell
python main_fancy.py examples/kind.yml
```


## Run some test containers

These will run indefintely until you stop them with Ctrl C

#### Idle

```sh
kubectl create namespace suo --dry-run=client -o yaml | kubectl apply -f - && kubectl run idle-test --namespace=suo --image=busybox --restart=Never --rm -it -- sleep infinity
```

#### Stress

```sh
kubectl create namespace sudo --dry-run=client -o yaml | kubectl apply -f - && kubectl run stress-test --namespace=suo --image=progrium/stress --restart=Never --rm -it -- --cpu 2 --io 1 --vm 2 --vm-bytes 128M
```


## Adapt Scrape interval using helm if necessary 

> [!WARNING]
> This will redeploy and may remove e.g. Grafana Dashboards

```sh
helm upgrade prometheus prometheus-community/kube-prometheus-stack -n monitoring --reuse-values --set prometheus.prometheusSpec.scrapeInterval=5s --set prometheus.prometheusSpec.scrapeTimeout=1s
```