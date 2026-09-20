"""
Pathology Laboratory — Employee Attendance & Roster Management Workbook
Company-grade HR workforce management Excel file.
"""
from datetime import date, timedelta
from calendar import monthrange

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, NamedStyle
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule, FormulaRule, ColorScaleRule
from openpyxl.chart import BarChart, PieChart, Reference, LineChart
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.page import PageMargins
from openpyxl.formatting.rule import Rule
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.workbook.protection import WorkbookProtection

OUT = r"E:\ai_data_rag\ai_data_v2\Pathology_Lab_Attendance_Roster_HR.xlsx"
OUT_FIXED = r"E:\ai_data_rag\ai_data_v2\Pathology_Lab_Attendance_Roster_HR_Weeks.xlsx"

# ── Palette (corporate medical / pathology lab) ─────────────────────────────
NAVY = "0D2137"
TEAL = "0E7C7B"
CORAL = "C7522A"
SLATE = "5A6A7A"
INK = "1A2332"
WHITE = "FFFFFF"
LIGHT = "F5F7FA"
ALT = "EEF3F6"
SAND = "F0EDE6"
GREEN = "1B7A4E"
GREEN_BG = "D4EDDA"
RED = "B71C1C"
RED_BG = "F8D7DA"
AMBER = "B78103"
AMBER_BG = "FFF3CD"
BLUE = "0D47A1"
BLUE_BG = "D6E4F0"
PURPLE = "5E35B1"
PURPLE_BG = "EDE7F6"
GRAY = "607D8B"
GRAY_BG = "ECEFF1"
LINE = "CBD5E1"

thin = Border(
    left=Side(style="thin", color=LINE),
    right=Side(style="thin", color=LINE),
    top=Side(style="thin", color=LINE),
    bottom=Side(style="thin", color=LINE),
)
thick_b = Border(bottom=Side(style="medium", color=TEAL))

fill_navy = PatternFill("solid", fgColor=NAVY)
fill_teal = PatternFill("solid", fgColor=TEAL)
fill_light = PatternFill("solid", fgColor=LIGHT)
fill_alt = PatternFill("solid", fgColor=ALT)
fill_white = PatternFill("solid", fgColor=WHITE)
fill_sand = PatternFill("solid", fgColor=SAND)
fill_green = PatternFill("solid", fgColor=GREEN_BG)
fill_red = PatternFill("solid", fgColor=RED_BG)
fill_amber = PatternFill("solid", fgColor=AMBER_BG)
fill_blue = PatternFill("solid", fgColor=BLUE_BG)
fill_purple = PatternFill("solid", fgColor=PURPLE_BG)
fill_gray = PatternFill("solid", fgColor=GRAY_BG)
fill_coral = PatternFill("solid", fgColor="F5E6E0")

font_title = Font(name="Calibri", size=18, bold=True, color=WHITE)
font_sub = Font(name="Calibri", size=11, color="A8C5C4")
font_white_b = Font(name="Calibri", size=10, bold=True, color=WHITE)
font_ink = Font(name="Calibri", size=10, color=INK)
font_ink_b = Font(name="Calibri", size=10, bold=True, color=INK)
font_small = Font(name="Calibri", size=9, color=SLATE)
font_teal_b = Font(name="Calibri", size=11, bold=True, color=TEAL)
font_navy_b = Font(name="Calibri", size=12, bold=True, color=NAVY)
font_kpi = Font(name="Calibri", size=22, bold=True, color=NAVY)
font_kpi_lbl = Font(name="Calibri", size=9, bold=True, color=SLATE)

center = Alignment(horizontal="center", vertical="center", wrap_text=True)
left = Alignment(horizontal="left", vertical="center", wrap_text=True)
left_indent = Alignment(horizontal="left", vertical="center", indent=1)

# ── Sample pathology lab data ───────────────────────────────────────────────
YEAR, MONTH = 2026, 9  # Default demo period (change anytime in Roster B5 / D5)
MAX_DAYS = 31  # Always show 1–31; invalid days auto-blank when month has fewer days
DAYS_IN_MONTH = monthrange(YEAR, MONTH)[1]  # used only to pre-fill demo sample marks

DEPARTMENTS = [
    "Hematology",
    "Biochemistry",
    "Microbiology",
    "Histopathology",
    "Phlebotomy",
    "Sample Receiving",
    "Quality Assurance",
    "Administration",
]

DESIGNATIONS = [
    "Lab Manager",
    "Pathologist",
    "Senior Lab Technologist",
    "Lab Technologist",
    "Lab Assistant",
    "Phlebotomist",
    "QA Officer",
    "Receptionist",
]

EMPLOYMENT_TYPES = ["Permanent", "Contract", "Trainee", "Part-time"]
SHIFT_ELIGIBILITY = ["All Shifts", "Morning Only", "Morning/Evening", "Night Eligible"]
STATUS_OPTS = ["Active", "Inactive"]

SHIFTS = [
    ("M", "Morning", "06:00–14:00"),
    ("E", "Evening", "14:00–22:00"),
    ("N", "Night", "22:00–06:00"),
    ("WO", "Weekly Off", "—"),
    ("PH", "Public Holiday", "—"),
    ("LV", "Leave", "—"),
    ("TR", "Training", "—"),
]

ATT_CODES = [
    ("P", "Present", GREEN_BG, GREEN),
    ("A", "Absent", RED_BG, RED),
    ("L", "Late Coming", AMBER_BG, AMBER),
    ("HD", "Half Day", "FFE0B2", "E65100"),
    ("WFO", "Work From Office", BLUE_BG, BLUE),
    ("PL", "Planned Leave", PURPLE_BG, PURPLE),
    ("UL", "Unscheduled Leave", "FCE4EC", "AD1457"),
    ("VL", "Vacation Leave", "E0F7FA", "00838F"),
    ("SL", "Sick Leave", "FFEBEE", "C62828"),
    ("H", "Holiday", GRAY_BG, GRAY),
    ("WO", "Weekly Off", GRAY_BG, GRAY),
    ("OT", "Overtime", "E8F5E9", "2E7D32"),
]

LEAVE_TYPES = ["Planned Leave", "Unplanned Leave", "Sick Leave", "Vacation Leave"]
LEAVE_STATUS = ["Pending", "Approved", "Rejected", "Cancelled"]

# Public holidays for Sep 2026 (sample — India-style placeholders)
PUBLIC_HOLIDAYS = [
    (date(2026, 9, 5), "Teachers' Day (Optional)"),
    (date(2026, 9, 14), "Hindi Diwas (Optional)"),
]

EMPLOYEES = [
    # EMP_ID, Name, Designation, Dept, Manager, DOJ, Type, ShiftElig, Phone, Email, Emergency, Status
    ("PL-001", "Dr. Ananya Mehta", "Pathologist", "Histopathology", "Lab Director", date(2019, 3, 12), "Permanent", "Morning Only", "9876543210", "ananya.mehta@pathlab.example", "Rajesh Mehta — 9876500001", "Active"),
    ("PL-002", "Vikram Singh", "Lab Manager", "Administration", "Lab Director", date(2018, 6, 1), "Permanent", "All Shifts", "9876543211", "vikram.singh@pathlab.example", "Priya Singh — 9876500002", "Active"),
    ("PL-003", "Sneha Patel", "Senior Lab Technologist", "Hematology", "Vikram Singh", date(2020, 1, 15), "Permanent", "All Shifts", "9876543212", "sneha.patel@pathlab.example", "Amit Patel — 9876500003", "Active"),
    ("PL-004", "Rahul Nair", "Lab Technologist", "Hematology", "Sneha Patel", date(2021, 8, 20), "Permanent", "All Shifts", "9876543213", "rahul.nair@pathlab.example", "Deepa Nair — 9876500004", "Active"),
    ("PL-005", "Fatima Khan", "Lab Technologist", "Biochemistry", "Vikram Singh", date(2020, 11, 5), "Permanent", "Morning/Evening", "9876543214", "fatima.khan@pathlab.example", "Imran Khan — 9876500005", "Active"),
    ("PL-006", "Arjun Reddy", "Lab Technologist", "Biochemistry", "Fatima Khan", date(2022, 2, 14), "Permanent", "All Shifts", "9876543215", "arjun.reddy@pathlab.example", "Kavitha Reddy — 9876500006", "Active"),
    ("PL-007", "Meera Iyer", "Senior Lab Technologist", "Microbiology", "Vikram Singh", date(2019, 9, 1), "Permanent", "Morning/Evening", "9876543216", "meera.iyer@pathlab.example", "Suresh Iyer — 9876500007", "Active"),
    ("PL-008", "Karan Malhotra", "Lab Technologist", "Microbiology", "Meera Iyer", date(2023, 4, 10), "Contract", "All Shifts", "9876543217", "karan.malhotra@pathlab.example", "Neha Malhotra — 9876500008", "Active"),
    ("PL-009", "Pooja Sharma", "Lab Assistant", "Histopathology", "Dr. Ananya Mehta", date(2021, 5, 18), "Permanent", "Morning Only", "9876543218", "pooja.sharma@pathlab.example", "Ravi Sharma — 9876500009", "Active"),
    ("PL-010", "Mohammed Irfan", "Phlebotomist", "Phlebotomy", "Vikram Singh", date(2022, 7, 1), "Permanent", "Morning/Evening", "9876543219", "m.irfan@pathlab.example", "Ayesha Irfan — 9876500010", "Active"),
    ("PL-011", "Lakshmi Devi", "Phlebotomist", "Phlebotomy", "Vikram Singh", date(2020, 3, 22), "Permanent", "Morning Only", "9876543220", "lakshmi.devi@pathlab.example", "Venkat Devi — 9876500011", "Active"),
    ("PL-012", "Suresh Kumar", "Lab Assistant", "Sample Receiving", "Vikram Singh", date(2021, 12, 6), "Permanent", "All Shifts", "9876543221", "suresh.kumar@pathlab.example", "Anita Kumar — 9876500012", "Active"),
    ("PL-013", "Nisha Gupta", "QA Officer", "Quality Assurance", "Vikram Singh", date(2019, 7, 15), "Permanent", "Morning Only", "9876543222", "nisha.gupta@pathlab.example", "Anil Gupta — 9876500013", "Active"),
    ("PL-014", "Deepak Joshi", "Lab Technologist", "Hematology", "Sneha Patel", date(2024, 1, 8), "Trainee", "Morning/Evening", "9876543223", "deepak.joshi@pathlab.example", "Sunita Joshi — 9876500014", "Active"),
    ("PL-015", "Anjali Verma", "Receptionist", "Administration", "Vikram Singh", date(2022, 9, 12), "Permanent", "Morning Only", "9876543224", "anjali.verma@pathlab.example", "Rohit Verma — 9876500015", "Active"),
    ("PL-016", "Ravi Teja", "Lab Technologist", "Biochemistry", "Fatima Khan", date(2023, 6, 20), "Contract", "Night Eligible", "9876543225", "ravi.teja@pathlab.example", "Sita Teja — 9876500016", "Active"),
    ("PL-017", "Geeta Rao", "Lab Assistant", "Microbiology", "Meera Iyer", date(2020, 10, 30), "Permanent", "Morning/Evening", "9876543226", "geeta.rao@pathlab.example", "Mohan Rao — 9876500017", "Active"),
    ("PL-018", "Imran Sheikh", "Phlebotomist", "Phlebotomy", "Vikram Singh", date(2024, 3, 1), "Part-time", "Morning Only", "9876543227", "imran.sheikh@pathlab.example", "Farah Sheikh — 9876500018", "Active"),
    ("PL-019", "Kavya Menon", "Lab Technologist", "Histopathology", "Dr. Ananya Mehta", date(2021, 4, 5), "Permanent", "Morning Only", "9876543228", "kavya.menon@pathlab.example", "Arun Menon — 9876500019", "Active"),
    ("PL-020", "Thomas Mathew", "Senior Lab Technologist", "Sample Receiving", "Vikram Singh", date(2018, 11, 19), "Permanent", "All Shifts", "9876543229", "thomas.mathew@pathlab.example", "Mary Mathew — 9876500020", "Inactive"),
]

