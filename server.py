#!/usr/bin/env python3

import argparse
import hashlib
import json
import math
import re
import os
import sys
from collections import namedtuple
from subprocess import check_call

import webvtt
from flask import Flask, request, render_template, jsonify, send_from_directory

from nlp.tagger import Tagger
from nlp.translate import Translator


FORCE_DOWNLOAD = False


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', dest='port', type=int, default=8080)
    parser.add_argument('--host', dest='host', type=str, default='localhost')
    parser.add_argument('--cache-dir', dest='cache_dir', type=str,
                        default='cache')
    parser.add_argument('--api-key', dest='api_key_file', type=str,
                        required=True)
    return parser.parse_args()


def set_api_key(key_path):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = key_path


def download_video(url, download_dir, langs):
    check_call([
        'youtube-dl', url, '--skip-download',
        '--write-sub', '--sub-lang', ','.join(sorted(langs)),
        '--convert-subs', 'vtt',
        '--write-info-json', '--write-description', '--write-thumbnail',
        '-o', '{}/video.%(ext)s'.format(download_dir)
    ])
    translated_dir = os.path.join(download_dir, 'translated')
    if not os.path.isdir(translated_dir):
        os.makedirs(translated_dir)
    cached_dir = os.path.join(download_dir, 'cached')
    if not os.path.isdir(cached_dir):
        os.makedirs(cached_dir)


def get_available_subs(video_dir):
    subs = []
    for fname in os.listdir(video_dir):
        if fname.endswith('.vtt'):
            subs.append(fname)
    return subs


def get_native_sub_path(video_dir, lang):
    return os.path.join(video_dir, 'video.{}.vtt'.format(lang))


def get_translated_sub_path(video_dir, lang):
    return os.path.join(video_dir, 'translated', 'video.{}.vtt'.format(lang))


def get_translation_cache_path(video_dir, src_lang, dst_lang, content_hash):
    return os.path.join(video_dir, 'cached', '{}.{}.{}.json'.format(
        src_lang, dst_lang, content_hash))


def md5_hash(s, length=8):
    return hashlib.md5(s.encode()).hexdigest()[:length]


def parse_vtt_time(s):
    tokens = s.split(':')
    seconds = float(tokens[-1]) + int(tokens[-2]) * 60
    if len(tokens) == 3:
        seconds += int(tokens[0]) * 3600
    return seconds


def format_vtt_time(t):
    millis = math.floor(t * 1000) % 1000
    seconds = math.floor(t) % 60
    minutes = math.floor(t / 60) % 60
    hours = math.floor(t / 3600)
    return '{:02}:{:02}:{:02}.{:03}'.format(
            hours, minutes, seconds, millis)


def read_vtt(path):
    result = []
    for line in webvtt.read(path):
        result.append(Caption(
            start=parse_vtt_time(line.start),
            end=parse_vtt_time(line.end),
            text=line.text,
            tokens=None
        ))
    return result


def translate_sub_file(video_dir, src_lang, dst_lang):
    translator = Translator.new(src_lang, dst_lang)
    dst_vtt = webvtt.WebVTT()
    for line in read_vtt(get_native_sub_path(video_dir, src_lang)):
        src_text = line.text.strip()
        if src_text:
            try:
                dst_text = translator.phrase(src_text)
                dst_vtt.captions.append(webvtt.Caption(
                    format_vtt_time(line.start), format_vtt_time(line.end),
                    dst_text))
            except Exception as e:
                print('Error {}: {}'.format(e, src_text), file=sys.stderr)
    dst_vtt.save(get_translated_sub_path(video_dir, dst_lang))


def translate_sub_words(video_dir, words, src_lang, dst_lang):
    tokens = list(sorted(set(w[0] for w in words)))
    cache_path = get_translation_cache_path(video_dir, src_lang, dst_lang,
                                            md5_hash(''.join(tokens)))
    if os.path.exists(cache_path):
        print('Already cached: {} -> {}, {}'.format(
              src_lang, dst_lang, video_dir), file=sys.stderr)
        with open(cache_path, 'r') as f:
            trans_dict = json.load(f)
    else:
        print('Translating: {} -> {}, {}'.format(
              src_lang, dst_lang, video_dir), file=sys.stderr)
        translator = Translator.new(src_lang, dst_lang)
        trans_dict = {}
        for w, tag in words:
            try:
                trans_dict[w] = translator.word(w, tag)
            except Exception as e:
                print('Error {}: {}'.format(e, w), file=sys.stderr)
        with open(cache_path, 'w') as f:
            json.dump(trans_dict, f)
    return trans_dict


