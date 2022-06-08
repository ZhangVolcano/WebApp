import logging;logging.basicConfig(level=logging.INFO)
import asyncio,os,json,time
from datetime import datetime
from aiohttp import web
import aiomysql
def index(request):
    return web.Response(body=b'<h1>Index</h1>',content_type='text/html')

async def init(loop):
    app = web.Application(loop=loop)
    app.router.add_route('GET','/',index)
    server = await loop.create_server(app.make_handler(),'127.0.0.1',9000)
    logging.info('server started at http://127.0.0.1:9000..')
    return server

loop = asyncio.get_event_loop()
#将协程对象交给loop运行.run_until_complete()是一个阻塞（blocking）调用，直到协程运行结束，它才返回
loop.run_until_complete(init(loop))
loop.run_forever()

#创建连接池
async def create_pool(loop,**kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = await aiomysql.create_pool(
        host=kw.get('host','localhost'),
        port=kw.get('port',3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset','utf-8'),
        autocommit=kw.get('autocommit',True),
        maxsize=kw.get('maxsize',10),
        minsize=kw.get('minsize',1),
        loop=loop
    )

#select语句
async def select(sql,args,size=None):
    logging.log(sql, args)
    global __pool
    with (await __pool) as conn:
        cur = await conn.cursor(aiomysql.DictCursor)
        #注意要始终坚持使用带参数的SQL，而不是自己拼接SQL字符串，这样可以防止SQL注入攻击。
        await cur.execute(sql.replace('?','%s'),args or ())
        if size:
            #fetchmany查询指定行数,所以要有size
            rs = await cur.fetchmany(size)
        else:
            #查询所有数据
            rs = await cur.fetchall()
        await cur.close()
        logging.info('rows returned:%s' % len(rs))
        return rs
#Insert,Update,Delete
async def execute(sql,args):
    logging.log(sql)
    with (await __pool) as conn:
        try:
            cur = await conn.cursor()
            await cur.execute(sql.replace('?','%s'),args)
            #因为Insert,Update,Delete是不会返回结果的,所以需要通过rowcount来返回结果数.
            affected = cur.rowcount
            await cur.close()
        except BaseException as e:
            raise
        return affected

#ORM:把数据库的表结构映射到对象上
from orm import Model,StringField,IntegerField
class User(Model):
    __table__='users'
    id = IntegerField(primary_key=True)
    name = StringField()
