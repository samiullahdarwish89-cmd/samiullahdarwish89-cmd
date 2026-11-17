"""Render local, script-free GitHub analytics images from a validated snapshot."""

from __future__ import annotations

from datetime import date
from html import escape
from math import pi

INK = "#eef2ff"
MUTED = "#a4b1ce"
FAINT = "#7282a4"
PALETTE = ["#b59bff", "#64d9dc", "#7da7ff", "#f6c387", "#e5a0cf", "#8e9dbd"]


def text(x: float, y: float, value: object, size: float = 18, color: str = INK,
         weight: int = 400, anchor: str = "start", spacing: float = 0) -> str:
    return (f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" fill="{color}" '
            f'font-weight="{weight}" text-anchor="{anchor}" letter-spacing="{spacing:g}">'
            f'{escape(str(value))}</text>')


def rect(x: float, y: float, width: float, height: float, radius: float = 20,
         fill: str = "url(#panel)", stroke: str = "#8c9ac2", opacity: float = .22) -> str:
    return (f'<rect x="{x:g}" y="{y:g}" width="{width:g}" height="{height:g}" rx="{radius:g}" '
            f'fill="{fill}" stroke="{stroke}" stroke-opacity="{opacity:g}"/>')


def line(x: float, y: float, end: float) -> str:
    return f'<path d="M{x:g} {y:g}H{end:g}" stroke="#8c9ac2" stroke-opacity=".17"/>'


def card(x: float, y: float, width: float, height: float, title: str, subtitle: str,
         mobile: bool) -> list[str]:
    pad = 30 if mobile else 26
    return [rect(x + 1, y + 1, width - 2, height - 2),
            text(x + pad, y + 38, title, 24 if mobile else 21, INK, 600),
            text(x + pad, y + 65, subtitle, 20 if mobile else 13, MUTED)]


def donut(cx: float, cy: float, radius: float, values: list[tuple[str, int]],
          center: str, caption: str, mobile: bool) -> list[str]:
    total = sum(value for _, value in values)
    circumference = 2 * pi * radius
    width = 19 if mobile else 17
    parts = [f'<circle cx="{cx:g}" cy="{cy:g}" r="{radius:g}" fill="none" '
             f'stroke="#27334f" stroke-width="{width}"/>']
    offset = 0.0
    for index, (name, value) in enumerate(values):
        if not total or not value:
            continue
        length = circumference * value / total
        parts.append(
            f'<circle cx="{cx:g}" cy="{cy:g}" r="{radius:g}" fill="none" '
            f'stroke="{PALETTE[index % len(PALETTE)]}" stroke-width="{width}" '
            f'stroke-dasharray="{length:.6f} {circumference:.6f}" '
            f'stroke-dashoffset="{-offset:.6f}" transform="rotate(-90 {cx:g} {cy:g})">'
            f'<title>{escape(name)}: {value:,}</title></circle>')
        offset += length
    parts.extend([text(cx, cy + 4, center, 35 if mobile else 31, INK, 600, "middle"),
                  text(cx, cy + 29, caption, 18 if mobile else 12, MUTED, anchor="middle")])
    return parts


def legend(x: float, y: float, width: float, values: list[tuple[str, int]],
           mobile: bool, percentages: bool = False) -> list[str]:
    parts = []
    total = sum(value for _, value in values)
    for index, (name, value) in enumerate(values):
        row = y + index * (31 if mobile else 26)
        parts.append(rect(x, row - 10, 8, 8, 3, PALETTE[index % len(PALETTE)], opacity=0))
        parts.append(text(x + 17, row, name, 20 if mobile else 15, MUTED))
        rendered = f"{value / total * 100:.1f}%" if percentages and total else f"{value:,}"
        parts.append(text(x + width, row, rendered, 20 if mobile else 15, INK, 500, "end"))
    return parts


def weekly_chart(snapshot: dict, x: float, y: float, width: float, height: float,
                 mobile: bool) -> list[str]:
    weeks = snapshot.get("weeks", [])
    maximum = max([week["contributions"] for week in weeks] + [1])
    bottom = y + height
    parts = [line(x, bottom, x + width), line(x, y, x + width)]
    parts.append(text(x + width, y - 10, f"Weekly peak · {max((w['contributions'] for w in weeks), default=0)}",
                      19 if mobile else 12, MUTED, anchor="end"))
    if weeks:
        cell = width / len(weeks)
        bar_width = cell * .65
        for index, week in enumerate(weeks):
            value = week["contributions"]
            bar_height = height * value / maximum
            bar_x = x + index * cell + (cell - bar_width) / 2
            parts.append(
                f'<rect x="{bar_x:.3f}" y="{bottom - bar_height:.3f}" width="{bar_width:.3f}" '
                f'height="{bar_height:.3f}" rx="2" fill="url(#bar)">'
                f'<title>Week of {escape(week["week_start"])}: {value} contributions</title></rect>')
    parts.extend([text(x, bottom + 26, f"Jan 1, {snapshot['period']['year']}", 19 if mobile else 12, FAINT),
                  text(x + width, bottom + 26, snapshot["fetched_at"][:10],
                       19 if mobile else 12, FAINT, anchor="end")])
    return parts


