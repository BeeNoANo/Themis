import json
import os
import curses

def show_student_details_scrollable(stdscr, target_name: str):
    """
    Hiển thị thông tin chi tiết của một thí sinh trên giao diện Curses với chức năng cuộn.
    """
    data_dir = os.path.join(os.getcwd(), 'data')
    found_student = None
    TextLine = [];
    try:
        with open(os.path.join(data_dir, 'students_submissions.json'), 'r', encoding='utf-8') as f:
            students = json.load(f)
    except FileNotFoundError:
        stdscr.clear()
        stdscr.addstr(0, 0, "Lỗi: Không tìm thấy file students_submissions.json")
        TextLine.append("Lỗi: Không tìm thấy file students_submissions.json")
        stdscr.refresh()
        stdscr.getch()
        return

    for student in students:
        if student.get("Name") == target_name:
            found_student = student
            break

    stdscr.clear()

    if not found_student:
        msg = f"❌ Không tìm thấy thí sinh '{target_name}'"
        TextLine.append(msg);
        stdscr.addstr(0, 0, msg)
        stdscr.addstr(1, 0, "Nhấn phím bất kỳ để quay lại...")
        stdscr.refresh()
        stdscr.getch()
        return

    screen_h, screen_w = stdscr.getmaxyx()
    pad = curses.newpad(1000, screen_w)
    pad_y = 0

    def add_line_to_pad(text, indent=0):
        nonlocal pad_y
        pad.addstr(pad_y, indent, text)
        pad_y += 1

    add_line_to_pad("--- THÔNG TIN THÍ SINH ---")
    TextLine.append("--- THÔNG TIN THÍ SINH ---")
    add_line_to_pad(f"Mã Số {found_student.get('Name')}:")
    TextLine.append(f"Mã Số {found_student.get('Name')}:")

    scores_data = found_student.get("Scores")
    if scores_data:
        for problem_name, score in scores_data.items():
            add_line_to_pad(f"  - Bài: {problem_name}, Điểm: {score}", indent=2)
            TextLine.append(f"  - Bài: {problem_name}, Điểm: {score}")
    else:
        TextLine.append("Thí sinh này không có dữ liệu.")
        add_line_to_pad("Thí sinh này không có dữ liệu.", indent=2)

    add_line_to_pad("")
    add_line_to_pad("--- KẾT QUẢ CHI TIẾT CÁC BÀI KIỂM TRA ---")
    TextLine.append("")
    TextLine.append("--- KẾT QUẢ CHI TIẾT CÁC BÀI KIỂM TRA ---")

    test_results_data = found_student.get("TestResults")
    if test_results_data:
        for problem_name, tests in test_results_data.items():
            add_line_to_pad(f"BÀI THI: {problem_name}")
            TextLine.append(f"BÀI THI: {problem_name}")
            for test in tests:
                stderr_output = "Không" if test.get('Stderr') == "" else test.get('Stderr')
                line = f"Test: {test.get('Test')} - Điểm: {test.get('MarkEarned')} - Lỗi: {stderr_output}"
                TextLine.append(line)
                add_line_to_pad(line, indent=2)
    else:
        TextLine.append("Thí sinh này không có dữ liệu thi.")
        add_line_to_pad("Thí sinh này không có dữ liệu thi.", indent=2)

    content_height = pad_y
    scroll_pos = 0

    # Bắt đầu chế độ không chờ đợi
    stdscr.nodelay(True)

    while True:
        # Hiển thị một phần của pad lên màn hình
        pad.refresh(scroll_pos, 0, 0, 0, screen_h - 2, screen_w - 1)

        # Hiển thị hướng dẫn cuộn
        field = "Sử dụng mũi tên lên/xuống để cuộn. Nhấn 'q' để thoát."
        stdscr.addstr(screen_h - 1, 0, field)
        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP:
            if scroll_pos > 0:
                scroll_pos -= 1
        elif key == curses.KEY_DOWN:
            if scroll_pos < content_height - (screen_h - 1):
                scroll_pos += 1
        elif key == ord('o'):
            filename = f"{found_student.get('Name')}.txt"
            save_dir = os.path.join(os.getcwd(), "saved_results")
            os.makedirs(save_dir, exist_ok=True)

            filepath = os.path.join(save_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("\n".join(TextLine))

            save_msg = f"✅ Đã lưu thành công vào file '{filename}' hiển thị ở desktop"

            # Hiện thông báo ngắn rồi quay lại pad
            stdscr.clear()
            stdscr.addstr(screen_h // 2, (screen_w - len(save_msg)) // 2, save_msg)
            stdscr.addstr(screen_h // 2 + 1, (screen_w - 28) // 2, "Nhấn phím bất kỳ để quay lại...")
            stdscr.refresh()
            stdscr.nodelay(False)   # chờ phím
            stdscr.getch()
            stdscr.nodelay(True)    # bật lại chế độ non-blocking

            # Vẽ lại pad
            pad.refresh(scroll_pos, 0, 0, 0, screen_h - 2, screen_w - 1)
        elif key == ord('q'):
            break

    # Trở lại chế độ chờ đợi để chương trình hoạt động bình thường
    stdscr.nodelay(False)

def save_multiple_students(names: list[str], output_dir: str = "saved_results"):
    """
    Lưu thông tin chi tiết của nhiều thí sinh vào các file .txt riêng trong folder.
    names: danh sách tên thí sinh cần lưu.
    output_dir: thư mục để lưu file.
    """
    data_dir = os.path.join(os.getcwd(), 'data')
    os.makedirs(output_dir, exist_ok=True)

    try:
        with open(os.path.join(data_dir, 'students_submissions.json'), 'r', encoding='utf-8') as f:
            students = json.load(f)
    except FileNotFoundError:
        print("❌ Không tìm thấy file students_submissions.json")
        return

    # Đưa danh sách học sinh vào dict để tra cứu nhanh
    student_dict = {s.get("Name"): s for s in students}

    for name in names:
        student = student_dict.get(name)
        if not student:
            print(f"⚠️ Không tìm thấy học sinh: {name}")
            continue

        lines = []
        lines.append("--- THÔNG TIN THÍ SINH ---")
        lines.append(f"Mã Số {student.get('Name')}:")

        scores_data = student.get("Scores")
        if scores_data:
            for problem_name, score in scores_data.items():
                lines.append(f"  - Bài: {problem_name}, Điểm: {score}")
        else:
            lines.append("Thí sinh này không có dữ liệu.")

        lines.append("")
        lines.append("--- KẾT QUẢ CHI TIẾT CÁC BÀI KIỂM TRA ---")

        test_results_data = student.get("TestResults")
        if test_results_data:
            for problem_name, tests in test_results_data.items():
                lines.append(f"BÀI THI: {problem_name}")
                for test in tests:
                    stderr_output = "Không" if test.get('Stderr') == "" else test.get('Stderr')
                    line = f"Test: {test.get('Test')} - Điểm: {test.get('MarkEarned')} - Lỗi: {stderr_output}"
                    lines.append(line)
        else:
            lines.append("Thí sinh này không có dữ liệu thi.")

        # Lưu file riêng cho mỗi học sinh
        filepath = os.path.join(output_dir, f"{name}.txt")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"✅ Đã lưu {filepath}")




# Ví dụ sử dụng
def main(stdscr):
    show_student_details_scrollable(stdscr, "TRUONGHUY")

if __name__ == "__main__":
    curses.wrapper(main)
