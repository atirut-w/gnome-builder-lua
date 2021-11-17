# These codes are based on Builder's TypeScript language server extension:
# https://gitlab.gnome.org/GNOME/gnome-builder/-/blob/main/src/plugins/ts-language-server/ts_language_server_plugin.py

import gi

from gi.repository import GLib
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import Ide

DEV_MODE = True

class LuaService(Ide.Object):
    _client = None
    _has_started = False
    _supervisor = None

    @classmethod
    def from_context(klass, context):
        return context.ensure_child_typed(LuaService)

    @GObject.Property(type=Ide.LspClient)
    def client(self):
        return self._client

    @client.setter
    def client(self, value):
        self._client = value
        self.notify('client')

    def do_stop(self):
        if self._supervisor:
            supervisor, self._supervisor = self._supervisor, None
            supervisor.stop()

    def _ensure_started(self):
        # To avoid starting the process unconditionally at startup, lazily
        # start it when the first provider tries to bind a client to its
        # :client property.
        if not self._has_started:
            self._has_started = True

            launcher = self._create_launcher()
            launcher.set_clear_env(False)

            # Locate the directory of the project and run lua-language-server from there
            workdir = self.get_context().ref_workdir()
            launcher.set_cwd(workdir.get_path())

            # this needs https://github.com/sumneko/lua-language-server installed on the host
            launcher.push_argv("lua-language-server")
            # launcher.push_argv("--stdio")

            # Spawn our peer process and monitor it for
            # crashes. We may need to restart it occasionally.
            self._supervisor = Ide.SubprocessSupervisor()
            self._supervisor.connect('spawned', self._ls_spawned)
            self._supervisor.set_launcher(launcher)
            self._supervisor.start()

    def _ls_spawned(self, supervisor, subprocess):
        stdin = subprocess.get_stdin_pipe()
        stdout = subprocess.get_stdout_pipe()
        io_stream = Gio.SimpleIOStream.new(stdout, stdin)

        if self._client:
            self._client.stop()
            self._client.destroy()

        self._client = Ide.LspClient.new(io_stream)
        self.append(self._client)
        self._client.add_language('lua')
        self._client.start()
        self.notify('client')

    def _create_launcher(self):
        flags = Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE
        if not DEV_MODE:
            flags |= Gio.SubprocessFlags.STDERR_SILENCE
        launcher = Ide.SubprocessLauncher()
        launcher.set_flags(flags)
        return launcher

    @classmethod
    def bind_client(klass, provider):
        context = provider.get_context()
        self = LuaService.from_context(context)
        self._ensure_started()
        self.bind_property('client', provider, 'client', GObject.BindingFlags.SYNC_CREATE)

class LuaDiagnosticProvider(Ide.LspDiagnosticProvider, Ide.DiagnosticProvider):
    def do_load(self):
        LuaService.bind_client(self)

class LuaCompletionProvider(Ide.LspCompletionProvider, Ide.CompletionProvider):
    def do_load(self, context):
        LuaService.bind_client(self)

    def do_get_priority(self, context):
        # This provider only activates when it is very likely that we
        # want the results. So use high priority (negative is better).
        return -1000

class LuaSymbolResolver(Ide.LspSymbolResolver, Ide.SymbolResolver):
    def do_load(self):
        LuaService.bind_client(self)

class LuaHighlighter(Ide.LspHighlighter, Ide.Highlighter):
    def do_load(self):
        LuaService.bind_client(self)

class LuaFormatter(Ide.LspFormatter, Ide.Formatter):
    def do_load(self):
        LuaService.bind_client(self)

class LuaHoverProvider(Ide.LspHoverProvider, Ide.HoverProvider):
    def do_prepare(self):
        self.props.category = 'Lua'
        self.props.priority = 200
        LuaService.bind_client(self)

class LuaRenameProvider(Ide.LspRenameProvider, Ide.RenameProvider):
    def do_load(self):
        LuaService.bind_client(self)

# Error: AttributeError: 'gi.repository.Ide' object has no attribute 'LspCodeActionProvider'
# class LuaCodeActionProvider(Ide.LspCodeActionProvider, Ide.CodeActionProvider):
#     def do_load(self):
#         LuaService.bind_client(self)

