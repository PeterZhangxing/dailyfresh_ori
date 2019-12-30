from django.db import models
from django.contrib.auth.models import AbstractUser
from db.base_model import BaseModel

# Create your models here.

class User(AbstractUser,BaseModel):
    # 使用django内置的用户认证模块

    class Meta:
        db_table = 'df_user'
        verbose_name = '用户'
        verbose_name_plural = verbose_name


class AddressManager(models.Manager):
    '''
    自定义模型管理器类,实现:
        1.改变原有查询的结果集:如all()函数的输出结果
        2.封装新方法:用户操作模型类对应的数据表(增删改查)
    '''
    def get_default_address(self,user):
        try:
            address = self.get(user=user,is_default=True)
        except self.model.DoesNotExist:
            address = None
        return address


class Address(BaseModel):
    '''地址模型类,存储用户的地址信息'''

    user = models.ForeignKey('User', verbose_name='所属账户',on_delete=models.CASCADE)
    receiver = models.CharField(max_length=20, verbose_name='收件人')
    addr = models.CharField(max_length=256, verbose_name='收件地址')
    zip_code = models.CharField(max_length=6, null=True, blank=True,verbose_name='邮政编码')
    phone = models.CharField(max_length=11, verbose_name='联系电话')
    is_default = models.BooleanField(default=False, verbose_name='是否默认')

    objects = AddressManager() # 自定义一个模型管理器对象

    class Meta:
        db_table = 'df_address'
        verbose_name = '地址'
        verbose_name_plural = verbose_name