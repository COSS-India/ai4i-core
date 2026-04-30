-- Alerting Service Database Schema
-- Connect to alerting_db and create tables for alerting and notifications

\c alerting_db;

-- Alert rules table
CREATE TABLE IF NOT EXISTS alert_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    metric_name VARCHAR(255) NOT NULL,
    threshold DECIMAL(15,6) NOT NULL,
    operator VARCHAR(10) NOT NULL, -- 'gt', 'lt', 'eq', 'gte', 'lte'
    severity VARCHAR(20) NOT NULL, -- 'low', 'medium', 'high', 'critical'
    evaluation_window INTEGER DEFAULT 300, -- in seconds
    notification_channels TEXT[], -- Array of notification channel configurations
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100)
);

-- Alerts table
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER REFERENCES alert_rules(id) ON DELETE CASCADE,
    metric_name VARCHAR(255) NOT NULL,
    current_value DECIMAL(15,6) NOT NULL,
    threshold DECIMAL(15,6) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    status VARCHAR(20) DEFAULT 'firing', -- 'firing', 'resolved', 'acknowledged'
    fired_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    acknowledged_by VARCHAR(100)
);

-- Notification history table
CREATE TABLE IF NOT EXISTS notification_history (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE CASCADE,
    channel VARCHAR(50) NOT NULL, -- 'email', 'slack', 'sms', 'webhook'
    recipient VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL, -- 'sent', 'failed', 'pending'
    sent_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT
);

-- Escalation policies table
CREATE TABLE IF NOT EXISTS escalation_policies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    rules JSONB NOT NULL, -- Escalation rules configuration
    schedule JSONB, -- Schedule configuration for on-call rotation
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Anomaly detection models table
CREATE TABLE IF NOT EXISTS anomaly_detection_models (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(255) NOT NULL,
    model_type VARCHAR(50) NOT NULL, -- 'isolation_forest', 'statistical', 'ml'
    model_parameters JSONB NOT NULL,
    training_data_size INTEGER NOT NULL,
    last_trained_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    accuracy_score DECIMAL(5,4), -- 0.0000 to 1.0000
    is_active BOOLEAN DEFAULT true
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_alert_rules_name ON alert_rules(name);
CREATE INDEX IF NOT EXISTS idx_alert_rules_metric_name ON alert_rules(metric_name);
CREATE INDEX IF NOT EXISTS idx_alert_rules_active ON alert_rules(is_active);
CREATE INDEX IF NOT EXISTS idx_alerts_rule_id ON alerts(rule_id);
CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_alerts_fired_at ON alerts(fired_at);
CREATE INDEX IF NOT EXISTS idx_alerts_metric_name ON alerts(metric_name);
CREATE INDEX IF NOT EXISTS idx_alerts_rule_status ON alerts(rule_id, status);
CREATE INDEX IF NOT EXISTS idx_notification_history_alert_id ON notification_history(alert_id);
CREATE INDEX IF NOT EXISTS idx_notification_history_sent_at ON notification_history(sent_at);
CREATE INDEX IF NOT EXISTS idx_notification_history_status ON notification_history(status);
CREATE INDEX IF NOT EXISTS idx_escalation_policies_name ON escalation_policies(name);
CREATE INDEX IF NOT EXISTS idx_anomaly_models_metric_name ON anomaly_detection_models(metric_name);
CREATE INDEX IF NOT EXISTS idx_anomaly_models_active ON anomaly_detection_models(is_active);
CREATE INDEX IF NOT EXISTS idx_anomaly_models_last_trained ON anomaly_detection_models(last_trained_at);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at columns
CREATE TRIGGER update_alert_rules_updated_at BEFORE UPDATE ON alert_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_escalation_policies_updated_at BEFORE UPDATE ON escalation_policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create a function to resolve alerts
CREATE OR REPLACE FUNCTION resolve_alert(alert_id integer, resolved_by varchar(100))
RETURNS void AS $$
BEGIN
    UPDATE alerts 
    SET status = 'resolved',
        resolved_at = CURRENT_TIMESTAMP
    WHERE id = alert_id AND status = 'firing';
END;
$$ LANGUAGE plpgsql;

-- Create a function to acknowledge alerts
CREATE OR REPLACE FUNCTION acknowledge_alert(alert_id integer, acknowledged_by varchar(100))
RETURNS void AS $$
BEGIN
    UPDATE alerts 
    SET status = 'acknowledged',
        acknowledged_at = CURRENT_TIMESTAMP,
        acknowledged_by = acknowledge_alert.acknowledged_by
    WHERE id = alert_id AND status = 'firing';
END;
$$ LANGUAGE plpgsql;

-- Create a function to clean up old alert data
CREATE OR REPLACE FUNCTION cleanup_old_alert_data(retention_days integer DEFAULT 90)
RETURNS void AS $$
BEGIN
    -- Delete old resolved alerts
    DELETE FROM alerts 
    WHERE status = 'resolved' 
    AND resolved_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
    
    -- Delete old notification history
    DELETE FROM notification_history 
    WHERE sent_at < CURRENT_TIMESTAMP - INTERVAL '1 day' * retention_days;
END;
$$ LANGUAGE plpgsql;
