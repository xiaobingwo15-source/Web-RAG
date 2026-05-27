# SmartEdge IoT Platform — Technical Whitepaper

## Executive Summary

SmartEdge is IE Industrial Technology's flagship IoT platform designed for industrial manufacturing environments. It bridges the gap between legacy factory equipment and modern cloud analytics through an edge-first architecture that ensures reliability, low latency, and data sovereignty. This whitepaper covers the platform architecture, communication protocols, deployment models, and real-world performance benchmarks.

## 1. Architecture Overview

SmartEdge follows a three-tier architecture:

### Tier 1: Device Layer
- Industrial equipment (PLCs, CNC machines, robots, sensors) connect to SmartEdge via protocol adapters
- Supports 150+ industrial protocols including Modbus RTU/TCP, PROFINET, EtherNet/IP, EtherCAT, OPC-UA, MQTT, BACnet, and CC-Link
- Device SDK available for C, C++, Python, and Java for custom integrations

### Tier 2: Edge Layer
- SmartEdge Gateway (SE-Core, SE-Pro, or SE-Enterprise) runs on-premise
- Performs real-time data processing, filtering, aggregation, and local rule execution
- Edge AI inference using ONNX Runtime for anomaly detection and predictive models
- Stores 72 hours of buffered data for offline resilience
- Hardware options: DIN-rail industrial PC, rack-mount server, or VM/container deployment

### Tier 3: Cloud Layer
- SmartEdge Cloud provides centralized dashboards, historical analytics, and fleet management
- Multi-tenant SaaS hosted on Alibaba Cloud (China) and Azure (global)
- Data retention: 13 months standard, 5 years optional
- RESTful API and GraphQL for third-party integrations

## 2. Communication Protocols

### OPC-UA (IEC 62541)
- Native server and client implementation
- Supports Pub/Sub and client-server patterns
- Security policies: None, Basic128Rsa15, Basic256, Basic256Sha256
- Typical throughput: 10,000 messages/second per connection

### MQTT 3.1.1 / 5.0
- Broker: Embedded Mosquitto or external HiveMQ/EMQ X
- QoS levels 0, 1, 2 supported
- Retained messages and last-will testament
- Typical latency: <5ms within local network

### Modbus
- RTU (serial) and TCP variants
- Supports function codes 1–4 (read) and 5–6, 15–16 (write)
- Automatic byte-order detection (big-endian / little-endian)
- Polling rates configurable from 10ms to 60s

### RESTful API
- OpenAPI 3.0 specification
- OAuth 2.0 and API key authentication
- Rate limiting: 1000 requests/minute (SE-Pro), unlimited (SE-Enterprise)
- Webhook support for event-driven integrations

## 3. Edge AI Capabilities

SmartEdge Pro and Enterprise include an embedded inference engine:

- **Runtime**: ONNX Runtime 1.16 with DirectML (Windows) or TensorRT (Linux GPU)
- **Supported Models**: CNN, LSTM, Transformer (up to 500M parameters)
- **Use Cases**:
  - Vibration anomaly detection (bearing failure, imbalance, misalignment)
  - Visual defect detection (surface scratches, missing components, color deviation)
  - Process optimization (energy consumption, cycle time, yield prediction)
- **Performance**: 50ms inference latency on SE-Pro (Intel i7), 12ms on SE-Enterprise (NVIDIA T4)
- **Model Updates**: Over-the-air deployment with A/B testing and rollback support

## 4. Deployment Models

### On-Premise Only
- All data stays within the factory network
- Suitable for defense, aerospace, and regulated industries
- Requires local server infrastructure
- Cloud features available via VPN tunnel (optional)

### Hybrid (Recommended)
- Edge processing on-premise, analytics and dashboards in the cloud
- Data filtered and aggregated before upload (reduces bandwidth by 85%)
- Automatic failover: edge continues operating if cloud connection drops
- Most common deployment (72% of customers)

### Full Cloud
- Lightweight edge agent on existing hardware, heavy processing in cloud
- Suitable for small factories with limited IT infrastructure
- Lowest upfront cost, highest bandwidth requirement

## 5. Security Architecture

- **Device Authentication**: X.509 certificates with hardware TPM 2.0 storage
- **Data Encryption**: TLS 1.3 in transit, AES-256 at rest
- **Network Segmentation**: Micro-segmentation via SmartEdge firewall rules
- **Access Control**: Role-based (RBAC) with LDAP/Active Directory integration
- **Audit Logging**: All configuration changes and data access logged to immutable audit trail
- **Compliance**: IEC 62443 SL2 certified, SOC 2 Type II compliant

## 6. Performance Benchmarks

| Metric | SE-Core | SE-Pro | SE-Enterprise |
|--------|---------|--------|---------------|
| Max Devices | 50 | 500 | Unlimited |
| Data Ingestion Rate | 1,000 points/sec | 50,000 points/sec | 500,000 points/sec |
| Local Storage | 16 GB | 256 GB | 2 TB |
| Edge Inference | Not available | 50ms/prediction | 12ms/prediction |
| Uptime SLA | 99.5% | 99.9% | 99.99% |
| Failover Time | N/A | <30 seconds | <5 seconds |

## 7. Integration Ecosystem

SmartEdge integrates with major enterprise systems:

- **ERP**: SAP S/4HANA, Oracle Cloud ERP, Kingdee, Yonyou
- **MES**: Siemens Opcenter, Rockwell Plex, domestic MES platforms
- **Cloud**: Azure IoT Hub, AWS IoT Core, Alibaba Cloud IoT
- **BI**: Power BI, Tableau, Grafana (native plugin)
- **Ticketing**: ServiceNow, Jira Service Management
