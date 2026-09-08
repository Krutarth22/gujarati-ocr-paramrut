"""
Shri Lipi (Shree Gujarati 7) to Unicode Gujarati Converter
Calibrated for "Pardarshi Paravani" PDF (font: SHREE-GUJ7-0751 / 0764)
"""

import re

# ── Phase 0: Pre-process (longest sequences first, applied before char loop) ─
PRE_PROCESS_MAPPINGS = [
    # Multi-char special sequences
    ('[óV$',  'ષ્ટિ'),   # ShTi ligature
    ('[ÞX$',  'ન્ડિ'),   # nDi ligature
    ('A„s×',  'અંતદૃ'),  # antadRu (antardrushti prefix)
    ('Ap¡¡',  'ઓ'),      # standalone O vowel (double e-matra variant)
    ('DW$ep ¡', 'ઉઠ્યો'), # UTHyo special case
    ('&&',    '।।'),     # old half marker, e.g. ૩।। વાગે / ૩।। વર્ષ

    # Standalone independent vowels (A-prefixed sequences → independent vowel)
    # ORDER: longest first so Ap¡ is caught before Ap
    ('Ap¡',   'ઓ'),      # standalone O (o vowel, U+0A93)
    ('A¥',    'ઐ'),      # standalone AI (ai vowel, U+0A90)
    ('A¡',    'એ'),      # standalone E (e vowel, U+0A8F)
    ('Ap',    'આ'),      # standalone AA (long aa vowel, U+0A86)
]

# ── Composite Mappings (2-char sequences, checked before single-char) ─────────
COMPOSITE_MAPPINGS = [
    ('p¡', 'ો'),    # aa-matra + e-matra → o-matra (ો)
    ('p¥', 'ૌ'),    # aa-matra + au-matra → au-matra (ૌ)
    ('L$', 'ક'),    # L$ → ka
    ('X$', 'ડ'),    # X$ → da (retroflex)
    ('V$', 'ટ'),    # V$ → Ta (retroflex)
    ('v$', 'દ'),    # v$ → da
    ('W$', 'ઠ'),    # W$ → Tha
    ('R>', 'છ'),    # R> → Chha
    ('S>', 'જ'),    # S> → Ja
    ('{$', 'રુ'),   # {$ → ru
    ('›$', 'ષ્ઠ'),  # ›$ → ShTha (niShThA, shreshTha)
    ('¾$', 'ક્ર'),  # ¾$ → kra (krodha, cricket)
    ('½$', 'ક્ક'),  # ½$ → kka (chokkasa, nakkI)
    ('Ë$', 'ટ્ટ'),  # Ë$ → TTa (bhaTTa)
]

