import pydicom
import uuid
from datetime import datetime
from typing import Dict, List, Any
import json


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

def generate_uuid() -> str:
    """
    Generate a UUID for FHIR resources.

    Returns:
        str: A string representation of a UUID.
    """
    return str(uuid.uuid4())

def format_dicom_date(date_str: str) -> str:
    """
    Format a DICOM date string (YYYYMMDD) to FHIR date format (YYYY-MM-DD).

    Args:
        date_str (str): The DICOM date string.

    Returns:
        str: Formatted date string or empty string if input is invalid.
    """
    if not date_str:
        return ""
    try:
        # Handle DICOM date format (YYYYMMDD)
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    except Exception:
        return ""

def generate_narrative(resource_type, resource_data, report_text= None) -> Dict[str, Any]:
    """
    Generate a basic narrative for FHIR resources.

    Args:
        resource_type (str): The type of FHIR resource.
        resource_data (Dict[str, Any]): The resource data.

    Returns:
        Dict[str, Any]: The text field for the resource.
    """

    if resource_type == "Patient":
        name = " ".join(resource_data["name"][0].get("given", [])) + " " + resource_data["name"][0].get("family", "")
        return {
            "status": "generated",
            "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">Patient: {name.strip()} (ID: {resource_data['identifier'][0]['value']})</div>"
        }
    elif resource_type == "Observation":
        if report_text:
            #value = resource_data.get("valueString", "No value")
            #code = resource_data["code"]["coding"][0]["display"]
            return {
                "status": "generated",
                "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">Observation:{report_text}</div>"
            }
    elif resource_type == "DiagnosticReport":
        return {
            "status": "generated",
            "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">Diagnostic Report: {resource_data['code']['coding'][0]['display']}</div>"
        }
    return {
        "status": "generated",
        "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">{resource_type} Resource</div>"
    }


def extract_patient_info(ds: pydicom.Dataset) -> Dict[str, Any]:
    """
    Extract comprehensive patient information from a DICOM dataset.

    Args:
        ds (pydicom.Dataset): The DICOM dataset.

    Returns:
        Dict[str, Any]: A dictionary representing the FHIR Patient resource.
    """
    patient_id = str(ds.get('PatientID', ''))
    patient_name = str(ds.get('PatientName', ''))

    # Parse patient name components
    name_parts = patient_name.split('^') if patient_name else []
    family_name = name_parts[0] if len(name_parts) > 0 else ''
    given_names = name_parts[1:] if len(name_parts) > 1 else []

    # Get additional patient demographics
    raw_birth_date = str(ds.get('PatientBirthDate', '')).strip()
    birth_date = ""
    if raw_birth_date and len(raw_birth_date) == 8 and raw_birth_date.isdigit():
        birth_date = f"{raw_birth_date[:4]}-{raw_birth_date[4:6]}-{raw_birth_date[6:8]}"

    gender = str(ds.get('PatientSex', 'unknown')).lower()

    if gender.lower() == 'm':
        gender = 'male'
    elif gender.lower() == 'f':
        gender = 'female'
    else:
        gender = 'other'

    patient_resource = {
        "resourceType": "Patient",
        "id": generate_uuid(),
        "identifier": [
            {
                "system": "http://hospital.smarthealth.org/patient-id",
                "value": patient_id
            }
        ],
        "name": [
            {
                "family": family_name,
                "given": given_names
            }
        ],
        "gender": gender
    }

    if birth_date:
        patient_resource["birthDate"] = birth_date

    # Add narrative text
    patient_resource["text"] = generate_narrative("Patient", patient_resource)

    return patient_resource


