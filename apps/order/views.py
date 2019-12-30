from django.shortcuts import render,redirect
from django.views.generic import View
from django.http import JsonResponse
from django.db import transaction
from django.urls import reverse
from django.conf import settings

from user.models import Address
from goods.models import GoodsSKU
from order.models import OrderInfo, OrderGoods

from utils.mixin import LoginRequiredMixin
from django_redis import get_redis_connection
from alipay import AliPay
from datetime import datetime
import os
import time

# Create your views here.

class OrderPlaceView(LoginRequiredMixin,View):
    '''
    根据购物车中的货品，生成订单页面
    '''
    def post(self,request):
        user = request.user
        sku_ids = request.POST.getlist('sku_ids')
        if not sku_ids:
            return redirect(reverse('cart:show'))

        # 从redis中获取商品的数量
        sr_conn = get_redis_connection('default')
        cart_key = "cart_%d"%user.id

        skus = []
        total_count = 0
        total_amount = 0
        for sku_id in sku_ids:
            sku = GoodsSKU.objects.get(id=sku_id)
            count = sr_conn.hget(cart_key,sku_id)
            amount = sku.price * int(count)
            sku.count = count
            sku.amount = amount
            skus.append(sku)
            total_count += int(count)
            total_amount += amount

        transit_price = 10 # 随便定的运费

        total_pay = total_amount + transit_price
        addrs = Address.objects.filter(user=user)
        sku_ids = ','.join(sku_ids)

        context = {
            'skus':skus,
            'total_count':total_count,
            'total_price':total_amount,
            'transit_price':transit_price,
            'total_pay':total_pay,
            'addrs':addrs,
            'sku_ids':sku_ids
        }

        return render(request,'place_order.html',context)


class OrderCommitView1(View):
    '''
    向数据库中添加订单信息，采用悲观锁控制并发访问
    '''
    @transaction.atomic # 此函数中的数据库操作将作为事务进行
    def post(self,request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res':0, 'errmsg':'用户未登录'})

        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids')

        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res':1, 'errmsg':'参数不完整'})

        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res':2, 'errmsg':'非法的支付方式'})

        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({'res':3, 'errmsg':'地址非法'})

        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)
        transit_price = 10
        total_count = 0
        total_price = 0

        save_id = transaction.savepoint() # 设置事务的回退点
        try:
            order = OrderInfo.objects.create(
                order_id=order_id,
                user=user,
                addr=addr,
                pay_method=pay_method,
                total_count=total_count,
                total_price=total_price,
                transit_price=transit_price
            )

            sr_conn = get_redis_connection('default')
            cart_key = 'cart_%d'%user.id

            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                try:
                    # 查询时锁定这行数据，其他进程或线程不能在查询这条数据
                    sku = GoodsSKU.objects.select_for_update().get(id=sku_id)
                except Exception as e:
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res':4, 'errmsg':'商品不存在'})

                count = sr_conn.hget(cart_key,sku_id)
                if int(count) > sku.stock:
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})

                OrderGoods.objects.create(
                    order=order,
                    sku=sku,
                    count=count,
                    price=sku.price
                )
                sku.stock -= int(count)
                sku.sales += int(count)
                sku.save()

                amount = sku.price * int(count)
                total_count += int(count)
                transit_price += amount

            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res':7, 'errmsg':'数据库插入失败'})

        transaction.savepoint_commit(save_id)
        sr_conn.hdel(cart_key,*sku_ids)

        return JsonResponse({'res': 5, 'message': '创建成功'})


class OrderCommitView(View):
    '''
    向数据库中添加订单信息，采用乐观锁控制并发访问，
    必须改变mysql数据库默认的事务级别为，改时其他事务不可见
    '''
    def post(self,request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res':0, 'errmsg':'用户未登录'})

        # 接收参数
        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        sku_ids = request.POST.get('sku_ids') # 1,3

        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res':1, 'errmsg':'参数不完整'})

        # 校验支付方式
        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res':2, 'errmsg':'非法的支付方式'})

        # 校验地址
        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            # 地址不存在
            return JsonResponse({'res':3, 'errmsg':'地址非法'})

        order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)

        # 运费
        transit_price = 10

        # 总数目和总金额
        total_count = 0
        total_price = 0

        # 设置事务保存点
        save_id = transaction.savepoint()
        try:
            order = OrderInfo.objects.create(order_id=order_id,
                                             user=user,
                                             addr=addr,
                                             pay_method=pay_method,
                                             total_count=total_count,
                                             total_price=total_price,
                                             transit_price=transit_price)
            conn = get_redis_connection('default')
            cart_key = 'cart_%d' % user.id
            sku_ids = sku_ids.split(',')

            for sku_id in sku_ids:
                # 尝试查询三次数据库中这个商品的库存，如果有一次查询到的库存和修改时的库存一致，购买成功
                for i in range(3):
                    # 获取商品的信息
                    try:
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except:
                        # 商品不存在
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 4, 'errmsg': '商品不存在'})

                    # 从redis中获取用户所要购买的商品的数量
                    count = conn.hget(cart_key, sku_id)

                    if int(count) > sku.stock:
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 6, 'errmsg': '商品库存不足'})

                    orgin_stock = sku.stock
                    new_stock = orgin_stock - int(count)
                    new_sales = sku.sales + int(count)

                    # 返回受影响的行数
                    # 只有在前面查询到的库存和现在更新时的库存一致时，才会更新库存和销售数据
                    res = GoodsSKU.objects.filter(id=sku_id, stock=orgin_stock).update(stock=new_stock, sales=new_sales)
                    if res == 0:
                        if i == 2:
                            # 尝试的第3次
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'res': 7, 'errmsg': '下单失败2'})
                        continue

                    OrderGoods.objects.create(order=order,
                                              sku=sku,
                                              count=count,
                                              price=sku.price)

                    amount = sku.price * int(count)
                    total_count += int(count)
                    total_price += amount

                    break

            order.total_count = total_count
            order.total_price = total_price
            order.save()

        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '数据库插入失败'})

        transaction.savepoint_commit(save_id)
        conn.hdel(cart_key, *sku_ids)

        return JsonResponse({'res': 5, 'message': '创建成功'})


