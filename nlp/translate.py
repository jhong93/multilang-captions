import os
import re
import json
from collections import defaultdict
from functools import lru_cache


from google.cloud import translate


def get_language_code(t):
    return t.split('-')[0]


class SentenceTranslator(object):

    def __init__(self, src, dst):
        self.src = get_language_code(src)
        self.dst = get_language_code(dst)
        self.translator = translate.Client()

    def translate(self, phrase: str) -> str:
        return self.translator.translate(
            phrase, source_language=self.src, target_language=self.dst
        )['translatedText']


JMDICT_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           'jmdict', 'JMdict.json')


def load_jmdict(max_len=15):
    with open(JMDICT_PATH) as f:
        jmdict = json.load(f)
    for ent in jmdict:
        k_ele = [y.strip() for x in ent.get('k_ele', ())
                 for y in x.get('keb', ())]
        r_ele = [y.strip() for x in ent.get('r_ele', ())
                 for y in x.get('reb', ())]
        for s in ent.get('sense', ()):
            g = s.get('gloss', ())
            if len(g) > 0:
                g_0 = g[0].strip()
                if len(g_0) <= max_len:
                    for k in k_ele:
                        yield k, g_0
                    for r in r_ele:
                        yield r, g_0


DICT_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'dicts')
DICT_RE = re.compile(r'^(.+)\s+(.+)$')


@lru_cache(25)
def load_dictionary(src, dst):
    dictionary = defaultdict(set)

    dict_path = os.path.join(DICT_DIR, '{}-{}.txt'.format(
                             src, dst))
    if os.path.exists(dict_path):
        with open(dict_path) as f:
            for line in f:
                m = DICT_RE.match(line.strip())
                if m:
                    s = m.group(1)
                    d = m.group(2)
                    dictionary[s].add(d)
    else:
        raise NotImplementedError(
            'Missing dictionary: {} -> {}'.format(src, dst))

    idict_path = os.path.join(DICT_DIR, '{}-{}.txt'.format(dst, src))
    if os.path.exists(idict_path):
        with open(idict_path) as f:
            for line in f:
                m = DICT_RE.match(line.strip())
                if m:
                    d = m.group(1)
                    s = m.group(2)
                    dictionary[s].add(d)
    else:
        raise NotImplementedError(
            'Missing dictionary: {} -> {}'.format(src, dst))

    if src == 'ja':
        for s, d in load_jmdict():
            dictionary[s].add(d)

    assert len(dictionary) > 0
    return dictionary


class WordTranslator(object):

    def __init__(self, src, dst):
        self.src = get_language_code(src)
        self.dst = get_language_code(dst)
        self.dictionary = load_dictionary(src, dst)

    def translate(self, word: str) -> str:
        return self.dictionary.get(word.lower(), None)
