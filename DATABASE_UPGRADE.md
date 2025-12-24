# Flames系统数据库升级说明

## 概述
本系统已升级为使用分表存储方案（方案3），将logs数据从主表的result字段中分离出来，存储到专门的`task_flames_logs`表中。

## 数据库结构变更

### 1. 新增表：task_flames_logs
```sql
CREATE TABLE IF NOT EXISTS task_flames_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    dimension VARCHAR(32) NOT NULL,
    predicted INT,
    prompt TEXT,
    response TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_task_id (task_id),
    INDEX idx_dimension (dimension)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 2. 主表字段更新
task_flames表新增以下字段（如果不存在）：
- `dataset_id` INT
- `submit_time` DATETIME  
- `end_time` DATETIME
- `result` JSON

## 代码变更

### 1. 新增数据库操作函数
- `insert_task_logs(task_id, logs)` - 批量插入日志数据
- `get_task_logs(task_id, limit_per_dimension=10)` - 获取任务日志
- `delete_task_logs(task_id)` - 删除任务日志

### 2. 接口变更
- `flames_report` - 从数据库logs表读取数据
- `download_flames_report` - 从数据库logs表读取数据
- `download_flames_logs` - 从数据库logs表读取数据

### 3. 任务处理变更
- `run_task_algorithm` - 任务完成时自动将logs插入数据库

## 部署步骤

### 1. 执行数据库升级
```bash
cd /path/to/Flames
python3 simple_db_test.py
```

### 2. 重启Flask应用
```bash
# 停止当前应用
pkill -f Flask.py

# 启动新应用
python3 Flask.py
```

### 3. 验证部署
1. 创建新任务并等待完成
2. 检查`task_flames_logs`表中是否有数据
3. 测试报告下载功能

## 优势

### 1. 性能提升
- 主表轻量化，查询性能更好
- logs数据独立存储，避免大字段影响查询
- 支持按维度索引查询

### 2. 扩展性
- 支持大量任务存储
- 便于数据分析和统计
- 易于数据备份和迁移

### 3. 维护性
- 数据结构更清晰
- 支持独立的数据清理策略
- 便于监控和优化

## 兼容性说明

### 1. 向后兼容
- 现有文件系统存储的logs仍可作为备用
- API接口保持不变
- 支持渐进式迁移

### 2. 数据迁移
- 新任务自动使用新的存储方式
- 老任务数据可选择性迁移
- 支持混合模式运行

## 监控建议

### 1. 数据库监控
```sql
-- 检查logs表大小
SELECT table_name, table_rows, data_length, index_length 
FROM information_schema.tables 
WHERE table_schema = 'redteam-dra' AND table_name = 'task_flames_logs';

-- 检查任务分布
SELECT task_id, COUNT(*) as log_count 
FROM task_flames_logs 
GROUP BY task_id 
ORDER BY log_count DESC;
```

### 2. 清理策略
建议定期清理过期任务的logs数据：
```sql
-- 删除30天前已完成任务的logs
DELETE l FROM task_flames_logs l
JOIN task_flames t ON l.task_id = t.task_id
WHERE t.status = 'completed' 
AND t.end_time < DATE_SUB(NOW(), INTERVAL 30 DAY);
```

## 故障处理

### 1. 如果logs表查询失败
系统会自动回退到文件系统读取，确保服务不中断。

### 2. 如果数据库插入失败
任务状态仍会正常更新，仅logs数据可能缺失，不影响核心功能。

### 3. 性能问题
如遇到性能问题，可考虑：
- 添加更多索引
- 实施数据分区
- 使用读写分离

## 联系支持
如有问题，请查看应用日志或联系技术支持。