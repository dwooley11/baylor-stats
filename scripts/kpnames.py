"""Map KenPom-style team names (e.g. "Iowa St.", "Miami FL") onto Warren Nolan's names, so the existing
ESPN -> Warren Nolan matcher works for either source."""
import re, difflib

# KenPom name (lowercase) -> Warren Nolan name (lowercase), where the simple rules below don't get there
FIX = {"mississippi": "ole miss", "unc wilmington": "uncw", "cal baptist": "california baptist", "illinois chicago": "uic",
       "seattle": "seattle university", "florida atlantic": "fau", "ut rio grande valley": "utrgv", "ut arlington": "uta",
       "csun": "cal state northridge", "massachusetts": "umass", "detroit mercy": "detroit", "florida gulf coast": "fgcu",
       "nebraska omaha": "omaha", "presbyterian": "presbyterian college", "unc greensboro": "uncg",
       "usc upstate": "south carolina upstate", "loyola md": "loyola-maryland", "louisiana monroe": "ulm", "kansas city": "umkc",
       "miami fl": "miami (fl)", "miami oh": "miami (oh)", "texas a&m corpus chris": "texas a&m-corpus christi",
       "liu": "long island", "iu indy": "iu indianapolis", "n.c. state": "north carolina state", "st. john's": "saint john's",
       "saint mary's": "saint mary's college", "arkansas pine bluff": "arkansas-pine bluff", "tennessee martin": "tennessee-martin",
       "gardner webb": "gardner-webb", "bethune cookman": "bethune-cookman"}


def to_wn(kp, wn_names):
    """kp: {kenpom name: rank}; wn_names: Warren Nolan team names. Returns ({wn name: rank}, [unmatched kenpom names])."""
    low = {n.lower(): n for n in wn_names}
    out, miss = {}, []
    for name, rk in kp.items():
        n = name.lower().strip()
        st = re.sub(r"\bst\.$", "state", n)
        cands = [FIX.get(n, n), n, st, re.sub(r"\bst\. ", "state ", st), re.sub(r"^st\. ", "saint ", n), st.replace(" ", "-")]
        hit = next((low[c] for c in cands if c in low), None)
        if not hit:
            best = difflib.get_close_matches(st, list(low), n=1, cutoff=0.85)
            hit = low[best[0]] if best else None
        if hit and hit not in out:
            out[hit] = rk
        else:
            miss.append(name)
    return out, miss
