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


def arcade_doc(w, h, body, css, title):
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
            '<radialGradient id="lens" cx="45%" cy="40%" r="70%"><stop offset="0" stop-color="#3f3f46"/><stop offset="1" stop-color="#050505"/></radialGradient></defs>'
            f'<rect width="{w}" height="{h}" rx="18" fill="#050505"/>{body}<rect width="{w}" height="{h}" rx="18" fill="url(#scan)"/>'
            f'<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="17" fill="none" stroke="#27272a" stroke-width="3"/></svg>')


def stars(w, h, n=30, seed=7):
    out = ""
    for k in range(n):
        sx, sy = (k * 97 + seed * 13) % (w - 40) + 20, (k * 53 + seed * 29) % (h - 40) + 20
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
    css, body = [], stars(w, h, 34)
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
    # SA monogram with morphing liquid blobs (after the LinkedIn banner)
    cx, cy = 690, 150
    blobs = [
        ("M612 96 C590 70 600 44 628 50 C652 56 650 84 636 96 C628 104 620 104 612 96 Z", "M608 98 C584 76 596 40 630 46 C660 52 654 88 638 100 C628 108 616 106 608 98 Z", 7),
        ("M760 90 C770 60 808 54 816 80 C824 106 800 120 780 114 C766 110 756 104 760 90 Z", "M756 94 C764 56 812 50 820 82 C826 112 796 124 776 116 C760 110 752 106 756 94 Z", 9),
        ("M748 212 C770 206 790 226 778 246 C766 264 740 256 736 238 C733 226 738 216 748 212 Z", "M744 208 C774 200 796 228 780 250 C764 270 734 258 732 236 C730 222 736 212 744 208 Z", 8),
        ("M618 226 C604 226 596 240 606 250 C616 260 632 252 630 240 C629 232 625 226 618 226 Z", "M620 222 C600 224 592 244 606 254 C620 264 636 252 634 238 C632 228 628 222 620 222 Z", 6)]
    for a, b, d in blobs:
        body += (f'<path d="{a}" fill="url(#blob)" stroke="#52525b" stroke-width="1"><animate attributeName="d" values="{a};{b};{a}" dur="{d}s" repeatCount="indefinite"/></path>')
    body += (f'<circle cx="{cx}" cy="{cy}" r="72" fill="url(#lens)" stroke="#3f3f46" stroke-width="2"/>'
             f'<circle cx="{cx}" cy="{cy}" r="72" fill="none" stroke="#fafafa" stroke-opacity=".08" stroke-width="10"/>'
             f'<path d="M{cx - 30} {cy - 58} A64 64 0 0 1 {cx + 44} {cy - 44}" fill="none" stroke="#fff" stroke-opacity=".18" stroke-width="4" stroke-linecap="round"/>'
             f'<image href="data:image/png;base64,{logo_b64("white")}" x="{cx - 49}" y="{cy - 24}" width="98" height="48"/>')
    for k, (ix, iy, col, d) in enumerate(((470, 34, "#a78bfa", 0), (520, 276, "#f472b6", .6))):
        css.append(f"@keyframes bob{k}{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-8px)}}}}.bob{k}{{animation:bob{k} 1.4s ease-in-out {d}s infinite}}")
        body += f'<g class="bob{k}">{invader(ix, iy, 2.6, col)}</g>'
    body += (f'<text x="{w - 44}" y="{h - 48}" font-size="21" class="mono" text-anchor="end" style="fill:#fafafa;letter-spacing:1px">_{html.escape(cfg["name"])}</text>'
             f'<text x="{w - 44}" y="{h - 26}" font-size="12" class="mono" text-anchor="end" style="fill:#a1a1aa;letter-spacing:2px">{html.escape(cfg["links"]["email"])}</text>')
    return arcade_doc(w, h, body, "".join(css), f"{cfg['name']}: " + "; ".join(lines))


