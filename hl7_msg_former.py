from datetime import datetime
import uuid
from typing import Union, List
import pydicom
from obx_former import generate_obx_from_mammo_sr

def create_hl7_msh_segment(data: dict) -> str:
    """
    Create the HL7 MSH (Message Header) segment.

    Args:
        data (dict or pydicom.dataset.FileDataset): Input data source.

    Returns:
        str: Formatted MSH segment string.
    """
    field_sep = '|'
    encoding_chars = '^~\\&'

    if type(data) is not dict:
        specific_char_set = getattr(data, 'SpecificCharacterSet')
    else:
        specific_char_set = 'UNICODE UTF-8'

    # MSH-1 to MSH-18 fields
    msh_fields = [
        'MSH',                        # Segment name
        #field_sep,                    # MSH-1: Field Separator (represented by the field_sep itself)
        encoding_chars,               # MSH-2: Encoding Characters
        'PythonApp',                  # MSH-3: Sending Application
        'PythonFacility',             # MSH-4: Sending Facility
        'HL7ReceiverApp',             # MSH-5: Receiving Application
        'HL7ReceiverFacility',        # MSH-6: Receiving Facility
        datetime.now().strftime('%Y%m%d%H%M%S'),  # MSH-7: Date/Time of Message
        '',                           # MSH-8: Security (optional)
        'ORU^R01',                    # MSH-9: Message Type
        str(uuid.uuid4()),            # MSH-10: Message Control ID
        'P',                          # MSH-11: Processing ID (P = Production)
        '2.5',                        # MSH-12: Version ID
        '',                           # MSH-13: Sequence Number (optional)
        '',                           # MSH-14: Continuation Pointer (optional)
        'AL',                         # MSH-15: Accept Acknowledgment Type
        'NE',                         # MSH-16: Application Acknowledgment Type
        'USA',                        # MSH-17: Country Code
        specific_char_set             # MSH-18: Character Set
    ]

    # Construct the MSH string (field separator is used between fields)
    msh_segment = field_sep.join(msh_fields)
    return msh_segment

def create_hl7_pid_segment(source: Union[dict, pydicom.dataset.FileDataset]) -> str:
    """
    Create the HL7 PID (Patient Identification) segment.

    Args:
        source (dict or pydicom.dataset.FileDataset): Input data source.

    Returns:
        str: Formatted PID segment string.
    """
    field_sep = '|'
    component_sep = '^'

    # Initialize PID fields (up to PID-18; others left empty)
    pid_fields = ['PID'] + [''] * 17

    # PID-1: Set ID
    pid_fields[1] = '1'

    # Determine if source is JSON or DICOM
    if isinstance(source, dict):
        patient = source.get('patient', {})

        # PID-3: Patient Identifier List (e.g., MRN)
        pid_fields[3] = patient.get('id', '')

        # PID-5: Patient Name (Family^Given)
        name_data = patient.get('name', [{}])
        if name_data:
            name_data = name_data[0]
            family = name_data.get('family', '')
            given_list = name_data.get('given', [])
            given = given_list[0] if given_list else ''

            if family:
                pid_fields[5] = f"{family}{component_sep}{given}"
            else:
                pid_fields[5] = f"{given}"
        else:
            pid_fields[5]

        # PID-7: Date of Birth (YYYYMMDD)
        dob = patient.get('birth_date', '')
        if dob:
            pid_fields[7] = dob.replace('-', '')  # Convert to HL7 format

        # PID-8: Administrative Sex
        gender = patient.get('gender', '').upper()
        pid_fields[8] = {'F': 'F', 'M': 'M', 'O': 'O'}.get(gender[0], '') if gender else ''

    elif isinstance(source, pydicom.dataset.FileDataset):
        # PID-3: Patient ID
        pid_fields[3] = getattr(source, 'PatientID', '')

        # PID-5: Patient Name
        name = getattr(source, 'PatientName', None)
        if name:
            family = name.family_name if hasattr(name, 'family_name') else ''
            given = name.given_name if hasattr(name, 'given_name') else ''
            if given:
                pid_fields[5] = f"{family}{component_sep}{given}"
            else:
                pid_fields[5] = f"{family}"

        # PID-7: Birth Date
        birth_date = getattr(source, 'PatientBirthDate', '')
        pid_fields[7] = birth_date

        # PID-8: Sex
        sex = getattr(source, 'PatientSex', '')
        pid_fields[8] = sex

    # Return the PID segment string
    return field_sep.join(pid_fields)

