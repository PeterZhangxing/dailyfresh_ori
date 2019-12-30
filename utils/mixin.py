from django.contrib.auth.decorators import login_required


class LoginRequiredMixin(object):

    @classmethod
    def as_view(cls,**initkwargs):
        view = super(LoginRequiredMixin,cls).as_view(**initkwargs)

        # 如果范文用户没有登录,将用户重定向到setting中定义的LOGIN_URL='/user/login'
        return login_required(view)