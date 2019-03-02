from abc import abstractmethod
import re
from typing import List
import os

from google.cloud import translate


class Translator(object):

    @abstractmethod
    def word(self, word: str) -> str:
        pass

    @abstractmethod
    def phrase(self, phrase: str, tag: str) -> str:
        pass

    @staticmethod
    def new(src, dst):
        if src.startswith('zh') and dst.startswith('en'):
            return ChineseEnglishTranslator()
        else:
            return GoogleTranslator(src, dst)


CEDICT_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           'cedict_ts.u8')
CEDICT = None
CEDICT_RE = re.compile(r'^(.+) (.+) \[.+\] /(.+)/$')


def _shortest(l):
    res = None
    for x in l:
        if not res or len(res) >= len(x):
            res = x
    return res


POS_SET = {'NOUN', 'ADJ', 'VERB', 'PRON', 'ADV', 'PROPN', 'ADP'}


class ChineseEnglishTranslator(Translator):

    def __init__(self):
        self.translator = translate.Client()
        global CEDICT
        if CEDICT is None:
            cedict = {}
            with open(CEDICT_PATH) as f:
                for line in f:
                    line = line.strip()
                    if not line or line[0] == '#':
                        continue
                    m = CEDICT_RE.search(line)
                    if not m:
                        print(line)
                    c1, c2 = m.group(1), m.group(2)
                    eng_cands = [x.split(' (')[0]
                                 for x in m.group(3).split('/')]
                    eng = _shortest(eng_cands)
                    if eng and len(eng) < 15:
                        cedict[c1] = eng
                        cedict[c2] = eng
            CEDICT = cedict

    def word(self, word, tag):
        if tag not in POS_SET:
            raise Exception('Unsupported part of speech ({})'.format(tag))
        if word in CEDICT:
            return CEDICT[word]
        raise KeyError('Not in lexicon')

    def phrase(self, phrase):
        return self.translator.translate(
            phrase, target_language='en'
        )['translatedText']


class GoogleTranslator(Translator):

    def __init__(self, src, dst):
        self.src = src.split('-')[0]
        self.dst = dst
        self.translator = translate.Client()

    def word(self, word, tag):
        if tag not in POS_SET:
            raise Exception('Unsupported part of speech ({})'.format(tag))
        return self.phrase(word)

    def phrase(self, phrase):
        return self.translator.translate(
            phrase, source_language=self.src, target_language=self.dst
        )['translatedText']
