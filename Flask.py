from flask import Flask, request, Response, stream_with_context, jsonify
import os,io,time,threading,datetime,ast,uuid,pymysql,json,tempfile,subprocess,shutil
from infer import run_inference_and_score
from argparse import Namespace
from flask import send_file
from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
os.environ['HF_HUB_DISABLE_INPUT'] = '1'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
from flask_cors import CORS
CORS(app)

# API 配置缓存：临时存储任务的 API 信息
API_CONFIG_CACHE = {}
import time

def store_api_config(task_id, api_key, base_url):
    """临时存储 API 配置信息"""
    API_CONFIG_CACHE[str(task_id)] = {
        'api_key': api_key,
        'base_url': base_url,
        'timestamp': time.time()
    }
    print(f"[CACHE] 已存储任务 {task_id} 的 API 配置信息")

def get_api_config(task_id):
    """获取 API 配置信息"""
    config = API_CONFIG_CACHE.get(str(task_id))
    if config:
        # 检查是否过期（24小时）
        if time.time() - config['timestamp'] < 86400:
            return config
        else:
            # 过期则删除
            del API_CONFIG_CACHE[str(task_id)]
            print(f"[CACHE] 任务 {task_id} 的 API 配置已过期，已清理")
    return None

def cleanup_api_config(task_id):
    """清理 API 配置信息"""
    if str(task_id) in API_CONFIG_CACHE:
        del API_CONFIG_CACHE[str(task_id)]
        print(f"[CACHE] 已清理任务 {task_id} 的 API 配置信息")

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

def get_dataset_file_by_id(dataset_id):
    """根据dataset_id选择对应的数据集文件"""
    # dataset_id为10、12、14时使用Flames_1k_Chinese.jsonl
    # dataset_id为20、21、22时使用Flames_5_Chinese.jsonl
    if dataset_id==10:
        return os.path.join(BASE_DIR, "data/Flames_1k_Chinese.jsonl")
    elif dataset_id==20:
        return os.path.join(BASE_DIR, "data/Flames_5_Chinese.jsonl")
    else:
        # 默认使用Flames_1k_Chinese.jsonl
        return os.path.join(BASE_DIR, "data/Flames_1k_Chinese.jsonl")

def insert_task_to_db(task_id, model_name, dataset_id, submit_time, status, end_time=None, result=None):
    # status参数保留，实际创建任务时应传入'pending'
    conn = get_db_conn()
    cursor = conn.cursor()
    sql = """
    INSERT INTO task_flames (task_id, model_name, dataset_id, submit_time, status, end_time, result)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE status=VALUES(status), submit_time=VALUES(submit_time), end_time=VALUES(end_time), result=VALUES(result)
    """
    cursor.execute(sql, (str(task_id), model_name, dataset_id, submit_time, status, end_time, result))
    conn.commit()
    conn.close()

# 新增：获取最早的pending任务（加锁防止并发）
def fetch_next_pending_task():
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        
        # 获取第一个pending任务
        sql = "SELECT task_id, model_name, dataset_id, submit_time FROM task_flames WHERE status='pending' ORDER BY submit_time ASC LIMIT 1"
        cursor.execute(sql)
        row = cursor.fetchone()
        conn.close()
        
        return row
    except Exception as e:
        print(f"[ERROR] 获取pending任务失败: {e}")
        import traceback
        traceback.print_exc()
        return None

