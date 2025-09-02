import curses
from setting import MENU_MAIN,LOGO
from ulti_tui import draw_logo,draw_menu,draw_title,get_text_input
import page
from ulti_tui import draw_answers_table

MENU = MENU_MAIN

def main(stdscr):
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_GREEN)
    stdscr.keypad(True)

    current_idx = 0
    while True:
        stdscr.clear()
        # Vẽ giao diện chính
        logo_height = draw_logo(stdscr, y=0)
        draw_title(stdscr, "Menu chính", logo_height + 1)
        draw_menu(stdscr, current_idx, logo_height + 3, MENU_MAIN)
        table_y = logo_height + 3 + len(MENU_MAIN) + 1
        draw_answers_table(stdscr, table_y)
        stdscr.refresh() # Cần refresh trước khi chờ input

        # Xử lý nhập liệu
        key = stdscr.getch()

        if key == ord('/'):
            input_id = get_text_input(stdscr,0,0,"Nhập ID người dùng hoặc tên")

            if input_id.strip():
                page.show_student_details(stdscr, input_id.strip())
            # Vòng lặp sẽ tự động vẽ lại màn hình chính
            continue

        # Xử lý menu bình thường
        if key == curses.KEY_UP and current_idx > 0:
            current_idx -= 1
        elif key == curses.KEY_DOWN and current_idx < len(MENU) - 1:
            current_idx += 1
        elif key in [curses.KEY_ENTER, 10, 13]:
            if current_idx == 0:
                page.setting(stdscr)
            elif current_idx == 1:
                page.start_grading(stdscr)
            else:
                break # Thoát nếu chọn "Thoát"
        elif key in [ord("q"), ord("Q")]:
            break

if __name__ == '__main__':
    curses.wrapper(main)
