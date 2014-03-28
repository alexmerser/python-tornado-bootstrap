# coding: utf-8
import os
import urllib

import tornado.web
from mongoengine import DoesNotExist

from apps.accounts.models import User
import connect_redis

redis_connection = connect_redis.connect_to_redis()


class BaseHandler(tornado.web.RequestHandler):
    def check_permission(self, action):
        user = self.get_current_user()
        admin = self.is_admin_user()
        if action in self.perm_public or (user and action in self.perm_user) or (admin and action in self.perm_admin):
            pass # ok
        else:
            self.raise403()

    def raise400(self):
        raise tornado.web.HTTPError(400, 'Invalid request')

    def raise401(self):
        raise tornado.web.HTTPError(401, 'Not enough permissions to perform this action')

    def raise403(self):
        raise tornado.web.HTTPError(403, 'Not enough permissions to perform this action')

    def raise404(self):
        raise tornado.web.HTTPError(404, 'Object not found')

    def raise422(self):
        raise tornado.web.HTTPError(422, 'Invalid request')

    def get_current_user(self):
        email = self.get_secure_cookie('user')
        if email is None:
            return None
        return User.objects(email=email).first()

    def is_admin_user(self):
        user = self.get_current_user()
        return user and user.admin

    def redirect(self, url, alert=None, alert_type=None, permanent=False, status=None):
        if alert:
            alert = urllib.pathname2url(alert)
            url = '%s?alert=%s' % (url, alert)
            if alert_type:
                url = '%s&alert_type=%s' % (url, alert_type)
        super(BaseHandler, self).redirect(url, permanent=permanent, status=status)

    def render(self, template_name, **kwargs):
        if 'alert' not in kwargs:
            kwargs['alert'] = self.get_argument('alert', None)
        if 'alert_type' not in kwargs:
            # alert-success, alert-info, alert-warning, alert-danger
            kwargs['alert_type'] = self.get_argument('alert_type', 'alert-info')
        if 'current_user' not in kwargs:
            kwargs['current_user'] = self.get_current_user()

        kwargs['SYSTEM_NAME'] = os.getenv('SYSTEM_NAME')
        kwargs['SYSTEM_EMAIL'] = os.getenv('SYSTEM_EMAIL')
        kwargs['SYSTEM_URL'] = os.getenv('SYSTEM_URL')
        kwargs['DOMAIN'] = os.getenv('DOMAIN')
        kwargs['DATE_FORMAT'] = os.getenv('DATE_FORMAT')
        kwargs['TIME_FORMAT'] = os.getenv('TIME_FORMAT')
        kwargs['DATETIME_FORMAT'] = os.getenv('DATETIME_FORMAT')

        kwargs['GOOGLE_ANALYTICS'] = os.getenv('GOOGLE_ANALYTICS')
        kwargs['GITHUB_ACCOUNT'] = os.getenv('GITHUB_ACCOUNT')
        kwargs['TWITTER_ACCOUNT'] = os.getenv('TWITTER_ACCOUNT')
        kwargs['FACEBOOK_ACCOUNT'] = os.getenv('FACEBOOK_ACCOUNT')
        kwargs['FACEBOOK_API_KEY'] = os.getenv('FACEBOOK_API_KEY')
        kwargs['GOOGLE_PLUS_ACCOUNT'] = os.getenv('GOOGLE_PLUS_ACCOUNT')
        kwargs['SKYPE_ACCOUNT'] = os.getenv('SKYPE_ACCOUNT')
        return super(BaseHandler, self).render(template_name, **kwargs)


class ImageHandler(BaseHandler):
    def get_image(self, identifier, index=0):
        return None

    def get(self, identifier, index=0):
        try:
            index = int(index)
            img = self.get_image(identifier, index)
            if img:
                if img.content_type:
                    self.set_header('Content-type', img.content_type)
                self.write(img.read())
            self.finish()
        except (DoesNotExist, IndexError):
            self.raise404()


class AuthenticatedBaseHandler(BaseHandler):
    LOGIN_MSG = 'You have to login first. It is simple and fast.'
    ADMIN_PERMISSION = False

    def prepare(self):
        super(AuthenticatedBaseHandler, self).prepare()
        user = self.get_current_user()
        if not user:
            alert = self.LOGIN_MSG
            url = self.settings.get('login_url', '/')
            self.redirect(url, alert=alert, alert_type='alert-warning')
        elif self.ADMIN_PERMISSION and not user.admin:
            self.raise403()
        elif (not user.admin) and (not self.user_has_permission()):
            self.raise403()

    def user_has_permission(self):
        # Tornado hack to get identifier begore GET/POST
        # identifier = self.request.path replace/split/etc
        return True


class CachedBaseHandler(BaseHandler):
    expire_timeout = 60 * 60 * 24 # in seconds

    def prepare(self):
        super(CachedBaseHandler, self).prepare()
        dev_mode = 'localhost' in self.request.host
        ignore_cache = self.get_argument('ignore_cache', None)
        if not ignore_cache and not dev_mode:
            cached = redis_connection.get(self.request.uri)
            if cached is not None:
                # print('Read cached page for %s' % self.request.uri)
                self.write(cached)
                self.finish()

    def render_string(self, template_name, **kwargs):
        html_generated = super(CachedBaseHandler, self).render_string(template_name, **kwargs)
        # redis_connection.setex(self.request.uri, self.expire_timeout, html_generated)
        redis_connection.set(self.request.uri, html_generated)
        redis_connection.expire(self.request.uri, self.expire_timeout)
        # print('Page %s cached' % self.request.uri)
        return html_generated


class ObjectHandlerMixin(object):
    model = None
    template = ''
    template_list = ''
    var = 'obj'
    var_list = 'objs'
    CHECK_USER = False

    def get(self, identifier=None):
        user = self.get_current_user()
        if identifier:
            try:
                objs = self.model.objects.filter(id=identifier)
                if self.CHECK_USER:
                    obj = objs.filter(user=user).get()
                else:
                    obj = objs.get()
                template_vars = {self.var: obj}
                self.render(self.template, **template_vars)
            except self.model.DoesNotExist:
                self.raise404()
        else:
            objs = self.model.objects
            if self.CHECK_USER:
                objs = objs.filter(user=user)
            template_vars = {self.var_list: obj}
            self.render(self.template_list, **template_vars)