class OrderPayView(View):
    '''
    获取订单id，引导用户到支付宝支付页面，登录支付
    '''
    def post(self,request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res':0, 'errmsg':'用户未登录'})

        order_id = request.POST.get('order_id')
        if not order_id:
            return JsonResponse({'res':1, 'errmsg':'无效的订单id'})

        # 找到要支付的订单
        try:
            order = OrderInfo.objects.get(
                order_id=order_id,
                user=user,
                pay_method=3,
                order_status=1
            )
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # 使用python sdk调用支付宝的支付接口
        alipay = AliPay(
            appid="2016090800464054",  # 应用id
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False
        )

        # 调用支付接口
        # 电脑网站支付，需要跳转到https://openapi.alipaydev.com/gateway.do? + order_string
        total_pay = order.total_price + order.transit_price
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id, # 订单id
            total_amount=str(total_pay), # 支付总金额
            subject='天天生鲜 订单号:%s'%order_id,
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )

        # 返回支付页面地址给前端
        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'res':3, 'pay_url':pay_url})


class CheckPayView(View):
    '''
    主动向支付宝开放平台发送支付结果查询请求，查看是否支付成功
    '''
    def post(self,request):
        # 用户是否登录
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': '用户未登录'})

        order_id = request.POST.get('order_id')
        if not order_id:
            return JsonResponse({'res':1, 'errmsg':'无效的订单id'})

        # 找到要支付的订单
        try:
            order = OrderInfo.objects.get(
                order_id=order_id,
                user=user,
                pay_method=3,
                order_status=1
            )
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        alipay = AliPay(
            appid="2016090800464054",  # 应用id
            app_notify_url=None,  # 默认回调url
            app_private_key_path=os.path.join(settings.BASE_DIR, 'apps/order/app_private_key.pem'),
            alipay_public_key_path=os.path.join(settings.BASE_DIR, 'apps/order/alipay_public_key.pem'),
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False
        )

        # 循环调用支付宝的支付结果查询api
        while True:
            response = alipay.api_alipay_trade_query(order_id)
            # 返回结果格式
            # response = {
            #         "trade_no": "2017032121001004070200176844", # 支付宝交易号
            #         "code": "10000", # 接口调用是否成功
            #         "invoice_amount": "20.00",
            #         "open_id": "20880072506750308812798160715407",
            #         "fund_bill_list": [
            #             {
            #                 "amount": "20.00",
            #                 "fund_channel": "ALIPAYACCOUNT"
            #             }
            #         ],
            #         "buyer_logon_id": "csq***@sandbox.com",
            #         "send_pay_date": "2017-03-21 13:29:17",
            #         "receipt_amount": "20.00",
            #         "out_trade_no": "out_trade_no15",
            #         "buyer_pay_amount": "20.00",
            #         "buyer_user_id": "2088102169481075",
            #         "msg": "Success",
            #         "point_amount": "0.00",
            #         "trade_status": "TRADE_SUCCESS", # 支付结果
            #         "total_amount": "20.00"
            # }

            code = response.get('code')
            trade_status = response.get('trade_status')
            if code == '10000' and trade_status == 'TRADE_SUCCESS':
                order.trade_no = response.get('trade_no')
                order.order_status = 4 # 订单状态变为待评价
                order.save()
                return JsonResponse({'res':3, 'message':'支付成功'})
            elif code == '40004' or (code == '10000' and trade_status == 'WAIT_BUYER_PAY'):
                # 等待买家付款
                # 业务处理失败，可能一会就会成功
                time.sleep(15)
                continue
            else:
                return JsonResponse({'res':4, 'errmsg':'支付失败','code':code,'trade_status':trade_status})


class CommentView(LoginRequiredMixin,View):
    '''
    显示评论页面，提交评论内容到数据库
    '''
    def get(self,request,order_id):
        user = request.user

        if not order_id:
            return redirect(reverse('user:order'))
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
            order.status_name = OrderInfo.ORDER_STATUS[order.order_status]
            order_skus = OrderGoods.objects.filter(order_id=order_id)
            for order_sku in order_skus: # 计算订单中每个商品的小计
                amount = order_sku.count * order_sku.price
                order_sku.amount = amount
            order.order_skus = order_skus # 将该订单关联的商品，作为属性，添加到订单中
        except OrderInfo.DoesNotExist:
            return redirect(reverse("user:order"))

        # 将渲染后的订单评论页面返回给前端
        context = {'order':order}
        return render(request,'order_comment.html',context)

    def post(self,request):
        user = request.user

        order_id = int(request.POST.get('order_id'))
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse("user:order"))

        total_count = int(request.POST.get("total_count"))

        # 获取每个商品的id和评论内容，并更新到数据库中
        for i in range(1,total_count+1):
            sku_id = request.POST.get('sku_%d'%i)
            sku_comment = request.POST.get('content_%d'%i)

            try:
                order_goods = OrderGoods.objects.get(sku_id=sku_id,order=order)
                order_goods.comment = sku_comment
                order_goods.save()
            except OrderGoods.DoesNotExist:
                continue

        # 更新订单状态为完成
        order.order_status = 5
        order.save()

        return redirect(reverse('user:order',kwargs={"page":1}))