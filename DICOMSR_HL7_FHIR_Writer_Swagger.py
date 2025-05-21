from flask import Flask, request, jsonify
from flasgger import Swagger, swag_from
import pydicom
import uuid
import os
import json
import tempfile
from datetime import datetime
import logging
from dicom_to_fhir import dicom_to_fhir  # Import the function from your DICOM SR parser module
from dicom_to_json import generate_custom_json

app = Flask(__name__)
swagger = Swagger(app)

def escape_hl7(text):
    """
    Escape special HL7 characters in the given text.
    HL7 uses special characters like \, |, ^, & which need to be escaped.
    
    Args:
        text (str): Input text to escape.
        
    Returns:
        str: Escaped text.
    """
    return text.replace('\\', '\\E\\').replace('|', '\\F\\').replace('^', '\\S\\').replace('&', '\\T\\')

def parse_mammo_sr(dcm_file):
    """
    Parse a mammogram Structured Report (SR) DICOM file to extract relevant information.
    
    Args:
        dcm_file (str): Path to the DICOM SR file.
        
    Returns:
        dict: Parsed data including patient info, study details, provider info, and findings.
    """
    ds = pydicom.dcmread(dcm_file)
    findings = []
    if 'ContentSequence' in ds:
        for item in ds.ContentSequence:
            text = item.get('TextValue') or item.get('CodeMeaning')
            if text:
                findings.append(str(text))

    gender_map = {'M': 'male', 'F': 'female', 'O': 'other'}
    dicom_gender = getattr(ds, 'PatientSex', 'U')
    fhir_gender = gender_map.get(dicom_gender, 'unknown')

    return {
        "patient": {
            "id": ds.PatientID,
            "name": [{"given": ["Jane"], "family": "Doe"}],
            "gender": fhir_gender,
            "birth_date": ds.get('PatientBirthDate', '0000-01-01')
        },
        "study": {
            "date": ds.StudyDate,
            "accession_number": getattr(ds, 'AccessionNumber', f"ACC-{uuid.uuid4()}"),
            "modality": getattr(ds, 'Modality', 'MG'),
            "procedure_code": {
                "code": "24606-6",
                "system": "http://loinc.org",
                "display": "Mammogram Diagnostic Report"
            }
        },
        "provider": {
            "id": "PROV001",
            "name": "Dr. Emily Carter",
            "department": "Radiology"
        },
        "findings": findings
    }

def build_hl7_message(parsed):
    """
    Build an HL7 ORU^R01 message string from parsed mammogram data.
    
    Args:
        parsed (dict): Parsed mammogram data.
        
    Returns:
        str: HL7 message string.
    """
    patient = parsed['patient']
    study = parsed['study']
    provider = parsed['provider']

    gender_map = {'male': 'M', 'female': 'F', 'other': 'O', 'unknown': 'U'}
    hl7_gender = gender_map.get(patient.get('gender', 'unknown'), 'U')
    birth_date = patient.get('birth_date', '')

    pid = f"PID|||{patient['id']}||{patient['name'][0]['family']}^{patient['name'][0]['given'][0]}||{birth_date}|{hl7_gender}"
    obr = f"OBR|1|{study['accession_number']}||{study['procedure_code']['code']}^{study['procedure_code']['display']}||{study['date']}|||||||{provider['name']}||||||{study.get('modality', '')}"

    obx = ""
    for idx, text in enumerate(parsed['findings']):
        obx += f"OBX|{idx+1}|TX|||{escape_hl7(text)}||||||F\n"

    msh = f"MSH|^~\\&|MAMMO_SYS|MAMMO_HOSP|HL7_RECEIVER|HOSP|{datetime.now().strftime('%Y%m%d%H%M%S')}||ORU^R01|{uuid.uuid4()}|P|2.3"
    return f"{msh}\n{pid}\n{obr}\n{obx}".strip()

