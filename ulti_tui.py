import curses, os, json
from setting import MENU_MAIN,LOGO
from curses import textpad
from typing import List, Dict, Any

def get_text_input(stdscr, y, x, width, prompt="Nhập: "):
    """
    Hiển thị một textbox để nhập văn bản.
    Trả về chuỗi đã nhập.
    """
    curses.curs_set(1)  # Hiện con trỏ
    stdscr.addstr(y, x, prompt)
    stdscr.refresh()

    # tạo cửa sổ để nhập liệu
    editwin = curses.newwin(1, width, y, x + len(prompt))
    box = textpad.Textbox(editwin)

    # cho phép Enter = kết thúc nhập
    def enter_is_terminate(ch):
        if ch == 10:  # Enter
            return 7   # Ctrl+G giả lập
        return ch

    user_input = box.edit(enter_is_terminate).strip()
    curses.curs_set(0)  # Ẩn con trỏ sau khi nhập xong
    return user_input

def draw_logo(stdscr, y=0):
    """Vẽ logo ở dòng y"""
    h, w = stdscr.getmaxyx()
    logo_lines = LOGO.strip("\n").splitlines()
    for i, line in enumerate(logo_lines):
        x = w // 2 - len(line) // 2
        stdscr.addstr(y + i, x, line, curses.A_BOLD)
    return len(logo_lines)  # trả về chiều cao logo

