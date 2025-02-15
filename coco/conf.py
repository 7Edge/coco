#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

"""
    coco.config
    ~~~~~~~~~~~~

    the configuration related objects.
    copy from flask

    :copyright: (c) 2015 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""

import os
import sys
import types
import errno
import json
import socket
import yaml

from werkzeug.utils import import_string


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
root_path = os.environ.get("COCO_PATH")
if not root_path:
    root_path = BASE_DIR


class ConfigAttribute(object):
    """Makes an attribute forward to the config"""

    def __init__(self, name, get_converter=None):
        self.__name__ = name
        self.get_converter = get_converter

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        rv = obj.config[self.__name__]
        if self.get_converter is not None:
            rv = self.get_converter(rv)
        return rv

    def __set__(self, obj, value):
        obj.config[self.__name__] = value


class Config(dict):
    """Works exactly like a dict but provides ways to fill it from files
    or special dictionaries.  There are two common patterns to populate the
    config.

    Either you can fill the config from a config file::

        app.config.from_pyfile('yourconfig.cfg')

    Or alternatively you can define the configuration options in the
    module that calls :meth:`from_object` or provide an import path to
    a module that should be loaded.  It is also possible to tell it to
    use the same module and with that provide the configuration values
    just before the call::

        DEBUG = True
        SECRET_KEY = 'development key'
        app.config.from_object(__name__)

    In both cases (loading from any Python file or loading from modules),
    only uppercase keys are added to the config.  This makes it possible to use
    lowercase values in the config file for temporary values that are not added
    to the config or to define the config keys in the same file that implements
    the application.

    Probably the most interesting way to load configurations is from an
    environment variable pointing to a file::

        app.config.from_envvar('YOURAPPLICATION_SETTINGS')

    In this case before launching the application you have to set this
    environment variable to the file you want to use.  On Linux and OS X
    use the export statement::

        export YOURAPPLICATION_SETTINGS='/path/to/config/file'

    On windows use `set` instead.

    :param root_path: path to which files are read relative from.  When the
                      config object is created by the application, this is
                      the application's :attr:`~flask.Flask.root_path`.
    :param defaults: an optional dictionary of default values
    """

    def __init__(self, root_path, defaults=None):
        self.defaults = defaults or {}
        self.root_path = root_path
        super(Config, self).__init__({})

    def from_envvar(self, variable_name, silent=False):
        """Loads a configuration from an environment variable pointing to
        a configuration file.  This is basically just a shortcut with nicer
        error messages for this line of code::

            app.config.from_pyfile(os.environ['YOURAPPLICATION_SETTINGS'])

        :param variable_name: name of the environment variable
        :param silent: set to ``True`` if you want silent failure for missing
                       files.
        :return: bool. ``True`` if able to load config, ``False`` otherwise.
        """
        rv = os.environ.get(variable_name)
        if not rv:
            if silent:
                return False
            raise RuntimeError('The environment variable %r is not set '
                               'and as such configuration could not be '
                               'loaded.  Set this variable and make it '
                               'point to a configuration file' %
                               variable_name)
        return self.from_pyfile(rv, silent=silent)

    def from_pyfile(self, filename, silent=False):
        """Updates the values in the config from a Python file.  This function
        behaves as if the file was imported as module with the
        :meth:`from_object` function.

        :param filename: the filename of the config.  This can either be an
                         absolute filename or a filename relative to the
                         root path.
        :param silent: set to ``True`` if you want silent failure for missing
                       files.

        .. versionadded:: 0.7
           `silent` parameter.
        """
        filename = os.path.join(self.root_path, filename)
        d = types.ModuleType('config')
        d.__file__ = filename
        try:
            with open(filename, mode='rb') as config_file:
                exec(compile(config_file.read(), filename, 'exec'), d.__dict__)
        except IOError as e:
            if silent and e.errno in (errno.ENOENT, errno.EISDIR):
                return False
            e.strerror = 'Unable to load configuration file (%s)' % e.strerror
            raise
        self.from_object(d)
        return True

    def from_object(self, obj):
        """Updates the values from the given object.  An object can be of one
        of the following two types:

        -   a string: in this case the object with that name will be imported
        -   an actual object reference: that object is used directly

        Objects are usually either modules or classes. :meth:`from_object`
        loads only the uppercase attributes of the module/class. A ``dict``
        object will not work with :meth:`from_object` because the keys of a
        ``dict`` are not attributes of the ``dict`` class.

        Example of module-based configuration::

            app.config.from_object('yourapplication.default_config')
            from yourapplication import default_config
            app.config.from_object(default_config)

        You should not use this function to load the actual configuration but
        rather configuration defaults.  The actual config should be loaded
        with :meth:`from_pyfile` and ideally from a location not within the
        package because the package might be installed system wide.

        See :ref:`config-dev-prod` for an example of class-based configuration
        using :meth:`from_object`.

        :param obj: an import name or object
        """
        if isinstance(obj, str):
            obj = import_string(obj)
        for key in dir(obj):
            if key.isupper():
                self[key] = getattr(obj, key)

    def from_json(self, filename, silent=False):
        """Updates the values in the config from a JSON file. This function
        behaves as if the JSON object was a dictionary and passed to the
        :meth:`from_mapping` function.

        :param filename: the filename of the JSON file.  This can either be an
                         absolute filename or a filename relative to the
                         root path.
        :param silent: set to ``True`` if you want silent failure for missing
                       files.

        .. versionadded:: 0.11
        """
        filename = os.path.join(self.root_path, filename)

        try:
            with open(filename) as json_file:
                obj = json.loads(json_file.read())
        except IOError as e:
            if silent and e.errno in (errno.ENOENT, errno.EISDIR):
                return False
            e.strerror = 'Unable to load configuration file (%s)' % e.strerror
            raise
        return self.from_mapping(obj)

    def from_yaml(self, filename, silent=False):
        if self.root_path:
            filename = os.path.join(self.root_path, filename)
        try:
            with open(filename) as f:
                obj = yaml.safe_load(f)
        except IOError as e:
            if silent and e.errno in (errno.ENOENT, errno.EISDIR):
                return False
            e.strerror = 'Unable to load configuration file (%s)' % e.strerror
            raise
        if obj:
            return self.from_mapping(obj)
        return True

    def from_mapping(self, *mapping, **kwargs):
        """Updates the config like :meth:`update` ignoring items with non-upper
        keys.

        .. versionadded:: 0.11
        """
        mappings = []
        if len(mapping) == 1:
            if hasattr(mapping[0], 'items'):
                mappings.append(mapping[0].items())
            else:
                mappings.append(mapping[0])
        elif len(mapping) > 1:
            raise TypeError(
                'expected at most 1 positional argument, got %d' % len(mapping)
            )
        mappings.append(kwargs.items())
        for mapping in mappings:
            for (key, value) in mapping:
                if key.isupper():
                    self[key] = value
        return True

    def get_namespace(self, namespace, lowercase=True, trim_namespace=True):
        """Returns a dictionary containing a subset of configuration options
        that match the specified namespace/prefix. Example usage::

            app.config['IMAGE_STORE_TYPE'] = 'fs'
            app.config['IMAGE_STORE_PATH'] = '/var/app/images'
            app.config['IMAGE_STORE_BASE_URL'] = 'http://img.website.com'
            image_store_config = app.config.get_namespace('IMAGE_STORE_')

        The resulting dictionary `image_store_config` would look like::

            {
                'types': 'fs',
                'path': '/var/app/images',
                'base_url': 'http://img.website.com'
            }

        This is often useful when configuration options map directly to
        keyword arguments in functions or class constructors.

        :param namespace: a configuration namespace
        :param lowercase: a flag indicating if the keys of the resulting
                          dictionary should be lowercase
        :param trim_namespace: a flag indicating if the keys of the resulting
                          dictionary should not include the namespace

        .. versionadded:: 0.11
        """
        rv = {}
        for k, v in self.items():
            if not k.startswith(namespace):
                continue
            if trim_namespace:
                key = k[len(namespace):]
            else:
                key = k
            if lowercase:
                key = key.lower()
            rv[key] = v
        return rv

    def convert_type(self, k, v):
        default_value = self.defaults.get(k)
        if default_value is None:
            return v
        tp = type(default_value)
        # 对bool特殊处理
        if tp is bool and isinstance(v, str):
            if v in ("true", "True", "1"):
                return True
            else:
                return False
        if tp in [list, dict] and isinstance(v, str):
            try:
                v = json.loads(v)
                return v
            except json.JSONDecodeError:
                return v

        try:
            v = tp(v)
        except Exception:
            pass
        return v

    def __getitem__(self, item):
        # 先从设置的来
        try:
            value = super().__getitem__(item)
        except KeyError:
            value = None
        if value is not None:
            return value
        # 其次从环境变量来
        value = os.environ.get(item, None)
        if value is not None:
            return self.convert_type(item, value)
        return self.defaults.get(item)

    def __getattr__(self, item):
        return self.__getitem__(item)

    def __setattr__(self, key, value):
        return self.__setitem__(key, value)

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, dict.__repr__(self))


access_key_path = os.path.abspath(
    os.path.join(root_path, 'data', 'keys', '.access_key')
)
host_key_path = os.path.abspath(
    os.path.join(root_path, 'data', 'keys', 'host_rsa_key')
)
defaults = {
    'NAME': socket.gethostname(),
    'CORE_HOST': 'http://127.0.0.1:8080',
    'BOOTSTRAP_TOKEN': '',
    'ROOT_PATH': root_path,
    'DEBUG': True,
    'BIND_HOST': '0.0.0.0',
    'SSHD_PORT': 2222,
    'HTTPD_PORT': 5000,
    'COCO_ACCESS_KEY': '',
    'ACCESS_KEY_FILE': access_key_path,
    'HOST_KEY_FILE': host_key_path,
    'SECRET_KEY': 'SDK29K03%MM0ksf&#2',
    'LOG_LEVEL': 'INFO',
    'LOG_DIR': os.path.join(root_path, 'data', 'logs'),
    'REPLAY_DIR': os.path.join(root_path, 'data', 'replays'),
    'ASSET_LIST_SORT_BY': 'hostname',  # hostname, ip
    'TELNET_REGEX': '',
    'PASSWORD_AUTH': True,
    'PUBLIC_KEY_AUTH': True,
    'SSH_TIMEOUT': 15,
    'ALLOW_SSH_USER': [],
    'BLOCK_SSH_USER': [],
    'HEARTBEAT_INTERVAL': 20,
    'MAX_CONNECTIONS': 500,  # Not use now
    'ADMINS': '',
    'COMMAND_STORAGE': {'TYPE': 'server'},   # server
    'REPLAY_STORAGE': {'TYPE': 'server'},
    'LANGUAGE_CODE': 'zh',
    'SECURITY_MAX_IDLE_TIME': 60,
    'ASSET_LIST_PAGE_SIZE': 'auto',
    'SFTP_ROOT': '/tmp',
    'SFTP_SHOW_HIDDEN_FILE': False,
    'UPLOAD_FAILED_REPLAY_ON_START': True,
    'REUSE_CONNECTION': True,
}


def load_from_object(config):  # 如果有conf.py模块，从conf模块的config对象中加载其大写属性作为配置。这个类似Flask但是指定了config对象名。
    try:
        from conf import config as c
        config.from_object(c)
        return True
    except ImportError:
        pass
    return False


def load_from_yml(config):
    for i in ['config.yml', 'config.yaml']:
        if not os.path.isfile(os.path.join(config.root_path, i)):
            continue
        loaded = config.from_yaml(i)
        if loaded:
            return True
    return False


def load_user_config():  # 加载配置文件，实例化Config对象
    sys.path.insert(0, root_path)  # root_path默认就是coco项目目录
    config = Config(root_path, defaults)  # 实例化Config对象，默认时defaults配置

    loaded = load_from_object(config)  # 从对象中更新配置
    if not loaded:
        loaded = load_from_yml(config)  # 如果对象更新失败，那么从yml文件更新
    if not loaded:  # 都根棍失败的话，报错
        msg = """

        Error: No config file found.

        You can run `cp config_example.yml config.yml`, and edit it.
        """
        raise ImportError(msg)
    return config


config = load_user_config()  # 加载配置文件，

# 主要是兼容新旧path的处理

old_host_key_path = os.path.join(root_path, 'keys', 'host_rsa_key')
old_access_key_path = os.path.join(root_path, 'keys', '.access_key')

if os.path.isfile(old_host_key_path) and not os.path.isfile(config.HOST_KEY_FILE):
    config.HOST_KEY_FILE = old_host_key_path

if os.path.isfile(old_access_key_path) and not os.path.isfile(config.ACCESS_KEY_FILE):
    config.ACCESS_KEY_FILE = old_access_key_path
