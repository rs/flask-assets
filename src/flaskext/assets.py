from os import path
from flask import _request_ctx_stack, url_for
from webassets import Bundle
from webassets.env import BaseEnvironment, ConfigStorage


__version__ = (0, 2, 'dev')

__all__ = ('Environment', 'Bundle',)


class FlaskConfigStorage(ConfigStorage):
    """Uses the config object of a Flask app as the backend: either the app
    instance bound to the extension directly, or the current Flasp app on
    the stack.

    Also provides per-application defaults for some values.

    Note that if no app is available, this config object is basically
    unusable - this is by design; this could also let the user set defaults
    by writing to a container not related to any app, which would be used
    as a fallback if a current app does not include a key. However, at least
    for now, I specifically made the choice to keep things simple and not
    allow global across-app defaults.
    """

    _mapping = [
        'debug', 'cache', 'updater', 'auto_create', 'expire', 'directory', 'url',]

    def __init__(self, *a, **kw):
        self._defaults = {}
        ConfigStorage.__init__(self, *a, **kw)

    def _transform_key(self, key):
        if key.lower() in self._mapping:
            return "ASSETS_%s" % key.upper()
        else:
            return key.upper()

    @property
    def _app(self):
        """The application object to work with; this is either the app
        that we have been bound to, or the current application.
        """
        if self.env.app is not None:
            return self.env.app
        else:
            ctx = _request_ctx_stack.top
            if ctx is not None:
                return ctx.app
        raise RuntimeError('assets instance not bound to an application, '+
                           'and no application in current context')

    def _app_default_url(self):
        # By default use url_for with static endpoint (see Environment.absurl)
        return None

    def _app_default_directory(self):
        return self._app.root_path + self._app.static_path

    def setdefault(self, key, value):
        """We may not always be connected to an app, but we still need
        to provide a way to the base environment to set it's defaults.
        """
        try:
            super(FlaskConfigStorage, self).setdefault(key, value)
        except RuntimeError:
            self._defaults.__setitem__(key, value)

    def __contains__(self, key):
        return self._transform_key(key) in self._app.config

    def __getitem__(self, key):
        # First try the current app's config
        public_key = self._transform_key(key)
        if self._app:
            if public_key in self._app.config:
                return self._app.config[public_key]

        # Try a non-app specific default value
        if key in self._defaults:
            return self._defaults.__getitem__(key)

        # Finally try to use a default based on the current app
        deffunc = getattr(self, "_app_default_%s" % key, False)
        if deffunc:
            return deffunc()

        # We've run out of options
        raise KeyError()

    def __setitem__(self, key, value):
        self._app.config[self._transform_key(key)] = value

    def __delitem__(self, key):
        del self._app.config[self._transform_key(key)]


class Environment(BaseEnvironment):

    config_storage_class = FlaskConfigStorage

    def __init__(self, app=None):
        self.app = app
        super(Environment, self).__init__()
        if app:
            self.init_app(app)

    def absurl(self, fragment):
        if self.url is not None:
            return super(Environment, self).absurl(fragment)
        else:
            try:
                filename, query = fragment.split('?', 1)
                query = '?' + query
            except (ValueError):
                filename = fragment
                query = ''
            try:
                module, name = filename.split('/', 1)
                self.app.modules[module] # generates keyerror if no module
                endpoint = '%s.static' % module
                filename = name
            except (ValueError, KeyError):
                endpoint = '.static'
            return url_for(endpoint, filename=filename) + query

    def abspath(self, filename):
        if path.isabs(filename):
            return filename
        try:
            module, name = filename.split('/', 1)
            directory = self.app.modules[module].root_path + self.app.static_path
            filename = name
        except (ValueError, KeyError):
            directory = self.directory
        return path.abspath(path.join(directory, filename))

    def init_app(self, app):
        app.jinja_env.add_extension('webassets.ext.jinja2.AssetsExtension')
        app.jinja_env.assets_environment = self


try:
    from flaskext import script
except ImportError:
    pass
else:
    class ManageAssets(script.Command):
        """Manage assets."""

        def __init__(self, assets_env):
            self.env = assets_env

        def handle(self, app, prog, name, remaining_args):
            from webassets import script
            script.main(remaining_args, env=self.env)

    __all__ = __all__ + ('ManageAssets',)