"""
Validates all hook registrations in all plugins
"""
import asyncio
import importlib
import inspect
import re
from collections import OrderedDict
from numbers import Number
from pathlib import Path

import pytest

import cloudbot.bot
from cloudbot.event import Event, CommandEvent, RegexEvent, CapEvent, PostHookEvent, IrcOutEvent
from cloudbot.hook import Action
from cloudbot.plugin import Plugin, Hook

Hook.original_init = Hook.__init__

DOC_RE = re.compile(r"^(?:[<{\[][^-]+?[>}\]][^-]+?)*?-\s.+$")
PLUGINS = []


class MockConfig(OrderedDict):
    def get_api_key(self, name, default=None):  # pylint: disable=locally-disabled, no-self-use, unused-argument
        return default  # pragma: no cover


class MockBot:
    loop = None
    user_agent = None

    def __init__(self):
        self.config = MockConfig()


def patch_hook_init(self, _type, plugin, func_hook):
    self.original_init(_type, plugin, func_hook)
    self.func_hook = func_hook


Hook.__init__ = patch_hook_init


def gather_plugins():
    plugin_dir = Path("plugins")
    path_list = plugin_dir.rglob("[!_]*.py")
    return path_list


def load_plugin(plugin_path):
    path = Path(plugin_path)
    file_path = path.resolve()
    file_name = file_path.name
    # Resolve the path relative to the current directory
    plugin_path = file_path.relative_to(Path().resolve())
    title = '.'.join(plugin_path.parts[1:]).rsplit('.', 1)[0]

    module_name = "plugins.{}".format(title)

    plugin_module = importlib.import_module(module_name)

    return Plugin(str(file_path), file_name, title, plugin_module)


def get_plugins():
    if not PLUGINS:
        cloudbot.bot.bot.set(MockBot())
        PLUGINS.extend(map(load_plugin, gather_plugins()))
        cloudbot.bot.bot.set(None)

    return PLUGINS


def pytest_generate_tests(metafunc):
    if 'plugin' in metafunc.fixturenames:  # pragma: no cover
        plugins = get_plugins()
        metafunc.parametrize('plugin', plugins, ids=[plugin.title for plugin in plugins])
    elif 'hook' in metafunc.fixturenames:
        plugins = get_plugins()
        hooks = [hook for plugin in plugins for hook_list in plugin.hooks.values() for hook in hook_list]
        metafunc.parametrize(
            'hook', hooks, ids=["{}.{}".format(hook.plugin.title, hook.function_name) for hook in hooks]
        )


HOOK_ATTR_TYPES = {
    'permissions': (list, set, frozenset, tuple),
    'single_thread': bool,
    'action': Action,
    'priority': int,

    'auto_help': bool,

    'run_on_cmd': bool,
    'only_no_match': bool,

    'interval': Number,
    'initial_interval': Number,
}


@pytest.mark.parametrize('text', [
    '- Foo',
    '<text> - Uses <text>',
    '[text] - Thing with [text]',
])
def test_doc_re_matches(text):
    assert DOC_RE.match(text)


@pytest.mark.parametrize('text', [
    '-- Foo',
    '<text> -- Uses <text>',
    '<text - Uses text>',
    'Foobar',
    '-Baz',
])
def test_doc_re_no_match(text):
    assert not DOC_RE.match(text)


def test_hook_kwargs(hook):
    assert not hook.func_hook.kwargs, \
        "Unknown arguments '{}' passed during registration of hook '{}'".format(
            hook.func_hook.kwargs, hook.function_name
        )

    for name, types in HOOK_ATTR_TYPES.items():
        try:
            attr = getattr(hook, name)
        except AttributeError:
            continue
        else:
            assert isinstance(attr, types), \
                "Unexpected type '{}' for hook attribute '{}'".format(type(attr).__name__, name)


def test_hook_doc(hook):
    if hook.type == "command":
        assert hook.doc

        assert DOC_RE.match(hook.doc), \
            "Invalid docstring '{}' format for command hook".format(hook.doc)

        found_blank = False
        for line in hook.function.__doc__.strip().splitlines():
            stripped = line.strip()
            if stripped.startswith(':'):
                assert found_blank
            elif not stripped:
                found_blank = True


def test_hook_args(hook):
    bot = MockBot()
    if hook.type in ("irc_raw", "perm_check", "periodic", "on_start", "on_stop", "event", "on_connect"):
        event = Event(bot=bot)
    elif hook.type == "command":
        event = CommandEvent(bot=bot, hook=hook, text="", triggered_command="", cmd_prefix='.')
    elif hook.type == "regex":
        event = RegexEvent(bot=bot, hook=hook, match=None)
    elif hook.type.startswith("on_cap"):
        event = CapEvent(bot=bot, cap="")
    elif hook.type == "post_hook":
        event = PostHookEvent(bot=bot)
    elif hook.type == "irc_out":
        event = IrcOutEvent(bot=bot)
    elif hook.type == "sieve":
        return
    else:  # pragma: no cover
        assert False, "Unhandled hook type '{}' in tests".format(hook.type)

    for arg in hook.required_args:
        assert hasattr(event, arg), "Undefined parameter '{}' for hook function".format(arg)


def test_coroutine_hooks(hook):
    if inspect.isgeneratorfunction(hook.function):  # pragma: no cover
        assert asyncio.iscoroutinefunction(hook.function), \
            "Non-coroutine generator function used for a hook. This is most liekly due to incorrect ordering of the " \
            "hook/coroutine decorators."
