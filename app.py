import re
from urllib import parse
from flask import Flask, render_template, redirect, url_for, request, make_response
import httpx
import zlib

prefix = "http://"
#hostip = "192.168.31.199:1122"


class DataStore():
    id_to_name = {}
    id_to_url = {}
    id_to_totalindex = {}
    index_to_title = {}
    hostip = ""


data = DataStore()


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
    bookurl经过crc32生成id
    全局变量
    id_to_url
    id_to_name
    """
    hostip = request.cookies.get('hostip')
    if hostip is None or check_ip(hostip) is False:
        return False

    data.hostip = hostip
    try:
        books = httpx.get(prefix + hostip + "/getBookshelf")
    except:
        return

    books = books.json()["data"]
    for book in books:
        id = zlib.crc32(book["bookUrl"].encode('utf8'))
        book["id"] = id
        book["unread"] = book["totalChapterNum"] - book["durChapterIndex"] - 1
        data.id_to_url[str(id)] = book["bookUrl"]
        data.id_to_name[str(id)] = book["name"]
        data.id_to_totalindex[str(id)] = book["totalChapterNum"]
    return books


def get_chapterlist(bookurl):
    '''
    全局变量
    index_to_title {"index": "title"}
    '''
    hostip = data.hostip
    bookurl = parse.quote(bookurl)
    r = httpx.get(prefix + hostip + "/getChapterList?url=" + bookurl)

    r = r.json()["data"]
    index = 0
    for i in r:
        data.index_to_title[str(index)] = i["title"]
        index += 1
    return r


def get_book_content(bookurl, bookindex):
    hostip = data.hostip
    bookurl = parse.quote(bookurl)
    n = 0
    try:
        n += 1
        r = httpx.get(prefix + hostip + "/getBookContent?url=" + bookurl +
                      "&index=" + bookindex)
        return r.json()["data"]
    except httpx.ReadTimeout:
        if n <= 3:
            n += 1
            r = httpx.get(prefix + hostip + "/getBookContent?url=" + bookurl +
                          "&index=" + bookindex,
                          timeout=10)
            return r.json()["data"]
    return


app = Flask(__name__)


@app.route('/', methods=["GET"])
def hello():
    return redirect(url_for("bookshelf"))


@app.route('/bookshelf/')
def bookshelf():
    """
    书架页面
    """
    if get_bookshelf():
        books = get_bookshelf()
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
            bookurl = data.id_to_url[str(bookid)]
        except KeyError as e:
            return redirect(url_for('go_404'))
        name = data.id_to_name[str(bookid)]
        r = get_chapterlist(bookurl)
        return render_template('catalog.html', catalogs=r, name=name)
    else:
        return redirect(url_for("set_ip"))


@app.route('/bookshelf/<int:bookid>/<int:index>/')
def content(bookid, index):
    """
    内容页面
    """
    if get_bookshelf():
        try:
            bookurl = data.id_to_url[str(bookid)]
            get_chapterlist(bookurl)
            r = get_book_content(bookurl, str(index))
            if r is None:
                return redirect(url_for('go_404'))
        except KeyError as e:
            return redirect(url_for('go_404'))

        content = re.split(r'\n', r)
        name = data.id_to_name[str(bookid)]
        title = data.index_to_title[str(index)]
        curid = str(bookid)
        total_index = data.id_to_totalindex[str(bookid)]
        if index - 1 >= 0:
            prev_index = index - 1
        else:
            prev_index = -1
        if index + 1 <= total_index - 1:
            next_index = index + 1
        else:
            next_index = -1
        word = re.sub(r"\s", "", r)
        return render_template('content.html',
                               content=content,
                               name=name,
                               title=title,
                               bookid=curid,
                               prev_index=prev_index,
                               next_index=next_index,
                               characters_num=len(word))
    else:
        return redirect(url_for("set_ip"))


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
