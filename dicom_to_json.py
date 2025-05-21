import pydicom
from typing import Dict, Any, List

def extract_custom_patient_info(ds: pydicom.Dataset) -> Dict[str, Any]:
    """
    Extract patient information for custom JSON output.
    
    Args:
        ds (pydicom.Dataset): The DICOM dataset.
        
    Returns:
        Dict[str, Any]: Patient information dictionary.
    """
    patient_id = str(ds.get("PatientID", ""))
    name_raw = str(ds.get("PatientName", ""))
    name_parts = name_raw.split("^")
    family = name_parts[0] if len(name_parts) > 0 else ""
    given = name_parts[1:] if len(name_parts) > 1 else []

    birth_date = str(ds.get("PatientBirthDate", "00000101"))
    if '-' in birth_date:
        pass
    else:
        birth_date = f"{birth_date[:4]}-{birth_date[4:6]}-{birth_date[6:8]}"

    gender = ds.get("PatientSex", "unknown").lower()
    gender = {"m": "male", "f": "female"}.get(gender, "other")

    return {
        "id": patient_id,
        "name": [{"given": given, "family": family}],
        "gender": gender,
        "birth_date": birth_date
    }

def extract_study_info(ds: pydicom.Dataset) -> Dict[str, Any]:
    """
    Extract study information from the DICOM dataset.
    
    Args:
        ds (pydicom.Dataset): The DICOM dataset.
        
    Returns:
        Dict[str, Any]: Study information dictionary.
    """
    study_date = str(ds.get("StudyDate", ""))
    if len(study_date) == 8:
        study_date = f"{study_date[:4]}-{study_date[4:6]}-{study_date[6:8]}"

    accession_number = str(ds.get("AccessionNumber", "UNKNOWN"))
    modality = str(ds.get("Modality", "MG"))

    procedure_code = {
        "code": "24606-6",
        "system": "http://loinc.org",
        "display": "Mammogram Diagnostic Report"
    }

    if hasattr(ds, "ProcedureCodeSequence"):
        pcs = ds.ProcedureCodeSequence[0]
        procedure_code = {
            "code": str(pcs.get("CodeValue", "24606-6")),
            "system": str(pcs.get("CodingSchemeDesignator", "http://loinc.org")),
            "display": str(pcs.get("CodeMeaning", "Mammogram Diagnostic Report"))
        }

    return {
        "date": study_date,
        "accession_number": accession_number,
        "modality": modality,
        "procedure_code": procedure_code
    }

def extract_provider_info(ds: pydicom.Dataset) -> Dict[str, Any]:
    """
    Extract provider information from the DICOM dataset.
    
    Args:
        ds (pydicom.Dataset): The DICOM dataset.
        
    Returns:
        Dict[str, Any]: Provider information dictionary.
    """
    provider_name = str(ds.get("ReferringPhysicianName", "Unknown"))
    provider_parts = provider_name.split("^")
    full_name = " ".join(provider_parts).strip()

    return {
        "name": full_name or "Unknown",
        "id": "PROV001",  # Static or mapped from your system
        "department": "Radiology"
    }

def extract_findings(ds: pydicom.Dataset) -> List[str]:
    """
    Extract textual findings from the SR ContentSequence.
    
    Args:
        ds (pydicom.Dataset): The DICOM dataset.
        
    Returns:
        List[str]: List of textual findings.
    """
    findings = []

    def process_sequence(seq):
        if not seq:
            return
        for item in seq:
            if hasattr(item, "TextValue"):
                findings.append(str(item.TextValue))
            if hasattr(item, "ContentSequence"):
                process_sequence(item.ContentSequence)

    if hasattr(ds, "ContentSequence"):
        process_sequence(ds.ContentSequence)

    return findings

def generate_custom_json(dicom_path: str) -> Dict[str, Any]:
    """
    Main function to generate custom JSON from DICOM SR.
    
    Args:
        dicom_path (str): Path to the DICOM SR file.
        
    Returns:
        Dict[str, Any]: Custom JSON message dictionary.
    """
    ds = pydicom.dcmread(dicom_path)

    patient = extract_custom_patient_info(ds)
    study = extract_study_info(ds)
    provider = extract_provider_info(ds)
    findings = extract_findings(ds)

    return {
        "message_type": "fhir",
        "patient": patient,
        "study": study,
        "provider": provider,
        "findings": findings
    }

if __name__ == "__main__":
    import json

    dicom_path = "/media/zain/New Volume/PycharmProjects/DataFormation/hl7 work/brayz_sr.dcm"
    output_json = generate_custom_json(dicom_path)

    print(output_json)

    # Write to file
    output_file = "custom_output.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output_json, f, indent=2, ensure_ascii=False)

    print(f"Custom JSON message written to {output_file}")



