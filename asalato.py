"""ドット絵アサラト (Python 3.12 / pygame + numpy 版)

  pip install pygame numpy
  python asalato.py

操作:
  Space / X キー / マウス左ボタン / ゲームパッドのボタン : Xボタン（押している間ホールド）
  C: キャラ切替   M: 音ON/OFF   D: デモ   T: ダーク/ライト   ↑↓: BPM   Esc: 終了
"""
import math
import sys

import numpy as np
import pygame

W, H = 192, 144
K = 128 / 96
SCALE = 4
HUD_H = 120
JOY_X_BUTTON = None  # 特定のボタン番号だけ使いたいときは数値を指定（None なら全ボタン）

# ---------- 色 ----------
WOOD = np.array([[78, 38, 14], [170, 96, 30], [214, 134, 44], [238, 166, 72], [252, 200, 112]], dtype=np.uint8)
SPEC = (255, 232, 170)
FLASH = (255, 214, 90)
INK, BLUSH, TONGUE, WHITE = (58, 28, 14), (248, 150, 112), (232, 84, 96), (255, 255, 255)
CHARS = {
    "asa": dict(name="アサラトくん ♂", short="アサラトくん",
                cord=[(34, 58, 112), (70, 104, 168), (20, 36, 76)], ribbon=False, flower=False, lash=False),
    "pachi": dict(name="パチカちゃん ♀", short="パチカちゃん",
                  cord=[(190, 52, 62), (236, 100, 104), (122, 28, 42)], ribbon=True, flower=True, lash=True),
}

# ---------- 配置（96基準）----------
R = 15
F = (54.0, 54.0)
TH0 = 0.0


def knot_pos(h, th, o=R + 1.5):
    return (h[0] + o * math.cos(th), h[1] + o * math.sin(th))


HP = knot_pos(F, TH0)


def rad(u):
    return 2 * R + 26 * max(0.0, math.sin(math.pi * u)) ** 0.6


# ---------- ピクセルバッファ（arr[x, y]）----------
arr = np.zeros((W, H, 3), dtype=np.uint8)


def put(x, y, c):
    x, y = math.floor(x), math.floor(y)
    if 0 <= x < W and 0 <= y < H:
        arr[x, y] = c


def putv(xs, ys, cols):
    xi = np.floor(xs).astype(int)
    yi = np.floor(ys).astype(int)
    m = (xi >= 0) & (yi >= 0) & (xi < W) & (yi < H)
    c = np.asarray(cols, dtype=np.uint8)
    arr[xi[m], yi[m]] = c[m] if c.ndim == 2 else c


def blend(x, y, c, a):
    if 0 <= x < W and 0 <= y < H:
        arr[x, y] = arr[x, y] * (1 - a) + np.array(c) * a


def hash2(a, b):
    s = np.sin(a * 12.9898 + b * 78.233) * 43758.5453
    return s - np.floor(s)


# ---------- 音 ----------
SR = 44100


class Sound:
    def __init__(self):
        self.on = True
        self.ok = False
        try:
            pygame.mixer.init(SR, -16, 1, 256)
            self.ok = True
        except pygame.error:
            return
        rng = np.random.default_rng(1)
        self.shakes = []
        for _ in range(4):  # シャカッ（高域ノイズの短いバースト）
            n = int(SR * .07)
            t = np.arange(n) / SR
            x = np.diff(rng.uniform(-1, 1, n + 1))
            env = np.minimum(t / .004, 1) * np.exp(-t * 55)
            self.shakes.append(self._snd(x * env * .5))
        self.hits = {b: self._hit(820 if b else 980, rng) for b in (True, False)}

    @staticmethod
    def _snd(x):
        x = np.clip(x, -1, 1)
        return pygame.mixer.Sound(buffer=(x * 32767).astype(np.int16).tobytes())

    def _hit(self, f0, rng):  # カチッ（木のぶつかる音）
        n = int(SR * .14)
        t = np.arange(n) / SR
        tri = 2 / np.pi * np.arcsin(np.sin(2 * np.pi * f0 * t)) * .55 * np.exp(-t * 35)
        sin = np.sin(2 * np.pi * f0 * 2.4 * t) * .25 * np.exp(-t * 90)
        click = np.diff(rng.uniform(-1, 1, n + 1)) * .45 * np.exp(-t * 200)
        return self._snd(tri + sin + click)

    def shake(self, g):
        if self.on and self.ok:
            s = self.shakes[np.random.randint(len(self.shakes))]
            s.set_volume(min(1.0, g * 1.6))
            s.play()

    def hit(self, bottom):
        if self.on and self.ok:
            self.hits[bool(bottom)].play()


