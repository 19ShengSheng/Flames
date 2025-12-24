#!/usr/bin/env python3
"""
测试数据集选择逻辑的脚本
"""

def get_dataset_file_by_id(dataset_id):
    """根据dataset_id选择对应的数据集文件"""
    # dataset_id为10、12、14时使用Flames_1k_Chinese.jsonl
    # dataset_id为20、21、22时使用Flames_5_Chinese.jsonl
    if dataset_id in [10, 12, 14]:
        return "data/Flames_1k_Chinese.jsonl"
    elif dataset_id in [20, 21, 22]:
        return "data/Flames_5_Chinese.jsonl"
    else:
        # 默认使用Flames_1k_Chinese.jsonl
        return "data/Flames_1k_Chinese.jsonl"

# 测试不同dataset_id的选择结果
test_cases = [10, 12, 14, 20, 21, 22, 99]

print("测试数据集选择逻辑:")
print("-" * 40)
for dataset_id in test_cases:
    selected_file = get_dataset_file_by_id(dataset_id)
    print(f"dataset_id: {dataset_id:2d} -> {selected_file}")

print("\n预期结果:")
print("dataset_id: 10, 12, 14 -> data/Flames_1k_Chinese.jsonl")
print("dataset_id: 20, 21, 22 -> data/Flames_5_Chinese.jsonl")
print("其他dataset_id -> data/Flames_1k_Chinese.jsonl (默认)")