def now(cfg, s):
    h = 190
    items = list(cfg["now"].items())[:3]
    b = t(W / 2, 46, "right now", 30, INK, "middle") + squiggle(W / 2 - 70, W / 2 + 70, 58, BLUE, 4)
    cw = 250
    for i, (k, v) in enumerate(items):
        x = 38 + i * (cw + 24)
        r = [-2.5, 1.8, -1.6][i]
        b += (f'<g class="pop" style="animation-delay:{.3 + i * .25}s"><g style="--r:{r}deg;transform-box:fill-box;transform-origin:50% 0;animation:sway {5 + i}s ease-in-out infinite">'
              f'<rect x="{x}" y="78" width="{cw}" height="92" rx="6" fill="{NOTE[i]}" stroke="{INK}" stroke-width="2.3" filter="url(#wob)"/>'
              f'<rect x="{x + cw / 2 - 26}" y="70" width="52" height="16" fill="#ffffffaa" stroke="#00000022"/>'
              f'{t(x + 18, 104, k, 17, MUTED)}' + "".join(t(x + 18, 132 + j * 24, ln, 20 if len(v) < 24 else 18) for j, ln in enumerate(wrap(v, 24)[:2])) + '</g></g>')
    return doc(h, b, title="Right now: " + "; ".join(f"{k}: {v}" for k, v in items))


def flame(x, y):
    return (f'<g transform="translate({x} {y})"><g class="flame">'
            f'<path d="M0 -38 C18 -18 26 -4 16 12 C10 22 -10 22 -16 12 C-26 -4 -12 -14 -6 -26 C-4 -14 4 -10 6 -16 C8 -24 4 -30 0 -38 Z" '
            f'fill="#fb923c" stroke="{INK}" stroke-width="2.4"/><path d="M0 -6 C8 2 8 12 0 14 C-8 12 -8 2 0 -6 Z" fill="#fde047"/></g></g>')


def stats(cfg, s):
    h = 290
    css = """.flame{transform-box:fill-box;transform-origin:50% 100%;animation:flick .9s ease-in-out infinite alternate}
@keyframes flick{0%{transform:scale(1,1) rotate(-3deg)}100%{transform:scale(1.08,.94) rotate(3deg)}}"""
    b = t(40, 52, "report card", 30) + squiggle(42, 190, 64, GREEN, 4) + t(W - 40, 52, f"since {s['since']} · updates daily", 17, MUTED, "end")
    big = [("contributions", f"{s['total']:,}", "all time", NOTE[1]), ("current streak", f"{s['streak']}", "days", NOTE[5]),
           ("longest streak", f"{s['longest']}", "days", NOTE[0]), ("stars earned", f"{s['stars']}", "★ on public repos", NOTE[4])]
    cw = 180
    for i, (lab, val, sub, col) in enumerate(big):
        x = 40 + i * (cw + 17)
        b += (f'<g class="pop" style="animation-delay:{.2 + i * .2}s">'
              f'<rect x="{x}" y="88" width="{cw}" height="118" rx="14" fill="{col}" stroke="{INK}" stroke-width="2.3" filter="url(#wob)"/>'
              f'{t(x + cw / 2, 116, lab, 18, MUTED, "middle")}{t(x + cw / 2, 164, val, 46, INK, "middle")}{t(x + cw / 2, 192, sub, 16, MUTED, "middle")}</g>')
        if i == 1:
            b += flame(x + cw - 12, 92)
    small = [(f"{s['commits_year']:,}", "commits this year"), (f"{s['prs']}", "pull requests"), (f"{s['repos']}", "public repos"), (f"{s['followers']}", "followers")]
    for i, (val, lab) in enumerate(small):
        x = 40 + i * (cw + 17)
        b += f'<g class="pop" style="animation-delay:{1 + i * .15}s">{t(x + 8, 246, val, 26, BLUE)}{t(x + 8 + len(val) * 13 + 10, 246, lab, 18, MUTED)}</g>'
    return doc(h, b, css, title=f"{s['total']} contributions, {s['streak']}-day streak, longest {s['longest']}, {s['stars']} stars")