def extract_study_info(ds: pydicom.Dataset, patient_reference: str) -> Dict[str, Any]:

    study_uid = str(ds.get('StudyInstanceUID', ''))
    accession_number = str(ds.get('AccessionNumber', ''))
    study_date = str(ds.get('StudyDate', ''))
    study_time = str(ds.get('StudyTime', ''))

    started = ""
    if study_date and len(study_date) == 8:
        started = f"{study_date[:4]}-{study_date[4:6]}-{study_date[6:8]}"
        if study_time and len(study_time) >= 6:
            started += f"T{study_time[:2]}:{study_time[2:4]}:{study_time[4:6]}Z"

    study_resource = {
        "resourceType": "ImagingStudy",
        "id": generate_uuid(),
        "identifier": [
            {
                "system": "urn:dicom:uid",
                "value": study_uid
            }
        ],
        "status": "registered",
        "subject": {
            "reference": patient_reference
        }
    }

    if accession_number:
        study_resource["identifier"].append({
            "system": "http://hospital.smarthealth.org/accession-number",
            "value": accession_number
        })

    if started:
        study_resource["started"] = started

    # Add narrative
    study_resource["text"] = generate_narrative("ImagingStudy", study_resource)

    return study_resource


def extract_observations(ds, report, patient_ref) -> List[Dict[str, Any]]:
    observations = []

    def process_content_sequence(report, parent_code=None):

        report_list = report.split('\n')

        heading = ''

        for i, line in enumerate(report_list):

            leading_spaces = len(line) - len(line.lstrip(' '))
            if leading_spaces == 0:
                heading = line

            if line.strip() == '':
                print(heading, line)
                if heading == 'Image Library':
                    line = "DXm image"
                else:
                    continue


            # Get observation code if available
            line_data = line.lstrip()
            value_string = line_data
            display = line_data
            if '=' in line_data:
                display = line_data.split('=')[0].strip()
                value_string = line_data.split('=')[1].strip()

            # Create observation if there's a text value
            observation = {
                "resourceType": "Observation",
                "id": generate_uuid(),
                "status": "final",
                "code": {
                    "coding": [
                        {
                            "system": "http://loinc.org"
                        }
                    ]
                },
                "subject": {
                    "reference": f"Patient/{patient_ref}"
                },
                "valueString": value_string,
                "performer": [
                    {
                        "display": "Radiologist System"
                    }
                ]
            }

            # Add narrative text
            observation["text"] = generate_narrative("Observation", observation, line)

            # Add additional metadata if available
            study_date = format_dicom_date(str(ds.StudyDate))
            study_time = str(ds.StudyTime).strip()
            if len(study_time) >= 6 and study_time.isdigit():
                time = f"{study_time[:2]}:{study_time[2:4]}:{study_time[4:6]}"
                observation["effectiveDateTime"] = f"{study_date}T{time}Z"
            elif study_date:
                observation["effectiveDateTime"] = study_date

            observations.append(observation)

    process_content_sequence(report)

    return observations


def create_diagnostic_report(patient_ref: str, observations: List[Dict[str, Any]], ds: pydicom.Dataset) -> Dict[str, Any]:
    """
    Create a comprehensive DiagnosticReport resource.

    Args:
        patient_ref (str): Reference ID for the patient.
        observations (List[Dict[str, Any]]): List of Observation resources.
        ds (pydicom.Dataset): The DICOM dataset.

    Returns:
        Dict[str, Any]: FHIR DiagnosticReport resource.
    """
    # Get study date and time
    study_date = format_dicom_date(str(ds.get('StudyDate', '')))
    study_time = str(ds.get('StudyTime', ''))
    if study_time:
        study_time = f"{study_time[:2]}:{study_time[2:4]}:{study_time[4:6]}"

    if study_date and study_time:
        effective_date_time = f"{study_date}T{study_time}Z"  # Add 'Z' for UTC timezone
    else:
        effective_date_time = study_date

    # Get procedure code
    procedure_code = None
    if hasattr(ds, 'ProcedureCodeSequence'):
        code_seq = ds.ProcedureCodeSequence[0]
        procedure_code = {
            "code": str(code_seq.get('CodeValue', '24606-6')),
            "display": str(code_seq.get('CodeMeaning', 'Mammogram Diagnostic Report')),
            "system": str(code_seq.get('CodingSchemeDesignator', 'http://loinc.org'))
        }

    report = {
        "resourceType": "DiagnosticReport",
        "id": generate_uuid(),
        "status": "final",
        "code": {
            "coding": [
                procedure_code or {
                    "code": "24606-6",
                    "display": "MG Breast Screening",
                    "system": "http://loinc.org"
                }
            ]
        },

        "subject": {
            "reference": f"Patient/{patient_ref}"
        },
        "effectiveDateTime": effective_date_time,
        "issued": datetime.utcnow().isoformat() + 'Z',
        "performer": [
            {
                "display": str(ds.get('ReferringPhysicianName', 'Unknown Physician'))
            }
        ],
        "result": [{"reference": f"urn:uuid:{obs['id']}"} for obs in observations],
        "identifier": [
            {
                "system": "urn:dicom:uid",
                "value": str(ds.get('StudyInstanceUID', ''))
            }
        ]
    }

    # Add narrative text
    report["text"] = generate_narrative("DiagnosticReport", report)

    return report


