from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

# -----------------------------
# 1. Setup analyzer and anonymizer
# -----------------------------
analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

# Define all entity types supported by Presidio
all_entities = [
    # Global
    "CREDIT_CARD", "CRYPTO", "DATE_TIME", "EMAIL_ADDRESS", "IBAN_CODE",
    "IP_ADDRESS", "NRP", "LOCATION", "PERSON", "PHONE_NUMBER", "MEDICAL_LICENSE", "URL",
    # USA
    "US_BANK_NUMBER", "US_DRIVER_LICENSE", "US_ITIN", "US_PASSPORT", "US_SSN",
    # UK
    "UK_NHS", "UK_NINO",
    # Spain
    "ES_NIF", "ES_NIE",
    # Italy
    "IT_FISCAL_CODE", "IT_DRIVER_LICENSE", "IT_VAT_CODE", "IT_PASSPORT", "IT_IDENTITY_CARD",
    # Poland
    "PL_PESEL",
    # Singapore
    "SG_NRIC_FIN", "SG_UEN",
    # Australia
    "AU_ABN", "AU_ACN", "AU_TFN", "AU_MEDICARE",
    # India
    "IN_PAN", "IN_AADHAAR", "IN_VEHICLE_REGISTRATION", "IN_VOTER", "IN_PASSPORT", "IN_GSTIN",
    # Finland
    "FI_PERSONAL_IDENTITY_CODE",
    # Korea
    "KR_RRN",
    # Thailand
    "TH_TNIN",
]

# Use the analyzer on some sample text
text = "My phone number is 212-555-5555 and my email is john.doe@example.com and my PAN is ABCDE1234F."
results = analyzer.analyze(
    text=text,
    entities=all_entities,
    language='en'
)

anonymized = anonymizer.anonymize(
    text=text,
    analyzer_results=results,
 
)

print("---- REPLACED TEXT ----")
print(anonymized.text)   # <-- this gives replaced/masked text

print("\n---- RAW ANALYSIS RESULTS ----")
for r in results:
    print(r)