def languages(cfg, s):
    langs = s["langs"]
    h = 110 + 44 * len(langs)
    css = "".join(f".bar{i}{{transform-box:fill-box;transform-origin:0 50%;animation:grow 1.1s cubic-bezier(.2,.8,.2,1) {.3 + i * .15}s both}}"
                  for i in range(len(langs))) + "@keyframes grow{from{transform:scaleX(0)}}"
    b = t(40, 52, "what I write in", 30) + squiggle(42, 250, 64, RED, 4) + t(W - 40, 52, "by code size, public repos", 17, MUTED, "end")
    mx = max(p for _, p, _ in langs) or 1
    for i, (n, p, col) in enumerate(langs):
        y = 96 + i * 44
        bw = 520 * p / mx
        b += t(40, y + 22, n, 21)
        b += (f'<g class="bar{i}"><rect x="200" y="{y}" width="{bw:.0f}" height="30" rx="8" fill="{col}" stroke="{INK}" stroke-width="2.2" filter="url(#wob)"/>'
              + "".join(f'<path d="M{200 + k} {y + 28} l12 -26" stroke="#ffffff66" stroke-width="3"/>' for k in range(10, int(bw) - 10, 16)) + "</g>")
        b += f'<g class="pop" style="animation-delay:{1 + i * .15}s">{t(210 + bw + 8, y + 22, f"{p * 100:.0f}%", 19, MUTED)}</g>'
    return doc(h, b, css, title="Languages: " + ", ".join(f"{n} {p * 100:.0f}%" for n, p, _ in langs))


def pixel_ship(x, y, px=3, color="#f472b6"):
    rows = ["....X....", "...XXX...", "...XXX...", ".XXXXXXX.", "XXXXXXXXX", "XX.XXX.XX", "X...X...X"]
    return "".join(f'<rect x="{x + c * px}" y="{y + r * px}" width="{px}" height="{px}" fill="{color}"/>'
                   for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == "X")


def calendar(cfg, s):
    weeks = s["weeks"][-52:]
    w, h = W, 300
    T = 18.0
    vals = sorted(v for wk in weeks for v in wk if v > 0)
    q = [vals[int(len(vals) * f)] if vals else 1 for f in (.25, .5, .75)]
    pal = ["#18181b", "#166534", "#16a34a", "#22c55e", "#86efac"]
    lvl = lambda v: 0 if v == 0 else 1 if v <= q[0] else 2 if v <= q[1] else 3 if v <= q[2] else 4
    cell, gap, x0, y0 = 11.6, 3.1, 44, 112
    n, step = len(weeks), cell + gap
    ship_y = y0 + 7 * step + 34
    css = [f".ship{{animation:fly {T}s linear infinite}}@keyframes fly{{from{{transform:translateX(0)}}to{{transform:translateX({n * step:.1f}px)}}}}",
           "@keyframes march{0%,100%{transform:translateX(0)}50%{transform:translateX(60px)}}.march{animation:march 6s ease-in-out infinite}",
           "@keyframes flipA{0%,49%{opacity:1}50%,100%{opacity:0}}@keyframes flipB{0%,49%{opacity:0}50%,100%{opacity:1}}"
           ".fa{animation:flipA .8s steps(1) infinite}.fb{animation:flipB .8s steps(1) infinite}"]
    body = stars(w, h, 26, 3)
    body += (f'<text x="44" y="46" font-size="15" class="px" style="fill:#67e8f9">COMMIT INVADERS</text>'
             f'<text x="{w - 44}" y="46" font-size="11" class="px" text-anchor="end" style="fill:#fde047">HI-SCORE {s["year_total"]:05d}</text>')
    body += '<g class="march">' + "".join(
        f'<g class="fa">{invader(90 + k * 130, 64, 2.2, c)}</g><g class="fb">{invader(90 + k * 130, 64, 2.2, c, 1)}</g>'
        for k, c in enumerate(["#a78bfa", "#f472b6", "#67e8f9", "#fde047", "#4ade80"])) + "</g>"
    score, hits = 0, []
    for i, wk in enumerate(weeks):
        colx = x0 + i * step
        p = 100 * (i + 0.5) / n
        live = [(j, v) for j, v in enumerate(wk) if v > 0]
        if live:
            a, b2, c2 = max(p - 0.3, 0), min(p + 0.9, 100), min(p + 5, 100)
            css.append(f"@keyframes lz{i}{{0%,{a:.2f}%{{opacity:0}}{a + .01:.2f}%,{b2:.2f}%{{opacity:1}}{b2 + .01:.2f}%,100%{{opacity:0}}}}"
                       f".lz{i}{{opacity:0;animation:lz{i} {T}s linear infinite}}"
                       f"@keyframes h{i}{{0%,{b2:.2f}%{{transform:scale(1);opacity:1}}{b2 + .4:.2f}%{{transform:scale(.15);opacity:.1}}{c2 - 1:.2f}%{{transform:scale(.15);opacity:.1}}{c2:.2f}%,100%{{transform:scale(1);opacity:1}}}}"
                       f".h{i}{{transform-box:fill-box;transform-origin:center;animation:h{i} {T}s linear infinite}}")
            for k2, (dx, dy) in enumerate(((-9, -9), (9, -9), (-9, 9), (9, 9))):
                css.append(f"@keyframes sp{i}_{k2}{{0%,{b2:.2f}%{{opacity:0;transform:translate(0,0)}}{b2 + .1:.2f}%{{opacity:1}}{b2 + 1.6:.2f}%{{opacity:0;transform:translate({dx}px,{dy}px)}}100%{{opacity:0}}}}"
                           f".sp{i}_{k2}{{opacity:0;animation:sp{i}_{k2} {T}s linear infinite}}")
            body += f'<rect class="lz{i}" x="{colx + cell / 2 - 1:.1f}" y="{y0:.1f}" width="2" height="{ship_y - y0:.1f}" fill="#fde047"/>'
            score += sum(v for _, v in live)
            hits.append((b2, score))
        for j, v in enumerate(wk):
            L = lvl(v)
            hc = f' class="h{i}"' if L else ""
            body += f'<rect{hc} x="{colx:.1f}" y="{y0 + j * step:.1f}" width="{cell}" height="{cell}" rx="2" fill="{pal[L]}"/>'
            if L:
                for k2 in range(4):
                    body += f'<rect class="sp{i}_{k2}" x="{colx + cell / 2 - 1.5:.1f}" y="{y0 + j * step + cell / 2 - 1.5:.1f}" width="3" height="3" fill="#fde047"/>'
    # live score: one text per hit, visible from its hit until the next
    marks = [(0.0, 0)] + hits
    for k, (start, val) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else 100
        css.append(f"@keyframes sc{k}{{0%,{max(start - .01, 0):.2f}%{{opacity:0}}{start:.2f}%,{max(end - .01, start):.2f}%{{opacity:1}}{end:.2f}%,100%{{opacity:0}}}}"
                   f".sc{k}{{opacity:0;animation:sc{k} {T}s linear infinite}}")
        body += f'<text class="sc{k} px" x="44" y="{h - 18}" font-size="10" style="fill:#fafafa">SCORE {val:05d}</text>'
    body += f'<g class="ship">{pixel_ship(x0 + cell / 2 - 13.5, ship_y, 3)}</g>'
    body += (f'<rect x="30" y="{h - 40}" width="{w - 60}" height="2" fill="#27272a"/>'
             f'<text x="{w - 44}" y="{h - 18}" font-size="10" class="px" text-anchor="end" style="fill:#a1a1aa">{s["total"]} COMMITS SINCE {s["since"]} · 1UP SRUSAN</text>')
    return arcade_doc(w, h, body, "".join(css), f"Commit Invaders: {s['year_total']} contributions in the last year")



