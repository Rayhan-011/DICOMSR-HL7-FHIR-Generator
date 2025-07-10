from flask import Flask, request, jsonify, Response
from flasgger import Swagger, swag_from
import pydicom
import uuid
import os
import json

import tempfile
import logging
from fhir_message_genrate import dicom_to_fhir  # Import the function from your DICOM SR parser module
from dicom_to_json import generate_custom_json
from hl7_msg_former import create_hl7_message
import re
from flask_cors import CORS


app = Flask(__name__)
CORS(app)
swagger = Swagger(app)

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


def build_fhir_report(parsed):

    """
    Build a FHIR Bundle containing Patient, DiagnosticReport and Observations
    Returns standard FHIR Bundle resource with properly formatted UUIDs
    """

    # Remove <html> and <body> tags
    for finding in parsed["findings"]:
        if finding["type"] == "html":
            value = finding["value"]
            # Remove opening and closing <html> and <body> tags using regex
            value = re.sub(r'</?(html|body)>', '', value, flags=re.IGNORECASE)
            finding["value"] = value.strip()

    # Generate proper UUIDs for all resources
    patient_id = "4db92043-8ad9-4b0a-a5ac-2305555f452a"  # Preserve original if already UUID
    report_id = str(uuid.uuid4())  # Generate new UUID for report
    observation_ids = [str(uuid.uuid4()) for _ in parsed["findings"]]  # Generate UUIDs for observations

    # Helper function to generate narrative text
    def generate_narrative(resource_type, resource_data):
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

    # Patient resource with narrative
    patient_resource = {
        "resourceType": "Patient",
        "id": patient_id.lower(),  # Ensure lowercase
        "gender": parsed["patient"]["gender"],
        "birthDate": parsed["patient"]["birth_date"],
        "identifier": [{
            "system": "http://hospital.smarthealth.org/patient-id",
            "value": parsed["patient"]["id"]
        }],
        "name": [{
            "family": parsed["patient"]["name"][0]["family"],
            "given": parsed["patient"]["name"][0]["given"]
        }],
        "text": generate_narrative("Patient", {
            "name": [{
                "family": parsed["patient"]["name"][0]["family"],
                "given": parsed["patient"]["name"][0]["given"]
            }],
            "identifier": [{
                "system": "http://hospital.smarthealth.org/patient-id",
                "value": parsed["patient"]["id"]
            }]
        })
    }

    # Observations with proper UUIDs and narrative
    observations = []
    for idx, finding in enumerate(parsed["findings"]):
        value = finding if isinstance(finding, str) else finding.get("value", str(finding))
        observation = {
            "resourceType": "Observation",
            "id": observation_ids[idx],
            "status": "final",
            "code": {
                "coding": [{
                    "system": "http://loinc.org"
                }]
            },
            "valueString": value,
            "effectiveDateTime": parsed["study"]["date"],
            "subject": {
                "reference": f"Patient/{patient_id.lower()}"
            },
            "performer": [
                {
                 "display": "Radiologist System"
                }
            ],
            "text": generate_narrative("Observation", {
                "code": {
                    "coding": [{
                        "system": "http://loinc.org",
                        "code": "24606-6",
                        "display": "MG Breast Screening"
                    }]
                },
                "valueString": value
            })
        }
        observations.append(observation)

    # DiagnosticReport with proper UUID and narrative
    report = {
        "resourceType": "DiagnosticReport",
        "id": report_id,
        "status": "final",
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "24606-6",
                "display": "MG Breast Screening"
            }]
        },
        "subject": {
            "reference": f"Patient/{patient_id.lower()}"
        },
        "effectiveDateTime": parsed["study"]["date"],
        "performer": [{
            "display": parsed.get("provider", {}).get("name") or "Radiologist System"
        }],
        "result": [{
            "reference": f"Observation/{obs_id}"
        } for obs_id in observation_ids],
        "text": generate_narrative("DiagnosticReport", {
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "24606-6",
                    "display": "MG Breast Screening"
                }]
            }
        })
    }

    # Create FHIR Bundle with properly formatted UUIDs
    bundle = {
        "resourceType": "Bundle",
        "id": str(uuid.uuid4()),
        "type": "collection",
        "entry": [
            {
                "fullUrl": f"urn:uuid:{patient_id.lower()}",  # Ensure lowercase
                "resource": patient_resource
            },
            {
                "fullUrl": f"urn:uuid:{report_id}",
                "resource": report
            },
            *[{
                "fullUrl": f"urn:uuid:{obs_id}",
                "resource": obs
            } for obs_id, obs in zip(observation_ids, observations)]
        ]
    }

    return bundle


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
                ds = pydicom.dcmread(dicom_path)
                hl7_msg = create_hl7_message(ds)
                os.remove(dicom_path)

                if hl7_msg is None:
                    return jsonify({"error": "Failed to generate HL7 from DICOM"}), 500
                return Response(hl7_msg, mimetype='application/hl7-v2')

            else:
                hl7_msg = create_hl7_message(parsed_json)

                return Response(hl7_msg, mimetype='application/hl7-v2')

        elif message_type == "fhir":
            if dicom_path:
                ds = pydicom.dcmread(dicom_path)
                fhir_msg = dicom_to_fhir(ds)
                os.remove(dicom_path)

                if fhir_msg is None:
                    return jsonify({"error": "Failed to generate FHIR from DICOM"}), 500
                return jsonify(fhir_msg)
            else:
                return jsonify(build_fhir_report(parsed))
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


if __name__ == '__main__':
    app.run(port=5000, debug=True)



