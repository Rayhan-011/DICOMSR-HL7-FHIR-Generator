from flask import Flask, request, jsonify
from flasgger import Swagger, swag_from
import pydicom
import uuid
import os
import json
import tempfile
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)
# Initialize Swagger for API documentation
swagger = Swagger(app)

# === HL7 Special Character Escaper ===
def escape_hl7(text):
    """
    Escape special HL7 characters in the given text.
    HL7 uses special characters like \, |, ^, & which need to be escaped.
    """
    return text.replace('\\', '\\E\\').replace('|', '\\F\\').replace('^', '\\S\\').replace('&', '\\T\\')

# === DICOM SR Parser ===
def parse_mammo_sr(dcm_file):
    """
    Parse a mammogram Structured Report (SR) DICOM file to extract relevant information.
    Args:
        dcm_file (str): Path to the DICOM SR file.
    Returns:
        dict: Parsed data including patient info, study details, provider info, and findings.
    """
    ds = pydicom.dcmread(dcm_file)  # Read DICOM file
    findings = []
    if 'ContentSequence' in ds:
        for item in ds.ContentSequence:
            # Extract text from TextValue or CodeMeaning in ContentSequence
            text = item.get('TextValue') or item.get('CodeMeaning')
            if text:
                findings.append(str(text))

    # Map DICOM gender codes to FHIR gender values
    gender_map = {'M': 'male', 'F': 'female', 'O': 'other'}
    dicom_gender = getattr(ds, 'PatientSex', 'U')
    fhir_gender = gender_map.get(dicom_gender, 'unknown')

    # Construct parsed dictionary with patient, study, provider, and findings
    return {
        "patient": {
            "id": ds.PatientID,
            "name": [{"given": ["Jane"], "family": "Doe"}],  # Placeholder name
            "gender": fhir_gender,
            "birth_date": ds.get('PatientBirthDate', '19700101')
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

# === HL7 Generator ===
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

    # Map FHIR gender to HL7 gender codes
    gender_map = {'male': 'M', 'female': 'F', 'other': 'O', 'unknown': 'U'}
    hl7_gender = gender_map.get(patient.get('gender', 'unknown'), 'U')
    birth_date = patient.get('birth_date', '')

    # Construct PID segment with patient info
    pid = f"PID|||{patient['id']}||{patient['name'][0]['family']}^{patient['name'][0]['given'][0]}||{birth_date}|{hl7_gender}"
    # Construct OBR segment with study and provider info
    obr = f"OBR|1|{study['accession_number']}||{study['procedure_code']['code']}^{study['procedure_code']['display']}||{study['date']}|||||||{provider['name']}||||||{study.get('modality', '')}"

    # Construct OBX segments for each finding, escaping HL7 special characters
    obx = ""
    for idx, text in enumerate(parsed['findings']):
        obx += f"OBX|{idx+1}|TX|||{escape_hl7(text)}||||||F\n"

    # Construct MSH segment with message metadata
    msh = f"MSH|^~\\&|MAMMO_SYS|MAMMO_HOSP|HL7_RECEIVER|HOSP|{datetime.now().strftime('%Y%m%d%H%M%S')}||ORU^R01|{uuid.uuid4()}|P|2.3"
    # Combine all segments into final HL7 message string
    return f"{msh}\n{pid}\n{obr}\n{obx}".strip()

# === FHIR Generator (Dict-based) ===
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
    patient_id = str(uuid.uuid4())  # Generate unique patient resource ID

    # Create Patient resource dictionary
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
    # Create Observation resources for each finding
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

    # Create DiagnosticReport resource linking to Patient and Observations
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

    # Return all resources as a dictionary
    return {
        "patient": patient_resource,
        "diagnostic_report": report,
        "observations": observations
    }

# === API Endpoint ===
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
    """
    API endpoint to generate HL7 or FHIR messages from mammogram data.
    Accepts JSON payload or file upload (.dcm or .json).
    Returns the requested message format.
    """
    try:
        message_type = None
        parsed = None

        # Handle JSON input
        if request.content_type and 'application/json' in request.content_type:
            data = request.get_json()
            message_type = data.get('message_type', '').lower()
            parsed = {
                "patient": data["patient"],
                "provider": data["provider"],
                "study": data["study"],
                "findings": data["findings"]
            }

        # Handle file upload input
        elif 'file' in request.files:
            file = request.files['file']
            message_type = request.form.get('message_type', '').lower()
            if file.filename.endswith('.dcm'):
                # Save uploaded DICOM file temporarily and parse
                temp_path = os.path.join(tempfile.gettempdir(), file.filename)
                file.save(temp_path)
                parsed = parse_mammo_sr(temp_path)
                os.remove(temp_path)
            elif file.filename.endswith('.json'):
                # Load JSON file and parse
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

        # Generate message based on requested type
        if message_type == "hl7":
            return jsonify({"hl7": build_hl7_message(parsed)})
        elif message_type == "fhir":
            return jsonify({"fhir": build_fhir_report(parsed)})
        elif message_type == "json":
            return jsonify({"parsed": parsed})
        else:
            return jsonify({"error": "Invalid message_type"}), 400

    except Exception as e:
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500

# Run the Flask app on port 5000 with debug enabled
if __name__ == '__main__':
    app.run(port=5000, debug=True)
