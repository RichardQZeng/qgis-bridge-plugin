from collections import OrderedDict

from qgis.gui import QgsMetadataWidget

from geocatbridge.utils import feedback

#: Lookup of language name: ISO-639/1 code
label2code = OrderedDict({
    'Abkhazian': 'ab',
    'Afar': 'aa',
    'Afrikaans': 'af',
    'Albanian': 'sq',
    'Amharic': 'am',
    'Arabic': 'ar',
    'Armenian': 'hy',
    'Assamese': 'as',
    'Aymara': 'ay',
    'Azerbaijani': 'az',
    'Bashkir': 'ba',
    'Basque': 'eu',
    'Bengali (Bangla)': 'bn',
    'Bhutani': 'dz',
    'Bihari': 'bh',
    'Bislama': 'bi',
    'Breton': 'br',
    'Bulgarian': 'bg',
    'Burmese': 'my',
    'Byelorussian (Belarusian)': 'be',
    'Cambodian': 'km',
    'Catalan': 'ca',
    'Chinese': 'zh',
    'Corsican': 'co',
    'Croatian': 'hr',
    'Czech': 'cs',
    'Danish': 'da',
    'Dutch': 'nl',
    'English': 'en',
    'Esperanto': 'eo',
    'Estonian': 'et',
    'Faeroese': 'fo',
    'Farsi': 'fa',
    'Fiji': 'fj',
    'Finnish': 'fi',
    'French': 'fr',
    'Frisian': 'fy',
    'Galician': 'gl',
    'Gaelic (Scottish)': 'gd',
    'Gaelic (Manx)': 'gv',
    'Georgian': 'ka',
    'German': 'de',
    'Greek': 'el',
    'Greenlandic': 'kl',
    'Guarani': 'gn',
    'Gujarati': 'gu',
    'Hausa': 'ha',
    'Hebrew': 'he',
    'Hindi': 'hi',
    'Hungarian': 'hu',
    'Icelandic': 'is',
    'Indonesian': 'id',
    'Interlingua': 'ia',
    'Interlingue': 'ie',
    'Inuktitut': 'iu',
    'Inupiak': 'ik',
    'Irish': 'ga',
    'Italian': 'it',
    'Japanese': 'ja',
    'Javanese': 'jv',
    'Kannada': 'kn',
    'Kashmiri': 'ks',
    'Kazakh': 'kk',
    'Kinyarwanda (Ruanda)': 'rw',
    'Kirghiz': 'ky',
    'Kirundi (Rundi)': 'rn',
    'Korean': 'ko',
    'Kurdish': 'ku',
    'Laothian': 'lo',
    'Latin': 'la',
    'Latvian (Lettish)': 'lv',
    'Limburgish (Limburger)': 'li',
    'Lingala': 'ln',
    'Lithuanian': 'lt',
    'Macedonian': 'mk',
    'Malagasy': 'mg',
    'Malay': 'ms',
    'Malayalam': 'ml',
    'Maltese': 'mt',
    'Maori': 'mi',
    'Marathi': 'mr',
    'Moldavian': 'mo',
    'Mongolian': 'mn',
    'Nauru': 'na',
    'Nepali': 'ne',
    'Norwegian': 'no',
    'Occitan': 'oc',
    'Oriya': 'or',
    'Oromo (Afan, Galla)': 'om',
    'Pashto (Pushto)': 'ps',
    'Polish': 'pl',
    'Portuguese': 'pt',
    'Punjabi': 'pa',
    'Quechua': 'qu',
    'Rhaeto-Romance': 'rm',
    'Romanian': 'ro',
    'Russian': 'ru',
    'Samoan': 'sm',
    'Sangro': 'sg',
    'Sanskrit': 'sa',
    'Serbian': 'sr',
    'Serbo-Croatian': 'sh',
    'Sesotho': 'st',
    'Setswana': 'tn',
    'Shona': 'sn',
    'Sindhi': 'sd',
    'Sinhalese': 'si',
    'Siswati': 'ss',
    'Slovak': 'sk',
    'Slovenian': 'sl',
    'Somali': 'so',
    'Spanish': 'es',
    'Sundanese': 'su',
    'Swahili (Kiswahili)': 'sw',
    'Swedish': 'sv',
    'Tagalog': 'tl',
    'Tajik': 'tg',
    'Tamil': 'ta',
    'Tatar': 'tt',
    'Telugu': 'te',
    'Thai': 'th',
    'Tibetan': 'bo',
    'Tigrinya': 'ti',
    'Tonga': 'to',
    'Tsonga': 'ts',
    'Turkish': 'tr',
    'Turkmen': 'tk',
    'Twi': 'tw',
    'Uighur': 'ug',
    'Ukrainian': 'uk',
    'Urdu': 'ur',
    'Uzbek': 'uz',
    'Vietnamese': 'vi',
    'Volapük': 'vo',
    'Welsh': 'cy',
    'Wolof': 'wo',
    'Xhosa': 'xh',
    'Yiddish': 'yi',
    'Yoruba': 'yo',
    'Zulu': 'zu'
})

code2label = {}


def _load():
    """ Validate label2code dict against supported QGIS languages and populate reverse lookup (code -> label). """
    global label2code, code2label

    qgis_lang = QgsMetadataWidget().parseLanguages()
    for label, code in label2code.copy().items():
        if code not in qgis_lang:
            # feedback.logWarning(f"{label} ({code}) not in QGIS language definitions")
            label2code.pop(label)
            continue
        if code in code2label:
            feedback.logWarning(f"Ignoring '{label}' ({code}): code already used by '{code2label.get(code)}'")
            continue
        code2label[code] = label


_load()