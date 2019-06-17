对coco进行二次开发及源码阅读
===
[toc]
> coco提供ssh-server和websocket-server服务，供ssh客户端和ws客户端访问。coco作为网关+代理方式，代理用户完成4A并转发SSH交互。
> 没文档，没注释的情况下进行。。。

## 入口点
从启动coco服务开始::python run_server.py
subprocess.call启动:: cocod start 

## 实际程序coco目录结构
coco/coco/
├── __init__.py
├── app.py          # 核心Coco类，提供一个单例Coco实例；Coco实例是整个coco组件的核心
├── char.py
├── compat.py
├── conf.py         # 配置文件模块，模仿Flask的config模块，config对象单例且类字典
├── connection.py
├── const.py
├── ctx.py
├── exception.py
├── httpd           # 这个应该是基于Flask的Websocket server 模块目录
│   ├── __init__.py
│   ├── app.py
│   ├── auth.py
│   ├── base.py
│   ├── elfinder
│   ├── static
│   ├── templates
│   ├── utils.py
│   ├── view.py
│   └── ws.py
├── interactive.py
├── interface.py
├── logger.py       # 日志模块，第一次导入该模块回创建两个全局logger，名字分别是“coco”和“jms”, 所有其它模块都'继承'自这两个logger
├── models.py
├── proxy.py
├── recorder.py
├── service.py
├── session.py
├── sftp.py
├── sshd.py
├── struct.py
├── tasks.py
└── utils.py

## Coco类






# Jumpserver terminal

Jumpserver terminal is a sub app of Jumpserver.

It's implement a ssh server and a web terminal server, 

User can connect them except jumpserver openssh server and connect.py 
pre version.


## Install

    $ git clone https://github.com/jumpserver/coco.git

## Setting

You need update config.py settings as you need, Be aware of: 

*YOU MUST SET SOME CONFIG THAT CONFIG POINT*

They are:

    NAME:
    JUMPSERVER_URL:
    SECRET_KEY:

Also some config you need kown:
    SSH_HOST:
    SSH_PORT:


## Start

    # python run_server.py

When your start ssh server, It will register with jumpserver api,

Then you need login jumpserver with admin user, active it in <Terminal>
 
 If all done, your can use your ssh tools connect it.
 
ssh user@host:port



