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
    birth_date = str(ds.get('PatientBirthDate', '0000-01-01'))
    if '-' in birth_date:
        pass
    else:
        birth_date = f"{birth_date[:4]}-{birth_date[4:6]}-{birth_date[6:8]}"
    gender = str(ds.get('PatientSex', 'unknown')).lower()

    if gender.lower() == 'm':
        gender = 'male'
    elif gender.lower() == 'f':
        gender = 'female'
    else:
        gender = 'other'
    
    return {
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

        "gender": gender,
        "birthDate": birth_date
    }

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
            # Get observation code if available
            code = None
            if hasattr(item, 'ConceptNameCodeSequence'):
                code_seq = item.ConceptNameCodeSequence[0]
                code = {
                    "code": str(code_seq.get('CodeValue', '24606-6')),
                    "display": str(code_seq.get('CodeMeaning', 'Mammogram observation')),
                    "system": str(code_seq.get('CodingSchemeDesignator', 'http://loinc.org'))
                }
            
            # Create observation if there's a text value
            if hasattr(item, 'TextValue'):
                observation = {
                    "resourceType": "Observation",
                    "id": f"obs-{len(observations) + 1}",
                    "status": "final",
                    "code": {
                        "coding": [
                            code or {
                                "code": "24606-6",
                                "display": "Mammogram observation",
                                "system": "http://loinc.org"
                            }
                        ]
                    },
                    "subject": {
                        "reference": f"Patient/{patient_ref}"
                    },
                    "valueString": str(item.TextValue)
                }
                
                # Add additional metadata if available
                if hasattr(item, 'ObservationDateTime'):
                    observation["effectiveDateTime"] = str(item.ObservationDateTime)
                if hasattr(item, 'ObservationUID'):
                    observation["identifier"] = [{
                        "system": "urn:dicom:uid",
                        "value": str(item.ObservationUID)
                    }]
                
                observations.append(observation)
            
            # Process nested content sequences
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
    # Get study date and time
    study_date = format_dicom_date(str(ds.get('StudyDate', '')))
    study_time = str(ds.get('StudyTime', ''))
    if study_time:
        study_time = f"{study_time[:2]}:{study_time[2:4]}:{study_time[4:6]}"
    
    effective_date_time = f"{study_date}T{study_time}" if study_date and study_time else study_date
    
    # Get procedure code
    procedure_code = None
    if hasattr(ds, 'ProcedureCodeSequence'):
        code_seq = ds.ProcedureCodeSequence[0]
        procedure_code = {
            "code": str(code_seq.get('CodeValue', '24606-6')),
            "display": str(code_seq.get('CodeMeaning', 'Mammogram Diagnostic Report')),
            "system": str(code_seq.get('CodingSchemeDesignator', 'http://loinc.org'))
        }
    
    return {
        "resourceType": "DiagnosticReport",
        "id": "report-1",
        "status": "final",
        "code": {
            "coding": [
                procedure_code or {
                    "code": "24606-6",
                    "display": "Mammogram Diagnostic Report",
                    "system": "http://loinc.org"
                }
            ]
        },
        "subject": {
            "reference": f"Patient/{patient_ref}"
        },
        "effectiveDateTime": effective_date_time,
        "issued": datetime.now().isoformat(),
        "performer": [
            {
                "display": str(ds.get('ReferringPhysicianName', 'Unknown Physician'))
            }
        ],
        "result": [{"reference": f"Observation/{obs['id']}"} for obs in observations],
        "identifier": [
            {
                "system": "urn:dicom:uid",
                "value": str(ds.get('StudyInstanceUID', ''))
            }
        ],
        "imagingStudy": [
            {
                "reference": f"ImagingStudy/{ds.get('StudyInstanceUID', '')}"
            }
        ]
    }

def dicom_to_fhir(dicom_path: str) -> Dict[str, Any]:
    """
    Convert a DICOM SR file to FHIR format.
    
    Args:
        dicom_path (str): Path to the DICOM SR file.
        
    Returns:
        Dict[str, Any]: FHIR message dictionary containing patient, observations, and diagnostic report.
    """
    # Read DICOM file
    ds = pydicom.dcmread(dicom_path)
    
    # Extract patient information
    patient = extract_patient_info(ds)
    patient_ref = patient['id']
    
    # Extract observations
    observations = extract_observations(ds, patient_ref)
    
    # Create diagnostic report
    diagnostic_report = create_diagnostic_report(patient_ref, observations, ds)
    
    # Construct final FHIR message
    fhir_message = {
        "fhir": {
            "patient": patient,
            "observations": observations,
            "diagnostic_report": diagnostic_report
        }
    }
    
    return fhir_message

if __name__ == "__main__":
    # Example usage
    fhir_message = dicom_to_fhir("/media/zain/New Volume/PycharmProjects/DataFormation/hl7 work/brayz_sr.dcm")
    import json
    print(fhir_message)
    # Write the FHIR message to a JSON file
    output_file = "fhir_output.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(fhir_message, f, indent=2, ensure_ascii=False)
    
    print(f"FHIR message has been written to {output_file}")

