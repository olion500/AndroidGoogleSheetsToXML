from __future__ import print_function

import io
import pickle
import os.path
import re

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# If modifying these scopes, delete the file token.pickle.
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# The ID and range of a sample spreadsheet.
SAMPLE_SPREADSHEET_ID = '1OVRSEmBCXbEl52ZlBwA8_WVm0eiOSXZbJLmkiqf9h0g'
SAMPLE_RANGE_NAME = 'Android'

OUTPUT_FOLDER = './output/'
languages = ['ko', 'en', 'zh', 'ja', 'zh-rCN', 'fr']
lang_index = [1, 3, 4, 5, 6, 7]  # index for each language value

default_language = 'en'
default_android_project = r"C:\Users\quara\Documents\projects\kosho-adr"

pattern = r"<([a-z][a-z0-9]*)\b[^>]*>(.*?)</\1>"


def replace_escape_word(content):
    if not len(content) > 0:
        return content

    tmp = content
    tmp = tmp.replace("\'", "\\'")
    tmp = tmp.replace('\"', '\\"')
    tmp = tmp.replace('&', '&amp;')
    tmp = tmp.replace('...', '&#8230;')
    tmp = tmp.replace('\\\\', '\\')

    return tmp


def handle_nested_html(content):
    phase = 0
    start_tag_start, start_tag_end = 0, 0
    end_tag_start, end_tag_end = 0, 0

    for idx, ch in enumerate(content):
        if ch == '<' and phase == 0:
            start_tag_start = idx
            phase += 1

        elif ch == '>' and phase == 1:
            start_tag_end = idx
            phase += 1

        elif ch == '<' and phase == 2:
            end_tag_start = idx
            phase += 1

        elif ch == '>' and phase == 3:
            end_tag_end = idx
            phase += 1

    # if phase is 4, nested tag exist.
    return phase == 4, start_tag_start, start_tag_end, end_tag_start, end_tag_end


def replace_escape_line(txt):
    matches = re.findall(pattern, txt)
    try:
        content = matches[0][1]
        content_start = txt.find(content)
        content_end = len(txt) - 9      # 9 is the length of '</string>'
        is_nested, start_tag_start, start_tag_end, end_tag_start, end_tag_end = handle_nested_html(content)

        if not is_nested:
            escape_changed = replace_escape_word(content)
            return txt.replace(content, escape_changed)
        else:
            # 1. content before nested tag
            before_nested = content[content_start: start_tag_start]
            before_nested_changed = replace_escape_word(before_nested)

            # 2. inside of nested tag
            inside_nested = content[start_tag_end+1: end_tag_start]
            inside_nested_changed = replace_escape_word(inside_nested)

            # 3. content after nested tag
            after_nested = content[end_tag_end+1: content_end]
            after_nested_changed = replace_escape_word(after_nested)

            if len(before_nested) > 0:
                txt = txt.replace(before_nested, before_nested_changed)

            if len(inside_nested) > 0:
                txt = txt.replace(inside_nested, inside_nested_changed)

            if len(after_nested) > 0:
                txt = txt.replace(after_nested, after_nested_changed)

            return txt

    except IndexError:
        return txt

def writeline(f, txt, tab=True):
    txt = txt.strip()
    if tab:
        f.write("    " + replace_escape_line(txt) + "\n")
    else:
        f.write(txt + "\n")


def writefile(f, idx_lang, sheet, additional=''):
    id_idx = 0  # index for android string key.

    writeline(f, '<?xml version="1.0" encoding="utf-8"?>', False)
    writeline(f, "<resources>", False)

    if len(additional) > 0:
        f.write(additional)

    for row in sheet[2:]:   # start from inside of <resources>
        try:
            key = row[id_idx]
            if len(key) > 0 and str(key).startswith('<!--'):    # for the comment on google sheet
                writeline(f, key)
            else:
                writeline(f, "<string name=\"{}\">{}</string>".format(key, row[idx_lang]))
        except IndexError:
            writeline(f, '')

    writeline(f, "</resources>", False)


def transform_strings(non_translatable_string_array):
    last_string_tag = 0
    for idx, line in enumerate(non_translatable_string_array):
        if line.startswith("    <string"):
            last_string_tag = idx

    if last_string_tag == 0:
        result = "".join(non_translatable_string_array)
    else:
        non_translatable_string_array[last_string_tag] += '\n'
        result = "".join(non_translatable_string_array[:last_string_tag+1])

    return result


def save(sheet):
    # 1. create dicts for use
    dict_col = dict(zip(languages, lang_index))

    # 2. create xml file for each language
    for lang in languages:

        dir = os.path.join(OUTPUT_FOLDER, 'values-' + lang)
        if not os.path.exists(dir):
            os.mkdir(dir)

        f = io.open(os.path.join(dir, 'strings.xml'), "w", encoding='utf8')
        idx_lang = dict_col.get(lang)

        writefile(f, idx_lang, sheet)
        f.close()

    # 3. retrieve current string from android project path,
    path_current = os.path.join(default_android_project, r'app\src\main\res\values\strings.xml')
    f_current = io.open(path_current, 'r', encoding='utf8')
    # non_translatable_strings = ''
    non_translatable_string_array = []
    if not os.path.isfile(path_current):
        print('not found android project. skipping this process...')
    else:
        for line in f_current:
            if line.startswith('<resources>'):
                continue

            if 'translatable=\"false\"' in line or '<!--' in line or line == '\n':
                non_translatable_string_array.append(line)
                # non_translatable_strings += line

    f_current.close()

    # 4. create xml file for default language
    dir = os.path.join(OUTPUT_FOLDER, 'values')
    if not os.path.exists(dir):
        os.mkdir(dir)

    f = io.open(os.path.join(dir, 'strings.xml'), 'w', encoding='utf8')
    idx_lang = dict_col.get(default_language)
    # writefile(f, idx_lang, sheet, non_translatable_strings)
    writefile(f, idx_lang, sheet, transform_strings(non_translatable_string_array))


def config():
    print('begin configurations. Enter to input as the default')
    input_def_lang = input('1. choose default language({}):'.format(', '.join(languages)))
    if len(input_def_lang) > 0 and languages.__contains__(input_def_lang):
        global default_language
        default_language = input_def_lang

    input_adr_dir = input('2. input android dir to get current strings.xml:')
    if len(input_adr_dir) > 0 and os.path.isdir(input_adr_dir):
        global default_android_project
        default_android_project = input_adr_dir


def main():
    """Shows basic usage of the Sheets API.
    Prints values from a sample spreadsheet.
    """
    print('start getting credential...', end=' ')
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow Dones for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        print('waiting for log in...', end=' ')
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    print('Done')
    print('load data from Google Sheets...', end=' ')

    service = build('sheets', 'v4', credentials=creds)

    # Call the Sheets API
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SAMPLE_SPREADSHEET_ID, range=SAMPLE_RANGE_NAME).execute()
    values = result.get('values', [])

    if not values:
        print('No data found.')
    else:
        print('Done')
        print('start parsing...', end=' ')

        # config()
        save(values)

        print('Done')
        print('All tasks are completed. You can find the output in {}'.format(OUTPUT_FOLDER))


if __name__ == '__main__':
    main()
