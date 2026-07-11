import flet as ft
import flet.canvas as cv
from datetime import datetime, timedelta, timezone

from app import theme
from app.services.database import Database
from config.i18n import t
from config.profiles import AppState

# Series to plot: (db column, sensor name, line color, value format)
# Colors match the dashboard cards so each sensor keeps one identity color.
_SERIES = [
    ("ec", "EC", "#2196F3", "{:.2f}"),
    ("ph", "PH", "#9C27B0", "{:.2f}"),
    ("temp", "Temperature", "#FF9800", "{:.1f}"),
    ("humidity", "Humidity", "#009688", "{:.1f}"),
]

# Selectable time windows: (key, label, hours)
_TIMEFRAMES = [
    ("1h", "1 h", 1),
    ("6h", "6 h", 6),
    ("24h", "24 h", 24),
    ("7d", "7 d", 24 * 7),
]

_CHART_H = 150          # canvas height (px)
_PAD_L, _PAD_R = 40, 8  # left gutter for y labels / right margin
_PAD_T, _PAD_B = 8, 18  # top margin / bottom gutter for time labels
_MAX_POINTS = 110       # downsample buckets — smooths jitter, keeps paint light
# Gap cap when integrating out-of-range time: a logging hole (app off) must not
# count as "out of range for hours". Readings land every ~30s.
_MAX_GAP_S = 120.0