def project(cfg, r, i):
    w, h = 270, 180
    lang = (r.get("primaryLanguage") or {}).get("name") or "code"
    col = (r.get("primaryLanguage") or {}).get("color") or "#9ca3af"
    blurb = r["blurb"] or f"{lang} project"
    upd = dt.datetime.fromisoformat(r["pushedAt"].replace("Z", "+00:00")).strftime("%b %Y")
    rot = [-1.8, 1.2, -1.0][i % 3]
    words, lines, cur = blurb.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) > 28:
            lines.append(cur); cur = wd
        else:
            cur = (cur + " " + wd).strip()
    lines.append(cur)
    css = (f"@keyframes sway2{{0%,100%{{transform:rotate({rot}deg)}}50%{{transform:rotate({-rot}deg)}}}}"
           ".card{transform-box:fill-box;transform-origin:50% 0;animation:sway2 6s ease-in-out infinite}")
    body = (f'<g class="card"><rect x="14" y="16" width="{w - 28}" height="{h - 30}" rx="8" fill="#fff" stroke="{INK}" stroke-width="2.3" filter="url(#wob)"/>'
            f'<line x1="14" y1="54" x2="{w - 14}" y2="54" stroke="{RED}" stroke-width="1.6" opacity=".6"/>'
            + "".join(f'<line x1="24" y1="{y}" x2="{w - 24}" y2="{y}" stroke="#c7dcf5" stroke-width="1.2"/>' for y in (82, 106, 130))
            + f'<circle cx="{w / 2}" cy="18" r="7" fill="{RED}" stroke="{INK}" stroke-width="1.6"/>'
            + t(28, 44, r["name"][:22], 22 if len(r["name"]) < 18 else 18)
            + "".join(t(28, 78 + k * 24, ln, 17, MUTED) for k, ln in enumerate(lines[:3]))
            + f'<circle cx="34" cy="{h - 30}" r="7" fill="{col}" stroke="{INK}" stroke-width="1.5"/>{t(48, h - 24, lang, 16)}'
            + t(w - 28, h - 24, f"★ {r['stargazerCount']} · {upd}", 16, MUTED, "end") + "</g>")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(r["name"])}">'
           f'<title>{html.escape(r["name"])}</title><style>{font_css()}{BASE_CSS}{css}</style>{DEFS}{body}</svg>')
    return svg