# ---------- 顔 ----------
def Rc(x0, y0, x1, y1):
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


EYE_L, EYE_R, EW = Rc(-8, -3, -6, 0), Rc(5, -3, 7, 0), [(-6, -3), (7, -3)]
MOUTH = Rc(-3, 3, 3, 4) + Rc(-2, 5, 2, 5) + Rc(-1, 6, 1, 6)
TONG = Rc(-1, 5, 1, 5) + [(0, 6)]
CHEEK = Rc(-12, 2, -10, 3) + Rc(9, 2, 11, 3)
LASH = [(-10, -2), (-9, -3), (9, -2), (8, -3)]
FACES = {
    "normal": dict(ink=EYE_L + EYE_R + MOUTH, t=TONG, w=EW),
    "blink": dict(ink=Rc(-8, -1, -6, -1) + Rc(5, -1, 7, -1) + MOUTH, t=TONG),
    "fly": dict(ink=Rc(-8, -4, -6, 0) + Rc(5, -4, 7, 0) + [(-1, 4), (0, 4), (1, 4), (-1, 5), (1, 5), (-1, 6), (0, 6), (1, 6)],
                t=[(0, 5)], w=[(-6, -4), (7, -4), (-7, -3), (6, -3)]),
    "hit": dict(ink=[(-9, -4), (-8, -3), (-7, -2), (-8, -1), (-9, 0), (8, -4), (7, -3), (6, -2), (7, -1), (8, 0)] + MOUTH, t=TONG),
    "happy": dict(ink=[(-9, -1), (-8, -2), (-7, -3), (-6, -2), (-5, -1), (4, -1), (5, -2), (6, -3), (7, -2), (8, -1)] + MOUTH, t=TONG),
    "sulk": dict(ink=Rc(-8, -2, -6, 0) + Rc(5, -2, 7, 0) + [(-9, -5), (-8, -4), (-7, -4), (-6, -3), (8, -5), (7, -4), (6, -4), (5, -3),
                                                         (-2, 5), (-1, 5), (0, 4), (1, 5), (2, 5)], w=[(-6, -2), (7, -2)]),
}


def rnd(v):
    return math.floor(v + .5)


def pts(cx, cy, lst, c):
    for p in lst:
        put(cx + p[0], cy + p[1], c)