def build_fhir_report(parsed):
    """
    Build a FHIR DiagnosticReport resource with associated Patient and Observation resources.
    
    Args:
        parsed (dict): Parsed mammogram data.
        
    Returns:
        dict: Dictionary containing Patient, DiagnosticReport, and Observations resources.
    """
    patient_data = parsed['patient']
    study = parsed['study']
    provider = parsed['provider']
    patient_id = str(uuid.uuid4())

    patient_resource = {
        "resourceType": "Patient",
        "id": patient_id,
        "gender": patient_data.get("gender", "unknown"),
        "birthDate": patient_data.get("birth_date", "1970-01-01"),
        "identifier": [{
            "system": "http://hospital.smarthealth.org/patient-id",
            "value": patient_data["id"]
        }],
        "name": [{
            "family": n.get("family", "Doe"),
            "given": n.get("given", ["Jane"])
        } for n in patient_data.get("name", [])]
    }

    observations = []
    for idx, text in enumerate(parsed["findings"]):
        obs_id = f"obs-{idx+1}"
        obs = {
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": study["procedure_code"]["code"],
                    "display": "Mammogram observation"
                }]
            },
            "valueString": text,
            "subject": {"reference": f"Patient/{patient_id}"}
        }
        observations.append(obs)

    report = {
        "resourceType": "DiagnosticReport",
        "id": "report-1",
        "status": "final",
        "code": {
            "coding": [{
                "system": study["procedure_code"]["system"],
                "code": study["procedure_code"]["code"],
                "display": study["procedure_code"]["display"]
            }]
        },
        "subject": {"reference": f"Patient/{patient_id}"},
        "effectiveDateTime": study["date"],
        "performer": [{"display": provider["name"]}],
        "result": [{"reference": f"Observation/{obs['id']}"} for obs in observations]
    }

    return {
        "patient": patient_resource,
        "diagnostic_report": report,
        "observations": observations
    }

@app.route('/generate-message', methods=['POST'])
@swag_from({
    'parameters': [
        {"name": "message_type", "in": "formData", "type": "string", "required": True, "enum": ["hl7", "fhir", "json"]},
        {"name": "file", "in": "formData", "type": "file", "required": False}
    ],
    'responses': {
        200: {"description": "Success"},
        400: {"description": "Bad request"},
        500: {"description": "Server error"}
    }
})
def generate_message():
    try:
        message_type = None
        parsed = None
        hl7_msg = None
        dicom_path = None

        if request.content_type and 'application/json' in request.content_type:
            data = request.get_json()
            message_type = data.get('message_type', '').lower()
            parsed = {
                "patient": data["patient"],
                "provider": data["provider"],
                "study": data["study"],
                "findings": data["findings"]
            }
        elif 'file' in request.files:
            file = request.files['file']
            message_type = request.form.get('message_type', '').lower()
            if file.filename.endswith('.dcm'):
                dicom_path = os.path.join(tempfile.gettempdir(), file.filename)
                file.save(dicom_path)
                parsed = parse_mammo_sr(dicom_path)
            elif file.filename.endswith('.json'):
                parsed_json = json.load(file)
                parsed = {
                    "patient": parsed_json["patient"],
                    "provider": parsed_json["provider"],
                    "study": parsed_json["study"],
                    "findings": parsed_json["findings"]
                }
            else:
                return jsonify({"error": "Unsupported file type"}), 400
        else:
            return jsonify({"error": "No input provided"}), 400

        if message_type == "hl7":
            if dicom_path:
                hl7_msg = generate_hl7_from_mammo_sr(dicom_path)
                os.remove(dicom_path)
                if hl7_msg is None:
                    return jsonify({"error": "Failed to generate HL7 from DICOM"}), 500
                return jsonify({"hl7": hl7_msg})
            else:
                return jsonify({"hl7": build_hl7_message(parsed)})
        elif message_type == "fhir":
            if dicom_path:
                fhir_msg = dicom_to_fhir(dicom_path)
                os.remove(dicom_path)
                if fhir_msg is None:
                    return jsonify({"error": "Failed to generate FHIR from DICOM"}), 500
                return jsonify(fhir_msg)
            else:
                return jsonify({"fhir": build_fhir_report(parsed)})
        elif message_type == "json":
            if file.filename.endswith('.dcm'):
                parsed = generate_custom_json(dicom_path)
            return jsonify({"parsed": parsed})
        else:
            return jsonify({"error": "Invalid message_type"}), 400
    except Exception as e:
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def format_patient_name(ds):
    patient_name = ds.PatientName
    if patient_name == 'Anonymous Patient':
        return 'Anonymous^Patient'
    else:
        parts = str(patient_name).split('^')
        if len(parts) >= 2:
            return f"{parts[0]}^{parts[1]}"
        else:
            return f"{patient_name}^"

