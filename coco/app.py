#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

import datetime
import os
import time
import threading
import json
import signal
import copy

from .conf import config
from .sshd import SSHServer
from .httpd import HttpServer
from .tasks import TaskHandler
from .utils import (
    get_logger, ugettext as _, ignore_error,
)
from .service import app_service
from .recorder import get_replay_recorder
from .session import Session
from .models import Connection


__version__ = '1.5.0'

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
logger = get_logger(__file__)  # 日志对象，继承自coco.主logger加载都是在coco.__init__.py文件中


class Coco:  # 主类
    def __init__(self):
        self.lock = threading.Lock()  # 线程锁
        self.stop_evt = threading.Event()  # 信号灯作用，进程级，多线程间控制与查看Event状态来工作
        self._service = None
        self._sshd = None
        self._httpd = None
        self.replay_recorder_class = None
        self.command_recorder_class = None
        self._task_handler = None
        self.first_load_extra_conf = True

    @property
    def sshd(self):  # ssh-server
        if self._sshd is None:
            self._sshd = SSHServer()
        return self._sshd

    @property
    def httpd(self):  # websocket-server
        if self._httpd is None:
            self._httpd = HttpServer()
        return self._httpd

    @property
    def task_handler(self):
        if self._task_handler is None:
            self._task_handler = TaskHandler()  # 初始化TaskHandler对象，
        return self._task_handler

    @ignore_error  # 报错记录日志中，线程不停
    def load_extra_conf_from_server(self):  # 从jumpserver restful api 获取terminal-config相关配置；然后更新到本地config对象中。
        configs = app_service.load_config_from_server()
        config.update(configs)

        tmp = copy.deepcopy(configs)
        tmp['HOST_KEY'] = tmp.get('HOST_KEY', '')[32:50] + '...'  # host_key属于安全数据，截取部分打印到日志中。
        if self.first_load_extra_conf:  # 加载额外的启动时加载文件，只加载一次。
            logger.debug("Loading config from server: {}".format(
                json.dumps(tmp)
            ))
            self.first_load_extra_conf = False

    def keep_load_extra_conf(self):  # 开启一个热加载额外配置线程，十分钟加载一次。
        def func():
            while True:
                self.load_extra_conf_from_server()
                time.sleep(60*10)
        thread = threading.Thread(target=func)
        thread.start()

    def bootstrap(self):  # 启动coco服务的引导过程：
        self.load_extra_conf_from_server()  # 1. 加载jms的相关配置，加载first_load_extra_conf
        self.keep_load_extra_conf()  # 2. 启动extra线程轮询热加载配置
        self.keep_heartbeat()  # 3. 启动心跳线程，目的：a) jms是否正常工作 b) 发送当前所有会话列表给后端，接受对会话的处理任务列表，然后进行处理。
        self.monitor_sessions()  # 4. 启动监控会话线程（保姆线程）, 检测周期同心跳配置周期时长。
        if config.UPLOAD_FAILED_REPLAY_ON_START:  # tmp_q04: 这是干嘛的？
            self.upload_failed_replay()

    # @ignore_error
    def heartbeat(self):  # 向jms发送心跳，心跳作用：让jms每一个终端会话是断开还是连接状态。
        sessions = list(Session.sessions.keys())  # 从Session中获取到所有会话的key
        data = {
            'sessions': sessions,
        }
        tasks = app_service.terminal_heartbeat(data)  # 发送的数据时所有会话的keys,而返回的是termianl_task对象列表。tmp_q03:terminal和session 有什么区别？

        if tasks:  # 对于心跳的会话，jms返回告知有任务需要处理。
            self.handle_task(tasks)  # 对任务列表进行相应的处理，通过task_handler对象
        if tasks is False:
            return False
        else:
            return True

    def heartbeat_async(self):  # 异步心跳
        t = threading.Thread(target=self.heartbeat)
        t.start()

    def handle_task(self, tasks):
        for task in tasks:
            self.task_handler.handle(task)

    def keep_heartbeat(self):  # 心跳线程：coco组件向jms restful心跳
        def func():
            while not self.stop_evt.is_set():  # event状态时False时进行心跳。
                try:
                    self.heartbeat()
                except IndexError as e:
                    logger.error("Unexpected error occur: {}".format(e))
                time.sleep(config["HEARTBEAT_INTERVAL"])  # 心跳间隔时长，但是下次心跳必须stop_evt状态时False才进行。tmp_q01：为什么心跳线程要受stop_evt控制？哪个线程在控制？
        thread = threading.Thread(target=func)
        thread.start()

    @staticmethod
    def upload_failed_replay():  # tmp_q02: 这个什么玩意儿？
        replay_dir = os.path.join(config.REPLAY_DIR)

        def retry_upload_replay(session_id, file_gz_path, target):
            recorder = get_replay_recorder()
            recorder.file_gz_path = file_gz_path
            recorder.session_id = session_id
            recorder.target = target
            recorder.upload_replay()

        def check_replay_is_need_upload(full_path):
            filename = os.path.basename(full_path)
            suffix = filename.split('.')[-1]
            if suffix != 'gz':
                return False
            session_id = filename.split('.')[0]
            if len(session_id) != 36:
                return False
            return True

        def func():
            if not os.path.isdir(replay_dir):
                return
            for d in os.listdir(replay_dir):
                date_path = os.path.join(replay_dir, d)
                for filename in os.listdir(date_path):
                    full_path = os.path.join(date_path, filename)
                    session_id = filename.split('.')[0]
                    # 检查是否需要上传
                    if not check_replay_is_need_upload(full_path):
                        continue
                    logger.debug("Retry upload retain replay: {}".format(filename))
                    target = os.path.join(d, filename)
                    retry_upload_replay(session_id, full_path, target)
                    time.sleep(1)
        thread = threading.Thread(target=func)
        thread.start()

    def monitor_sessions(self):
        interval = config["HEARTBEAT_INTERVAL"]

        def check_session_idle_too_long(s):
            delta = datetime.datetime.utcnow() - s.date_last_active  # 获取最近一次或与时间点与现在时间点的时长。
            max_idle_seconds = config['SECURITY_MAX_IDLE_TIME'] * 60  # 配置文件的最长空闲时长。
            if delta.seconds > max_idle_seconds:
                msg = _(
                    "Connect idle more than {} minutes, disconnect").format(
                    config['SECURITY_MAX_IDLE_TIME']
                )
                s.terminate(msg=msg)
                return True

        def func():
            while not self.stop_evt.is_set():  # 同心跳线程一样，对stop_evt事件为False才执行。
                try:
                    sessions_copy = [s for s in Session.sessions.values()]  # 所有coco活跃的session对象的拷贝
                    for s in sessions_copy:
                        # Session 没有正常关闭,
                        if s.closed_unexpected:  # 处理异常关闭的session对象。
                            Session.remove_session(s.id)
                            continue
                        # Session已正常关闭
                        if s.closed:  # 正常关闭的session对象从列表中移除。
                            Session.remove_session(s.id)
                        else:
                            check_session_idle_too_long(s)  # 检查session空闲事件，如果空闲太长进行处理。
                except Exception as e:
                    logger.error("Unexpected error occur: {}".format(e))
                    logger.error(e, exc_info=True)
                time.sleep(interval)
        thread = threading.Thread(target=func)
        thread.start()

    def run_forever(self):  # 启动入口：执行力入口前已经完成了的工作：app_service的初始化；config配置对象实例化；
        self.bootstrap()  # 1. 完成启动引导过程： 加载获取jms端配置数据；启动extra持续加载线程；启动心跳线程；
        print(time.ctime())
        print('Coco version {}, more see https://www.jumpserver.org'.format(__version__))
        print('Quit the server with CONTROL-C.')

        try:
            if config["SSHD_PORT"] != 0:  # 启动ssh server 线程
                self.run_sshd()

            if config['HTTPD_PORT'] != 0:  # 启动ws server 线程
                self.run_httpd()

            signal.signal(signal.SIGTERM, lambda x, y: self.shutdown())  # 定义信号处理，收到SIGTERM 9信号,执行平滑shutdown
            self.lock.acquire()
            self.lock.acquire()
        except KeyboardInterrupt:
            self.shutdown()

    def run_sshd(self):
        thread = threading.Thread(target=self.sshd.run, args=())
        thread.daemon = True
        thread.start()

    def run_httpd(self):
        thread = threading.Thread(target=self.httpd.run, args=())
        thread.daemon = True
        thread.start()

    def shutdown(self):
        logger.info("Grace shutdown the server")  # 优雅平滑关闭，处理完所有任务
        for connection in Connection.connections.values():
            connection.close()
        self.heartbeat()  # 进行一次心跳任务处理
        self.lock.release()  # 释放所有锁
        self.stop_evt.set()  # stop_evt设置为True, 不再进行心跳任务和保姆任务
        self.sshd.shutdown()  # 关闭ssh-server
        self.httpd.shutdown()  # 关闭ws-server
