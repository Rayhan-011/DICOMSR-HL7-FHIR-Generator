from datetime import datetime
import uuid
from typing import Union, List
import pydicom
from obx_former import generate_obx_from_mammo_sr


def create_hl7_msh_segment(data: dict) -> str:
    field_sep = '|'
    encoding_chars = '^~\\&'

    # MSH-1 to MSH-18
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
        'UNICODE UTF-8'              # MSH-18: Character Set
    ]

    # Construct the MSH string (note: field separator is not included as a field, it's used between fields)
    msh_segment = field_sep.join(msh_fields)
    return msh_segment


def create_hl7_pid_segment(source: Union[dict, pydicom.dataset.FileDataset]) -> str:
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
            "", "",                        # OBR-17, OBR-18 (Accession duplication)
            accession_number,              # OBR-18
            "", "", "", "", "",            # OBR-19 to OBR-23
            modality                       # OBR-24: Diagnostic Service Section ID
        ]
        return field_sep.join(obr_fields)

    if isinstance(data, dict):
        return get_from_json()
    elif isinstance(data, pydicom.dataset.FileDataset):
        return get_from_dicom()
    else:
        raise ValueError("Input must be a JSON dictionary or pydicom DICOM SR dataset.")


def create_zds_segment(data: Union[dict, pydicom.dataset.FileDataset]) -> str:
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
        if not study_instance_uid:
            raise ValueError("StudyInstanceUID is required in DICOM to create ZDS segment.")
        return f"ZDS{field_sep}{study_instance_uid}"

    # Determine source type
    if isinstance(data, dict):
        return from_json()
    elif isinstance(data, pydicom.dataset.FileDataset):
        return from_dicom()
    else:
        raise TypeError("Input must be a dictionary (JSON) or a pydicom DICOM dataset.")


def create_obx_segments(data: Union[dict, pydicom.dataset.FileDataset]) -> List[str]:
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

def create_hl7_message(data):
    hl7_list = []

    hl7_list.append(create_hl7_msh_segment(data))
    hl7_list.append(create_hl7_pid_segment(data))
    hl7_list.append(create_obr_segment(data))
    hl7_list.append(create_zds_segment(data))
    hl7_list.append(create_obx_segments(data))

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
            "procedure_code": {
                "code": "24606-6",
                "system": "http://loinc.org",
                "display": "Mammogram Diagnostic Report"
            },
            "study_instance_uid": "1.2.840.113619.2.55.3.604688351.100.100.10000000000000000000"
        },
        "findings": [
            {
                "type": "text",
                "tag": "RESULTTAG",
                "value": "Suspicious mass in right breast, upper outer quadrant."
            },
            {
                "type": "text",
                "tag": "RESULTTAG",
                "value": "Left breast tissue appears normal."
            },
            {
                "type": "text",
                "tag": "RESULTTAG",
                "value": "BI-RADS 4: Suspicious abnormality. Consider biopsy."
            },
            {
                "type": "html",
                "tag": "HTMLTAG",
                "value": "<div><b>Impression:</b> Further evaluation recommended.</div>"
            },
            {
                "type": "html",
                "tag": "HTMLCRTAG",
                "value": "<html><body><p>Image result:</p><img src='data:image/png;base64,iVBOR...=='></body></html>"
            }
        ]
    }
    print(create_hl7_message(json_data))

    #print(create_hl7_pid_segment(json_data))

    #print(create_obr_segment(json_data))
    #print(create_zds_segment(json_data))
    #print(create_obx_segments(json_data))

    print()

    ds = pydicom.dcmread('brayz_sr.dcm')
    print(create_hl7_message(ds))
    #print(create_obr_segment(ds))
    #print(create_zds_segment(ds))
    #print(create_obx_segments(ds))

    print("\n")
    ds = pydicom.dcmread('IM-0003-0022.dcm')
    print(create_hl7_message(ds))
    #print(create_obr_segment(ds))
    #print(create_zds_segment(ds))
    #print(create_obx_segments(ds))

# IM-0003-0022.dcm
