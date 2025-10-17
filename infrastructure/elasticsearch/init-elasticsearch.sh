#!/bin/bash

# Initialize Elasticsearch with indices, mappings, and lifecycle policies
# This script is executed when the Elasticsearch container starts

set -e

echo "Starting Elasticsearch initialization..."

# Wait for Elasticsearch to be ready
echo "Waiting for Elasticsearch to be ready..."
until curl -f -u "${ELASTIC_USERNAME:-elastic}:${ELASTIC_PASSWORD:-elastic_secure_password_2024}" http://localhost:9200/_cluster/health; do
    echo "Elasticsearch is not ready yet, waiting..."
    sleep 5
done

echo "Elasticsearch is ready, starting initialization..."

# Set environment variables
ELASTICSEARCH_URL="http://localhost:9200"
ELASTIC_USERNAME="${ELASTIC_USERNAME:-elastic}"
ELASTIC_PASSWORD="${ELASTIC_PASSWORD:-elastic_secure_password_2024}"

# Create index template for logs
echo "Creating index template for logs..."
curl -X PUT "$ELASTICSEARCH_URL/_index_template/logs_template" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{
        "index_patterns": ["logs-*"],
        "template": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "index.lifecycle.name": "logs-policy",
                "index.lifecycle.rollover_alias": "logs"
            },
            "mappings": {
                "properties": {
                    "timestamp": {
                        "type": "date"
                    },
                    "level": {
                        "type": "keyword"
                    },
                    "message": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "service": {
                        "type": "keyword"
                    },
                    "environment": {
                        "type": "keyword"
                    },
                    "correlation_id": {
                        "type": "keyword"
                    },
                    "metadata": {
                        "type": "object"
                    }
                }
            }
        }
    }' || echo "Logs template already exists"

# Create index template for traces
echo "Creating index template for traces..."
curl -X PUT "$ELASTICSEARCH_URL/_index_template/traces_template" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{
        "index_patterns": ["traces-*"],
        "template": {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "index.lifecycle.name": "traces-policy",
                "index.lifecycle.rollover_alias": "traces"
            },
            "mappings": {
                "properties": {
                    "timestamp": {
                        "type": "date"
                    },
                    "trace_id": {
                        "type": "keyword"
                    },
                    "span_id": {
                        "type": "keyword"
                    },
                    "parent_span_id": {
                        "type": "keyword"
                    },
                    "service_name": {
                        "type": "keyword"
                    },
                    "operation_name": {
                        "type": "keyword"
                    },
                    "duration": {
                        "type": "float"
                    },
                    "status": {
                        "type": "keyword"
                    },
                    "tags": {
                        "type": "object"
                    }
                }
            }
        }
    }' || echo "Traces template already exists"

# Create lifecycle policy for logs
echo "Creating lifecycle policy for logs..."
curl -X PUT "$ELASTICSEARCH_URL/_ilm/policy/logs-policy" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{
        "policy": {
            "phases": {
                "hot": {
                    "actions": {
                        "rollover": {
                            "max_size": "50GB",
                            "max_age": "30d"
                        }
                    }
                },
                "delete": {
                    "min_age": "90d"
                }
            }
        }
    }' || echo "Logs lifecycle policy already exists"

# Create lifecycle policy for traces
echo "Creating lifecycle policy for traces..."
curl -X PUT "$ELASTICSEARCH_URL/_ilm/policy/traces-policy" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{
        "policy": {
            "phases": {
                "hot": {
                    "actions": {
                        "rollover": {
                            "max_size": "10GB",
                            "max_age": "7d"
                        }
                    }
                },
                "delete": {
                    "min_age": "30d"
                }
            }
        }
    }' || echo "Traces lifecycle policy already exists"

# Create initial indices
echo "Creating initial indices..."

# Create logs index
curl -X PUT "$ELASTICSEARCH_URL/logs-000001" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{
        "aliases": {
            "logs": {
                "is_write_index": true
            }
        }
    }' || echo "Logs index already exists"

# Create traces index
curl -X PUT "$ELASTICSEARCH_URL/traces-000001" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{
        "aliases": {
            "traces": {
                "is_write_index": true
            }
        }
    }' || echo "Traces index already exists"

# Create index aliases for easy querying
echo "Creating index aliases..."

# Logs alias
curl -X PUT "$ELASTICSEARCH_URL/_alias/logs" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{
        "actions": [
            {
                "add": {
                    "index": "logs-*",
                    "alias": "logs"
                }
            }
        ]
    }' || echo "Logs alias already exists"

# Traces alias
curl -X PUT "$ELASTICSEARCH_URL/_alias/traces" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{
        "actions": [
            {
                "add": {
                    "index": "traces-*",
                    "alias": "traces"
                }
            }
        ]
    }' || echo "Traces alias already exists"

# Configure index settings for optimal performance
echo "Configuring index settings..."

# Configure logs index settings
curl -X PUT "$ELASTICSEARCH_URL/logs-*/_settings" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "refresh_interval": "30s"
        }
    }' || echo "Logs index settings already configured"

# Configure traces index settings
curl -X PUT "$ELASTICSEARCH_URL/traces-*/_settings" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    -d '{
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "refresh_interval": "30s"
        }
    }' || echo "Traces index settings already configured"

echo "Elasticsearch initialization completed successfully!"

# Test the setup
echo "Testing Elasticsearch setup..."
curl -X GET "$ELASTICSEARCH_URL/_cat/indices?v" \
    -u "$ELASTIC_USERNAME:$ELASTIC_PASSWORD" \
    || echo "Failed to test Elasticsearch setup"

echo "Elasticsearch is ready for use!"
