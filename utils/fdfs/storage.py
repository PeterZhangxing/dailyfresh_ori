from django.core.files.storage import Storage
from django.conf import settings
from fdfs_client.client import Fdfs_client

class FdfsStorage(Storage):
    '''
    使用django自带的后台管理页面上传文件,会调用此类中的方法,需要在配置文件中指明类路径
    '''
    def __init__(self):
        self.client_conf = settings.FDFS_CLIENT_CONF
        self.base_url = settings.FDFS_URL

    def _open(self,name,mode='rb'):
        pass

    def _save(self,name,content):
        # name:你选择上传文件的名字
        # content:包含你上传文件内容的File对象
        client = Fdfs_client(self.client_conf)
        res = client.upload_by_buffer(content.read())

        if res.get('Status') != 'Upload successed.':
            raise Exception('UpLoad_File_To_Fdfs_Failed')

        filename = res.get('Remote file_id')

        return filename

    def exists(self, name):
        '''Django判断文件名是否可用'''
        return False

    def url(self, name):
        '''返回访问文件的url路径'''
        return self.base_url+name