N_EMP = len(EMPLOYEES)
N_ACTIVE = sum(1 for e in EMPLOYEES if e[11] == "Active")


def banner(ws, last_col, title, subtitle, org="PATHCARE DIAGNOSTICS  ·  Pathology Laboratory"):
    for r in (1, 2, 3):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=last_col)
        for c in range(1, last_col + 1):
            ws.cell(r, c).fill = fill_navy
    ws.cell(1, 1, org).font = Font(name="Calibri", size=9, bold=True, color=TEAL)
    ws.cell(1, 1).alignment = left_indent
    ws.cell(2, 1, title).font = font_title
    ws.cell(2, 1).alignment = left_indent
    ws.cell(3, 1, subtitle).font = font_sub
    ws.cell(3, 1).alignment = left_indent
    ws.row_dimensions[1].height = 16
    ws.row_dimensions[2].height = 26
    ws.row_dimensions[3].height = 18


def style_header_row(ws, row, start_col, end_col, fill=None):
    f = fill or fill_teal
    for c in range(start_col, end_col + 1):
        cell = ws.cell(row, c)
        cell.font = font_white_b
        cell.fill = f
        cell.alignment = center
        cell.border = thin


def set_widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def apply_print(ws, landscape=True):
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_margins = PageMargins(0.4, 0.4, 0.5, 0.5, 0.2, 0.2)
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 90


def alt_fill(i):
    return fill_white if i % 2 == 0 else fill_alt


wb = Workbook()

# ═══════════════════════════════════════════════════════════════════════════
# 00_HOME — Navigation
# ═══════════════════════════════════════════════════════════════════════════
ws_h = wb.active
ws_h.title = "00_Home"
banner(ws_h, 6, "EMPLOYEE ATTENDANCE & ROSTER MANAGEMENT",
       "Workforce HR system  ·  Single source of truth for staff, shifts, attendance & leave")
set_widths(ws_h, [4, 28, 55, 22, 18, 18])

ws_h["B5"] = "WORKBOOK NAVIGATION"
ws_h["B5"].font = font_white_b
ws_h["B5"].fill = fill_teal
ws_h.merge_cells("B5:D5")
for c in range(2, 5):
    ws_h.cell(5, c).fill = fill_teal
    ws_h.cell(5, c).border = thin

headers_nav = [("B6", "Sheet"), ("C6", "Purpose"), ("D6", "Edit here?")]
for addr, txt in headers_nav:
    ws_h[addr] = txt
    ws_h[addr].font = font_white_b
    ws_h[addr].fill = PatternFill("solid", fgColor=NAVY)
    ws_h[addr].alignment = center
    ws_h[addr].border = thin

nav_rows = [
    ("01_Config", "Shifts, attendance codes, leave types, departments, public holidays, leave policy.", "Yes — setup only"),
    ("02_Employee_Master", "Master employee register. All other sheets pull names/IDs from here.", "Yes — HR master"),
    ("03_Roster", "Full-month view (auto from Week sheets). Set Month/Year here. Use week buttons to edit.", "View + period"),
    ("W1–W5_Roster", "Week-wise roster (Days 1–7, 8–14, 15–21, 22–28, 29–31). Edit shifts here.", "Yes — weekly edit"),
    ("04_Attendance", "Daily attendance marks linked to roster month. Color-coded statuses.", "Yes — daily mark"),
    ("05_Leave", "Leave applications, balances, approval workflow, manager remarks.", "Yes — leave desk"),
    ("06_Dashboard", "Live KPIs, shift headcount, dept stats, trends. Formula-driven — do not type.", "No — auto"),
]
for i, (a, b, c) in enumerate(nav_rows):
    r = 7 + i
    ws_h.cell(r, 2, a).font = font_ink_b
    ws_h.cell(r, 3, b).font = font_ink
    ws_h.cell(r, 4, c).font = font_ink
    for col in range(2, 5):
        ws_h.cell(r, col).fill = alt_fill(i)
        ws_h.cell(r, col).border = thin
        ws_h.cell(r, col).alignment = left
    ws_h.row_dimensions[r].height = 28

# Week navigation buttons on Home
ws_h["B15"] = "WEEK ROSTER SHORTCUTS  (click to open)"
ws_h.merge_cells("B15:D15")
ws_h["B15"].font = font_white_b
ws_h["B15"].fill = fill_navy
for c in range(2, 5):
    ws_h.cell(15, c).fill = fill_navy
    ws_h.cell(15, c).border = thin

def _home_btn(cell, label, sheet, color):
    cell.value = label
    cell.hyperlink = f"#{sheet}!A1"
    cell.font = Font(name="Calibri", size=11, bold=True, color=WHITE, underline="single")
    cell.fill = PatternFill("solid", fgColor=color)
    cell.alignment = center
    cell.border = thin

_home_btn(ws_h.cell(16, 2), "▶ Week 1 (Days 1–7)", "W1_Roster", "0E7C7B")
_home_btn(ws_h.cell(16, 3), "▶ Week 2 (Days 8–14)", "W2_Roster", "1565C0")
_home_btn(ws_h.cell(16, 4), "▶ Week 3 (Days 15–21)", "W3_Roster", "5E35B1")
_home_btn(ws_h.cell(17, 2), "▶ Week 4 (Days 22–28)", "W4_Roster", "C7522A")
_home_btn(ws_h.cell(17, 3), "▶ Week 5 (Days 29–31)", "W5_Roster", "B78103")
_home_btn(ws_h.cell(17, 4), "📅 Full Month", "03_Roster", NAVY)
ws_h.row_dimensions[16].height = 26
ws_h.row_dimensions[17].height = 26

ws_h.merge_cells("B19:D21")
ws_h["B19"] = (
    "OPERATING RULES\n"
    "1. Maintain employees only on Employee Master (Active/Inactive).\n"
    "2. Set Month / Year on 03_Roster (B5 / D5). Enter shifts on Week 1–5 sheets (buttons above).\n"
    "3. Full Month roster mirrors weeks automatically. Then mark Attendance daily.\n"
    "4. Leave sheet updates balances; Dashboard recalculates from live data."
)
ws_h["B19"].font = Font(name="Calibri", size=10, color=INK)
ws_h["B19"].alignment = Alignment(wrap_text=True, vertical="top")
ws_h["B19"].fill = fill_sand
ws_h["B19"].border = thin

# Month-change playbook
ws_h["B23"] = "WHEN THE MONTH CHANGES — DO THIS"
ws_h.merge_cells("B23:D23")
ws_h["B23"].font = font_white_b
ws_h["B23"].fill = PatternFill("solid", fgColor=CORAL)
for c in range(2, 5):
    ws_h.cell(23, c).fill = PatternFill("solid", fgColor=CORAL)
    ws_h.cell(23, c).border = thin

month_steps = [
    ("Step 1", "Optional archive: File → Save As → Pathology_Roster_YYYY-MM.xlsx"),
    ("Step 2", "03_Roster → set B5 = new month, D5 = year."),
    ("Step 3", "Open each Week 1–5 sheet → clear old marks → enter new week roster."),
    ("Step 4", "Full Month updates from weeks. Clear & mark 04_Attendance for the new month."),
    ("Step 5", "Update holidays / leave as needed. Check Dashboard."),
]
for i, (step, detail) in enumerate(month_steps):
    r = 24 + i
    ws_h.cell(r, 2, step).font = font_ink_b
    ws_h.cell(r, 2).fill = fill_coral
    ws_h.cell(r, 2).border = thin
    ws_h.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
    ws_h.cell(r, 3, detail).font = font_ink
    ws_h.cell(r, 3).border = thin
    ws_h.cell(r, 4).border = thin
    for col in (3, 4):
        ws_h.cell(r, col).fill = alt_fill(i)
    ws_h.row_dimensions[r].height = 20

ws_h["B30"] = "CURRENT PERIOD"
ws_h["C30"] = "='03_Roster'!B5"
ws_h["D30"] = "='03_Roster'!D5"
ws_h["B30"].font = font_white_b
ws_h["B30"].fill = fill_teal
ws_h["B30"].border = thin
ws_h["C30"].font = font_navy_b
ws_h["C30"].fill = fill_amber
ws_h["C30"].border = thin
ws_h["C30"].alignment = center
ws_h["D30"].font = font_navy_b
ws_h["D30"].fill = fill_amber
ws_h["D30"].border = thin
ws_h["D30"].alignment = center

apply_print(ws_h)
ws_h.sheet_properties.tabColor = NAVY

# ═══════════════════════════════════════════════════════════════════════════
# 01_CONFIG
# ═══════════════════════════════════════════════════════════════════════════
ws_c = wb.create_sheet("01_Config")
banner(ws_c, 10, "SYSTEM CONFIGURATION",
       "Controlled lists for drop-downs  ·  Change carefully — used across the workbook")
set_widths(ws_c, [4, 14, 22, 16, 4, 18, 28, 12, 12, 28])

# Shifts
ws_c["B5"] = "SHIFT CODES"
ws_c.merge_cells("B5:D5")
style_header_row(ws_c, 5, 2, 4)
for col, h in enumerate(["Code", "Shift", "Timing"], 2):
    ws_c.cell(6, col, h).font = font_white_b
    ws_c.cell(6, col).fill = fill_navy
    ws_c.cell(6, col).alignment = center
    ws_c.cell(6, col).border = thin
for i, (code, name, timing) in enumerate(SHIFTS):
    r = 7 + i
    for col, v in enumerate([code, name, timing], 2):
        ws_c.cell(r, col, v).font = font_ink
        ws_c.cell(r, col).border = thin
        ws_c.cell(r, col).fill = alt_fill(i)
        ws_c.cell(r, col).alignment = center if col == 2 else left

# Attendance codes
ws_c["F5"] = "ATTENDANCE CODES"
ws_c.merge_cells("F5:I5")
style_header_row(ws_c, 5, 6, 9)
for col, h in enumerate(["Code", "Meaning", "Fill", "Font"], 6):
    ws_c.cell(6, col, h).font = font_white_b
    ws_c.cell(6, col).fill = fill_navy
    ws_c.cell(6, col).alignment = center
    ws_c.cell(6, col).border = thin
for i, (code, meaning, bg, fg) in enumerate(ATT_CODES):
    r = 7 + i
    ws_c.cell(r, 6, code).font = Font(name="Calibri", size=10, bold=True, color=fg)
    ws_c.cell(r, 6).fill = PatternFill("solid", fgColor=bg)
    ws_c.cell(r, 7, meaning).font = font_ink
    ws_c.cell(r, 8, bg).font = font_small
    ws_c.cell(r, 9, fg).font = font_small
    for col in range(6, 10):
        ws_c.cell(r, col).border = thin
        if col > 6:
            ws_c.cell(r, col).fill = alt_fill(i)
        ws_c.cell(r, col).alignment = center if col != 7 else left

