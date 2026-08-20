#!/usr/bin/env python3
"""Render the Okada demo video to MP4.

Frames are generated with Pillow and piped straight into ffmpeg, so no
intermediate images are ever written to disk.

    .venv/bin/python scripts/make_video.py out.mp4
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1280, 720, 15

BG = (15, 20, 19)
PANEL = (26, 32, 31)
INK = (233, 237, 235)
SOFT = (147, 160, 156)
LINE = (44, 53, 51)
ACCENT = (232, 132, 43)
OK = (59, 184, 119)
DOWN = (224, 97, 83)

SF = "/System/Library/Fonts/SFNS.ttf"
MONO = "/System/Library/Fonts/SFNSMono.ttf"


def font(size, mono=False, weight=None):
    f = ImageFont.truetype(MONO if mono else SF, size)
    if weight is not None and not mono:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


F = {
    "huge": font(76, weight=780), "big": font(46, weight=760),
    "mid": font(30, weight=600), "body": font(24, weight=420),
    "small": font(19, weight=420), "tiny": font(15, weight=500),
    "m": font(16, mono=True), "ms": font(13, mono=True), "mb": font(22, mono=True),
}


def rrect(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def wrap(d, text, f, maxw):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def para(d, text, f, x, y, maxw, fill, lh=1.45):
    for i, ln in enumerate(wrap(d, text, f, maxw)):
        d.text((x, y + i * int(f.size * lh)), ln, font=f, fill=fill)
    return y + len(wrap(d, text, f, maxw)) * int(f.size * lh)


def ease(t):
    return t * t * (3 - 2 * t)


# ── phone ───────────────────────────────────────────────────────────────
PX, PY, PW, PH = 706, 62, 330, 596


def phone(d, pill_text, pill_color, bubbles, chip=None, overlay=None):
    rrect(d, (PX - 6, PY - 6, PX + PW + 6, PY + PH + 6), 34, fill=(8, 11, 10))
    rrect(d, (PX, PY, PX + PW, PY + PH), 28, fill=PANEL, outline=LINE, width=1)

    # header
    d.text((PX + 20, PY + 22), "okada", font=F["mid"], fill=INK)
    wlen = d.textlength("okada", font=F["mid"])
    d.text((PX + 20 + wlen, PY + 22), ".", font=F["mid"], fill=ACCENT)

    pw = d.textlength(pill_text, font=F["ms"]) + 34
    px0 = PX + PW - 20 - pw
    rrect(d, (px0, PY + 26, px0 + pw, PY + 50), 12, fill=(35, 43, 41), outline=LINE)
    d.ellipse((px0 + 11, PY + 34, px0 + 19, PY + 42), fill=pill_color)
    d.text((px0 + 25, PY + 31), pill_text, font=F["ms"], fill=SOFT)
    d.line((PX + 14, PY + 66, PX + PW - 14, PY + 66), fill=LINE)

    y = PY + 84
    for kind, text in bubbles:
        if not text:
            continue
        if kind == "me":
            lines = wrap(d, text, F["small"], PW - 100)
            bh = len(lines) * 26 + 22
            bw = max(d.textlength(l, font=F["small"]) for l in lines) + 30
            x0 = PX + PW - 18 - bw
            rrect(d, (x0, y, x0 + bw, y + bh), 15, fill=(233, 237, 235))
            for i, l in enumerate(lines):
                d.text((x0 + 15, y + 11 + i * 26), l, font=F["small"], fill=(15, 20, 19))
            y += bh + 14
        else:
            lines = wrap(d, text, F["small"], PW - 56)
            for i, l in enumerate(lines):
                d.text((PX + 20, y + i * 26), l, font=F["small"], fill=INK)
            y += len(lines) * 26 + 12

    if chip:
        label, col = chip
        cw = d.textlength(label, font=F["ms"]) + 34
        rrect(d, (PX + 18, y, PX + 18 + cw, y + 24), 12, fill=(35, 43, 41))
        d.ellipse((PX + 29, y + 8, PX + 37, y + 16), fill=col)
        d.text((PX + 43, y + 5), label, font=F["ms"], fill=SOFT)

    # composer
    rrect(d, (PX + 16, PY + PH - 62, PX + PW - 16, PY + PH - 18), 22,
          fill=(15, 20, 19), outline=LINE)
    d.text((PX + 34, PY + PH - 50), "Message Okada…", font=F["small"], fill=(80, 92, 88))
    rrect(d, (PX + PW - 60, PY + PH - 56, PX + PW - 24, PY + PH - 24), 16, fill=ACCENT)

    if overlay:
        rrect(d, (PX + 30, PY + PH // 2 - 46, PX + PW - 30, PY + PH // 2 + 46), 14,
              fill=(30, 12, 10), outline=DOWN, width=2)
        tw = d.textlength(overlay, font=F["mid"])
        d.text((PX + PW // 2 - tw / 2, PY + PH // 2 - 18), overlay, font=F["mid"], fill=DOWN)


def chrome(d, t_total, t_now, label):
    d.text((72, 40), "okada", font=F["tiny"], fill=SOFT)
    d.text((72 + d.textlength("okada", font=F["tiny"]), 40), ".", font=F["tiny"], fill=ACCENT)
    d.text((W - 72 - d.textlength(label, font=F["ms"]), 40), label, font=F["ms"], fill=SOFT)
    d.line((72, H - 40, W - 72, H - 40), fill=LINE, width=3)
    p = max(0.0, min(1.0, t_now / t_total))
    d.line((72, H - 40, 72 + (W - 144) * p, H - 40), fill=ACCENT, width=3)


# ── scenes ──────────────────────────────────────────────────────────────
def s_title(d, p):
    if p < 0.34:
        a = ease(min(1, p / 0.18))
        col = tuple(int(BG[i] + (INK[i] - BG[i]) * a) for i in range(3))
        para(d, "Nigeria recorded 27,000 fibre cuts last year.", F["big"], 150, 260, 980, col)
        d.text((150, 400), "Grid power fails about 190 days a year.", font=F["mid"], fill=SOFT)
    elif p < 0.68:
        para(d, "Every AI application assumes the internet is working.",
             F["big"], 150, 250, 980, INK)
        d.text((150, 400), "When it isn't, they show a spinner and die.", font=F["mid"], fill=DOWN)
    else:
        a = ease(min(1, (p - 0.68) / 0.2))
        col = tuple(int(BG[i] + (INK[i] - BG[i]) * a) for i in range(3))
        acc = tuple(int(BG[i] + (ACCENT[i] - BG[i]) * a) for i in range(3))
        tw = d.textlength("okada", font=F["huge"])
        d.text((W / 2 - tw / 2 - 14, 280), "okada", font=F["huge"], fill=col)
        d.text((W / 2 - tw / 2 - 14 + tw, 280), ".", font=F["huge"], fill=acc)
        sub = "AI that answers whatever the network does"
        d.text((W / 2 - d.textlength(sub, font=F["mid"]) / 2, 400), sub, font=F["mid"], fill=SOFT)


def caption(d, head, body, note=None):
    d.text((90, 210), head, font=F["big"], fill=INK)
    y = para(d, body, F["body"], 90, 300, 540, SOFT)
    if note:
        d.text((90, y + 24), note, font=F["m"], fill=ACCENT)


def s_cloud(d, p):
    caption(d, "Good connection", "Okada sends the question to the full cloud model. "
            "Exactly what a normal app would do.", "route: full cloud model · 340ms")
    typed = "What's the fee on a 50,000 naira transfer?"
    n = int(len(typed) * min(1, p / 0.3))
    ans = "The transfer fee is 250 naira for amounts between 50,001 and 100,000."
    bub = [("me", typed[:n])]
    chip = None
    if p > 0.45:
        an = int(len(ans) * min(1, (p - 0.45) / 0.4))
        bub.append(("bot", ans[:an]))
        if p > 0.82:
            chip = ("cloud · 340ms", OK)
    phone(d, "excellent", OK, bub, chip)


def s_degraded(d, p):
    caption(d, "The network degrades", "Okada notices the latency climbing and drops to a "
            "smaller, cheaper model. Fewer bytes over an expensive link.",
            "route: small cloud model")
    bub = [("me", "What does error 51 mean?")]
    chip = None
    if p > 0.35:
        ans = "Error 51 means insufficient funds in the sender's account."
        an = int(len(ans) * min(1, (p - 0.35) / 0.4))
        bub.append(("bot", ans[:an]))
        if p > 0.8:
            chip = ("cloud · small", OK)
    phone(d, "3g  680ms", ACCENT, bub, chip)


def s_offline(d, p):
    caption(d, "Now the network dies", "Nobody tells Okada. It detects the dead link from its "
            "own probes in about six seconds, and answers from a model on the device.",
            "route: on-device · no network used")
    if p < 0.22:
        phone(d, "offline", DOWN, [], None, overlay="WI-FI OFF")
        return
    q = "Draft an SMS: delivery delayed but on the way."
    bub = [("me", q)]
    chip = None
    if p > 0.45:
        ans = "\"Sorry, your package is delayed, but it's on its way.\""
        an = int(len(ans) * min(1, (p - 0.45) / 0.35))
        bub.append(("bot", ans[:an]))
        if p > 0.78:
            chip = ("on-device · 2.1s", ACCENT)
    phone(d, "offline", DOWN, bub, chip)


def s_work(d, p):
    d.text((90, 170), "Real work, with no internet", font=F["big"], fill=INK)
    para(d, "Still offline, we asked it to study a fragrance brand and write a "
         "seven-section launch plan for its first collection.", F["body"], 90, 250, 540, SOFT)
    stats = [("6s", "to detect the dead link"), ("82s", "to write the report"),
             ("623", "tokens generated on-device"), ("0", "bytes of network used")]
    for i, (n, l) in enumerate(stats):
        if p > 0.25 + i * 0.13:
            x, y = 90 + (i % 2) * 270, 400 + (i // 2) * 110
            d.text((x, y), n, font=F["big"], fill=ACCENT)
            d.text((x, y + 56), l, font=F["m"], fill=SOFT)
    lines = ["Dropping the First Collection", "", "1. Positioning statement",
             "2. Drop format and timing", "3. Scarcity and pricing",
             "4. Pre-launch waitlist", "5. Launch week, day by day",
             "6. Imagery direction", "7. Risks and mitigations"]
    rrect(d, (PX, PY, PX + PW, PY + PH), 28, fill=PANEL, outline=LINE)
    shown = int(len(lines) * min(1, p / 0.7))
    for i, ln in enumerate(lines[:shown]):
        d.text((PX + 26, PY + 40 + i * 34), ln, font=F["m"] if i else F["small"],
               fill=INK if i == 0 else SOFT)


def s_queue(d, p):
    caption(d, "Nothing is ever lost", "Some questions need live data and can't be answered "
            "locally. Okada writes them to disk and delivers them the moment the link returns.",
            "route: queued → synced automatically")
    bub = [("me", "Reconcile today's takings.")]
    chip = ("queued · will sync", DOWN)
    pill, pc = "offline", DOWN
    if p > 0.55:
        pill, pc = "excellent", OK
        bub.append(("bot", "Today's takings: 412,500 naira across 38 transactions."))
        chip = ("synced automatically", OK)
    phone(d, pill, pc, bub, chip)


def s_close(d, p):
    d.text((90, 150), "Measured, not claimed", font=F["big"], fill=INK)
    rows = [("A normal app", "69.6%", DOWN), ("The same app through Okada", "100%", OK)]
    for i, (lbl, val, col) in enumerate(rows):
        if p > 0.12 + i * 0.16:
            y = 260 + i * 92
            d.text((90, y), lbl, font=F["body"], fill=SOFT)
            d.text((90, y + 34), val, font=F["big"], fill=col)
    if p > 0.45:
        d.text((90, 460), "requests answered across seven network conditions",
               font=F["m"], fill=SOFT)
    if p > 0.6:
        a = ease(min(1, (p - 0.6) / 0.25))
        col = tuple(int(BG[i] + (INK[i] - BG[i]) * a) for i in range(3))
        acc = tuple(int(BG[i] + (ACCENT[i] - BG[i]) * a) for i in range(3))
        tw = d.textlength("okada", font=F["big"])
        d.text((PX + PW / 2 - tw / 2 - 8, 250), "okada", font=F["big"], fill=col)
        d.text((PX + PW / 2 - tw / 2 - 8 + tw, 250), ".", font=F["big"], fill=acc)
        for i, ln in enumerate(["Cloud when you have it.", "On-device when you don't.",
                                "Queued when there's nothing."]):
            d.text((PX + 10, 330 + i * 34), ln, font=F["m"], fill=SOFT)
        d.text((PX + 10, 460), "github.com/demimadeit/okada-router", font=F["ms"], fill=ACCENT)


SCENES = [
    (s_title, 13, "0:00"), (s_cloud, 16, "0:13"), (s_degraded, 15, "0:29"),
    (s_offline, 22, "0:44"), (s_work, 20, "1:06"), (s_queue, 17, "1:26"),
    (s_close, 17, "1:43"),
]


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "okada-demo.mp4")
    total = sum(s[1] for s in SCENES)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-pix_fmt", "yuv420p", str(out)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    elapsed = 0.0
    for fn, dur, tc in SCENES:
        for i in range(int(dur * FPS)):
            p = i / (dur * FPS)
            img = Image.new("RGB", (W, H), BG)
            d = ImageDraw.Draw(img)
            fn(d, p)
            chrome(d, total, elapsed + p * dur, tc)
            # short cross-fade to black at scene edges
            k = min(p, 1 - p)
            if k < 0.03:
                ov = Image.new("RGB", (W, H), BG)
                img = Image.blend(img, ov, 1 - k / 0.03)
            proc.stdin.write(img.tobytes())
        elapsed += dur
        print(f"  rendered {tc} ({dur}s)", flush=True)

    proc.stdin.close()
    proc.wait()
    print(f"done: {out} ({total}s)")


if __name__ == "__main__":
    main()
