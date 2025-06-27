#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import logging
import json
import uuid

import valkey as redis
from rag import settings
from rag.utils import singleton
from valkey.lock import Lock
import trio


class RedisMsg:
    def __init__(self, consumer, queue_name, group_name, msg_id, message):
        self.__consumer = consumer
        self.__queue_name = queue_name
        self.__group_name = group_name
        self.__msg_id = msg_id
        self.__message = json.loads(message["message"])

    def ack(self):
        try:
            self.__consumer.xack(self.__queue_name, self.__group_name, self.__msg_id)
            return True
        except Exception as e:
            logging.warning("[EXCEPTION]ack" + str(self.__queue_name) + "||" + str(e))
        return False

    def get_message(self):
        return self.__message

    def get_msg_id(self):
        return self.__msg_id


@singleton
class RedisDB:
    lua_delete_if_equal = None
    LUA_DELETE_IF_EQUAL_SCRIPT = """
        local current_value = redis.call('get', KEYS[1])
        if current_value and current_value == ARGV[1] then
            redis.call('del', KEYS[1])
            return 1
        end
        return 0
    """

    def __init__(self):
        self.REDIS = None
        self.config = settings.REDIS
        self.is_cluster = False
        self.cluster_slot_cache = {}  # 槽位到节点的映射缓存
        self.node_connections = {}  # 节点连接缓存
        self.__open__()

    def register_scripts(self) -> None:
        cls = self.__class__
        client = self.REDIS
        cls.lua_delete_if_equal = client.register_script(cls.LUA_DELETE_IF_EQUAL_SCRIPT)

    def _get_key_slot(self, key):
        """计算键的哈希槽"""
        if isinstance(key, str):
            key = key.encode("utf-8")

        # Redis集群使用CRC16算法计算哈希槽
        def crc16(data):
            """CRC16算法实现"""
            crc = 0
            for byte in data:
                crc ^= byte << 8
                for _ in range(8):
                    if crc & 0x8000:
                        crc = (crc << 1) ^ 0x1021
                    else:
                        crc <<= 1
                    crc &= 0xFFFF
            return crc

        return crc16(key) % 16384

    def _get_node_for_slot(self, slot):
        """从缓存中获取槽位对应的节点"""
        return self.cluster_slot_cache.get(slot)

    def _get_connection_for_node(self, host, port):
        """获取到指定节点的连接"""
        node_key = f"{host}:{port}"
        if node_key not in self.node_connections:
            try:
                # 集群模式下不能设置db参数，只能使用数据库0
                conn = redis.StrictRedis(
                    host=host,
                    port=port,
                    password=self.config.get("password"),
                    decode_responses=True,
                )
                # 测试连接
                conn.ping()
                self.node_connections[node_key] = conn
                return conn
            except Exception as e:
                logging.warning(f"Failed to connect to node {host}:{port}: {e}")
                return None
        return self.node_connections[node_key]

    def _handle_cluster_redirect(self, error_str, key):
        """处理集群重定向错误"""
        try:
            # 解析MOVED错误: MOVED slot_number host:port
            if "MOVED" in error_str:
                parts = error_str.split()
                if len(parts) >= 3:
                    slot = int(parts[1])
                    host_port = parts[2]
                    if ":" in host_port:
                        host, port = host_port.split(":")
                        port = int(port)
                        # 更新槽位缓存
                        self.cluster_slot_cache[slot] = (host, port)
                        logging.info(f"Updated slot cache: slot {slot} -> {host}:{port}")
                        return True
        except Exception as e:
            logging.warning(f"Failed to handle cluster redirect: {e}")
        return False

    def __open__(self):
        try:
            # 检查是否为集群模式
            mode = self.config.get("mode", "single")
            if mode == "cluster":
                self.is_cluster = True
                # 解析集群节点
                cluster_nodes_str = self.config.get("cluster_nodes", "")
                if cluster_nodes_str:
                    nodes = []
                    for node in cluster_nodes_str.split(","):
                        node = node.strip()
                        if ":" in node:
                            host, port = node.split(":")
                            nodes.append({"host": host.strip(), "port": int(port.strip())})

                    if nodes:
                        # 尝试连接到集群中的任意一个节点
                        for node in nodes:
                            try:
                                # 集群模式下不能设置db参数，只能使用数据库0
                                self.REDIS = redis.StrictRedis(
                                    host=node["host"],
                                    port=node["port"],
                                    password=self.config.get("password"),
                                    decode_responses=True,
                                )
                                self.REDIS.ping()
                                logging.info(f"Connected to cluster node: {node['host']}:{node['port']}")
                                break
                            except Exception as e:
                                logging.warning(f"Failed to connect to cluster node {node['host']}:{node['port']}: {e}")
                                continue
                        else:
                            raise Exception("Failed to connect to any cluster node")
                    else:
                        raise Exception("No valid cluster nodes found in configuration")
                else:
                    raise Exception("cluster_nodes not configured")
            else:
                # 单节点模式
                self.is_cluster = False
                self.REDIS = redis.StrictRedis(
                    host=self.config["host"].split(":")[0],
                    port=int(self.config.get("host", ":6379").split(":")[1]),
                    db=int(self.config.get("db", 1)),
                    password=self.config.get("password"),
                    decode_responses=True,
                )

            self.register_scripts()
        except Exception as e:
            logging.warning(f"Redis can't be connected: {e}")
        return self.REDIS

    def _execute_with_cluster_redirect(self, operation_name, key, operation_func, *args, **kwargs):
        """统一的集群重定向处理器"""
        if not self.is_cluster:
            return operation_func(*args, **kwargs)

        # 计算键的槽位，找到正确的节点
        slot = self._get_key_slot(key)
        cached_node = self._get_node_for_slot(slot)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 如果有缓存的节点，使用该节点
                if cached_node:
                    host, port = cached_node
                    target_connection = self._get_connection_for_node(host, port)
                    if target_connection:
                        return operation_func(*args, connection=target_connection, **kwargs)

                # 否则使用默认连接
                return operation_func(*args, **kwargs)

            except Exception as e:
                error_str = str(e)
                if "MOVED" in error_str and attempt < max_retries - 1:
                    # 解析MOVED重定向
                    if self._handle_cluster_redirect(error_str, key):
                        # 更新缓存的节点信息
                        slot = self._get_key_slot(key)
                        cached_node = self._get_node_for_slot(slot)
                        continue
                if attempt == max_retries - 1:
                    raise
                logging.warning(f"{operation_name} attempt {attempt + 1} failed: {e}")

    def health(self):
        self.REDIS.ping()
        a, b = "xx", "yy"
        self.REDIS.set(a, b, 3)

        if self.REDIS.get(a) == b:
            return True

    def is_alive(self):
        return self.REDIS is not None

    def exist(self, k):
        if not self.REDIS:
            return

        def _exist_operation(connection=None):
            client = connection if connection else self.REDIS
            return client.exists(k)

        try:
            return self._execute_with_cluster_redirect("exist", k, _exist_operation)
        except Exception as e:
            logging.warning("RedisDB.exist " + str(k) + " got exception: " + str(e))
            self.__open__()

    def get(self, k):
        if not self.REDIS:
            return

        def _get_operation(connection=None):
            client = connection if connection else self.REDIS
            return client.get(k)

        try:
            return self._execute_with_cluster_redirect("get", k, _get_operation)
        except Exception as e:
            logging.warning("RedisDB.get " + str(k) + " got exception: " + str(e))
            self.__open__()

    def set_obj(self, k, obj, exp=3600):
        try:
            return self.set(k, json.dumps(obj, ensure_ascii=False), exp)
        except Exception as e:
            logging.warning("RedisDB.set_obj " + str(k) + " got exception: " + str(e))
            self.__open__()
        return False

    def set(self, k, v, exp=3600):
        def _set_operation(connection=None):
            client = connection if connection else self.REDIS
            client.set(k, v, exp)
            return True

        try:
            return self._execute_with_cluster_redirect("set", k, _set_operation)
        except Exception as e:
            logging.warning("RedisDB.set " + str(k) + " got exception: " + str(e))
            self.__open__()
        return False

    def sadd(self, key: str, member: str):
        def _sadd_operation(connection=None):
            client = connection if connection else self.REDIS
            client.sadd(key, member)
            return True

        try:
            return self._execute_with_cluster_redirect("sadd", key, _sadd_operation)
        except Exception as e:
            logging.warning("RedisDB.sadd " + str(key) + " got exception: " + str(e))
            self.__open__()
        return False

    def srem(self, key: str, member: str):
        def _srem_operation(connection=None):
            client = connection if connection else self.REDIS
            client.srem(key, member)
            return True

        try:
            return self._execute_with_cluster_redirect("srem", key, _srem_operation)
        except Exception as e:
            logging.warning("RedisDB.srem " + str(key) + " got exception: " + str(e))
            self.__open__()
        return False

    def smembers(self, key: str):
        def _smembers_operation(connection=None):
            client = connection if connection else self.REDIS
            return client.smembers(key)

        try:
            return self._execute_with_cluster_redirect("smembers", key, _smembers_operation)
        except Exception as e:
            logging.warning("RedisDB.smembers " + str(key) + " got exception: " + str(e))
            self.__open__()
        return None

    def zadd(self, key: str, member: str, score: float):
        def _zadd_operation(connection=None):
            client = connection if connection else self.REDIS
            client.zadd(key, {member: score})
            return True

        try:
            return self._execute_with_cluster_redirect("zadd", key, _zadd_operation)
        except Exception as e:
            logging.warning("RedisDB.zadd " + str(key) + " got exception: " + str(e))
            self.__open__()
        return False

    def zcount(self, key: str, min: float, max: float):
        def _zcount_operation(connection=None):
            client = connection if connection else self.REDIS
            return client.zcount(key, min, max)

        try:
            return self._execute_with_cluster_redirect("zcount", key, _zcount_operation)
        except Exception as e:
            logging.warning("RedisDB.zcount " + str(key) + " got exception: " + str(e))
            self.__open__()
        return 0

    def zpopmin(self, key: str, count: int):
        def _zpopmin_operation(connection=None):
            client = connection if connection else self.REDIS
            return client.zpopmin(key, count)

        try:
            return self._execute_with_cluster_redirect("zpopmin", key, _zpopmin_operation)
        except Exception as e:
            logging.warning("RedisDB.zpopmin " + str(key) + " got exception: " + str(e))
            self.__open__()
        return None

    def zrangebyscore(self, key: str, min: float, max: float):
        def _zrangebyscore_operation(connection=None):
            client = connection if connection else self.REDIS
            return client.zrangebyscore(key, min, max)

        try:
            return self._execute_with_cluster_redirect("zrangebyscore", key, _zrangebyscore_operation)
        except Exception as e:
            logging.warning("RedisDB.zrangebyscore " + str(key) + " got exception: " + str(e))
            self.__open__()
        return None

    def transaction(self, key, value, exp=3600):
        def _transaction_operation(connection=None):
            client = connection if connection else self.REDIS
            pipeline = client.pipeline(transaction=True)
            pipeline.set(key, value, exp, nx=True)
            pipeline.execute()
            return True

        try:
            return self._execute_with_cluster_redirect("transaction", key, _transaction_operation)
        except Exception as e:
            logging.warning("RedisDB.transaction " + str(key) + " got exception: " + str(e))
            self.__open__()
        return False

    def queue_product(self, queue, message) -> bool:
        def _queue_product_operation(connection=None):
            client = connection if connection else self.REDIS
            payload = {"message": json.dumps(message)}
            client.xadd(queue, payload)
            return True

        for _ in range(3):
            try:
                return self._execute_with_cluster_redirect("queue_product", queue, _queue_product_operation)
            except Exception as e:
                logging.exception("RedisDB.queue_product " + str(queue) + " got exception: " + str(e))
        return False

    def queue_consumer(self, queue_name, group_name, consumer_name, msg_id=b">") -> RedisMsg:
        """https://redis.io/docs/latest/commands/xreadgroup/"""

        if not self.is_cluster:
            # 单节点模式的原有逻辑
            try:
                group_info = self.REDIS.xinfo_groups(queue_name)
                if not any(gi["name"] == group_name for gi in group_info):
                    self.REDIS.xgroup_create(queue_name, group_name, id="0", mkstream=True)
                args = {
                    "groupname": group_name,
                    "consumername": consumer_name,
                    "count": 1,
                    "block": 5,
                    "streams": {queue_name: msg_id},
                }
                messages = self.REDIS.xreadgroup(**args)
                if not messages:
                    return None
                stream, element_list = messages[0]
                if not element_list:
                    return None
                msg_id, payload = element_list[0]
                res = RedisMsg(self.REDIS, queue_name, group_name, msg_id, payload)
                return res
            except Exception as e:
                if str(e) == "no such key":
                    pass
                else:
                    logging.exception("RedisDB.queue_consumer " + str(queue_name) + " got exception: " + str(e))
            return None

        # 集群模式处理
        slot = self._get_key_slot(queue_name)
        cached_node = self._get_node_for_slot(slot)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 如果有缓存的节点，使用该节点
                if cached_node:
                    host, port = cached_node
                    target_connection = self._get_connection_for_node(host, port)
                    if target_connection:
                        client = target_connection
                    else:
                        client = self.REDIS
                else:
                    client = self.REDIS

                group_info = client.xinfo_groups(queue_name)
                if not any(gi["name"] == group_name for gi in group_info):
                    client.xgroup_create(queue_name, group_name, id="0", mkstream=True)

                args = {
                    "groupname": group_name,
                    "consumername": consumer_name,
                    "count": 1,
                    "block": 5,
                    "streams": {queue_name: msg_id},
                }
                messages = client.xreadgroup(**args)
                if not messages:
                    return None
                stream, element_list = messages[0]
                if not element_list:
                    return None
                msg_id, payload = element_list[0]
                res = RedisMsg(client, queue_name, group_name, msg_id, payload)
                return res

            except Exception as e:
                error_str = str(e)
                if "MOVED" in error_str and attempt < max_retries - 1:
                    # 解析MOVED重定向
                    if self._handle_cluster_redirect(error_str, queue_name):
                        # 更新缓存的节点信息
                        slot = self._get_key_slot(queue_name)
                        cached_node = self._get_node_for_slot(slot)
                        continue
                elif "NOGROUP" in error_str and attempt < max_retries - 1:
                    # 处理NOGROUP错误：队列或消费者组不存在
                    logging.info(f"Queue or group doesn't exist, creating: {queue_name}/{group_name}")
                    try:
                        # 使用正确的节点创建消费者组
                        if cached_node:
                            host, port = cached_node
                            target_connection = self._get_connection_for_node(host, port)
                            if target_connection:
                                target_connection.xgroup_create(queue_name, group_name, id="0", mkstream=True)
                        continue  # 重试消费
                    except Exception as create_error:
                        if "BUSYGROUP" not in str(create_error):
                            logging.warning(f"Failed to create consumer group: {create_error}")
                        continue

                if str(e) == "no such key":
                    pass
                elif attempt == max_retries - 1:
                    logging.exception("RedisDB.queue_consumer " + str(queue_name) + " got exception: " + str(e))
                else:
                    logging.warning(f"queue_consumer attempt {attempt + 1} failed: {e}")
        return None

    def get_unacked_iterator(self, queue_names: list[str], group_name, consumer_name):
        try:
            for queue_name in queue_names:
                try:
                    if self.is_cluster:
                        # 集群模式：使用正确的节点
                        slot = self._get_key_slot(queue_name)
                        cached_node = self._get_node_for_slot(slot)
                        if cached_node:
                            host, port = cached_node
                            target_connection = self._get_connection_for_node(host, port)
                            if target_connection:
                                group_info = target_connection.xinfo_groups(queue_name)
                            else:
                                group_info = self.REDIS.xinfo_groups(queue_name)
                        else:
                            group_info = self.REDIS.xinfo_groups(queue_name)
                    else:
                        group_info = self.REDIS.xinfo_groups(queue_name)
                except Exception as e:
                    if str(e) == "no such key":
                        logging.warning(f"RedisDB.get_unacked_iterator queue {queue_name} doesn't exist")
                        continue
                    elif "MOVED" in str(e) and self.is_cluster:
                        # 处理MOVED重定向
                        if self._handle_cluster_redirect(str(e), queue_name):
                            continue

                if not any(gi["name"] == group_name for gi in group_info):
                    logging.warning(f"RedisDB.get_unacked_iterator queue {queue_name} group {group_name} doesn't exist")
                    continue
                current_min = 0
                while True:
                    payload = self.queue_consumer(queue_name, group_name, consumer_name, current_min)
                    if not payload:
                        break
                    current_min = payload.get_msg_id()
                    logging.info(f"RedisDB.get_unacked_iterator {queue_name} {consumer_name} {current_min}")
                    yield payload
        except Exception:
            logging.exception("RedisDB.get_unacked_iterator got exception: ")
            self.__open__()

    def get_pending_msg(self, queue, group_name):
        def _get_pending_operation(connection=None):
            client = connection if connection else self.REDIS
            return client.xpending_range(queue, group_name, "-", "+", 10)

        try:
            return self._execute_with_cluster_redirect("get_pending_msg", queue, _get_pending_operation)
        except Exception as e:
            if "No such key" not in (str(e) or ""):
                logging.warning("RedisDB.get_pending_msg " + str(queue) + " got exception: " + str(e))
        return []

    def requeue_msg(self, queue: str, group_name: str, msg_id: str):
        def _requeue_operation(connection=None):
            client = connection if connection else self.REDIS
            messages = client.xrange(queue, msg_id, msg_id)
            if messages:
                client.xadd(queue, messages[0][1])
                client.xack(queue, group_name, msg_id)

        try:
            self._execute_with_cluster_redirect("requeue_msg", queue, _requeue_operation)
        except Exception as e:
            logging.warning("RedisDB.requeue_msg " + str(queue) + " got exception: " + str(e))

    def queue_info(self, queue, group_name) -> dict | None:
        def _queue_info_operation(connection=None):
            client = connection if connection else self.REDIS
            groups = client.xinfo_groups(queue)
            for group in groups:
                if group["name"] == group_name:
                    return group
            return None

        try:
            return self._execute_with_cluster_redirect("queue_info", queue, _queue_info_operation)
        except Exception as e:
            logging.warning("RedisDB.queue_info " + str(queue) + " got exception: " + str(e))
        return None

    def delete_if_equal(self, key: str, expected_value: str) -> bool:
        """
        Do follwing atomically:
        Delete a key if its value is equals to the given one, do nothing otherwise.
        """

        def _delete_if_equal_operation(connection=None):
            client = connection if connection else self.REDIS
            return bool(self.lua_delete_if_equal(keys=[key], args=[expected_value], client=client))

        try:
            return self._execute_with_cluster_redirect("delete_if_equal", key, _delete_if_equal_operation)
        except Exception as e:
            logging.warning("RedisDB.delete_if_equal " + str(key) + " got exception: " + str(e))
            self.__open__()
        return False

    def delete(self, key) -> bool:
        def _delete_operation(connection=None):
            client = connection if connection else self.REDIS
            client.delete(key)
            return True

        try:
            return self._execute_with_cluster_redirect("delete", key, _delete_operation)
        except Exception as e:
            logging.warning("RedisDB.delete " + str(key) + " got exception: " + str(e))
            self.__open__()
        return False


