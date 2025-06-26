import pydicom
import uuid
from datetime import datetime
from typing import Dict, List, Any

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

def generate_narrative(resource_type: str, resource_data: Dict[str, Any]) -> Dict[str, Any]:
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
        value = resource_data.get("valueString", "No value")
        code = resource_data["code"]["coding"][0]["display"]
        return {
            "status": "generated",
            "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">Observation: {code} - {value}</div>"
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

    # Parse patient name components from DICOM format (Family^Given^Middle)
    name_parts = patient_name.split('^') if patient_name else []
    family_name = name_parts[0] if len(name_parts) > 0 else ''
    given_names = name_parts[1:] if len(name_parts) > 1 else []

    # Get additional patient demographics
    raw_birth_date = str(ds.get('PatientBirthDate', '')).strip()
    birth_date = ""
    if raw_birth_date and len(raw_birth_date) == 8 and raw_birth_date.isdigit():
        birth_date = f"{raw_birth_date[:4]}-{raw_birth_date[4:6]}-{raw_birth_date[6:8]}"

    gender = str(ds.get('PatientSex', 'unknown')).lower()

    # Map DICOM gender codes to FHIR standard
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

    # Add narrative text for human-readable summary
    patient_resource["text"] = generate_narrative("Patient", patient_resource)

    return patient_resource

def extract_observations(ds: pydicom.Dataset, patient_ref: str) -> List[Dict[str, Any]]:
    """
    Extract comprehensive observations from a DICOM SR dataset.

    Args:
        ds (pydicom.Dataset): The DICOM dataset.
        patient_ref (str): Reference ID for the patient.

    Returns:
        List[Dict[str, Any]]: List of FHIR Observation resources.
    """
    observations = []

    def process_content_sequence(sequence, parent_code=None):
        if not sequence:
            return

        for i, item in enumerate(sequence):
            # Extract observation code if available
            code = None
            if hasattr(item, 'ConceptNameCodeSequence'):
                code_seq = item.ConceptNameCodeSequence[0]
                code = {
                    "code": str(code_seq.get('CodeValue', '24606-6')),
                    "display": str(code_seq.get('CodeMeaning', 'Mammogram observation')),
                    "system": str(code_seq.get('CodingSchemeDesignator', 'http://loinc.org'))
                }

            # Create observation resource if there's a text value
            if hasattr(item, 'TextValue'):
                observation = {
                    "resourceType": "Observation",
                    "id": generate_uuid(),
                    "status": "final",
                    "code": {
                        "coding": [
                            code or {
                                "code": "24606-6",
                                "display": "MG Breast Screening",
                                "system": "http://loinc.org"
                            }
                        ]
                    },
                    "subject": {
                        "reference": f"Patient/{patient_ref}"
                    },
                    "valueString": str(item.TextValue),
                    "performer": [
                        {
                            "display": "Radiologist System"
                        }
                    ]
                }

                # Add narrative text for observation
                observation["text"] = generate_narrative("Observation", observation)

                # Add additional metadata if available
                if hasattr(item, 'ObservationDateTime') and item.ObservationDateTime:
                    obs_datetime = str(item.ObservationDateTime).strip()
                    if len(obs_datetime) == 14 and obs_datetime.isdigit():
                        # Format: YYYYMMDDHHMMSS → YYYY-MM-DDTHH:MM:SSZ
                        formatted = f"{obs_datetime[:4]}-{obs_datetime[4:6]}-{obs_datetime[6:8]}T{obs_datetime[8:10]}:{obs_datetime[10:12]}:{obs_datetime[12:14]}Z"
                        observation["effectiveDateTime"] = formatted
                elif hasattr(ds, 'StudyDate') and hasattr(ds, 'StudyTime'):
                    study_date = format_dicom_date(str(ds.StudyDate))
                    study_time = str(ds.StudyTime).strip()
                    if len(study_time) >= 6 and study_time.isdigit():
                        time = f"{study_time[:2]}:{study_time[2:4]}:{study_time[4:6]}"
                        observation["effectiveDateTime"] = f"{study_date}T{time}Z"
                    elif study_date:
                        observation["effectiveDateTime"] = study_date
                if hasattr(item, 'ObservationUID'):
                    observation["identifier"] = [{
                        "system": "urn:dicom:uid",
                        "value": str(item.ObservationUID)
                    }]

                observations.append(observation)

            # Recursively process nested content sequences
            if hasattr(item, 'ContentSequence'):
                process_content_sequence(item.ContentSequence, code)

    # Start processing from the root content sequence
    if hasattr(ds, 'ContentSequence'):
        process_content_sequence(ds.ContentSequence)

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
    # Get study date and time from DICOM dataset
    study_date = format_dicom_date(str(ds.get('StudyDate', '')))
    study_time = str(ds.get('StudyTime', ''))
    if study_time:
        study_time = f"{study_time[:2]}:{study_time[2:4]}:{study_time[4:6]}"

    # Combine date and time for effectiveDateTime
    if study_date and study_time:
        effective_date_time = f"{study_date}T{study_time}Z"  # Add 'Z' for UTC timezone
    else:
        effective_date_time = study_date

    # Extract procedure code if available
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

    # Add narrative text for diagnostic report
    report["text"] = generate_narrative("DiagnosticReport", report)

    return report

def dicom_to_fhir(dicom_path: str) -> Dict[str, Any]:
    """
    Convert a DICOM SR file to a FHIR Bundle with proper fullUrl references.

    Args:
        dicom_path (str): Path to the DICOM SR file.

    Returns:
        Dict[str, Any]: FHIR Bundle.
    """
    ds = pydicom.dcmread(dicom_path)

    # Extract patient resource
    patient = extract_patient_info(ds)
    patient_id = patient["id"]
    patient_ref = f"urn:uuid:{patient_id}"

    # Extract observations
    observations = extract_observations(ds, patient_id)

    # Update observation subject references to patient reference
    for obs in observations:
        obs["subject"]["reference"] = patient_ref

    # Create diagnostic report resource
    diagnostic_report = create_diagnostic_report(patient_id, observations, ds)
    diagnostic_report["subject"]["reference"] = patient_ref
    diagnostic_report["result"] = [{"reference": f"urn:uuid:{obs['id']}"} for obs in observations]

    # Construct Bundle entries combining patient, observations, and diagnostic report
    entries = [
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
    ]

    # Return the complete FHIR Bundle resource
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": entries
    }

if __name__ == "__main__":
    # Example usage: Convert a DICOM SR file to FHIR Bundle and print the result
    fhir_message = dicom_to_fhir("brayz_sr.dcm")
    import json
    print(fhir_message)
    # Write the FHIR message to a JSON file for further use or inspection
    output_file = "fhir_output.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(fhir_message, f, indent=2, ensure_ascii=False)

    print(f"FHIR message has been written to {output_file}")

