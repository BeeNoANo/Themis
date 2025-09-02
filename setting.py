MENU_MAIN = ["Cài đặt", "Bắt đầu chấm", "Thoát"]
MENU_SETTING = ["Thêm folder đáp án", "Thêm folder thí sinh", "Thoát"]
current_idx = 0

LOGO = r"""
_____ _   _ _____ __  __ ___ ____
 |_   _| | | | ____|  \/  |_ _/ ___|
   | | | |_| |  _| | |\/| || |\___ \
   | | |  _  | |___| |  | || | ___) |
   |_| |_| |_|_____|_|  |_|___|____/
"""

default_setting = {
    "version": "1.0",
    "encoding": "utf-8",
    "ExamInfomation": {
        "UseStdIn": "true",
        "UseStdOut": "true",
        "EvaluatorName":"C1LinesWordsIgnoreCase.dll",
        "Mark": 0.25,
        "TimeLimit": 1,
        "MemoryLimit": 1024
    }
}