def language_card(snapshot: dict, x: float, y: float, width: float, height: float,
                  mobile: bool) -> list[str]:
    values = [(item["name"], item["bytes"]) for item in snapshot.get("languages", []) if item["bytes"]]
    language_count = len(values)
    if len(values) > 5:
        values = values[:4] + [("Other", sum(value for _, value in values[4:]))]
    parts = card(x, y, width, height, "Public code languages", "Share of code bytes · non-fork repositories", mobile)
    cy = y + (177 if mobile else 166)
    cx = x + (117 if mobile else 108)
    total = sum(value for _, value in values)
    center = str(language_count) if total else "0"
    parts.extend(donut(cx, cy, 67 if mobile else 59, values, center,
                       "language" if language_count == 1 else "languages", mobile))
    if values:
        legend_x = x + (224 if mobile else 205)
        step = 31 if mobile else 26
        legend_y = cy - (len(values) - 1) * step / 2 + 6
        parts.extend(legend(legend_x, legend_y, width - (255 if mobile else 234), values, mobile, True))
    else:
        parts.append(text(x + width - 28, cy, "No public code detected", 20 if mobile else 14,
                          MUTED, anchor="end"))
    parts.append(text(x + (30 if mobile else 26), y + height - 25,
                      "Private code is excluded.", 20 if mobile else 13, FAINT))
    return parts


def weekday_card(snapshot: dict, x: float, y: float, width: float, height: float,
                 mobile: bool) -> list[str]:
    parts = card(x, y, width, height, "Contribution rhythm", "Contributions by weekday · year to date · UTC", mobile)
    values = [0] * 7
    for day in snapshot.get("daily", []):
        values[date.fromisoformat(day["date"]).weekday()] += day["contributions"]
    maximum = max(values + [1])
    pad = 33 if mobile else 30
    chart_x, chart_width = x + pad, width - pad * 2
    baseline = y + height - 48
    chart_height = height - (165 if mobile else 155)
    parts.append(line(chart_x, baseline, chart_x + chart_width))
    cell = chart_width / 7
    for index, (name, value) in enumerate(zip(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], values)):
        center = chart_x + (index + .5) * cell
        bar_height = chart_height * value / maximum
        parts.append(
            f'<rect x="{center - cell * .23:.3f}" y="{baseline - bar_height:.3f}" '
            f'width="{cell * .46:.3f}" height="{bar_height:.3f}" rx="4" fill="url(#bar)">'
            f'<title>{name}: {value} contributions</title></rect>')
        parts.extend([text(center, baseline - bar_height - 12, value, 19 if mobile else 14, INK, 500, "middle"),
                      text(center, baseline + 28, name, 20 if mobile else 13, MUTED, anchor="middle")])
    return parts


