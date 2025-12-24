CREATE TABLE IF NOT EXISTS task_flames (
    task_id VARCHAR(64) PRIMARY KEY,
    model_name VARCHAR(128),
    dataset_name VARCHAR(128),
    start_time DATETIME,
    status VARCHAR(32)
); 