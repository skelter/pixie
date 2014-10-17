py_object = object
import pixie.vm.object as object
from pixie.vm.object import affirm
from pixie.vm.primitives import nil, true, false
import pixie.vm.numbers as numbers
from pixie.vm.cons import cons
from pixie.vm.symbol import symbol, Symbol
from pixie.vm.keyword import keyword
import pixie.vm.rt as rt
from pixie.vm.persistent_vector import EMPTY as EMPTY_VECTOR
from pixie.vm.libs.readline import _readline
from pixie.vm.string import String
from pixie.vm.code import wrap_fn
from pixie.vm.persistent_hash_map import EMPTY as EMPTY_MAP

class PlatformReader(object.Object):
    _type = object.Type(u"PlatformReader")

class StringReader(PlatformReader):

    def __init__(self, s):
        #affirm(isinstance(s, unicode), u"StringReader requires unicode")
        self._str = s
        self._idx = 0

    def read(self):
        if self._idx >= len(self._str):
            raise EOFError()
        ch = self._str[self._idx]
        self._idx += 1
        return ch

    def unread(self, ch):
        self._idx -= 1

class PromptReader(PlatformReader):
    def __init__(self):
        self._string_reader = None

    def read(self):
        if self._string_reader is None:
            self._string_reader = StringReader(_readline(">>") + u"\n")

        try:
            return self._string_reader.read()
        except EOFError:
            self._string_reader = None
            return self.read()

    def unread(self, ch):
        assert self._string_reader is not None
        self._string_reader.unread(ch)


def is_whitespace(ch):
    return ch in u"\r\n\t ," or ch == u""

def is_digit(ch):
    return ch in u"0123456789"

def eat_whitespace(rdr):
    while True:
        ch = rdr.read()
        if is_whitespace(ch):
            continue
        rdr.unread(ch)
        return


class ReaderHandler(py_object):
    def invoke(self, rdr, ch):
        pass

class ListReader(ReaderHandler):
    def invoke(self, rdr, ch):
        lst = []
        while True:
            eat_whitespace(rdr)
            ch = rdr.read()
            if ch == u")":
                acc = nil
                for x in range(len(lst) - 1, -1, -1):
                    acc = cons(lst[x], acc)
                return acc

            rdr.unread(ch)
            lst.append(read(rdr, True))

class UnmachedListReader(ReaderHandler):
    def invoke(self, rdr, ch):
        raise SyntaxError()

class VectorReader(ReaderHandler):
    def invoke(self, rdr, ch):
        acc = EMPTY_VECTOR
        while True:
            eat_whitespace(rdr)
            ch = rdr.read()
            if ch == u"]":
                return acc

            rdr.unread(ch)
            acc = rt.conj(acc, read(rdr, True))

class UnmachedVectorReader(ReaderHandler):
    def invoke(self, rdr, ch):
        raise SyntaxError()

class MapReader(ReaderHandler):
    def invoke(self, rdr, ch):
        acc = EMPTY_MAP
        while True:
            eat_whitespace(rdr)
            ch = rdr.read()
            if ch == u"}":
                return acc

            rdr.unread(ch)
            k = read(rdr, True)
            v = read(rdr, False)
            acc = rt._assoc(acc, k, v)
        return acc

class UnmachedMapReader(ReaderHandler):
    def invoke(self, rdr, ch):
        affirm(False, u"Unmatched Map brace")

class QuoteReader(ReaderHandler):
    def invoke(self, rdr, ch):
        itm = read(rdr, True)
        return cons(symbol(u"quote"), cons(itm))

class KeywordReader(ReaderHandler):
    def invoke(self, rdr, ch):
        itm = read(rdr, True)
        affirm(isinstance(itm, Symbol), u"Can't keyword quote a non-symbol")

        return keyword(itm._str)

class LiteralStringReader(ReaderHandler):
    def invoke(self, rdr, ch):
        acc = []

        # TODO: implement escape characters
        while True:
            try:
                v = rdr.read()
            except EOFError:
                raise Exception("unmatched quote")
            if v == "\"":
                return String(u"".join(acc))
            acc.append(v)

class DerefReader(ReaderHandler):
    def invoke(self, rdr, ch):
        return rt.cons(symbol(u"-deref"), rt.cons(read(rdr, True), nil))


