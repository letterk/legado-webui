import re
from urllib import parse
from flask import Flask, render_template, redirect, url_for, request, make_response
import httpx
import zlib
import json
import os

prefix = "http://"


class DataStore():
    '''
    全局变量
    '''
    id_to_name = {}
    id_to_url = {}
    id_to_totalindex = {}
    index_to_title = {}
    hostip = ""


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
    赋值全局变量
    id_to_url
    id_to_name
    id_to_totalindex
    hostip
    """
    hostip = request.cookies.get('hostip')
    if hostip is None or check_ip(hostip) is False:
        return False

    store.hostip = hostip
    try:
        books = httpx.get(prefix + hostip + "/getBookshelf")
    except:
        return False

    books = books.json()["data"]
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
    赋值全局变量
    index_to_title
    '''
    hostip = store.hostip
    bookurl = parse.quote(bookurl)
    r = httpx.get(prefix + hostip + "/getChapterList?url=" + bookurl)
    r = r.json()["data"]
    index = 0
    for i in r:
        store.index_to_title[str(index)] = i["title"]
        index += 1
    return r


def get_book_content(bookurl, bookindex):
    '''
    超时重试3次
    '''
    hostip = store.hostip
    bookurl = parse.quote(bookurl)
    n = 0
    try:
        n += 1
        r = httpx.get(prefix + hostip + "/getBookContent?url=" + bookurl +
                      "&index=" + bookindex)
        return r.json()["data"]
    except httpx.ReadTimeout:
        if n <= 3:
            print("超时重试:", n, "次")
            n += 1
            r = httpx.get(prefix + hostip + "/getBookContent?url=" + bookurl +
                          "&index=" + bookindex,
                          timeout=10)
            return r.json()["data"]
    return


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
    if get_bookshelf():
        try:
            bookurl = store.id_to_url[str(bookid)]
        except KeyError as e:
            return redirect(url_for('go_404'))
        name = store.id_to_name[str(bookid)]
        r = get_chapterlist(bookurl)
        return render_template('catalog.html', catalogs=r, name=name)
    else:
        return redirect(url_for("set_ip"))


@app.route('/bookshelf/<int:bookid>/<int:index>/')
def content(bookid, index):
    """
    内容页面
    """
    data = get_local_txt(bookid, index)
    if data:
        pass

    elif get_bookshelf():
        try:
            bookurl = store.id_to_url[str(bookid)]
            get_chapterlist(bookurl)
            r = get_book_content(bookurl, str(index))
            if r is None:
                return redirect(url_for('go_404'))
        except KeyError as e:
            return redirect(url_for('go_404'))

        content = re.split(r'\n', r)
        name = store.id_to_name[str(bookid)]
        title = store.index_to_title[str(index)]
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
        return redirect(url_for("set_ip"))

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
    return '<h2>地址错误, 返回<a href="bookshelf/">书架</a>吧</h2>'


@app.errorhandler(404)
def page_not_found(e):
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
