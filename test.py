# import jieba
#
# string = '特别好吃的猪肉'
#
# res_iter = jieba.cut(string,cut_all=True)
#
# for res in res_iter:
#     print(res)

# from fdfs_client.client import Fdfs_client
#
# client = Fdfs_client('./utils/fdfs/client.conf')
# ret = client.upload_by_filename('C:\Personal\pycharm_projects\dailyfresh\manage.py')
# print(ret)

# test_dict = {'a':1,'b':2,'c':23,'d':19}
# test_str_dict = {'a':'1','b':'2','c':'23','d':'19'}
#
# # mysum = sum(test_dict.values())
# # print(mysum)
#
# mysum = sum([ int(val) for val in test_str_dict.values() ])
# print(mysum)

string = 's3'
print(string.isdigit())