class App:
    def __init__(self):
        self.snd = Sound()
        self.ch = CHARS["asa"]
        self.dark = False
        self.u = self.hy = self.hv = 0.0
        self.flash = 0.0
        self.flash_y = 0
        self.fs = 9
        self.auto = False
        self.demo_t = 0.0
        self.demo_x = True
        self.hit_text = ""
        self.mode = "hold"  # hold / free / catch
        self.time = 0.0
        self.ph = 0.0
        self.n = 0
        self.bpm = 110
        self.leg = None
        self.catch_leg = None
        self.press_t = None
        self.pending_top = None
        self.x_down = True
        self.face_t = "normal"
        self.face_until = 0.0

    WIN = 0.05

    def d16(self):
        return 60 / self.bpm / 4

    def start_catch(self, T):
        self.mode = "catch"
        self.catch_leg = dict(t0=self.time, T=T, frm=self.u)
        self.pending_top = None
        self.press_t = None

    def set_x(self, down):
        self.x_down = down
        if down:
            self.press_t = self.time
            if self.mode == "free" and self.pending_top is not None and self.time - self.pending_top <= self.WIN:
                self.hit(False, self.time - self.pending_top)
                self.set_face("happy", .5)
                self.start_catch(.06)
        elif self.mode == "hold":
            self.press_t = None
            self.pending_top = None
            self.mode = "free"
            self.leg = dict(t0=self.time, T=2 * self.d16(), frm=0, to=1)

    def set_face(self, t, dur):
        self.face_t, self.face_until = t, self.time + dur

    def hit(self, to_bottom, dt_sec=None):
        self.flash, self.fs, self.flash_y = .14, 9, 1 if to_bottom else -1
        self.hit_text = "カチッ！（下から）" if to_bottom else "カチッ！（上から）"
        if dt_sec is not None:
            self.hit_text += ("  +" if dt_sec >= 0 else "  ") + str(round(dt_sec * 1000)) + "ms"
        self.set_face("hit", .25)
        self.snd.hit(to_bottom)

    @staticmethod
    def swing_ease(t):
        return max(0.0, min(1.0, t)) ** 1.5

    def step(self, dt):
        self.time += dt
        w = 2 * math.pi * (self.bpm / 60) * 2
        self.ph += dt * w
        self.hy = 4.5 * math.sin(self.ph)
        self.hv = 4.5 * math.cos(self.ph) * w
        n = math.floor((self.ph - math.pi / 2) / math.pi)
        if n != self.n:
            self.n = n
            self.snd.shake(.12 if self.mode == "free" else .5)
        if self.pending_top is not None and self.time - self.pending_top > self.WIN:
            self.pending_top = None
        if self.auto:
            self.demo_t += dt
            want = (self.demo_t / (60 / self.bpm * 4)) % 2 < 1
            if want != self.demo_x:
                self.demo_x = want
                if not want:
                    self.set_x(False)
            if self.demo_x and self.mode == "free" and self.leg["to"] == 0 \
                    and self.leg["t0"] + self.leg["T"] - self.time <= 1.5 * dt:
                self.set_x(True)

        if self.mode == "hold":
            self.u = 0.004 * (0.5 + 0.5 * math.cos(2 * self.ph))
        elif self.mode == "free":
            L = self.leg
            tau = (self.time - L["t0"]) / L["T"]
            while tau >= 1:
                arr_t = L["t0"] + L["T"]
                top = L["to"] == 0
                tap_near = self.press_t is not None and abs(self.press_t - arr_t) <= self.WIN
                if top and (self.x_down or tap_near):
                    self.u = 0
                    self.hit(False, self.press_t - arr_t if tap_near else None)
                    self.set_face("happy", .5)
                    self.mode = "hold"
                    self.press_t = None
                    self.pending_top = None
                    break
                self.hit(L["to"] == 1)
                if top and self.press_t is not None:
                    self.set_face("sulk", .7)
                if top:
                    self.pending_top = arr_t
                nf = L["to"]
                L["t0"], L["T"], L["frm"], L["to"] = arr_t, 3 * self.d16(), nf, 1 - nf
                tau = (self.time - L["t0"]) / L["T"]
            if self.mode == "free":
                self.u = L["frm"] + (L["to"] - L["frm"]) * self.swing_ease(tau)
        elif self.mode == "catch":
            C = self.catch_leg
            tau = min(1.0, (self.time - C["t0"]) / C["T"])
            self.u = C["frm"] * (1 - tau * tau * (3 - 2 * tau))
            if tau >= 1:
                self.mode = "hold"
        if self.flash > 0:
            self.flash -= dt

    # ---------- 描画 ----------
    def head_pos(self, u):
        f = -math.pi / 2 + math.pi * u
        r = rad(u)
        return (F[0] + r * math.cos(f), F[1] + self.hy - self.hv * 0.012 + r * math.sin(f))

    def knot_dir(self, h):
        return math.atan2(HP[1] + self.hy - h[1], HP[0] - h[0])

    def face_kind(self):
        if self.time < self.face_until:
            return self.face_t
        if self.mode != "hold":
            return "fly"
        return "blink" if (self.time % 2.8) < 0.12 else "normal"

    def draw_face(self, Hx, Hy, kind):
        f = FACES.get(kind, FACES["normal"])
        cx, cy = rnd(Hx * K), rnd(Hy * K)
        pts(cx, cy, CHEEK, BLUSH)
        pts(cx, cy, f["ink"], INK)
        if "t" in f:
            pts(cx, cy, f["t"], TONGUE)
        if "w" in f:
            pts(cx, cy, f["w"], WHITE)
        if self.ch["lash"]:
            pts(cx, cy, LASH, INK)

    def draw_bow(self, Hx, Hy):
        cx, cy = rnd(Hx * K) - 12, rnd(Hy * K) - 13
        pts(cx, cy, Rc(-5, -3, -2, 2) + Rc(2, -3, 5, 2), (240, 104, 140))
        pts(cx, cy, Rc(-5, -3, -2, -3) + Rc(2, -3, 5, -3), (255, 170, 196))
        pts(cx, cy, Rc(-5, 2, -2, 2) + Rc(2, 2, 5, 2) + Rc(-1, -1, 1, 1), (200, 60, 100))

    def draw_flower(self, Hx, Hy, th):
        cx, cy = rnd(Hx * K - 9 * math.cos(th)), rnd(Hy * K - 9 * math.sin(th))
        pts(cx, cy, Rc(-1, -3, 1, 3) + Rc(-3, -1, 3, 1), (240, 110, 150))
        pts(cx, cy, [(-2, -2), (2, -2), (-2, 2), (2, 2)], (250, 150, 182))
        pts(cx, cy, [(0, 0)], (255, 222, 232))

    def ball(self, Hx, Hy, th, face, deco):
        cs, sn = math.cos(th), math.sin(th)
        g = np.arange(-R - 1, R + 1 + 1e-9, .4)
        lx, ly = np.meshgrid(g, g)
        lx, ly = lx.ravel(), ly.ravel()
        r = np.hypot(lx, ly)
        m = r <= R
        lx, ly, r = lx[m], ly[m], r[m]
        wx, wy = lx * cs - ly * sn, lx * sn + ly * cs
        nx, ny = wx / R, wy / R
        nz = np.sqrt(np.maximum(0, 1 - nx * nx - ny * ny))
        lit = nx * -.45 + ny * -.55 + nz * .7
        idx = np.clip(np.floor(lit * 4.2 + .4).astype(int), 0, 4)
        spec = (lit > .93) & (nz > .5)
        grain = ~spec & (hash2(np.floor(lx * 1.6), np.floor(ly * 1.6)) > .94)
        idx = np.where(grain, np.minimum(4, idx + 1), idx)
        cols = WOOD[idx].copy()
        cols[spec] = SPEC
        cols[r > R - 1.4] = WOOD[0]
        putv((Hx + wx) * K, (Hy + wy) * K, cols)
        if face:
            self.draw_face(Hx, Hy, face)
        if deco == "flower":
            self.draw_flower(Hx, Hy, th)
        if deco == "bow":
            self.draw_bow(Hx, Hy)
        # 結び目
        Kp = knot_pos((Hx, Hy), th, R + .8)
        g = np.arange(-3, 3 + 1e-9, .4)
        x, y = np.meshgrid(g, g)
        x, y = x.ravel(), y.ravel()
        h = np.hypot(x, y)
        m = h <= 2.7
        x, y, h = x[m], y[m], h[m]
        q = hash2(np.floor((x + 4) * 1.2), np.floor((y + 4) * 1.2))
        cc = np.array(self.ch["cord"], dtype=np.uint8)
        cols = np.where((h > 2.1)[:, None], cc[2], np.where((q > .65)[:, None], cc[1], cc[0]))
        putv((Kp[0] + x) * K, (Kp[1] + y) * K, cols)

    def cord(self, A, E):
        dx, dy = E[0] - A[0], E[1] - A[1]
        L = math.hypot(dx, dy) or 1
        nx, ny = dy / L, -dx / L
        if ny > 0:
            nx, ny = -nx, -ny
        sg = (1 - max(0.0, math.sin(math.pi * self.u)) ** 0.6) * 18
        B = (A[0] + dx / 3 + nx * sg, A[1] + dy / 3 + ny * sg)
        C = (A[0] + 2 * dx / 3 + nx * sg, A[1] + 2 * dy / 3 + ny * sg)
        i = np.arange(361)
        t = i / 360
        u = 1 - t
        x = u**3 * A[0] + 3 * u * u * t * B[0] + 3 * u * t * t * C[0] + t**3 * E[0]
        y = u**3 * A[1] + 3 * u * u * t * B[1] + 3 * u * t * t * C[1] + t**3 * E[1]
        cc = np.array(self.ch["cord"], dtype=np.uint8)
        cols = cc[np.where((i // 4) % 2 == 1, 1, 0)]
        for a in range(-1, 3):
            for b in range(-1, 3):
                putv(x * K + a, y * K + b, cols)

    def render(self):
        bg = (26, 29, 36) if self.dark else (246, 243, 238)
        arr[:, :] = bg
        UH = self.head_pos(self.u)
        UT = self.knot_dir(UH)
        # 足もとの影
        sx, sy, rx, ry = (F[0] + 14) * K, 103 * K, 38 * K, 3.4 * K
        sc = np.array((12, 14, 18) if self.dark else (222, 208, 194))
        for y in range(math.floor(sy - ry), math.floor(sy + ry) + 1):
            for x in range(math.floor(sx - rx), math.floor(sx + rx) + 1):
                if ((x - sx) / rx) ** 2 + ((y - sy) / ry) ** 2 <= 1:
                    blend(x, y, sc, .65)
        for i in range(25):  # ガイド
            h = self.head_pos(i / 24)
            blend(math.floor(h[0] * K), math.floor(h[1] * K), (110, 130, 100), .6)
        self.cord((HP[0], HP[1] + self.hy), knot_pos(UH, UT, R + 1.5))
        self.ball(UH[0], UH[1], UT, None, "flower" if self.ch["flower"] else None)
        self.ball(F[0], F[1] + self.hy, TH0, self.face_kind(), "bow" if self.ch["ribbon"] else None)
        if self.flash > 0:
            cx, cy = F[0] * K, (F[1] + self.hy + self.flash_y * R) * K
            for a in range(8):
                gg = a * math.pi / 4
                r = self.fs * .45
                while r < self.fs:
                    put(cx + math.cos(gg) * r * K * .8, cy + math.sin(gg) * r * K * .8, FLASH)
                    r += 1


def pick_font(size, bold=False):
    names = "meiryo,yugothic,msgothic,hiraginosans,notosanscjkjp,notosansjp,takaoexgothic,ipagothic,arialunicodems"
    return pygame.font.SysFont(names, size, bold=bold)


def main():
    pygame.mixer.pre_init(SR, -16, 1, 256)
    pygame.init()
    screen = pygame.display.set_mode((W * SCALE, H * SCALE + HUD_H))
    pygame.display.set_caption("ドット絵アサラト")
    app = App()
    canvas = pygame.Surface((W, H))
    big = pick_font(22, True)
    mid = pick_font(18, True)
    small = pick_font(15)
    clock = pygame.time.Clock()
    for j in range(pygame.joystick.get_count()):
        pygame.joystick.Joystick(j).init()
    is_x = lambda k: k in (pygame.K_SPACE, pygame.K_x)

    running = True
    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif is_x(e.key):
                    app.auto = False
                    app.set_x(True)
                elif e.key == pygame.K_c:
                    app.ch = CHARS["pachi"] if app.ch is CHARS["asa"] else CHARS["asa"]
                elif e.key == pygame.K_m:
                    app.snd.on = not app.snd.on
                elif e.key == pygame.K_t:
                    app.dark = not app.dark
                elif e.key == pygame.K_d:
                    app.auto = not app.auto
                    app.demo_t, app.demo_x = 0.0, True
                    app.set_x(True)
                elif e.key == pygame.K_UP:
                    app.bpm = min(200, app.bpm + 5)
                elif e.key == pygame.K_DOWN:
                    app.bpm = max(60, app.bpm - 5)
            elif e.type == pygame.KEYUP and is_x(e.key):
                app.set_x(False)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                app.auto = False
                app.set_x(True)
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                app.set_x(False)
            elif e.type == pygame.JOYBUTTONDOWN and JOY_X_BUTTON in (None, e.button):
                app.auto = False
                app.set_x(True)
            elif e.type == pygame.JOYBUTTONUP and JOY_X_BUTTON in (None, e.button):
                app.set_x(False)

        dt = min(.02, clock.tick(60) / 1000)
        app.step(dt)
        app.render()

        pygame.surfarray.blit_array(canvas, arr)
        screen.fill((26, 29, 36) if app.dark else (246, 243, 238))
        screen.blit(pygame.transform.scale(canvas, (W * SCALE, H * SCALE)), (0, 0))
        fg = (230, 233, 236) if app.dark else (42, 47, 51)
        sub = (154, 165, 148) if app.dark else (102, 112, 96)
        screen.blit(big.render(app.ch["name"], True, fg), (12, 6))
        if app.flash > 0:
            screen.blit(mid.render(app.hit_text, True, fg), (12, H * SCALE - 30))
        y = H * SCALE + 8
        info = f"BPM {app.bpm} (↑↓)   音: {'ON' if app.snd.on else 'OFF'} (M)   キャラ切替: C   デモ: D{'(実行中)' if app.auto else ''}   テーマ: T"
        for line in (info,
                     "Space/Xキー/クリック（押している間）= ホールド（M球はS球とシェイク）",
                     "離す→8分後に下から衝突、その後16分3つ分ごとに上下交互に衝突",
                     "M球が上に戻った瞬間（前後0.05秒）にXを押していればキャッチ"):
            screen.blit(small.render(line, True, sub), (12, y))
            y += 24
        pygame.display.flip()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
