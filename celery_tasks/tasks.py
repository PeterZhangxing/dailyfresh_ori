import os

# 初始化dlango的运行环境,不启动项目,要使用项目中的变量就必须初始化
# import django
# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dailyfresh.settings")
# django.setup()

from django.core.mail import send_mail
from django.conf import settings
from django.template import loader,RequestContext
from celery import Celery

from goods.models import GoodsType, GoodsSKU, IndexGoodsBanner,IndexPromotionBanner,IndexTypeGoodsBanner


app = Celery('celery_task.tasks',broker='redis://10.1.1.128:6379/9')

@app.task
def send_reg_active_mail(to_email, username, token):
    subject = '天天生鲜欢迎信息'
    message = ''
    sender = settings.EMAIL_FROM
    receiver = [to_email]
    html_message = '<a href="http://127.0.0.1:8000/user/active/%s"><h1>%s,欢迎您成为天天生鲜注册会员,点击激活您的账户</h1></a>' % (token, username)
    send_mail(subject, message, sender, receiver, html_message=html_message)


@app.task
def generate_static_index_html():
    '''产生首页静态页面,不包含用户信息,给第一次访问站点的大量用户使用'''

    # 获取商品的种类信息
    types = GoodsType.objects.all()

    # 获取首页轮播商品信息
    goods_banners = IndexGoodsBanner.objects.all().order_by('index')

    # 获取首页促销活动信息
    promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

    # 获取首页分类商品展示信息,并给每个分类添加此分类下要展示的商品
    for ctype in types:
        ctype.image_banners = IndexTypeGoodsBanner.objects.filter(type=ctype, display_type=1).order_by('index')
        ctype.title_banners = IndexTypeGoodsBanner.objects.filter(type=ctype, display_type=0).order_by('index')

    context = {
        'types': types,
        'goods_banners': goods_banners,
        'promotion_banners': promotion_banners
    }

    # 获取并渲染模板,生成静态页面
    temp = loader.get_template('static_index.html')
    static_index_html = temp.render(context)

    # 生成首页对应静态文件
    static_index_html_path = os.path.join(settings.BASE_DIR,'static/index.html')
    with open(static_index_html_path,'w',encoding='utf-8') as f:
        f.write(static_index_html)