Caption = namedtuple('CaptionLine', ['start', 'end', 'text', 'tokens'])


def get_translation_dict(video_dir, src_lang, dst_lang):
    lines = read_vtt(get_native_sub_path(video_dir, src_lang))

    tagger = Tagger.new(src_lang)
    trans_set = set()

    tokenized_lines = []
    for line in lines:
        tokens = tagger.tag(line.text)
        tokenized_lines.append(line._replace(tokens=tokens))
        trans_set.update([
            (w.text.strip(), w.tag) for w in tokens if w.text.strip() != ''])
    return translate_sub_words(video_dir, trans_set, src_lang, dst_lang)


def parse_youtube_url(url):
    m = re.search(r'^([\-\w]+)$', url)
    if m:
        return m.group(1)
    m = re.search(r'youtu.be/([\-\w]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'v=([\-\w]+)', url)
    if m:
        return m.group(1)
    return None


def list_caption_languages(video_dir):
    languages = []
    for name in os.listdir(video_dir):
        m = re.search('video.([\-\w]+).vtt', name)
        if m:
            languages.append(m.group(1))
    languages.sort()
    return languages


def get_video_info(video_dir):
    with open(os.path.join(video_dir, 'video.info.json')) as f:
        return json.load(f)


def build_flask_app(cache_dir):
    app = Flask(__name__)

    def get_video_dir(video):
        return os.path.join(cache_dir, video)

    @app.route('/')
    def root():
        videos = []
        for video in os.listdir(cache_dir):
            if os.path.isdir(get_video_dir(video)):
                info = get_video_info(get_video_dir(video))
                videos.append({'id': video, 'title': info.get('title', '')})
        return render_template('home.html', videos=videos)

    def get_other_languages(native):
        if not native:
            return []
        languages = []
        has_en = any(l.startswith('en') for l in native)
        for l in Tagger.languages():
            if l in native or not l.startswith('en') or (not has_en and l == 'en'):
                languages.append(l)
        languages.sort()
        return languages

    @app.route('/player')
    def player():
        url = request.args.get('url')
        video = parse_youtube_url(url)
        if video is None:
            return 'No video found', 404
        video_dir = get_video_dir(video)
        download_url = 'https://youtu.be/' + video
        if FORCE_DOWNLOAD or not os.path.isdir(video_dir):
            download_video(download_url, video_dir, Tagger.languages())
        video_info = get_video_info(video_dir)
        cc_languages = list_caption_languages(video_dir)
        all_languages = get_other_languages(cc_languages)
        return render_template(
            'player.html', url=download_url, video=video,
            title=video_info.get('title', ''),
            cc_languages=cc_languages, all_languages=all_languages)

    @app.route('/captions/<video>')
    def captions(video):
        lang = request.args.get('lang')
        video_dir = get_video_dir(video)
        native_sub_path = get_native_sub_path(video_dir, lang)
        if os.path.exists(native_sub_path):
            captions = read_vtt(native_sub_path)
        else:
            trans_sub_path = get_translated_sub_path(video_dir, lang)
            if not os.path.exists(trans_sub_path):
                orig = request.args.get('orig')
                if not orig:
                    return 'No original language to translate', 400
                translate_sub_file(video_dir, orig, lang)
            captions = read_vtt(trans_sub_path)
        tagger = Tagger.new(lang)
        captions = [
            line._replace(tokens=tagger.tag(line.text))
            for line in captions]
        response = jsonify(captions)
        response.cache_control.max_age = 3600
        return response

    @app.route('/translations/<video>')
    def translation_dict(video):
        video_dir = get_video_dir(video)
        src_lang = request.args.get('src')
        dst_lang = request.args.get('dst')
        if src_lang == dst_lang:
            return 'Source language cannot equal destination language', 400
        response = jsonify(get_translation_dict(video_dir, src_lang, dst_lang))
        response.cache_control.max_age = 3600
        return response

    @app.route('/thumbnail/<video>')
    def thumbnail(video):
        video_dir = get_video_dir(video)
        return send_from_directory(video_dir, 'video.jpg')

    return app


def main(host, port, cache_dir, api_key_file):
    set_api_key(api_key_file)
    app = build_flask_app(cache_dir)
    app.run(host=host, port=port, debug=True)


if __name__ == '__main__':
    main(**vars(get_args()))
