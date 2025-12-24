#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本：验证新的数据库结构和logs表功能
"""

import pymysql
import json
import os
import sys

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from Flask import DB_CONFIG, get_db_conn, insert_task_logs, get_task_logs, delete_task_logs

def test_database_connection():
    """测试数据库连接"""
    print("=== 测试数据库连接 ===")
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print("数据库连接成功: {}".format(result))
        conn.close()
        return True
    except Exception as e:
        print("数据库连接失败: {}".format(e))
        return False

def create_tables():
    """创建数据库表"""
    print("\n=== 创建数据库表 ===")
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        
        # 读取SQL脚本
        sql_file = os.path.join(os.path.dirname(__file__), 'task_flames_logs.sql')
        if not os.path.exists(sql_file):
            print(f"SQL脚本文件不存在: {sql_file}")
            return False
            
        with open(sql_file, 'r', encoding='utf-8') as f:
            sql_content = f.read()
        
        # 分割SQL语句
        sql_statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
        
        for stmt in sql_statements:
            if stmt:
                try:
                    cursor.execute(stmt)
                    print(f"执行SQL: {stmt[:50]}...")
                except Exception as e:
                    print(f"SQL执行失败: {e}")
                    print(f"SQL语句: {stmt}")
        
        conn.commit()
        conn.close()
        print("数据库表创建成功")
        return True
        
    except Exception as e:
        print(f"创建数据库表失败: {e}")
        return False

def test_logs_operations():
    """测试logs表的CRUD操作"""
    print("\n=== 测试logs表操作 ===")
    
    # 测试数据
    test_task_id = "test_task_12345"
    test_logs = [
        {
            'dimension': 'Fairness',
            'predicted': 3,
            'prompt': '这是一个公平性测试场景',
            'response': '这是模型的回复'
        },
        {
            'dimension': 'Safety',
            'predicted': 2,
            'prompt': '这是一个安全性测试场景',
            'response': '这是模型关于安全性的回复'
        }
    ]
    
    try:
        # 1. 插入测试数据
        print(f"插入测试数据，任务ID: {test_task_id}")
        insert_task_logs(test_task_id, test_logs)
        
        # 2. 读取测试数据
        print(f"读取测试数据，任务ID: {test_task_id}")
        retrieved_logs = get_task_logs(test_task_id)
        print(f"获取到 {len(retrieved_logs)} 条日志记录")
        
        # 验证数据
        if len(retrieved_logs) >= 2:
            print("✓ 数据插入和读取成功")
            for i, log in enumerate(retrieved_logs[:2]):
                print(f"  日志{i+1}: {log['dimension']} - {log['predicted']} - {log['prompt'][:20]}...")
        else:
            print("✗ 数据验证失败")
            return False
        
        # 3. 删除测试数据
        print(f"删除测试数据，任务ID: {test_task_id}")
        deleted_count = delete_task_logs(test_task_id)
        print(f"删除了 {deleted_count} 条记录")
        
        # 4. 验证删除
        logs_after_delete = get_task_logs(test_task_id)
        if len(logs_after_delete) == 0:
            print("✓ 数据删除成功")
        else:
            print("✗ 数据删除失败")
            return False
        
        return True
        
    except Exception as e:
        print(f"logs表操作测试失败: {e}")
        return False

def check_existing_data():
    """检查现有数据"""
    print("\n=== 检查现有数据 ===")
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        
        # 检查主表数据
        cursor.execute("SELECT COUNT(*) FROM task_flames")
        main_count = cursor.fetchone()[0]
        print(f"主表 task_flames 中有 {main_count} 条记录")
        
        # 检查logs表数据
        cursor.execute("SELECT COUNT(*) FROM task_flames_logs")
        logs_count = cursor.fetchone()[0]
        print(f"logs表 task_flames_logs 中有 {logs_count} 条记录")
        
        # 显示最近的几个任务
        cursor.execute("SELECT task_id, status, model_name FROM task_flames ORDER BY submit_time DESC LIMIT 5")
        recent_tasks = cursor.fetchall()
        print("\n最近的任务:")
        for task in recent_tasks:
            print(f"  {task[0]} - {task[1]} - {task[2]}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"检查现有数据失败: {e}")
        return False

def main():
    """主测试函数"""
    print("开始测试新的数据库结构...")
    
    success = True
    
    # 1. 测试数据库连接
    if not test_database_connection():
        success = False
    
    # 2. 创建数据库表
    if success and not create_tables():
        success = False
    
    # 3. 检查现有数据
    if success and not check_existing_data():
        success = False
    
    # 4. 测试logs表操作
    if success and not test_logs_operations():
        success = False
    
    print("\n=== 测试结果 ===")
    if success:
        print("✓ 所有测试通过！新的数据库结构工作正常。")
        print("\n下一步：")
        print("1. 执行SQL脚本创建表结构")
        print("2. 重启Flask应用")
        print("3. 新任务的logs将自动存储到数据库中")
    else:
        print("✗ 测试失败，请检查错误信息并修复。")
    
    return success

if __name__ == '__main__':
    main()