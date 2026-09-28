#!/usr/bin/env python3
"""SruSan's Sketchbook: builds the animated, hand-drawn SVGs for this GitHub profile from live GitHub data.

  GITHUB_TOKEN=... python scripts/build.py            # fetch data, write assets/sketchbook/*.svg
  python scripts/build.py --data cache.json           # offline: reuse cached data
  python scripts/build.py --save cache.json           # fetch and keep a cache

Standard library only. Text lives in profile.json; fonts (SIL OFL) are embedded from fonts/.
"""
import argparse
import base64
import datetime as dt
import hashlib
import html
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "sketchbook")
W = 850
PAPER, INK, MUTED = "#fff8e7", "#1f2937", "#6b7280"
PURPLE, AMBER, BLUE, RED, GREEN = "#7c3aed", "#f59e0b", "#2563eb", "#ef4444", "#15803d"
NOTE = ["#fde68a", "#bfdbfe", "#fecaca", "#bbf7d0", "#e9d5ff", "#fed7aa"]


# ---------------------------------------------------------------- data

def gql(query, token):
    req = urllib.request.Request("https://api.github.com/graphql", json.dumps({"query": query}).encode(),
                                 {"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if "errors" in out:
        raise SystemExit(f"GraphQL error: {out['errors']}")
    return out["data"]


def fetch(login, token):
    base = gql(f"""{{ user(login: "{login}") {{
      name createdAt followers {{ totalCount }}
      pullRequests {{ totalCount }} issues {{ totalCount }}
      repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100, orderBy: {{field: PUSHED_AT, direction: DESC}}) {{
        totalCount nodes {{ name description stargazerCount url pushedAt primaryLanguage {{ name color }}
          languages(first: 10, orderBy: {{field: SIZE, direction: DESC}}) {{ edges {{ size node {{ name color }} }} }} }} }}
      contributionsCollection {{ contributionYears totalCommitContributions
        contributionCalendar {{ totalContributions weeks {{ contributionDays {{ date contributionCount }} }} }} }} }} }}""", token)["user"]
    days = {}
    for y in base["contributionsCollection"]["contributionYears"]:
        c = gql(f"""{{ user(login: "{login}") {{ contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") {{
          contributionCalendar {{ weeks {{ contributionDays {{ date contributionCount }} }} }} }} }} }}""", token)
        for wk in c["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in wk["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
    base["all_days"] = days
    return base


def summarize(d, cfg):
    days = sorted(d["all_days"].items())
    today = dt.date.today().isoformat()
    days = [(k, v) for k, v in days if k <= today]
    total = sum(v for _, v in days)
    longest = run = 0
    for _, v in days:
        run = run + 1 if v > 0 else 0
        longest = max(longest, run)
    cur = 0
    for i, (k, v) in enumerate(reversed(days)):
        if v > 0:
            cur += 1
        elif i == 0:
            continue          # today may not have contributions yet
        else:
            break
    repos = [r for r in d["repositories"]["nodes"] if r["name"].lower() != cfg["login"].lower()]
    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, [0, e["node"]["color"] or "#9ca3af"])[0] += e["size"]
    tot_all = sum(v[0] for v in langs.values()) or 1
    top = [kv for kv in sorted(langs.items(), key=lambda x: -x[1][0]) if kv[1][0] / tot_all >= 0.01][:6]
    tot = tot_all
    cal = d["contributionsCollection"]["contributionCalendar"]
    by = {r["name"].lower(): r for r in repos}
    feat = []
    for f in cfg.get("featured", []):
        r = by.get(f["repo"].lower())
        if r:
            feat.append({**r, "blurb": f.get("blurb") or r.get("description") or ""})
    for r in sorted(repos, key=lambda r: (-r["stargazerCount"], r["pushedAt"]), reverse=False):
        if len(feat) >= 3:
            break
        if all(r["name"] != x["name"] for x in feat):
            feat.append({**r, "blurb": r.get("description") or ""})
    return {"total": total, "streak": cur, "longest": longest,
            "stars": sum(r["stargazerCount"] for r in repos), "repos": d["repositories"]["totalCount"],
            "prs": d["pullRequests"]["totalCount"], "issues": d["issues"]["totalCount"],
            "followers": d["followers"]["totalCount"], "commits_year": d["contributionsCollection"]["totalCommitContributions"],
            "since": d["createdAt"][:4],
            "langs": [(n, v[0] / tot, v[1]) for n, (v) in top],
            "weeks": [[c["contributionCount"] for c in w["contributionDays"]] for w in cal["weeks"]],
            "year_total": cal["totalContributions"], "featured": feat[:3],
            "recent": [r["name"] for r in sorted(repos, key=lambda r: r["pushedAt"], reverse=True)],
            "recent_info": [{"name": r["name"], "lang": (r.get("primaryLanguage") or {}).get("name") or "code", "stars": r["stargazerCount"]}
                            for r in sorted(repos, key=lambda r: r["pushedAt"], reverse=True)]}


# ---------------------------------------------------------------- drawing helpers

def wrap(text, width):
    lines, cur = [], ""
    for wd in text.split():
        if cur and len(cur) + 1 + len(wd) > width:
            lines.append(cur); cur = wd
        else:
            cur = (cur + " " + wd).strip()
    return lines + ([cur] if cur else [])


def font_css(sign=False):
    def face(name, file):
        b64 = base64.b64encode(open(os.path.join(ROOT, "fonts", file), "rb").read()).decode()
        return f"@font-face{{font-family:'{name}';src:url(data:font/woff2;base64,{b64}) format('woff2');}}"
    return face("Hand", "hand.woff2") + (face("Sign", "sign.woff2") if sign else "")


BASE_CSS = """
text{font-family:'Hand','Patrick Hand','Comic Sans MS',cursive;fill:%s}
.sign{font-family:'Sign','Caveat','Bradley Hand',cursive;font-weight:700}
@keyframes pop{from{opacity:0;transform:translateY(10px) scale(.96)}}
@keyframes draw{from{stroke-dashoffset:100}}
@keyframes sway{0%%,100%%{transform:rotate(var(--r,0deg))}50%%{transform:rotate(calc(var(--r,0deg) * -1))}}
@keyframes twinkle{0%%,100%%{transform:scale(.6);opacity:.5}50%%{transform:scale(1.15);opacity:1}}
.pop{animation:pop .6s ease-out both;transform-box:fill-box;transform-origin:center}
.tw{transform-box:fill-box;transform-origin:center;animation:twinkle 2.4s ease-in-out infinite}
@media (prefers-reduced-motion: reduce){*{animation:none!important}}
""" % INK

DEFS = """<defs>
<filter id="wob" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="4" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="3"/></filter>
<pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.3" fill="#e7dcc3"/></pattern>
</defs>"""


def doc(h, body, css="", sign=False, title=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" role="img" aria-label="{html.escape(title)}">'
            f'<title>{html.escape(title)}</title><style>{font_css(sign)}{BASE_CSS}{css}</style>{DEFS}'
            f'<rect x="3" y="3" width="{W - 6}" height="{h - 6}" rx="20" fill="{PAPER}"/><rect x="3" y="3" width="{W - 6}" height="{h - 6}" rx="20" fill="url(#dots)"/>'
            f'<rect x="6" y="6" width="{W - 12}" height="{h - 12}" rx="18" fill="none" stroke="{INK}" stroke-width="2.6" filter="url(#wob)"/>'
            f'{body}</svg>')


def t(x, y, s, size=20, fill=INK, anchor="start", cls="", extra=""):
    c = f' class="{cls}"' if cls else ""
    return f'<text x="{x}" y="{y}" font-size="{size}" style="fill:{fill}" text-anchor="{anchor}"{c} {extra}>{html.escape(str(s))}</text>'


def squiggle(x1, x2, y, color=AMBER, w=5, animate=True):
    pts, x, up = [f"M{x1} {y}"], x1, True
    while x < x2:
        pts.append(f"Q{x + 10} {y + (-6 if up else 6)} {x + 20} {y}"); x += 20; up = not up
    a = ' pathLength="100" style="stroke-dasharray:100;animation:draw 1.2s ease-out .6s both"' if animate else ""
    return f'<path d="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round"{a}/>'


def spark(x, y, r=8, color=AMBER, delay=0):
    return (f'<path class="tw" style="animation-delay:{delay}s" d="M{x} {y - r} Q{x} {y} {x + r} {y} Q{x} {y} {x} {y + r} '
            f'Q{x} {y} {x - r} {y} Q{x} {y} {x} {y - r} Z" fill="{color}" stroke="{INK}" stroke-width="1.3"/>')


def signature(x, y, size=34, rot=-7):
    return (f'<g transform="rotate({rot} {x} {y})"><text x="{x}" y="{y}" font-size="{size}" class="sign" text-anchor="middle" '
            f'style="fill:{PURPLE}">SruSan</text>'
            f'<path d="M{x - size * 1.4} {y + size * .3} Q{x} {y + size * .6} {x + size * 1.6} {y + size * .1}" fill="none" stroke="{PURPLE}" '
            f'stroke-width="2.4" stroke-linecap="round" pathLength="100" style="stroke-dasharray:100;animation:draw 1s ease-out 2.2s both"/></g>')


# ---------------------------------------------------------------- sections

def fontface(name, file):
    b64 = base64.b64encode(open(os.path.join(ROOT, "fonts", file), "rb").read()).decode()
    return f"@font-face{{font-family:'{name}';src:url(data:font/woff2;base64,{b64}) format('woff2');}}"


def logo_b64(kind):
    return base64.b64encode(open(os.path.join(ROOT, "assets", "brand", f"srusan-logo-{kind}.png"), "rb").read()).decode()


def credit(cfg, s):
    w, h = 330, 56
    body = (f'<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="28" fill="#050505" stroke="#3f3f46" stroke-width="2"/>'
            f'<image href="data:image/png;base64,{logo_b64("white")}" x="22" y="17" width="45" height="22"/>'
            f'<text x="82" y="27" font-size="13" class="mono" style="fill:#fafafa">custom-built by SruSan</text>'
            f'<text x="82" y="43" font-size="11" class="mono" style="fill:#a1a1aa;letter-spacing:1px">srusan.com · redrawn daily</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="custom-built by SruSan">'
            f'<title>custom-built by SruSan</title><style>{fontface("Mono", "mono.woff2")}.mono{{font-family:"Mono","Space Mono",monospace}}</style>{body}</svg>')


def invader(x, y, px=3, color="#a78bfa", frame=0):
    a = ["..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.", "XXXXXXXXXXX", "X.XXXXXXX.X", "X.X.....X.X", "...XX.XX..."]
    b = ["..X.....X..", "X..X...X..X", "X.XXXXXXX.X", "XXX.XXX.XXX", "XXXXXXXXXXX", ".XXXXXXXXX.", "..X.....X..", ".X.......X."]
    rows = a if frame == 0 else b
    return "".join(f'<rect x="{x + c * px}" y="{y + r * px}" width="{px}" height="{px}" fill="{color}"/>'
                   for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == "X")


def arcade_doc(w, h, body, css, title, scan=True, radius=18):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">'
            f'<title>{html.escape(title)}</title><style>{fontface("Mono", "mono.woff2")}{fontface("MonoB", "monob.woff2")}'
            f'{fontface("Pixel", "pixel.woff2")}'
            ".mono{font-family:'Mono','Space Mono',monospace}.monob{font-family:'MonoB','Space Mono',monospace;font-weight:700}"
            ".px{font-family:'Pixel','Press Start 2P',monospace}"
            "@keyframes twinkle{0%,100%{opacity:.25}50%{opacity:1}}.star{animation:twinkle 2.2s ease-in-out infinite}"
            f"{css}@media (prefers-reduced-motion: reduce){{*{{animation:none!important}}}}</style>"
            '<defs><pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#ffffff" opacity=".035"/></pattern>'
            '<radialGradient id="blob" cx="35%" cy="30%" r="80%"><stop offset="0" stop-color="#6b7280"/><stop offset=".35" stop-color="#1f2937"/>'
            '<stop offset="1" stop-color="#000"/></radialGradient>'
            '<radialGradient id="lens" cx="45%" cy="40%" r="70%"><stop offset="0" stop-color="#3f3f46"/><stop offset="1" stop-color="#050505"/></radialGradient>'
            '<linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#67e8f9"/><stop offset=".5" stop-color="#a78bfa"/><stop offset="1" stop-color="#f472b6"/></linearGradient>'
            '<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="22"/></filter>'
            '<radialGradient id="disc" cx="50%" cy="35%" r="75%"><stop offset="0" stop-color="#1c1c26"/><stop offset="1" stop-color="#07070b"/></radialGradient></defs>'
            + (f'<rect width="{w}" height="{h}" rx="{radius}" fill="#050505"/>{body}<rect width="{w}" height="{h}" rx="{radius}" fill="url(#scan)"/>'
             f'<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="{radius - 1}" fill="none" stroke="#27272a" stroke-width="3"/></svg>' if scan
             else f'{body}</svg>'))


def stars(w, h, n=30, seed=7, avoid=None):
    out = ""
    for k in range(n):
        sx, sy = (k * 97 + seed * 13) % (w - 40) + 20, (k * 53 + seed * 29) % (h - 40) + 20
        if avoid and any(x1 <= sx <= x2 and y1 <= sy <= y2 for x1, y1, x2, y2 in avoid):
            continue
        out += f'<rect class="star" style="animation-delay:{(k % 9) * .27:.2f}s" x="{sx}" y="{sy}" width="2" height="2" fill="#e5e7eb"/>'
    return out


def hero(cfg, s):
    w, h = W, 330
    lines = cfg["terminal"]
    shown, used = [], 2
    for r in s["recent"]:                      # repo names that fit left of the monogram
        if used + len(r) + 3 > 54:
            break
        shown.append(r); used += len(r) + 3
    specs = [(f"> {lines[0]}", 26, "#fafafa", "monob"), (f"> {lines[1]}", 18, "#4ade80", "mono"),
             ("> ls ~/projects", 18, "#a1a1aa", "mono"), (" · ".join(shown), 15, "#67e8f9", "mono")]
    css, body = [], stars(w, h, 34, avoid=[(30, 30, 580, 270), (520, 250, 830, 310)])
    body += f'<text x="44" y="56" font-size="15" class="mono" style="fill:#d4d4d8;letter-spacing:6px">{html.escape(cfg.get("site", "").upper())}</text>'
    t0, y = 0.4, 110
    for i, (txt, size, col, cls) in enumerate(specs):
        cw = size * 0.625
        n = len(txt)
        dur = max(0.6, n * 0.045)
        width = n * cw + 4
        vals = ";".join(f"{k * cw + (8 if k == n else 0):.1f}" for k in range(n + 1))
        body += (f'<clipPath id="c{i}"><rect x="40" y="{y - size}" width="0" height="{size * 1.5}">'
                 f'<animate attributeName="width" values="{vals}" calcMode="discrete" begin="{t0:.2f}s" dur="{dur:.2f}s" fill="freeze"/></rect></clipPath>'
                 f'<text x="44" y="{y}" font-size="{size}" class="{cls}" clip-path="url(#c{i})" style="fill:{col}">{html.escape(txt)}</text>')
        t0 += dur + 0.35
        y += 34 if i == 0 else 30 if i < 3 else 0
    css.append("@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}.cur{animation:blink 1s steps(1) infinite}")
    rot = [r for r in s["recent_info"] if r["name"] not in shown][:4] or s["recent_info"][:4]
    N, per = len(rot), 3.0
    for k, r in enumerate(rot):
        a, b = 100 * k / N, 100 * (k + 1) / N
        css.append(f"@keyframes pr{k}{{0%,{max(a - .01, 0):.2f}%{{opacity:0}}{a:.2f}%,{b - 1:.2f}%{{opacity:1}}{b:.2f}%,100%{{opacity:0}}}}"
                   f".pr{k}{{opacity:{1 if k == 0 else 0};animation:pr{k} {N * per:.0f}s linear {t0:.1f}s infinite}}")
        star = f" · ★{r['stars']}" if r["stars"] else ""
        line = f"> open {r['name']}" + (f" · {r['lang']}" if r["lang"] != "code" else "") + star
        body += f'<text class="pr{k} mono" x="44" y="{y + 34}" font-size="15" style="fill:#fde047">{html.escape(line)}</text>'
    body += f'<rect class="cur" x="44" y="{y + 48}" width="11" height="18" fill="#4ade80"/>'
    # SA logo in a glowing orb: drifting colour glow, gradient ring with a rotating arc, orbiting dot
    cx, cy = 690, 150
    spin = lambda d, rev=False: (f'<animateTransform attributeName="transform" type="rotate" from="{360 if rev else 0} {cx} {cy}" '
                                 f'to="{0 if rev else 360} {cx} {cy}" dur="{d}s" repeatCount="indefinite"/>')
    body += (f'<g opacity=".85">{spin(14)}<circle cx="{cx - 34}" cy="{cy - 20}" r="54" fill="#67e8f9" filter="url(#glow)"/>'
             f'<circle cx="{cx + 36}" cy="{cy + 22}" r="54" fill="#a78bfa" filter="url(#glow)"/><circle cx="{cx + 20}" cy="{cy - 40}" r="38" fill="#f472b6" filter="url(#glow)"/></g>'
             f'<circle cx="{cx}" cy="{cy}" r="96" fill="none" stroke="#3f3f46" stroke-width="1" stroke-dasharray="2 8"><animateTransform attributeName="transform" type="rotate" from="360 {cx} {cy}" to="0 {cx} {cy}" dur="40s" repeatCount="indefinite"/></circle>'
             f'<circle cx="{cx}" cy="{cy}" r="74" fill="url(#disc)"/>'
             f'<circle cx="{cx}" cy="{cy}" r="74" fill="none" stroke="url(#ring)" stroke-width="1.5" stroke-opacity=".45"/>'
             f'<circle cx="{cx}" cy="{cy}" r="74" fill="none" stroke="url(#ring)" stroke-width="3.5" stroke-linecap="round" '
             f'stroke-dasharray="120 345">{spin(6)}</circle>'
             f'<g>{spin(10, True)}<circle cx="{cx + 96}" cy="{cy}" r="4" fill="#67e8f9"/><circle cx="{cx + 96}" cy="{cy}" r="9" fill="#67e8f9" opacity=".25"/></g>'
             f'<image href="data:image/png;base64,{logo_b64("white")}" x="{cx - 52}" y="{cy - 26}" width="104" height="51"/>')
    for k, (ix, iy, col, d) in enumerate(((470, 34, "#a78bfa", 0), (520, 276, "#f472b6", .6))):
        css.append(f"@keyframes bob{k}{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-8px)}}}}.bob{k}{{animation:bob{k} 1.4s ease-in-out {d}s infinite}}")
        body += f'<g class="bob{k}">{invader(ix, iy, 2.6, col)}</g>'
    body += (f'<text x="{w - 44}" y="{h - 48}" font-size="21" class="mono" text-anchor="end" style="fill:#fafafa;letter-spacing:1px">_{html.escape(cfg["name"])}</text>'
             f'<text x="{w - 44}" y="{h - 26}" font-size="12" class="mono" text-anchor="end" style="fill:#a1a1aa;letter-spacing:2px">{html.escape(cfg["links"]["email"])}</text>')
    return arcade_doc(w, h, body, "".join(css), f"{cfg['name']}: " + "; ".join(lines))


def pixel_ship(x, y, px=3, color="#f472b6"):
    rows = ["....X....", "...XXX...", "...XXX...", ".XXXXXXX.", "XXXXXXXXX", "XX.XXX.XX", "X...X...X"]
    return "".join(f'<rect x="{x + c * px}" y="{y + r * px}" width="{px}" height="{px}" fill="{color}"/>'
                   for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == "X")


def calendar(cfg, s):
    # v2 look (navy cabinet, grid on top) + laser, sparks, tiles cleared until the wave restarts, live score
    weeks = s["weeks"][-52:]
    h = 270
    T = 18.0
    END = 94.0  # ship reaches the right edge here; the cleared board holds, then the wave respawns
    vals = sorted(v for w in weeks for v in w if v > 0)
    q = [vals[int(len(vals) * f)] if vals else 1 for f in (.25, .5, .75)]
    pal = ["#1b2447", "#166534", "#16a34a", "#22c55e", "#86efac"]
    lvl = lambda v: 0 if v == 0 else 1 if v <= q[0] else 2 if v <= q[1] else 3 if v <= q[2] else 4
    cell, gap, x0, y0 = 11.6, 3.1, 44, 78
    n = len(weeks)
    step = cell + gap
    ship_y = 208
    css = [f".ship{{animation:fly {T}s linear infinite}}@keyframes fly{{0%{{transform:translateX(0)}}{END}%,100%{{transform:translateX({(n - 1) * step:.1f}px)}}}}",
           ".star{animation:twinkle 1.8s ease-in-out infinite;transform-box:fill-box;transform-origin:center}",
           f"@keyframes clear{{0%,{END + 1}%{{opacity:0}}{END + 2}%,{END + 4}%{{opacity:1}}{END + 5}%,100%{{opacity:0}}}}.clear{{opacity:0;animation:clear {T}s linear infinite}}"]
    b = f'<rect x="10" y="10" width="{W - 20}" height="{h - 20}" rx="16" fill="#0b1026"/>'
    for k in range(26):
        sx, sy = (k * 97) % (W - 60) + 30, (k * 53) % (h - 60) + 24
        b += f'<rect class="star" style="animation-delay:{(k % 7) * .3:.1f}s" x="{sx}" y="{sy}" width="2" height="2" fill="#e0e7ff" opacity=".7"/>'
    b += (f'<text x="44" y="52" font-size="16" class="px" style="fill:#67e8f9">COMMIT INVADERS</text>'
          f'<text x="{W - 44}" y="52" font-size="12" class="px" text-anchor="end" style="fill:#fde047">HI-SCORE {s["year_total"]:05d}</text>')
    score, hits = 0, []
    for i, wk in enumerate(weeks):
        colx = x0 + i * step
        p = END * i / max(n - 1, 1)
        live = [v for v in wk if v > 0]
        if live:
            a, b2 = max(p - 0.3, 0), p + 0.8
            css.append(f"@keyframes lz{i}{{0%,{a:.2f}%{{opacity:0}}{a + .01:.2f}%,{b2:.2f}%{{opacity:1}}{b2 + .01:.2f}%,100%{{opacity:0}}}}"
                       f".lz{i}{{opacity:0;animation:lz{i} {T}s linear infinite}}"
                       f"@keyframes h{i}{{0%,{b2:.2f}%{{transform:scale(1);opacity:1}}{b2 + .5:.2f}%,98%{{transform:scale(0);opacity:0}}99.5%,100%{{transform:scale(1);opacity:1}}}}"
                       f".h{i}{{transform-box:fill-box;transform-origin:center;animation:h{i} {T}s linear infinite}}")
            for k2, (dx, dy) in enumerate(((-10, -10), (10, -10), (-10, 10), (10, 10))):
                css.append(f"@keyframes sp{i}_{k2}{{0%,{b2:.2f}%{{opacity:0;transform:translate(0,0)}}{b2 + .1:.2f}%{{opacity:1}}{b2 + 1.8:.2f}%{{opacity:0;transform:translate({dx}px,{dy}px)}}100%{{opacity:0}}}}"
                           f".sp{i}_{k2}{{opacity:0;animation:sp{i}_{k2} {T}s linear infinite}}")
            b += f'<rect class="lz{i}" x="{colx + cell / 2 - 1:.1f}" y="{y0:.1f}" width="2" height="{ship_y - y0:.1f}" fill="#fde047"/>'
            score += sum(live)
            hits.append((b2, score))
        for j, v in enumerate(wk):
            L = lvl(v)
            cls = f' class="h{i}"' if L else ""
            b += f'<rect{cls} x="{colx:.1f}" y="{y0 + j * step:.1f}" width="{cell}" height="{cell}" rx="2" fill="{pal[L]}"/>'
            if L:
                b += "".join(f'<rect class="sp{i}_{k2}" x="{colx + cell / 2 - 1.5:.1f}" y="{y0 + j * step + cell / 2 - 1.5:.1f}" width="3" height="3" fill="#fde047"/>' for k2 in range(4))
    b += f'<g class="ship">{pixel_ship(x0 + cell / 2 - 13.5, ship_y, 3)}</g>'
    b += f'<text class="clear px" x="{W / 2}" y="{y0 + 3.5 * step + 6}" font-size="14" text-anchor="middle" style="fill:#fde047">WAVE CLEARED</text>'
    # live score: one text per hit, shown from that hit until the next (resting frame = final score)
    marks = [(0.0, 0)] + hits
    for k, (start, val) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else None
        if end is None:
            css.append(f"@keyframes sc{k}{{0%,{start - .01:.2f}%{{opacity:0}}{start:.2f}%,98%{{opacity:1}}98.01%,100%{{opacity:0}}}}.sc{k}{{animation:sc{k} {T}s linear infinite}}")
        else:
            css.append(f"@keyframes sc{k}{{0%,{max(start - .01, 0):.2f}%{{opacity:0}}{start:.2f}%,{end - .01:.2f}%{{opacity:1}}{end:.2f}%,100%{{opacity:0}}}}.sc{k}{{opacity:0;animation:sc{k} {T}s linear infinite}}")
        b += f'<text class="sc{k} px" x="{W / 2}" y="{h - 16}" font-size="9" text-anchor="middle" style="fill:#fafafa">SCORE {val:05d}</text>'
    b += (f'<rect x="30" y="{h - 34}" width="{W - 60}" height="2" fill="#312e81"/>'
          f'<text x="44" y="{h - 16}" font-size="9" class="px" style="fill:#a5b4fc">1UP SRUSAN</text>'
          f'<text x="{W - 44}" y="{h - 16}" font-size="9" class="px" text-anchor="end" style="fill:#a5b4fc">{s["total"]} COMMITS SHOT DOWN SINCE {s["since"]}</text>')
    return arcade_doc(W, h, b, "".join(css), f"Commit Invaders: {s['year_total']} contributions in the last year")


# ---------------------------------------------------------------- dark arcade theme (every section matches the hero)

CY, GR, YE, VI, PK, FG, MU, PANEL, EDGE = "#67e8f9", "#4ade80", "#fde047", "#a78bfa", "#f472b6", "#fafafa", "#a1a1aa", "#0f0f15", "#27272a"


def head(title, color, caption=""):
    out = f'<text x="40" y="50" font-size="15" class="px" style="fill:{color}">{html.escape(title)}</text>'
    if caption:
        out += f'<text x="{W - 40}" y="50" font-size="12" class="mono" text-anchor="end" style="fill:{MU}">{html.escape(caption)}</text>'
    return out


def rise(i, base=.15, gap=.12):
    return f'class="rise" style="animation-delay:{base + i * gap:.2f}s"'


RISE = "@keyframes rise{from{opacity:0;transform:translateY(8px)}}.rise{animation:rise .7s cubic-bezier(.2,.8,.2,1) both}"


def now(cfg, s):
    h = 170
    items = list(cfg["now"].items())[:3]
    cols = [GR, CY, PK]
    b = head("RIGHT NOW", YE, "what I'm up to")
    cw, gap = 248, 13
    for i, (k, v) in enumerate(items):
        x = 40 + i * (cw + gap)
        b += (f'<g {rise(i)}><rect x="{x}" y="72" width="{cw}" height="74" rx="10" fill="{PANEL}" stroke="{EDGE}"/>'
              f'<rect x="{x}" y="72" width="4" height="74" rx="2" fill="{cols[i]}"/>'
              f'<text x="{x + 18}" y="96" font-size="12" class="mono" style="fill:{cols[i]}">$ {html.escape(k)}</text>'
              + "".join(f'<text x="{x + 18}" y="{118 + j * 18}" font-size="13" class="mono" style="fill:{FG}">{html.escape(ln)}</text>'
                        for j, ln in enumerate(wrap(v, 30)[:2])) + "</g>")
    return arcade_doc(W, h, b, RISE, "Right now: " + "; ".join(f"{k}: {v}" for k, v in items))


def pixel_flame(x, y, px=3):
    rows = ["...X...", "..XX...", "..XXX..", ".XXYXX.", ".XYYYX.", "XXYYYXX", ".XXXXX."]
    return "".join(f'<rect x="{x + c * px}" y="{y + r * px}" width="{px}" height="{px}" fill="{"#fb923c" if ch == "X" else YE}"/>'
                   for r, row in enumerate(rows) for c, ch in enumerate(row) if ch in "XY")


def stats(cfg, s):
    h = 250
    css = RISE + ".fl{transform-box:fill-box;transform-origin:50% 100%;animation:flick .5s steps(2) infinite alternate}@keyframes flick{to{transform:scaleY(.85)}}"
    b = head("PLAYER STATS", CY, f"since {s['since']} · updates daily")
    big = [("CONTRIBUTIONS", f"{s['total']:,}", "all time", GR), ("CURRENT STREAK", f"{s['streak']}", "days", "#fb923c"),
           ("LONGEST STREAK", f"{s['longest']}", "days", YE), ("STARS EARNED", f"{s['stars']}", "on public repos", VI)]
    cw, gap = 184, 10
    for i, (lab, val, sub, col) in enumerate(big):
        x = 40 + i * (cw + gap)
        b += (f'<g {rise(i)}><rect x="{x}" y="72" width="{cw}" height="112" rx="10" fill="{PANEL}" stroke="{EDGE}"/>'
              f'<text x="{x + 16}" y="96" font-size="8" class="px" style="fill:{MU}">{lab}</text>'
              f'<text x="{x + 16}" y="146" font-size="40" class="monob" style="fill:{col}">{val}</text>'
              f'<text x="{x + 16}" y="170" font-size="12" class="mono" style="fill:{MU}">{sub}</text>')
        if i == 1:
            b += f'<g class="fl">{pixel_flame(x + cw - 38, 84)}</g>'
        b += "</g>"
    small = [(f"{s['commits_year']:,}", "commits this year"), (f"{s['prs']}", "pull requests"), (f"{s['repos']}", "public repos"), (f"{s['followers']}", "followers")]
    for i, (val, lab) in enumerate(small):
        x = 40 + i * (cw + gap)
        b += (f'<g {rise(i, .7)}><text x="{x + 16}" y="218" font-size="18" class="monob" style="fill:{FG}">{val}</text>'
              f'<text x="{x + 24 + len(val) * 11}" y="218" font-size="12" class="mono" style="fill:{MU}">{lab}</text></g>')
    return arcade_doc(W, h, b, css, f"{s['total']} contributions, {s['streak']}-day streak, longest {s['longest']}, {s['stars']} stars")


def languages(cfg, s):
    langs = s["langs"]
    h = 100 + 34 * len(langs)
    seg, sgap, nseg = 10, 3, 40
    b = head("LANGUAGES", PK, "by code size, public repos")
    css = [RISE]
    mx = max(p for _, p, _ in langs) or 1
    for i, (n, p, col) in enumerate(langs):
        y = 76 + i * 34
        k = max(1, round(nseg * p / mx))
        b += f'<text x="40" y="{y + 13}" font-size="14" class="mono" style="fill:{FG}">{html.escape(n)}</text>'
        for j in range(nseg):
            on = j < k
            cls = f' class="s{i}_{j}"' if on else ""
            b += f'<rect{cls} x="{190 + j * (seg + sgap)}" y="{y}" width="{seg}" height="16" rx="2" fill="{col if on else "#18181f"}"/>'
            if on:
                css.append(f".s{i}_{j}{{animation:rise .25s ease-out {.2 + i * .12 + j * .02:.2f}s both}}")
        b += f'<text x="{W - 40}" y="{y + 13}" font-size="13" class="mono" text-anchor="end" style="fill:{MU}">{p * 100:.0f}%</text>'
    return arcade_doc(W, h, b, "".join(css), "Languages: " + ", ".join(f"{n} {p * 100:.0f}%" for n, p, _ in langs))


def project(cfg, r, i):
    w, h = 270, 150
    lang = (r.get("primaryLanguage") or {}).get("name") or "code"
    col = (r.get("primaryLanguage") or {}).get("color") or "#9ca3af"
    blurb = r["blurb"] or (r.get("description") or f"{lang} project")
    upd = dt.datetime.fromisoformat(r["pushedAt"].replace("Z", "+00:00")).strftime("%b %Y")
    name = r["name"] if len(r["name"]) <= 20 else r["name"][:19] + "…"
    b = (f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="12" fill="{PANEL}" stroke="{EDGE}" stroke-width="2"/>'
         f'<rect x="1" y="1" width="{w - 2}" height="4" rx="2" fill="{col}"/>'
         f'<text x="18" y="36" font-size="11" class="mono" style="fill:{MU}">&gt; repo</text>'
         f'<text x="18" y="60" font-size="17" class="monob" style="fill:{FG}">{html.escape(name)}</text>'
         + "".join(f'<text x="18" y="{84 + k * 17}" font-size="12" class="mono" style="fill:{MU}">{html.escape(ln)}</text>'
                   for k, ln in enumerate(wrap(blurb, 34)[:2]))
         + f'<circle cx="24" cy="{h - 22}" r="5" fill="{col}"/><text x="36" y="{h - 18}" font-size="12" class="mono" style="fill:{FG}">{html.escape(lang)}</text>'
         f'<text x="{w - 18}" y="{h - 18}" font-size="12" class="mono" text-anchor="end" style="fill:{YE}">★ {r["stargazerCount"]} <tspan style="fill:{MU}">· {upd}</tspan></text>')
    return arcade_doc(w, h, b, "", r["name"], scan=False)


def toolbox_header(cfg, s):
    b = head("TOOLBOX", GR, "click a tool to visit it")
    return arcade_doc(W, 76, b, "", "Toolbox")


TOOL_COL = {"Python": CY, "PyTorch": CY, "Hugging Face": CY, "LightGBM": CY, "polars": CY, "VAPT": PK,
            "TypeScript": YE, "JavaScript": YE, "HTML/CSS": YE, "C++": VI, "Java": VI, "MySQL": VI,
            "Docker": GR, "Git": GR, "Modal": GR, "Kaggle": GR, "Blender": PK, "Unity": PK}
CHIP_W, CHIP_H = 132, 40


def tool_chip(name, i):
    w, h = CHIP_W, CHIP_H
    col = TOOL_COL.get(name, CY)
    b = (f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="10" fill="{PANEL}" stroke="{EDGE}" stroke-width="1.5"/>'
         f'<rect x="14" y="{h / 2 - 4}" width="8" height="8" rx="1" fill="{col}"/>'
         f'<text x="{(w + 22) / 2}" y="{h / 2 + 4.5}" font-size="13" class="mono" text-anchor="middle" style="fill:{FG}">{html.escape(name)}</text>')
    return arcade_doc(w, h, b, "", name, scan=False, radius=10)


def button(kind, label):
    w, h = 200, 48
    col = {"linkedin": "#0a66c2", "email": YE, "github": FG}[kind]
    icons = {"linkedin": f'<rect x="16" y="14" width="20" height="20" rx="4" fill="#0a66c2"/><text x="26" y="29" font-size="12" class="monob" text-anchor="middle" style="fill:#fff">in</text>',
             "email": f'<rect x="16" y="16" width="22" height="16" rx="2" fill="none" stroke="{YE}" stroke-width="2"/><path d="M16 17 L27 25 L38 17" fill="none" stroke="{YE}" stroke-width="2"/>',
             "github": f'<text x="27" y="30" font-size="14" class="monob" text-anchor="middle" style="fill:{GR}">&gt;_</text>'}
    b = (f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="12" fill="{PANEL}" stroke="{col}" stroke-opacity=".7" stroke-width="1.5"/>'
         f'{icons[kind]}<text x="50" y="29" font-size="14" class="mono" style="fill:{FG}">{html.escape(label)}</text>')
    return arcade_doc(w, h, b, "", label, scan=False, radius=12)


def readme(cfg, s):
    L = cfg["links"]
    A = "assets/sketchbook"
    ver = lambda f: hashlib.sha1(open(os.path.join(OUT, f + ".svg"), "rb").read()).hexdigest()[:10]
    img = lambda f, alt, w="100%": f'<img src="{A}/{f}.svg?v={ver(f)}" width="{w}" alt="{html.escape(alt)}">'
    projects = " ".join(f'<a href="{r["url"]}">{img(f"project-{i + 1}", r["name"], "32%")}</a>' for i, r in enumerate(s["featured"]))
    slug = lambda n: "".join(ch for ch in n.lower() if ch.isalnum())
    tools = " ".join(f'<a href="{x["url"]}"><img src="{A}/tool-{slug(x["name"])}.svg?v={ver("tool-" + slug(x["name"]))}" height="40" alt="{html.escape(x["name"])}"></a>' for x in cfg["toolbox"])
    views = (f'<img src="https://komarev.com/ghpvc/?username={cfg["login"].lower()}&label=visitors&color=7c3aed&style=flat-square" '
             f'alt="profile views">')
    return f"""<!-- generated by scripts/build.py from profile.json + live GitHub data; edit profile.json, not this file -->
<div align="center">

{img("hero", f"Hi there! I'm {cfg['name']} (SruSan)")}

{img("now", "Right now: " + "; ".join(f"{k}: {v}" for k, v in cfg["now"].items()))}

{img("stats", f"{s['total']} contributions, current streak {s['streak']} days, longest {s['longest']} days, {s['stars']} stars")}

{img("languages", "Languages I write in")}

{img("calendar", "Commit Invaders: a pixel ship shoots down every week with commits")}

{projects}

{img("toolbox", "Toolbox")}

{tools}

<a href="{L['linkedin']}">{img("btn-linkedin", "LinkedIn", "200")}</a> <a href="mailto:{L['email']}">{img("btn-email", "Email", "200")}</a> <a href="{L['github']}">{img("btn-github", "GitHub", "200")}</a>

{views}

<a href="{L.get('site', L['github'])}">{img("credit", "custom-built by SruSan", "330")}</a>

<sub>redrawn every day from live GitHub data by <a href="scripts/build.py">scripts/build.py</a></sub>

</div>
"""


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data"); ap.add_argument("--save")
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, "profile.json")))
    if a.data:
        d = json.load(open(a.data))
    else:
        tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not tok:
            raise SystemExit("set GITHUB_TOKEN (or use --data cache.json)")
        d = fetch(cfg["login"], tok)
        if a.save:
            json.dump(d, open(a.save, "w"))
    s = summarize(d, cfg)
    os.makedirs(OUT, exist_ok=True)
    files = {"hero": hero(cfg, s), "now": now(cfg, s), "stats": stats(cfg, s), "languages": languages(cfg, s),
             "calendar": calendar(cfg, s), "toolbox": toolbox_header(cfg, s),
             "btn-linkedin": button("linkedin", "LinkedIn"), "btn-email": button("email", "Say hi"), "btn-github": button("github", "@SruSanCyborg"), "credit": credit(cfg, s)}
    for i, r in enumerate(s["featured"]):
        files[f"project-{i + 1}"] = project(cfg, r, i)
    for i, x in enumerate(cfg["toolbox"]):
        files["tool-" + "".join(ch for ch in x["name"].lower() if ch.isalnum())] = tool_chip(x["name"], i)
    for k, v in files.items():
        open(os.path.join(OUT, k + ".svg"), "w").write(v)
    open(os.path.join(ROOT, "README.md"), "w").write(readme(cfg, s))
    json.dump({k: v for k, v in s.items() if k not in ("weeks", "featured")} | {"featured": [r["name"] for r in s["featured"]]},
              open(os.path.join(OUT, "summary.json"), "w"), indent=1)
    print(f"wrote {len(files)} SVGs: {s['total']} contributions, streak {s['streak']}, longest {s['longest']}, "
          f"{s['stars']} stars, featured {[r['name'] for r in s['featured']]}")


if __name__ == "__main__":
    main()