def toolbox_header(cfg, s):
    b = t(40, 52, "toolbox", 30) + squiggle(42, 150, 64, AMBER, 4) + t(W - 40, 52, "click a tool to visit it", 17, MUTED, "end")
    return doc(86, b, title="Toolbox")


def tool_chip(name, i):
    w, h = int(len(name) * 10.5 + 44), 50
    r = [-3, 2, -1.5, 2.5, -2][i % 5]
    body = (f'<g transform="rotate({r} {w / 2} {h / 2})"><rect x="6" y="9" width="{w - 12}" height="34" rx="17" fill="#00000022"/>'
            f'<rect x="4" y="6" width="{w - 12}" height="34" rx="17" fill="{NOTE[i % len(NOTE)]}" stroke="{INK}" stroke-width="2" filter="url(#wob)"/>'
            f'{t((w - 8) / 2, 29, name, 18, INK, "middle")}</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(name)}">'
            f'<title>{html.escape(name)}</title><style>{font_css()}{BASE_CSS}</style>{DEFS}<g class="pop" style="animation-delay:{.1 + i * .06:.2f}s">{body}</g></svg>')



def button(kind, label):
    w, h = 200, 60
    icons = {"linkedin": f'<rect x="22" y="16" width="28" height="28" rx="6" fill="#0a66c2" stroke="{INK}" stroke-width="2"/><text x="36" y="37" font-size="17" text-anchor="middle" style="fill:#fff">in</text>',
             "email": f'<rect x="20" y="19" width="32" height="22" rx="3" fill="#fde68a" stroke="{INK}" stroke-width="2"/><path d="M20 20 L36 32 L52 20" fill="none" stroke="{INK}" stroke-width="2"/>',
             "github": f'<circle cx="36" cy="30" r="14" fill="{INK}"/><text x="36" y="35" font-size="13" text-anchor="middle" style="fill:#fff">&lt;/&gt;</text>'}
    body = (f'<rect x="6" y="8" width="{w - 10}" height="{h - 14}" rx="22" fill="#00000018"/>'
            f'<rect x="3" y="4" width="{w - 10}" height="{h - 14}" rx="22" fill="{PAPER}" stroke="{INK}" stroke-width="2.4" filter="url(#wob)"/>'
            f'{icons[kind]}{t(66, 36, label, 20)}')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{label}">'
            f'<title>{label}</title><style>{font_css()}{BASE_CSS}</style>{DEFS}{body}</svg>')


def readme(cfg, s):
    L = cfg["links"]
    A = "assets/sketchbook"
    ver = lambda f: hashlib.sha1(open(os.path.join(OUT, f + ".svg"), "rb").read()).hexdigest()[:10]
    img = lambda f, alt, w="100%": f'<img src="{A}/{f}.svg?v={ver(f)}" width="{w}" alt="{html.escape(alt)}">'
    projects = " ".join(f'<a href="{r["url"]}">{img(f"project-{i + 1}", r["name"], "32%")}</a>' for i, r in enumerate(s["featured"]))
    slug = lambda n: "".join(ch for ch in n.lower() if ch.isalnum())
    tools = " ".join(f'<a href="{x["url"]}"><img src="{A}/tool-{slug(x["name"])}.svg?v={ver("tool-" + slug(x["name"]))}" height="50" alt="{html.escape(x["name"])}"></a>' for x in cfg["toolbox"])
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
