# 非v1.0版本的不足
这样应该可以解决评估文件生成超时的问题。容器已重启，修改已生效。

    > 也许算法要执行很久呢？120秒也不够呢？有没有什么其他的逻辑建议？（先不要改代码）               

✦ 你说得对，120秒也可能不够。让我分析一下现有逻辑的问题和可能的改进方案：

  当前逻辑的问题

   1. 固定等待时间不可靠：算法执行时间不确定，可能几秒，也可能几分钟
   2. 被动等待：只是简单地检查文件是否存在，不知道算法的进度
   3. 没有重试机制：一旦超时就放弃，没有恢复机制
   4. 用户体验差：用户不知道实际进度

  改进方案建议

  方案1：实时监控文件大小变化
    1 # 逻辑：监控score文件的大小变化
    2 # 如果文件大小在一段时间内不再增长，说明生成完成
    3 score_file = os.path.join(BASE_DIR, f"result/{task_id}/Flames_{task_id}_score.jsonl")
    4 last_size = 0
    5 stable_count = 0
    6 max_stable_checks = 5  # 连续5次检查文件大小不变，认为完成
    7 
    8 while True:
    9     if os.path.exists(score_file):
   10         current_size = os.path.getsize(score_file)
   11         if current_size == last_size:
   12             stable_count += 1
   13             if stable_count >= max_stable_checks:
   14                 break  # 文件大小稳定，生成完成
   15         else:
   16             stable_count = 0
   17             last_size = current_size
   18     time.sleep(2)  # 每2秒检查一次

  优点：
   - 自适应，不依赖固定时间
   - 能检测到文件是否真的生成完成

  缺点：
   - 如果算法在写入过程中暂停，可能误判

  方案2：检查任务状态标志位
    1 # 逻辑：让算法在完成时创建一个标志文件
    2 # 算法完成时创建: result/{task_id}/.completed
    3 # 或者在score文件中写入完成标记
    4 
    5 flag_file = os.path.join(BASE_DIR, f"result/{task_id}/.completed")
    6 max_wait = 600  # 最多等待10分钟
    7 wait_count = 0
    8 
    9 while not os.path.exists(flag_file) and wait_count < max_wait:
   10     time.sleep(1)
   11     wait_count += 1

  优点：
   - 明确的完成信号
   - 简单可靠

  缺点：
   - 需要修改算法代码，在完成时创建标志文件

  方案3：检查score文件内容完整性
    1 # 逻辑：检查score文件是否有预期的行数
    2 # 比如输入有5条数据，score文件应该也有5条
    3 
    4 input_file = os.path.join(BASE_DIR, f"result/{task_id}/Flames_{task_id}.jsonl")
    5 score_file = os.path.join(BASE_DIR, f"result/{task_id}/Flames_{task_id}_score.jsonl")
    6 
    7 # 获取输入文件行数
    8 with open(input_file, 'r') as f:
    9     expected_lines = sum(1 for _ in f)
   10 
   11 # 等待score文件行数匹配
   12 while True:
   13     if os.path.exists(score_file):
   14         with open(score_file, 'r') as f:
   15             actual_lines = sum(1 for _ in f)
   16         if actual_lines >= expected_lines:
   17             break
   18     time.sleep(2)

  优点：
   - 确保数据完整性
   - 不依赖时间

  缺点：
   - 需要知道预期行数
   - 需要频繁读取文件

  方案4：结合文件存在性和内容检查（推荐）
    1 # 逻辑：先等待文件存在，然后检查内容
    2 
    3 score_file = os.path.join(BASE_DIR, f"result/{task_id}/Flames_{task_id}_score.jsonl")
    4 
    5 # 阶段1：等待文件创建（最多5分钟）
    6 wait_count = 0
    7 max_wait = 300
    8 while not os.path.exists(score_file) and wait_count < max_wait:
    9     time.sleep(1)
   10     wait_count += 1
   11     # 每10秒推送一次进度
   12     if wait_count % 10 == 0:
   13         yield f"data: {json.dumps({'eval_log': f'正在生成评估文件... ({wait_count}s)'}, 
      ensure_ascii=False)}\n\n"
   14 
   15 if not os.path.exists(score_file):
   16     yield f"data: {json.dumps({'error': '评估文件生成超时'}, ensure_ascii=False)}\n\n"
   17     return
   18 
   19 # 阶段2：等待文件写入完成（通过文件大小变化判断）
   20 last_size = 0
   21 stable_count = 0
   22 max_stable_checks = 3
   23 
   24 while stable_count < max_stable_checks:
   25     time.sleep(2)
   26     current_size = os.path.getsize(score_file)
   27     if current_size == last_size:
   28         stable_count += 1
   29     else:
   30         stable_count = 0
   31         last_size = current_size

  优点：
   - 分阶段检查，更可靠
   - 有进度反馈
   - 自适应等待时间

  方案5：异步轮询 + 前端重试
   1 # 逻辑：如果score文件未就绪，返回"处理中"状态
   2 # 前端通过轮询API获取结果
   3 
   4 # 不在流式响应中等待，直接返回当前状态
   5 if not os.path.exists(score_file):
   6     yield f"data: {json.dumps({'status': 'processing', 'message': 
     '评估进行中，请稍后查看结果'}, ensure_ascii=False)}\n\n"
   7     return
   8 
   9 # 前端可以定期调用 /api/flames/report/{task_id} 获取最终结果

  优点：
   - 不阻塞HTTP连接
   - 用户可以刷新页面
   - 更符合现代Web应用模式

  缺点：
   - 需要修改前端逻辑
   - 用户体验可能略有变化

  我的推荐

  方案4（结合文件存在性和内容检查） 是最适合当前场景的，因为：
   1. 不需要修改算法代码
   2. 自适应等待时间
   3. 有进度反馈
   4. 可靠性高

  备选方案：如果前端可以配合修改，方案5（异步轮询）是更现代、更优雅的解决方案。