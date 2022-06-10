import logging;logging.basicConfig(level=logging.INFO)
import aiomysql

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


# 这个函数只在下面的 Model元类中被调用， 作用好像是加数量为 num 的'?'
def create_args_string(num):
    L = []
    for _ in range(num):
    # 源码是 for n in range(num):  我看着反正 n 也不会用上，改成这个就不报错了
        L.append('?')
    return ', '.join(L)





#ORM:把数据库的表结构映射到对象上
from orm import Model, StringField, IntegerField, ModelMetaclass

class User(Model):
    #关联数据库表users
    __table__='users'
    id = IntegerField(primary_key=True)
    name = StringField()


class ModelMetaclass(type):
    #cls表示类本身
    def __new__(cls,name,bases,attrs):
        if name == 'Model':
            return type.__new__(cls,name,bases,attrs)
        tableName = attrs.get('__table__',None) or name
        logging.info('found model:%s (table:%s)' % (name,tableName))
        mappings = dict()
        fields = []
        primaryKey = None
        #ditc.items()是以列表形式返回可遍历的key,value
        for k,v in attrs.items():
            if isinstance(v,Field):
                logging.info('found mapping:%s==>%s' % (k,v))
                mappings[k] = v
                if v.primary_key:
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field:%s' % k)
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found')
        for k in mappings.keys():
            attrs.pop(k)
        #map(function, iterable, …) 接收函数和迭代对象,返回迭代器
        #所以这里应该是将fields所有元素都添加''单引号再返回map对象,再转成list对象
        escaped_fields = list(map(lambda f:'`%s`' % f,fields))
        attrs['__mappings__'] = mappings
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey
        attrs['__fields__'] =fields
        #','.join(escaped_fields)是将escaped_fields的所有元素以分隔符为,进行合并
        attrs['__select__'] = 'select `%s`,%s from `%s`' %(primaryKey,','.join(escaped_fields),tableName)
        #这里调用create_args_string()是基于mysql语句,insert添加多少行
        #eg:INSERT INTO t able1 VALUES(1),(2),(3),(4),(5);
        attrs['__insert__'] = 'insert into `%s` (%s,`%s`) values (%s)' %(tableName,','.join(escaped_fields),primaryKey,create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s` = ?' %(tableName,','.join(map(lambda f:'`%s`=?' % (mappings.get(f).name or f),fields)),primaryKey)
        attrs['__delete__'] = 'delete from `%s` where  `%s`=?' % (tableName,primaryKey)

        return type.__new__(cls,name,bases,attrs)

#定义Model
#创建Model类,继承dict,并自定义元类
#元类:即通过class关键字定义的类肯定也是调用了一个类得到的,这个类就是元类,在这里就是dict
class Model(dict,metaclass=ModelMetaclass):
    def __init__(self,**kw):
        super(Model,self).__init__(**kw)
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(r"'Model' object has no attr ' %s'" %key)
    def __setattr__(self, key, value):
        self[key] = value
    def getValue(self,key):
        #getattr用于返回对象的属性值,这里就是根据key返回一个value
        return getattr(self,key,None)
    def getValueOrDefault(self,key):
        value = getattr(self,key,None)
        if value is None:
            #__mappings__是model继承ModelMetaclass来的一个dict
            field = self.__mappings__[key]
            if field.default is not None:
                #callable检查对象是否能调用
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s:%s' %(key,str(value)))
        return value
    @classmethod
    async def find(cls,pk):
        'find object by primary key.'
        rs = await select('%s where `%s` = ?' % (cls.__select__,cls.__primary_key__),[pk],1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])
    async def save(self):
        args = list(map(self.getValueOrDefault,self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__,args)
        if rows != 1:
            logging.warn('failed to insert record:affected rows:%s' % rows)


#Field和各种Field子类

class Field(object):
    def __init__(self,name,column_type,primary_key,default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default
    def __str__(self):
        return '<%s,%s:%s>' %(self,__class__,__name__,self.column_type,self.name)


class StringField(Field):
    def __init__(self,name=None,primary_key=False,default=None,ddl='varchar(100)'):
        super.__init__(name,ddl,primary_key,default)

class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)