def get_dicom_value(ds, tag, default=''):
    """
    Safely retrieves the DICOM tag value as a string.
    
    Args:
        ds (pydicom.Dataset): The DICOM dataset.
        tag (Union[int, Tuple[int, int]]): DICOM tag.
        default (str): Default value if tag not found.
        
    Returns:
        str: Value of the DICOM tag or default.
    """
    try:
        value = ds.get(tag, default)
        if isinstance(value, pydicom.DataElement):
            value = value.value
        if isinstance(value, (list, tuple)):
            return ','.join(map(str, value))
        return str(value)
    except Exception as e:
        logger.warning(f"Failed to retrieve DICOM tag {tag}: {str(e)}")
        return default

def format_hl7_datetime(dt):
    """
    Formats a datetime object into the HL7 standard format YYYYMMDDHHMMSS.
    
    Args:
        dt (datetime): Datetime object.
        
    Returns:
        str: Formatted datetime string.
    """
    try:
        return dt.strftime('%Y%m%d%H%M%S')
    except Exception as e:
        logger.warning(f"Failed to format datetime: {str(e)}")
        return datetime.now().strftime('%Y%m%d%H%M%S')

def extract_observations(content_seq):
    """
    Recursively extracts TextValue from DICOM ContentSequence.
    
    Args:
        content_seq (Sequence): DICOM ContentSequence.
        
    Returns:
        List[str]: List of extracted text values.
    """
    observations = []
    if not content_seq:
        return observations
    for item in content_seq:
        if hasattr(item, 'TextValue'):
            text_value = get_dicom_value(item, 'TextValue', '')
            if text_value:
                observations.append(text_value)
        if hasattr(item, 'ContentSequence'):
            observations.extend(extract_observations(item.ContentSequence))
    return observations

def extract_image_quality(content_sequence):
    """
    Recursively extract Image Quality descriptions from the SR.
    
    Args:
        content_sequence (Sequence): DICOM ContentSequence.
        
    Returns:
        List[str]: List of image quality descriptions.
    """
    results = []

    def recursive_search(sequence):
        for item in sequence:
            concept = getattr(item, "ConceptNameCodeSequence", [{}])[0]
            code_meaning = getattr(concept, "CodeMeaning", "").lower()
            if "image quality" in code_meaning:
                quality = getattr(item, "TextValue", "") or getattr(item, "ConceptCodeSequence", [{}])[0].get("CodeMeaning", "")
                if quality:
                    results.append(quality)
            if hasattr(item, "ContentSequence"):
                recursive_search(item.ContentSequence)

    recursive_search(content_sequence)
    return results if results else ["No image quality info found"]

def extract_measurement_values(content_sequence):
    """
    Extracts measurement values with their units and labels from the SR.
    
    Args:
        content_sequence (Sequence): DICOM ContentSequence.
        
    Returns:
        List[str]: List of measurement descriptions.
    """
    results = []

    def recursive_search(sequence):
        for item in sequence:
            if getattr(item, "ValueType", "") == "NUM":
                concept = getattr(item, "ConceptNameCodeSequence", [{}])[0]
                label = getattr(concept, "CodeMeaning", "Unknown measurement")

                numeric_value = getattr(item, "NumericValue", None)
                units = getattr(item, "MeasuredValueSequence", [{}])[0].get("MeasurementUnitsCodeSequence", [{}])[0].get("CodeValue", "")
                unit_meaning = getattr(item, "MeasuredValueSequence", [{}])[0].get("MeasurementUnitsCodeSequence", [{}])[0].get("CodeMeaning", "")

                if numeric_value is not None:
                    result_str = f"{label}: {numeric_value} {unit_meaning or units}"
                    results.append(result_str)
            if hasattr(item, "ContentSequence"):
                recursive_search(item.ContentSequence)

    recursive_search(content_sequence)
    return results if results else ["No measurements found"]

