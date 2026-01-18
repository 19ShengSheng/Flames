import time
import threading

class ApiConfigCache:
    """API 配置缓存类，封装配置的存储、获取和清理功能，线程安全"""
    
    def __init__(self):
        # 初始化缓存字典和线程锁，不再使用全局变量
        self.api_config_cache = {}
        self.api_config_lock = threading.Lock()
        # 过期时间常量（24小时，单位：秒），便于后续修改
        self.EXPIRE_SECONDS = 86400

    def store_api_config(self, task_id, api_key, base_url):
        """
        临时存储 API 配置信息
        :param task_id: 任务ID（任意可转为字符串的类型）
        :param api_key: API 密钥
        :param base_url: API 基础地址
        """
        with self.api_config_lock:
            task_id_str = str(task_id)
            self.api_config_cache[task_id_str] = {
                'api_key': api_key,
                'base_url': base_url,
                'timestamp': time.time()
            }

    def get_api_config(self, task_id):
        """
        获取 API 配置信息（自动过滤过期和无效配置）
        :param task_id: 任务ID（任意可转为字符串的类型）
        :return: 有效配置字典（None表示无有效配置）
        """
        with self.api_config_lock:
            task_id_str = str(task_id)
            config = self.api_config_cache.get(task_id_str)
            if config:
                # 检查配置是否过期
                if time.time() - config['timestamp'] < self.EXPIRE_SECONDS:
                    # 检查 api_key 和 base_url 是否非空有效
                    if config.get('api_key') and config.get('base_url'):
                        return config
                    else:
                        # 无效配置则删除
                        del self.api_config_cache[task_id_str]
                else:
                    # 过期配置则删除
                    del self.api_config_cache[task_id_str]
            return None

    def cleanup_api_config(self, task_id):
        """
        主动清理指定任务的 API 配置信息
        :param task_id: 任务ID（任意可转为字符串的类型）
        """
        with self.api_config_lock:
            task_id_str = str(task_id)
            if task_id_str in self.api_config_cache:
                del self.api_config_cache[task_id_str]