QUOTE = symbol(u"quote")
UNQUOTE = symbol(u"unquote")
UNQUOTE_SPLICING = symbol(u"unquote-splicing")
APPLY = symbol(u"apply")
CONCAT = symbol(u"concat")
SEQ = symbol(u"seq")
LIST = symbol(u"list")

def is_unquote(form):
    return True if rt.instance_QMARK_(rt.ISeq.deref(), form) \
                   and rt.eq(rt.first(form), UNQUOTE) \
           else False

def is_unquote_splicing(form):
    return True if rt.instance_QMARK_(rt.ISeq.deref(), form) \
                   and rt.eq(rt.first(form), UNQUOTE_SPLICING) \
           else False

class SyntaxQuoteReader(ReaderHandler):
    def invoke(self, rdr, ch):
        form = read(rdr, True)
        return self.syntax_quote(form)

    @staticmethod
    def syntax_quote(form):
        if isinstance(form, Symbol):
            ret = rt.list(QUOTE, form)
        elif is_unquote(form):
            ret = rt.first(rt.next(form))
        elif is_unquote_splicing(form):
            raise Exception("Unquote splicing not used inside list")
        elif rt.vector_QMARK_(form) is true:
            ret = rt.list(APPLY, CONCAT, SyntaxQuoteReader.expand_list(form))
        elif rt.seq_QMARK_(form) is true:
            ret = rt.list(APPLY, LIST, rt.cons(CONCAT, SyntaxQuoteReader.expand_list(rt.seq(form))))
        else:
            ret = rt.list(QUOTE, form)
        return ret

    @staticmethod
    def expand_list(form):
        return rt.reduce(expand_list_rfn, EMPTY_VECTOR, form)

@wrap_fn
def expand_list_rfn(ret, item):
    if is_unquote(item):
        ret = rt.conj(ret, rt.vector(rt.first(rt.next(item))))
    elif is_unquote_splicing(item):
        ret = rt.conj(ret, rt.first(rt.next(item)))
    else:
        ret = rt.conj(ret, rt.vector(SyntaxQuoteReader.syntax_quote(item)))
    return ret

class UnquoteReader(ReaderHandler):
    def invoke(self, rdr, ch):
        ch = rdr.read()
        sym = UNQUOTE
        if ch == "@":
            sym = UNQUOTE_SPLICING
        else:
            rdr.unread(ch)

        form = read(rdr, True)
        return rt.list(sym, form)

handlers = {u"(": ListReader(),
            u")": UnmachedListReader(),
            u"[": VectorReader(),
            u"]": UnmachedVectorReader(),
            u"{": MapReader(),
            u"}": UnmachedMapReader(),
            u"'": QuoteReader(),
            u":": KeywordReader(),
            u"\"": LiteralStringReader(),
            u"@": DerefReader(),
            u"`": SyntaxQuoteReader(),
            u"~": UnquoteReader()}

def read_number(rdr, ch):
    acc = [ch]
    try:
        while True:
            ch = rdr.read()
            if is_whitespace(ch) or ch in handlers:
                rdr.unread(ch)
                break
            acc.append(ch)
    except EOFError:
        pass

    return numbers.Integer(int(u"".join(acc)))

def read_symbol(rdr, ch):
    acc = [ch]
    try:
        while True:
            ch = rdr.read()
            if is_whitespace(ch) or ch in handlers:
                rdr.unread(ch)
                break
            acc.append(ch)
    except EOFError:
        pass

    sym_str = u"".join(acc)
    if sym_str == u"true":
        return true
    if sym_str == u"false":
        return false
    if sym_str == u"nil":
        return nil
    return symbol(sym_str)

class EOF(object.Object):
    _type = object.Type(u"EOF")


eof = EOF()

def read(rdr, error_on_eof):
    try:
        eat_whitespace(rdr)
    except EOFError as ex:
        if error_on_eof:
            raise ex
        return eof



    ch = rdr.read()

    macro = handlers.get(ch, None)
    if macro is not None:
        return macro.invoke(rdr, ch)

    if is_digit(ch):
        return read_number(rdr, ch)

    if ch == u"-":
        ch2 = rdr.read()
        if is_digit(ch2):
            rdr.unread(ch2)
            return read_number(rdr, ch)
        else:
            rdr.unread(ch2)
            return read_symbol(rdr, ch)

    return read_symbol(rdr, ch)


