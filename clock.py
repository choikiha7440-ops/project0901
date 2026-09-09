import tkinter as tk
from time import strftime
from datetime import datetime, date
import calendar
import math
import sys

# ---- Windows DPI 스케일링 보정 ----
# 라떼판다 같은 소형 모니터는 Windows에서 기본 125%~150% 배율이 걸려있는 경우가 많다.
# DPI 인식(Aware) 상태로 만들지 않으면 tkinter가 조회하는 화면 해상도와 실제 렌더링 픽셀이
# 어긋나서, 계산은 맞아도 가장자리가 미세하게 밀리거나 잘리는 현상이 생긴다.
if sys.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# 'holidays' 패키지가 설치되어 있으면 음력 공휴일(설날/추석/부처님오신날)과
# 대체공휴일까지 정확하게 계산합니다. (설치: pip install holidays)
# 없으면 양력 고정 공휴일만 표시하는 자체 목록으로 대체됩니다.
try:
    import holidays as _holidays_lib
    HOLIDAYS_LIB_AVAILABLE = True
except ImportError:
    HOLIDAYS_LIB_AVAILABLE = False


class FullScreenCalendarClock:
    # ---- 고급스러운 다크 & 골드 컬러 팔레트 ----
    BG_COLOR       = '#0B0B0D'   # 메인 배경 (거의 검정, 약간 따뜻한 톤)
    PANEL_BORDER   = '#2A2A2E'   # 패널 구분선
    GOLD           = '#D4AF37'   # 포인트 골드
    GOLD_DIM       = '#8A7534'   # 어두운 골드 (보조선/틱)
    TEXT_MAIN      = '#EDEDED'   # 기본 텍스트(오프화이트)
    TEXT_SUB       = '#9A9A9E'   # 보조 텍스트(연한 회색)
    SUNDAY_COLOR   = '#E0555A'   # 일요일 (톤 다운된 레드)
    SATURDAY_COLOR = '#4A90D9'   # 토요일 (톤 다운된 블루)
    TODAY_BG       = '#D4AF37'   # 오늘 날짜 강조 배경(골드)
    TODAY_FG       = '#0B0B0D'   # 오늘 날짜 강조 글자(배경과 대비)
    HOLIDAY_COLOR  = '#FF5A5A'   # 공휴일 숫자 강조색(선명한 레드)

    FONT_SERIF   = 'Georgia'      # 타이틀/장식용 세리프 폰트
    FONT_KOREAN  = 'Malgun Gothic' # 한글 표기용
    FONT_DIGITAL = 'Helvetica'    # 디지털 숫자용

    # 아래 모든 폰트 크기 / 픽셀 크기는 1920x1080 모니터를 기준으로 설계된 값이며,
    # 실제 실행 시 화면 해상도에 맞춰 self.s()를 통해 자동으로 비례 축소/확대됩니다.
    BASE_WIDTH = 1920
    BASE_HEIGHT = 1080

    def __init__(self, root):
        self.root = root

        # 1. 전체 화면 설정 및 고급스러운 배경색 지정
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg=self.BG_COLOR)
        self.root.update_idletasks()  # 아래 화면 해상도 조회 전에 창 상태를 확정

        # ---- 화면 해상도 기반 스케일 계산 ----
        # 라떼판다 델타의 작은 모니터(예: 1024x600급)처럼 해상도가 낮으면 축소,
        # 일반 데스크톱 모니터(1920x1080 이상)에서는 원래 설계 크기 그대로 사용.
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        raw_scale = min(screen_w / self.BASE_WIDTH, screen_h / self.BASE_HEIGHT)
        # DPI 스케일링 오차나 미세한 계산 차이로 인해 가장자리가 잘리는 것을 막기 위해
        # 계산된 배율에서 10% 정도 여유 공간을 확보한다.
        SAFETY_MARGIN = 0.90
        self.scale = max(0.35, min(raw_scale * SAFETY_MARGIN, 1.4))

        self.root.bind("<Escape>", lambda event: self.root.attributes('-fullscreen', False))
        self.root.bind("<q>", lambda event: self.root.destroy())

        # 2. 메인 레이아웃 프레임 생성 (좌측 50%: 달력 / 중앙: 구분선 / 우측 50%: 시계)
        self.main_frame = tk.Frame(self.root, bg=self.BG_COLOR)
        self.main_frame.pack(expand=True, fill='both', padx=self.s(20), pady=self.s(20))

        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)  # 좌측 50%
        self.main_frame.grid_columnconfigure(1, weight=0)  # 구분선 (고정폭)
        self.main_frame.grid_columnconfigure(2, weight=1)  # 우측 50%

        # 왼쪽 영역 (달력) - 50%
        self.cal_frame = tk.Frame(self.main_frame, bg=self.BG_COLOR)
        self.cal_frame.grid(row=0, column=0, sticky='nsew')

        # 중앙 얇은 구분선
        self.divider = tk.Frame(self.main_frame, bg=self.PANEL_BORDER, width=2)
        self.divider.grid(row=0, column=1, sticky='ns', padx=self.s(30))

        # 오른쪽 영역 (아날로그 시계 + 디지털 시계 + 날짜 텍스트) - 50%
        self.time_frame = tk.Frame(self.main_frame, bg=self.BG_COLOR)
        self.time_frame.grid(row=0, column=2, sticky='nsew')

        # 좌/우 각 프레임 내부 컨텐츠를 화면 정중앙(수평+수직)에 배치하기 위한 래퍼
        self.cal_frame.grid_rowconfigure(0, weight=1)
        self.cal_frame.grid_columnconfigure(0, weight=1)
        self.cal_content = tk.Frame(self.cal_frame, bg=self.BG_COLOR)
        self.cal_content.grid(row=0, column=0)

        self.time_frame.grid_rowconfigure(0, weight=1)
        self.time_frame.grid_columnconfigure(0, weight=1)
        self.time_content = tk.Frame(self.time_frame, bg=self.BG_COLOR)
        self.time_content.grid(row=0, column=0)

        # 3. 우측 상단 장식용 타이틀
        self.lbl_brand = tk.Label(self.time_content, text="T I M E P I E C E",
                                   font=(self.FONT_SERIF, self.s(16), 'bold'),
                                   bg=self.BG_COLOR, fg=self.GOLD_DIM)
        self.lbl_brand.pack(pady=(self.s(10), 0))

        # 4. 아날로그 시계 캔버스 (해상도에 비례해 지름 결정)
        self.clock_size = self.s(360)
        self.clock_center = (self.clock_size // 2, self.clock_size // 2)
        self.clock_radius = self.clock_size // 2 - self.s(20)
        self.clock_canvas = tk.Canvas(self.time_content, width=self.clock_size, height=self.clock_size,
                                       bg=self.BG_COLOR, highlightthickness=0)
        self.clock_canvas.pack(pady=(self.s(10), self.s(20)))
        self.draw_clock_face()

        # 5. 디지털 날짜 / 시간 라벨
        self.lbl_date = tk.Label(self.time_content, font=(self.FONT_KOREAN, self.s(24), 'bold'),
                                  bg=self.BG_COLOR, fg=self.TEXT_SUB)
        self.lbl_date.pack(anchor='center', pady=(0, self.s(5)))

        self.lbl_time = tk.Label(self.time_content, font=(self.FONT_DIGITAL, self.s(64), 'bold'),
                                  bg=self.BG_COLOR, fg=self.GOLD)
        self.lbl_time.pack(anchor='center')

        # 6. 좌측 달력 그리기 초기화
        self.draw_calendar()

        # 7. 실시간 업데이트 시작
        self.update_clock()

    # ------------------------------------------------------------------
    # 해상도 스케일 헬퍼: 1920x1080 기준 픽셀/포인트 값을 실제 화면에 맞게 변환
    # ------------------------------------------------------------------
    def s(self, value):
        return max(1, int(round(value * self.scale)))

    # ------------------------------------------------------------------
    # 아날로그 시계 - 문자판(고정 요소) 그리기
    # ------------------------------------------------------------------
    def draw_clock_face(self):
        cx, cy = self.clock_center
        r = self.clock_radius

        # 바깥 골드 테두리 (이중 링으로 고급스러움 강조)
        self.clock_canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                       outline=self.GOLD, width=self.s(3))
        self.clock_canvas.create_oval(cx - r + self.s(10), cy - r + self.s(10),
                                       cx + r - self.s(10), cy + r - self.s(10),
                                       outline=self.GOLD_DIM, width=1)

        # 시간 눈금 및 숫자
        for i in range(12):
            angle = math.radians(i * 30 - 90)
            x1 = cx + (r - self.s(22)) * math.cos(angle)
            y1 = cy + (r - self.s(22)) * math.sin(angle)
            x2 = cx + (r - self.s(10)) * math.cos(angle)
            y2 = cy + (r - self.s(10)) * math.sin(angle)
            self.clock_canvas.create_line(x1, y1, x2, y2, fill=self.GOLD, width=self.s(3))

            num = i if i != 0 else 12
            nx = cx + (r - self.s(45)) * math.cos(angle)
            ny = cy + (r - self.s(45)) * math.sin(angle)
            self.clock_canvas.create_text(nx, ny, text=str(num),
                                           fill=self.TEXT_MAIN,
                                           font=(self.FONT_SERIF, self.s(18), 'bold'))

        # 분 단위 얇은 눈금
        for i in range(60):
            if i % 5 != 0:
                angle = math.radians(i * 6 - 90)
                x1 = cx + (r - self.s(14)) * math.cos(angle)
                y1 = cy + (r - self.s(14)) * math.sin(angle)
                x2 = cx + (r - self.s(10)) * math.cos(angle)
                y2 = cy + (r - self.s(10)) * math.sin(angle)
                self.clock_canvas.create_line(x1, y1, x2, y2, fill=self.GOLD_DIM, width=1)

    # ------------------------------------------------------------------
    # 아날로그 시계 - 시/분/초 바늘 업데이트 (매초 다시 그림)
    # ------------------------------------------------------------------
    def update_analog_hands(self, now):
        self.clock_canvas.delete('hands')
        cx, cy = self.clock_center
        r = self.clock_radius

        hour = (now.hour % 12) + now.minute / 60
        minute = now.minute + now.second / 60
        second = now.second

        hour_angle = math.radians(hour * 30 - 90)
        minute_angle = math.radians(minute * 6 - 90)
        second_angle = math.radians(second * 6 - 90)

        hour_len = r * 0.5
        minute_len = r * 0.72
        second_len = r * 0.82

        # 시침
        self.clock_canvas.create_line(cx, cy,
                                       cx + hour_len * math.cos(hour_angle),
                                       cy + hour_len * math.sin(hour_angle),
                                       fill=self.TEXT_MAIN, width=self.s(7), capstyle='round', tags='hands')
        # 분침
        self.clock_canvas.create_line(cx, cy,
                                       cx + minute_len * math.cos(minute_angle),
                                       cy + minute_len * math.sin(minute_angle),
                                       fill=self.TEXT_MAIN, width=self.s(4), capstyle='round', tags='hands')
        # 초침
        self.clock_canvas.create_line(cx, cy,
                                       cx - second_len * 0.15 * math.cos(second_angle),
                                       cy - second_len * 0.15 * math.sin(second_angle),
                                       cx + second_len * math.cos(second_angle),
                                       cy + second_len * math.sin(second_angle),
                                       fill=self.GOLD, width=self.s(2), tags='hands')
        # 중심 캡
        cap = self.s(9)
        self.clock_canvas.create_oval(cx - cap, cy - cap, cx + cap, cy + cap,
                                       fill=self.GOLD, outline=self.BG_COLOR, width=self.s(2), tags='hands')

    # ------------------------------------------------------------------
    # 공휴일 데이터 조회
    # ------------------------------------------------------------------
    def get_korean_holidays(self, year):
        """{date: '공휴일 이름'} 형태의 딕셔너리 반환.
        holidays 패키지가 있으면 음력 공휴일/대체공휴일까지 정확히 계산하고,
        없으면 양력 고정 공휴일만 담은 자체 목록으로 대체한다."""
        if HOLIDAYS_LIB_AVAILABLE:
            try:
                # 시스템 로케일과 무관하게 항상 한글 공휴일명이 나오도록 명시적으로 지정
                return _holidays_lib.KR(years=year, language='ko')
            except TypeError:
                return _holidays_lib.KR(years=year)

        # ---- 폴백: 양력 고정 공휴일만 (음력 공휴일 미포함) ----
        return {
            date(year, 1, 1): "신정",
            date(year, 3, 1): "삼일절",
            date(year, 5, 5): "어린이날",
            date(year, 6, 6): "현충일",
            date(year, 8, 15): "광복절",
            date(year, 10, 3): "개천절",
            date(year, 10, 9): "한글날",
            date(year, 12, 25): "크리스마스",
        }

    # ------------------------------------------------------------------
    # 달력 그리기
    # ------------------------------------------------------------------
    def draw_calendar(self):
        """현재 년/월에 맞는 달력을 텍스트 격자 구조로 화면에 그림"""
        for widget in self.cal_content.winfo_children():
            widget.destroy()

        now = datetime.now()
        year, month, today = now.year, now.month, now.day

        # 이번 달 공휴일 데이터
        kr_holidays = self.get_korean_holidays(year)

        # 달력 상단 제목
        lbl_cal_title = tk.Label(self.cal_content, text=f"{year}  ·  {month}월",
                                  font=(self.FONT_SERIF, self.s(44), 'bold'),
                                  bg=self.BG_COLOR, fg=self.GOLD)
        lbl_cal_title.pack(pady=(self.s(20), self.s(10)))

        # 제목 아래 얇은 골드 언더라인
        underline = tk.Frame(self.cal_content, bg=self.GOLD_DIM, height=1, width=self.s(260))
        underline.pack(pady=(0, self.s(30)))

        # 요일 표기 프레임
        days_frame = tk.Frame(self.cal_content, bg=self.BG_COLOR)
        days_frame.pack()

        week_days = ["일", "월", "화", "수", "목", "금", "토"]
        colors = [self.SUNDAY_COLOR, self.TEXT_MAIN, self.TEXT_MAIN, self.TEXT_MAIN,
                  self.TEXT_MAIN, self.TEXT_MAIN, self.SATURDAY_COLOR]

        for i, day in enumerate(week_days):
            lbl = tk.Label(days_frame, text=day, font=(self.FONT_KOREAN, self.s(23), 'bold'),
                            width=5, bg=self.BG_COLOR, fg=colors[i])
            lbl.grid(row=0, column=i, padx=self.s(10), pady=self.s(10))

        # 날짜 숫자 배치 프레임
        dates_frame = tk.Frame(self.cal_content, bg=self.BG_COLOR)
        dates_frame.pack()

        cal = calendar.Calendar(firstweekday=6)  # 일요일 시작
        month_days = cal.monthdayscalendar(year, month)

        # 이번 달에 걸친 공휴일 목록 (하단 범례용)
        month_holidays = []

        for r, week in enumerate(month_days):
            for c, day in enumerate(week):
                if day == 0:
                    lbl = tk.Label(dates_frame, text="", font=(self.FONT_DIGITAL, self.s(26)),
                                    width=5, bg=self.BG_COLOR)
                else:
                    if c == 0:
                        fg_color = self.SUNDAY_COLOR
                    elif c == 6:
                        fg_color = self.SATURDAY_COLOR
                    else:
                        fg_color = self.TEXT_MAIN

                    holiday_name = kr_holidays.get(date(year, month, day))
                    if holiday_name:
                        fg_color = self.HOLIDAY_COLOR
                        month_holidays.append((day, holiday_name))

                    if day == today:
                        lbl = tk.Label(dates_frame, text=str(day), font=(self.FONT_DIGITAL, self.s(26), 'bold'),
                                        width=5, bg=self.TODAY_BG, fg=self.TODAY_FG,
                                        relief='flat', borderwidth=0)
                    else:
                        lbl = tk.Label(dates_frame, text=str(day), font=(self.FONT_DIGITAL, self.s(26)),
                                        width=5, bg=self.BG_COLOR, fg=fg_color)

                lbl.grid(row=r, column=c, padx=self.s(10), pady=self.s(14))

        # 이번 달 공휴일 이름 범례
        if month_holidays:
            legend_frame = tk.Frame(self.cal_content, bg=self.BG_COLOR)
            legend_frame.pack(pady=(self.s(25), 0), fill='x')

            for day, name in sorted(set(month_holidays)):
                row = tk.Frame(legend_frame, bg=self.BG_COLOR)
                row.pack(anchor='w', pady=self.s(2))

                lbl_dot = tk.Label(row, text="●", font=(self.FONT_DIGITAL, self.s(10)),
                                    bg=self.BG_COLOR, fg=self.HOLIDAY_COLOR)
                lbl_dot.pack(side='left', padx=(0, self.s(8)))

                lbl_holiday = tk.Label(row, text=f"{month}월 {day}일  {name}",
                                        font=(self.FONT_KOREAN, self.s(16)),
                                        bg=self.BG_COLOR, fg=self.HOLIDAY_COLOR)
                lbl_holiday.pack(side='left')

    # ------------------------------------------------------------------
    # 매초 갱신
    # ------------------------------------------------------------------
    def update_clock(self):
        """1초마다 아날로그/디지털 시계와 날짜 텍스트를 새로고침하는 함수"""
        now = datetime.now()

        date_string = now.strftime('%Y년 %m월 %d일 (%a)') \
            .replace('Mon', '월').replace('Tue', '화').replace('Wed', '수') \
            .replace('Thu', '목').replace('Fri', '금').replace('Sat', '토').replace('Sun', '일')
        self.lbl_date.config(text=date_string)

        time_string = strftime('%H:%M:%S')
        self.lbl_time.config(text=time_string)

        self.update_analog_hands(now)

        if time_string == "00:00:00":
            self.draw_calendar()

        self.lbl_time.after(1000, self.update_clock)


if __name__ == "__main__":
    root = tk.Tk()
    root.title("전체화면 달력 & 아날로그 시계 (고급 테마)")
    app = FullScreenCalendarClock(root)
    root.mainloop()