def stats_card(snapshot: dict, x: float, y: float, width: float, height: float,
               mobile: bool) -> list[str]:
    parts = card(x, y, width, height, "Public profile", "Current public totals", mobile)
    metrics = snapshot["metrics"]
    items = [("Stars received", metrics.get("public_stars", 0)),
             ("Followers", metrics.get("followers", 0)),
             ("Public repositories", metrics["public_repositories"]),
             ("Active days this year", metrics.get("active_days", 0))]
    left = x + (30 if mobile else 26)
    cell_width = (width - (60 if mobile else 52)) / 2
    top = y + (124 if mobile else 112)
    row_height = 90 if mobile else 82
    parts.append(line(left, y + (181 if mobile else 166), x + width - (30 if mobile else 26)))
    parts.append(f'<path d="M{x + width / 2:g} {y + 91:g}V{y + height - 25:g}" stroke="#8c9ac2" stroke-opacity=".17"/>')
    for index, (label, value) in enumerate(items):
        px = left + (index % 2) * cell_width + (14 if index % 2 else 0)
        py = top + (index // 2) * row_height
        parts.extend([text(px, py, f"{value:,}", 38 if mobile else 33, PALETTE[index % 3], 600),
                      text(px, py + 28, label, 20 if mobile else 13, MUTED)])
    return parts


def contribution_card(snapshot: dict, x: float, y: float, width: float, height: float,
                      mobile: bool) -> list[str]:
    kinds = snapshot.get("contribution_types", {})
    labels = [("Commits", "commits"), ("Issues", "issues"), ("Pull requests", "pull_requests"),
              ("Reviews", "reviews"), ("Repositories", "repositories"), ("Account joined", "joined")]
    values = [(label, kinds.get(key, 0)) for label, key in labels]
    parts = card(x, y, width, height, "Contribution breakdown", "Public contributions · year to date", mobile)
    cy, cx = y + (194 if mobile else 180), x + (117 if mobile else 108)
    parts.extend(donut(cx, cy, 67 if mobile else 59, values,
                       f"{snapshot['metrics']['public_contributions']:,}", "total", mobile))
    legend_x = x + (224 if mobile else 205)
    parts.extend(legend(legend_x, y + (115 if mobile else 108),
                        width - (255 if mobile else 234), values, mobile))
    return parts


def render(snapshot: dict, mobile: bool) -> str:
    width, height = (600, 1824) if mobile else (1000, 962)
    year, updated = snapshot["period"]["year"], snapshot["fetched_at"][:10]
    metrics = snapshot["metrics"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="analytics-title analytics-desc">',
        '<title id="analytics-title">Samiullah Darwish — Public GitHub analytics</title>',
        f'<desc id="analytics-desc">{escape(snapshot["login"])}: {metrics["public_repositories"]} public repositories, {metrics["public_contributions"]} public contributions, {metrics.get("active_days", 0)} active days from January 1, {year} through {escape(updated)} UTC. Charts show actual weekly contributions, public code language bytes, weekday contributions and contribution types. Private repositories are excluded.</desc>',
        '<defs><linearGradient id="panel" x2="1" y2="1"><stop stop-color="#121b30"/><stop offset="1" stop-color="#17172f"/></linearGradient><linearGradient id="hero" x2="1" y2="1"><stop stop-color="#18233c"/><stop offset="1" stop-color="#1a1837"/></linearGradient><linearGradient id="bar" x2="0" y2="1"><stop stop-color="#72e0df"/><stop offset="1" stop-color="#aa8bf5"/></linearGradient></defs>',
        '<g font-family="Arial,Helvetica,sans-serif">',
    ]
    hero_height = 410 if mobile else 332
    parts.append(rect(1, 1, width - 2, hero_height - 2, fill="url(#hero)"))
    pad = 30 if mobile else 32
    parts.extend([text(pad, 36, "GITHUB / ANALYTICS", 19 if mobile else 12, "#9ecedc", 600, spacing=2),
                  text(pad, 81 if mobile else 78, "Samiullah Darwish", 33 if mobile else 34, INK, 600)])
    if mobile:
        parts.append(text(pad, 112, f"Public activity · {year} · updated {updated}", 20, MUTED))
    else:
        parts.append(text(width - pad, 36, f"Updated {updated} · UTC", 12, MUTED, anchor="end"))
        parts.append(text(pad, 104, "Public activity. A clear view of the work shared on GitHub.", 15, MUTED))
    top = 174 if mobile else 163
    positions = [pad, 310] if mobile else [pad, 355, 674]
    main_metrics = [(metrics["public_repositories"], "Public repositories"),
                    (metrics["public_contributions"], "Contributions · YTD"),
                    (metrics.get("active_days", 0), "Active days · YTD")]
    for index, ((value, label), px) in enumerate(zip(main_metrics, positions)):
        parts.extend([text(px, top, f"{value:,}", 40 if mobile else 38, PALETTE[index], 600),
                      text(px, top + 27, label, 20 if mobile else 13, MUTED)])
    chart_y = 263 if mobile else 229
    parts.append(text(pad, chart_y - 22, "Weekly contributions", 20 if mobile else 14, INK, 500))
    parts.extend(weekly_chart(snapshot, pad, chart_y, width - pad * 2, 91 if mobile else 53, mobile))
    if mobile:
        parts.extend(language_card(snapshot, 0, 428, 600, 310, True))
        parts.extend(weekday_card(snapshot, 0, 756, 600, 320, True))
        parts.extend(stats_card(snapshot, 0, 1094, 600, 310, True))
        parts.extend(contribution_card(snapshot, 0, 1422, 600, 340, True))
        parts.extend([text(30, 1794, "GitHub API · Public only · Daily refresh", 19, MUTED),
                      text(30, 1818, "Public language shares are code statistics.", 19, FAINT)])
    else:
        parts.extend(language_card(snapshot, 0, 350, 490, 278, False))
        parts.extend(weekday_card(snapshot, 510, 350, 490, 278, False))
        parts.extend(stats_card(snapshot, 0, 646, 490, 278, False))
        parts.extend(contribution_card(snapshot, 510, 646, 490, 278, False))
        parts.append(text(26, 952, "GitHub API · Public data only · Refreshed daily", 12, MUTED))
        parts.append(text(974, 952, "Language shares describe code, not skill levels.", 12, FAINT, anchor="end"))
    parts.append('</g></svg>\n')
    return "\n".join(parts)


def activity_svg(snapshot: dict) -> str:
    return render(snapshot, False)


def activity_svg_mobile(snapshot: dict) -> str:
    return render(snapshot, True)