# Departments / Designations / Types
ws_c["B16"] = "DEPARTMENTS"
ws_c["C16"] = "DESIGNATIONS"
ws_c["D16"] = "EMPLOYMENT TYPE"
ws_c["F16"] = "SHIFT ELIGIBILITY"
ws_c["G16"] = "LEAVE TYPES"
ws_c["H16"] = "LEAVE STATUS"
ws_c["I16"] = "EMPLOYEE STATUS"
for col in (2, 3, 4, 6, 7, 8, 9):
    ws_c.cell(16, col).font = font_white_b
    ws_c.cell(16, col).fill = fill_teal
    ws_c.cell(16, col).alignment = center
    ws_c.cell(16, col).border = thin

lists = {
    2: DEPARTMENTS,
    3: DESIGNATIONS,
    4: EMPLOYMENT_TYPES,
    6: SHIFT_ELIGIBILITY,
    7: LEAVE_TYPES,
    8: LEAVE_STATUS,
    9: STATUS_OPTS,
}
for col, items in lists.items():
    for i, v in enumerate(items):
        cell = ws_c.cell(17 + i, col, v)
        cell.font = font_ink
        cell.border = thin
        cell.fill = alt_fill(i)
        cell.alignment = left

# Public holidays
ws_c["B27"] = "PUBLIC HOLIDAYS (update annually)"
ws_c.merge_cells("B27:D27")
style_header_row(ws_c, 27, 2, 4)
ws_c.cell(28, 2, "Date").font = font_white_b
ws_c.cell(28, 3, "Holiday Name").font = font_white_b
ws_c.cell(28, 4, "Applies").font = font_white_b
for col in range(2, 5):
    ws_c.cell(28, col).fill = fill_navy
    ws_c.cell(28, col).border = thin
    ws_c.cell(28, col).alignment = center

# Sample holidays + blank rows for year
hol_samples = [
    (date(2026, 1, 26), "Republic Day", "Yes"),
    (date(2026, 3, 14), "Holi", "Yes"),
    (date(2026, 8, 15), "Independence Day", "Yes"),
    (date(2026, 10, 2), "Gandhi Jayanti", "Yes"),
    (date(2026, 10, 20), "Diwali", "Yes"),
    (date(2026, 12, 25), "Christmas", "Yes"),
]
for i, (dt, name, applies) in enumerate(hol_samples):
    r = 29 + i
    ws_c.cell(r, 2, dt).number_format = "DD-MMM-YYYY"
    ws_c.cell(r, 3, name)
    ws_c.cell(r, 4, applies)
    for col in range(2, 5):
        ws_c.cell(r, col).font = font_ink
        ws_c.cell(r, col).border = thin
        ws_c.cell(r, col).fill = alt_fill(i)
        ws_c.cell(r, col).alignment = center if col != 3 else left

# Leave policy
ws_c["F27"] = "LEAVE POLICY (annual entitlement days)"
ws_c.merge_cells("F27:I27")
style_header_row(ws_c, 27, 6, 9)
for col, h in enumerate(["Leave Type", "Annual Days", "Carry Forward", "Notes"], 6):
    ws_c.cell(28, col, h).font = font_white_b
    ws_c.cell(28, col).fill = fill_navy
    ws_c.cell(28, col).border = thin
    ws_c.cell(28, col).alignment = center
policy = [
    ("Planned Leave", 12, "Max 5", "Requires prior approval"),
    ("Unplanned Leave", 6, "No", "Inform same day"),
    ("Sick Leave", 10, "No", "Medical certificate > 2 days"),
    ("Vacation Leave", 15, "Max 7", "Plan 15 days ahead"),
]
for i, row in enumerate(policy):
    r = 29 + i
    for col, v in enumerate(row, 6):
        ws_c.cell(r, col, v).font = font_ink
        ws_c.cell(r, col).border = thin
        ws_c.cell(r, col).fill = alt_fill(i)
        ws_c.cell(r, col).alignment = center if col != 6 and col != 9 else left

# Named ranges conceptually via fixed cells for DV formulas:
# Shift codes B7:B13, Att codes F7:F18, Depts B17:B24, etc.

apply_print(ws_c)
ws_c.sheet_properties.tabColor = TEAL

# ═══════════════════════════════════════════════════════════════════════════
# 02_EMPLOYEE_MASTER
# ═══════════════════════════════════════════════════════════════════════════
ws_e = wb.create_sheet("02_Employee_Master")
EM_COLS = [
    ("A", "Employee ID", 12),
    ("B", "Employee Name", 22),
    ("C", "Designation", 24),
    ("D", "Department", 18),
    ("E", "Reporting Manager", 20),
    ("F", "Date of Joining", 14),
    ("G", "Employment Type", 14),
    ("H", "Shift Eligibility", 16),
    ("I", "Contact Number", 14),
    ("J", "Email ID", 30),
    ("K", "Emergency Contact", 32),
    ("L", "Status", 10),
]
banner(ws_e, 12, "EMPLOYEE MASTER REGISTER",
       "Single source of truth  ·  Roster, Attendance, Leave & Dashboard reference this sheet")
for i, (_, title, w) in enumerate(EM_COLS, 1):
    ws_e.column_dimensions[get_column_letter(i)].width = w

style_header_row(ws_e, 5, 1, 12)
for i, (_, title, _) in enumerate(EM_COLS, 1):
    ws_e.cell(5, i, title)

# Data validations
dv_desig = DataValidation(type="list", formula1="'01_Config'!$C$17:$C$24", allow_blank=True)
dv_dept = DataValidation(type="list", formula1="'01_Config'!$B$17:$B$24", allow_blank=True)
dv_etype = DataValidation(type="list", formula1="'01_Config'!$D$17:$D$20", allow_blank=True)
dv_shift = DataValidation(type="list", formula1="'01_Config'!$F$17:$F$20", allow_blank=True)
dv_status = DataValidation(type="list", formula1="'01_Config'!$I$17:$I$18", allow_blank=False)
for dv in (dv_desig, dv_dept, dv_etype, dv_shift, dv_status):
    ws_e.add_data_validation(dv)

MASTER_START = 6
MASTER_END = 5 + max(N_EMP, 40)  # room for growth

for i, emp in enumerate(EMPLOYEES):
    r = MASTER_START + i
    for col, v in enumerate(emp, 1):
        cell = ws_e.cell(r, col, v)
        cell.font = font_ink
        cell.border = thin
        cell.fill = alt_fill(i)
        cell.alignment = center if col in (1, 6, 7, 8, 9, 12) else left
    ws_e.cell(r, 6).number_format = "DD-MMM-YYYY"
    if emp[11] == "Inactive":
        for col in range(1, 13):
            ws_e.cell(r, col).font = Font(name="Calibri", size=10, color="9E9E9E", italic=True)
            ws_e.cell(r, col).fill = fill_gray
    dv_desig.add(ws_e.cell(r, 3))
    dv_dept.add(ws_e.cell(r, 4))
    dv_etype.add(ws_e.cell(r, 7))
    dv_shift.add(ws_e.cell(r, 8))
    dv_status.add(ws_e.cell(r, 12))

# Empty template rows for new hires
for i in range(N_EMP, 40):
    r = MASTER_START + i
    for col in range(1, 13):
        cell = ws_e.cell(r, col, "")
        cell.border = thin
        cell.fill = alt_fill(i)
    dv_desig.add(ws_e.cell(r, 3))
    dv_dept.add(ws_e.cell(r, 4))
    dv_etype.add(ws_e.cell(r, 7))
    dv_shift.add(ws_e.cell(r, 8))
    dv_status.add(ws_e.cell(r, 12))

# Status conditional formatting
ws_e.conditional_formatting.add(
    f"L{MASTER_START}:L{MASTER_END}",
    CellIsRule(operator="equal", formula=['"Active"'], fill=fill_green,
               font=Font(name="Calibri", size=10, bold=True, color=GREEN)),
)
ws_e.conditional_formatting.add(
    f"L{MASTER_START}:L{MASTER_END}",
    CellIsRule(operator="equal", formula=['"Inactive"'], fill=fill_gray,
               font=Font(name="Calibri", size=10, italic=True, color=GRAY)),
)

ws_e.freeze_panes = "C6"
ws_e.auto_filter.ref = f"A5:L{MASTER_END}"
ws_e.row_dimensions[5].height = 28

# Summary strip
sr = MASTER_END + 2
ws_e.cell(sr, 1, "Total rows").font = font_ink_b
ws_e.cell(sr, 2, f'=COUNTA(A{MASTER_START}:A{MASTER_END})')
ws_e.cell(sr, 3, "Active").font = font_ink_b
ws_e.cell(sr, 4, f'=COUNTIF(L{MASTER_START}:L{MASTER_END},"Active")')
ws_e.cell(sr, 5, "Inactive").font = font_ink_b
ws_e.cell(sr, 6, f'=COUNTIF(L{MASTER_START}:L{MASTER_END},"Inactive")')
for col in range(1, 7):
    ws_e.cell(sr, col).border = thin
    ws_e.cell(sr, col).fill = fill_sand

apply_print(ws_e)
ws_e.sheet_properties.tabColor = "1B7A4E"

# ═══════════════════════════════════════════════════════════════════════════
# Helper: default roster pattern for pathology lab
# ═══════════════════════════════════════════════════════════════════════════
def default_roster_code(emp_idx, day):
    """Generate a realistic monthly pattern: WO on rotating days, mostly M/E/N."""
    emp = EMPLOYEES[emp_idx]
    if emp[11] != "Active":
        return ""
    d = date(YEAR, MONTH, day)
    # Sunday weekly off for most; night staff get mid-week WO
    night_eligible = "Night" in emp[7] or emp[7] == "All Shifts"
    # Rotate WO: based on emp index
    wo_weekday = (emp_idx * 2) % 7  # 0=Mon ... 6=Sun
    if d.weekday() == wo_weekday:
        return "WO"
    # Sample PH in month — none critical for Sep in our list for lab ops
    if emp[7] == "Morning Only":
        return "M"
    if emp[7] == "Morning/Evening":
        return "E" if (day + emp_idx) % 3 == 0 else "M"
    if night_eligible and (day + emp_idx) % 7 == 3:
        return "N"
    if (day + emp_idx) % 5 == 0:
        return "E"
    return "M"


def default_att_from_roster(roster_code, day, emp_idx):
    if not roster_code:
        return ""
    if roster_code == "WO":
        return "WO"
    if roster_code == "PH":
        return "H"
    if roster_code == "LV":
        return "PL"
    # Sprinkle some realistic variance for demo
    seed = (emp_idx * 31 + day * 17) % 97
    if seed == 1:
        return "L"
    if seed == 2:
        return "HD"
    if seed == 5 and emp_idx % 7 == 0:
        return "SL"
    if seed == 8 and emp_idx % 5 == 0:
        return "A"
    return "P"


# ═══════════════════════════════════════════════════════════════════════════
# 03_ROSTER
# ═══════════════════════════════════════════════════════════════════════════
ws_r = wb.create_sheet("03_Roster")
# Layout: A EmpID, B Name, C Dept, D Designation, then days 1..31, then WO count, OT hrs, Backup, Swap notes
day_cols_start = 5  # column E = day 1
meta_after = day_cols_start + MAX_DAYS  # first summary col after days
# Columns after days: WO Days | OT Hours | Backup Resource | Shift Swap Notes | Remarks
last_col_r = meta_after + 4  # 5 meta cols (0..4) → meta_after+0 .. +4

banner(ws_r, last_col_r, "MONTHLY SHIFT ROSTER",
       "Pathology Lab scheduling  ·  Change Month (B5) & Year (D5) for a new period  ·  M/E/N/WO/PH/LV/TR")

