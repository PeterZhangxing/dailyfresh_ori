from django.shortcuts import render
from django.http import JsonResponse
from django.views.generic import View
from django_redis import get_redis_connection
from utils.mixin import LoginRequiredMixin

from goods.models import GoodsSKU

# Create your views here.

class CartAddView(View):
    '''
    向购物车中添加商品,就是对redis中的数据进行增删改查
    '''
    def post(self,request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res':0, 'errmsg':'请先登录'})

        # 获取前端传来的数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 验证前端穿过来的数据的完整性及合法性
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})
        try:
            count = int(count) # 检测商品数量是不是整数
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目出错'})
        try:
            sku = GoodsSKU.objects.get(id=sku_id) # 检测商品是不是存在
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res':3, 'errmsg':'商品不存在'})

        # 将商品添加到用户的购物车中
        sr_conn = get_redis_connection('default')
        cart_key = 'cart_%d'%user.id
        cart_count = sr_conn.hget(cart_key,sku_id)
        if not cart_count:
            count = count
        else:
            count += cart_count

        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})
        sr_conn.hset(cart_key, sku_id, count)

        total_count = sr_conn.hlen(cart_key)

        return JsonResponse({'res':5,'total_count':total_count,'message':'添加成功'})


class CartInfoView(LoginRequiredMixin,View):
    '''
    显示购物车中的内容
    '''
    def get(self,request):
        '''
        从redis中获取用户购物车中{'商品id':'商品数量'}构成的字典
        :param request:
        :return:
        '''
        user = request.user
        sr_conn = get_redis_connection('default')
        cart_key = "cart_%d"%user.id
        cart_dict = sr_conn.hgetall(cart_key)

        skus = []
        total_count = 0
        total_price = 0
        for sku_id,count in cart_dict.items():
            sku = GoodsSKU.objects.get(id=sku_id)
            # 获取此种商品的购买的总数和总价格
            sku.amount = sku.price * int(count)
            sku.count = count
            skus.append(sku)

            total_count += int(count)
            total_price += sku.amount

        context = {
            'total_count': total_count,
            'total_price': total_price,
            'skus': skus
        }

        return render(request,'cart.html',context)


class CartUpdateView(View):
    '''
    增加或减少某客户购物车中商品的数量
    '''
    def post(self,request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res':0, 'errmsg':'请先登录'})

        # 获取前端传来的数据
        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 验证前端穿过来的数据的完整性及合法性
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': '数据不完整'})
        try:
            count = int(count) # 检测商品数量是不是整数
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目出错'})
        try:
            sku = GoodsSKU.objects.get(id=sku_id) # 检测商品是不是存在
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res':3, 'errmsg':'商品不存在'})

        # 获取商品存货,如果存货小于购买量,返回错误信息
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})

        cart_key = "cart_%d"%user.id
        sr_conn = get_redis_connection('default')
        sr_conn.hset(cart_key, sku_id, count)

        # 计算商品总件数
        total_count = 0
        goods_count = sr_conn.hvals(cart_key)
        for val in goods_count:
            total_count += int(val)

        return JsonResponse({'res':5, 'total_count':total_count, 'message':'更新成功'})


class CartDeleteView(View):
    '''
    删除购物车中的商品
    '''
    def post(self,request):
        user = request.user
        if not user.is_authenticated(): # 用户未登录
            return JsonResponse({'res': 0, 'errmsg': '请先登录'})

        # 获取前端传来的数据
        sku_id = request.POST.get('sku_id')

        if (not sku_id) or (not sku_id.isdigit()): # 如果商品id是空或者不是数字
            return JsonResponse({'res': 1, 'errmsg': '无效的商品id'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id) # 检测商品是不是存在
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res':2, 'errmsg':'商品不存在'})

        # 删除某用户购物车中的商品
        cart_key = "cart_%d"%user.id
        sr_conn = get_redis_connection('default')
        sr_conn.hdel(cart_key,sku_id)

        # 计算商品总件数
        total_count = 0
        goods_count = sr_conn.hvals(cart_key)
        for val in goods_count:
            total_count += int(val)

        return JsonResponse({'res':3, 'total_count':total_count, 'message':'删除成功'})