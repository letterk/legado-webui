import re
from urllib import parse
from flask import Flask
from flask import render_template
from flask import redirect
from flask import url_for
from flask import request
from flask import abort
import httpx
import zlib
import json
import os
from datetime import datetime
import copy
#from flask_caching import Cache

app = Flask(__name__)
app.jinja_env.auto_reload = True
'''
config = {
    "DEBUG": True,  # some Flask specific configs
    "CACHE_TYPE": "SimpleCache",  # Flask-Caching related configs
    "CACHE_DEFAULT_TIMEOUT": 300
}
app.config.from_mapping(config)
cache = Cache(app)
'''

prefix = "http://"


class DataStore():
    '''
    全局变量
    '''
    id_to_name = {}
    id_to_url = {}
    id_to_totalindex = {}
    id_index_to_title = {}
    hostip = ""
    shelf = {}
    catalogs = {}


store = DataStore()


def is_legado(ip):
    """
    检查ip是否是阅读app
    """
    if ip and check_ip(ip):
        try:
            r = httpx.get(prefix + ip, timeout=2)
            if r.status_code == 200 and r.text.find("Legado") > -1:
                return True
            else:
                return False
        except:
            return False


def check_ip(str):
    """
    检查ip和端口格式是否正确
    """
    re_exp = '^[a-zA-Z0-9][-a-zA-Z0-9]{0,62}(\.[a-zA-Z0-9][-a-zA-Z0-9]{0,62})+\:([1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]{1}|6553[0-5]|[1-9][0-9]{0,3})$'
    res = re.search(re_exp, str)
    if res:
        return True
    else:
        return False


def get_bookshelf():
    """
    获取书架
    赋值全局变量
    id_to_url
    id_to_name
    id_to_totalindex
    hostip
    """
    print("请求app获取书架")
    hostip = request.cookies.get('hostip')
    if hostip is None or check_ip(hostip) is False:
        return False
    store.id_index_to_title = {}
    store.hostip = hostip
    try:
        books = httpx.get(prefix + hostip + "/getBookshelf")
    except:
        return False

    books = books.json()["data"]
    store.shelf = books
    for book in books:
        url_id = zlib.crc32(book["bookUrl"].encode('utf8'))
        book["id"] = url_id
        book["unread"] = book["totalChapterNum"] - book["durChapterIndex"] - 1
        store.id_to_url[str(url_id)] = book["bookUrl"]
        store.id_to_name[str(url_id)] = book["name"]
        store.id_to_totalindex[str(url_id)] = book["totalChapterNum"]
    return books


def get_chapterlist(bookurl):
    '''
    获取目录
    赋值全局变量
    id_index_to_title
    '''
    print("请求app获取目录")
    hostip = store.hostip
    bookurl = parse.quote(bookurl)
    try:
        r = httpx.get(prefix + hostip + "/getChapterList?url=" + bookurl)
        r = r.json()["data"]
    except Exception as e:
        print("获取目录出错:", str(e))
        return False

    url_id = zlib.crc32(r[0]["bookUrl"].encode('utf8'))
    store.id_index_to_title[str(url_id)] = {}
    for i in r:
        store.id_index_to_title[str(url_id)][str(i["index"])] = i["title"]
    return r


#@cache.cached(timeout=3600, key_prefix="content/%s")
def get_book_content(bookurl, bookindex, n):
    '''
    获取正文
    超时重试3次
    '''
    print("请求app获取正文")
    hostip = store.hostip
    bookurl = parse.quote(bookurl)
    if n <= 3:
        r = httpx.get(prefix + hostip + "/getBookContent?url=" + bookurl +
                      "&index=" + bookindex,
                      timeout=10)
        data = r.json().get("data")
        error = r.json().get("errorMsg")
        if data:
            return data
        elif error == "未找到":
            return None
        else:
            return ""


'''
def mkdir(path):
    folder = os.path.exists(path)
    if not folder:
        os.makedirs(path)


def get_local_txt(url_id, index):
    path = './data/' + str(url_id) + '/'
    filename = str(index) + '.json'
    try:
        with open(path + filename, "rt", encoding='utf8') as f:
            r = json.load(f)
        return r
    except FileNotFoundError:
        return False


def set_local_txt(url_id, index, data):
    path = './data/' + str(url_id) + '/'
    filename = str(index) + '.json'
    mkdir(path)
    with open(path + filename, "w+", encoding='utf8') as f:
        json.dump(data, f, ensure_ascii=False)
'''


