from abc import abstractmethod
from collections import namedtuple
from typing import List
from subprocess import check_call


class Tagger(object):

    Token = namedtuple('Token', ['text', 'tag'])

    LANGUAGES = frozenset({
        'en', 'en-US', 'en-GB',
        'de', 'fr', 'es', 'it', 'nl', 'pl', 'ja',
        'zh-CN', 'zh-TW'
    })

    @abstractmethod
    def tag(self, text: str) -> List['Tagger.Token']:
        pass

    @staticmethod
    def new(lang: str) -> 'Tagger':
        if lang in {'de', 'fr', 'es', 'it', 'nl', 'pl'}:
            return SpacyTagger(lang)
        elif lang.startswith('en'):
            return SpacyTagger('en')
        elif lang.startswith('zh'):
            return ChineseTagger()
        elif lang == 'ja':
            return JapaneseTagger()
        else:
            raise Exception('Unsupported language: {}'.format(lang))

    @staticmethod
    def languages():
        return Tagger.LANGUAGES


class SpacyTagger(Tagger):

    def __init__(self, lang):
        import spacy
        try:
            nlp = spacy.load(lang, diable=['ner'])
        except:
            check_call(['python3', '-m', 'spacy', 'download', lang])
            nlp = spacy.load(lang, diable=['ner'])
        self._nlp = nlp

    def tag(self, text):
        if not text:
            return []
        return [Tagger.Token(t.text, str(t.pos_)) for t in self._nlp(text)]


class JapaneseTagger(Tagger):

    POS_TAG = {
        '名詞': 'NOUN',
        '動詞': 'VERB',
        '記号': 'SYM',
        '副詞': 'ADV',
        '形容詞': 'ADJ',
        '接尾辞': 'suffix',
        '代名詞': 'PRON',
        '助動詞': 'VERB',
        '助詞': 'PART',
        '補助記号': 'PUNCT',
        '英単語': 'english',
        '漢文': 'chinese',
        'ローマ字文': 'romanji'
    }

    def __init__(self):
        import nagisa
        self._nagisa = nagisa

    def tag(self, text):
        if not text:
            return []
        result = self._nagisa.tagging(text)
        return [Tagger.Token(w, JapaneseTagger.POS_TAG.get(t, None))
                for w, t in zip(result.words, result.postags)]


class ChineseTagger(Tagger):

    POS_TAG = {
        'c': 'CONJ',
        'v': 'VERB',
        'vn': 'VERB',
        'vx': 'VERB',
        'n': 'NOUN',
        'a': 'ADJ',
        'd': 'ADV',
        'ad': 'ADV',
        'nr': 'PROPN',
        'ns': 'PROPN',
        'nt': 'PROPN',
        'r': 'PRON',
        'u': 'PART',
        'i': 'IDIOM',
    }

    def __init__(self):
        import pkuseg
        self._seg = pkuseg.pkuseg(postag=True)

    def tag(self, text):
        if not text:
            return []
        return [Tagger.Token(w, ChineseTagger.POS_TAG.get(t, None))
                for w, t in self._seg.cut(text)]