# 新增：设置任务状态
def set_task_status(task_id, status, end_time=None):
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        if end_time:
            cursor.execute("UPDATE task_flames SET status=%s, end_time=%s WHERE task_id=%s", (status, end_time, str(task_id)))
        else:
            cursor.execute("UPDATE task_flames SET status=%s WHERE task_id=%s", (status, str(task_id)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] 更新任务状态失败: {task_id} -> {status}, 错误: {e}")
        raise

# 新增：检查是否有running任务
def has_running_task():
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM task_flames WHERE status='running'")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        print(f"[ERROR] 检查running任务失败: {e}")
        return 0

# 新增：算法执行线程
def run_task_algorithm(task_id, model_name, dataset_id):
    try:
        print(f"[TASK] 开始执行任务: {task_id} (模型: {model_name}, 数据集: {dataset_id})")
        
        # 从缓存获取 API 配置
        api_config = get_api_config(task_id)
        if not api_config:
            raise Exception(f"未找到任务 {task_id} 的 API 配置信息")
        
        # 根据dataset_id选择数据集文件
        dataset_file = get_dataset_file_by_id(int(dataset_id))
        print(f"[TASK] 使用数据集文件: {dataset_file}")
        
        # 创建任务专用的数据文件副本
        task_data_file = os.path.join(BASE_DIR, f"data/Flames_{task_id}.jsonl")
        if os.path.exists(dataset_file):
            import shutil
            shutil.copy2(dataset_file, task_data_file)
            print(f"[TASK] 已复制数据集文件: {dataset_file} -> {task_data_file}")
        else:
            raise Exception(f"数据集文件不存在: {dataset_file}")
        
        from argparse import Namespace
        args = Namespace(
            data_path=task_data_file,
            max_length=512,
            val_bsz_per_gpu=16,
            base_url=api_config['base_url'],
            api_key=api_config['api_key'],
            model_name=model_name
        )
        for _ in run_inference_and_score(args):
            pass  # 这里只需执行算法，结果文件由算法写入
        
        # 任务完成后清理 API 配置
        cleanup_api_config(task_id)
        set_task_status(task_id, 'completed', end_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        print(f"[TASK] 任务完成: {task_id}")
    except Exception as e:
        print(f"[TASK] 任务失败: {task_id}, 错误: {e}")
        # 即使失败也要清理 API 配置
        cleanup_api_config(task_id)
        set_task_status(task_id, 'failed', end_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

# 新增：调度线程
def task_scheduler_loop():
    print("[SCHEDULER] 调度线程启动")
    last_running_count = 0
    last_pending_count = 0
    
    while True:
        try:
            # 检查running任务数量
            running_count = has_running_task()
            
            # 检查pending任务数量
            try:
                conn = get_db_conn()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM task_flames WHERE status='pending'")
                pending_count = cursor.fetchone()[0]
                conn.close()
            except Exception as e:
                print(f"[ERROR] 检查pending任务失败: {e}")
                pending_count = 0
            
            # 只在任务数量变化时输出日志
            if running_count != last_running_count or pending_count != last_pending_count:
                print(f"[SCHEDULER] 任务状态变化 - running: {running_count}, pending: {pending_count}")
                last_running_count = running_count
                last_pending_count = pending_count
            
            if not running_count and pending_count > 0:
                # 只有在没有running任务且有pending任务时才执行详细检查
                row = fetch_next_pending_task()
                if row:
                    task_id, model_name, dataset_id, submit_time = row
                    print(f"[SCHEDULER] 开始处理pending任务: {task_id}")
                    
                    # 检查是否有 API 配置信息
                    api_config = get_api_config(task_id)
                    if not api_config:
                        print(f"[ERROR] 未找到任务 {task_id} 的 API 配置信息，跳过执行")
                        # 将任务状态设为失败
                        set_task_status(task_id, 'failed', end_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                        continue
                    
                    # 原子性地更新任务状态为running
                    try:
                        conn = get_db_conn()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE task_flames SET status='running' WHERE task_id=%s AND status='pending'", (str(task_id),))
                        updated_rows = cursor.rowcount
                        conn.commit()
                        conn.close()
                        
                        if updated_rows > 0:
                            print(f"[SCHEDULER] 成功启动任务: {task_id}")
                            t = threading.Thread(target=run_task_algorithm, args=(task_id, model_name, dataset_id))
                            t.start()
                        else:
                            print(f"[SCHEDULER] 任务已被其他线程处理: {task_id}")
                    except Exception as e:
                        print(f"[ERROR] 更新任务状态失败: {task_id}, 错误: {e}")
        except Exception as e:
            print(f"[SCHEDULER] 调度异常: {e}")
            import traceback
            traceback.print_exc()
        time.sleep(5)  # 每5秒轮询一次

# Flask启动时自动启动调度线程
def start_scheduler_thread():
    t = threading.Thread(target=task_scheduler_loop, daemon=True)
    t.start()

def update_task_status(task_id, status):
    conn = get_db_conn()
    cursor = conn.cursor()
    if status == 'completed':
        end_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("UPDATE task_flames SET status=%s, end_time=%s WHERE task_id=%s", (status, end_time, str(task_id)))
    else:
        cursor.execute("UPDATE task_flames SET status=%s WHERE task_id=%s", (status, str(task_id)))
    conn.commit()
    conn.close()

def get_task_row(task_id):
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT model_name, dataset_id, submit_time, status, end_time, result FROM task_flames WHERE task_id=%s", (str(task_id),))
    row = cursor.fetchone()
    conn.close()
    return row

def create_flames_tasks(model_name, dataset_ids, submit_time):
    tasks = []
    
    # 检查是否有running任务
    running_count = has_running_task()
    
    for i, dataset_id in enumerate(dataset_ids):
        task_id = uuid.uuid4()
        
        # 策略：
        # 1. 如果当前没有running任务，且这是第一个新任务，直接设为running
        # 2. 否则设为pending，由调度器按FIFO顺序处理
        if running_count == 0 and i == 0:
            initial_status = 'running'
            print(f"[TASK] 立即启动任务: {task_id} (模型: {model_name}, 数据集: {dataset_id})")
            # 立即启动任务执行线程
            t = threading.Thread(target=run_task_algorithm, args=(task_id, model_name, dataset_id))
            t.start()
        else:
            initial_status = 'pending'
        
        insert_task_to_db(task_id, model_name, dataset_id, submit_time, initial_status, None)
        tasks.append({"dataset_id": dataset_id, "task_id": str(task_id)})
    
    return tasks

def parse_score_file(score_file):
    result = {
        'harmless_rate': None,
        'harmless_rate_each_dim': {},
        'harmless_score': None,
        'harmless_score_each_dim': {}
    }
    
    # 检查文件是否存在
    if not os.path.exists(score_file):
        print(f"[ERROR] 评分文件不存在: {score_file}")
        return result
    
    try:
        with open(score_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i, line in enumerate(lines):
                if line.startswith('harmless_rate:'):
                    result['harmless_rate'] = float(line.split(':', 1)[1].strip())
                elif line.startswith('harmless_rate_each_dim:'):
                    result['harmless_rate_each_dim'] = ast.literal_eval(line.split(':', 1)[1].strip())
                elif line.startswith('harmless_score:'):
                    result['harmless_score'] = float(line.split(':', 1)[1].strip())
                elif line.startswith('harmless_score_each_dim:'):
                    result['harmless_score_each_dim'] = ast.literal_eval(line.split(':', 1)[1].strip())
    except Exception as e:
        print(f"[ERROR] 解析评分文件失败: {e}")
        # 返回默认值，不中断流程
        return result
    
    return result


def get_all_tasks():
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT task_id, model_name, dataset_id, submit_time, end_time, status FROM task_flames ORDER BY submit_time DESC")
    rows = cursor.fetchall()
    conn.close()
    tasks = []
    for row in rows:
        task_id, model_name, dataset_id, submit_time, end_time, status = row
        tasks.append({
            'task_id': str(task_id),
            'model_name': model_name,
            'dataset_id': dataset_id,
            'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None,
            'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else None,
            'status': status
        })
    return tasks

def read_score_log(score_file_path):
    # 只读评分文件内容，不写入
    if not os.path.exists(score_file_path):
        yield f"评估文件不存在: {score_file_path}"
        return
    with open(score_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            yield line.rstrip('\n')

def parse_predicted_log(pred_file):
    # 每个维度各10条记录，逐行解析时容错，遇到坏行则跳过并记录警告
    dimensions = ['Fairness', 'Safety', 'Morality', 'Legality', 'Data protection']
    logs = {dim: [] for dim in dimensions}

    if not os.path.exists(pred_file):
        print(f"[WARN] predicted file does not exist: {pred_file}")
        return []

    try:
        with open(pred_file, 'r', encoding='utf-8-sig', errors='ignore') as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[WARN] Failed to parse JSON line {lineno} in {pred_file}: {line[:200]}")
                    continue
                except Exception as e:
                    print(f"[WARN] Unexpected error parsing line {lineno} in {pred_file}: {e}")
                    continue

                dim = data.get('dimension')
                if dim in dimensions and len(logs[dim]) < 10:
                    logs[dim].append({
                        'prompt': data.get('prompt', ''),
                        'response': data.get('response', ''),
                        'predicted': data.get('predicted', None),
                        'dimension': dim
                    })
    except Exception as e:
        print(f"[ERROR] Error reading predicted file {pred_file}: {e}")
        traceback.print_exc()
        return []

    # 将所有维度的记录合并为一个数组
    all_logs = []
    for dim in dimensions:
        all_logs.extend(logs[dim])

    return all_logs

# --- 路由定义 ---

@app.route('/api/flames/create_task', methods=['POST'])
def create_task():
    """
    创建任务，接收前端传来的 ids（数组）和 api_site，转换为后端内部变量 dataset_ids 和 base_url。
    """
    data = request.get_json()
    model_name = data.get('model_name')
    dataset_ids = data.get('ids')
    submit_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(dataset_ids, str):
        dataset_ids = [dataset_ids]
    
    # 获取 API 信息（用于缓存）
    api_site = data.get('api_site')
    base_url = api_site if api_site else ""
    api_key = data.get('api_key', "")
    
    # 记录前端请求日志（不记录敏感信息）
    print(f"[API] 收到创建任务请求 - 模型: {model_name}, 数据集: {dataset_ids}")
    
    # 创建任务
    tasks = create_flames_tasks(model_name, dataset_ids, submit_time)
    
    # 为每个任务存储 API 配置到内存缓存
    for task in tasks:
        task_id = task['task_id']
        store_api_config(task_id, api_key, base_url)
    
    print(f"[API] 成功创建任务: {len(tasks)} 个")
    return jsonify({'tasks': tasks})



@app.route('/api/flames/progress/<task_id>', methods=['GET'])
def flames_progress_stream(task_id):
    """
    SSE流式推送任务进度：
    - running时推送全部推理流
    - 前端无需传递进度参数
    """
    print(f"[API] 收到进度查询请求: {task_id}")
    
    def generate():
        row = get_task_row(task_id)
        if not row:
            yield f"data: {json.dumps({'task_id': str(task_id), 'msg': 'not found'})}\n\n"
            return
        model_name, dataset_id, submit_time, status, end_time, result = row
        task_info = {
            'task_id': str(task_id),
            'model_name': model_name,
            'dataset_id': dataset_id,
            'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None,
            'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else None,
            'status': status,
            'result': result
        }
        if status == 'running':
            # 正常流式推送全部推理流（断点续流）
            yield f"data: {json.dumps({'task_info': task_info})}\n\n"
            
            # 从缓存获取 API 配置
            api_config = get_api_config(task_id)
            if not api_config:
                yield f"data: {json.dumps({'error': 'API配置信息丢失，无法继续执行'}, ensure_ascii=False)}\n\n"
                return
                
            args = Namespace(
                data_path=os.path.join(BASE_DIR, f"data/Flames_{task_id}.jsonl"),
                max_length=512,
                val_bsz_per_gpu=16,
                base_url=api_config['base_url'],
                api_key=api_config['api_key'],
                model_name=model_name
            )
            # 根据dataset_id选择正确的数据集文件来统计总条数
            total_file = get_dataset_file_by_id(int(dataset_id))
            # 调试阶段只取5条，全部的有1000条
            # total_count = sum(1 for _ in open(total_file, 'r', encoding='utf-8') if _.strip()) if os.path.exists(total_file) else 0
            total_count=5
            # 断点续流：统计已完成条数
            data_file = os.path.join(BASE_DIR, f"data/Flames_{task_id}.jsonl")
            already_done = 0
            lines = []
            if os.path.exists(data_file):
                with open(data_file, 'r', encoding='utf-8-sig', errors='ignore') as f:
                    lines = [line for line in f if line.strip()]
                    already_done = len(lines)
            finished_count = already_done
            # 判断是否全部推理已完成
            inference_total = total_count  # 这里假设推理流总数等于已完成条数
            if already_done >= inference_total and already_done > 0:
                print(f"[DEBUG] 任务 {task_id} 推理已完成，开始推送评估日志")
                
                # 推送最后一条推理流
                last_line = json.loads(lines[-1])
                last_line['finished_count'] = already_done
                last_line['total_count'] = total_count
                yield f"data: {json.dumps(last_line, ensure_ascii=False)}\n\n"
                
                # 断点续流时等待5秒再推送评估日志
                time.sleep(5)
                print(f"[DEBUG] 等待5秒后开始推送评估日志")
                yield f"data: {json.dumps({'eval_log': '正在进行评估，请等候'}, ensure_ascii=False)}\n\n"
                

                time.sleep(5)
                # 推送评估日志
                score_file = os.path.join(BASE_DIR, f"data/Flames_{task_id}_score.jsonl")
                eval_log_count = 0
                for log_line in read_score_log(score_file):
                    eval_log_count += 1
                    yield f"data: {json.dumps({'eval_log': log_line, 'finished_count': already_done, 'total_count': total_count}, ensure_ascii=False)}\n\n"
                    time.sleep(2)
                print(f"[DEBUG] 推送了 {eval_log_count} 条评估日志")
                
                # 推送完所有评估日志后，更新任务状态为completed
                set_task_status(task_id, 'completed', end_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                print(f"[DEBUG] 任务 {task_id} 状态已更新为completed")
                
                # 推送任务完成状态给前端
                completed_task_info = {
                    'task_id': str(task_id),
                    'model_name': model_name,
                    'dataset_id': dataset_id,
                    'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None,
                    'end_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'status': 'completed',
                    'result': result
                }
                time.sleep(3)
                yield f"data: {json.dumps({'task_info': completed_task_info})}\n\n"
                print(f"[DEBUG] 已推送任务完成状态给前端: {completed_task_info}")
            else:
                try:
                    for idx, item in enumerate(run_inference_and_score(args)):
                        if idx < already_done:
                            continue
                        finished_count += 1
                        item['finished_count'] = finished_count
                        item['total_count'] = total_count
                    
                        yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                    time.sleep(3)
                    # 推送任务完成状态给前端
                    completed_task_info = {
                        'task_id': str(task_id),
                        'model_name': model_name,
                        'dataset_id': dataset_id,
                        'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None,
                        'end_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'status': 'completed',
                        'result': result
                    }
                        
                    yield f"data: {json.dumps({'task_info': completed_task_info})}\n\n"
                    print(f"[DEBUG] 已推送任务完成状态给前端: {completed_task_info}")
                except Exception as e:
                    # 捕获异常并推送错误信息
                    error_message = f"任务执行失败: {str(e)}"
                    yield f"data: {json.dumps({'error': error_message}, ensure_ascii=False)}\n\n"
                    
                    # 更新任务状态为failed
                    set_task_status(task_id, 'failed', end_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    
                    # 推送任务失败状态给前端
                    failed_task_info = {
                        'task_id': str(task_id),
                        'model_name': model_name,
                        'dataset_id': dataset_id,
                        'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None,
                        'end_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'status': 'failed',
                        'error_message': error_message,
                        'result': result
                    }
                    yield f"data: {json.dumps({'task_info': failed_task_info})}\n\n"
                    print(f"[DEBUG] 已推送任务失败状态给前端: {failed_task_info}")
                    
        elif status == 'completed':
            # 推送任务完成状态给前端
            print(f"[DEBUG] 任务 {task_id} 已完成，推送完成状态")
            completed_task_info = {
                'task_id': str(task_id),
                'model_name': model_name,
                'dataset_id': dataset_id,
                'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None,
                'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else None,
                'status': 'completed',
                'result': result
            }
            yield f"data: {json.dumps({'task_info': completed_task_info})}\n\n"
        elif status == 'failed':
            # 推送任务失败状态给前端
            failed_task_info = {
                'task_id': str(task_id),
                'model_name': model_name,
                'dataset_id': dataset_id,
                'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None,
                'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else None,
                'status': 'failed',
                'error_message': '任务执行失败，请检查日志或重新提交任务',
                'result': result
            }
            yield f"data: {json.dumps({'task_info': failed_task_info})}\n\n"
        else:
            # 其他状态（如pending）直接推送当前状态
            print(f"[DEBUG] 任务 {task_id} 状态为 {status}，推送当前状态")
            yield f"data: {json.dumps({'task_info': task_info})}\n\n"
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

# /api/flames/report/<task_id> 只返回聚合JSON，无流式逻辑
@app.route('/api/flames/report/<task_id>', methods=['GET'])
def flames_report(task_id):
    row = get_task_row(task_id)
    if not row:
        return jsonify({'task_id': str(task_id), 'msg': 'not found'}), 404
    model_name, dataset_id, submit_time, status, end_time, result = row
    if status != 'completed':
        return jsonify({'task_id': str(task_id), 'msg': 'not completed'}), 400
    score_file = os.path.join(BASE_DIR, f"data/Flames_{task_id}_score.jsonl")
    pred_file = os.path.join(BASE_DIR, f"data/Flames_{task_id}_predicted.jsonl")
    if not (os.path.exists(score_file) and os.path.exists(pred_file)):
        return jsonify({'task_id': str(task_id), 'msg': 'result file not found'}), 404
    score_data = parse_score_file(score_file)
    logs = parse_predicted_log(pred_file)
    
    # 构建result数据（包含 logs）
    result_data = {
        'harmless_rate': score_data.get('harmless_rate'),
        'harmless_rate_each_dim': score_data.get('harmless_rate_each_dim', {}),
        'harmless_score': score_data.get('harmless_score'),
        'harmless_score_each_dim': score_data.get('harmless_score_each_dim', {}),
        'logs': logs
    }
    
    # 将result数据保存到数据库
    try:
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE task_flames SET result=%s WHERE task_id=%s", (json.dumps(result_data, ensure_ascii=False), str(task_id)))
        conn.commit()
        conn.close()
        print(f"[DEBUG] 已将result与logs数据保存到数据库，任务ID: {task_id}")
    except Exception as e:
        print(f"[ERROR] 保存result数据到数据库失败: {e}")
        traceback.print_exc()
    
    return jsonify({
        'taskId': str(task_id),
        'model_name': model_name,
        'dataset_id': dataset_id,
        'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None,
        'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else None,
        'status': status,
        'data': result_data,
        'log': logs
    })

@app.route('/api/flames/history', methods=['GET'])
def get_flames_history():
    print(f"[API] 收到历史记录查询请求")
    try:
        tasks = get_all_tasks()
        return jsonify({'tasks': tasks})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/flames/debug/<task_id>', methods=['GET'])
def debug_task_status(task_id):
    """
    调试API：检查任务状态和相关信息
    """
    try:
        row = get_task_row(task_id)
        if not row:
            return jsonify({'task_id': str(task_id), 'msg': 'not found'}), 404
        
        model_name, dataset_id, submit_time, status, end_time, result = row  # result 为空
        
        # 检查相关文件是否存在
        data_file = f"data/Flames_{task_id}.jsonl"
        pred_file = f"data/Flames_{task_id}_predicted.jsonl"
        score_file = f"data/Flames_{task_id}_score.jsonl"
        error_file = f"data/Flames_{task_id}_error.log"
        
        file_status = {
            'data_file': os.path.exists(data_file),
            'pred_file': os.path.exists(pred_file),
            'score_file': os.path.exists(score_file),
            'error_file': os.path.exists(error_file)
        }
        
        # 检查是否有running任务
        running_count = 0
        try:
            conn = get_db_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM task_flames WHERE status='running'")
            running_count = cursor.fetchone()[0]
            conn.close()
        except Exception as e:
            print(f"[ERROR] 检查running任务失败: {e}")
        
        return jsonify({
            'task_id': str(task_id),
            'model_name': model_name,
            'dataset_id': dataset_id,
            'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None,
            'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else None,
            'status': status,
            'file_status': file_status,
            'running_tasks_count': running_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/flames/debug/scheduler', methods=['GET'])
def debug_scheduler():
    """
    调试API：手动触发调度器检查
    """
    try:
        print(f"[DEBUG] 手动触发调度器检查")
        
        # 检查running任务
        running_count = has_running_task()
        
        # 检查pending任务
        conn = get_db_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM task_flames WHERE status='pending'")
        pending_count = cursor.fetchone()[0]
        
        # 获取所有任务状态统计
        cursor.execute("SELECT status, COUNT(*) FROM task_flames GROUP BY status")
        status_counts = dict(cursor.fetchall())
        
        # 获取最近的几个任务详情
        cursor.execute("SELECT task_id, status, submit_time FROM task_flames ORDER BY submit_time DESC LIMIT 5")
        recent_tasks = []
        for row in cursor.fetchall():
            task_id, status, submit_time = row
            recent_tasks.append({
                'task_id': str(task_id),
                'status': status,
                'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None
            })
        
        conn.close()
        
        result = {
            'running_count': running_count,
            'pending_count': pending_count,
            'status_counts': status_counts,
            'recent_tasks': recent_tasks,
            'message': '调度器状态检查完成'
        }
        
        print(f"[DEBUG] 调度器状态: {result}")
        return jsonify(result)
        
    except Exception as e:
        print(f"[ERROR] 调度器调试失败: {e}")
        return jsonify({'error': str(e)}), 500

def generate_pdf_report(task_id, task_info, score_data, logs):
    """
    生成PDF格式的评估报告
    """
    # 维度翻译映射
    dimension_map = {
        'Fairness': '公平性',
        'Safety': '安全性', 
        'Morality': '道德性',
        'Legality': '合法性',
        'Data protection': '数据保护'
    }
    
    # 设置Jinja2环境 - 使用绝对路径
    template_dir = os.path.join(BASE_DIR, 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('pdf_report.html')
    
    # 准备模板数据
    template_data = {
        'task_info': task_info,
        'score_data': score_data,
        'logs': logs,
        'dimension_map': dimension_map,
        'generation_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # 渲染HTML
    html_content = template.render(**template_data)
    
    try:
        # 配置字体路径（Linux环境下）
        font_config = {
            'font_config': {
                'font_family': {
                    'serif': ['SimSun', 'DejaVu Serif', 'serif'],
                    'sans_serif': ['Microsoft YaHei', 'SimHei', 'DejaVu Sans', 'sans-serif'],
                    'monospace': ['Courier New', 'DejaVu Sans Mono', 'monospace']
                }
            }
        }
        
        # 转换为PDF，添加字体配置
        pdf = HTML(string=html_content).write_pdf(**font_config)
        
        print(f"[DEBUG] PDF生成成功，大小: {len(pdf)} 字节")
        return pdf
        
    except Exception as e:
        print(f"[ERROR] PDF生成失败: {str(e)}")
        # 尝试不使用字体配置的备用方案
        try:
            pdf = HTML(string=html_content).write_pdf()
            print(f"[DEBUG] 备用PDF生成成功，大小: {len(pdf)} 字节")
            return pdf
        except Exception as e2:
            print(f"[ERROR] 备用PDF生成也失败: {str(e2)}")
            raise e2

def generate_report_html(task_id, task_info, score_data, logs):
    """
    生成HTML格式的评估报告
    """
    # 维度翻译映射
    dimension_map = {
        'Fairness': '公平性',
        'Safety': '安全性', 
        'Morality': '道德性',
        'Legality': '合法性',
        'Data protection': '数据保护'
    }
    
    # 参考模型数据
    reference_models = {
        'Claude': 63.77,
        'InternLM - Chat - 20B': 58.56,
        'InternLM - Chat - 7B': 53.93,
        'ChatGPT': 46.91
    }
    
    # 设置Jinja2环境 - 使用绝对路径
    template_dir = os.path.join(BASE_DIR, 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('flames_report.html')
    
    # 准备模板数据
    template_data = {
        'task_info': task_info,
        'score_data': score_data,
        'logs': logs,
        'dimension_map': dimension_map,
        'reference_models': reference_models,
        'generation_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # 渲染HTML
    html_content = template.render(**template_data)
    
    return html_content

def _generate_pdf_with_puppeteer(html_content: str) -> bytes:
    """使用puppeteer生成PDF（参考 3.txt ）"""
    # 获取当前文件目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    pdf_script_path = os.path.join(current_dir, "generate_pdf.js")

    # 检查PDF生成脚本是否存在
    if not os.path.exists(pdf_script_path):
        raise Exception(f"PDF generation script not found: {pdf_script_path}")

    # 创建临时文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as html_file:
        html_file.write(html_content)
        html_file_path = html_file.name

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_file:
        pdf_file_path = pdf_file.name

    try:
        # 执行PDF生成脚本
        result = subprocess.run(
            ["node", pdf_script_path, html_file_path, pdf_file_path],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=current_dir
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            print(f"[ERROR] PDF generation script failed with return code {result.returncode}")
            print(f"[ERROR] stdout: {result.stdout}")
            print(f"[ERROR] stderr: {result.stderr}")
            raise Exception(f"PDF generation failed (code {result.returncode}): {error_msg}")

        # 检查PDF文件是否生成成功
        if not os.path.exists(pdf_file_path) or os.path.getsize(pdf_file_path) == 0:
            raise Exception("PDF file was not generated or is empty")

        # 读取生成的PDF
        with open(pdf_file_path, 'rb') as f:
            pdf_bytes = f.read()

        print(f"[INFO] PDF generated successfully, size: {len(pdf_bytes)} bytes")
        return pdf_bytes

    finally:
        # 清理临时文件
        try:
            os.unlink(html_file_path)
        except Exception:
            pass
        try:
            os.unlink(pdf_file_path)
        except Exception:
            pass

@app.route('/api/flames/report/<task_id>/download', methods=['GET'])
def download_flames_report(task_id):
    """
    下载Flames评估报告
    """
    print(f"[API] 收到报告下载请求: {task_id}")
    
    # 检查任务是否存在
    row = get_task_row(task_id)
    if not row:
        print(f"[DEBUG] 任务 {task_id} 不存在")
        return jsonify({'task_id': str(task_id), 'msg': 'not found'}), 404
    
    model_name, dataset_id, submit_time, status, end_time, result = row
    print(f"[DEBUG] 任务状态: {status}")
    
    if status != 'completed':
        print(f"[DEBUG] 任务未完成，无法下载报告")
        return jsonify({'task_id': str(task_id), 'msg': 'task is not completed'}), 400
    
    # 使用数据库中的 result 字段（包含 scores 与 logs），不再依赖 jsonl 文件
    print(f"[DEBUG] 使用数据库 result 字段: {'存在' if result else '为空'}")

    if not result:
        print(f"[ERROR] 数据库 result 字段为空，无法生成报告")
        return jsonify({'task_id': str(task_id), 'msg': 'result not found in DB'}), 404

    try:
        # 解析 result 字段（支持 str/dict/bytes）
        if isinstance(result, str):
            result_json = json.loads(result)
        elif isinstance(result, (dict, list)):
            result_json = result
        elif isinstance(result, bytes):
            result_json = json.loads(result.decode('utf-8'))
        else:
            raise TypeError(f"Unsupported result type: {type(result)}")
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        print(f"[ERROR] 解析数据库 result 字段失败: {e}")
        traceback.print_exc()
        return jsonify({'task_id': str(task_id), 'msg': 'invalid result in DB'}), 500

    score_data = {
        'harmless_rate': result_json.get('harmless_rate'),
        'harmless_rate_each_dim': result_json.get('harmless_rate_each_dim', {}),
        'harmless_score': result_json.get('harmless_score'),
        'harmless_score_each_dim': result_json.get('harmless_score_each_dim', {})
    }
    
    # 尝试从数据库获取 logs，如果没有则从文件读取
    logs = result_json.get('logs', [])
    if not logs:
        # 从文件系统读取 predicted 数据
        pred_file = os.path.join(BASE_DIR, f"data/Flames_{task_id}_predicted.jsonl")
        if os.path.exists(pred_file):
            print(f"[DEBUG] 从文件读取 logs: {pred_file}")
            logs = parse_predicted_log(pred_file)
        else:
            print(f"[DEBUG] 未找到 predicted 文件，使用空 logs: {pred_file}")
            logs = []

    # 基本校验
    if score_data.get('harmless_rate') is None and score_data.get('harmless_score') is None:
        print(f"[ERROR] 无法获取有效的评分数据 from DB")
        return jsonify({'task_id': str(task_id), 'msg': 'insufficient score data'}), 400

    # 任务信息
    task_info = {
        'task_id': str(task_id),
        'model_name': model_name,
        'dataset_id': dataset_id,
        'submit_time': submit_time.strftime('%Y-%m-%d %H:%M:%S') if submit_time else None,
        'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else None,
        'status': status
    }

    try:
        # 渲染HTML（模板：templates/html_report.html）
        html_content = generate_report_html(task_id, task_info, score_data, logs)

        # 使用puppeteer将HTML转换为PDF
        try:
            pdf_bytes = _generate_pdf_with_puppeteer(html_content)
        except Exception as e:
            print(f"[ERROR] PDF生成失败: {str(e)}")
            return jsonify({'error': 'PDFServiceUnavailable', 'message': 'PDF生成失败，可能由于puppeteer未安装或脚本缺失。', 'details': str(e)}), 503

        # 以PDF文件形式返回
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'Flames_Report_{task_id}.pdf'
        )
    except Exception as e:
        return jsonify({'task_id': str(task_id), 'msg': f'generate report failed: {str(e)}'}), 500


@app.route('/api/flames/logs/<task_id>/download', methods=['GET'])
def download_flames_logs(task_id):
    """
    下载指定任务的预测日志为log文件
    """
    # 检查任务是否存在
    row = get_task_row(task_id)
    if not row:
        return jsonify({'task_id': str(task_id), 'msg': 'not found'}), 404
    
    model_name, dataset_id, submit_time, status, end_time, result = row
    if status != 'completed':
        return jsonify({'task_id': str(task_id), 'msg': 'not completed'}), 400
    
    # 检查预测文件是否存在
    pred_file = os.path.join(BASE_DIR, f"data/Flames_{task_id}_predicted.jsonl")
    if not os.path.exists(pred_file):
        return jsonify({'task_id': str(task_id), 'msg': 'predicted file not found'}), 404
    
    # 维度翻译映射
    dimension_map = {
        'Fairness': '公平性',
        'Safety': '安全性',
        'Morality': '道德性',
        'Legality': '合法性',
        'Data protection': '数据保护'
    }
    
    # 读取预测文件并组装log内容
    log_content = []
    log_content.append('Flames任务执行日志')
    log_content.append(f'任务ID: {task_id}')
    log_content.append(f'生成时间: {datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")}')
    log_content.append('')  # 空行
    
    entry_count = 1
    with open(pred_file, 'r', encoding='utf-8-sig', errors='ignore') as f:
        for line in f:
            data = json.loads(line)
            dimension = data.get('dimension', '')
            predicted = data.get('predicted', '')
            prompt = data.get('prompt', '')
            response = data.get('response', '')
            
            # 翻译维度名称
            dimension_cn = dimension_map.get(dimension, dimension)
            
            # 组装log条目
            log_content.append(f'=== 日志条目 {entry_count} ===')
            log_content.append(f'维度: {dimension_cn}')
            log_content.append(f'预测分数: {predicted}')
            log_content.append(f'场景描述: {prompt}')
            log_content.append(f'模型回复: {response}')
            log_content.append('')  # 空行分隔
            
            entry_count += 1
    
    # 创建log文件
    log_text = '\n'.join(log_content)
    
    # 创建内存文件对象
    log_buffer = io.BytesIO()
    log_buffer.write(log_text.encode('utf-8'))  # 使用UTF-8编码
    log_buffer.seek(0)
    
    # 返回文件下载
    return send_file(
        log_buffer,
        mimetype='text/plain',
        as_attachment=True,
        download_name=f'Flames_logs_{task_id}.log'
    )

# 在主入口启动调度线程
if __name__ == '__main__':
    start_scheduler_thread()
    app.run(host='0.0.0.0', port=5001, debug=True)
