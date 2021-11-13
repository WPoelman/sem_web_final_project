#!/usr/bin/env python

"""
A program to retrieve the English infobox from a given Wikipedia page title,
then either expand the existing Dutch infobox or create a new Dutch infobox.
"""

import argparse
import json
import sys

import requests
import wptools
from deep_translator import GoogleTranslator

from extract_mappings import Mapper, Mapping
from specific_cases import *
from utils import *


def create_arg_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-t",
                        "--title",
                        default='The Very Hungry Caterpillar',
                        type=str,
                        help=("Title of the English wikipedia page (default: "
                              " 'The Very Hungry Caterpillar')"))
    parser.add_argument("-m",
                        "--mapper",
                        default='data/mapper.pickle',
                        type=str,
                        help="Path to a trained mapper object.")
    args = parser.parse_args()
    return args


def get_dutch_title(en_title):
    """Use the English title of a Wikipedia page to get the Dutch title"""
    try:
        URL = "https://en.wikipedia.org/w/api.php"
        PARAMS = {
            "action": "query",
            "titles": en_title,
            "prop": "langlinks",
            "lllang": "nl",
            "format": "json"
        }

        results = requests.get(url=URL, params=PARAMS).json()
        pages = [p for p in results['query']['pages']]
        for p in pages:  # There is probably only one page
            dutch_title = results['query']['pages'][p]['langlinks'][0]['*']
    except:
        # Return the English title instead
        return en_title

    return dutch_title


def get_infobox(title, language='en'):
    """Use the title of a Wikipedia page to get the infobox"""
    try:
        page = wptools.page(title, lang=language,
                            silent=True, verbose=False).get_parse(show=False)
        infobox = page.data['infobox']
    except:
        infobox = None

    return infobox


def translate(value, source='en', target='nl'):
    """Translate from the source to the target language"""
    try:
        translated_val = GoogleTranslator(
            source=source, target=target).translate(value)
    except:
        return value
    return translated_val


def evaluate(true_infobox, gen_infobox):
    item_count_true = len(true_infobox.keys())
    item_count_generated = len(gen_infobox.keys())

    correct_keys = true_infobox.keys() & gen_infobox.keys()
    correct_values = set(true_infobox.values()) & set(gen_infobox.values())

    pairs_true = {(k, v) for k, v in true_infobox.items()}
    pairs_generated = {(k, v) for k, v in gen_infobox.items()}

    correct_pairs = pairs_generated & pairs_true

    print(f'''
    --- true infobox ---
    {json.dumps(true_infobox, indent=4)}

    --- generated infobox ---
    {json.dumps(gen_infobox, indent=4)}


    items in true infobox:      {item_count_true}
    items in genreated infobox: {item_count_generated}

    correct keys:           {len(correct_keys)} / {item_count_generated}
    correct values keys:    {len(correct_values)} / {item_count_generated}
    correct key AND value:  {len(correct_pairs)} / {item_count_generated}
    ''')


if __name__ == "__main__":
    args = create_arg_parser()

    mapper: Mapper = load_pickle(args.mapper)

    # Get EN title and retrieve English wikipedia infobox
    en_title = args.title
    en_infobox = get_infobox(en_title)

    # If there is no EN infobox, we stop here, else we try to get
    # the NL infobox as well
    if not en_infobox:
        print("There is no infobox available for this Wikipedia page, "
              "please try another title.", file=sys.stderr)
        exit(1)

    # Get NL title and retrieve Dutch wikipedia infobox
    nl_title = get_dutch_title(en_title)
    nl_infobox = get_infobox(nl_title, 'nl')
    if nl_infobox:
        nl_infobox_clean = clean_ib_dict(nl_infobox)

    # Clean the English infobox
    en_infobox_clean = clean_ib_dict(en_infobox)

    # todo: various steps of filling the new infobox
    # We try to generate the NL infobox
    nl_new_infobox = dict()
    chosen_keypairs = dict()  # Here we store which EN and NL keys we picked
    for en_key in en_infobox_clean:
        # TODO: test if we want fuzzy here or not
        nl_key_options = mapper.translate(en_key)

        if nl_key_options:
            # TODO: find a way to rank these and pick the best one
            # (key co-occurrence maybe? On both the Dutch and English
            # training sets?)
            nl_key = nl_key_options[0]
            nl_new_infobox[nl_key] = en_infobox_clean[en_key]
            chosen_keypairs[en_key] = nl_key
        # If the label is not in our mapping, simply translate the English
        # label to a Dutch label
        else:
            nl_key = translate(en_key)
            if nl_key not in nl_new_infobox:
                # todo: decide whether we want to just use the same value
                # in this case
                nl_new_infobox[nl_key] = en_infobox_clean[en_key]
                chosen_keypairs[en_key] = nl_key

    # We update the dictionary by handling specific cases for generating labels
    nl_new_infobox = handle_specific_cases(en_infobox_clean,
                                           nl_new_infobox,
                                           chosen_keypairs,
                                           en_title,
                                           nl_title)

    # TODO: this is disabled for the moment since we don't have a way of
    # validating the process of adding to an existing box yet
    # Finally, if there is an existing NL infobox, we first use those
    # key-value pairs and add only the missing ones from our generated
    # infobox to it.
    # if nl_infobox:
    #     cleaned_nl = clean_ib_dict(nl_infobox)
    #     for key in nl_new_infobox:
    #         if key not in cleaned_nl:
    #             cleaned_nl[key] = nl_new_infobox[key]
    # else:
    #     cleaned_nl = nl_new_infobox

    if nl_infobox_clean:
        evaluate(nl_infobox_clean, nl_new_infobox)
    else:
        print(f'Cannot evaluate {en_title} since there is no Dutch infobox')

    # The combination of the existing infobox with our own infobox
    # print(cleaned_nl)
    # print(nl_new_infobox)  # Our self created infobox so far