# Period controls — THIS is what you change each month
ws_r["A5"] = "Month"
ws_r["B5"] = MONTH
ws_r["C5"] = "Year"
ws_r["D5"] = YEAR
for addr in ("A5", "C5"):
    ws_r[addr].font = font_white_b
    ws_r[addr].fill = fill_teal
    ws_r[addr].alignment = center
    ws_r[addr].border = thin
for addr in ("B5", "D5"):
    ws_r[addr].font = font_navy_b
    ws_r[addr].fill = fill_amber
    ws_r[addr].alignment = center
    ws_r[addr].border = thin
ws_r["E5"] = (
    "NEW MONTH: change B5 & D5 → use Week 1–5 buttons below to enter roster week-by-week → Full Month auto-updates. "
    "Grey columns = day does not exist in that month."
)
ws_r.merge_cells(start_row=5, start_column=5, end_row=5, end_column=min(last_col_r, 14))
ws_r["E5"].font = font_small
ws_r["E5"].alignment = left

# Clickable week navigation "buttons"
def style_nav_button(cell, label, target_sheet, fill_color):
    cell.value = label
    cell.hyperlink = f"#{target_sheet}!A1"
    cell.font = Font(name="Calibri", size=10, bold=True, color=WHITE, underline="single")
    cell.fill = PatternFill("solid", fgColor=fill_color)
    cell.alignment = center
    cell.border = thin

WEEK_BTN_COLORS = ["0E7C7B", "1565C0", "5E35B1", "C7522A", "B78103"]
# Row 4 reserved for nav buttons (above period row)
ws_r.row_dimensions[4].height = 22
ws_r.cell(4, 1, "GO →").font = font_white_b
ws_r.cell(4, 1).fill = fill_navy
ws_r.cell(4, 1).alignment = center
ws_r.cell(4, 1).border = thin
style_nav_button(ws_r.cell(4, 2), "Full Month", "03_Roster", NAVY)
style_nav_button(ws_r.cell(4, 3), "▶ Week 1", "W1_Roster", WEEK_BTN_COLORS[0])
style_nav_button(ws_r.cell(4, 4), "▶ Week 2", "W2_Roster", WEEK_BTN_COLORS[1])
style_nav_button(ws_r.cell(4, 5), "▶ Week 3", "W3_Roster", WEEK_BTN_COLORS[2])
style_nav_button(ws_r.cell(4, 6), "▶ Week 4", "W4_Roster", WEEK_BTN_COLORS[3])
style_nav_button(ws_r.cell(4, 7), "▶ Week 5", "W5_Roster", WEEK_BTN_COLORS[4])
ws_r.cell(4, 8, "Click a week button to open that week’s roster (edit there — Full Month syncs automatically)")
ws_r.merge_cells("H4:N4")
ws_r["H4"].font = font_small
ws_r["H4"].alignment = left

# Header row 6: Emp meta + day numbers; row 7: weekday letters (formula-driven from B5/D5)
headers_left = ["Emp ID", "Employee Name", "Department", "Designation"]
for i, h in enumerate(headers_left, 1):
    ws_r.cell(6, i, h).font = font_white_b
    ws_r.cell(6, i).fill = fill_teal
    ws_r.cell(6, i).alignment = center
    ws_r.cell(6, i).border = thin
    ws_r.cell(7, i, "").fill = fill_navy
    ws_r.cell(7, i).border = thin

ws_r.column_dimensions["A"].width = 10
ws_r.column_dimensions["B"].width = 20
ws_r.column_dimensions["C"].width = 16
ws_r.column_dimensions["D"].width = 22

for day in range(1, MAX_DAYS + 1):
    col = day_cols_start + day - 1
    letter = get_column_letter(col)
    cell = ws_r.cell(6, col, day)
    cell.font = font_white_b
    cell.alignment = center
    cell.border = thin
    cell.fill = fill_navy
    # Weekday from Month/Year — blank if day invalid for selected month
    # DATE($D$5,$B$5+1,0) = last day of month B5/D5
    wcell = ws_r.cell(
        7, col,
        f'=IF({letter}$6>DAY(DATE($D$5,$B$5+1,0)),"",TEXT(DATE($D$5,$B$5,{letter}$6),"DDD"))',
    )
    wcell.font = Font(name="Calibri", size=8, bold=True, color=WHITE)
    wcell.alignment = center
    wcell.border = thin
    wcell.fill = fill_navy
    ws_r.column_dimensions[letter].width = 3.5

meta_headers = ["WO Days", "OT Hours", "Backup Resource", "Shift Swap / Notes", "Remarks"]
meta_widths = [9, 9, 18, 22, 18]
for i, (h, w) in enumerate(zip(meta_headers, meta_widths)):
    col = meta_after + i
    ws_r.cell(6, col, h).font = font_white_b
    ws_r.cell(6, col).fill = fill_coral
    ws_r.cell(6, col).alignment = center
    ws_r.cell(6, col).border = thin
    ws_r.cell(7, col, "").fill = fill_navy
    ws_r.cell(7, col).border = thin
    ws_r.column_dimensions[get_column_letter(col)].width = w

ws_r.row_dimensions[6].height = 22
ws_r.row_dimensions[7].height = 14

dv_roster = DataValidation(
    type="list",
    formula1='"M,E,N,WO,PH,LV,TR"',
    allow_blank=True,
)
dv_roster.prompt = "M Morning · E Evening · N Night · WO Off · PH Holiday · LV Leave · TR Training"
dv_roster.promptTitle = "Shift code"
ws_r.add_data_validation(dv_roster)

# Backup DV from employee names
dv_backup = DataValidation(
    type="list",
    formula1=f"'02_Employee_Master'!$B${MASTER_START}:$B${MASTER_START + N_EMP - 1}",
    allow_blank=True,
)
ws_r.add_data_validation(dv_backup)

ROSTER_DATA_START = 8
ROSTER_DATA_END = ROSTER_DATA_START + N_EMP - 1

# ── Create Week 1–5 roster sheets FIRST (editable); Full Month pulls from them ──
WEEK_DEFS = [
    (1, 1, 7),    # Week 1: days 1–7
    (2, 8, 14),   # Week 2: days 8–14
    (3, 15, 21),  # Week 3: days 15–21
    (4, 22, 28),  # Week 4: days 22–28
    (5, 29, 31),  # Week 5: days 29–31
]
week_sheets = {}

for week_num, d_start, d_end in WEEK_DEFS:
    n_days = d_end - d_start + 1
    ws_w = wb.create_sheet(f"W{week_num}_Roster")
    week_sheets[week_num] = ws_w
    last_w = 4 + n_days + 2  # meta: Backup, Notes
    banner(
        ws_w, last_w,
        f"WEEK {week_num} ROSTER  ·  Days {d_start}–{d_end}",
        f"Edit shifts here  ·  Syncs to Full Month automatically  ·  Period = Roster Month/Year",
    )
    # Nav buttons
    ws_w.row_dimensions[4].height = 22
    ws_w.cell(4, 1, "GO →").font = font_white_b
    ws_w.cell(4, 1).fill = fill_navy
    ws_w.cell(4, 1).alignment = center
    ws_w.cell(4, 1).border = thin
    style_nav_button(ws_w.cell(4, 2), "Full Month", "03_Roster", NAVY)
    for wn in range(1, 6):
        style_nav_button(
            ws_w.cell(4, 2 + wn),
            f"{'●' if wn == week_num else '▶'} W{wn}",
            f"W{wn}_Roster",
            WEEK_BTN_COLORS[wn - 1],
        )
    ws_w.cell(4, 8, f"You are on Week {week_num}  |  Drop-down: M E N WO PH LV TR")
    ws_w.merge_cells("H4:L4")
    ws_w["H4"].font = font_small

    ws_w["A5"] = "Month"
    ws_w["B5"] = "='03_Roster'!B5"
    ws_w["C5"] = "Year"
    ws_w["D5"] = "='03_Roster'!D5"
    for addr in ("A5", "C5"):
        ws_w[addr].font = font_white_b
        ws_w[addr].fill = fill_teal
        ws_w[addr].border = thin
        ws_w[addr].alignment = center
    for addr in ("B5", "D5"):
        ws_w[addr].font = font_navy_b
        ws_w[addr].fill = fill_amber
        ws_w[addr].border = thin
        ws_w[addr].alignment = center

    for i, h in enumerate(headers_left, 1):
        ws_w.cell(6, i, h).font = font_white_b
        ws_w.cell(6, i).fill = fill_teal
        ws_w.cell(6, i).alignment = center
        ws_w.cell(6, i).border = thin
        ws_w.cell(7, i).fill = fill_navy
        ws_w.cell(7, i).border = thin

    ws_w.column_dimensions["A"].width = 10
    ws_w.column_dimensions["B"].width = 20
    ws_w.column_dimensions["C"].width = 16
    ws_w.column_dimensions["D"].width = 22

    dv_w = DataValidation(type="list", formula1='"M,E,N,WO,PH,LV,TR"', allow_blank=True)
    dv_w.promptTitle = f"Week {week_num} shift"
    dv_w.prompt = "M Morning · E Evening · N Night · WO Off · PH · LV · TR"
    ws_w.add_data_validation(dv_w)

    for di, day in enumerate(range(d_start, d_end + 1)):
        col = 5 + di
        letter = get_column_letter(col)
        # Day number header
        ws_w.cell(6, col, day).font = font_white_b
        ws_w.cell(6, col).fill = PatternFill("solid", fgColor=WEEK_BTN_COLORS[week_num - 1])
        ws_w.cell(6, col).alignment = center
        ws_w.cell(6, col).border = thin
        # Weekday from month/year
        ws_w.cell(
            7, col,
            f'=IF({letter}$6>DAY(DATE(\'03_Roster\'!$D$5,\'03_Roster\'!$B$5+1,0)),"",'
            f'TEXT(DATE(\'03_Roster\'!$D$5,\'03_Roster\'!$B$5,{letter}$6),"DDD"))',
        )
        ws_w.cell(7, col).font = Font(name="Calibri", size=8, bold=True, color=WHITE)
        ws_w.cell(7, col).fill = fill_navy
        ws_w.cell(7, col).alignment = center
        ws_w.cell(7, col).border = thin
        ws_w.column_dimensions[letter].width = 8

    # Backup / notes for the week
    for col, h, w in [(5 + n_days, "Backup", 18), (6 + n_days, "Week notes", 28)]:
        ws_w.cell(6, col, h).font = font_white_b
        ws_w.cell(6, col).fill = fill_coral
        ws_w.cell(6, col).alignment = center
        ws_w.cell(6, col).border = thin
        ws_w.cell(7, col).fill = fill_navy
        ws_w.cell(7, col).border = thin
        ws_w.column_dimensions[get_column_letter(col)].width = w

    for i, emp in enumerate(EMPLOYEES):
        r = ROSTER_DATA_START + i
        ws_w.cell(r, 1, f"='02_Employee_Master'!A{MASTER_START + i}")
        ws_w.cell(r, 2, f"='02_Employee_Master'!B{MASTER_START + i}")
        ws_w.cell(r, 3, f"='02_Employee_Master'!D{MASTER_START + i}")
        ws_w.cell(r, 4, f"='02_Employee_Master'!C{MASTER_START + i}")
        for col in range(1, 5):
            ws_w.cell(r, col).font = font_ink
            ws_w.cell(r, col).border = thin
            ws_w.cell(r, col).fill = alt_fill(i)
            ws_w.cell(r, col).alignment = left if col > 1 else center

        for di, day in enumerate(range(d_start, d_end + 1)):
            col = 5 + di
            if emp[11] == "Active" and day <= DAYS_IN_MONTH:
                code = default_roster_code(i, day)
            else:
                code = ""
            cell = ws_w.cell(r, col, code)
            cell.font = Font(name="Calibri", size=11, bold=True, color=INK)
            cell.alignment = center
            cell.border = thin
            cell.fill = alt_fill(i)
            dv_w.add(cell)

        # Backup / notes
        backup = ""
        if emp[11] == "Active" and i % 6 == 0 and i + 1 < N_EMP:
            backup = EMPLOYEES[(i + 1) % N_EMP][1]
        ws_w.cell(r, 5 + n_days, backup)
        ws_w.cell(r, 6 + n_days, "")
        for col in (5 + n_days, 6 + n_days):
            ws_w.cell(r, col).font = font_ink
            ws_w.cell(r, col).border = thin
            ws_w.cell(r, col).fill = alt_fill(i)
            ws_w.cell(r, col).alignment = center
        ws_w.row_dimensions[r].height = 20

    # CF for week codes
    w_range = f"E{ROSTER_DATA_START}:{get_column_letter(4 + n_days)}{ROSTER_DATA_END}"
    for code, bg, fg in [
        ("M", "E3F2FD", "1565C0"),
        ("E", "FFF8E1", "F9A825"),
        ("N", "EDE7F6", "5E35B1"),
        ("WO", "ECEFF1", "607D8B"),
        ("PH", "FFECB3", "FF6F00"),
        ("LV", "F3E5F5", "7B1FA2"),
        ("TR", "E0F2F1", "00695C"),
    ]:
        ws_w.conditional_formatting.add(
            w_range,
            CellIsRule(operator="equal", formula=[f'"{code}"'],
                       fill=PatternFill("solid", fgColor=bg),
                       font=Font(name="Calibri", size=11, bold=True, color=fg)),
        )
    # Grey invalid days
    for di, day in enumerate(range(d_start, d_end + 1)):
        col = 5 + di
        letter = get_column_letter(col)
        ws_w.conditional_formatting.add(
            f"{letter}7:{letter}{ROSTER_DATA_END}",
            FormulaRule(
                formula=[f"{letter}$6>DAY(DATE('03_Roster'!$D$5,'03_Roster'!$B$5+1,0))"],
                fill=PatternFill("solid", fgColor="F0F0F0"),
                font=Font(name="Calibri", size=11, color="BDBDBD"),
            ),
        )

    # Headcount strip
    tot_w = ROSTER_DATA_END + 1
    ws_w.merge_cells(start_row=tot_w, start_column=1, end_row=tot_w, end_column=4)
    ws_w.cell(tot_w, 1, "On duty (M+E+N)")
    ws_w.cell(tot_w, 1).font = font_white_b
    ws_w.cell(tot_w, 1).fill = fill_navy
    ws_w.cell(tot_w, 1).alignment = Alignment(horizontal="right", vertical="center", indent=1)
    for col in range(1, 5):
        ws_w.cell(tot_w, col).fill = fill_navy
        ws_w.cell(tot_w, col).border = thin
    for di in range(n_days):
        col = 5 + di
        letter = get_column_letter(col)
        ws_w.cell(
            tot_w, col,
            f'=COUNTIF({letter}{ROSTER_DATA_START}:{letter}{ROSTER_DATA_END},"M")'
            f'+COUNTIF({letter}{ROSTER_DATA_START}:{letter}{ROSTER_DATA_END},"E")'
            f'+COUNTIF({letter}{ROSTER_DATA_START}:{letter}{ROSTER_DATA_END},"N")',
        )
        ws_w.cell(tot_w, col).font = Font(name="Calibri", size=10, bold=True, color=WHITE)
        ws_w.cell(tot_w, col).fill = fill_navy
        ws_w.cell(tot_w, col).alignment = center
        ws_w.cell(tot_w, col).border = thin

    ws_w.freeze_panes = "E8"
    apply_print(ws_w)
    ws_w.sheet_properties.tabColor = WEEK_BTN_COLORS[week_num - 1]