def _parse_ts(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _downsample(points: list[tuple[datetime, float]], n: int) -> list[tuple[datetime, float]]:
    """Average into at most n time buckets (oldest→newest input). Keeps the
    trend readable instead of plotting every noisy 30-second sample."""
    if len(points) <= n:
        return points
    t0, t1 = points[0][0], points[-1][0]
    span = (t1 - t0).total_seconds() or 1.0
    buckets: dict[int, list] = {}
    for dt, v in points:
        i = min(n - 1, int((dt - t0).total_seconds() / span * n))
        buckets.setdefault(i, []).append((dt, v))
    out = []
    for i in sorted(buckets):
        vals = buckets[i]
        mid = vals[len(vals) // 2][0]
        out.append((mid, sum(v for _, v in vals) / len(vals)))
    return out


def _out_of_range_minutes(points: list[tuple[datetime, float]],
                          lo: float, hi: float) -> tuple[float, float]:
    """(minutes above hi, minutes below lo) integrated over sample intervals,
    capping gaps so logging holes don't inflate the total."""
    over = under = 0.0
    for (t_a, v_a), (t_b, _v_b) in zip(points, points[1:]):
        dt = min((t_b - t_a).total_seconds(), _MAX_GAP_S)
        if v_a > hi:
            over += dt
        elif v_a < lo:
            under += dt
    return over / 60.0, under / 60.0


def _time_label(dt: datetime, hours: int) -> str:
    local = dt.astimezone()
    return local.strftime("%d %b %H:%M") if hours > 24 else local.strftime("%H:%M")


def build_history(db: Database, state: AppState) -> ft.Container:
    lang = state.language
    timeframe = ["24h"]  # mutable so the selector closure can swap it

    def hours_selected() -> int:
        return next(h for k, _l, h in _TIMEFRAMES if k == timeframe[0])

    # ---- one sensor chart ----------------------------------------------------

    def sensor_chart(points: list[tuple[datetime, float]], sensor_name: str,
                     color: str, fmt: str, tgt: dict | None,
                     hours: int) -> ft.Control:
        title = ft.Text(
            t(f"sensor.name.{sensor_name}", lang),
            size=13, weight=ft.FontWeight.W_600, color=color,
        )
        if len(points) < 2:
            return theme.card(
                col={"xs": 12, "md": 6},
                content=ft.Column(spacing=4, controls=[
                    title,
                    ft.Container(
                        height=_CHART_H, alignment=ft.Alignment.CENTER,
                        content=ft.Text(t("history.empty_chart", lang),
                                        size=12, color=theme.TEXT_MUTED),
                    ),
                ]),
            )

        raw = points
        pts = _downsample(points, _MAX_POINTS)
        values = [v for _, v in pts]
        data_lo, data_hi = min(values), max(values)

        # Y scale anchored to the target band, not the data: the band ± ~25%
        # headroom keeps the line calm; only a real excursion widens the view.
        if tgt:
            t_lo, t_hi = float(tgt["min"]), float(tgt["max"])
            pad = (t_hi - t_lo) * 0.25 or 1.0
            y_lo = min(t_lo - pad, data_lo)
            y_hi = max(t_hi + pad, data_hi)
        else:
            t_lo = t_hi = None
            pad = (data_hi - data_lo) * 0.15 or 1.0
            y_lo, y_hi = data_lo - pad, data_hi + pad
        y_span = (y_hi - y_lo) or 1.0

        t0, t1 = pts[0][0], pts[-1][0]
        t_span = (t1 - t0).total_seconds() or 1.0

        label_style = ft.TextStyle(size=10, color=theme.TEXT_MUTED)
        # Limit lines read as thresholds: dashed red, slightly translucent so
        # the data line stays the loudest mark on the chart.
        limit_color = ft.Colors.with_opacity(0.65, theme.DANGER)
        limit_label_style = ft.TextStyle(
            size=10, color=theme.DANGER, weight=ft.FontWeight.W_600,
        )

        def build_shapes(w: float, h: float) -> list[cv.Shape]:
            plot_w = max(1.0, w - _PAD_L - _PAD_R)
            plot_h = max(1.0, h - _PAD_T - _PAD_B)

            def x_at(dt: datetime) -> float:
                return _PAD_L + (dt - t0).total_seconds() / t_span * plot_w

            def y_at(v: float) -> float:
                return _PAD_T + (1 - (v - y_lo) / y_span) * plot_h

            shapes: list[cv.Shape] = []

            if t_lo is not None:
                band_top, band_bot = y_at(t_hi), y_at(t_lo)
                # In-range band: faint green fill between the min/max guides.
                shapes.append(cv.Rect(
                    x=_PAD_L, y=band_top, width=plot_w,
                    height=band_bot - band_top,
                    paint=ft.Paint(
                        color=ft.Colors.with_opacity(0.08, theme.SUCCESS),
                        style=ft.PaintingStyle.FILL,
                    ),
                ))
                guide = ft.Paint(
                    color=limit_color,
                    stroke_width=1.5, style=ft.PaintingStyle.STROKE,
                    stroke_dash_pattern=[6, 4],
                )
                for yy in (band_top, band_bot):
                    shapes.append(cv.Line(_PAD_L, yy, _PAD_L + plot_w, yy, paint=guide))
                shapes.append(cv.Text(
                    x=_PAD_L - 4, y=band_top, value=fmt.format(t_hi),
                    style=limit_label_style, alignment=ft.Alignment.CENTER_RIGHT,
                ))
                shapes.append(cv.Text(
                    x=_PAD_L - 4, y=band_bot, value=fmt.format(t_lo),
                    style=limit_label_style, alignment=ft.Alignment.CENTER_RIGHT,
                ))
                # Tiny max/min tags at the right end of each limit line.
                shapes.append(cv.Text(
                    x=_PAD_L + plot_w, y=band_top - 2, value="max",
                    style=limit_label_style, alignment=ft.Alignment.BOTTOM_RIGHT,
                ))
                shapes.append(cv.Text(
                    x=_PAD_L + plot_w, y=band_bot + 2, value="min",
                    style=limit_label_style, alignment=ft.Alignment.TOP_RIGHT,
                ))

            # Data line.
            elems: list = [cv.Path.MoveTo(x_at(pts[0][0]), y_at(pts[0][1]))]
            elems += [cv.Path.LineTo(x_at(dt), y_at(v)) for dt, v in pts[1:]]
            shapes.append(cv.Path(elems, paint=ft.Paint(
                color=color, stroke_width=2, style=ft.PaintingStyle.STROKE,
                stroke_cap=ft.StrokeCap.ROUND, stroke_join=ft.StrokeJoin.ROUND,
                anti_alias=True,
            )))

            # Time ticks: start / middle / end.
            mid = t0 + timedelta(seconds=t_span / 2)
            for dt, align in ((t0, ft.Alignment.TOP_LEFT),
                              (mid, ft.Alignment.TOP_CENTER),
                              (t1, ft.Alignment.TOP_RIGHT)):
                shapes.append(cv.Text(
                    x=x_at(dt), y=_PAD_T + plot_h + 4,
                    value=_time_label(dt, hours),
                    style=label_style, alignment=align,
                ))
            return shapes

        canvas = cv.Canvas(height=_CHART_H, expand=True,
                           shapes=[], resize_interval=100)

        def on_resize(e: cv.CanvasResizeEvent):
            canvas.shapes = build_shapes(e.width, e.height)
            canvas.update()

        canvas.on_resize = on_resize

        # Footer: latest value + how long the sensor sat outside the band.
        footer_bits: list[ft.Control] = [
            ft.Text(
                f"now {fmt.format(values[-1])}  ·  "
                f"min {fmt.format(data_lo)} / max {fmt.format(data_hi)}",
                size=11, color=theme.TEXT_MUTED, expand=True,
            ),
        ]
        if tgt:
            over_min, under_min = _out_of_range_minutes(raw, t_lo, t_hi)
            if over_min >= 1:
                footer_bits.append(ft.Text(f"▲ over {over_min:.0f} min",
                                           size=11, color=theme.DANGER))
            if under_min >= 1:
                footer_bits.append(ft.Text(f"▼ under {under_min:.0f} min",
                                           size=11, color=theme.WARNING))
            if over_min < 1 and under_min < 1:
                footer_bits.append(ft.Text("in range", size=11,
                                           color=theme.SUCCESS))

        return theme.card(
            col={"xs": 12, "md": 6},
            content=ft.Column(
                spacing=4,
                controls=[title, canvas, ft.Row(controls=footer_bits)],
            ),
        )

    # ---- charts grid + timeframe selector ------------------------------------

    def build_charts() -> list[ft.Control]:
        hours = hours_selected()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)) \
            .isoformat(timespec="seconds")
        rows = db.readings_since(since)
        targets = state.targets

        by_col: dict[str, list[tuple[datetime, float]]] = {c: [] for c, *_ in _SERIES}
        for r in rows:
            dt = _parse_ts(r["ts"])
            if dt is None:
                continue
            for col, *_ in _SERIES:
                if r[col] is not None:
                    by_col[col].append((dt, r[col]))

        return [
            sensor_chart(by_col[col], name, color, fmt, targets.get(name), hours)
            for col, name, color, fmt in _SERIES
        ]

    charts = ft.ResponsiveRow(spacing=12, run_spacing=12, controls=build_charts())

    def on_timeframe(e):
        selected = list(e.control.selected)
        if not selected:
            return
        timeframe[0] = selected[0]
        charts.controls = build_charts()
        e.control.page.update()

    tf_selector = ft.SegmentedButton(
        segments=[ft.Segment(value=k, label=ft.Text(lbl, size=12))
                  for k, lbl, _h in _TIMEFRAMES],
        selected=[timeframe[0]],
        on_change=on_timeframe,
        allow_multiple_selection=False,
        allow_empty_selection=False,
    )

    # ---- dosing log (unchanged) ----------------------------------------------

    doses = db.recent_doses(limit=30)
    if doses:
        dose_items = [
            ft.Row(
                controls=[
                    ft.Icon(
                        ft.Icons.SMART_TOY if d["source"] == "llm" else ft.Icons.PAN_TOOL,
                        size=16,
                        color="#7E57C2" if d["source"] == "llm" else "#1976D2",
                    ),
                    ft.Text(f"{d['pump']}", size=12, weight=ft.FontWeight.W_600,
                            color=theme.TEXT, expand=True),
                    ft.Text(f"{d['amount']:.1f} ml", size=12, color="#1976D2"),
                    ft.Text(d["ts"].replace("T", " "), size=11, color=theme.TEXT_MUTED),
                ],
            )
            for d in doses
        ]
    else:
        dose_items = [
            ft.Text(t("history.no_doses", lang), size=12, color=theme.TEXT_MUTED)
        ]

    dose_log = theme.card(
        ft.Column(
            spacing=8,
            controls=[
                theme.section_title(t("history.doses_title", lang)),
                *dose_items,
            ],
        ),
    )

    return ft.Container(
        expand=True,
        padding=theme.PAGE_PADDING,
        content=ft.Column(
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                theme.page_header(
                    t("history.title", lang),
                    t("history.subtitle", lang),
                    trailing=[tf_selector],
                ),
                charts,
                dose_log,
            ],
        ),
    )
