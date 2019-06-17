# -*- coding: utf-8 -*-
#

from jms.service import AppService
from .conf import config


inited = False
app_service = AppService(config)  # 使用coco配置文件，实例化appservice实例

if not inited:
    app_service.initial()  #  初始化，完成auth_class的实例，进行一次认证访问，请求头添加'X-JMS-ORG', 'ROOT'
    inited = True
