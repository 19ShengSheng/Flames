#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pymysql
import json
import os
import sys

# 数据库配置
DB_CONFIG = {
    'host': 'dbconn.sealosbja.site',
    'port': 31247,
    'user': 'root',
    'password': '6xgvj9jx',
    'db': 'redteam-dra',
    'charset': 'utf8mb4'
}

def get_db_conn():
    return pymysql.connect(**DB_CONFIG)

def test_database_connection():
    print("=== 测试数据库连接 ===")
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print("数据库连接成功: " + str(result))
        conn.close()
        return True
    except Exception as e:
        print("数据库连接失败: " + str(e))
        return False

def create_tables():
    print("\n=== 创建数据库表 ===")
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        
        # 创建logs表
        sql = """
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        cursor.execute(sql)
        print("创建 task_flames_logs 表成功")
        
        # 更新主表字段（如果不存在）
        try:
            cursor.execute("ALTER TABLE task_flames ADD COLUMN IF NOT EXISTS dataset_id INT")
            cursor.execute("ALTER TABLE task_flames ADD COLUMN IF NOT EXISTS submit_time DATETIME")
            cursor.execute("ALTER TABLE task_flames ADD COLUMN IF NOT EXISTS end_time DATETIME")
            cursor.execute("ALTER TABLE task_flames ADD COLUMN IF NOT EXISTS result JSON")
            print("更新 task_flames 表字段成功")
        except Exception as e:
            print("更新字段时出现警告（可能已存在）: " + str(e))
        
        conn.commit()
        conn.close()
        print("数据库表创建完成")
        return True
        
    except Exception as e:
        print("创建数据库表失败: " + str(e))
        return False

def check_tables():
    print("\n=== 检查表结构 ===")
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        
        # 检查主表
        cursor.execute("SHOW TABLES LIKE 'task_flames'")
        main_table = cursor.fetchone()
        if main_table:
            print("✓ task_flames 表存在")
        else:
            print("✗ task_flames 表不存在")
        
        # 检查logs表
        cursor.execute("SHOW TABLES LIKE 'task_flames_logs'")
        logs_table = cursor.fetchone()
        if logs_table:
            print("✓ task_flames_logs 表存在")
            
            # 检查表结构
            cursor.execute("DESCRIBE task_flames_logs")
            columns = cursor.fetchall()
            print("表结构:")
            for col in columns:
                print("  " + col[0] + " - " + col[1])
        else:
            print("✗ task_flames_logs 表不存在")
        
        conn.close()
        return True
        
    except Exception as e:
        print("检查表结构失败: " + str(e))
        return False

def main():
    print("开始测试新的数据库结构...")
    
    success = True
    
    # 1. 测试数据库连接
    if not test_database_connection():
        success = False
    
    # 2. 创建数据库表
    if success and not create_tables():
        success = False
    
    # 3. 检查表结构
    if success and not check_tables():
        success = False
    
    print("\n=== 测试结果 ===")
    if success:
        print("✓ 数据库结构设置成功！")
        print("\n下一步操作:")
        print("1. 重启Flask应用")
        print("2. 新任务的logs将自动存储到task_flames_logs表中")
        print("3. 查询接口将从数据库读取logs数据")
    else:
        print("✗ 设置失败，请检查错误信息")
    
    return success

if __name__ == '__main__':
    main()