def draw_title(stdscr, title, y):
    """Vẽ tiêu đề ở dòng y"""
    h, w = stdscr.getmaxyx()
    stdscr.addstr(y, w // 2 - len(title) // 2, title, curses.A_BOLD)

def draw_menu(stdscr, current_idx, y_start, MENU):
    """Vẽ menu bắt đầu từ dòng y_start"""
    h, w = stdscr.getmaxyx()
    for idx, row in enumerate(MENU):
        x = w // 2 - len(row) // 2
        y = y_start + idx
        if idx == current_idx:
            stdscr.attron(curses.color_pair(1))
            stdscr.addstr(y, x, row)
            stdscr.attroff(curses.color_pair(1))
        else:
            stdscr.addstr(y, x, row)

def get_input(stdscr, current_idx, menu_len):
    """
    Xử lý phím cho menu.
    - Trả về (new_idx, action)
    - action: None, "enter", "quit"
    """
    key = stdscr.getch()

    if key == curses.KEY_UP and current_idx > 0:
        return current_idx - 1, None
    elif key == curses.KEY_DOWN and current_idx < menu_len - 1:
        return current_idx + 1, None
    elif key in [curses.KEY_ENTER, 10, 13]:
        return current_idx, "enter"
    elif key in [ord("q"), ord("Q")]:
        return current_idx, "quit"
    return current_idx, None

def is_valid_folder_path(path: str, must_exist: bool = True) -> bool:
    """
    Kiểm tra xem 'path' có phải là đường dẫn folder hợp lệ.

    :param path: Đường dẫn cần kiểm tra
    :param must_exist: True = kiểm tra folder có tồn tại, False = chỉ kiểm tra cú pháp
    :return: True nếu hợp lệ, False nếu không
    """
    if not path or not isinstance(path, str):
        return False

    cleaned = os.path.expanduser(path.strip())
    normalized_path = os.path.normpath(os.path.abspath(cleaned))

    if not must_exist:
        return True

    return os.path.isdir(normalized_path)

def _format_table(rows: List[List[str]], headers: List[str], max_width: int) -> List[str]:
    """Return list of table lines (strings) fitting within max_width."""
    # compute column widths
    cols = len(headers)
    # Đảm bảo các cột điểm có độ rộng tối thiểu
    min_widths = {
        "ID": 4,
        "Thí sinh": 15,
        "Tổng điểm": 10,
        "Time": 6,
        "Ram": 6
    }
    # Các cột điểm bài thi cũng có độ rộng tối thiểu 8
    col_widths = []
    for i, h in enumerate(headers):
        if h in min_widths:
            col_widths.append(max(len(h), min_widths[h]))
        else:
            col_widths.append(max(len(h), 8))  # cột điểm bài thi

    # Cập nhật độ rộng dựa trên nội dung
    for r in rows:
        for i in range(cols):
            if i < len(r):
                col_widths[i] = max(col_widths[i], len(str(r[i])))

    total = sum(col_widths) + 3 * (cols - 1) + 4
    # if too wide, truncate some columns evenly
    if total > max_width - 4:  # Trừ 4 cho viền 2 bên
        excess = total - (max_width - 4)
        reducible = list(range(2, cols)) if cols > 2 else []
        while excess > 0 and reducible:
            for ci in reducible:
                if col_widths[ci] > 6 and excess > 0:
                    col_widths[ci] -= 1
                    excess -= 1
            if all(col_widths[c] <= 6 for c in reducible):
                break

    # build format with border
    fmt_parts = []
    for w in col_widths:
        fmt_parts.append(f"{{:<{w}}}")
    fmt = "│ " + " │ ".join(fmt_parts) + " │"
    sep_line = "+" + "-" * (sum(col_widths) + 3 * (cols - 1) + 2) + "+"

    lines = []
    lines.append(sep_line)
    lines.append(fmt.format(*headers))
    lines.append(sep_line)
    for r in rows:
        row = [str(c) for c in r]
        # pad to cols
        while len(row) < cols:
            row.append("")
        # truncate long cells
        for i, cell in enumerate(row):
            if len(cell) > col_widths[i]:
                row[i] = cell[:col_widths[i]-1] + "…"
        lines.append(fmt.format(*row))
    lines.append(sep_line)
    return lines

def show_student_test_details(stdscr, student_name: str, data_dir: str):
    """Hiển thị chi tiết các test của một thí sinh."""
    h, w = stdscr.getmaxyx()
    try:
        # Đọc students_submissions.json để lấy TestResults
        with open(os.path.join(data_dir, 'students_submissions.json'), 'r', encoding='utf-8') as f:
            students = json.load(f)
        # Tìm thông tin học sinh
        student = None
        for s in students:
            if s.get('Name') == student_name:
                student = s
                break
        if not student:
            return

        # Lấy TestResults
        test_results = student.get('TestResults', {})
        if not test_results:
            return

        stdscr.clear()
        # Căn giữa tiêu đề
        title = f"Chi tiết test của thí sinh: {student_name}"
        stdscr.addstr(0, (w - len(title)) // 2, title)
        sep_line = "-" * 50
        stdscr.addstr(1, (w - len(sep_line)) // 2, sep_line)

        y = 2
        for prob_name, tests in test_results.items():
            prob_title = f"\nBài {prob_name}:"
            stdscr.addstr(y, (w - len(prob_title)) // 2, prob_title)
            y += 2
            for test in tests:
                status = "✓" if test.get('Passed') else "✗"
                name = test.get('Test', '')
                mark = test.get('MarkEarned', 0)
                out = test.get('Stdout', '')[:50]
                if len(out) == 50:
                    out += "..."
                detail_line = f"{status} Test {name}: {mark} điểm - Output: {out}"
                stdscr.addstr(y, (w - len(detail_line)) // 2, detail_line)
                y += 1

        prompt = "Nhấn phím bất kỳ để quay lại..."
        stdscr.addstr(y + 1, (w - len(prompt)) // 2, prompt)
        stdscr.refresh()
        stdscr.getch()
    except Exception as e:
        error_msg = f"Lỗi: {str(e)}"
        stdscr.addstr(0, (w - len(error_msg)) // 2, error_msg)
        stdscr.refresh()
        stdscr.getch()

def draw_answers_table(stdscr, y_start: int, file_path: str = "answers_settings.json"):
    """If `file_path` exists, read it and draw a pretty ASCII table at y_start.
    Table columns: 'Bài thi', <student names... or 'Null'>, 'Time', 'Ram'
    Each row: exam name, scores per student (0 if missing), Time default, Ram default
    Returns number of lines drawn.
    """
    # use data/ folder inside project
    data_dir = os.path.join(os.getcwd(), 'data')
    path = os.path.join(data_dir, file_path)
    if not os.path.isfile(path):
        return 0

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return 0

    # gather student names (union of keys under 'Students')
    students = set()
    for v in data.values():
        studs = v.get('Students')
        if isinstance(studs, dict):
            students.update(studs.keys())

    # Kiểm tra có file students_submissions.json không
    ss_path = os.path.join(data_dir, 'students_submissions.json')
    if os.path.isfile(ss_path):
        try:
            with open(ss_path, 'r', encoding='utf-8') as sf:
                sdata = json.load(sf)
            # sdata expected as list of student objects
            if isinstance(sdata, dict):
                student_names = list(sdata.keys())
            elif isinstance(sdata, list):
                student_names = [s.get('Name') for s in sdata if isinstance(s, dict) and s.get('Name')]
            else:
                student_names = []
            students.update([n for n in student_names if n])
        except Exception:
            pass

    # Xác định danh sách học sinh để hiển thị
    student_cols = []
    if students:  # Nếu có học sinh từ file students_submissions.json
        student_cols = sorted(students)
    else:  # Nếu không có học sinh, chỉ hiển thị hàng "Null" với điểm 0
        student_cols = ["Null"]

    # Rotate table: students as rows, problems as columns
    headers = ["ID", "Thí sinh"] + list(data.keys()) + ["Tổng điểm", "Time", "Ram"]

    rows: List[List[str]] = []
    # load global defaults to resolve TimeLimit/MemoryLimit if exam has -1
    try:
        import setting as _setting
        global_defaults = _setting.default_setting.get('ExamInfomation', {})
    except Exception:
        global_defaults = {}

    # First add student rows
    for idx, student in enumerate(student_cols):
        row = [str(idx + 1), student]  # ID and student name columns
        student_time = "1"  # default
        student_ram = "1024"  # default

        # Add scores for each problem and calculate total
        total_score = 0.0
        for exam_name, v in data.items():
            exam = v.get('ExamInformation', {})
            studs = v.get('Students', {}) or {}
            # Get student's score for this problem
            score = studs.get(student, 0)
            score_float = float(score if score is not None else 0)
            total_score += score_float
            row.append(f"{score_float:.2f}")

            # Update student's time/ram limits if this problem requires more
            try:
                prob_time = int(exam.get('TimeLimit', 1))
                prob_ram = int(exam.get('MemoryLimit', 1024))
                student_time = str(max(int(student_time), prob_time))
                student_ram = str(max(int(student_ram), prob_ram))
            except:
                pass

        # Add total score, time and ram columns
        row.append(f"{total_score:.2f}")
        row.append(student_time)
        row.append(student_ram)
        rows.append(row)

    # Then add a row showing max marks possible for each problem
    total_row = ["", "Max điểm"]  # Empty ID cell for max marks row
    max_total = 0.0
    for exam_name, v in data.items():
        total_marks = 0.0
        try:
            for tc in v.get('TestCases', []):
                total_marks += float(tc.get('Mark', 0))
            max_total += total_marks
        except:
            pass
        total_row.append(f"{total_marks:.2f}")
    total_row.append(f"{max_total:.2f}")
    total_row.extend(["", ""])  # empty time/ram cells
    rows.append(total_row)

    h, w = stdscr.getmaxyx()
    lines = _format_table(rows, headers, max_width=w-2)

    # Tính toán độ rộng thực tế của bảng (dựa vào dòng đầu tiên)
    table_width = len(lines[0]) if lines else 0
    # Tính x để căn giữa
    x_start = (w - table_width) // 2

    for i, line in enumerate(lines):
        if y_start + i >= h - 1:
            break
        try:
            stdscr.addstr(y_start + i, max(1, x_start), line)
        except Exception:
            pass

    stdscr.refresh()
    return len(lines)
