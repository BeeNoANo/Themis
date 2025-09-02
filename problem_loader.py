import xml.etree.ElementTree as ET

# ======== Default setting ========
default_setting = {
    "version": "1.0",
    "encoding": "utf-8",
    "ExamInformation": {
        "Name": "GOC",
        "InputFile": "GOC.INP",
        "OutputFile": "GOC.OUT",
        "UseStdIn": "true",
        "UseStdOut": "true",
        "EvaluatorName": "C1LinesWordsIgnoreCase.dll",
        "Mark": "0.25",
        "TimeLimit": "1",
        "MemoryLimit": "1024"
    },
    "TestCases": [
        {"Name": "test01", "Mark": "-1", "TimeLimit": "1", "MemoryLimit": "-1"},
        {"Name": "test02", "Mark": "-1", "TimeLimit": "1", "MemoryLimit": "-1"},
        {"Name": "test03", "Mark": "-1", "TimeLimit": "1", "MemoryLimit": "-1"},
    ]
}

# ======== Load .cfg (xml) file ========
def load_cfg(filename: str):
    tree = ET.parse(filename)
    root = tree.getroot()

    data = {
        "ExamInformation": root.attrib,
        "TestCases": [tc.attrib for tc in root.findall("TestCase")]
    }
    return data, tree, root

# ======== Update main ExamInformation ========
def update_exam_info(root, **kwargs):
    for key, value in kwargs.items():
        if key in root.attrib:
            root.attrib[key] = str(value)

# ======== Add or update TestCase ========
def update_testcase(root, name, **kwargs):
    testcases = root.findall("TestCase")
    for tc in testcases:
        if tc.attrib.get("Name") == name:
            for k, v in kwargs.items():
                tc.attrib[k] = str(v)
            return

    # Nếu không có thì thêm mới
    new_tc = ET.SubElement(root, "TestCase")
    new_tc.attrib.update({"Name": name})
    for k, v in kwargs.items():
        new_tc.attrib[k] = str(v)

# ======== Save back to file ========
def save_cfg(tree, filename: str):
    tree.write(filename, encoding="utf-8", xml_declaration=True)


# ================== DEMO ==================
# if __name__ == "__main__":
#     # Load
#     data, tree, root = load_cfg("Settings.cfg")
#     print("Before:", data)

#     # Update exam info
#     update_exam_info(root,
#                      Name="NEWNAME",
#                      InputFile="NEW.INP",
#                      OutputFile="NEW.OUT",
#                      Mark="0.5",
#                      TimeLimit="2")

#     # Update test case
#     update_testcase(root, "test02", Mark="1", TimeLimit="3", MemoryLimit="512")
#     update_testcase(root, "test04", Mark="2", TimeLimit="5", MemoryLimit="2048")  # thêm mới

#     # Save
#     save_cfg(tree, "config_new.cfg")
#     print("Updated config saved.")