def create_obr_segment(data: Union[dict, pydicom.dataset.FileDataset], obr_set_id=1) -> str:
    """
    Create the HL7 OBR (Observation Request) segment.

    Args:
        data (dict or pydicom.dataset.FileDataset): Input data source.
        obr_set_id (int): Set ID for the OBR segment.

    Returns:
        str: Formatted OBR segment string.
    """
    field_sep = '|'
    comp_sep = '^'

    def get_from_json():
        study = data.get("study", {})
        provider = data.get("provider", {})
        proc_code = study.get("procedure_code", {})

        procedure_code_str = comp_sep.join([
            proc_code.get("code", "24606-6"),
            proc_code.get("display", "Mammogram Diagnostic Report"),
            "LN"
        ])

        ordering_provider = comp_sep.join([
            provider.get("id", "UNKNOWN"),
            provider.get("name", "Unknown Physician")
        ])

        observation_datetime = (
            study.get("date", "").replace("-", "") + "000000"
            if study.get("date") else ""
        )

        accession_number = study.get("accession_number", "")

        obr_fields = [
            "OBR",                         # Segment name
            str(obr_set_id),               # OBR-1
            "",                            # OBR-2: Placer Order Number
            accession_number,              # OBR-3: Filler Order Number
            procedure_code_str,            # OBR-4: Universal Service Identifier
            "", "", "",                    # OBR-5 to OBR-7
            observation_datetime,          # OBR-7: Observation Date/Time
            "", "", "", "", "", "", "",    # OBR-8 to OBR-15
            ordering_provider,             # OBR-16: Ordering Provider
            "", "",                        # OBR-17, OBR-18 (can optionally duplicate accession)
            accession_number,              # OBR-18: Placer Field 1 (duplicate Accession)
            "", "", "", "", "",            # OBR-19 to OBR-23
            study.get("modality", "")      # OBR-24: Diagnostic Service Section ID (Modality)
        ]
        return field_sep.join(obr_fields)

    def get_from_dicom():
        study_date = getattr(data, "StudyDate", "")
        accession_number = getattr(data, "AccessionNumber", "")
        modality = getattr(data, "Modality", "")
        procedure_code_seq = getattr(data, "ProcedureCodeSequence", None)

        if not accession_number:
            raise ValueError("Accession number is required for OBR segment.")

        # Extract Procedure Code
        if procedure_code_seq and len(procedure_code_seq) > 0:
            procedure_code = procedure_code_seq[0]
            code_value = getattr(procedure_code, "CodeValue", "24606-6")
            code_meaning = getattr(procedure_code, "CodeMeaning", "Mammogram Diagnostic Report")
            coding_scheme = getattr(procedure_code, "CodingSchemeDesignator", "LN")
        else:
            code_value = "24606-6"
            code_meaning = "Mammogram Diagnostic Report"
            coding_scheme = "LN"

        procedure_code_str = comp_sep.join([code_value, code_meaning, coding_scheme])

        # Ordering Provider
        provider_id_seq = getattr(data, "ReferringPhysicianIdentificationSequence", None)
        provider_id = ""
        if provider_id_seq and len(provider_id_seq) > 0:
            provider_id = getattr(provider_id_seq[0], "IDNumber", "UNKNOWN")

        provider_name = str(getattr(data, "ReferringPhysicianName", "Anonymous Physician"))
        ordering_provider = comp_sep.join([provider_id, provider_name])

        observation_datetime = study_date + "000000" if study_date else ""

        obr_fields = [
            "OBR",                         # Segment name
            str(obr_set_id),               # OBR-1
            "",                            # OBR-2: Placer Order Number
            accession_number,              # OBR-3: Filler Order Number
            procedure_code_str,            # OBR-4
            "", "", "",                    # OBR-5 to OBR-7
            observation_datetime,          # OBR-7: Observation Date/Time
            "", "", "", "", "", "", "",    # OBR-8 to OBR-15
            ordering_provider,             # OBR-16: Ordering Provider
            "",                            # OBR-17
            accession_number,              # OBR-18
            "", "", "", "", "",            # OBR-19 to OBR-23
            modality,
            "F"                            # OBR-25: Status
        ]
        return field_sep.join(obr_fields)

    if isinstance(data, dict):
        return get_from_json()
    elif isinstance(data, pydicom.dataset.FileDataset):
        return get_from_dicom()
    else:
        raise ValueError("Input must be a JSON dictionary or pydicom DICOM SR dataset.")