def dicom_to_fhir(ds):
    report = extract_sr_report(ds)

    # Extract patient
    patient = extract_patient_info(ds)
    patient_id = patient["id"]
    patient_ref = f"urn:uuid:{patient_id}"

    study_resource = extract_study_info(ds, f"urn:uuid:{patient_id}")

    # Extract observations
    observations = extract_observations(ds, report, patient_id)

    # Fix observation subject references
    for obs in observations:
        obs["subject"]["reference"] = patient_ref

        # Create diagnostic report
        diagnostic_report = create_diagnostic_report(patient_id, observations, ds)
        diagnostic_report["subject"]["reference"] = patient_ref
        diagnostic_report["result"] = [{"reference": f"urn:uuid:{obs['id']}"} for obs in observations]

        # Construct Bundle entries
        entries = ([
                      {
                          "fullUrl": f"urn:uuid:{patient_id}",
                          "resource": patient
                      }
                    ] + [
                    {
                    "fullUrl": f"urn:uuid:{study_resource['id']}",
                    "resource": study_resource
                    }
                    ] +

                   [
                      {
                          "fullUrl": f"urn:uuid:{obs['id']}",
                          "resource": obs
                      } for obs in observations
                  ] + [
                      {
                          "fullUrl": f"urn:uuid:{diagnostic_report['id']}",
                          "resource": diagnostic_report
                      }
                  ])

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": entries
    }

if __name__ == "__main__":
    # Example usage
    ds = pydicom.dcmread("IM-0003-0022.dcm")
    suid = ds.StudyInstanceUID
    print("SUID", suid)
    report = extract_sr_report(ds)
    print(report)

    # Extract patient
    patient = extract_patient_info(ds)
    patient_id = patient["id"]
    patient_ref = f"urn:uuid:{patient_id}"



    # Extract observations
    observations = extract_observations(ds, report, patient_id)

    # Fix observation subject references
    for obs in observations:
        obs["subject"]["reference"] = patient_ref

        # Create diagnostic report
        diagnostic_report = create_diagnostic_report(patient_id, observations, ds)
        diagnostic_report["subject"]["reference"] = patient_ref
        diagnostic_report["result"] = [{"reference": f"urn:uuid:{obs['id']}"} for obs in observations]

        # Construct Bundle entries
        entries = ([
                      {
                          "fullUrl": f"urn:uuid:{patient_id}",
                          "resource": patient
                      }
                  ] + [
                      {
                          "fullUrl": f"urn:uuid:{obs['id']}",
                          "resource": obs
                      } for obs in observations
                  ] + [
                      {
                          "fullUrl": f"urn:uuid:{diagnostic_report['id']}",
                          "resource": diagnostic_report
                      }
                  ])

    print({
        "resourceType": "Bundle",
        "type": "collection",
        "entry": entries
    })

    with open("output.json", "w") as f:
        json.dump({
        "resourceType": "Bundle",
        "type": "collection",
        "entry": entries
        },f, indent=4)


