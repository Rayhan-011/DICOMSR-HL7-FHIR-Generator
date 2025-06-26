import pydicom


def extract_sr_report(ds):
    if not hasattr(ds, 'ContentSequence'):
        return "No ContentSequence found."

    output = []
    for item in ds.ContentSequence:
        parse_item(item, output, level=0)
    return "\n".join(output)


def parse_item(item, output, level):
    indent = "  " * level

    # Get concept name if exists
    name = ""
    if "ConceptNameCodeSequence" in item:
        name = item.ConceptNameCodeSequence[0].CodeMeaning

    value_type = item.get("ValueType", "")
    rel_type = item.get("RelationshipType", "")

    if value_type == "CONTAINER":
        if name:
            output.append(f"{indent}{name}")
        else:
            output.append(f"{indent}[Unnamed CONTAINER]")
    elif value_type == "IMAGE":
        output.append(f"{indent}") # DXm image
    elif value_type == "CODE":
        code = item.get("ConceptCodeSequence", [{}])[0]
        code_meaning = code.get("CodeMeaning", "")
        code_value = code.get("CodeValue", "")
        code_scheme = code.get("CodingSchemeDesignator", "")
        output.append(f"{indent}{name} = {code_meaning} ({code_value}, {code_scheme})")
    elif value_type == "NUM":
        mvs = item.get("MeasuredValueSequence", [{}])[0]
        val = mvs.get("NumericValue", "")
        unit = mvs.get("MeasurementUnitsCodeSequence", [{}])[0].get("CodeMeaning", "")
        output.append(f"{indent}{name} = {val} {unit}")
    elif value_type == "TEXT":
        val = item.get("TextValue", "")
        output.append(f"{indent}{name} = \"{val}\"")

    elif value_type == "DATE":
        output.append(f"{indent}{name} = {item.get('Date', '')}")
    elif value_type == "TIME":
        output.append(f"{indent}{name} = {item.get('Time', '')}")
    else:
        output.append(f"{indent}{name} = [Unknown or unhandled value type: {value_type}]")

    # Recursively handle nested content
    if "ContentSequence" in item:
        for sub_item in item.ContentSequence:
            parse_item(sub_item, output, level + 1)


def process_acquisition_context(image_item, output, level):
    indent = "  " * level
    if not hasattr(image_item, "ContentSequence"):
        return

    for ac_item in image_item.ContentSequence:
        if ac_item.get("RelationshipType") != "HAS ACQ CONTEXT":
            continue

        name = ac_item.get("ConceptNameCodeSequence", [{}])[0].get("CodeMeaning", "Unknown")
        value_type = ac_item.get("ValueType", "")

        value = ""
        if value_type == "CODE":
            code_seq = ac_item.get("ConceptCodeSequence", [{}])[0]
            code_meaning = code_seq.get("CodeMeaning", "")
            code_value = code_seq.get("CodeValue", "")
            code_scheme = code_seq.get("CodingSchemeDesignator", "")
            value = f"{code_meaning} ({code_value}, {code_scheme})"

        elif value_type == "NUM":
            mvs = ac_item.get("MeasuredValueSequence", [{}])[0]
            num = mvs.get("NumericValue", "")
            unit = mvs.get("MeasurementUnitsCodeSequence", [{}])[0].get("CodeMeaning", "")
            value = f"{num} {unit}"

        elif value_type == "TEXT":
            value = ac_item.get("TextValue", "")

        elif value_type == "DATE":
            value = ac_item.get("Date", "")

        elif value_type == "TIME":
            value = ac_item.get("Time", "")

        if value:
            output.append(f"{indent}Acquisition Context: {name} = {value}")


def create_obx_segments(report):
    report_list = report.split('\n')
    obx_segments = []
    i = 1  # OBX segment index starts at 1

    heading = ''

    for line in report_list:
        if line.strip() == '':
            if heading == 'Image Library':
                obx_segments.append(f"OBX|{i}|ST|IMAGELIBRARY^^AIENGINE||DXm image||||||F")
                i += 1
            continue


        leading_spaces = len(line) - len(line.lstrip(' '))
        if leading_spaces == 0: # heading
            if '=' in line:
                line1 = line.split('=', 1)[0].strip()
                line2 = line.split('=', 1)[1].strip()

                obx_segments.append(f"OBX|{i}|ST|TITLETAG^^AIENGINE||{line1}||||||F")
                i += 1
                obx_segments.append(f"OBX|{i}|ST|RESULTSTAG^^AIENGINE||{line2.lstrip(' ')}||||||F")

                heading = line

            else:
                obx_segments.append(f"OBX|{i}|ST|TITLETAG^^AIENGINE||{line}||||||F")

                heading = line


        else:
            obx_segments.append(f"OBX|{i}|ST|RESULTSTAG^^AIENGINE||{line}||||||F")
        i += 1
    obx_segments = '\n'.join(obx_segments)
    return obx_segments


def generate_obx_from_mammo_sr(ds):
    report = extract_sr_report(ds)
    obx_srgments = create_obx_segments(report)
    return  obx_srgments


if __name__ == "__main__":
    # Example usage
    ds = pydicom.dcmread("IM-0003-0022.dcm", force=True)
    report = extract_sr_report(ds)
    print(report)
    print(type(report))
    print()
    obx_srgments = create_obx_segments(report)
    print(obx_srgments)
