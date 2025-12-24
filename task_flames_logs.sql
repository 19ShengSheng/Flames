-- 创建Flames任务日志表
CREATE TABLE IF NOT EXISTS task_flames_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    dimension VARCHAR(32) NOT NULL,
    predicted INT,
    prompt TEXT,
    response TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_task_id (task_id),
    INDEX idx_dimension (dimension),
    FOREIGN KEY (task_id) REFERENCES task_flames(task_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 更新主表，添加缺失的字段（如果不存在）
ALTER TABLE task_flames 
ADD COLUMN IF NOT EXISTS dataset_id INT,
ADD COLUMN IF NOT EXISTS submit_time DATETIME,
ADD COLUMN IF NOT EXISTS end_time DATETIME,
ADD COLUMN IF NOT EXISTS result JSON;