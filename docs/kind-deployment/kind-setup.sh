#! /bin/sh

kind create cluster --name kind-cluster --config kind-config.yaml

helm install prometheus prometheus-community/kube-prometheus-stack \
    --namespace monitoring \
    --create-namespace \
    --set prometheus.prometheusSpec.scrapeInterval=5s \
    --set prometheus.prometheusSpec.scrapeTimeout=1s \
    --set prometheus.service.nodePort=30990 \
    --set prometheus.service.type=NodePort \
    --set grafana.service.nodePort=30989 \
    --set grafana.service.type=NodePort \
    --wait

helm install kepler kepler/kepler \
    --namespace kepler \
    --create-namespace \
    --set serviceMonitor.enabled=true \
    --set serviceMonitor.labels.release=prometheus

helm upgrade --install metrics-server metrics-server/metrics-server --set args="{--kubelet-insecure-tls}" -n kube-system

