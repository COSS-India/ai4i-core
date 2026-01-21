#!/bin/sh

# Generate demo certificates for OpenSearch RBAC testing
# This runs the demo installer inside a temporary container

set -e

echo "Generating OpenSearch demo certificates for RBAC testing..."

# Create certs directory
mkdir -p infrastructure/opensearch/certs

# Run demo installer in temporary container
docker run --rm \
    -v "$(pwd)/infrastructure/opensearch/certs:/certs" \
    opensearchproject/opensearch:2.11.0 \
    bash -c "
        # Copy installer script
        cp /usr/share/opensearch/plugins/opensearch-security/tools/install_demo_configuration.sh /tmp/
        chmod +x /tmp/install_demo_configuration.sh
        
        # Create minimal opensearch.yml for installer
        mkdir -p /usr/share/opensearch/config
        echo 'cluster.name: docker-cluster' > /usr/share/opensearch/config/opensearch.yml
        echo 'network.host: 0.0.0.0' >> /usr/share/opensearch/config/opensearch.yml
        echo 'discovery.type: single-node' >> /usr/share/opensearch/config/opensearch.yml
        
        # Run installer (non-interactive)
        /tmp/install_demo_configuration.sh -y -i -c
        
        # Copy certificates to mounted volume
        cp -r /usr/share/opensearch/config/certs/* /certs/ 2>/dev/null || true
    "

echo "✅ Certificates generated in infrastructure/opensearch/certs/"
ls -la infrastructure/opensearch/certs/