def generate_hl7_from_mammo_sr(dicom_file_path):
    """
    Generates an HL7 message from a Mammography DICOM SR file.
    
    Args:
        dicom_file_path (str): Path to the DICOM SR file.
        
    Returns:
        str or None: HL7 message string or None if failure.
    """
    try:
        ds = pydicom.dcmread(dicom_file_path)
    except Exception as e:
        logger.error(f"Failed to read DICOM file: {str(e)}")
        return None

    patient_id = get_dicom_value(ds, (0x0010, 0x0020), 'secret ID')

    patient_name = get_dicom_value(ds, (0x0010, 0x0010), 'Anonymous^Patient')
    if patient_name != 'Anonymous^Patient':
        parts = patient_name.split(' ')
        if len(parts) >= 2:
            patient_name = f"{parts[0]}^{parts[1]}"
        else:
            patient_name = f"{parts[0]}^"

    patient_dob = str(ds.get('PatientBirthDate', '00000101'))
    if '-' in patient_dob:
        patient_dob = patient_dob.replace('-', '')
    if len(patient_dob) != 8:
        patient_dob = ''

    patient_sex = get_dicom_value(ds, (0x0010, 0x0040), '')
    if patient_sex not in ['M', 'F', 'O', 'U']:
        patient_sex = patient_sex.upper()

    accession_number = getattr(ds, 'AccessionNumber', 'UNKNOWN')
    study_date = getattr(ds, 'StudyDate', '')
    study_time = getattr(ds, 'StudyTime', '000000')

    dt_str = study_date + study_time
    try:
        dt_study = datetime.strptime(dt_str, '%Y%m%d%H%M%S')
    except ValueError:
        logger.warning("Invalid study date/time, using current datetime")
        dt_study = datetime.now()

    hl7_date = format_hl7_datetime(dt_study)

    observations = extract_observations(getattr(ds, 'ContentSequence', []))
    if not observations:
        observations = ["No observations extracted"]

    image_quality = extract_image_quality(getattr(ds, 'ContentSequence', []))
    measurements = extract_measurement_values(getattr(ds, 'ContentSequence', []))

    message_control_id = str(uuid.uuid4())
    msh = f"MSH|^~\\&|MAMMO_SYS|MAMMO_HOSP|HL7_RECEIVER|HOSP|{hl7_date}||ORU^R01|{message_control_id}|P|2.3|"
    pid = f"PID|||{patient_id}||{patient_name}||{patient_dob}|{patient_sex}||"
    obr = f"OBR|1||{accession_number}|24606-6^Mammogram Diagnostic Report^LN|{hl7_date}|||||||||Dr. Emily Carter||||||MG|"

    obx_segments = []
    index = 1
    for obs in observations:
        clean_obs = obs.replace('\n', ' ').replace('\r', '').strip()
        obx_segments.append(f"OBX|{index}|TX|||{clean_obs}||||||F|")
        index += 1

    for quality in image_quality:
        clean_quality = quality.replace('\n', ' ').replace('\r', '').strip()
        obx_segments.append(f"OBX|{index}|TX|||Image Quality: {clean_quality}||||||F|")
        index += 1

    for meas in measurements:
        clean_meas = meas.replace('\n', ' ').replace('\r', '').strip()
        obx_segments.append(f"OBX|{index}|TX|||Measurement: {clean_meas}||||||F|")
        index += 1

    hl7_message = '\n'.join([msh, pid, obr] + obx_segments)
    return hl7_message

if __name__ == '__main__':
    app.run(port=5000, debug=True)

