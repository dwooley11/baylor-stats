"""Build Baylor football data for the site.

  data/cfb.json            index: every season since 2019 with each game's opponent, site, score, status
  data/cfb/<id>.json       one compact file per game: header, quarter scores, team stats, box score categories,
                           drives, and every play (raw ESPN fields; the page classifies them)

Source: ESPN public site API. Past seasons are cached in .cache/cfb and only re-downloaded if missing;
the current season is always refreshed.

    python3 scripts/build_cfb.py
"""
import json, os, subprocess

API = "https://site.api.espn.com/apis/site/v2/sports/football/college-football"
BAY = "239"
FIRST = 2019
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(os.environ.get("BAYLOR_CACHE") or os.path.join(ROOT, ".cache"), "cfb")
DATA = os.path.join(ROOT, "data")
GAMES = os.path.join(DATA, "cfb")
for d in (CACHE, GAMES):
    os.makedirs(d, exist_ok=True)
SKIP_TYPES = {"Timeout", "End Period", "End of Half", "End of Game", "End of Regulation"}


def fetch(url, path, fresh=False):
    if fresh or not os.path.exists(path) or os.path.getsize(path) < 50:
        subprocess.run(["curl", "-sL", "-m", "40", "-o", path, url])
    try:
        return json.load(open(path))
    except Exception:
        return None


def compact(s):
    """Raw ESPN football summary -> compact game file (the page builds the same shape from a live summary)."""
    comp = s["header"]["competitions"][0]
    st = comp.get("status", {}).get("type", {})
    teams = []
    for c in comp["competitors"]:
        bt = next((t for t in s.get("boxscore", {}).get("teams", []) if t["team"]["id"] == c["team"]["id"]), {})
        teams.append({"id": c["team"]["id"], "abbr": c["team"].get("abbreviation"), "name": c["team"].get("displayName"),
                      "loc": c["team"].get("location"), "short": c["team"].get("shortDisplayName"), "color": c["team"].get("color"),
                      "homeAway": c["homeAway"], "score": c.get("score"),
                      "lines": [l.get("displayValue") for l in c.get("linescores", [])],
                      "stats": {x["name"]: x["displayValue"] for x in bt.get("statistics", [])}})
    box = {}
    for p in s.get("boxscore", {}).get("players", []):
        box[p["team"]["id"]] = {c["name"]: {"keys": c.get("keys", []), "athletes": [
            [a["athlete"].get("displayName"), a["athlete"].get("jersey") or "", a["athlete"].get("id") or "", a.get("stats") or []]
            for a in c.get("athletes", [])]} for c in p.get("statistics", [])}
    drives, plays = [], []
    for i, dr in enumerate((s.get("drives") or {}).get("previous", []) + ([s["drives"]["current"]] if (s.get("drives") or {}).get("current") else [])):
        tid = (dr.get("team") or {}).get("id")
        a0, b0 = dr.get("start") or {}, dr.get("end") or {}
        drives.append({"team": tid, "result": dr.get("result") or dr.get("displayResult"), "label": dr.get("displayResult"), "isScore": bool(dr.get("isScore")),
                       "start": a0.get("yardLine"), "plays": dr.get("offensivePlays"), "yds": dr.get("yards"),
                       "t0": [(a0.get("period") or {}).get("number"), (a0.get("clock") or {}).get("displayValue")],
                       "t1": [(b0.get("period") or {}).get("number"), (b0.get("clock") or {}).get("displayValue")]})
        for p in dr.get("plays", []):
            typ = p["type"]["text"]
            if typ in SKIP_TYPES:
                continue
            a, b = p.get("start") or {}, p.get("end") or {}
            plays.append([i, tid, p["period"]["number"], p["clock"]["displayValue"], typ, p.get("text", ""),
                          a.get("down"), a.get("distance"), a.get("yardsToEndzone"), b.get("yardsToEndzone"),
                          p.get("statYardage", 0), 1 if p.get("scoringPlay") else 0, p.get("homeScore"), p.get("awayScore"),
                          1 if p.get("isPenalty") else 0, 1 if p.get("isTurnover") else 0])
    return {"date": comp["date"], "neutral": comp.get("neutralSite", False), "conf": bool(comp.get("conferenceCompetition")),
            "state": st.get("state"), "status": st.get("shortDetail") or st.get("detail"), "completed": bool(st.get("completed")),
            "teams": teams, "box": box, "drives": drives, "plays": plays}


cur = fetch(f"{API}/teams/{BAY}/schedule", f"{CACHE}/sched_current.json", fresh=True)
CUR = cur["season"]["year"]
seasons = []
for y in range(FIRST, CUR + 1):
    fresh = y == CUR
    games = []
    for st in (2, 3):
        sch = fetch(f"{API}/teams/{BAY}/schedule?season={y}&seasontype={st}", f"{CACHE}/sched_{y}_{st}.json", fresh) or {}
        for e in sch.get("events", []):
            c = e["competitions"][0]
            opp = next(t for t in c["competitors"] if t["team"]["id"] != BAY)
            bay = next(t for t in c["competitors"] if t["team"]["id"] == BAY)
            stt = c["status"]["type"]
            sc = lambda t: (t.get("score") or {}).get("value") if isinstance(t.get("score"), dict) else t.get("score")
            g = {"id": e["id"], "date": e["date"], "opp": opp["team"].get("location") or opp["team"].get("displayName"),
                 "oppName": opp["team"].get("displayName"), "oppAbbr": opp["team"].get("abbreviation"), "oppId": opp["team"]["id"],
                 "site": "N" if c.get("neutralSite") else ("H" if bay["homeAway"] == "home" else "A"),
                 "post": st == 3, "completed": bool(stt.get("completed")), "state": stt.get("state")}
            if g["completed"] or g["state"] == "in":
                s = fetch(f"{API}/summary?event={e['id']}", f"{CACHE}/sum_{e['id']}.json", fresh=fresh and not os.path.exists(f"{GAMES}/{e['id']}.json") or g["state"] == "in")
                try:
                    cg = compact(s)
                    bt = next(t for t in cg["teams"] if t["id"] == BAY); ot = next(t for t in cg["teams"] if t["id"] != BAY)
                    g.update({"pf": int(bt["score"] or 0), "pa": int(ot["score"] or 0), "conf": cg["conf"], "hasCard": bool(cg["plays"])})
                    out = f"{GAMES}/{e['id']}.json"
                    txt = json.dumps(cg, separators=(",", ":"))
                    if not os.path.exists(out) or open(out).read() != txt:
                        open(out, "w").write(txt)
                except Exception as ex:
                    print("  could not read", e["id"], ex)
            games.append(g)
    games.sort(key=lambda g: g["date"])
    seasons.append({"year": y, "label": str(y), "games": games})
    done = [g for g in games if g["completed"] and "pf" in g]
    w = sum(g["pf"] > g["pa"] for g in done)
    print(y, f"{w}-{len(done) - w}", len(done), "games")

index = {"season": str(CUR), "seasonYear": CUR, "seasons": seasons}
OUT = os.path.join(DATA, "cfb.json")
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
print(OUT, os.path.getsize(OUT), "bytes;", len(os.listdir(GAMES)), "game files")