def create_zds_segment(data: Union[dict, pydicom.dataset.FileDataset]) -> str:
    """
    Create the HL7 ZDS segment.

    Args:
        data (dict or pydicom.dataset.FileDataset): Input data source.

    Returns:
        str: Formatted ZDS segment string.
    """
    field_sep = '|'

    # Helper for JSON input
    def from_json():
        study = data.get("study", {})
        study_instance_uid = study.get("study_instance_uid", "").strip()
        if not study_instance_uid:
            raise ValueError("StudyInstanceUID is required in JSON to create ZDS segment.")
        return f"ZDS{field_sep}{study_instance_uid}"

    # Helper for DICOM input
    def from_dicom():
        study_instance_uid = getattr(data, "StudyInstanceUID", "").strip()
        series_instance_uid = getattr(data, "SeriesInstanceUID", "").strip()
        sop_instance_uid = getattr(data, "SOPInstanceUID", "").strip()
        if not study_instance_uid:
            raise ValueError("StudyInstanceUID is required in DICOM to create ZDS segment.")

        return f"ZDS{field_sep}{sop_instance_uid}{field_sep}{series_instance_uid}{field_sep}{study_instance_uid}"

    # Determine source type
    if isinstance(data, dict):
        return from_json()
    elif isinstance(data, pydicom.dataset.FileDataset):
        return from_dicom()
    else:
        raise TypeError("Input must be a dictionary (JSON) or a pydicom DICOM dataset.")

def create_obx_report_segments(data: Union[dict, pydicom.dataset.FileDataset]) -> List[str]:
    """
    Create HL7 OBX segments from findings in JSON or DICOM SR dataset.

    Args:
        data (dict or pydicom.dataset.FileDataset): Input data source.

    Returns:
        List[str]: List of formatted OBX segment strings.
    """
    field_sep = '|'
    comp_sep = '^'
    obx_segments = []

    def from_json():
        findings = data.get("findings", [])
        segments = []
        for idx, finding in enumerate(findings, start=1):
            ftype = finding.get("type", "text").lower()
            value = finding.get("value", "")
            value = " ".join(value.split())

            obx_1 = str(idx)              # Set ID
            obx_2 = "ST"
            tag = "RESULTSTAG"  #Default Value Type

            if ftype == "html":
                tag = "HTMLCRTAG"
                obx_2 = "ST"  # Formatted Text
            if ftype == "rtf":
                tag = "RTFCRTAG"
                obx_2 = "FT"

            obx_3 = f"{tag}{comp_sep * 2}AIENGINE"  # Observation Identifier (OBX-3)
            obx_4 = ""  # Observation Sub-ID (leave blank)
            obx_5 = value  # Observation Value

            # Build OBX
            obx_fields = [
                "OBX", obx_1, obx_2, obx_3, obx_4, obx_5,
                "", "", "", "", "",  # OBX-6 to OBX-10
                "F"                 # OBX-11: Final Result
            ]
            segments.append(field_sep.join(obx_fields))
        return segments

    if isinstance(data, dict):
        obx_segments = from_json()
        obx_segments = '\n'.join(obx_segments)
    elif isinstance(data, pydicom.dataset.FileDataset):
        obx_segments = generate_obx_from_mammo_sr(data)
    else:
        raise TypeError("Input must be a JSON dict or DICOM SR dataset")

    return obx_segments

