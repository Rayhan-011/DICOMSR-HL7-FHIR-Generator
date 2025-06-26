# 🩻 Mammogram SR HL7 and FHIR Message Generator

*A Python-based service to extract clinical findings from mammogram DICOM SR files and generate standardized HL7 and FHIR messages*

---

## 📌 1. Overview

### Objective

This project provides a standards-compliant service to:

* Extract structured clinical information from mammogram DICOM SR files.
* Generate HL7 v2.3 ORU^R01 messages and FHIR R4 DiagnosticReport bundles.

It enables smooth integration of imaging workflows with EHR/EMR systems in compliance with global interoperability standards.

### Target Users

* Health IT developers
* Radiology information systems (RIS)
* PACS vendors
* Clinical research tools

---

## 🏗️ 2. System Architecture

```plaintext
             ┌──────────────┐
             │ DICOM SR /   │
             │ JSON Input   │
             └─────┬────────┘
                   │
                   ▼
        ┌────────────────────┐
        │ Flask API Service  │
        ├────────────────────┤
        │ - pydicom parser   │
        │ - HL7 generator    │
        │ - FHIR generator   │
        │ - Internal parsing │
        │   for mammogram SR │
        │   DICOM files      │
        └─────┬──────────────┘
              │
              ▼
 ┌────────────────────┐  ┌────────────────────┐
 │ HL7 ORU^R01 Output │  │ FHIR R4 JSON Output│
 └────────────────────┘  └────────────────────┘
```
 └────────────────────┘  └────────────────────┘

---

## 📂 3. Code Structure and Logic

### dicom_to_fhir.py

This module provides functions to convert DICOM Structured Report (SR) files into FHIR R4 DiagnosticReport bundles. Key functions include:

- `generate_uuid()`: Generates UUIDs for FHIR resources.
- `format_dicom_date(date_str)`: Converts DICOM date strings to FHIR-compliant date format.
- `extract_patient_info(ds)`: Extracts patient demographics and identifiers from the DICOM dataset.
- `extract_observations(ds, patient_ref)`: Recursively extracts observations from the DICOM SR ContentSequence.
- `create_diagnostic_report(patient_ref, observations, ds)`: Creates a FHIR DiagnosticReport resource linking patient and observations.
- `dicom_to_fhir(dicom_path)`: Main function that reads a DICOM file and returns a FHIR message dictionary.

**Example usage:**

```python
from dicom_to_fhir import dicom_to_fhir

fhir_message = dicom_to_fhir("path/to/dicom_file.dcm")
print(fhir_message)
```

### dicom_to_json.py

This module extracts patient, study, provider, and findings information from DICOM SR files and generates a custom JSON message. Key functions include:

- `extract_custom_patient_info(ds)`: Extracts patient information for JSON output.
- `extract_study_info(ds)`: Extracts study details including procedure codes.
- `extract_provider_info(ds)`: Extracts referring provider information.
- `extract_findings(ds)`: Recursively extracts textual findings from the DICOM ContentSequence.
- `generate_custom_json(dicom_path)`: Main function to generate the custom JSON message.

**Example usage:**

```python
from dicom_to_json import generate_custom_json

custom_json = generate_custom_json("path/to/dicom_file.dcm")
print(custom_json)
```

### hl7_msg_former.py

This module constructs HL7 v2.5 message segments (`MSH`, `PID`, `OBR`, `ZDS`, `OBX`) from either JSON data or DICOM SR datasets. It assembles these segments into a complete HL7 ORU^R01 message.

Key functions include:

- `create_hl7_msh_segment(data)`: Creates the MSH segment.
- `create_hl7_pid_segment(data)`: Creates the PID segment.
- `create_obr_segment(data)`: Creates the OBR segment.
- `create_zds_segment(data)`: Creates the ZDS segment.
- `create_obx_segments(data)`: Creates OBX segments from findings.
- `create_hl7_message(data)`: Assembles all segments into a full HL7 message.

**Example usage:**

```python
from hl7_msg_former import create_hl7_message

hl7_message = create_hl7_message(json_data_or_dicom_dataset)
print(hl7_message)
```

### obx_former.py

This helper module generates OBX segments specifically from mammogram DICOM SR datasets. It is used internally by `hl7_msg_former.py` to build observation segments.

### DICOMSR_HL7_FHIR_Writer_Swagger.py

This is the main Flask API service that provides the `/generate-message` endpoint. It supports generating HL7, FHIR, or JSON messages from uploaded DICOM SR or JSON files. Features include:

- HL7 special character escaping.
- Parsing mammogram SR DICOM files.
- Building HL7 ORU^R01 messages.
- Building FHIR DiagnosticReport resources.
- Swagger UI integration for API documentation.
- Helper functions for DICOM value extraction and formatting.
- HL7 message generation from DICOM SR.
- Flask app run configuration.

**API Endpoint Usage Example:**

```bash
curl -X POST http://localhost:5000/generate-message \
  -F "message_type=fhir" \
  -F "file=@path/to/dicom_file.dcm"
```



---

## 🔧 4. API Documentation

### Endpoint

`POST /generate-message`

#### Content Types

* `multipart/form-data` with DICOM/JSON file
* `application/json` body (optional for JSON-based clients)

#### Parameters

| Parameter      | Type   | Required | Description                 |
| -------------- | ------ | -------- | --------------------------- |
| `message_type` | string | ✅        | `hl7`, `fhir`, or `json`    |
| `file`         | file   | ✅        | DICOM SR or JSON input file |

#### Response Format

* `200 OK`: Returns HL7 string or FHIR resources.
* `400`: Missing or invalid input.
* `500`: Processing or parsing error.

---

## 📜 5. HL7 and FHIR Compliance

### HL7 v2.3 ORU^R01

* Segments: `MSH`, `PID`, `OBR`, `OBX`
* Text observations encoded as `TX`
* Uses:

  * `PatientID` → `PID`
  * `Findings` → `OBX[n]`
  * `Procedure Code` → `OBR-4`

### FHIR R4

* Resources generated:

  * `Patient`
  * `Observation[]`
  * `DiagnosticReport`
* Uses `LOINC` codes (e.g., `24606-6`)
* Linked via FHIR references (e.g., `Observation.subject → Patient.id`)

---

## 🛠️ 6. Installation & Deployment

### Prerequisites

* Python 3.7+
* pip

### Installation

```bash
pip install flask flasgger pydicom
```

### Run Server

```bash
python DICOMSR_HL7_FHIR_Writer_Swagger.py
```

Swagger UI:
👉 `http://localhost:5000/apidocs`

---

## 🧪 7. Testing & Validation

### ✅ Example Curl Request

```bash
curl -X POST http://localhost:5000/generate-message \
  -F "message_type=fhir" \
  -F "file=@Input_Message.json;type=application/json"
```

### ✅ Postman Collection

Postman JSON export file available upon request.

### ✅ HL7 Validation

Use:

* [NIST HL7 Validator](https://hl7v2tools.nist.gov/)
* HL7 Validator tool 
* https://freeonlineformatter.com/hl7-validator

### ✅ FHIR Validation

Use:

* [HL7 FHIR Validator JAR](https://confluence.hl7.org/display/FHIR/Using+the+FHIR+Validator)
* [HAPI FHIR Server](https://hapi.fhir.org/)
* FHIR Validator : https://validator.fhir.org/

---

## 🤝 8. Development & Contribution

### File Structure

```plaintext
├── DICOMSR_HL7_FHIR_Writer_Swagger.py  # Main Flask app
├── dicom_to_fhir.py                     # DICOM to FHIR conversion module
├── dicom_to_json.py                     # DICOM to custom JSON conversion module
├── README.md                           # Project documentation
├── brayz_sr.dcm                       # Sample DICOM SR file
├── Input_Message.json                 # Sample JSON input
```

### Contribution Guide

* Fork and clone the repository
* Branch: `feature/<feature-name>`
* Use Black or PEP8 formatting
* Submit PR with description and test cases

---

## ⚖️ 9. License

This project is licensed under the **MIT License**. You are free to use, modify, and distribute.

---

## 📚 10. Appendix

### 📁 Sample JSON Input

```json
{
  "message_type": "fhir",
  "patient": {
    "id": "123456",
    "name": [{ "given": ["Jane"], "family": "Doe" }],
    "gender": "female",
    "birth_date": "1985-03-15"
  },
  "study": {
    "date": "2025-05-12",
    "accession_number": "ACC20250512001",
    "modality": "MG",
    "procedure_code": {
      "code": "24606-6",
      "system": "http://loinc.org",
      "display": "Mammogram Diagnostic Report"
    }
  },
  "provider": {
    "name": "Dr. Emily Carter",
    "id": "PROV001",
    "department": "Radiology"
  },
  "findings": [
    "Suspicious mass in right breast, upper outer quadrant.",
    "Left breast tissue appears normal.",
    "BI-RADS 4: Suspicious abnormality. Consider biopsy."
  ]
}
