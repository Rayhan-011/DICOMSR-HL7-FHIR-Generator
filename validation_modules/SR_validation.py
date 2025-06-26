import pydicom

validation_dict = {}

def extract_content_sequence_data(ds):
    try:
        if not hasattr(ds, 'ContentSequence'):
            return False

        output = []
        for item in ds.ContentSequence:
            parse_item(item, output, level=0)
            data = "\n".join(output)
        return True
    except Exception as e:
        return False

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

def validate_SR(ds):

    global validation_dict

    # Extract SOP Class UID
    sop_class_uid = ds.get("SOPClassUID", None)

    # Validate SOP Class UID
    if sop_class_uid :
        validation_dict['SOPClassUID'] = True
    else:
        print(f"❌ Invalid or unsupported SOP Class UID: {sop_class_uid}")
        validation_dict['SOPClassUID'] = False

    if ds.get('Modality') != "SR":
        print("❌ Modality is not 'SR'")
        validation_dict['Modality'] = False
        print(f"❌ Invalid or unsupported Modality: {ds.get('Modality')}")
        exit()
    else:
        validation_dict['Modality'] = True

    if ds.get('StudyInstanceUID'):
        validation_dict['StudyInstanceUID'] = True
    else:
        print("❌ StudyInstanceUID is missing")
        validation_dict['StudyInstanceUID'] = False
        exit()

    if ds.get('SeriesInstanceUID'):
        validation_dict['SeriesInstanceUID'] = True
    else:
        print("❌ StudyInstanceUID is missing")
        validation_dict['StudyInstanceUID'] = False
        exit()

    if ds.get('PatientID'):
        validation_dict['PatientID'] = True
    else:
        print("❌ PatientID is missing")
        validation_dict['PatientID'] = False

        print("SR file invalid")
        exit()

    if ds.get('AccessionNumber'):
        validation_dict['AccessionNumber'] = True
    else:
        print("❌ AccessionNumber is missing")
        validation_dict['AccessionNumber'] = False
        print("SR file invalid")
        exit()

    if ds.get('SOPInstanceUID'):
        validation_dict['SOPInstanceUID'] = True
    else:
        print("❌ SOPInstanceUID is missing")
        validation_dict['SOPInstanceUID'] = False
        print("SR file invalid")
        exit()

    if ds.get('StudyDate'):
        validation_dict['StudyDate'] = True
    else:
        print("❌ StudyDate is missing")
        validation_dict['StudyDate'] = False
        print("SR file invalid")
        exit()

    if ds.get('StudyTime'):
        validation_dict['StudyTime'] = True
    else:
        print("❌ StudyTime is missing")
        validation_dict['StudyTime'] = False
        print("SR file invalid")
        exit()


    if ds.get('ContentDate'):
        validation_dict['ContentDate'] = True
    else:
        print("❌ ContentDate is missing")
        validation_dict['ContentDate'] = False
        print("SR file invalid")
        exit()


    if ds.get('ContentTime'):
        validation_dict['ContentTime'] = True
    else:
        print("❌ ContentTime is missing")
        validation_dict['ContentTime'] = False
        print("SR file invalid")
        exit()

    try:
        status = extract_content_sequence_data(ds)
        if status == False:
            print("❌ ContentSequence is missing or invalid")
            validation_dict['ContentSequence'] = False
            print("Unable to extract ContentSequence data. SR file invalid or missing ContentSequence.")
            exit()
        elif status == True:
            validation_dict['ContentSequence'] = True

    except:
        print("❌ ContentSequence is missing or invalid")
        validation_dict['ContentSequence'] = False


if __name__ == "__main__":
    path_to_dcm_file = 'E:\\WORK\\MachineLearning\\Python\\DICOMSRtoHL7_FHIR\\v2\\IM-0003-0022.dcm'  # Replace with your DICOM file path
    ds = pydicom.dcmread(path_to_dcm_file)

    print("Validating SR FILE tags and structured data...")
    validate_SR(ds)
    print("✅ Validation complete.")

    print("\nValidation results:")

    for key, value in validation_dict.items():
        if value:
            print(f"✅ {key} exits.")
        else:
            print(f"❌ {key} is invalid or missing.")


