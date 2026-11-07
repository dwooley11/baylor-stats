"""Parse Warren Nolan's Ranking Comparison page (POM = KenPom) and match ESPN team names to it."""
import re, html as H, difflib

ALIAS = {"st. john's": "saint john's", "saint mary's": "saint mary's college", "nc state": "north carolina state",
         "miami": "miami (fl)", "ole miss": "mississippi", "uconn": "connecticut", "app state": "appalachian state",
         "ut martin": "tennessee-martin", "utrgv": "texas rio grande valley", "uic": "illinois-chicago",
         "umass": "massachusetts", "unlv": "nevada-las vegas", "texas a&m-cc": "texas a&m-corpus christi",
         "texas a&m-corpus christi": "texas a&m-corpus christi", "queens university": "queens", "hawai'i": "hawaii",
         "san josé state": "san jose state", "louisiana": "louisiana-lafayette", "ul monroe": "louisiana-monroe",
         "southeast missouri state": "southeast missouri state", "se louisiana": "southeastern louisiana",
         "sam houston": "sam houston state", "grambling": "grambling state", "omaha": "nebraska-omaha",
         "pitt": "pittsburgh", "ucsb": "uc santa barbara", "fau": "florida atlantic", "fiu": "florida international",
         "cal state northridge": "csun", "umkc": "kansas city", "kansas city": "kansas city", "liu": "long island",
         "iupui": "iu indianapolis", "prairie view a&m": "prairie view a&m", "mcneese": "mcneese",
         "nicholls": "nicholls", "stephen f. austin": "stephen f. austin", "texas a&m-commerce": "east texas a&m",
         "east texas a&m": "east texas a&m", "central arkansas": "central arkansas", "utah tech": "utah tech",
         "incarnate word": "incarnate word", "houston christian": "houston christian", "ualbany": "albany"}


def load_wn(path):
    """Return {team name: KenPom rank} from a saved compare-rankings page, or {} if it has no POM column."""
    page = open(path, errors="ignore").read()
    out, cols = {}, None
    for r in re.findall(r"(?s)<tr[^>]*>(.*?)</tr>", page):
        c = [re.sub(r"\s+", " ", H.unescape(re.sub("<[^>]+>", "", x))).strip()
             for x in re.findall(r"(?s)<t[hd][^>]*>(.*?)</t[hd]>", r)]
        if c and c[0] == "Team":
            cols = c; continue
        if cols and "POM" in cols and len(c) == len(cols) and c[cols.index("POM")].isdigit():
            out[c[0]] = int(c[cols.index("POM")])
    return out


def norm(s):
    s = s.lower().replace("’", "'").strip()
    return ALIAS.get(s, s)


def matcher(wn):
    wn_norm = {norm(k): k for k in wn}
    def match(espn_loc):
        n = norm(espn_loc)
        for cand in (n, n.replace("st.", "saint"), n.replace("st.", "state"), n.replace(" ", "-"), n.replace("-", " ")):
            if cand in wn_norm:
                return wn_norm[cand]
        best = difflib.get_close_matches(n, list(wn_norm), n=1, cutoff=0.88)
        return wn_norm[best[0]] if best else None
    return match
