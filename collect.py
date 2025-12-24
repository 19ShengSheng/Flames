import openai
import json
import time
import os

def initialize_openai(api_key, api_base):
    return openai.OpenAI(api_key=api_key, base_url=api_base)

# 定义一个函数来调用 GPT-3.5 API
def ask_gpt(prompt, client, model_name="gpt-3.5-turbo"):
    try:
        response = client.chat.completions.create(
            model=model_name,  # 使用指定的模型
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=500,  # 增加生成回答的最大长度，从150增加到500
            temperature=0.7,  # 设置生成回答的随机性
            top_p=1,# 控制生成文本的多样性
            frequency_penalty=0, # 减少重复词的生成
            presence_penalty=0# 减少重复句子或段落的生成
        )
        content = response.choices[0].message.content
        print(f"GPT响应长度: {len(content)} 字符")
        
        # 检查响应是否被截断（通常截断的响应会以不完整的句子结尾）
        if len(content) >= 490:  # 接近max_tokens限制
            print(f"[WARNING] 响应可能被截断，长度: {len(content)} 字符")
            # 可以在这里添加重试逻辑或警告
        elif len(content) < 10:  # 响应太短
            print(f"[WARNING] 响应可能不完整，长度: {len(content)} 字符")
        
        return content
    except Exception as e:
        print(f"Error processing prompt: {prompt}. Error: {e}")
        # 返回一个更明确的错误信息
        return f"Error: Unable to process - {str(e)}"

# def process_data(task_id, api_key, api_base, model_name, limit=5):
#     try:
#         client = initialize_openai(api_key, api_base)
#         input_file_path = f'data/Flames_1k_Chinese.jsonl'
#         output_file_path = f'data/Flames_{task_id}.jsonl'
        
#         results = []
#         count = 0
#         progress_data = {"total": 0, "processed": 0, "status": "processing"}
        
#         with open(input_file_path, 'r', encoding='utf-8') as f:
#             for line in f:
#                 if count >= limit:
#                     break
#                 entry = json.loads(line)
#                 prompt = entry["prompt"]
#                 answer = ask_gpt(prompt, client, model_name)
#                 entry["response"] = answer
#                 results.append(entry)
#                 count += 1
#                 progress_data["processed"] = count
#                 time.sleep(1)
        
#         with open(output_file_path, 'w', encoding='utf-8') as f:
#             for result in results:
#                 json.dump(result, f, ensure_ascii=False)
#                 f.write('\n')
        
#         progress_data["total"] = count
#         progress_data["status"] = "completed"
#         progress_data["output_file"] = output_file_path
        
#         return progress_data
    
#     except Exception as e:
#         return {"status": "error", "message": str(e)}

# 新增：流式处理并写入文件，同时yield每条响应
def stream_process_data(task_id, api_key, api_base, model_name, limit=5):
    client = initialize_openai(api_key, api_base)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    input_file_path = os.path.join(BASE_DIR, 'data/Flames_1k_Chinese.jsonl')
    output_file_path = os.path.join(BASE_DIR, f'data/Flames_{task_id}.jsonl')
    count = 0
    with open(input_file_path, 'r', encoding='utf-8') as fin, \
         open(output_file_path, 'w', encoding='utf-8') as fout:
        for line in fin:
            if count >= limit:
                break
            entry = json.loads(line)
            prompt = entry["prompt"]
            answer = ask_gpt(prompt, client, model_name)
            entry["response"] = answer
            
            # 安全写入JSON行
            try:
                json_line = json.dumps(entry, ensure_ascii=False) + '\n'
                fout.write(json_line)
                fout.flush()  # 立即刷新缓冲区，确保数据写入磁盘
                count += 1
                yield {'prompt': prompt, 'response': answer}
                time.sleep(1)
            except Exception as e:
                print(f"[ERROR] 写入第{count+1}条数据失败: {e}")
                # 继续处理下一条，不中断整个流程
                continue
