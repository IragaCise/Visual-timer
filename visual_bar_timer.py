#!/usr/bin/env python3
"""Visual Bar Timer — Windows/macOS Tkinter focus timer (standard library only)."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import wave
from array import array
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

BG = '#eef0ec'
INK = '#20292a'
MUTED = '#6d7875'
PALE = '#aab6b2'
ACCENT = '#276d65'
APP_NAME = 'Visual Bar Timer'
CONFIG = Path.home() / '.visual_bar_timer.json'
SOUNDS = {'なし': None, 'システムベル': 'bell', 'Glass': 'Glass', 'Ping': 'Ping', 'Hero': 'Hero', 'Pop': 'Pop', 'Submarine': 'Submarine', '音楽ファイル': 'file'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac', '.wma', '.aiff', '.aif', '.mid', '.midi'}


class AudioPlayer:
    """外部音声を再生する。pygameがあれば優先、なければOSの機能で再生。"""

    def __init__(self):
        self.backend = None
        self.process = None
        self.mci_alias = 'VisualBarTimerAudio'
        self.pygame = None
        self.mci = None

    def stop(self):
        if self.backend == 'pygame' and self.pygame:
            try:
                self.pygame.mixer.music.stop()
            except Exception:
                pass
        elif self.backend == 'mci' and self.mci:
            try:
                self._mci('stop ' + self.mci_alias)
                self._mci('close ' + self.mci_alias)
            except OSError:
                pass
        elif self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
        self.process = None
        self.backend = None

    def _mci(self, command):
        import ctypes
        if self.mci is None:
            self.mci = ctypes.windll.winmm.mciSendStringW
        buffer = ctypes.create_unicode_buffer(512)
        code = self.mci(command, buffer, len(buffer), 0)
        if code:
            error = ctypes.create_unicode_buffer(512)
            ctypes.windll.winmm.mciGetErrorStringW(code, error, len(error))
            raise OSError(error.value or f'Windows音声エラー: {code}')
        return buffer.value

    def play_file(self, path):
        path = Path(path).expanduser()
        if not path.is_file():
            raise FileNotFoundError('音楽ファイルが見つかりません。もう一度選択してください。')
        self.stop()
        failures = []

        # pygameがインストールされていればMP3 / OGG / WAV等を再生できる。
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            self.pygame = pygame
            self.backend = 'pygame'
            return
        except Exception as exc:
            failures.append(f'pygame: {exc}')

        if sys.platform == 'win32':
            # Windows標準のMCI: 主にMP3/WAV/WMA/MIDIを追加ライブラリなしで再生。
            try:
                self._mci(f'open "{str(path).replace(chr(34), "")}" alias {self.mci_alias}')
                try:
                    self._mci(f'play {self.mci_alias} from 0')
                except OSError:
                    self._mci(f'close {self.mci_alias}')
                    raise
                self.backend = 'mci'
                return
            except (OSError, AttributeError) as exc:
                failures.append(f'Windows標準プレイヤー: {exc}')
        elif sys.platform == 'darwin':
            try:
                self.process = subprocess.Popen(
                    ['/usr/bin/afplay', str(path)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self.backend = 'process'
                return
            except OSError as exc:
                failures.append(f'afplay: {exc}')

        # ffplayが入っていればM4Aなど幅広い形式に対応できる。
        import shutil
        ffplay = shutil.which('ffplay')
        if ffplay:
            try:
                self.process = subprocess.Popen(
                    [ffplay, '-nodisp', '-autoexit', '-loglevel', 'quiet', str(path)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self.backend = 'process'
                return
            except OSError as exc:
                failures.append(f'ffplay: {exc}')
        raise RuntimeError(
            'この形式を再生できません。MP3やWAVを試すか、'
            '「python -m pip install pygame」を実行してください。 ' +
            ' / '.join(failures[-2:])
        )


class VisualBarTimer:
    def __init__(self, root):
        self.root = root
        self.settings = self.load_settings()
        self.goal = tk.StringVar(value=self.settings.get('goal', ''))
        self.minutes = tk.StringVar(value=str(self.settings.get('minutes', '30')))
        self.focus_minutes = tk.StringVar(value=str(self.settings.get('focus', 25)))
        self.short_minutes = tk.StringVar(value=str(self.settings.get('short', 5)))
        self.long_minutes = tk.StringVar(value=str(self.settings.get('long', 15)))
        self.cycles = tk.StringVar(value=str(self.settings.get('cycles', 4)))
        self.sound = tk.StringVar(value=self.settings.get('sound', 'Glass'))
        self.music_file = tk.StringVar(value=self.settings.get('music_file', ''))
        self.audio = AudioPlayer()
        self.save_job = None
        self.tick_job = None
        if self.sound.get() not in SOUNDS:
            self.sound.set('Glass')
        self.pomodoro = tk.BooleanVar(value=bool(self.settings.get('pomodoro', False)))
        self.topmost = tk.BooleanVar(value=bool(self.settings.get('topmost', False)))
        self.controls_visible = bool(self.settings.get('controls_visible', True))
        self.phase = '集中'
        self.completed_focus = 0
        self.total = 30 * 60.0
        try:
            self.total = self.valid_minutes(self.minutes.get()) * 60
        except (ValueError, OverflowError):
            self.minutes.set('30')
        self.remaining = self.total
        self.deadline = None
        self.running = False
        self.status = tk.StringVar(value='時間を決めてスタート')
        self.phase_text = tk.StringVar(value='通常タイマー')

        root.title(APP_NAME)
        root.geometry('940x540')
        root.minsize(760, 500)
        root.configure(bg=BG)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.outer = tk.Frame(root, bg=BG, padx=17, pady=13)
        self.outer.pack(fill='both', expand=True)
        self.top = tk.Frame(self.outer, bg=BG)
        self.top.pack(fill='x', pady=(0, 8))
        tk.Label(self.top, text='VISUAL BAR TIMER', font=('Helvetica', 11, 'bold'), bg=BG, fg=INK).pack(side='left')
        tk.Button(self.top, text='操作を隠す  ⌃', command=self.toggle_controls, relief='flat', bg='#dbe1dd', fg=INK, padx=12).pack(side='right')
        self.hide_btn = self.top.winfo_children()[-1]
        self.phase_label = tk.Label(self.top, textvariable=self.phase_text, bg=BG, fg=ACCENT, font=('Helvetica', 11, 'bold'))
        self.phase_label.pack(side='right', padx=15)

        self.display_area = tk.Frame(self.outer, bg=BG, height=145)
        self.display_area.pack(fill='x')
        self.display_area.pack_propagate(False)
        self.canvas = tk.Canvas(self.display_area, height=125, bg=BG, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.draw())

        # 目標はバー上に描画せず、必ず別の高さを持つ行に表示する。
        # この行をCanvasと操作パネルの間に置くことで、窓の大きさにかかわらず
        # 目標が残り時間バーに重なることはない。
        self.goal_line = tk.Frame(self.outer, bg=BG, height=31)
        self.goal_line.pack(fill='x', pady=(4, 0))
        self.goal_line.pack_propagate(False)
        self.goal_caption = tk.Label(self.goal_line, text='目標', bg=BG, fg=ACCENT,
                                     font=('Helvetica', 10, 'bold'))
        self.goal_caption.pack(side='left', padx=(7, 10))
        self.goal_preview = tk.StringVar()
        self.goal_display = tk.Label(self.goal_line, textvariable=self.goal_preview,
                                     bg=BG, fg=INK, anchor='w',
                                     font=('Helvetica', 11))
        self.goal_display.pack(side='left', fill='x', expand=True)
        self.goal.trace_add('write', self.refresh_goal_preview)
        self.refresh_goal_preview()

        self.controls = tk.Frame(self.outer, bg=BG)
        self.controls.pack(fill='x', pady=(12, 0))
        row1 = tk.Frame(self.controls, bg=BG)
        row1.pack(fill='x')
        for m in (5, 15, 25, 30, 45, 60):
            tk.Button(row1, text=f'{m}分', command=lambda n=m: self.set_minutes(n), bg='#dce2de', fg=INK, relief='flat', padx=8).pack(side='left', padx=(0, 5))
        self.minute_entry = tk.Entry(row1, width=5, textvariable=self.minutes, justify='center')
        self.minute_entry.pack(side='left', padx=(6, 3))
        self.minute_entry.bind('<Return>', lambda e: self.apply_minutes())
        tk.Label(row1, text='分', bg=BG, fg=INK).pack(side='left')
        tk.Button(row1, text='設定', command=self.apply_minutes, padx=7).pack(side='left', padx=(5, 12))
        # macOS/Aquaではtk.Buttonのbgが無視されることがあり、白いfgだけ残って
        # ボタンが空白に見えてしまう。Macのみ標準のttkボタンを使用し、
        # OS側に背景色と文字色を一括して決めてもらう。
        if sys.platform == 'darwin':
            self.start_btn = ttk.Button(row1, text='▶ スタート', command=self.toggle)
            self.reset_btn = ttk.Button(row1, text='↺ リセット', command=self.reset)
        else:
            self.start_btn = tk.Button(row1, text='▶ スタート', command=self.toggle,
                                       bg=INK, fg='white', padx=11)
            self.reset_btn = tk.Button(row1, text='↺ リセット', command=self.reset)
        self.start_btn.pack(side='left', padx=(0, 5))
        self.reset_btn.pack(side='left')

        row2 = tk.Frame(self.controls, bg=BG)
        row2.pack(fill='x', pady=(12, 0))
        tk.Label(row2, text='目標', bg=BG, fg=INK).pack(side='left')
        tk.Entry(row2, textvariable=self.goal, width=38).pack(side='left', padx=(7, 15), fill='x', expand=True)
        tk.Label(row2, text='終了音', bg=BG, fg=INK).pack(side='left')
        ttk.Combobox(row2, textvariable=self.sound, values=list(SOUNDS), state='readonly', width=11).pack(side='left', padx=7)
        tk.Button(row2, text='試聴', command=self.play_sound).pack(side='left')
        tk.Button(row2, text='■ 停止', command=self.stop_sound).pack(side='left', padx=(5, 0))

        file_row = tk.Frame(self.controls, bg=BG)
        file_row.pack(fill='x', pady=(6, 0))
        tk.Button(file_row, text='♪ 音楽ファイルを選ぶ…', command=self.choose_music_file).pack(side='left')
        self.music_label = tk.Label(file_row, textvariable=self.music_file, bg=BG, fg=MUTED,
                                    anchor='w', font=('Helvetica', 9))
        self.music_label.pack(side='left', padx=9, fill='x', expand=True)

        row3 = tk.Frame(self.controls, bg=BG)
        row3.pack(fill='x', pady=(12, 0))
        tk.Checkbutton(row3, text='ポモドーロ（集中 → 休憩を自動切替）', variable=self.pomodoro, command=self.change_mode, bg=BG, fg=INK).pack(side='left')
        for label, var, width in [('集中', self.focus_minutes, 4), ('短休憩', self.short_minutes, 4), ('長休憩', self.long_minutes, 4), ('長休憩まで', self.cycles, 3)]:
            tk.Label(row3, text=label, bg=BG, fg=INK).pack(side='left', padx=(9, 3))
            tk.Entry(row3, textvariable=var, width=width, justify='center').pack(side='left')
        tk.Label(row3, text='回', bg=BG, fg=INK).pack(side='left')
        tk.Button(row3, text='適用', command=self.apply_pomodoro).pack(side='left', padx=8)

        self.bottom = tk.Frame(self.outer, bg=BG)
        self.bottom.pack(fill='x', pady=(10, 0))
        tk.Label(self.bottom, textvariable=self.status, bg=BG, fg=MUTED, anchor='w').pack(side='left')
        tk.Checkbutton(self.bottom, text='常に手前に表示', variable=self.topmost, command=self.update_topmost, bg=BG, fg=INK).pack(side='right')
        self.update_topmost()
        if self.pomodoro.get():
            self.apply_pomodoro()
        if not self.controls_visible:
            self.controls_visible = True
            self.toggle_controls()
        for variable in (self.goal, self.minutes, self.focus_minutes, self.short_minutes,
                         self.long_minutes, self.cycles, self.sound, self.music_file,
                         self.pomodoro, self.topmost):
            variable.trace_add('write', self.schedule_save)
        root.bind('<space>', self.on_space)
        root.bind('<Escape>', lambda e: self.reset())
        root.bind('<Command-h>', lambda e: self.toggle_controls())
        root.bind('<Control-h>', lambda e: self.toggle_controls())
        self.tick()

    def refresh_goal_preview(self, *args):
        goal = self.goal.get().strip()
        self.goal_preview.set(goal if goal else '（未設定）')
        self.goal_display.configure(fg=INK if goal else MUTED)

    def load_settings(self):
        try:
            data = json.loads(CONFIG.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def settings_dict(self):
        return {
            'goal': self.goal.get(), 'minutes': self.minutes.get(),
            'focus': self.focus_minutes.get(), 'short': self.short_minutes.get(),
            'long': self.long_minutes.get(), 'cycles': self.cycles.get(),
            'sound': self.sound.get(), 'music_file': self.music_file.get(),
            'pomodoro': self.pomodoro.get(), 'topmost': self.topmost.get(),
            'controls_visible': self.controls_visible,
        }

    def schedule_save(self, *args):
        if self.save_job is not None:
            self.root.after_cancel(self.save_job)
        self.save_job = self.root.after(400, self.save_settings)

    def save_settings(self):
        self.save_job = None
        try:
            CONFIG.parent.mkdir(parents=True, exist_ok=True)
            staging = CONFIG.with_suffix('.tmp')
            staging.write_text(json.dumps(self.settings_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
            staging.replace(CONFIG)
        except OSError as exc:
            self.status.set(f'設定を保存できませんでした: {exc}')

    def close(self):
        if self.save_job is not None:
            self.root.after_cancel(self.save_job)
            self.save_job = None
        if self.tick_job is not None:
            self.root.after_cancel(self.tick_job)
            self.tick_job = None
        self.save_settings()
        self.audio.stop()
        self.root.destroy()

    def choose_music_file(self):
        path = filedialog.askopenfilename(
            parent=self.root, title='終了時に再生する音楽ファイルを選択',
            filetypes=[('音楽・音声ファイル', '*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.wma *.aiff *.aif *.mid *.midi'),
                       ('すべてのファイル', '*.*')]
        )
        if path:
            self.music_file.set(path)
            self.sound.set('音楽ファイル')
            self.status.set(f'終了音に設定しました: {Path(path).name}')
            self.schedule_save()

    def stop_sound(self):
        self.audio.stop()
        self.status.set('音声再生を停止しました')

    def on_space(self, event):
        if isinstance(event.widget, (tk.Entry, ttk.Combobox)):
            return
        self.toggle()

    def toggle_controls(self):
        """操作パネルの開閉。Tkのpack順序を常に明示して復元する。"""
        self.controls_visible = not self.controls_visible
        if self.controls_visible:
            # 非表示中のself.bottomをbefore=で指定するとTclErrorになる。
            # 常に表示されているgoal_lineを起点に、パネル→ステータスの順で配置する。
            self.controls.pack(fill='x', pady=(12, 0), after=self.goal_line)
            self.bottom.pack(fill='x', pady=(10, 0), after=self.controls)
            self.hide_btn.configure(text='操作を隠す  ⌃')
            self.root.minsize(760, 500)
            self.root.geometry(f'{max(self.root.winfo_width(), 940)}x540')
        else:
            self.controls.pack_forget()
            self.bottom.pack_forget()
            self.hide_btn.configure(text='操作を表示  ⌄')
            self.root.minsize(520, 240)
            self.root.geometry(f'{max(520, self.root.winfo_width())}x260')
        self.root.after_idle(self.draw)
        self.schedule_save()

    def update_topmost(self):
        self.root.attributes('-topmost', self.topmost.get())

    def valid_minutes(self, value):
        n = float(value)
        if not math.isfinite(n) or not 0 < n <= 1440:
            raise ValueError
        return n

    def set_minutes(self, m):
        self.pomodoro.set(False)
        self.phase_text.set('通常タイマー')
        self.minutes.set(str(m))
        self.total = m * 60.0
        self.reset()

    def apply_minutes(self):
        try:
            self.total = self.valid_minutes(self.minutes.get()) * 60
        except (ValueError, OverflowError):
            self.status.set('時間は0より大きく1440分以下で入力してください')
            return
        self.pomodoro.set(False)
        self.phase_text.set('通常タイマー')
        self.reset()

    def pomodoro_config(self):
        focus = self.valid_minutes(self.focus_minutes.get())
        short = self.valid_minutes(self.short_minutes.get())
        long = self.valid_minutes(self.long_minutes.get())
        cycles = int(self.cycles.get())
        if not 1 <= cycles <= 100:
            raise ValueError
        return focus, short, long, cycles

    def change_mode(self):
        if self.pomodoro.get():
            self.apply_pomodoro()
        else:
            self.phase_text.set('通常タイマー')
            self.apply_minutes()

    def apply_pomodoro(self):
        try:
            focus, _, _, _ = self.pomodoro_config()
        except (ValueError, OverflowError):
            self.status.set('集中・休憩は0〜1440分、回数は1〜100の整数で指定してください')
            self.pomodoro.set(False)
            return
        self.pomodoro.set(True)
        self.completed_focus = 0
        self.phase = '集中'
        self.phase_text.set('ポモドーロ · 集中 1回目')
        self.total = focus * 60
        self.reset()

    def reset(self):
        self.audio.stop()
        self.running = False
        self.remaining = self.total
        self.deadline = None
        self.start_btn.configure(text='▶ スタート')
        self.status.set('準備完了')
        self.draw()

    def toggle(self):
        if not self.running:
            self.audio.stop()
        if self.running:
            self.remaining = max(0.0, self.deadline - time.monotonic())
            self.running = False
            self.start_btn.configure(text='▶ 再開')
            self.status.set('一時停止中')
        else:
            if self.remaining <= 0:
                self.remaining = self.total
            self.deadline = time.monotonic() + self.remaining
            self.running = True
            self.start_btn.configure(text='Ⅱ 一時停止')
            self.status.set('集中中…' if self.phase == '集中' or not self.pomodoro.get() else '休憩中…')
        self.draw()

    def tick(self):
        if self.running:
            self.remaining = max(0, self.deadline - time.monotonic())
            if self.remaining <= 0:
                self.running = False
                self.remaining = 0
                self.on_finished()
        self.draw()
        self.tick_job = self.root.after(100, self.tick)

    def on_finished(self):
        self.play_sound()
        if self.pomodoro.get():
            try:
                focus, short, long, cycles = self.pomodoro_config()
            except (ValueError, OverflowError):
                self.status.set('設定値が不正です。ポモドーロを再設定してください')
                self.start_btn.configure(text='▶ スタート')
                return
            if self.phase == '集中':
                self.completed_focus += 1
                is_long = self.completed_focus % cycles == 0
                self.phase = '長休憩' if is_long else '短休憩'
                self.total = (long if is_long else short) * 60
                self.phase_text.set(f'ポモドーロ · {self.phase}')
            else:
                self.phase = '集中'
                self.total = focus * 60
                self.phase_text.set(f'ポモドーロ · 集中 {self.completed_focus + 1}回目')
            self.remaining = self.total
            self.deadline = time.monotonic() + self.total
            self.running = True
            self.start_btn.configure(text='Ⅱ 一時停止')
            self.status.set(f'{self.phase}を自動開始しました')
            self.notify(f'{self.phase}を開始します')
        else:
            self.start_btn.configure(text='▶ もう一度')
            self.status.set('時間になりました！')
            self.notify('設定した時間が終了しました')

    @staticmethod
    def make_windows_sound(name):
        """Windows用のオリジナルWAVを標準ライブラリだけで生成する。"""
        # (開始時刻[秒], 周波数[Hz], 長さ[秒], 相対音量) のセット。
        melodies = {
            'Glass': [(0.00, 880, .35, .45), (.08, 1320, .43, .23),
                      (.18, 1760, .52, .11)],
            'Ping': [(0.00, 1046.5, .35, .58)],
            'Hero': [(0.00, 523.25, .17, .45), (.19, 659.25, .17, .45),
                     (.38, 783.99, .20, .47), (.60, 1046.5, .45, .58)],
            'Pop': [(0.00, 392.0, .12, .60), (.09, 261.63, .13, .40)],
            'Submarine': [(0.00, 440.0, .24, .48), (.30, 349.23, .24, .48),
                          (.60, 293.66, .36, .52)],
        }
        if name not in melodies:
            raise ValueError(f'不明なサウンド名: {name}')
        rate = 22050
        notes = melodies[name]
        duration = max(start + length for start, _, length, _ in notes) + .045
        samples = array('h', [0]) * int(duration * rate)
        for start, freq, length, volume in notes:
            pos = int(start * rate)
            count = int(length * rate)
            for i in range(count):
                t = i / rate
                # クリック音の出ない滑らかな立ち上がりと減衰。
                attack = min(1.0, t / .012)
                decay = (1.0 - t / length) ** 2
                env = attack * decay
                if name == 'Pop':
                    # 短く丸いポップ音。音程を少しだけ下降させる。
                    phase = 2 * math.pi * (freq * t - 0.22 * freq * t * t / length)
                    signal = math.sin(phase)
                elif name == 'Glass':
                    signal = (math.sin(2 * math.pi * freq * t)
                              + .24 * math.sin(2 * math.pi * freq * 2.01 * t)) / 1.24
                elif name == 'Submarine':
                    signal = (math.sin(2 * math.pi * freq * t)
                              + .18 * math.sin(2 * math.pi * freq * .5 * t)) / 1.18
                else:
                    signal = math.sin(2 * math.pi * freq * t)
                idx = pos + i
                if idx < len(samples):
                    mixed = samples[idx] + int(23500 * volume * env * signal)
                    samples[idx] = max(-32768, min(32767, mixed))
        sound_dir = Path(tempfile.gettempdir()) / 'visual_bar_timer_wav_v2'
        sound_dir.mkdir(parents=True, exist_ok=True)
        destination = sound_dir / f'{name}.wav'
        if not destination.exists():
            with wave.open(str(destination), 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(rate)
                if sys.byteorder != 'little':
                    samples.byteswap()
                audio.writeframes(samples.tobytes())
        return destination

    def play_sound(self):
        choice = SOUNDS.get(self.sound.get())
        if choice is None:
            return
        if choice == 'file':
            try:
                if not self.music_file.get():
                    self.status.set('「音楽を選択…」から音楽ファイルを設定してください')
                    return
                self.audio.play_file(self.music_file.get())
            except (OSError, RuntimeError, ValueError) as exc:
                self.status.set('音楽ファイルの再生に失敗しました')
                messagebox.showerror('終了音の再生エラー', str(exc), parent=self.root)
            return
        self.audio.stop()
        if choice == 'bell':
            self.root.bell()
            return
        if sys.platform == 'win32':
            try:
                import winsound
                path = self.make_windows_sound(choice)
                winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                return
            except (OSError, RuntimeError, ValueError) as exc:
                self.status.set(f'終了音を再生できませんでした: {exc}')
                self.root.bell()
                return
        if sys.platform == 'darwin':
            sound_path = f'/System/Library/Sounds/{choice}.aiff'
            if os.path.isfile(sound_path):
                try:
                    subprocess.Popen(['/usr/bin/afplay', sound_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
                except OSError:
                    pass
        self.root.bell()

    def notify(self, message):
        if sys.platform == 'darwin':
            try:
                safe_message = message.replace('\\', '\\\\').replace('"', '\\"')
                subprocess.Popen(['/usr/bin/osascript', '-e', f'display notification "{safe_message}" with title "Visual Bar Timer"'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass

    def draw(self):
        c = self.canvas
        c.delete('all')
        w, h = max(c.winfo_width(), 160), max(c.winfo_height(), 85)
        pad = 7
        y0, y1 = 7, h - 8
        c.create_rectangle(pad + 3, y0 + 5, w - pad + 3, y1 + 5, fill='#cbd0cc', outline='')
        c.create_rectangle(pad, y0, w - pad, y1, fill='#fcfdfa', outline='#d8ddda', width=2)
        left, right = pad + 16, w - pad - 16
        display_width = min(170, max(105, (right - left) * .27))
        gap = 12
        bx0, bx1 = left, right - display_width - gap
        by0, by1 = y0 + 16, y1 - 16
        c.create_rectangle(bx0, by0, bx1, by1, fill='#b2bdb8', outline='#788581', width=2)
        segments = 24
        ratio = max(0, min(1, self.remaining / self.total)) if self.total else 0
        active = math.ceil(ratio * segments - 1e-9)
        unit = (bx1 - bx0 - 6) / segments
        for i in range(segments):
            x0 = bx0 + 3 + i * unit + 1
            x1 = bx0 + 3 + (i + 1) * unit - 1
            if x1 > x0:
                c.create_rectangle(x0, by0 + 4, x1, by1 - 4, fill=INK if i < active else PALE, outline='')
        dx0, dx1 = bx1 + gap, right
        c.create_rectangle(dx0, by0, dx1, by1, fill='#b2bdb8', outline='#788581', width=2)
        seconds = math.ceil(self.remaining)
        hours, rem = divmod(seconds, 3600)
        mins, sec = divmod(rem, 60)
        clock = f'{hours}:{mins:02d}:{sec:02d}' if hours else f'{mins:02d}:{sec:02d}'
        font_size = max(17, min(38, int(display_width / (len(clock) * .64)), int((by1 - by0) * .55)))
        c.create_text((dx0 + dx1) / 2, (by0 + by1) / 2, text=clock, font=('Menlo', font_size, 'bold'), fill=INK)


if __name__ == '__main__':
    root = tk.Tk()
    VisualBarTimer(root)
    root.mainloop()