# ── Single-Character Mappings ─────────────────────────────────────────────────
SHRI_LIPI_TO_UNICODE = {
    # ── Independent Vowels ──────────────────────────────────────────────────
    'A': 'અ',   # short a  (standalone long AA handled in pre-process as Ap→આ)
    'B': 'ઇ',   # short i
    'C': 'ઈ',   # long I
    'D': 'ઉ',   # short u
    'E': 'ઊ',   # long U
    'F': 'ઋ',   # Ru vowel

    # ── Consonants ──────────────────────────────────────────────────────────
    'k': 'સ',   # sa
    'K': 'ખ',   # kha
    'g': 'લ',   # la
    'G': 'ઘ',   # gha
    'c': 'ભ',   # bha
    'j': 'ષ',   # Sha (retroflex sha)
    'J': 'ઝ',   # jha (voiced)
    't': 'ટ',   # Ta (retroflex)
    'T': 'ઝ',   # jha (alternate)
    'd': 'મ',   # ma
    's': 'ત',   # ta
    'S': 'શ',   # sha
    'h': 'વ',   # va
    'L': 'ક',   # ka
    'M': 'ખ',   # kha (alternate)
    'X': 'ડ',   # Da (retroflex)
    'Z': 'ણ',   # Na (retroflex)
    'R': 'છ',   # Chha
    'f': 'ર',   # ra
    'b': 'બ',   # ba
    'm': 'ળ',   # La (retroflex la)
    'N': 'ગ',   # ga
    'v': 'દ',   # da
    'V': 'ટ',   # Ta (alternate)
    'n': 'ક્ષ', # kSha (conjunct)
    '^': 'ધ',   # dha
    'l': 'હ',   # ha
    'i': 'શ',   # sha (alternate slot)
    'Q': 'ચ',   # cha
    'a': 'ફ',   # pha/fa
    'O': 'ઘ',   # gha (alternate)
    'P': 'પ',   # pa
    '`': 'પ',   # pa alternate

    # ── Half-forms / Conjunct starters ──────────────────────────────────────
    'Ð': 'ત્',  # half-ta  (ta + virama) — before s/k/p
    'Ä': 'ત્',  # half-ta  (ta + virama) — before y (ty conjunct)
    'Ò': 'ત્',  # half-ta  (ta + virama) — before v (tv conjunct)
    'ë': 'લ્',  # half-la
    '¿': 'ખ્',  # half-kha
    '¼': 'ક્',  # half-ka
    'Ã': 'ચ્',  # half-cha
    'Þ': 'ન્',  # half-na
    'Ý': 'ધ્',  # half-dha
    'õ': 'સ્',  # half-sa
    'ì': 'વ્',  # half-va  (va + virama) — before y (vy conjunct)
    'à': 'પ્',  # half-pa  (pa + virama) — before l/r (pl/pr conjunct starters)
    'þ': 'લ્',  # half-la  (la + virama) — for kly/mly conjuncts
    'Á': 'ગ્',  # half-ga  (ga + virama) — for gy conjunct (bhAgya etc.)

    # ── Conjunct ligatures (multi-char glyphs encoded as single char) ────────
    'î': 'શ્ર',  # shra ligature
    'Æ': 'જી',   # jI (ja + I-matra)
    'Å': 'જા',   # jA (ja + aa-matra)
    '°': '્ર',   # -ra (subscript, virama + ra)
    '²': '્ર',   # -ra (alternate)
    'û': 'હ્મ',  # hma ligature
    'â': 'પ્ર',  # pra ligature
    'ô': 'ષ્ટ',  # ShTa ligature
    '‰': 'લ્લ',  # lla (half-la + la)
    '‛': 'સ્ત્ર', # stra conjunct
    'ê': 'રુ',   # ru (ra + u-matra)
    'Ó': 'ત્ર',  # tra ligature
    'Ô': 'ત્ર',  # tra ligature alternate
    '{': 'રુ',   # ru (alternate)
    '»': 'ૃ',   # Ru-matra (vocalic R matra)
    '©': 'ૃ',   # Ru-matra (alternate slot)
    'ü': 'ષ્ટિ', # ShTi (ShTa + i-matra)
    '×': 'દૃ',   # dRu (da + Ru-matra)
    'ù': 'હૃ',   # hRu (ha + Ru-matra)
    'ú': 'હૃ',   # hRu (alternate slot — for suhRdbhAva)
    'Ù': 'દ્ધ',  # ddha ligature
    'Ñ': 'ત્ત',  # tta (double ta)
    'Y': 'ઢ',   # Dha (retroflex)
    'Ö': 'દ્ર',  # dra ligature (da + virama + ra)
    'Ü': 'દ્વ',  # dva ligature (da + virama + va)
    'Û': 'દ્ય',  # dya ligature (da + virama + ya) — for vidyA
    'á': 'પ્ત',  # pta conjunct (pa + virama + ta)
    'Î': 'ણ',   # Na retroflex (alternate slot, same as Z)
    'Ï': 'ણુ',   # Na + u-matra (for ghaNuM, ApaNuM)
    'ñ': 'શ્ન',  # shna conjunct
    'ò': 'શ્ચ',  # shcha conjunct (for nishchaya)
    'Õ': 'થ',   # Tha (alternate slot, same as ')
    'ð': 'શ્વ',  # shva ligature (sha + va, for vishvAs)
    'Ì': 'ઠ',   # Tha (for chiTThI context)
    'Ÿ': 'ર',   # ra (alternate slot)
    'Â': 'ર',   # ra (alternate, for kharyuM etc.)
    'o': 'જ્ઞ', # jna ligature (j્ઞાન, યજ્ઞ)
    'Ç': 'જ્ર', # jra conjunct (વજ્ર)
    'ˆ': 'જ્જ', # jja conjunct (કરોડરજ્જુ)
    'Ú': 'દ્મ', # dma conjunct (પદ્મ)
    'À': 'ખ્ર', # khra conjunct (ખ્રિસ્ત્રી)
    'Í': 'ડ્ડ', # DDa conjunct (કબડ્ડી)
    '”': 'સ્ત્ર', # stra conjunct alternate
    '³': '્રુ',  # -ru conjunct/matra sequence (ટ્રુથ)

    # ── Additional consonant alternates ─────────────────────────────────────
    'å': 'બ',   # ba (alternate slot — for public/shabda)
    'æ': 'ભ',   # bha (alternate slot — for abhyAs)
    'ç': 'મ',   # ma (alternate slot — for janmyo)
    'ï': 'શ',   # sha (alternate — for vishvAs, ashlIla)
    'ä': 'ફ',   # pha/fa (alternate — for Africa)
    'Ø': 'ક',   # ka (alternate — for mushkil)
    'W': 'ઠ',   # Tha alternate
    'ã': 'ફ',   # pha/fa alternate (ફ્લેક્સિબલ, ફ્યુઅલ)
    'H': 'ઈ',   # independent I alternate (ઈંચ, ઈંગ્લીશ)
    'I': 'ઈ',   # independent I alternate (ઈંચ, ઈંટ)
    'è': 'ય',   # ya alternate
    '\\': 'થ',  # tha alternate

    # ── Matras (vowel signs) ─────────────────────────────────────────────────
    'p': 'ા',   # aa-matra
    '¡': 'ે',   # e-matra
    '¸': 'ે',   # e-matra (alternate)
    '¥': 'ૈ',   # ai-matra
    'u': 'ી',   # I-matra (long i)
    'y': 'ુ',   # u-matra (short u)
    '|': 'ૂ',   # U-matra (long u)
    'w': 'ૂ',   # U-matra alternate
    'z': 'ુ',   # u-matra alternate
    'º': 'ું',  # u + anusvara (combined)
    'r': 'િ',   # i-matra (pre-matra form — handled specially in loop)
    'q': 'િ',   # i-matra (alternate pre-matra)
    '„': 'ં',   # anusvara
    '®': 'ર્',  # reph (ra + virama, appears after consonant in Shri Lipi)
    '£': 'ર્ે', # reph + e-matra
    'e': 'ય',   # ya (consonant/semi-vowel)
    'ƒ': '',    # font artifact / zero-width (mA- prefix separator)
    ']': 'ં',   # anusvara/chandrabindu-style nasal marker
    '˜': 'મૃ',  # mRu ligature (અમૃત)
    '&': '।',   # old single half marker fragment

    # ── Symbols quoted punctuation mapped to consonants in this font ─────────
    '‘': 'પ',   # pa  (opening single quote slot)
    '’': 'થ',   # tha (closing single quote slot)
    '‚': 'ન',   # na  (low-9 quote slot)

    # ── Additional unmapped characters (identified from corpus) ─────────────
    'ó': 'ષ',   # Sha (retroflex sha) — standalone in manuShya, niShkrodha  U+00F3
    '¢': 'ં',   # anusvara alt (hAM, mAM, pahAMchI)  U+00A2
    '¹': '્',   # virama alt (tadna, sadguru, asadgati)  U+00B9
    'é': 'ય',   # ya alt (paDyA, uThayo)  U+00E9
    'í': 'શ',   # sha alt (Ghanshyam, mushkil, dushman)  U+00ED
    'ý': 'ળ',   # LA alt (sAMbhALyA, gALyuM)  U+00FD
    '¯': 'ં',   # anusvara alt (karyuM, sarvAMga, dugandha)  U+00AF
    'ÿ': 'ક્ષ', # kSha alt (LakShmaNa)  U+00FF
    'ß': 'ધ',   # dha alt (baMdhey, adha)  U+00DF
    '¦': 'વ',   # va alt (pAvA, saundarya)  U+00A6
    '±': 'ૐ',   # OM symbol (OM namo, OM mAM brahma)  U+00B1
    'È': 'ઝ',   # jha alt (sUjhayuM, visualize)  U+00C8
    '÷': 'સ્ત્ર', # str ligature (strI)  U+00F7
    '“': 'ન',   # na (sAdhanA, mahArAjanA, vachane)  U+201C
    '_': 'ન',   # na (strIne, ene)  U+005F
    '›': 'ષ્ઠ', # ShTha standalone  U+203A
    '¾': 'ક્ર', # kra standalone  U+00BE
    '½': 'ક',   # ka standalone  U+00BD
    'Ë': 'ટ્ટ', # TTa standalone  U+00CB
    # Private-use area list bullets (Shri Lipi decorative glyphs)
    '': '',
    '': '',
    '': '',
    '': '',
    '•': '',

    # ── Pass-through / neutrals ───────────────────────────────────────────────
    '>': '',    # composite trailer (consumed by R>, S>)
    '$': '',    # composite trailer (consumed by L$, X$, V$, v$, W$)
    '[': '',    # composite trailer
    '.': '.', ',': ',', '-': '-', '–': '–', '—': '—',
    '(': '(', ')': ')',
    '!': '!', '?': '?', '"': '"', '\'': '\'',
    ':': ':', ';': ';', '/': '/',
    ' ': ' ', '\n': '\n', '\t': '\t', '\r': '\r',

    # ── Gujarati numerals ─────────────────────────────────────────────────────
    '1': '૧', '2': '૨', '3': '૩', '4': '૪', '5': '૫',
    '6': '૬', '7': '૭', '8': '૮', '9': '૯', '0': '૦',

    # ── Special ───────────────────────────────────────────────────────────────
    '%': '%',
    '©': 'ૃ',  # duplicate key fine — last wins (Ru-matra)
}