def generate_sr_obx_UID_segments(ds):
    """
    Generate OBX segments for SR Document SOP Instance UID and related references.

    Args:
        ds (pydicom.Dataset): The DICOM dataset.

    Returns:
        List[str]: List of OBX segment strings.
    """
    obx_segments = []

    # OBX for SR Document SOP Instance UID
    sr_uid = ds.SOPInstanceUID
    obx_segments.append(['HD', 'SRINSTANCEUID^SR Instance UID^99IHE', '1', sr_uid])

    # Step 1: Build SOPInstanceUID → (SeriesInstanceUID, StudyInstanceUID) map
    sop_uid_map = {}
    for seq_tag in ['CurrentRequestedProcedureEvidenceSequence', 'PertinentOtherEvidenceSequence']:
        if seq_tag not in ds:
            continue
        for study_item in ds[seq_tag]:
            study_uid = getattr(study_item, 'StudyInstanceUID', '')
            for series_item in study_item.get('ReferencedSeriesSequence', []):
                series_uid = getattr(series_item, 'SeriesInstanceUID', '')
                for ref in series_item.get('ReferencedSOPSequence', []):
                    sop_uid = ref.ReferencedSOPInstanceUID
                    sop_uid_map[sop_uid] = (series_uid, study_uid)

    # Step 2: Walk through SR Content Sequence
    def walk_content_sequence(seq, sub_id_start, seen=set()):
        obx_data = []
        sub_id = sub_id_start

        for item in seq:
            if 'ReferencedSOPSequence' in item:
                for ref in item.ReferencedSOPSequence:
                    sop_uid = ref.ReferencedSOPInstanceUID
                    sop_class_uid = ref.ReferencedSOPClassUID

                    if sop_uid in seen:
                        continue
                    seen.add(sop_uid)

                    # Lookup Series and Study UID
                    series_uid, study_uid = sop_uid_map.get(sop_uid, ('', ''))


                    obx_data.append(['ST', 'STUDYINSTANCEUID^Study Instance UID^99IHE', str(sub_id), study_uid])
                    obx_data.append(['ST', 'SERIESINSTANCEUID^Series Instance UID^99IHE', str(sub_id), series_uid])
                    obx_data.append(['ST', 'SOPINSTANCEUID^SOP Instance UID^99IHE', str(sub_id), sop_uid])
                    obx_data.append(['ST', 'SOPCLASSUID^SOP Class UID^99IHE', str(sub_id), sop_class_uid])

                    sub_id += 1

            if 'ContentSequence' in item:
                nested_obx, sub_id = walk_content_sequence(item.ContentSequence, sub_id, seen)
                obx_data.extend(nested_obx)

        return obx_data, sub_id

    if 'ContentSequence' in ds:
        obx_img_refs, _ = walk_content_sequence(ds.ContentSequence, sub_id_start=2)
        obx_segments.extend(obx_img_refs)

    # Format into HL7 OBX segments with Set ID (OBX-1)
    formatted = []
    for i, obx in enumerate(obx_segments):
        obx_type, identifier, sub_id, value = obx
        formatted.append(f'OBX|{i + 1}|HD|{identifier}|{sub_id}|{value}||||||F')

    segments = '\n'.join(formatted)

    return segments

def create_hl7_message(data):
    """
    Create a complete HL7 message from input data.

    Args:
        data (dict or pydicom.dataset.FileDataset): Input data source.

    Returns:
        str: Complete HL7 message string.
    """
    hl7_list = []

    hl7_list.append(create_hl7_msh_segment(data))
    hl7_list.append(create_hl7_pid_segment(data))
    hl7_list.append(create_obr_segment(data))
    hl7_list.append(create_zds_segment(data))
    hl7_list.append(generate_sr_obx_UID_segments(data))
    hl7_list.append(create_obx_report_segments(data))

    hl7_message = '\n'.join(hl7_list)
    return hl7_message


if __name__ == "__main__":
    json_data = {
        "message_type": "json",
        "patient": {
            "id": "123456",
            "name": [
                {
                    "given": ["Jane"],
                    "family": "Doe"
                }
            ],
            "gender": "female",
            "birth_date": "1985-03-15"
        },
        "provider": {
            "id": "PROV001",
            "name": "Dr. Emily Carter",
            "department": "Radiology"
        },
        "study": {
            "date": "2025-05-12",
            "accession_number": "ACC20250512001",
            "modality": "MG",


