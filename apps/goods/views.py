from django.shortcuts import render,redirect
from django.views.generic import View
from django.urls import reverse
from django.core.cache import cache
from django_redis import get_redis_connection
from django.core.paginator import Paginator

from goods.models import GoodsType, GoodsSKU, IndexGoodsBanner,IndexPromotionBanner,IndexTypeGoodsBanner
from order.models import OrderGoods

# Create your views here.

class IndexView(View):

    def get(self,request):
        # 从缓存中获取redis中缓存的首页数据
        context = cache.get('index_page_data')

        if context is None: # 如果缓存中没有数据
            # 获取商品的种类信息
            types = GoodsType.objects.all()

            # 获取首页轮播商品信息
            goods_banners = IndexGoodsBanner.objects.all().order_by('index')

            # 获取首页促销活动信息
            promotion_banners = IndexPromotionBanner.objects.all().order_by('index')

            # 获取首页分类商品展示信息,并给每个分类添加此分类下要展示的商品
            for ctype in types:
                ctype.image_banners = IndexTypeGoodsBanner.objects.filter(type=ctype,display_type=1).order_by('index')
                ctype.title_banners = IndexTypeGoodsBanner.objects.filter(type=ctype,display_type=0).order_by('index')

            context = {
                'types': types,
                'goods_banners': goods_banners,
                'promotion_banners': promotion_banners
            }

            # 设置缓存
            # key  value timeout
            cache.set('index_page_data',context,3600)

        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        if user.is_authenticated: # 如果用户已经登录,从redis缓存中获取购物车信息
            sr_conn = get_redis_connection('default')
            cart_key = 'cart_%d'%user.id
            cart_count = sr_conn.hlen(cart_key)

        context.update(cart_count=cart_count)

        return render(request,'index.html',context)


class DetailView(View):
    '''
    显示商品详情页
    '''
    def get(self,request,goods_id):
        # 获取商品sku对象
        try:
            sku = GoodsSKU.objects.get(id=goods_id)
        except GoodsSKU.DoesNotExist:
            return redirect(reverse('goods:index')) # 商品不存在,重定向到首页

        # 获取所有商品分类
        types = GoodsType.objects.all()

        # 获取当前商品的评论
        sku_orders = OrderGoods.objects.filter(sku=sku).exclude(comment='')

        # 获取新品信息
        new_skus = GoodsSKU.objects.filter(type=sku.type).order_by('-create_time')[:2]

        # 获取同一个SPU的其他规格商品
        same_spu_skus = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=goods_id)

        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        if user.is_authenticated:  # 如果用户已经登录,从redis缓存中获取购物车信息
            sr_conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = sr_conn.hlen(cart_key)

            # 添加用户的历史商品浏览记录
            sr = get_redis_connection()
            history_key = 'history_%d' % user.id
            sr.lrem(history_key,0,goods_id) # 删除该列表中所有的给定的值
            sr.lpush(history_key,goods_id) # 在列表最左侧插入一个数据
            sr.ltrim(history_key,0,4) # 只保存列表中的前5个数据

        context = {
            'sku':sku,
            'types':types,
            'sku_orders':sku_orders,
            'new_skus':new_skus,
            'same_spu_skus':same_spu_skus,
            'cart_count':cart_count
        }

        return render(request,'detail.html',context)


class ListView(View):
    '''
    生成商品列表展示页面
    '''
    def get(self,request,type_id,page):
        # 获取此商品的种类对象
        try:
            ctype = GoodsType.objects.get(id=type_id)
        except GoodsType.DoesNotExist:
            # 种类不存在
            return redirect(reverse('goods:index'))

        # 获取商品种类信息
        types = GoodsType.objects.all()

        # 获取新品信息
        new_skus = GoodsSKU.objects.filter(type=ctype).order_by('-create_time')[:2]

        # 获取用户购物车中商品的数目
        user = request.user
        cart_count = 0
        if user.is_authenticated:  # 如果用户已经登录,从redis缓存中获取购物车信息
            sr_conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            cart_count = sr_conn.hlen(cart_key)

        # 获取商品的排序方式
        sort = request.GET.get('sort')
        if sort == 'price':
            if request.session.get('last_sort_by',None):
                if request.session['last_sort_by'] == '-price':
                    skus = GoodsSKU.objects.filter(type=ctype).order_by('price')
                    request.session['last_sort_by'] = 'price'
                elif request.session['last_sort_by'] == 'price':
                    skus = GoodsSKU.objects.filter(type=ctype).order_by('-price')
                    request.session['last_sort_by'] = '-price'
                else:
                    skus = GoodsSKU.objects.filter(type=ctype).order_by('price')
                    request.session['last_sort_by'] = 'price'
            else:
                skus = GoodsSKU.objects.filter(type=ctype).order_by('price')
                request.session['last_sort_by'] = 'price'

        elif sort == 'hot':
            if request.session.get('last_sort_by',None):
                if request.session['last_sort_by'] == '-sales':
                    skus = GoodsSKU.objects.filter(type=ctype).order_by('sales')
                    request.session['last_sort_by'] = 'sales'
                elif request.session['last_sort_by'] == 'sales':
                    skus = GoodsSKU.objects.filter(type=ctype).order_by('-sales')
                    request.session['last_sort_by'] = '-sales'
                else:
                    skus = GoodsSKU.objects.filter(type=ctype).order_by('sales')
                    request.session['last_sort_by'] = 'sales'
            else:
                skus = GoodsSKU.objects.filter(type=ctype).order_by('sales')
                request.session['last_sort_by'] = 'sales'

        else:
            if request.session.get('last_sort_by',None):
                if request.session['last_sort_by'] == '-id':
                    skus = GoodsSKU.objects.filter(type=ctype).order_by('id')
                    request.session['last_sort_by'] = 'id'
                elif request.session['last_sort_by'] == 'id':
                    skus = GoodsSKU.objects.filter(type=ctype).order_by('-id')
                    request.session['last_sort_by'] = '-id'
                else:
                    skus = GoodsSKU.objects.filter(type=ctype).order_by('id')
                    request.session['last_sort_by'] = 'id'
                sort = 'default'
            else:
                sort = 'default'
                skus = GoodsSKU.objects.filter(type=ctype).order_by('id')
                request.session['last_sort_by'] = 'id'

        # 生成页码
        paginator = Paginator(skus, 1)
        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages:
            page = 1

        # 获取某页上的数据对象
        skus_page = paginator.page(page)

        # 进行页码的控制，页面上最多显示5个页码
        if paginator.num_pages <= 5:
            page_range = range(1,paginator.num_pages+1)
        elif page <= 3:
            page_range = range(1, 6)
        elif paginator.num_pages - page <= 2:
            page_range = range(paginator.num_pages-4,paginator.num_pages+1)
        else:
            page_range = range(page-2,page+3)

        context = {
            'type':ctype,
            'types':types,
            'skus_page':skus_page,
            'new_skus':new_skus,
            'cart_count':cart_count,
            'sort':sort,
            'page_range':page_range,
        }

        return render(request,'list.html',context)