def remove_bold_duplicates(text: str) -> str:
    """
    Remove bold-simulation duplicates where 'bold' is rendered by printing
    a character twice (a common DTP workaround). Only applied to lines where
    >30% of adjacent chars are identical pairs.
    """
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        total = len(line)
        if total < 2:
            new_lines.append(line)
            continue
        repeats = sum(1 for i in range(total - 1) if line[i] == line[i + 1])
        if repeats / total > 0.30:
            deduped = []
            skip = False
            for i in range(total):
                if skip:
                    skip = False
                    continue
                if i < total - 1 and line[i] == line[i + 1]:
                    deduped.append(line[i])
                    skip = True
                else:
                    deduped.append(line[i])
            new_lines.append(''.join(deduped))
        else:
            new_lines.append(line)
    return '\n'.join(new_lines)


def cleanup_unicode_gujarati(text: str) -> str:
    """Clean spacing artifacts introduced by PDF text extraction."""
    gujarati_letter = r'[\u0a85-\u0ab9\u0ae0-\u0ae1]'
    gujarati_matra = r'[\u0abe-\u0ac5\u0ac7-\u0ac9\u0acb-\u0acd]'

    # Conjuncts are often extracted with a space after virama: વ્ યક્તિ.
    text = re.sub(r'્[ \t]+(?=' + gujarati_letter + r'|' + gujarati_matra + r')', '્', text)
    # Matras can be separated from the base consonant: વરસ ે, મીઠ ુ.
    text = re.sub(r'(?<=' + gujarati_letter + r')[ \t]+(?=' + gujarati_matra + r')', '', text)
    # Rare duplicate viramas come from overprinted source glyphs.
    text = re.sub(r'્{2,}', '્', text)
    # Broken running headers can leave lines like "ે ૧" after extraction.
    text = re.sub(r'(?m)^[\u0abe-\u0ac5\u0ac7-\u0acc]\s*[૦-૯]+\s*\n?', '', text)
    return text