# Helper: map calendar day → week sheet cell
def week_cell_ref(day, row):
    week_num = (day - 1) // 7 + 1
    day_in_week = (day - 1) % 7  # 0-based index within week
    col = 5 + day_in_week
    return f"'W{week_num}_Roster'!{get_column_letter(col)}{row}"

# Fill Full Month from week sheets (formulas — edit on Week tabs)
for i, emp in enumerate(EMPLOYEES):
    r = ROSTER_DATA_START + i
    ws_r.cell(r, 1, f"='02_Employee_Master'!A{MASTER_START + i}")
    ws_r.cell(r, 2, f"='02_Employee_Master'!B{MASTER_START + i}")
    ws_r.cell(r, 3, f"='02_Employee_Master'!D{MASTER_START + i}")
    ws_r.cell(r, 4, f"='02_Employee_Master'!C{MASTER_START + i}")
    for col in range(1, 5):
        ws_r.cell(r, col).font = font_ink
        ws_r.cell(r, col).border = thin
        ws_r.cell(r, col).fill = alt_fill(i)
        ws_r.cell(r, col).alignment = left if col > 1 else center

    for day in range(1, MAX_DAYS + 1):
        col = day_cols_start + day - 1
        cell = ws_r.cell(r, col, f"={week_cell_ref(day, r)}")
        cell.font = Font(name="Calibri", size=9, bold=True, color=INK)
        cell.alignment = center
        cell.border = thin
        cell.fill = alt_fill(i)
        # No DV on monthly — edit on week sheets (avoids conflicting with formulas)

    day_range = f"{get_column_letter(day_cols_start)}{r}:{get_column_letter(day_cols_start + MAX_DAYS - 1)}{r}"
    ws_r.cell(r, meta_after, f'=COUNTIF({day_range},"WO")')
    ws_r.cell(r, meta_after + 1, 0 if emp[11] == "Active" else "")
    backup = ""
    if emp[11] == "Active" and i % 6 == 0 and i + 1 < N_EMP:
        backup = EMPLOYEES[(i + 1) % N_EMP][1]
    ws_r.cell(r, meta_after + 2, backup)
    ws_r.cell(r, meta_after + 3, "")
    ws_r.cell(r, meta_after + 4, "")
    for j in range(5):
        cell = ws_r.cell(r, meta_after + j)
        cell.font = font_ink
        cell.border = thin
        cell.fill = alt_fill(i)
        cell.alignment = center
    dv_backup.add(ws_r.cell(r, meta_after + 2))
    ws_r.row_dimensions[r].height = 18

# Note under monthly grid
note_row = ROSTER_DATA_END + 5
ws_r.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=8)
ws_r.cell(
    note_row, 1,
    "Note: Day cells on Full Month are linked from Week 1–5 sheets. Enter / change shifts on W1_Roster … W5_Roster (use the buttons above).",
)
ws_r.cell(note_row, 1).font = font_small
ws_r.cell(note_row, 1).fill = fill_sand

# Conditional formatting for roster codes
roster_range = f"{get_column_letter(day_cols_start)}{ROSTER_DATA_START}:{get_column_letter(day_cols_start + MAX_DAYS - 1)}{ROSTER_DATA_END}"
roster_cf = [
    ("M", "E3F2FD", "1565C0"),
    ("E", "FFF8E1", "F9A825"),
    ("N", "EDE7F6", "5E35B1"),
    ("WO", "ECEFF1", "607D8B"),
    ("PH", "FFECB3", "FF6F00"),
    ("LV", "F3E5F5", "7B1FA2"),
    ("TR", "E0F2F1", "00695C"),
]
for code, bg, fg in roster_cf:
    ws_r.conditional_formatting.add(
        roster_range,
        CellIsRule(operator="equal", formula=[f'"{code}"'],
                   fill=PatternFill("solid", fgColor=bg),
                   font=Font(name="Calibri", size=9, bold=True, color=fg)),
    )

# Grey out invalid day columns (day number > days in selected month)
invalid_fill = PatternFill("solid", fgColor="F0F0F0")
for day in range(1, MAX_DAYS + 1):
    col = day_cols_start + day - 1
    letter = get_column_letter(col)
    # Apply to header weekday + data rows when day is invalid
    ws_r.conditional_formatting.add(
        f"{letter}7:{letter}{ROSTER_DATA_END}",
        FormulaRule(
            formula=[f"{letter}$6>DAY(DATE($D$5,$B$5+1,0))"],
            fill=invalid_fill,
            font=Font(name="Calibri", size=9, color="BDBDBD"),
        ),
    )

# Daily shift headcount row
tot = ROSTER_DATA_END + 1
ws_r.cell(tot, 1, "").fill = fill_navy
ws_r.merge_cells(start_row=tot, start_column=1, end_row=tot, end_column=4)
ws_r.cell(tot, 1, "Morning (M) headcount")
ws_r.cell(tot, 1).font = font_white_b
ws_r.cell(tot, 1).fill = fill_navy
ws_r.cell(tot, 1).alignment = Alignment(horizontal="right", vertical="center", indent=1)
for col in range(1, 5):
    ws_r.cell(tot, col).fill = fill_navy
    ws_r.cell(tot, col).border = thin
for day in range(1, MAX_DAYS + 1):
    col = day_cols_start + day - 1
    letter = get_column_letter(col)
    ws_r.cell(
        tot, col,
        f'=IF({letter}$6>DAY(DATE($D$5,$B$5+1,0)),"",COUNTIF({letter}{ROSTER_DATA_START}:{letter}{ROSTER_DATA_END},"M"))',
    )
    ws_r.cell(tot, col).font = Font(name="Calibri", size=8, bold=True, color=WHITE)
    ws_r.cell(tot, col).fill = fill_navy
    ws_r.cell(tot, col).alignment = center
    ws_r.cell(tot, col).border = thin

for label, code, offset, bg in [
    ("Evening (E) headcount", "E", 1, TEAL),
    ("Night (N) headcount", "N", 2, "5E35B1"),
]:
    rr = tot + offset
    ws_r.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=4)
    ws_r.cell(rr, 1, label).font = font_white_b
    ws_r.cell(rr, 1).fill = PatternFill("solid", fgColor=bg)
    ws_r.cell(rr, 1).alignment = Alignment(horizontal="right", vertical="center", indent=1)
    for col in range(1, 5):
        ws_r.cell(rr, col).fill = PatternFill("solid", fgColor=bg)
        ws_r.cell(rr, col).border = thin
    for day in range(1, MAX_DAYS + 1):
        col = day_cols_start + day - 1
        letter = get_column_letter(col)
        ws_r.cell(
            rr, col,
            f'=IF({letter}$6>DAY(DATE($D$5,$B$5+1,0)),"",COUNTIF({letter}{ROSTER_DATA_START}:{letter}{ROSTER_DATA_END},"{code}"))',
        )
        ws_r.cell(rr, col).font = Font(name="Calibri", size=8, bold=True, color=WHITE)
        ws_r.cell(rr, col).fill = PatternFill("solid", fgColor=bg)
        ws_r.cell(rr, col).alignment = center
        ws_r.cell(rr, col).border = thin

ws_r.freeze_panes = "E8"
apply_print(ws_r)
ws_r.sheet_properties.tabColor = "1565C0"

