BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE datasets (
    id VARCHAR(36) NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    description TEXT NOT NULL, 
    created_at VARCHAR(32) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (name)
);

CREATE TABLE sources (
    id VARCHAR(36) NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    latitude FLOAT NOT NULL, 
    longitude FLOAT NOT NULL, 
    baseline_speed FLOAT NOT NULL, 
    created_at VARCHAR(32) NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE events (
    id VARCHAR(36) NOT NULL, 
    source_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(40) NOT NULL, 
    severity VARCHAR(20) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    confidence FLOAT, 
    description TEXT NOT NULL, 
    origin VARCHAR(20) NOT NULL, 
    image_id VARCHAR(36), 
    created_at VARCHAR(32) NOT NULL, 
    updated_at VARCHAR(32) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(source_id) REFERENCES sources (id)
);

CREATE INDEX ix_events_created_at ON events (created_at);

CREATE INDEX ix_events_source_kind_time ON events (source_id, kind, created_at);

CREATE INDEX ix_events_status ON events (status);

CREATE TABLE images (
    id VARCHAR(36) NOT NULL, 
    dataset_id VARCHAR(36), 
    filename VARCHAR(200) NOT NULL, 
    width INTEGER NOT NULL, 
    height INTEGER NOT NULL, 
    split VARCHAR(10) NOT NULL, 
    annotations JSON NOT NULL, 
    created_at VARCHAR(32) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(dataset_id) REFERENCES datasets (id)
);

CREATE TABLE metrics (
    id VARCHAR(36) NOT NULL, 
    source_id VARCHAR(36) NOT NULL, 
    observed_at VARCHAR(32) NOT NULL, 
    speed FLOAT NOT NULL, 
    congestion FLOAT NOT NULL, 
    volume INTEGER NOT NULL, 
    anomaly BOOLEAN NOT NULL, 
    score FLOAT NOT NULL, 
    baseline FLOAT NOT NULL, 
    reason TEXT NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(source_id) REFERENCES sources (id), 
    UNIQUE (source_id, observed_at)
);

CREATE INDEX ix_metrics_source_time ON metrics (source_id, observed_at);

CREATE TABLE event_actions (
    id VARCHAR(36) NOT NULL, 
    event_id VARCHAR(36) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    note TEXT NOT NULL, 
    created_at VARCHAR(32) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(event_id) REFERENCES events (id)
);

CREATE INDEX ix_event_actions_event_id ON event_actions (event_id);

CREATE TABLE jobs (
    id VARCHAR(36) NOT NULL, 
    source_id VARCHAR(36) NOT NULL, 
    image_id VARCHAR(36) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    result JSON, 
    error TEXT, 
    attempts INTEGER NOT NULL, 
    lease_token VARCHAR(36), 
    lease_until VARCHAR(32), 
    created_at VARCHAR(32) NOT NULL, 
    updated_at VARCHAR(32) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(image_id) REFERENCES images (id), 
    FOREIGN KEY(source_id) REFERENCES sources (id)
);

CREATE INDEX ix_jobs_status ON jobs (status);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