def convert_shri_lipi_to_unicode(text: str) -> str:
    """Convert Shri Lipi 7 encoded text to Unicode Gujarati."""
    if not text:
        return ''

    # Phase -1: remove bold duplicates
    text = remove_bold_duplicates(text)

    # Phase 0: pre-process multi-char sequences (longest first)
    for src, dst in PRE_PROCESS_MAPPINGS:
        text = text.replace(src, dst)

    chars = list(text)
    result = []
    i = 0
    length = len(chars)

    while i < length:
        char = chars[i]

        # ── 1. Pre-matra (i-matra, chhoti i) ────────────────────────────────
        # 'r' and 'q' appear BEFORE the consonant in Shri Lipi but must be
        # written AFTER it in Unicode. We buffer the flag and emit after.
        is_pre_matra = char in ('r', 'q')
        if is_pre_matra:
            if i + 1 < length:
                i += 1  # advance to the consonant
            else:
                i += 1
                continue

        # ── 2. Reph look-ahead (®, £, }) ─────────────────────────────────
        # These appear AFTER the base consonant in Shri Lipi but Unicode
        # requires reph (ર્) BEFORE the consonant.
        reph_char = None
        if i + 1 < length:
            nxt = chars[i + 1]
            if nxt in ('®', '£', '}'):
                reph_char = nxt
                result.append('ર્')   # emit reph first

        # ── 3. Resolve current consonant / glyph ─────────────────────────
        matched_val = None
        consumed = 1

        # Try 2-char composite (only when no reph look-ahead consumed next)
        if i + 1 < length and reph_char is None:
            two = chars[i] + chars[i + 1]
            for k, v in COMPOSITE_MAPPINGS:
                if two == k:
                    matched_val = v
                    consumed = 2
                    break

        # Fallback: single-char lookup
        if matched_val is None:
            matched_val = SHRI_LIPI_TO_UNICODE.get(chars[i], chars[i])
            consumed = 1

        result.append(matched_val)

        # ── 4. Post-emit matras ───────────────────────────────────────────
        if is_pre_matra:
            result.append('િ')   # i-matra after consonant

        if reph_char == '£':
            result.append('ે')   # e-matra for £ (reph + e)
        elif reph_char == '}':
            result.append('ી')   # I-matra for } (reph + I)

        # ── 5. Advance cursor ─────────────────────────────────────────────
        i += consumed
        if reph_char is not None:
            i += 1  # skip the reph char we peeked at

    return cleanup_unicode_gujarati(''.join(result))


if __name__ == '__main__':
    # Quick self-test on known phrases from the PDF
    tests = [
        ('Ad¡', 'અME'),   # ame (we)
        ('A¡V$gy„', 'etaluM'),  # should start with e not A-e
        ("Ap‘Z¡", "AapaNe"),   # us/our (આ’પણે)
        ('kÐk„N', 'satsang'),
    ]
    for raw, expected_hint in tests:
        out = convert_shri_lipi_to_unicode(raw)
        print(f'{repr(raw):20s} → {out!r:30s}  (hint: {expected_hint})')
