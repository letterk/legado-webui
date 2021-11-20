import re
from urllib import parse
from flask import Flask, render_template, redirect, url_for, request, make_response
import httpx
import zlib
import json
import os
from datetime import datetime
import copy

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
    reset = 0  #刷新书架后需刷新目录


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
    store.reset = 1
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
    except:
        return False
    r = r.json()["data"]
    url_id = zlib.crc32(r[0]["bookUrl"].encode('utf8'))
    store.id_index_to_title[str(url_id)] = {}
    for i in r:
        store.id_index_to_title[str(url_id)][str(i["index"])] = i["title"]
    store.reset = 0
    return r


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
                      timeout=5)
        if "data" in r.json():
            return r.json()["data"]


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


def sync_mark(url_id, title, index):
    '''
    同步书签
    '''
    hostip = store.hostip
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
            r = httpx.post(prefix + hostip + "/saveBook",
                           data=json.dumps(mark))


app = Flask(__name__)


@app.route('/', methods=["GET"])
def hello():
    return redirect(url_for("bookshelf"))


@app.route('/bookshelf/')
def bookshelf():
    """
    书架页面
    """
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
            return redirect(url_for('go_404'))
        name = store.id_to_name[str(bookid)]
        r = store.catalogs.get(str(bookid))
        if r is None or store.reset == 1:
            r = get_chapterlist(bookurl)
        if r:
            store.catalogs[str(bookid)] = r
            return render_template('catalog.html', catalogs=r, name=name)
        else:
            return render_template('error.html', msg="请检查网络连接")
    else:
        return redirect(url_for("bookshelf"))


@app.route('/bookshelf/<int:bookid>/<int:index>/')
def content(bookid, index):
    """
    内容页面
    """
    data = get_local_txt(bookid, index)

    if not store.shelf:
        get_bookshelf()

    if data:
        sync_mark(bookid, data["title"], index)

    elif store.shelf:
        bookurl = store.id_to_url.get(str(bookid))
        if not bookurl:
            return redirect(url_for('go_404'))
        elif not store.id_index_to_title.get(str(bookid)):
            get_chapterlist(bookurl)

        n = 1
        while n <= 3:
            try:
                r = get_book_content(bookurl, str(index), n)
            except httpx.ReadTimeout:
                print("超时重试:", n, "次")
                r = False
            except:
                # 其他错误跳出循环
                n = 3
                r = False
            n += 1

        if r is None:
            return render_template('error.html', msg="没有该章节内容")
        elif r is False:
            return render_template('error.html', msg="请检查网络连接")
        content = re.split(r'\n', r)
        name = store.id_to_name[str(bookid)]
        title = store.id_index_to_title[str(bookid)][str(index)]
        curid = str(bookid)
        #total_index = store.id_to_totalindex[str(bookid)]
        prev_index = index - 1
        next_index = index + 1
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
        set_local_txt(str(bookid), str(index), data)

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


@app.route('/404')
def go_404():
    return render_template('error.html', msg="404页面未找到")


@app.errorhandler(404)
def page_not_found():
    return redirect(url_for('go_404'))


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
