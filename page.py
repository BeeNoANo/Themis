import curses
import os
import json
import gzip
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path
from setting import MENU_MAIN,LOGO
from setting import MENU_SETTING
from ulti_tui import draw_logo, draw_title, draw_menu, get_input, get_text_input, is_valid_folder_path
import problem_loader
import subprocess
import shlex
import sys
import time
import shutil

file_path = {"Folder Answer": "","Folder Test": ""}


def process_answer_folder(folder_path: str):
    """Scan each immediate subfolder of folder_path, look for a Settings.cfg
    (in the first subfolder or directly inside the problem folder). Parse found
    Settings.cfg with problem_loader.load_cfg and save results to
    <project>/answers_settings.json. Returns (out_path, results_dict).
    """
    folder_path = os.path.expanduser(folder_path)
    data_dir = Path(__file__).resolve().parent / 'data'
    data_dir.mkdir(exist_ok=True)
    out = data_dir / 'answers_settings.json'
    results = {}

    if not os.path.isdir(folder_path):
        raise NotADirectoryError(folder_path)

    for entry in sorted(os.listdir(folder_path)):
        prob_path = os.path.join(folder_path, entry)
        if not os.path.isdir(prob_path):
            continue

        # candidate locations to look for Settings.cfg
        candidates = []
        # check directly inside problem folder first
        candidates.append(os.path.join(prob_path, 'Settings.cfg'))
        # also check any immediate child subfolder for Settings.cfg (not only first)
        subdirs = [d for d in os.listdir(prob_path) if os.path.isdir(os.path.join(prob_path, d))]
        for sd in sorted(subdirs):
            candidates.append(os.path.join(prob_path, sd, 'Settings.cfg'))

        found = None
        for c in candidates:
            if os.path.isfile(c):
                found = c
                break

        if found:
            # first try the normal loader which expects a plain XML file
            data = None
            try:
                data, tree, root = problem_loader.load_cfg(found)
            except Exception as e1:
                # fallback: try reading bytes, decompress (gzip/zlib) and parse from string
                try:
                    raw = Path(found).read_bytes()
                except Exception as e2:
                    results[entry] = {"error": f"read error: {e2}"}
                    continue

                def try_decompress_bytes(b: bytes) -> bytes:
                    try:
                        return gzip.decompress(b)
                    except Exception:
                        pass
                    try:
                        return zlib.decompress(b)
                    except Exception:
                        pass
                    return b

                dec = try_decompress_bytes(raw)
                parsed = False
                last_err = None
                for enc in ("utf-8", "latin-1"):
                    try:
                        text = dec.decode(enc)
                    except Exception as e3:
                        last_err = e3
                        continue
                    try:
                        root = ET.fromstring(text)
                        tree = ET.ElementTree(root)
                        data = {"ExamInformation": root.attrib,
                                "TestCases": [tc.attrib for tc in root.findall("TestCase")]}
                        results[entry] = data
                        parsed = True
                        break
                    except Exception as e4:
                        last_err = e4

                if not parsed:
                    results[entry] = {"error": f"original: {e1}; fallback: {last_err}"}
                else:
                    # parsed via fallback; populate data and continue to resolution step below
                    # `data` variable already set in fallback parsing above
                    pass

            # if parsed successfully (either normal or fallback), resolve defaults
            if data is not None and 'ExamInformation' in data and 'TestCases' in data:
                exam = data.get('ExamInformation', {})
                tests = data.get('TestCases', [])
                # record path to problem folder so grader can find testdata
                try:
                    data['Path'] = prob_path
                except Exception:
                    pass
                # get global defaults from setting.py
                try:
                    import setting as _setting
                    global_defaults = _setting.default_setting.get('ExamInfomation', {})
                except Exception:
                    global_defaults = {}

                # normalize exam-level defaults: if exam has -1 or missing, fill from global defaults
                for ek in ('Mark', 'TimeLimit', 'MemoryLimit'):
                    ev = exam.get(ek)
                    if ev is None or str(ev) == "-1":
                        gv = global_defaults.get(ek)
                        if gv is not None:
                            exam[ek] = str(gv)

                for tc in tests:
                    # helper to resolve a key
                    def _resolve(key):
                        v = tc.get(key)
                        if v is None or str(v) == "-1":
                            # try exam level
                            ev = exam.get(key)
                            if ev is None or str(ev) == "-1":
                                # try global default
                                gv = global_defaults.get(key)
                                return str(gv) if gv is not None else ""
                            return str(ev)
                        return str(v)

                    eff_mark = _resolve('Mark')
                    eff_time = _resolve('TimeLimit')
                    eff_mem = _resolve('MemoryLimit')

                    # overwrite TestCase fields directly with resolved values
                    tc['Mark'] = eff_mark
                    tc['TimeLimit'] = eff_time
                    tc['MemoryLimit'] = eff_mem

                data['TestCases'] = tests
                results[entry] = data
        else:
            results[entry] = {"error": "Settings.cfg not found"}

    with open(out, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    return str(out), results


def process_student_folder(folder_path: str):
    """Scan a student submissions folder and produce students_submissions.json.

    Folder layout accepted:
    - Folder/Test/<StudentName>/<ProblemName>.<ext>
    - Folder/Test/<StudentName>/<ProblemName>/<files...>
    - Or: Folder/Test/<ProblemName>/<StudentName>.<ext> (single student or root)

    It will build a dict of students -> { 'Name': name, 'BaiLam': {problem_file: abs_path}, 'Scores': {problem_name: 0}}
    Then it will merge student names into answers_settings.json under each exam as 'Students': {student_name: 0}
    Returns (out_path, students_dict)
    """
    folder_path = os.path.expanduser(folder_path)
    data_dir = Path(__file__).resolve().parent / 'data'
    data_dir.mkdir(exist_ok=True)
    out_students = data_dir / 'students_submissions.json'

    if not os.path.isdir(folder_path):
        raise NotADirectoryError(folder_path)

    # try to load existing exams index so we can match file names to exams
    answers_path = Path(__file__).resolve().parent / 'data' / 'answers_settings.json'
    exams = {}
    if answers_path.is_file():
        try:
            with open(answers_path, 'r', encoding='utf-8') as f:
                exams = json.load(f)
        except Exception:
            exams = {}

    students = {}

    # detect if provided folder_path itself is a single student's folder
    code_exts = ('.cpp', '.py', '.pas', '.pascal')
    def _contains_code(dirp: str) -> bool:
        for root, dirs, files in os.walk(dirp):
            rel = os.path.relpath(root, dirp)
            if rel.count(os.sep) > 1:
                continue
            for f in files:
                if f.lower().endswith(code_exts):
                    return True
        return False

    if _contains_code(folder_path):
        # treat this folder as a single student
        student_name = os.path.basename(os.path.normpath(folder_path))
        students = {student_name: {"Name": student_name, "BaiLam": {}, "Scores": {}}}
        s = students[student_name]
        for root, dirs, files in os.walk(folder_path):
            rel = os.path.relpath(root, folder_path)
            if rel.count(os.sep) > 1:
                continue
            for f in files:
                if not f.lower().endswith(code_exts):
                    continue
                s['BaiLam'][f] = os.path.join(root, f)

        # compute scores against exams
        for exam_name in exams.keys():
            matched = any(os.path.splitext(fname)[0] == exam_name for fname in s['BaiLam'].keys())
            s['Scores'][exam_name] = 0 if matched else -1

        # write students_submissions.json as list
        students_list = list(students.values())
        with open(out_students, 'w', encoding='utf-8') as f:
            json.dump(students_list, f, ensure_ascii=False, indent=2)

        # merge into answers_settings.json
        for exam_name, ex in exams.items():
            if 'Students' not in ex or not isinstance(ex.get('Students'), dict):
                ex['Students'] = {}
            ex['Students'][student_name] = int(s['Scores'].get(exam_name, -1))
        try:
            # write back into data/answers_settings.json
            with open(Path(__file__).resolve().parent / 'data' / 'answers_settings.json', 'w', encoding='utf-8') as f:
                json.dump(exams, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return str(out_students), list(students.values())

    # detect layout: student-first vs problem-first
    code_exts = ('.cpp', '.py', '.pas', '.pascal')
    student_like = 0
    problem_like = 0
    for entry in os.listdir(folder_path):
        entry_path = os.path.join(folder_path, entry)
        if not os.path.isdir(entry_path):
            continue
        # if this dir contains a Settings.cfg or many test folders, count as problem-like
        if os.path.isfile(os.path.join(entry_path, 'Settings.cfg')):
            problem_like += 1
            continue
        # if this dir contains code files directly or in a child folder, count as student-like
        found_code = False
        for root, dirs, files in os.walk(entry_path):
            for f in files:
                if f.lower().endswith(code_exts):
                    found_code = True
                    break
            if found_code:
                break
            # limit detection depth
            if os.path.relpath(root, entry_path).count(os.sep) >= 1:
                break
        if found_code:
            student_like += 1

    layout = 'student' if student_like >= problem_like else 'problem'

    # helper to ensure student entry exists
    def _ensure_student(name: str):
        if name not in students:
            students[name] = {"Name": name, "BaiLam": {}, "Scores": {}}
        return students[name]

    if layout == 'student':
        # treat each top-level dir as student folder
        for entry in sorted(os.listdir(folder_path)):
            entry_path = os.path.join(folder_path, entry)
            if not os.path.isdir(entry_path):
                continue
            student_name = entry
            s = _ensure_student(student_name)
            # scan files one level deep under student folder
            for root, dirs, files in os.walk(entry_path):
                rel = os.path.relpath(root, entry_path)
                if rel.count(os.sep) > 1:
                    continue
                for f in files:
                    if not f.lower().endswith(code_exts):
                        continue
                    absf = os.path.join(root, f)
                    s['BaiLam'][f] = absf

    else:
        # problem-first: each top-level dir is a problem; look for student submissions inside
        # two-pass approach: first, collect basenames of files directly under problem folders
        basename_counts = {}
        direct_files = []  # tuples (prob, fname, fullpath)
        for prob in sorted(os.listdir(folder_path)):
            prob_path = os.path.join(folder_path, prob)
            if not os.path.isdir(prob_path):
                continue
            for child in sorted(os.listdir(prob_path)):
                child_path = os.path.join(prob_path, child)
                if os.path.isfile(child_path) and any(child.lower().endswith(ext) for ext in code_exts):
                    base = os.path.splitext(child)[0]
                    basename_counts[base] = basename_counts.get(base, 0) + 1
                    direct_files.append((prob, child, child_path))

        # now process each problem: handle student-folder children and direct files only when basename appears multiple times
        for prob in sorted(os.listdir(folder_path)):
            prob_path = os.path.join(folder_path, prob)
            if not os.path.isdir(prob_path):
                continue
            # look for per-student subfolders
            for child in sorted(os.listdir(prob_path)):
                child_path = os.path.join(prob_path, child)
                if os.path.isdir(child_path):
                    # child may be a student folder containing code files
                    found_any = False
                    for root, dirs, files in os.walk(child_path):
                        rel = os.path.relpath(root, child_path)
                        if rel.count(os.sep) > 1:
                            continue
                        for f in files:
                            if not f.lower().endswith(code_exts):
                                continue
                            student_name = child
                            s = _ensure_student(student_name)
                            s['BaiLam'][f] = os.path.join(root, f)
                            found_any = True
                    if found_any:
                        continue
            # handle direct files under the problem folder, but only treat basename as student if it appears in multiple problems
            for prob2, child, child_path in direct_files:
                if prob2 != prob:
                    continue
                base = os.path.splitext(child)[0]
                if basename_counts.get(base, 0) >= 2:
                    # treat as student submission file named by basename
                    student_name = base
                    s = _ensure_student(student_name)
                    s['BaiLam'][child] = child_path

    # now compute Scores per student per exam according to matching rule:
    # if student has a file whose basename == exam name -> score 0 (ready to grade)
    # else score -1 (skip / mismatched)
    for sname, sdata in students.items():
        for exam_name in exams.keys():
            matched = False
            for fname in sdata['BaiLam'].keys():
                if os.path.splitext(fname)[0] == exam_name:
                    matched = True
                    break
            sdata['Scores'][exam_name] = 0 if matched else -1

    # prepare list format as requested by user
    students_list = list(students.values())
    # write students_submissions.json (list)
    with open(out_students, 'w', encoding='utf-8') as f:
        json.dump(students_list, f, ensure_ascii=False, indent=2)
    # merge students into answers_settings.json under 'Students'
    for exam_name, ex in exams.items():
        if 'Students' not in ex or not isinstance(ex.get('Students'), dict):
            ex['Students'] = {}
        for sname, sdata in students.items():
            # set 0 if matched, -1 if not
            ex['Students'][sname] = int(sdata['Scores'].get(exam_name, -1))

    # write back answers_settings.json
    try:
        with open(answers_path, 'w', encoding='utf-8') as f:
            json.dump(exams, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return str(out_students), students_list


def setting(stdscr):
    """Trang Cài đặt: hiển thị MENU_SETTING và xử lý điều hướng"""
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_GREEN)

    current_idx = 0
    while True:
        stdscr.clear()
        logo_height = draw_logo(stdscr, y=0)
        draw_title(stdscr, "Cài đặt", logo_height + 1)
        draw_menu(stdscr, current_idx, logo_height + 3, MENU_SETTING)

        current_idx, action = get_input(stdscr, current_idx, len(MENU_SETTING))

        if action == "enter":
            if current_idx == 0:
                # Thêm folder đáp án (placeholder)
                stdscr.clear()
                path = get_text_input(stdscr, 0, 0, 30)
                if is_valid_folder_path(path):
                    file_path["Folder Answer"] = path
                    stdscr.addstr(5, 0, "Folder hợp lệ, quét các subfolder...")
                    stdscr.refresh()
                    try:
                        out_file, results = process_answer_folder(path)
                        stdscr.addstr(6, 0, f"Đã lưu index: {out_file}")
                        ok_count = sum(1 for v in results.values() if 'ExamInformation' in v)
                        stdscr.addstr(7, 0, f"Parsed: {ok_count} entries, total: {len(results)}")
                    except Exception as e:
                        stdscr.addstr(6, 0, f"Lỗi khi quét folder: {e}")
                else:
                    stdscr.addstr(5, 0, "File không tồn tại, Vui lòng nhập lại")
                stdscr.refresh()
                stdscr.getch()
            elif current_idx == 1:
                # Thêm folder thí sinh (placeholder)
                stdscr.clear()
                path = get_text_input(stdscr, 0, 0, 30)
                if is_valid_folder_path(path):
                    file_path["Folder Test"] = path
                    stdscr.addstr(5, 0, "File hợp lệ, quét bài làm thí sinh...")
                    stdscr.refresh()
                    try:
                        out_students, students = process_student_folder(path)
                        stdscr.addstr(6, 0, f"Đã lưu danh sách thí sinh: {out_students}")
                        stdscr.addstr(7, 0, f"Tổng thí sinh: {len(students)}")
                    except Exception as e:
                        stdscr.addstr(6, 0, f"Lỗi khi quét folder thí sinh: {e}")
                else:
                    stdscr.addstr(5, 0, "File không tồn tại, Vui lòng nhập lại")
                stdscr.refresh()
                stdscr.getch()
            else:
                # Thoát trang cài đặt -> trở về menu chính
                break
        elif action == "quit":
            break

def run_program(cmd, input_path, timeout_sec, memory_mb=None):
    """Run a command string with input redirected from input_path.
    Return (returncode, stdout, stderr, timed_out)
    """
    try:
        with open(input_path, 'rb') as fin:
            # if prlimit is available, use it to apply memory and cpu limits
            prlimit = shutil.which('prlimit')
            if prlimit and memory_mb is not None:
                # compute bytes for address space and pass as single-arg options
                as_bytes = int(memory_mb) * 1024 * 1024
                # use --as=<bytes> and --cpu=<seconds> form to avoid some prlimit variants
                wrapped = [prlimit, f'--as={as_bytes}', f'--cpu={int(timeout_sec)}', '--'] + shlex.split(cmd)
                proc = subprocess.run(wrapped, stdin=fin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_sec + 1)
            else:
                proc = subprocess.run(shlex.split(cmd), stdin=fin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_sec)
            return proc.returncode, proc.stdout, proc.stderr, False
    except subprocess.TimeoutExpired:
        return -1, b'', b'Timeout', True
    except FileNotFoundError as e:
        return -2, b'', str(e).encode('utf-8'), False
    except Exception as e:
        return -3, b'', str(e).encode('utf-8'), False


def find_test_io(tc, workdir, prob_name, answers_index=None):
    """Find input and expected output paths for a test case."""
    tc_name = tc.get('Name') if isinstance(tc, dict) else str(tc)
    cand_in = []
    cand_out = []

    # Check TestCase attributes first
    if isinstance(tc, dict):
        for k in ('Input', 'InputFile', 'Inp'):
            v = tc.get(k)
            if v:
                cand_in.append(v)
        for k in ('Output', 'OutputFile', 'Out'):
            v = tc.get(k)
            if v:
                cand_out.append(v)

    # If problem path available in answers_index
    if answers_index and isinstance(answers_index, dict):
        prob_path = answers_index.get('Path')
        if prob_path and os.path.isdir(prob_path):
            # Check test subfolder with same name as test case
            test_subdir = os.path.join(prob_path, tc_name)
            if os.path.isdir(test_subdir):
                # Search in test subfolder
                for f in os.listdir(test_subdir):
                    fp = os.path.join(test_subdir, f)
                    if f.lower().endswith(('.inp', '.in')):
                        cand_in.append(fp)
                    elif f.lower().endswith('.out'):
                        cand_out.append(fp)

            # Check common test folders
            for test_dir in ('tests', 'testdata', 'data', 'input', tc_name):
                test_path = os.path.join(prob_path, test_dir)
                if os.path.isdir(test_path):
                    # Add candidates with various extensions
                    for ext in ('.INP', '.inp', '.in'):
                        cand_in.append(os.path.join(test_path, tc_name + ext))
                        cand_in.append(os.path.join(test_path, prob_name + ext))
                    cand_out.append(os.path.join(test_path, tc_name + '.OUT'))
                    cand_out.append(os.path.join(test_path, tc_name + '.out'))

    # Add local submission directory candidates
    cand_in += [
        os.path.join(workdir, tc_name + '.INP'),
        os.path.join(workdir, tc_name + '.in'),
        os.path.join(workdir, tc_name + '.inp'),
        os.path.join(workdir, prob_name + '.INP'),
        os.path.join(workdir, prob_name + '.in')
    ]

    # Find first existing input file
    input_path = None
    for p in cand_in:
        if p and os.path.exists(p):
            input_path = p
            break

    # Find first existing output file
    output_path = None
    for p in cand_out:
        if p and os.path.exists(p):
            output_path = p
            break

    # If no output found but input exists, try corresponding .OUT file
    if input_path and not output_path:
        guess_out = input_path.replace('.INP', '.OUT').replace('.inp', '.out').replace('.in', '.out')
        if os.path.exists(guess_out):
            output_path = guess_out

    return input_path, output_path

def show_student_details(stdscr, student_id_or_name: str):
    """Hiển thị chi tiết một thí sinh dựa trên ID hoặc tên."""
    data_dir = os.path.join(os.getcwd(), 'data')
    try:
        # Đọc dữ liệu
        with open(os.path.join(data_dir, 'students_submissions.json'), 'r', encoding='utf-8') as f:
            students = json.load(f)
        with open(os.path.join(data_dir, 'answers_settings.json'), 'r', encoding='utf-8') as f:
            answers = json.load(f)

        # Tìm thí sinh
        found_student = None

        if not found_student:
            stdscr.clear()
            h, w = stdscr.getmaxyx()
            msg = "Không tìm thấy người dùng"
            stdscr.addstr(h//2, (w-len(msg))//2, msg)
            stdscr.refresh()
            stdscr.getch()
            return

        # Tính thứ hạng
        all_students.sort(key=lambda x: x[1], reverse=True)
        rank = next(idx for idx, (name, _) in enumerate(all_students, 1)
                   if name == found_student.get('Name'))

        # Hiển thị thông tin
        stdscr.clear()
        name = found_student.get('Name')
        scores = found_student.get('Scores', {})
        test_results = found_student.get('TestResults', {})
        total_score = sum(float(score) for score in scores.values())

        # Dòng đầu: thông tin tổng quan
        h, w = stdscr.getmaxyx()
        header = f"Thí sinh: {name} | Điểm tổng: {total_score:.2f} | Thứ hạng: {rank}/{len(all_students)}"
        stdscr.addstr(0, (w-len(header))//2, header)
        stdscr.addstr(1, 0, "="*w)

        # Điểm từng môn
        y = 2
        stdscr.addstr(y, 0, "Điểm các môn:")
        y += 1
        for exam_name, score in scores.items():
            score_line = f"{exam_name}: {float(score):.2f} điểm"
            stdscr.addstr(y, 2, score_line)
            y += 1

        y += 1
        stdscr.addstr(y, 0, "Chi tiết các bài thi:")
        y += 1

        # Chi tiết từng bài
        for prob_name, tests in test_results.items():
            passed = sum(1 for t in tests if t.get('Passed'))
            total = len(tests)
            prob_header = f"\nBài {prob_name} ({passed}/{total} test đúng)"
            stdscr.addstr(y, 0, prob_header)
            y += 1

            for test in tests:
                status = "✓" if test.get('Passed') else "✗"
                name = test.get('Test', '')
                mark = test.get('MarkEarned', 0)
                result_line = f"  {status} Test {name}: {mark} điểm"
                if not test.get('Passed'):
                    if test.get('TimedOut'):
                        result_line += " (Time limit exceeded)"
                    elif test.get('Ret') != 0:
                        result_line += f" (Runtime error: {test.get('Ret')})"
                    else:
                        result_line += " (Wrong answer)"
                stdscr.addstr(y, 0, result_line)
                y += 1

        # Footer
        stdscr.addstr(h-1, 0, "Nhấn phím bất kỳ để quay lại...")
        stdscr.refresh()
        stdscr.getch()

    except Exception as e:
        stdscr.clear()
        h, w = stdscr.getmaxyx()
        error_msg = f"Lỗi: {str(e)}"
        stdscr.addstr(h//2, (w-len(error_msg))//2, error_msg)
        stdscr.refresh()
        stdscr.getch()

def start_grading(stdscr):
    """Interactive grading flow triggered from main menu.
    For each student and each exam, run their submission against available input files
    and compare stdout with expected output files. Shows a per-test log page and
    updates `data/students_submissions.json` and `data/answers_settings.json`.
    This is a best-effort implementation: timeouts enforced; memory limits not enforced.
    """
    curses.curs_set(0)
    base = os.path.dirname(__file__)
    data_answers = os.path.join(base, 'data', 'answers_settings.json')
    data_students = os.path.join(base, 'data', 'students_submissions.json')
    try:
        with open(data_answers, 'r', encoding='utf-8') as f:
            answers = json.load(f)
    except Exception:
        answers = {}
    try:
        with open(data_students, 'r', encoding='utf-8') as f:
            students = json.load(f)
    except Exception:
        students = []

    # students is a list of student dicts
    for student in students:
        name = student.get('Name')
        bai_lam = student.get('BaiLam', {})
        scores = student.get('Scores', {})

        for prob_name, prob_def in answers.items():
            # find student's submission file for this problem
            sub_path = None
            for fname, fpath in bai_lam.items():
                if prob_name.upper() in fname.upper() or os.path.splitext(fname)[0].upper() == prob_name.upper():
                    sub_path = fpath
                    break
            if not sub_path:
                # student didn't submit for this prob
                continue

            cmd = None
            sub_lower = sub_path.lower()
            workdir = os.path.dirname(sub_path)

            if sub_lower.endswith('.py'):
                cmd = f"{shlex.quote(sys.executable)} {shlex.quote(sub_path)}"
            elif sub_lower.endswith('.cpp'):
                bin_name = os.path.join(workdir, os.path.splitext(os.path.basename(sub_path))[0])
                compile_cmd = f"g++ -O2 -std=gnu++17 {shlex.quote(sub_path)} -o {shlex.quote(bin_name)}"
                try:
                    cproc = subprocess.run(shlex.split(compile_cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
                    if cproc.returncode == 0:
                        cmd = shlex.quote(bin_name)
                    else:
                        cmd = None
                except Exception:
                    cmd = None
            else:
                cmd = shlex.quote(sub_path)

            if not cmd:
                scores[prob_name] = 0
                student['Scores'] = scores
                continue

            testcases = prob_def.get('TestCases', [])
            exam_info = prob_def.get('ExamInformation', {})
            tl = int(exam_info.get('TimeLimit', 1))

            earned = 0.0
            total_marks = 0.0
            for tc in testcases:
                tc_name = tc.get('Name')
                try:
                    tc_mark = float(tc.get('Mark', 0))
                except Exception:
                    tc_mark = 0.0
                total_marks += tc_mark

                # Use the module-level find_test_io instead of redefining it
                input_path, expected = find_test_io(tc, workdir, prob_name, prob_def)

                if not input_path:
                    passed = False
                    ret = -9
                    stdout = b''
                    stderr = b''
                    timed_out = False
                else:
                    # determine memory limit per test (TestCase->ExamInformation->global default)
                    mem_mb = None
                    try:
                        mm = tc.get('MemoryLimit') or exam_info.get('MemoryLimit')
                        if mm is not None and str(mm) != "-1":
                            mem_mb = int(mm)
                    except Exception:
                        mem_mb = None
                    ret, stdout, stderr, timed_out = run_program(cmd, input_path, tl, memory_mb=mem_mb)
                    # expected output was returned by find_test_io; if missing, try some common fallbacks
                    if not expected:
                        expected_candidates = [input_path.replace('.INP', '.OUT'), input_path.replace('.inp', '.out'), os.path.join(workdir, tc_name + '.OUT')]
                        for ep in expected_candidates:
                            if os.path.exists(ep):
                                expected = ep
                                break
                    # comparison: normalize text
                    def normalize_text(b: bytes):
                        try:
                            s = b.decode('utf-8')
                        except Exception:
                            s = b.decode('latin-1', errors='replace')
                        s = s.replace('\r\n', '\n').strip()
                        # normalize each line by stripping trailing spaces
                        lines = [ln.rstrip() for ln in s.split('\n')]
                        return '\n'.join(lines)

                    evaluator = exam_info.get('EvaluatorName', '') or ''
                    ignore_case = 'IgnoreCase' in evaluator

                    if expected:
                        with open(expected, 'rb') as ef:
                            exp_bytes = ef.read()
                        out_bytes = stdout
                        norm_exp = normalize_text(exp_bytes)
                        norm_out = normalize_text(out_bytes)
                        if ignore_case:
                            norm_exp = norm_exp.lower()
                            norm_out = norm_out.lower()
                        passed = (norm_out == norm_exp) and not timed_out and ret == 0
                    else:
                        passed = False

                # show log page
                stdscr.clear()
                stdscr.addstr(0, 0, f"Student: {name}  Problem: {prob_name}  Test: {tc_name}")
                stdscr.addstr(2, 0, f"Cmd: {cmd}")
                stdscr.addstr(3, 0, f"Return: {ret} TimedOut: {timed_out}")
                try:
                    stdscr.addstr(5, 0, stdout.decode('utf-8', errors='replace')[:800])
                except Exception:
                    pass
                try:
                    stdscr.addstr(13, 0, stderr.decode('utf-8', errors='replace')[:800])
                except Exception:
                    pass
                stdscr.addstr(21, 0, f"Passed: {passed}")
                stdscr.refresh()
                # auto-advance: brief pause so user can observe, then continue
                time.sleep(0.05)

                # record test result
                tr = {
                    'Test': tc_name,
                    'Passed': bool(passed),
                    'Ret': int(ret) if isinstance(ret, int) else -1,
                    'TimedOut': bool(timed_out),
                    'MarkEarned': float(tc_mark) if passed else 0.0,
                }
                # include truncated stdout/stderr
                try:
                    tr['Stdout'] = stdout.decode('utf-8', errors='replace')[:2000]
                except Exception:
                    tr['Stdout'] = ''
                try:
                    tr['Stderr'] = stderr.decode('utf-8', errors='replace')[:2000]
                except Exception:
                    tr['Stderr'] = ''

                # append to student TestResults
                if 'TestResults' not in student or not isinstance(student['TestResults'], dict):
                    student['TestResults'] = {}
                if prob_name not in student['TestResults'] or not isinstance(student['TestResults'][prob_name], list):
                    student['TestResults'][prob_name] = []
                student['TestResults'][prob_name].append(tr)

                if passed:
                    earned += tc_mark

            # use raw marks (sum of earned marks) instead of percentage
            scores[prob_name] = earned
            student['Scores'] = scores

            # update answers mapping with raw marks
            if prob_name in answers:
                if 'Students' not in answers[prob_name] or not isinstance(answers[prob_name].get('Students'), dict):
                    answers[prob_name]['Students'] = {}
                answers[prob_name]['Students'][name] = earned

            # write progress
            try:
                with open(data_students, 'w', encoding='utf-8') as f:
                    json.dump(students, f, ensure_ascii=False, indent=2)
                with open(data_answers, 'w', encoding='utf-8') as f:
                    json.dump(answers, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    # final
    stdscr.clear()
    stdscr.addstr(0, 0, "Grading complete. Press Enter to return.")
    stdscr.refresh()
    while True:
        c = stdscr.getch()
        if c in (10, 13):
            break