def sync_mark(url_id, title, index):
    '''
    同步书签
    '''
    #hostip = store.hostip
    books = store.shelf
    ts = int(datetime.now().timestamp() * 1000)
    for book in books:
        if book["id"] == url_id:
            mark = copy.copy(book)
            mark.pop("id")
            mark.pop("unread")
            mark["durChapterIndex"] = index
            mark["durChapterTitle"] = title
            mark["durChapterTime"] = ts
            #httpx.post(prefix + hostip + "/saveBook", data=json.dumps(mark))
            return mark


@app.route('/', methods=["GET"])
def hello():
    return redirect(url_for("bookshelf"))


@app.route('/bookshelf/')
def bookshelf():
    """
    书架页面
    """
    #cache.clear()
    books = get_bookshelf()
    if books:
        return render_template('bookshelf.html', books=books)
    else:
        return redirect(url_for("set_ip"))


@app.route('/bookshelf/<int:bookid>/')
def catalog(bookid):
    """
    目录页面
    """
    if not store.shelf:
        get_bookshelf()
    if store.shelf:
        bookurl = store.id_to_url.get(str(bookid))
        if not bookurl:
            abort(404)
        name = store.id_to_name[str(bookid)]
        #r = store.catalogs.get(str(bookid))
        #if r is None:
        #    r = get_chapterlist(bookurl)
        r = get_chapterlist(bookurl)
        if r:
            #store.catalogs[str(bookid)] = r
            return render_template('catalog.html', catalogs=r, name=name)
        else:
            return render_template('error.html', msg="请检查网络连接")
    else:
        return redirect(url_for("bookshelf"))


@app.route('/bookshelf/<int:bookid>/<int:index>/')
#@cache.cached(timeout=300)
def content(bookid, index):
    """
    内容页面
    """

    if not store.shelf:
        get_bookshelf()
    if store.shelf:
        bookurl = store.id_to_url.get(str(bookid))
        if not bookurl:
            abort(404)
        elif not store.id_index_to_title.get(str(bookid)):
            get_chapterlist(bookurl)

        n = 1
        while n <= 3:
            try:
                r = get_book_content(bookurl, str(index), n)
                n = 3
            except httpx.ReadTimeout:
                print("超时重试:", n, "次")
                r = False
            except Exception as e:
                # 其他错误跳出循环
                print("其他错误:" + str(e))
                n = 3
                r = False
            n += 1

        if r is None:
            return render_template('error.html', msg="没有找到该章节"), 404
        if r is False:
            return render_template('error.html', msg="请检查网络连接"), 504
        content = re.split(r'\n', r)
        name = store.id_to_name[str(bookid)]
        title = store.id_index_to_title[str(bookid)][str(index)]
        curid = str(bookid)
        total_index = store.id_to_totalindex[str(bookid)]
        if index - 1 >= 0:
            prev_index = index - 1
        else:
            prev_index = -1
        if index + 1 <= total_index - 1:
            next_index = index + 1
        else:
            next_index = -1
        #prev_index = index - 1
        #next_index = index + 1
        word = re.sub(r"\s", "", r)
        data = {
            "content": content,
            "name": name,
            "title": title,
            "bookid": curid,
            "prev_index": prev_index,
            "next_index": next_index,
            "characters_num": len(word)
        }
        #mark = sync_mark(bookid, data["title"], index)
    else:
        return redirect(url_for("bookshelf"))

    return render_template('content.html',
                           content=data["content"],
                           name=data["name"],
                           title=data["title"],
                           bookid=data["bookid"],
                           prev_index=data["prev_index"],
                           next_index=data["next_index"],
                           characters_num=data["characters_num"])
    #mark=json.dumps(mark))


@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', msg=e), 404


@app.route('/set_ip', methods=['GET', "POST"])
def set_ip():
    if request.method == 'POST':
        hostip = request.cookies.get('hostip')
        if check_ip(hostip) and is_legado(hostip):
            return redirect(url_for("bookshelf"))
        else:
            return render_template('bookshelf.html', islegado=False)
    else:
        return render_template('bookshelf.html', islegado=False)
