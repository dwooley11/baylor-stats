"""Build all Baylor men's basketball data for the site.

  data/mbb.json            index: every season since 2019-20, every game's team totals + opponent KenPom rank,
                           prior-season team stats (for "tonight vs. usual"), current-season KenPom ranks
  data/games/<id>.json     one compact file per game (box score, scoring + shots + TV timeouts) for the game card

Sources: ESPN public site API; KenPom ranks via Warren Nolan's Ranking Comparison page (POM column).
Past seasons are cached in .cache/ and only re-downloaded if missing; the current season is always refreshed.

    python3 scripts/build_mbb.py
"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wnmatch import load_wn, matcher

API = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
BAY = "239"
FIRST = 2020                                   # ESPN season year; 2020 = 2019-20 (game cards)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(os.environ.get("BAYLOR_CACHE") or os.path.join(ROOT, ".cache"), "mbb")
DATA = os.path.join(ROOT, "data")
GAMES = os.path.join(DATA, "games")
for d in (CACHE, GAMES):
    os.makedirs(d, exist_ok=True)
STAT_KEYS = ("points", "fieldGoalsMade", "fieldGoalsAttempted", "threePointFieldGoalsMade", "freeThrowsAttempted",
             "offensiveRebounds", "turnovers", "gamesPlayed")


def fetch(url, path, fresh=False, ua=False):
    if fresh or not os.path.exists(path) or os.path.getsize(path) < 50:
        subprocess.run(["curl", "-sL", "-m", "40"] + (["-A", "Mozilla/5.0"] if ua else []) + ["-o", path, url])
    try:
        return json.load(open(path)) if path.endswith(".json") else open(path, errors="ignore").read()
    except Exception:
        return None


def team_stats(tid, year, fresh):
    d = fetch(f"{API}/teams/{tid}/statistics?season={year}", f"{CACHE}/stats_{tid}_{year}.json", fresh)
    try:
        allv = {s["name"]: s.get("value") for c in d["results"]["stats"]["categories"] for s in c["stats"]}
        return {k: allv.get(k) for k in STAT_KEYS} if allv.get("fieldGoalsAttempted") else None
    except (KeyError, TypeError):
        return None


def totals(team):
    m = {s["name"]: s["displayValue"] for s in team.get("statistics", [])}
    sp = lambda k: [int(x or 0) for x in m.get(k, "0-0").split("-")]
    fgm, fga = sp("fieldGoalsMade-fieldGoalsAttempted"); tpm, tpa = sp("threePointFieldGoalsMade-threePointFieldGoalsAttempted")
    ftm, fta = sp("freeThrowsMade-freeThrowsAttempted")
    n = lambda k: int(m.get(k) or 0)
    return dict(fgm=fgm, fga=fga, tpm=tpm, tpa=tpa, ftm=ftm, fta=fta, orb=n("offensiveRebounds"), drb=n("defensiveRebounds"),
                to=int(m.get("totalTurnovers") or m.get("turnovers") or 0), stl=n("steals"))


def compact(s):
    """Raw ESPN summary -> compact game file (same shape the page builds from a live ESPN summary)."""
    comp = s["header"]["competitions"][0]
    teams = []
    for c in comp["competitors"]:
        bt = next((t for t in s["boxscore"]["teams"] if t["team"]["id"] == c["team"]["id"]), {})
        teams.append({"id": c["team"]["id"], "abbr": c["team"].get("abbreviation"), "name": c["team"].get("displayName"),
                      "loc": c["team"].get("location"), "color": c["team"].get("color"), "homeAway": c["homeAway"],
                      "score": c.get("score"), "stats": {x["name"]: x["displayValue"] for x in bt.get("statistics", [])}})
    players = {}
    for p in s["boxscore"].get("players", []):
        st = (p.get("statistics") or [{}])[0]
        players[p["team"]["id"]] = {"keys": st.get("keys", []), "athletes": [
            [a["athlete"].get("displayName") or a["athlete"].get("shortName") or "—", (a["athlete"].get("position") or {}).get("abbreviation", ""), bool(a.get("starter")), a.get("stats") or [],
             a["athlete"].get("jersey") or "", a["athlete"].get("id") or ""]
            for a in st.get("athletes", [])]}
    plays = []
    for p in s.get("plays", []):
        typ = p["type"]["text"]
        tv = bool(re.search("TVTime", typ, re.I))
        shot = bool(p.get("shootingPlay"))
        if not (tv or shot or p.get("scoringPlay")):
            continue
        ft = bool(re.search("FreeThrow", typ, re.I))
        co = p.get("coordinate") or {}
        plays.append([p["period"]["number"], p["clock"]["displayValue"], (p.get("team") or {}).get("id"),
                      p.get("homeScore"), p.get("awayScore"), "T" if tv else ("F" if ft else "S"),
                      p.get("scoreValue", 0) if p.get("scoringPlay") else 0,
                      co.get("x"), co.get("y"), 1 if p.get("scoringPlay") else 0,
                      3 if (p.get("pointsAttempted") == 3 or p.get("scoreValue") == 3) else 0])
    return {"date": comp["date"], "neutral": comp.get("neutralSite", False), "conf": bool(comp.get("conferenceCompetition")), "teams": teams, "players": players, "plays": plays}


# ---- current season id from ESPN ----
cur_sched = fetch(f"{API}/teams/{BAY}/schedule", f"{CACHE}/sched_current.json", fresh=True)
CUR = cur_sched["season"]["year"]

seasons, stats, cur_kenpom, stale = [], {}, {}, False
for y in range(FIRST, CUR + 1):
    fresh = y == CUR
    wn_html = fetch(f"https://www.warrennolan.com/basketball/{y}/compare-rankings", f"{CACHE}/wn_{y}.html", fresh, ua=True)
    wn = load_wn(f"{CACHE}/wn_{y}.html") if wn_html else {}
    if y == CUR and wn:
        prev = load_wn(f"{CACHE}/wn_{y-1}.html")
        same = sum(1 for k, v in wn.items() if prev.get(k) == v)
        stale = same / len(wn) > 0.95
    match = matcher(wn)
    stats.setdefault(str(y - 1), {})
    stats[str(y - 1)][BAY] = team_stats(BAY, y - 1, False)
    games, nodi = [], set()
    for st in (2, 3):
        sch = fetch(f"{API}/teams/{BAY}/schedule?season={y}&seasontype={st}", f"{CACHE}/sched_{y}_{st}.json", fresh)
        for e in (sch or {}).get("events", []):
            c = e["competitions"][0]
            opp = next(t for t in c["competitors"] if t["team"]["id"] != BAY)
            bay = next(t for t in c["competitors"] if t["team"]["id"] == BAY)
            name = match(opp["team"]["location"]) if wn else None
            rank = wn.get(name) if name else None
            if y == CUR:
                cur_kenpom[opp["team"]["id"]] = rank
            g = {"id": e["id"], "date": e["date"], "opp": opp["team"]["location"], "oppName": opp["team"]["displayName"],
                 "oppAbbr": opp["team"]["abbreviation"], "oppId": opp["team"]["id"],
                 "site": "N" if c.get("neutralSite") else ("H" if bay["homeAway"] == "home" else "A"),
                 "post": st == 3, "rank": rank, "completed": c["status"]["type"]["completed"]}
            if g["completed"]:
                s = fetch(f"{API}/summary?event={e['id']}", f"{CACHE}/sum_{e['id']}.json", fresh=False)
                try:
                    bt = next(t for t in s["boxscore"]["teams"] if t["team"]["id"] == BAY)
                    ot = next(t for t in s["boxscore"]["teams"] if t["team"]["id"] != BAY)
                    if not bt.get("statistics"):
                        raise ValueError
                except Exception:
                    g["completed"] = False; games.append(g); continue
                comp = s["header"]["competitions"][0]
                g["bay"], g["o"] = totals(bt), totals(ot)
                g["bay"]["pts"] = int(next(x for x in comp["competitors"] if x["team"]["id"] == BAY)["score"])
                g["o"]["pts"] = int(next(x for x in comp["competitors"] if x["team"]["id"] != BAY)["score"])
                g["hasCard"] = True
                g["conf"] = bool(comp.get("conferenceCompetition"))
                out = f"{GAMES}/{e['id']}.json"
                txt = json.dumps(compact(s), separators=(",", ":"))
                if not os.path.exists(out) or open(out).read() != txt:
                    open(out, "w").write(txt)
                stats[str(y - 1)].setdefault(g["oppId"], team_stats(g["oppId"], y - 1, False))
                if wn and rank is None:
                    nodi.add(g["opp"])
            games.append(g)
    games.sort(key=lambda g: g["date"])
    # Baylor roster (bio) + season totals per player, from the box scores
    ros = fetch(f"{API}/teams/{BAY}/roster" + ("" if fresh else f"?season={y}"), f"{CACHE}/roster_{y}.json", fresh) or {}
    roster = {}
    for a in ros.get("athletes", []):
        bp = (a.get("birthPlace") or {})
        roster[a["id"]] = {"name": a.get("displayName"), "jersey": a.get("jersey"), "pos": (a.get("position") or {}).get("abbreviation"),
                           "ht": a.get("displayHeight"), "wt": a.get("displayWeight"), "cls": (a.get("experience") or {}).get("displayValue"),
                           "home": bp.get("displayText") or ", ".join(x for x in (bp.get("city"), bp.get("state") or bp.get("country")) if x)}
    tot = {}
    SUMK = ("minutes", "points", "rebounds", "assists", "steals", "blocks", "turnovers", "offensiveRebounds", "fouls")
    for g in games:
        if not g.get("hasCard"):
            continue
        gm = json.load(open(f"{GAMES}/{g['id']}.json"))
        pl = gm["players"].get(BAY)
        if not pl:
            continue
        ix = {k: i for i, k in enumerate(pl["keys"])}
        for a in pl["athletes"]:
            name, pos, starter, st, jersey, aid = (a + ["", ""])[:6]
            if not st or not aid:
                continue
            t = tot.setdefault(aid, {"name": name, "jersey": jersey, "pos": pos, "gp": 0, "gs": 0, "fgm": 0, "fga": 0, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0, **{k: 0 for k in SUMK}})
            t["gp"] += 1; t["gs"] += 1 if starter else 0
            for k in SUMK:
                try: t[k] += int(st[ix[k]])
                except (KeyError, ValueError, IndexError): pass
            for k, (m_, a_) in (("fieldGoalsMade-fieldGoalsAttempted", ("fgm", "fga")), ("threePointFieldGoalsMade-threePointFieldGoalsAttempted", ("tpm", "tpa")), ("freeThrowsMade-freeThrowsAttempted", ("ftm", "fta"))):
                try:
                    mk, at = st[ix[k]].split("-"); t[m_] += int(mk); t[a_] += int(at)
                except (KeyError, ValueError, IndexError): pass
    for aid, t in tot.items():
        t.update({k: v for k, v in (roster.get(aid) or {}).items() if v})
    players = tot
    seasons.append({"year": y, "label": f"{y-1}-{str(y)[2:]}", "hasRanks": bool(wn), "games": games, "players": players})
    print(seasons[-1]["label"], sum(g["completed"] for g in games), "games; no KenPom:", sorted(nodi) or "-")

cur_kenpom[BAY] = load_wn(f"{CACHE}/wn_{CUR}.html").get("Baylor")
r247 = os.path.join(DATA, "mbb-247.json")
recruit = json.load(open(r247)) if os.path.exists(r247) else None
index = {"recruit": recruit, "season": cur_sched["season"]["displayName"], "seasonYear": CUR, "seasons": seasons, "stats": stats,
         "kenpom": cur_kenpom, "kenpomStale": stale}
OUT = os.path.join(DATA, "mbb.json")
# keep old timestamps when nothing changed, so the scheduled job only commits real updates
now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
index["pulled"] = now
if os.path.exists(OUT):
    try:
        old = json.load(open(OUT))
        if {k: v for k, v in old.items() if k != "pulled"} == json.loads(json.dumps({k: v for k, v in index.items() if k != "pulled"})):
            index["pulled"] = old["pulled"]
    except Exception:
        pass
json.dump(index, open(OUT, "w"), separators=(",", ":"))
print(OUT, os.path.getsize(OUT), "bytes;", len(os.listdir(GAMES)), "game files;",
      "KenPom this season:", "last season's (Warren Nolan not updated yet)" if stale else "current")
