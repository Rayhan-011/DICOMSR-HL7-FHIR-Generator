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
        └─────┬──────────────┘
              │
              ▼
 ┌────────────────────┐  ┌────────────────────┐
 │ HL7 ORU^R01 Output │  │ FHIR R4 JSON Output│
 └────────────────────┘  └────────────────────┘
```

---

## 🔧 3. API Documentation

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

## 📜 4. HL7 and FHIR Compliance

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

## 🛠️ 5. Installation & Deployment

### Prerequisites

* Python 3.7+
* pip

### Installation

```bash
pip install flask flasgger pydicom
```

### Run Server

```bash
python HL7_FHIRWriter_Swagger.py
```

Swagger UI:
👉 `http://localhost:5000/apidocs`

---

## 🧪 6. Testing & Validation

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
* HL7 Inspector tool

### ✅ FHIR Validation

Use:

* [HL7 FHIR Validator JAR](https://confluence.hl7.org/display/FHIR/Using+the+FHIR+Validator)
* [HAPI FHIR Server](https://hapi.fhir.org/)

---

## 🤝 7. Development & Contribution

### File Structure

```plaintext
├── HL7_FHIRWriter_Swagger.py      # Main Flask app
├── sample_mammogram_sr.dcm        # DICOM SR sample
├── Input_Message.json             # JSON test input
├── README.md                      # Project documentation
```

### Contribution Guide

* Fork and clone the repository
* Branch: `feature/<feature-name>`
* Use Black or PEP8 formatting
* Submit PR with description and test cases

---

## ⚖️ 8. License

This project is licensed under the **MIT License**. You are free to use, modify, and distribute.

---

## 📚 9. Appendix

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