# ═══════════════════════════════════════════════════════════════════════════
# 04_ATTENDANCE
# ═══════════════════════════════════════════════════════════════════════════
ws_a = wb.create_sheet("04_Attendance")
# Similar grid: Emp meta + days 1–31 + summary: Present, Absent, Late, Leave, WO, OT Hrs, Att %
att_meta_start = day_cols_start + MAX_DAYS
att_meta_headers = ["Present", "Absent", "Late", "Half Day", "Leave", "WO/H", "OT Hrs", "Att %"]
last_col_a = att_meta_start + len(att_meta_headers) - 1

banner(ws_a, last_col_a, "DAILY ATTENDANCE REGISTER",
       "Period follows Roster Month/Year  ·  Clear marks when month changes  ·  Color-coded statuses")

ws_a["A5"] = "Period"
ws_a["B5"] = "='03_Roster'!B5"  # month
ws_a["C5"] = "='03_Roster'!D5"  # year
ws_a["D5"] = "=DATE(C5,B5,1)"
ws_a["D5"].number_format = "MMMM YYYY"
for addr in ("A5",):
    ws_a[addr].font = font_white_b
    ws_a[addr].fill = fill_teal
    ws_a[addr].border = thin
for addr in ("B5", "C5", "D5"):
    ws_a[addr].font = font_navy_b
    ws_a[addr].fill = fill_light
    ws_a[addr].border = thin
    ws_a[addr].alignment = center

ws_a["E5"] = "Legend: P Present · A Absent · L Late · HD Half Day · WFO Work From Office · PL/UL/VL/SL Leave · H Holiday · WO Off · OT Overtime  |  Grey = invalid day for month"
ws_a.merge_cells(start_row=5, start_column=5, end_row=5, end_column=min(14, last_col_a))
ws_a["E5"].font = font_small

for i, h in enumerate(headers_left, 1):
    ws_a.cell(6, i, h).font = font_white_b
    ws_a.cell(6, i).fill = fill_teal
    ws_a.cell(6, i).alignment = center
    ws_a.cell(6, i).border = thin
    ws_a.cell(7, i).fill = fill_navy
    ws_a.cell(7, i).border = thin

ws_a.column_dimensions["A"].width = 10
ws_a.column_dimensions["B"].width = 20
ws_a.column_dimensions["C"].width = 16
ws_a.column_dimensions["D"].width = 22

for day in range(1, MAX_DAYS + 1):
    col = day_cols_start + day - 1
    letter = get_column_letter(col)
    cell = ws_a.cell(6, col, day)
    cell.font = font_white_b
    cell.alignment = center
    cell.border = thin
    cell.fill = fill_navy
    # Weekday follows Roster month/year
    wcell = ws_a.cell(
        7, col,
        f"=IF({letter}$6>DAY(DATE('03_Roster'!$D$5,'03_Roster'!$B$5+1,0)),\"\","
        f"TEXT(DATE('03_Roster'!$D$5,'03_Roster'!$B$5,{letter}$6),\"DDD\"))",
    )
    wcell.font = Font(name="Calibri", size=8, bold=True, color=WHITE)
    wcell.alignment = center
    wcell.border = thin
    wcell.fill = fill_navy
    ws_a.column_dimensions[letter].width = 3.5

for i, h in enumerate(att_meta_headers):
    col = att_meta_start + i
    ws_a.cell(6, col, h).font = font_white_b
    ws_a.cell(6, col).fill = fill_coral
    ws_a.cell(6, col).alignment = center
    ws_a.cell(6, col).border = thin
    ws_a.cell(7, col).fill = fill_navy
    ws_a.cell(7, col).border = thin
    ws_a.column_dimensions[get_column_letter(col)].width = 9 if i < 7 else 8

dv_att = DataValidation(
    type="list",
    formula1='"P,A,L,HD,WFO,PL,UL,VL,SL,H,WO,OT"',
    allow_blank=True,
)
dv_att.promptTitle = "Attendance"
dv_att.prompt = "Select attendance status"
ws_a.add_data_validation(dv_att)

ATT_START = 8
for i, emp in enumerate(EMPLOYEES):
    r = ATT_START + i
    ws_a.cell(r, 1, f"='02_Employee_Master'!A{MASTER_START + i}")
    ws_a.cell(r, 2, f"='02_Employee_Master'!B{MASTER_START + i}")
    ws_a.cell(r, 3, f"='02_Employee_Master'!D{MASTER_START + i}")
    ws_a.cell(r, 4, f"='02_Employee_Master'!C{MASTER_START + i}")
    for col in range(1, 5):
        ws_a.cell(r, col).font = font_ink
        ws_a.cell(r, col).border = thin
        ws_a.cell(r, col).fill = alt_fill(i)
        ws_a.cell(r, col).alignment = left if col > 1 else center

    for day in range(1, MAX_DAYS + 1):
        col = day_cols_start + day - 1
        if emp[11] == "Active" and day <= DAYS_IN_MONTH:
            roster_code = default_roster_code(i, day)
            mark = default_att_from_roster(roster_code, day, i)
        else:
            mark = ""
        cell = ws_a.cell(r, col, mark)
        cell.font = Font(name="Calibri", size=8, bold=True)
        cell.alignment = center
        cell.border = thin
        cell.fill = alt_fill(i)
        dv_att.add(cell)

    day_rng = f"{get_column_letter(day_cols_start)}{r}:{get_column_letter(day_cols_start + MAX_DAYS - 1)}{r}"
    ws_a.cell(r, att_meta_start, f'=COUNTIF({day_rng},"P")+COUNTIF({day_rng},"L")+COUNTIF({day_rng},"WFO")+COUNTIF({day_rng},"OT")')
    ws_a.cell(r, att_meta_start + 1, f'=COUNTIF({day_rng},"A")')
    ws_a.cell(r, att_meta_start + 2, f'=COUNTIF({day_rng},"L")')
    ws_a.cell(r, att_meta_start + 3, f'=COUNTIF({day_rng},"HD")')
    ws_a.cell(r, att_meta_start + 4, f'=COUNTIF({day_rng},"PL")+COUNTIF({day_rng},"UL")+COUNTIF({day_rng},"VL")+COUNTIF({day_rng},"SL")')
    ws_a.cell(r, att_meta_start + 5, f'=COUNTIF({day_rng},"WO")+COUNTIF({day_rng},"H")')
    ws_a.cell(r, att_meta_start + 6, f"='03_Roster'!{get_column_letter(meta_after + 1)}{ROSTER_DATA_START + i}")
    ws_a.cell(
        r, att_meta_start + 7,
        f'=IFERROR(({get_column_letter(att_meta_start)}{r}+{get_column_letter(att_meta_start + 3)}{r}*0.5)'
        f'/(COUNTA({day_rng})-{get_column_letter(att_meta_start + 5)}{r}),"")',
    )
    ws_a.cell(r, att_meta_start + 7).number_format = "0%"
    for j in range(8):
        cell = ws_a.cell(r, att_meta_start + j)
        cell.font = font_ink_b
        cell.border = thin
        cell.fill = alt_fill(i)
        cell.alignment = center
    ws_a.row_dimensions[r].height = 18

ATT_END = ATT_START + N_EMP - 1

att_range = f"{get_column_letter(day_cols_start)}{ATT_START}:{get_column_letter(day_cols_start + MAX_DAYS - 1)}{ATT_END}"
for code, meaning, bg, fg in ATT_CODES:
    ws_a.conditional_formatting.add(
        att_range,
        CellIsRule(operator="equal", formula=[f'"{code}"'],
                   fill=PatternFill("solid", fgColor=bg),
                   font=Font(name="Calibri", size=8, bold=True, color=fg)),
    )

# Grey invalid days
for day in range(1, MAX_DAYS + 1):
    col = day_cols_start + day - 1
    letter = get_column_letter(col)
    ws_a.conditional_formatting.add(
        f"{letter}7:{letter}{ATT_END}",
        FormulaRule(
            formula=[f"{letter}$6>DAY(DATE('03_Roster'!$D$5,'03_Roster'!$B$5+1,0))"],
            fill=invalid_fill,
            font=Font(name="Calibri", size=8, color="BDBDBD"),
        ),
    )

pct_col_letter = get_column_letter(att_meta_start + 7)
ws_a.conditional_formatting.add(
    f"{pct_col_letter}{ATT_START}:{pct_col_letter}{ATT_END}",
    ColorScaleRule(start_type="num", start_value=0.7, start_color="F8D7DA",
                   mid_type="num", mid_value=0.9, mid_color="FFF3CD",
                   end_type="num", end_value=1, end_color="D4EDDA"),
)

# Daily present count
tot_a = ATT_END + 1
ws_a.merge_cells(start_row=tot_a, start_column=1, end_row=tot_a, end_column=4)
ws_a.cell(tot_a, 1, "Present headcount (P+L+WFO+OT)")
ws_a.cell(tot_a, 1).font = font_white_b
ws_a.cell(tot_a, 1).fill = fill_navy
ws_a.cell(tot_a, 1).alignment = Alignment(horizontal="right", vertical="center", indent=1)
for col in range(1, 5):
    ws_a.cell(tot_a, col).fill = fill_navy
    ws_a.cell(tot_a, col).border = thin
for day in range(1, MAX_DAYS + 1):
    col = day_cols_start + day - 1
    letter = get_column_letter(col)
    ws_a.cell(
        tot_a, col,
        f'=IF({letter}$6>DAY(DATE(\'03_Roster\'!$D$5,\'03_Roster\'!$B$5+1,0)),"",'
        f'COUNTIF({letter}{ATT_START}:{letter}{ATT_END},"P")'
        f'+COUNTIF({letter}{ATT_START}:{letter}{ATT_END},"L")'
        f'+COUNTIF({letter}{ATT_START}:{letter}{ATT_END},"WFO")'
        f'+COUNTIF({letter}{ATT_START}:{letter}{ATT_END},"OT"))',
    )
    ws_a.cell(tot_a, col).font = Font(name="Calibri", size=8, bold=True, color=WHITE)
    ws_a.cell(tot_a, col).fill = fill_navy
    ws_a.cell(tot_a, col).alignment = center
    ws_a.cell(tot_a, col).border = thin

ws_a.freeze_panes = "E8"
apply_print(ws_a)
ws_a.sheet_properties.tabColor = GREEN

# ═══════════════════════════════════════════════════════════════════════════
# 05_LEAVE
# ═══════════════════════════════════════════════════════════════════════════
ws_l = wb.create_sheet("05_Leave")
banner(ws_l, 14, "LEAVE MANAGEMENT",
       "Applications · Balances · Approvals  ·  Entitlements from Config leave policy")

# Leave balance summary (employee-wise)
bal_headers = [
    "Emp ID", "Employee Name", "Department",
    "PL Entitled", "PL Used", "PL Balance",
    "UL Entitled", "UL Used", "UL Balance",
    "SL Entitled", "SL Used", "SL Balance",
    "VL Entitled", "VL Used", "VL Balance",
]
ws_l["A5"] = "LEAVE BALANCE SUMMARY (auto from policy + applications)"
ws_l.merge_cells("A5:O5")
style_header_row(ws_l, 5, 1, 15)
for i, h in enumerate(bal_headers, 1):
    ws_l.cell(6, i, h).font = font_white_b
    ws_l.cell(6, i).fill = fill_navy
    ws_l.cell(6, i).alignment = center
    ws_l.cell(6, i).border = thin

# Column widths for leave
for i, w in enumerate([10, 20, 16, 10, 8, 10, 10, 8, 10, 10, 8, 10, 10, 8, 10], 1):
    ws_l.column_dimensions[get_column_letter(i)].width = w

