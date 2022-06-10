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