REDIS_CONN = RedisDB()


class RedisDistributedLock:
    def __init__(self, lock_key, lock_value=None, timeout=10, blocking_timeout=1):
        self.lock_key = lock_key
        if lock_value:
            self.lock_value = lock_value
        else:
            self.lock_value = str(uuid.uuid4())
        self.timeout = timeout

        # 集群模式需要特殊处理
        if REDIS_CONN.is_cluster:
            slot = REDIS_CONN._get_key_slot(lock_key)
            cached_node = REDIS_CONN._get_node_for_slot(slot)
            if cached_node:
                host, port = cached_node
                target_connection = REDIS_CONN._get_connection_for_node(host, port)
                if target_connection:
                    self.lock = Lock(target_connection, lock_key, timeout=timeout, blocking_timeout=blocking_timeout)
                else:
                    self.lock = Lock(REDIS_CONN.REDIS, lock_key, timeout=timeout, blocking_timeout=blocking_timeout)
            else:
                self.lock = Lock(REDIS_CONN.REDIS, lock_key, timeout=timeout, blocking_timeout=blocking_timeout)
        else:
            self.lock = Lock(REDIS_CONN.REDIS, lock_key, timeout=timeout, blocking_timeout=blocking_timeout)

    def acquire(self):
        REDIS_CONN.delete_if_equal(self.lock_key, self.lock_value)
        try:
            return self.lock.acquire(token=self.lock_value)
        except Exception as e:
            # 如果是集群重定向错误，重新初始化锁
            if "MOVED" in str(e) and REDIS_CONN.is_cluster:
                if REDIS_CONN._handle_cluster_redirect(str(e), self.lock_key):
                    # 重新创建锁对象
                    slot = REDIS_CONN._get_key_slot(self.lock_key)
                    cached_node = REDIS_CONN._get_node_for_slot(slot)
                    if cached_node:
                        host, port = cached_node
                        target_connection = REDIS_CONN._get_connection_for_node(host, port)
                        if target_connection:
                            self.lock = Lock(target_connection, self.lock_key, timeout=self.timeout, blocking_timeout=1)
                            return self.lock.acquire(token=self.lock_value)
            raise

    async def spin_acquire(self):
        REDIS_CONN.delete_if_equal(self.lock_key, self.lock_value)
        while True:
            try:
                if self.lock.acquire(token=self.lock_value):
                    break
            except Exception as e:
                if "MOVED" in str(e) and REDIS_CONN.is_cluster:
                    if REDIS_CONN._handle_cluster_redirect(str(e), self.lock_key):
                        # 重新创建锁对象
                        slot = REDIS_CONN._get_key_slot(self.lock_key)
                        cached_node = REDIS_CONN._get_node_for_slot(slot)
                        if cached_node:
                            host, port = cached_node
                            target_connection = REDIS_CONN._get_connection_for_node(host, port)
                            if target_connection:
                                self.lock = Lock(target_connection, self.lock_key, timeout=self.timeout, blocking_timeout=1)
            await trio.sleep(10)

    def release(self):
        REDIS_CONN.delete_if_equal(self.lock_key, self.lock_value)