# Entitlements from config: Planned F29=12, Unplanned F30=6, Sick F31=10, Vacation F32=15
# Actually policy is in F29:G32 — G column has days
# Planned Leave row 29 G=12, Unplanned 30, Sick 31, Vacation 32

LEAVE_APP_START = 30  # applications table starts later
LEAVE_BAL_START = 7

for i, emp in enumerate(EMPLOYEES):
    r = LEAVE_BAL_START + i
    ws_l.cell(r, 1, f"='02_Employee_Master'!A{MASTER_START + i}")
    ws_l.cell(r, 2, f"='02_Employee_Master'!B{MASTER_START + i}")
    ws_l.cell(r, 3, f"='02_Employee_Master'!D{MASTER_START + i}")
    # Entitlements
    ws_l.cell(r, 4, "='01_Config'!G29")  # PL
    ws_l.cell(r, 7, "='01_Config'!G30")  # UL
    ws_l.cell(r, 10, "='01_Config'!G31")  # SL
    ws_l.cell(r, 13, "='01_Config'!G32")  # VL
    # Used = COUNTIFS on applications where Emp ID match, type match, status Approved
    # Applications will be in rows LEAVE_APP_START+...
    # Columns: A EmpID, D Leave Type, H Status, E Days
    app_end = LEAVE_APP_START + 49
    eid = f"$A{r}"
    ws_l.cell(r, 5, f'=SUMIFS($E${LEAVE_APP_START}:$E${app_end},$A${LEAVE_APP_START}:$A${app_end},A{r},$D${LEAVE_APP_START}:$D${app_end},"Planned Leave",$H${LEAVE_APP_START}:$H${app_end},"Approved")')
    ws_l.cell(r, 8, f'=SUMIFS($E${LEAVE_APP_START}:$E${app_end},$A${LEAVE_APP_START}:$A${app_end},A{r},$D${LEAVE_APP_START}:$D${app_end},"Unplanned Leave",$H${LEAVE_APP_START}:$H${app_end},"Approved")')
    ws_l.cell(r, 11, f'=SUMIFS($E${LEAVE_APP_START}:$E${app_end},$A${LEAVE_APP_START}:$A${app_end},A{r},$D${LEAVE_APP_START}:$D${app_end},"Sick Leave",$H${LEAVE_APP_START}:$H${app_end},"Approved")')
    ws_l.cell(r, 14, f'=SUMIFS($E${LEAVE_APP_START}:$E${app_end},$A${LEAVE_APP_START}:$A${app_end},A{r},$D${LEAVE_APP_START}:$D${app_end},"Vacation Leave",$H${LEAVE_APP_START}:$H${app_end},"Approved")')
    # Balances
    ws_l.cell(r, 6, f"=D{r}-E{r}")
    ws_l.cell(r, 9, f"=G{r}-H{r}")
    ws_l.cell(r, 12, f"=J{r}-K{r}")
    ws_l.cell(r, 15, f"=M{r}-N{r}")
    for col in range(1, 16):
        cell = ws_l.cell(r, col)
        cell.font = font_ink
        cell.border = thin
        cell.fill = alt_fill(i)
        cell.alignment = center if col != 2 and col != 3 else left

LEAVE_BAL_END = LEAVE_BAL_START + N_EMP - 1

# Balance conditional — low balance amber
for col in (6, 9, 12, 15):
    letter = get_column_letter(col)
    ws_l.conditional_formatting.add(
        f"{letter}{LEAVE_BAL_START}:{letter}{LEAVE_BAL_END}",
        CellIsRule(operator="lessThanOrEqual", formula=["2"],
                   fill=fill_amber, font=Font(name="Calibri", size=10, bold=True, color=AMBER)),
    )

# Leave applications section
ws_l.cell(LEAVE_APP_START - 2, 1, "LEAVE APPLICATIONS & APPROVAL WORKFLOW")
ws_l.merge_cells(start_row=LEAVE_APP_START - 2, start_column=1, end_row=LEAVE_APP_START - 2, end_column=10)
style_header_row(ws_l, LEAVE_APP_START - 2, 1, 10)

app_headers = [
    "Emp ID", "Employee Name", "Department", "Leave Type", "Days",
    "From Date", "To Date", "Approval Status", "Approver", "Manager Remarks",
]
for i, h in enumerate(app_headers, 1):
    ws_l.cell(LEAVE_APP_START - 1, i, h).font = font_white_b
    ws_l.cell(LEAVE_APP_START - 1, i).fill = fill_navy
    ws_l.cell(LEAVE_APP_START - 1, i).alignment = center
    ws_l.cell(LEAVE_APP_START - 1, i).border = thin

dv_emp_id = DataValidation(
    type="list",
    formula1=f"'02_Employee_Master'!$A${MASTER_START}:$A${MASTER_START + N_EMP - 1}",
    allow_blank=True,
)
dv_leave_type = DataValidation(type="list", formula1="'01_Config'!$G$17:$G$20", allow_blank=True)
dv_leave_stat = DataValidation(type="list", formula1="'01_Config'!$H$17:$H$20", allow_blank=True)
ws_l.add_data_validation(dv_emp_id)
ws_l.add_data_validation(dv_leave_type)
ws_l.add_data_validation(dv_leave_stat)

# Sample leave applications
sample_leaves = [
    ("PL-004", "Planned Leave", 2, date(2026, 9, 8), date(2026, 9, 9), "Approved", "Sneha Patel", "Family function — approved"),
    ("PL-007", "Sick Leave", 1, date(2026, 9, 3), date(2026, 9, 3), "Approved", "Vikram Singh", "Fever — certificate received"),
    ("PL-010", "Unplanned Leave", 1, date(2026, 9, 11), date(2026, 9, 11), "Approved", "Vikram Singh", "Emergency at home"),
    ("PL-005", "Vacation Leave", 3, date(2026, 9, 22), date(2026, 9, 24), "Pending", "Vikram Singh", ""),
    ("PL-014", "Planned Leave", 1, date(2026, 9, 15), date(2026, 9, 15), "Rejected", "Sneha Patel", "Short staffing on that day"),
    ("PL-016", "Sick Leave", 2, date(2026, 9, 4), date(2026, 9, 5), "Approved", "Fatima Khan", "Medical advice"),
    ("PL-011", "Planned Leave", 1, date(2026, 9, 18), date(2026, 9, 18), "Approved", "Vikram Singh", "OK"),
    ("PL-008", "Unplanned Leave", 1, date(2026, 9, 2), date(2026, 9, 2), "Pending", "Meera Iyer", "Awaiting confirmation"),
]

emp_lookup = {e[0]: e for e in EMPLOYEES}
for i, (eid, ltype, days, fr, to, status, approver, remarks) in enumerate(sample_leaves):
    r = LEAVE_APP_START + i
    emp = emp_lookup[eid]
    ws_l.cell(r, 1, eid)
    ws_l.cell(r, 2, f'=IFERROR(VLOOKUP(A{r},\'02_Employee_Master\'!$A${MASTER_START}:$B${MASTER_START + N_EMP - 1},2,FALSE),"")')
    ws_l.cell(r, 3, f'=IFERROR(VLOOKUP(A{r},\'02_Employee_Master\'!$A${MASTER_START}:$D${MASTER_START + N_EMP - 1},4,FALSE),"")')
    ws_l.cell(r, 4, ltype)
    ws_l.cell(r, 5, days)
    ws_l.cell(r, 6, fr).number_format = "DD-MMM-YYYY"
    ws_l.cell(r, 7, to).number_format = "DD-MMM-YYYY"
    ws_l.cell(r, 8, status)
    ws_l.cell(r, 9, approver)
    ws_l.cell(r, 10, remarks)
    for col in range(1, 11):
        ws_l.cell(r, col).font = font_ink
        ws_l.cell(r, col).border = thin
        ws_l.cell(r, col).fill = alt_fill(i)
        ws_l.cell(r, col).alignment = center if col not in (2, 3, 9, 10) else left
    dv_emp_id.add(ws_l.cell(r, 1))
    dv_leave_type.add(ws_l.cell(r, 4))
    dv_leave_stat.add(ws_l.cell(r, 8))

# Empty application rows
for i in range(len(sample_leaves), 50):
    r = LEAVE_APP_START + i
    ws_l.cell(r, 2, f'=IF(A{r}="","",IFERROR(VLOOKUP(A{r},\'02_Employee_Master\'!$A${MASTER_START}:$B${MASTER_START + N_EMP - 1},2,FALSE),""))')
    ws_l.cell(r, 3, f'=IF(A{r}="","",IFERROR(VLOOKUP(A{r},\'02_Employee_Master\'!$A${MASTER_START}:$D${MASTER_START + N_EMP - 1},4,FALSE),""))')
    for col in range(1, 11):
        ws_l.cell(r, col).border = thin
        ws_l.cell(r, col).fill = alt_fill(i)
    dv_emp_id.add(ws_l.cell(r, 1))
    dv_leave_type.add(ws_l.cell(r, 4))
    dv_leave_stat.add(ws_l.cell(r, 8))
    # Date formats
    ws_l.cell(r, 6).number_format = "DD-MMM-YYYY"
    ws_l.cell(r, 7).number_format = "DD-MMM-YYYY"

# Status CF
stat_range = f"H{LEAVE_APP_START}:H{LEAVE_APP_START + 49}"
ws_l.conditional_formatting.add(stat_range, CellIsRule(operator="equal", formula=['"Approved"'], fill=fill_green, font=Font(bold=True, color=GREEN, name="Calibri", size=10)))
ws_l.conditional_formatting.add(stat_range, CellIsRule(operator="equal", formula=['"Pending"'], fill=fill_amber, font=Font(bold=True, color=AMBER, name="Calibri", size=10)))
ws_l.conditional_formatting.add(stat_range, CellIsRule(operator="equal", formula=['"Rejected"'], fill=fill_red, font=Font(bold=True, color=RED, name="Calibri", size=10)))
ws_l.conditional_formatting.add(stat_range, CellIsRule(operator="equal", formula=['"Cancelled"'], fill=fill_gray, font=Font(italic=True, color=GRAY, name="Calibri", size=10)))

ws_l.freeze_panes = "D7"
apply_print(ws_l)
ws_l.sheet_properties.tabColor = PURPLE

# ═══════════════════════════════════════════════════════════════════════════
# 06_DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════
ws_d = wb.create_sheet("06_Dashboard")
banner(ws_d, 12, "WORKFORCE DASHBOARD",
       f"Live management view  ·  {date(YEAR, MONTH, 1).strftime('%B %Y')}  ·  Formula-driven from Master / Roster / Attendance / Leave")

set_widths(ws_d, [3, 18, 14, 14, 14, 14, 3, 22, 12, 12, 12, 14])

# KPI cards row 5-8
kpis = [
    (2, "TOTAL EMPLOYEES", f"=COUNTA('02_Employee_Master'!A{MASTER_START}:A{MASTER_START + 39})", TEAL),
    (3, "ACTIVE STAFF", f"=COUNTIF('02_Employee_Master'!L{MASTER_START}:L{MASTER_START + 39},\"Active\")", GREEN),
    (4, "INACTIVE", f"=COUNTIF('02_Employee_Master'!L{MASTER_START}:L{MASTER_START + 39},\"Inactive\")", GRAY),
    (5, "ON LEAVE (apps)", f"=COUNTIF('05_Leave'!H{LEAVE_APP_START}:H{LEAVE_APP_START + 49},\"Approved\")", PURPLE),
    (6, "PENDING LEAVE", f"=COUNTIF('05_Leave'!H{LEAVE_APP_START}:H{LEAVE_APP_START + 49},\"Pending\")", AMBER),
]

