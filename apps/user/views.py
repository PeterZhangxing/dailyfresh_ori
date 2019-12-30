from django.shortcuts import render,HttpResponse,redirect
from django.views.generic import View
from django.urls import reverse
from django.core.mail import send_mail
from django.contrib.auth import authenticate,login,logout
from django.conf import settings
from django.core.paginator import Paginator

from user.models import User,Address
from goods.models import GoodsSKU
from order.models import OrderInfo,OrderGoods

from utils.mixin import LoginRequiredMixin
from celery_tasks.tasks import send_reg_active_mail

from itsdangerous import TimedJSONWebSignatureSerializer as Tjsser
from itsdangerous import SignatureExpired
from django_redis import get_redis_connection
import re

# Create your views here.

class RegisterView(View):
    '''
    完成新用户注册功能
    '''
    def get(self,request):
        return render(request,'register.html')

    def post(self,request):
        # 接收注册数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 完成数据校验
        email_pattern = re.compile(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$')
        if not email_pattern.match(email):
            return render(request, 'register.html', {'errmsg': '邮箱格式不正确'})

        print(allow)
        if allow != 'on':
            return render(request,'register.html',{'errmsg': '请同意协议'})

        try:
            User.objects.get(username=username)
            return render(request, 'register.html', {'errmsg': '用户名已存在'})
        except Exception as e:
            pass

        # 将新用户添加到数据库
        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()

        # 发送激活邮件给用户,让用户激活账户

        # 加密用户id,作为激活凭证
        myser = Tjsser(settings.SECRET_KEY,3600)
        user_info = {'user_id':user.id}
        token = myser.dumps(user_info).decode()

        # 使用celery发送邮件
        send_reg_active_mail.delay(email,username,token)

        # 跳转到首页
        return redirect(reverse('goods:index'))


class ActiveView(View):
    '''
    完成新注册用户激活的功能
    '''
    def get(self,request,token):
        myser = Tjsser(settings.SECRET_KEY, 3600)
        if token is not None:
            try:
                user_id = myser.loads(token).get('user_id')
                # print(user_id)

                try:
                    user = User.objects.get(id=user_id)
                    if user.is_active == 0:
                        user.is_active = 1
                        user.save()
                    return redirect(reverse('user:login'))
                except Exception as e:
                    return HttpResponse('找不到需要激活的用户')
            except SignatureExpired as s:
                return HttpResponse('激活链接已过期')


class LoginView(View):
    '''
    完成用户登录功能
    '''
    def get(self,request):
        username = request.COOKIES.get('username')
        # print(username)
        if username:
            checked = 'checked'
        else:
            username = ''
            checked = ''
        return render(request,'login.html',{'username':username,'checked':checked})

    def post(self,request):
        username = request.POST.get('username')
        password = request.POST.get('pwd')

        if not all([username, password]):
            return render(request, 'login.html', {'errmsg':'数据不完整'})

        # 调用django自带的认证模块，完成用户认证，成功返回用户对象，否则为空
        user = authenticate(username=username,password=password)
        if user:
            if user.is_active:
                # 记录用户的登录状态
                login(request,user)
                next_url = request.GET.get('next',reverse('goods:index'))
                response = redirect(next_url)
                remember = request.POST.get('remember')
                if remember == 'on':
                    response.set_cookie('username',username,max_age=7*24*3600)
                else:
                    response.delete_cookie('username')

                return response
            else:
                return render(request, 'login.html', {'errmsg': '账户未激活'})
        else:
            return render(request, 'login.html', {'errmsg': '账户或密码错误'})


class LogoutView(LoginRequiredMixin,View):
    '''
    完成用户注销功能,只有登录用户才能执行其中的方法
    '''
    def get(self,request):
        # 调用系统自带的注销功能注销登录用户
        logout(request=request)
        # 重定向浏览器到商品首页
        return redirect(reverse('goods:index'))


class UserInfoView(LoginRequiredMixin,View):
    '''
    用户中心-信息页,登录用户才可以访问
    '''
    def get(self,request):
        '''
        返回用户中心-信息页
        :param request:
        :return:
        '''
        # Django会给request对象添加一个属性request.user
        # 如果用户未登录->user是AnonymousUser类的一个实例对象
        # 如果用户登录->user是User类的一个实例对象
        # request.user.is_authenticated()

        # 获取用户个人信息
        user = request.user
        default_address = Address.objects.get_default_address(user)

        # 从redis中,获取用户的最近5条浏览记录的商品skuid
        # 数据存储格式为:history_userid:[skuid1,skuid2,skuid3...]
        sr = get_redis_connection()
        skuid_li = sr.lrange('history_%d'%user.id,0,4)

        goods_li = []
        for skuid in skuid_li:
            goods = GoodsSKU.objects.get(id=skuid)
            goods_li.append(goods)

        context = {'page':'user','address':default_address,'goods_li':goods_li}
        return render(request,'user_center_info.html',context)


class UserOrderView(LoginRequiredMixin,View):
    '''
    用户中心-订单页,展示用户订单相关信息
    '''
    def get(self,request,page):
        user = request.user
        orders = OrderInfo.objects.filter(user=user).order_by('-create_time')

        for order in orders:
            order_skus = OrderGoods.objects.filter(order_id=order.order_id)
            for order_sku in order_skus:
                order_sku.amount = order_sku.count * order_sku.price

            order.order_skus = order_skus
            order.status_name = OrderInfo.ORDER_STATUS[order.order_status]

        # 分页显示
        paginator = Paginator(orders,1)

        try:
            page = int(page)
        except Exception as e:
            page = 1
        if page > paginator.num_pages:
            page = 1

        # 获取当前请求页对象，其中包括该页要显示的所有数据
        order_page = paginator.get_page(page)

        if paginator.num_pages < 5:
            pages = range(1,paginator.num_pages+1)
        elif page <= 3:
            pages = range(1,6)
        elif page >= paginator.num_pages - 2:
            pages = range(paginator.num_pages-4,paginator.num_pages+1)
        else:
            pages = range(page-2,page+3)

        context = {'order_page':order_page,'pages':pages,'page':'order'}
        return render(request,'user_center_order.html',context)


class AddressView(LoginRequiredMixin,View):
    '''
    用户中心-地址页,管理用户地址信息
    '''
    def get(self,request):
        user = request.user
        default_address = Address.objects.get_default_address(user)

        context = {'page':'address','address':default_address}
        return render(request,'user_center_site.html',context)

    def post(self,request):
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')

        if not all([receiver, addr, phone]):
            return render(request, 'user_center_site.html', {'errmsg':'数据不完整'})

        phone_pattern = re.compile(r'^1[3|4|5|7|8][0-9]{9}$')
        if not phone_pattern.match(phone):
            return render(request, 'user_center_site.html', {'errmsg': '手机格式不正确'})

        # 添加地址到数据库,如果没有默认地址,设置新加地址为默认地址
        user = request.user
        default_address = Address.objects.get_default_address(user)

        if default_address:
            Address.objects.create(
                user=user,
                receiver=receiver,
                addr=addr,
                zip_code=zip_code,
                phone=phone,
                is_default=False)
        else:
            Address.objects.create(
                user=user,
                receiver=receiver,
                addr=addr,
                zip_code=zip_code,
                phone=phone,
                is_default=True)

        return redirect(reverse('user:address'))