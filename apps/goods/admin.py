from django.contrib import admin
from goods.models import GoodsType, GoodsSKU, IndexGoodsBanner,IndexPromotionBanner,IndexTypeGoodsBanner
from celery_tasks import tasks
from django.core.cache import cache

# Register your models here.

class BaseModelAdmin(admin.ModelAdmin):

    def save_model(self, request, obj, form, change):
        '''
        在该管理类关联的表格类中添加数据,或者更新数据时,调用该函数
        '''
        super().save_model(request, obj, form, change)
        # 发出任务，让celery worker重新生成首页静态页
        tasks.generate_static_index_html.delay()
        # 清除首页的缓存
        cache.delete('index_page_data')

    def delete_model(self, request, obj):
        '''
        在该管理类关联的表格类中删除数据,调用该函数
        '''
        super().delete_model(request, obj)
        # 发出任务，让celery worker重新生成首页静态页
        tasks.generate_static_index_html.delay()
        # 清除首页的缓存
        cache.delete('index_page_data')


class GoodsTypeAdmin(BaseModelAdmin):
    pass

class IndexGoodsBannerAdmin(BaseModelAdmin):
    pass

class IndexTypeGoodsBannerAdmin(BaseModelAdmin):
    pass

class IndexPromotionBannerAdmin(BaseModelAdmin):
    pass


admin.site.register(GoodsType,GoodsTypeAdmin)
admin.site.register(IndexGoodsBanner,IndexGoodsBannerAdmin)
admin.site.register(IndexTypeGoodsBanner,IndexTypeGoodsBannerAdmin)
admin.site.register(IndexPromotionBanner,IndexPromotionBannerAdmin)