ws_d.cell(5, 2, "KEY PERFORMANCE INDICATORS").font = font_white_b
ws_d.merge_cells("B5:F5")
style_header_row(ws_d, 5, 2, 6)

for col, label, formula, color in kpis:
    ws_d.cell(6, col, label).font = font_kpi_lbl
    ws_d.cell(6, col).fill = PatternFill("solid", fgColor=color)
    ws_d.cell(6, col).font = Font(name="Calibri", size=9, bold=True, color=WHITE)
    ws_d.cell(6, col).alignment = center
    ws_d.cell(6, col).border = thin
    ws_d.cell(7, col, formula).font = Font(name="Calibri", size=20, bold=True, color=NAVY)
    ws_d.cell(7, col).fill = fill_light
    ws_d.cell(7, col).alignment = center
    ws_d.cell(7, col).border = thin
    ws_d.row_dimensions[7].height = 36

# Today's snapshot — use day 15 as "report day" for demo KPIs from attendance
REPORT_DAY = 15
report_col = day_cols_start + REPORT_DAY - 1
report_letter = get_column_letter(report_col)

ws_d.cell(9, 2, f"ATTENDANCE SNAPSHOT — Day {REPORT_DAY} of month (change formula day refs as needed)")
ws_d.merge_cells("B9:F9")
style_header_row(ws_d, 9, 2, 6)

snap = [
    (2, "Present", f"=COUNTIF('04_Attendance'!{report_letter}{ATT_START}:{report_letter}{ATT_END},\"P\")"
                  f"+COUNTIF('04_Attendance'!{report_letter}{ATT_START}:{report_letter}{ATT_END},\"L\")"
                  f"+COUNTIF('04_Attendance'!{report_letter}{ATT_START}:{report_letter}{ATT_END},\"WFO\")"
                  f"+COUNTIF('04_Attendance'!{report_letter}{ATT_START}:{report_letter}{ATT_END},\"OT\")"),
    (3, "Absent", f"=COUNTIF('04_Attendance'!{report_letter}{ATT_START}:{report_letter}{ATT_END},\"A\")"),
    (4, "Late", f"=COUNTIF('04_Attendance'!{report_letter}{ATT_START}:{report_letter}{ATT_END},\"L\")"),
    (5, "On Leave", f"=COUNTIF('04_Attendance'!{report_letter}{ATT_START}:{report_letter}{ATT_END},\"PL\")"
                   f"+COUNTIF('04_Attendance'!{report_letter}{ATT_START}:{report_letter}{ATT_END},\"UL\")"
                   f"+COUNTIF('04_Attendance'!{report_letter}{ATT_START}:{report_letter}{ATT_END},\"VL\")"
                   f"+COUNTIF('04_Attendance'!{report_letter}{ATT_START}:{report_letter}{ATT_END},\"SL\")"),
    (6, "Att % (month avg)", f"=IFERROR(AVERAGE('04_Attendance'!{pct_col_letter}{ATT_START}:{pct_col_letter}{ATT_END}),0)"),
]
for col, label, formula in snap:
    ws_d.cell(10, col, label).font = font_white_b
    ws_d.cell(10, col).fill = fill_navy
    ws_d.cell(10, col).alignment = center
    ws_d.cell(10, col).border = thin
    ws_d.cell(11, col, formula).font = font_kpi
    ws_d.cell(11, col).fill = fill_sand
    ws_d.cell(11, col).alignment = center
    ws_d.cell(11, col).border = thin
ws_d.cell(11, 6).number_format = "0.0%"
ws_d.row_dimensions[11].height = 32

# Shift-wise headcount for report day
ws_d.cell(13, 2, f"SHIFT-WISE HEADCOUNT — Roster Day {REPORT_DAY}")
ws_d.merge_cells("B13:D13")
style_header_row(ws_d, 13, 2, 4)
for i, (code, name, _) in enumerate([("M", "Morning", ""), ("E", "Evening", ""), ("N", "Night", "")]):
    ws_d.cell(14, 2 + i, name).font = font_white_b
    ws_d.cell(14, 2 + i).fill = fill_navy
    ws_d.cell(14, 2 + i).alignment = center
    ws_d.cell(14, 2 + i).border = thin
    ws_d.cell(15, 2 + i, f"=COUNTIF('03_Roster'!{report_letter}{ROSTER_DATA_START}:{report_letter}{ROSTER_DATA_END},\"{code}\")")
    ws_d.cell(15, 2 + i).font = font_kpi
    ws_d.cell(15, 2 + i).alignment = center
    ws_d.cell(15, 2 + i).border = thin
    ws_d.cell(15, 2 + i).fill = fill_light

# Department-wise stats
ws_d.cell(13, 8, "DEPARTMENT-WISE ACTIVE HEADCOUNT")
ws_d.merge_cells("H13:K13")
style_header_row(ws_d, 13, 8, 11)
ws_d.cell(14, 8, "Department").font = font_white_b
ws_d.cell(14, 9, "Active").font = font_white_b
ws_d.cell(14, 10, "Avg Att %").font = font_white_b
ws_d.cell(14, 11, "On Leave (bal SL used)").font = font_white_b
for col in range(8, 12):
    ws_d.cell(14, col).fill = fill_navy
    ws_d.cell(14, col).border = thin
    ws_d.cell(14, col).alignment = center

for i, dept in enumerate(DEPARTMENTS):
    r = 15 + i
    ws_d.cell(r, 8, dept).font = font_ink
    ws_d.cell(r, 9, f'=COUNTIFS(\'02_Employee_Master\'!$D${MASTER_START}:$D${MASTER_START + 39},H{r},\'02_Employee_Master\'!$L${MASTER_START}:$L${MASTER_START + 39},"Active")')
    # Avg att % for dept — AVERAGEIF on attendance sheet dept col C
    ws_d.cell(r, 10, f"=IFERROR(AVERAGEIF('04_Attendance'!$C${ATT_START}:$C${ATT_END},H{r},'04_Attendance'!${pct_col_letter}${ATT_START}:${pct_col_letter}${ATT_END}),\"\")")
    ws_d.cell(r, 10).number_format = "0%"
    ws_d.cell(r, 11, f"=SUMIF('05_Leave'!$C${LEAVE_BAL_START}:$C${LEAVE_BAL_END},H{r},'05_Leave'!$K${LEAVE_BAL_START}:$K${LEAVE_BAL_END})")
    for col in range(8, 12):
        ws_d.cell(r, col).border = thin
        ws_d.cell(r, col).fill = alt_fill(i)
        ws_d.cell(r, col).alignment = center if col > 8 else left

# Leave summary block
ws_d.cell(17, 2, "LEAVE SUMMARY (this period)")
ws_d.merge_cells("B17:D17")
style_header_row(ws_d, 17, 2, 4)
leave_sum = [
    ("Approved applications", f"=COUNTIF('05_Leave'!H{LEAVE_APP_START}:H{LEAVE_APP_START + 49},\"Approved\")"),
    ("Pending approvals", f"=COUNTIF('05_Leave'!H{LEAVE_APP_START}:H{LEAVE_APP_START + 49},\"Pending\")"),
    ("Rejected", f"=COUNTIF('05_Leave'!H{LEAVE_APP_START}:H{LEAVE_APP_START + 49},\"Rejected\")"),
    ("Total leave days approved", f"=SUMIF('05_Leave'!H{LEAVE_APP_START}:H{LEAVE_APP_START + 49},\"Approved\",'05_Leave'!E{LEAVE_APP_START}:E{LEAVE_APP_START + 49})"),
]
for i, (label, formula) in enumerate(leave_sum):
    r = 18 + i
    ws_d.cell(r, 2, label).font = font_ink_b
    ws_d.cell(r, 2).fill = fill_sand
    ws_d.cell(r, 2).border = thin
    ws_d.merge_cells(start_row=r, start_column=2, end_row=r, end_column=3)
    ws_d.cell(r, 3).border = thin
    ws_d.cell(r, 3).fill = fill_sand
    ws_d.cell(r, 4, formula).font = font_navy_b
    ws_d.cell(r, 4).border = thin
    ws_d.cell(r, 4).alignment = center
    ws_d.cell(r, 4).fill = fill_light

# Monthly attendance trend data (for chart) — present headcount per day from attendance total row
ws_d.cell(24, 2, "MONTHLY ATTENDANCE TREND (Present headcount by day)")
ws_d.merge_cells("B24:F24")
style_header_row(ws_d, 24, 2, 6)

ws_d.cell(25, 2, "Day").font = font_white_b
ws_d.cell(25, 3, "Present").font = font_white_b
ws_d.cell(25, 2).fill = fill_navy
ws_d.cell(25, 3).fill = fill_navy
ws_d.cell(25, 2).border = thin
ws_d.cell(25, 3).border = thin

for day in range(1, MAX_DAYS + 1):
    r = 25 + day
    col_letter = get_column_letter(day_cols_start + day - 1)
    ws_d.cell(r, 2, day).font = font_ink
    ws_d.cell(r, 2).border = thin
    ws_d.cell(r, 2).alignment = center
    ws_d.cell(r, 3, f"='04_Attendance'!{col_letter}{tot_a}")
    ws_d.cell(r, 3).border = thin
    ws_d.cell(r, 3).alignment = center
    ws_d.cell(r, 2).fill = alt_fill(day)
    ws_d.cell(r, 3).fill = alt_fill(day)

chart = LineChart()
chart.title = "Daily Present Headcount"
chart.style = 10
chart.y_axis.title = "Employees"
chart.x_axis.title = "Day"
chart.height = 8
chart.width = 15
data = Reference(ws_d, min_col=3, min_row=25, max_row=25 + MAX_DAYS)
cats = Reference(ws_d, min_col=2, min_row=26, max_row=25 + MAX_DAYS)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
chart.legend = None
ws_d.add_chart(chart, "E24")

# Dept bar chart
chart2 = BarChart()
chart2.type = "col"
chart2.title = "Active Staff by Department"
chart2.style = 10
chart2.height = 8
chart2.width = 12
data2 = Reference(ws_d, min_col=9, min_row=14, max_row=14 + len(DEPARTMENTS))
cats2 = Reference(ws_d, min_col=8, min_row=15, max_row=14 + len(DEPARTMENTS))
chart2.add_data(data2, titles_from_data=True)
chart2.set_categories(cats2)
chart2.legend = None
ws_d.add_chart(chart2, "H24")

# How to refresh note
ws_d.merge_cells("B58:F60")
ws_d["B58"] = (
    "Manager tip: To change month — set Roster B5/D5, clear old roster & attendance marks, then re-enter. "
    "Dashboard KPIs/charts recalculate automatically. "
    f"Snapshot formulas currently reference Day {REPORT_DAY}; change the column letter for another day. "
    "See 00_Home for the full month-change checklist. Print this sheet in landscape for monthly review."
)
ws_d["B58"].font = font_small
ws_d["B58"].alignment = Alignment(wrap_text=True, vertical="top")
ws_d["B58"].fill = fill_sand

apply_print(ws_d)
ws_d.sheet_properties.tabColor = CORAL

# ── Finalize ───────────────────────────────────────────────────────────────
# Prefer primary path; if Excel has the file locked, write v2
try:
    wb.save(OUT)
    print("Wrote", OUT)
except PermissionError:
    wb.save(OUT_FIXED)
    print("Primary file locked — wrote", OUT_FIXED)
print(f"Employees: {N_EMP} ({N_ACTIVE} active) | Days: {DAYS_IN_MONTH} | Period: {YEAR}-{MONTH:02d}")
